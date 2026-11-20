"""Fixed-price support factorial; no historical activity-threshold re-sweep."""
from pathlib import Path
from dataclasses import asdict,replace
import hashlib,json,os,sys
import numpy as np
import pandas as pd
from autogrid.engine import run_backtest,AccountState
from autogrid.strategy import StrategySpec
from source_activity_context_20261119 import load_prepared as old_prepared,BASE
from hourly_clock_audit_20261119 import parse_source
from source_activity_signals_20261119 import signals as old_signals
from availability_signals_20261119 import candidates,signals,support,FUTURE_HYPOTHESES
from availability_runtime_20261119 import atomic_json as dump,restore_state,resume_state,sha,clean
from inverse_etf_retry_20261116 import CFG
from session_signal_provenance import mask_session_signals

OUT=Path('runs/availability_ablation_20261119_0800');PREV=Path('runs/source_activity_grid_20261119_0700')
DEV=[('2025-01-01','2025-07-01'),('2025-07-01','2026-01-01')];DIAG=('2026-01-01','2026-11-14')
STRESS=(('base',1,0),('cost2',2,0),('delay1',1,1))
SPEC=lambda n:StrategySpec(n,(),(),1,1,4,60,3,2)

def load_context():
    data,times,old=old_prepared()
    ctx={'valid':old['valid'],**{feed:{k:old[feed][k] for k in ('open','high','low','close')} for feed in ('source','ETF')}}
    with np.load(OUT/'masks_LOCAL.npz') as f:ctx.update({k:f[k] for k in f.files})
    return data,times,ctx

def prepare():
    if (OUT/'prepared_manifest.json').exists():raise SystemExit('Prepared output protected')
    data,times,old=old_prepared();schedule=pd.read_csv(BASE/'calendar_schedule.csv',index_col='day')
    for k in ('open','close'):schedule[k]=pd.to_datetime(schedule[k],utc=True)
    qqq,meta=parse_source('QQQ',schedule)
    raw=json.loads(Path('runs/source_lead_audit_20261119_0200/hourly_access/QQQ_raw_LOCAL.json').read_text())['chart']['result'][0]['indicators']['quote'][0]
    rawf=pd.DataFrame(raw);volume_only_null=int((np.isfinite(rawf[['open','high','low','close']]).all(axis=1)&~np.isfinite(rawf.volume)).sum())
    assert volume_only_null==0,'Price-only parse still contaminated by volume-only NaN removal'
    positive=np.zeros(len(times),bool);trace=pd.read_csv(PREV/'source_trace_LOCAL.csv')
    for row in trace.itertuples():
        j=int(row.source_index);assert str(qqq.start.iloc[j])==row.source_start and str(qqq.end.iloc[j])==row.source_end
        k=int(times.get_loc(pd.Timestamp(row.source_start)));v=qqq.volume.iloc[j];ev=data.volume[k,data.symbols.index('TQQQ')]
        positive[row.index]=bool(np.isfinite(v) and np.isfinite(ev) and v>0 and ev>0)
    masks={'current_positive':positive}
    for lookback in (20,40):masks['history'+str(lookback)]=np.isfinite(old['source']['rvol'+str(lookback)])&(old['source']['rvol'+str(lookback)]>0)&np.isfinite(old['ETF']['rvol'+str(lookback)])&(old['ETF']['rvol'+str(lookback)]>0)
    assert not np.any(masks['history40']&~masks['history20']) and not np.any(masks['history20']&~positive)
    np.savez_compressed(OUT/'masks_LOCAL.npz',**masks);data,times,ctx=load_context();rawscore={};checks=0
    for c in candidates():rawscore[c['name']]=signals(data,times,ctx,c)
    for feed in ('source','ETF'):
        for lookback in (20,40):
            c=dict(family='participation_follow',lookback=lookback,a=1.25,b=.5)
            np.testing.assert_array_equal(rawscore[f'{feed}__L{lookback}'],old_signals(data,times,old,c,feed,True));checks+=1
    with np.load(PREV/'scores_LOCAL.npz') as f:coin=f['coin_only'];legacy=f['legacy_nasdaq'];oldfull={k:f[k] for k in f.files if k.startswith('no_volume__')}
    score={k:v+coin for k,v in rawscore.items()};score.update(coin_only=coin,legacy_nasdaq=legacy)
    for lookback in (20,40):np.testing.assert_array_equal(score[f'source__L{lookback}'],oldfull[f'no_volume__participation_follow_L{lookback}_a1.25_b0.5']);checks+=1
    prefixchecks=0
    for n in (103,803,1803):
        d=replace(data,timestamps=data.timestamps[:n],**{k:getattr(data,k)[:n] for k in ('open','high','low','close','volume')})
        pc={k:(v[:n] if isinstance(v,np.ndarray) else {a:b[:n] for a,b in v.items()}) for k,v in ctx.items()}
        for c in candidates():np.testing.assert_array_equal(signals(d,times[:n],pc,c),rawscore[c['name']][:n]);prefixchecks+=1
    np.savez_compressed(OUT/'scores_LOCAL.npz',**score);np.savez_compressed(OUT/'Nasdaq_scores_LOCAL.npz',**rawscore)
    rows=[];days=times.tz_convert('America/New_York').strftime('%Y-%m-%d');dm=(times>=pd.Timestamp(DEV[0][0],tz='UTC'))&(times<pd.Timestamp(DEV[-1][1],tz='UTC'));aliases={};reps={}
    for c in candidates():
        s=mask_session_signals(rawscore[c['name']],times,0,0,'event');base=mask_session_signals(rawscore[c['feed']+'__none'],times,0,0,'event');digest=hashlib.sha256(s[dm].tobytes()).hexdigest();aliases[c['name']]=reps.setdefault(digest,c['name'])
        for a,b in DEV:
            m=(times>=pd.Timestamp(a,tz='UTC'))&(times<pd.Timestamp(b,tz='UTC'));changed=np.any(s!=base,axis=1)&m
            rows.append(dict(**c,start=a,end_exclusive=b,price_support_rows=int((m&support(data,times,ctx,c['gate'])).sum()),onsets=int(np.any(s[m],axis=1).sum()),changed_vs_none=int(changed.sum()),changed_days=len(set(days[changed])),development_alias=aliases[c['name']]))
    pd.DataFrame(rows).to_csv(OUT/'returnblind_preflight.csv',index=False)
    dump(OUT/'future_hypotheses.json',dict(status='PROPOSED_ONLY_NOT_EXECUTED',families=FUTURE_HYPOTHESES))
    dump(OUT/'prepared_manifest.json',dict(status='PREPARED_BEFORE_PNL',definitions=candidates(),aliases=aliases,exact_legacy_array_regressions=checks,score_prefix_checks=prefixchecks,raw_QQQ_volume_only_null_OHLC_finite=volume_only_null,mask_nesting=True,source_meta=meta,masks_sha256=sha(OUT/'masks_LOCAL.npz'),scores_sha256=sha(OUT/'scores_LOCAL.npz'),Nasdaq_scores_sha256=sha(OUT/'Nasdaq_scores_LOCAL.npz'),independent_validation=False,news_macro=False,orders=0));print(pd.DataFrame(rows).to_string(index=False))

class Runner:
    def __init__(self):
        self.data,self.times,self.ctx=load_context();self.days=self.times.tz_convert('America/New_York').strftime('%Y-%m-%d')
        self.plan=json.loads((OUT/'preregistered_plan.json').read_text());self.plan_hash=sha(OUT/'preregistered_plan.json')
        for p,h in self.plan['hashes'].items():assert sha(Path(p))==h,p
        with np.load(OUT/'scores_LOCAL.npz') as f:self.score={k:f[k] for k in f.files}
        checkpoint=OUT/'checkpoint_LOCAL.json';self.ck=json.loads(checkpoint.read_text()) if checkpoint.exists() else dict(calls=[],rows=[],actual={},logical={},prior={},monthly={})
        if (OUT/'call_intent_LOCAL.json').exists():raise RuntimeError('In-flight intent exists; verify commit/ledger/state before any replay')
        self.oldrows=pd.read_csv(PREV/'reset_window_results.csv')
    def save(self):
        dump(OUT/'checkpoint_LOCAL.json',self.ck);pd.DataFrame(self.ck['calls']).to_csv(OUT/'actual_calls.csv',index=False);pd.DataFrame(self.ck['rows']).to_csv(OUT/'reset_window_results.csv',index=False)
        dump(OUT/'monthly_progress.json',self.ck['monthly'])
    def bounds(self,a,b):return [int(self.times.searchsorted(pd.Timestamp(x,tz='UTC'))) for x in (a,b)]
    def log(self,ref):
        origin,ident=ref.split(':');path=(OUT if origin=='new' else PREV)/f'call_{ident}_ledger_LOCAL.jsonl'
        return [json.loads(x) for x in path.read_text().splitlines() if x]
    def call(self,ref):return self.ck['calls'][int(ref.split(':')[1])-1] if ref.startswith('new:') else self.ck['prior'][ref]
    def begin(self,intent):
        if (OUT/'call_intent_LOCAL.json').exists():raise RuntimeError('Active/unresolved call intent')
        dump(OUT/'call_intent_LOCAL.json',dict(intent,plan_hash=self.plan_hash))
    def commit(self):self.save();(OUT/'call_intent_LOCAL.json').unlink()
    def record(self,n,a,b,scenario,kind,result,log):
        ident=len(self.ck['calls'])+1
        for t in log:
            si=int(t['signal_index']);entry=int(self.times.get_loc(pd.Timestamp(t['entry'])));end=int(self.times.get_loc(pd.Timestamp(t['end'])))
            assert self.days[si]==self.days[entry]==self.days[end]
            assert all(0<w<=.150000001 for w in t['bought_weights']) and sum(t['bought_weights'])<=.300000001
        path=OUT/f'call_{ident}_ledger_LOCAL.jsonl';path.write_text(''.join(json.dumps(t,separators=(',',':'))+'\n' for t in log))
        Nasdaq=sum(any(s in ('TQQQ','SQQQ') for s in t['bought_symbols']) for t in log);btc=sum(any(s in ('IBIT','BITI') for s in t['bought_symbols']) for t in log)
        self.ck['calls'].append(dict(call_id=ident,kind=kind,first_policy=n,start=a,end_exclusive=b,scenario=scenario,**result.to_dict(),Nasdaq_rounds=Nasdaq,Bitcoin_rounds=btc,max_gross=max([sum(t['bought_weights']) for t in log],default=0),ledger_sha256=sha(path)))
        return 'new:'+str(ident)
    def prior(self,n,a,b,scenario,s):
        if n in ('coin_only','legacy_nasdaq'):options=[n]
        elif a in ('2025-01-01','2025-07-01') and scenario=='base':options=['no_volume__participation_follow_L20_a1.25_b0.5','no_volume__participation_follow_L40_a1.25_b0.5']
        else:return None
        lo,hi=self.bounds(a,b);delay=1 if scenario=='delay1' else 0;q=None
        with np.load(PREV/'scores_LOCAL.npz') as f:
            for old in options:
                candidate=self.oldrows[(self.oldrows.name==old)&(self.oldrows.start==a)&(self.oldrows.end_exclusive==b)&(self.oldrows.scenario==scenario)]
                previous=mask_session_signals(f[old],self.times,delay,0,'event')
                if len(candidate)==1 and np.array_equal(s[max(0,lo-1-delay):hi],previous[max(0,lo-1-delay):hi]):q=candidate;break
        if q is None:return None
        row=q.iloc[0].to_dict();ident=int(row['call_id']);ref='old:'+str(ident);path=PREV/f'call_{ident}_ledger_LOCAL.jsonl';assert path.exists()
        self.ck['prior'][ref]={k:v for k,v in row.items() if k not in ('name','purpose')};self.ck['prior'][ref].update(first_policy=old,kind='prior_reset',ledger_sha256=sha(path))
        return ref
    def evaluate(self,n,a,b,scenario='base',cost=1,delay=0,purpose='development'):
        lk=json.dumps([n,a,b,scenario])
        if lk in self.ck['logical']:return self.ck['rows'][self.ck['logical'][lk]]
        lo,hi=self.bounds(a,b);s=mask_session_signals(self.score[n],self.times,delay,0,'event');digest=hashlib.sha256(s[max(0,lo-1-delay):hi].tobytes()).hexdigest();key=json.dumps([a,b,scenario,digest])
        if key not in self.ck['actual']:
            ref=self.prior(n,a,b,scenario,s)
            if ref is None:
                self.begin(dict(kind='reset',name=n,start=a,end=b,scenario=scenario,key=key,next_call_id=len(self.ck['calls'])+1));log=[]
                result=run_backtest(self.data,s,SPEC(n),CFG.execution,CFG.risk,CFG.capital,lo,hi,cost,delay,trade_log=log,exit_mode='joint_close',funded_pair=True,funded_allow_single=True)
                ref=self.record(n,a,b,scenario,'reset_window',result,log)
            self.ck['actual'][key]=ref
        ref=self.ck['actual'][key];call=self.call(ref)
        row=dict(name=n,start=a,end_exclusive=b,scenario=scenario,purpose=purpose,call_ref=ref,**{k:v for k,v in call.items() if k not in ('name','call_id','start','end_exclusive','scenario','purpose','first_policy','kind')})
        self.ck['logical'][lk]=len(self.ck['rows']);self.ck['rows'].append(row)
        if (OUT/'call_intent_LOCAL.json').exists():self.commit()
        else:self.save()
        return row
    def continuous(self,schedule,scenario,cost,delay,trailing,pause_after_one=False):
        months=list(pd.date_range('2026-01-01','2026-11-01',freq='MS'));key=hashlib.sha256(json.dumps([schedule,scenario,self.plan_hash]).encode()).hexdigest()
        saved=self.ck['monthly'].setdefault(key,dict(schedule=list(schedule),scenario=scenario,plan_hash=self.plan_hash,segments=[]))
        state,start=resume_state(saved,schedule,scenario,self.plan_hash)
        for i in range(start,len(months)):
            month=months[i];n=schedule[i];a=str(month.date());b=str(min(month+pd.DateOffset(months=1),pd.Timestamp(DIAG[1])).date());lo,hi=self.bounds(a,b);log=[]
            self.begin(dict(kind='continuous',schedule_key=key,month_index=i,name=n,start=a,end=b,scenario=scenario,starting_state=asdict(state),next_call_id=len(self.ck['calls'])+1))
            result=run_backtest(self.data,mask_session_signals(self.score[n],self.times,delay,0,'event'),SPEC(n),CFG.execution,CFG.risk,CFG.capital,lo,hi,cost,delay,trade_log=log,exit_mode='joint_close',funded_pair=True,funded_allow_single=True,account_state=state)
            ref=self.record(n,a,b,scenario,'continuous_month',result,log)
            saved['segments'].append(dict(month=a,selected=n,call_ref=ref,**result.to_dict(),state=asdict(state)));self.commit()
            if pause_after_one:raise CheckpointPause('One NEW month committed atomically; resume without replay')
        return key,saved

class CheckpointPause(Exception):pass

def development():
    if (OUT/'selection.json').exists():raise SystemExit('Development already frozen')
    r=Runner();base=[]
    for c in candidates():
        for a,b in DEV:base.append(r.evaluate(c['name'],a,b))
    frame=pd.DataFrame(base);rank=frame.groupby('name').agg(worst=('total_return','min'),mean=('total_return','mean'),min_Nasdaq_rounds=('Nasdaq_rounds','min'),any_halt=('mdd_halt','max'),max_hard_halts=('hard_halts','max')).reset_index().sort_values(['worst','mean','name'],ascending=[False,False,True]);aliases=json.loads((OUT/'prepared_manifest.json').read_text())['aliases']
    shortlist=[x.name for x in rank.itertuples() if x.min_Nasdaq_rounds>=20 and not x.any_halt and x.max_hard_halts==0 and aliases[x.name]==x.name][:8]
    for n in shortlist:
        for a,b in DEV:
            for s,c,d in STRESS:r.evaluate(n,a,b,s,c,d)
    for n in ('coin_only','legacy_nasdaq'):
        for a,b in DEV:
            for s,c,d in STRESS:r.evaluate(n,a,b,s,c,d,purpose='fixed_reference')
    pool=[];passed=[];failure=[];pre=pd.read_csv(OUT/'returnblind_preflight.csv')
    for n in rank.name:
        reason=[];group=[x for x in r.ck['rows'] if x['name']==n and (x['start'],x['end_exclusive']) in DEV]
        if n not in shortlist:reason.append('BASE_SAMPLE_HALT_ALIAS_OR_BELOW_TOP8')
        else:
            if min(x['Nasdaq_rounds'] for x in group)>=20 and not any(x['mdd_halt'] or x['hard_halts'] for x in group):pool.append(n)
            else:reason.append('STRESS_MIN20_OR_HALT_FAILED')
            if min(x['total_return'] for x in group)<=0:reason.append('NONPOSITIVE_DEVELOPMENT_STRESS')
            bg=[r.evaluate('coin_only',a,b,s,c,d) for a,b in DEV for s,c,d in STRESS];ordered=[r.evaluate(n,a,b,s,c,d) for a,b in DEV for s,c,d in STRESS]
            if any(x['total_return']<=y['total_return'] or x['max_drawdown']>y['max_drawdown'] for x,y in zip(ordered,bg)):reason.append('NO_UNIFORM_INCREMENT_VS_BITCOIN_BACKGROUND')
            evidence=pre[pre.name==n]
            if not n.endswith('__none') and (evidence.changed_vs_none.min()<20 or evidence.changed_days.min()<10):reason.append('AVAILABILITY_INTERVENTION_NOT_IDENTIFIED_IN_BOTH_HALVES')
            if not reason:passed.append(n)
        failure.append(dict(name=n,reasons=reason,independent_history_missing=True))
    rank.to_csv(OUT/'ranking.csv',index=False);dump(OUT/'selection.json',dict(shortlist=shortlist,diagnostic_pool=pool,development_screen_pass=passed,approved=[],failures=failure));dump(OUT/'development_checkpoint.json',dict(actual_new_calls=len(r.ck['calls']),logical_cells=len(r.ck['rows']),prior_unique_cells=len(r.ck['prior']),pool=pool));r.save();print(rank.to_string(index=False));print('shortlist',shortlist,'pool',pool)

def research(pause=False):
    if (OUT/'manifest.json').exists():raise SystemExit('Completed output protected')
    r=Runner();selection=json.loads((OUT/'selection.json').read_text());pool=selection['diagnostic_pool'];recent=[]
    for n in ['coin_only','legacy_nasdaq']+pool:
        for s,c,d in STRESS:r.evaluate(n,*DIAG,s,c,d,purpose='reused2026_diagnostic')
    for months in (3,6):
        end=pd.Timestamp(DIAG[1]);a=str((end-pd.DateOffset(months=months)).date());b=str(end.date())
        for n in pool:
            group=[r.evaluate(n,a,b,s,c,d,purpose=f'recent{months}m_fit') for s,c,d in STRESS]
            recent.append(dict(months=months,name=n,start=a,end_exclusive=b,worst_stress=min(x['total_return'] for x in group),min_Nasdaq_rounds=min(x['Nasdaq_rounds'] for x in group),**{k:group[0][k] for k in ('total_return','rounds','Nasdaq_rounds','win_rate','max_drawdown')}))
    pd.DataFrame(recent,columns=['months','name','start','end_exclusive','worst_stress','min_Nasdaq_rounds','total_return','rounds','Nasdaq_rounds','win_rate','max_drawdown']).sort_values(['months','total_return'],ascending=[True,False]).to_csv(OUT/'recent_fitted_ranks.csv',index=False)
    decisions=[];choices={};monthlist=list(pd.date_range('2026-01-01','2026-11-01',freq='MS'))
    for months in (3,6):
        for month in monthlist:
            a=str((month-pd.DateOffset(months=months)).date());b=str(month.date());bg=[r.evaluate('coin_only',a,b,s,c,d,purpose='training_fixed_background') for s,c,d in STRESS];eligible=[]
            for n in pool:
                group=[r.evaluate(n,a,b,s,c,d,purpose=f'prior{months}m_train') for s,c,d in STRESS]
                if min(x['Nasdaq_rounds'] for x in group)>=20 and min(x['total_return'] for x in group)>0 and not any(x['mdd_halt'] or x['hard_halts'] for x in group) and all(x['total_return']>y['total_return'] and x['max_drawdown']<=y['max_drawdown'] for x,y in zip(group,bg)):
                    eligible.append((min(x['total_return'] for x in group),np.mean([x['total_return'] for x in group]),n))
            n=max(eligible)[2] if eligible else 'coin_only';choices[(months,b)]=n;decisions.append(dict(months=months,month=b,training_start=a,training_end_exclusive=b,selected=n,eligible_count=len(eligible),Nasdaq_cash=n=='coin_only',explicit_whole_cash_policy=False))
    pd.DataFrame(decisions).to_csv(OUT/'monthly_choices.csv',index=False);wf=[];segments=[]
    for months in (3,6):
        schedule=[choices[(months,str(m.date()))] for m in monthlist]
        for s,c,d in STRESS:
            key,saved=r.continuous(schedule,s,c,d,months,pause_after_one=pause);whole=[t for segment in saved['segments'] for t in r.log(segment['call_ref'])];net=np.asarray([t['net_return'] for t in whole]);last=saved['segments'][-1]['state']
            wf.append(dict(months=months,scenario=s,start=DIAG[0],end_exclusive=DIAG[1],schedule_key=key,total_return=last['equity']/CFG.capital-1,rounds=len(whole),Nasdaq_rounds=sum(any(z in ('TQQQ','SQQQ') for z in t['bought_symbols']) for t in whole),Bitcoin_rounds=sum(any(z in ('IBIT','BITI') for z in t['bought_symbols']) for t in whole),win_rate=float(np.mean(net>0)) if len(net) else 0,max_drawdown=max(seg['max_drawdown'] for seg in saved['segments']),ever_halted=any(seg['mdd_halt'] for seg in saved['segments']),Nasdaq_cash_months=schedule.count('coin_only'),actual_zero_trade_months=sum(seg['rounds']==0 for seg in saved['segments'])))
            segments.extend(dict(segment,months=months,scenario=s,schedule_key=key) for segment in saved['segments'])
    pd.DataFrame(wf).to_csv(OUT/'continuous_walkforward.csv',index=False);dump(OUT/'monthly_state_checkpoints.json',segments);r.save()
    prioruse=pd.DataFrame([x for x in r.ck['rows'] if x['call_ref'].startswith('old:')]);prioruse.to_csv(OUT/'prior_cache_reuse.csv',index=False)
    files=['scripts/availability_signals_20261119.py','scripts/availability_runtime_20261119.py','scripts/availability_retry_20261119.py','tests/test_availability_signals.py','src/autogrid/engine.py','configs/win60_search.yaml']
    dump(OUT/'manifest.json',dict(status='COMPLETE_AVAILABILITY_RESEARCH',actual_new_calls=len(r.ck['calls']),reset_actual_calls=sum(c['kind']=='reset_window' for c in r.ck['calls']),continuous_actual_calls=sum(c['kind']=='continuous_month' for c in r.ck['calls']),logical_reset_cells=len(r.ck['rows']),prior_unique_calls_reused=len(r.ck['prior']),prior_logical_cells_reused=len(prioruse),logical_month_segments=len(segments),unique_month_schedule_paths=len(r.ck['monthly']),definitions=8,new_alpha_threshold_trials=0,shortlist=selection['shortlist'],diagnostic_pool=pool,development_screen_pass=selection['development_screen_pass'],approved=[],hashes={p:sha(Path(p)) for p in files},independent_validation=False,news_macro=False,orders=0,raw_upload='not attempted'));print(pd.DataFrame(wf).to_string(index=False));print('newactualcalls',len(r.ck['calls']))

if __name__=='__main__':
    mode=sys.argv[1:]
    if mode==['prepare']:prepare()
    elif mode and mode[0] in ('development','research'):
        fd=os.open(OUT/'RUNNING.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
        try:
            try:(development() if mode[0]=='development' else research('--pause-after-one-month' in mode))
            except CheckpointPause as e:print('CHECKPOINT_PAUSED:',str(e))
        finally:(OUT/'RUNNING.lock').unlink()
    else:raise SystemExit('Use prepare/development/research [--pause-after-one-month]')
