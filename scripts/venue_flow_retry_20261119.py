"""New venue-flow grid; actual BUY ETFs, immutable prior experiments."""
from pathlib import Path
from dataclasses import asdict,replace
import hashlib,json,os,sys
import numpy as np
import pandas as pd
from autogrid.engine import run_backtest,AccountState
from autogrid.strategy import StrategySpec
from venue_flow_context_20261119 import load_prepared as load_context,OUT,ETF
from venue_flow_signals_20261119 import candidates as alpha_candidates,signals
from hourly_night_signals_20261119 import signals as night_signals
from availability_runtime_20261119 import atomic_json as dump,restore_state,resume_state,sha,clean
from availability_guarded_research_20261119 import verify_prefix
from inverse_etf_retry_20261116 import CFG
from session_signal_provenance import mask_session_signals
DEV=[('2025-01-01','2025-07-01'),('2025-07-01','2026-01-01')];DIAG=('2026-01-01','2026-11-14')
STRESS=(('base',1,0),('cost2',2,0),('delay1',1,1))
SPEC=lambda n:StrategySpec(n,(),(),1,1,4,60,3,2)
def candidates():
    return [dict(c,name=arm+'__'+c['name'],alpha=c['name'],arm=arm) for c in alpha_candidates() for arm in ('source','price')]
def prepare():
    if (OUT/'prepared_manifest.json').exists():raise RuntimeError('Prepared output protected')
    data,times,ctx=load_context()
    with np.load('runs/hourly_clock_retry_20261119_0300/audit_v2/context_LOCAL.npz') as f:oldctx={k:f[k] for k in f.files}
    background=night_signals(data,times,oldctx,dict(family='night_nasdaq',a=5,b=.5))
    assert not np.any(background[:,2:])
    score={'nasdaq_only':background};raw={};prefix=0
    for c in candidates():
        raw[c['name']]=signals(data,times,ctx,{k:v for k,v in c.items() if k not in ('alpha','arm')},c['arm']=='price');score[c['name']]=raw[c['name']]+background
    for n in (103,803,1803):
        d=replace(data,timestamps=data.timestamps[:n],**{k:getattr(data,k)[:n] for k in ('open','high','low','close','volume')})
        pc={k:(v[:n] if isinstance(v,np.ndarray) else {a:b[:n] for a,b in v.items()}) for k,v in ctx.items()}
        for c in candidates():np.testing.assert_array_equal(signals(d,times[:n],pc,{k:v for k,v in c.items() if k not in ('alpha','arm')},c['arm']=='price'),raw[c['name']][:n]);prefix+=1
    np.savez_compressed(OUT/'scores_LOCAL.npz',**score);np.savez_compressed(OUT/'crypto_scores_LOCAL.npz',**raw)
    rows=[];aliases={};reps={};days=times.tz_convert('America/New_York').strftime('%Y-%m-%d');dm=(times>=pd.Timestamp(DEV[0][0],tz='UTC'))&(times<pd.Timestamp(DEV[-1][1],tz='UTC'))
    for c in candidates():
        s=mask_session_signals(raw[c['name']],times,0,0,'event');base=mask_session_signals(raw['price__'+c['alpha']],times,0,0,'event');digest=hashlib.sha256(s[dm].tobytes()).hexdigest();aliases[c['name']]=reps.setdefault(digest,c['name'])
        for a,b in DEV:
            m=(times>=pd.Timestamp(a,tz='UTC'))&(times<pd.Timestamp(b,tz='UTC'));changed=np.any(s!=base,axis=1)&m
            active=np.any(s!=0,axis=1);control=np.any(base!=0,axis=1)
            rows.append(dict(**c,start=a,end_exclusive=b,eligible_clock_rows=int((ctx['valid']&m).sum()),onsets=int(active[m].sum()),changed_vs_price=int(changed.sum()),changed_days=len(set(days[changed])),source_only=int((active&~control&m).sum()),control_only=int((~active&control&m).sum()),both_changed=int((active&control&changed).sum()),development_alias=aliases[c['name']]))
    pd.DataFrame(rows).to_csv(OUT/'returnblind_preflight.csv',index=False)
    dump(OUT/'prepared_manifest.json',dict(status='PREPARED_BEFORE_PNL',definitions=candidates(),aliases=aliases,score_prefix_checks=prefix,scores_sha256=sha(OUT/'scores_LOCAL.npz'),crypto_scores_sha256=sha(OUT/'crypto_scores_LOCAL.npz'),independent_validation=False,news_macro=False,orders=0))
    print(pd.DataFrame(rows).groupby('arm')[['onsets','changed_vs_price']].agg(['min','max']).to_string())
class Runner:
    def __init__(self):
        self.data,self.times,self.ctx=load_context();self.days=self.times.tz_convert('America/New_York').strftime('%Y-%m-%d')
        self.plan=json.loads((OUT/'preregistered_plan.json').read_text());self.plan_hash=sha(OUT/'preregistered_plan.json')
        for p,h in self.plan['hashes'].items():assert sha(Path(p))==h,p
        with np.load(OUT/'scores_LOCAL.npz') as f:self.score={k:f[k] for k in f.files}
        checkpoint=OUT/'checkpoint_LOCAL.json';self.ck=json.loads(checkpoint.read_text()) if checkpoint.exists() else dict(calls=[],rows=[],actual={},logical={},prior={},monthly={})
        if (OUT/'call_intent_LOCAL.json').exists():raise RuntimeError('In-flight intent exists; verify commit/ledger/state before any replay')
        
    def save(self):
        dump(OUT/'checkpoint_LOCAL.json',self.ck);pd.DataFrame(self.ck['calls']).to_csv(OUT/'actual_calls.csv',index=False);pd.DataFrame(self.ck['rows']).to_csv(OUT/'reset_window_results.csv',index=False)
        dump(OUT/'monthly_progress.json',self.ck['monthly'])
    def bounds(self,a,b):return [int(self.times.searchsorted(pd.Timestamp(x,tz='UTC'))) for x in (a,b)]
    def log(self,ref):
        origin,ident=ref.split(':');path=OUT/f'call_{ident}_ledger_LOCAL.jsonl'
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
    def prior(self,*args):return None
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
        verify_prefix(saved,OUT,self.ck['calls'],CFG.capital)
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
    if (OUT/'selection.json').exists():raise RuntimeError('Development frozen')
    r=Runner();base=[]
    for c in candidates():
        for a,b in DEV:base.append(r.evaluate(c['name'],a,b))
    frame=pd.DataFrame(base);rank=frame.groupby('name').agg(worst=('total_return','min'),mean=('total_return','mean'),min_Bitcoin_rounds=('Bitcoin_rounds','min'),any_halt=('mdd_halt','max'),max_hard_halts=('hard_halts','max')).reset_index().sort_values(['worst','mean','name'],ascending=[False,False,True])
    aliases=json.loads((OUT/'prepared_manifest.json').read_text())['aliases'];pre=pd.read_csv(OUT/'returnblind_preflight.csv');shortlist=[]
    for row in rank.itertuples():
        if not row.name.startswith('source__') or aliases[row.name]!=row.name:continue
        pair='price__'+row.name.split('__',1)[1];evidence=pre[pre.name==row.name];pr=rank[rank.name==pair].iloc[0]
        if min(row.min_Bitcoin_rounds,pr.min_Bitcoin_rounds)<20 or row.any_halt or pr.any_halt or row.max_hard_halts or pr.max_hard_halts or evidence.changed_vs_price.min()<20 or evidence.changed_days.min()<10:continue
        additions=[x for x in (row.name,pair) if x not in shortlist]
        if len(shortlist)+len(additions)<=8:shortlist.extend(additions)
    for n in shortlist+['nasdaq_only']:
        for a,b in DEV:
            for s,c,d in STRESS:r.evaluate(n,a,b,s,c,d,purpose='development_stress' if n!='nasdaq_only' else 'fixed_reference')
    pool=[];passed=[];failure=[]
    for n in rank.name:
        reason=[];group=[x for x in r.ck['rows'] if x['name']==n and (x['start'],x['end_exclusive']) in DEV]
        if n not in shortlist:reason.append('BASE_SAMPLE_HALT_ALIAS_INTERVENTION_OR_BELOW_TOP4_PAIRS')
        else:
            if min(x['Bitcoin_rounds'] for x in group)>=20 and not any(x['mdd_halt'] or x['hard_halts'] for x in group):pool.append(n)
            else:reason.append('STRESS_CRYPTO_MIN20_OR_HALT_FAILED')
            if min(x['total_return'] for x in group)<=0:reason.append('NONPOSITIVE_DEVELOPMENT_STRESS')
            bg=[r.evaluate('nasdaq_only',a,b,s,c,d) for a,b in DEV for s,c,d in STRESS];ordered=[r.evaluate(n,a,b,s,c,d) for a,b in DEV for s,c,d in STRESS]
            if any(x['total_return']<=y['total_return'] or x['max_drawdown']>y['max_drawdown'] for x,y in zip(ordered,bg)):reason.append('NO_UNIFORM_INCREMENT_VS_NASDAQ_BACKGROUND')
            if not reason:passed.append(n)
        failure.append(dict(name=n,reasons=reason,independent_history_missing=True))
    rank.to_csv(OUT/'ranking.csv',index=False);dump(OUT/'selection.json',dict(shortlist=shortlist,diagnostic_pool=pool,development_screen_pass=passed,approved=[],failures=failure));dump(OUT/'development_checkpoint.json',dict(actual_new_calls=len(r.ck['calls']),logical_cells=len(r.ck['rows']),prior_unique_cells=0,pool=pool));r.save();print(rank.head(12).to_string(index=False));print('shortlist',shortlist,'pool',pool)

def research(pause=False):
    if (OUT/'manifest.json').exists():raise SystemExit('Completed output protected')
    r=Runner();selection=json.loads((OUT/'selection.json').read_text());pool=selection['diagnostic_pool'];recent=[]
    for n in ['nasdaq_only']+pool:
        for s,c,d in STRESS:r.evaluate(n,*DIAG,s,c,d,purpose='reused2026_diagnostic')
    for months in (3,6):
        end=pd.Timestamp(DIAG[1]);a=str((end-pd.DateOffset(months=months)).date());b=str(end.date())
        for n in pool:
            group=[r.evaluate(n,a,b,s,c,d,purpose=f'recent{months}m_fit') for s,c,d in STRESS]
            recent.append(dict(months=months,name=n,start=a,end_exclusive=b,worst_stress=min(x['total_return'] for x in group),min_Bitcoin_rounds=min(x['Bitcoin_rounds'] for x in group),**{k:group[0][k] for k in ('total_return','rounds','Bitcoin_rounds','win_rate','max_drawdown')}))
    pd.DataFrame(recent,columns=['months','name','start','end_exclusive','worst_stress','min_Bitcoin_rounds','total_return','rounds','Bitcoin_rounds','win_rate','max_drawdown']).sort_values(['months','total_return'],ascending=[True,False]).to_csv(OUT/'recent_fitted_ranks.csv',index=False)
    decisions=[];choices={};monthlist=list(pd.date_range('2026-01-01','2026-11-01',freq='MS'))
    for months in (3,6):
        for month in monthlist:
            a=str((month-pd.DateOffset(months=months)).date());b=str(month.date());bg=[r.evaluate('nasdaq_only',a,b,s,c,d,purpose='training_fixed_Nasdaq_background') for s,c,d in STRESS];eligible=[]
            for n in pool:
                group=[r.evaluate(n,a,b,s,c,d,purpose=f'prior{months}m_train') for s,c,d in STRESS]
                if min(x['Bitcoin_rounds'] for x in group)>=20 and min(x['total_return'] for x in group)>0 and not any(x['mdd_halt'] or x['hard_halts'] for x in group) and all(x['total_return']>y['total_return'] and x['max_drawdown']<=y['max_drawdown'] for x,y in zip(group,bg)):
                    eligible.append((min(x['total_return'] for x in group),np.mean([x['total_return'] for x in group]),n))
            n=max(eligible)[2] if eligible else 'nasdaq_only';choices[(months,b)]=n;decisions.append(dict(months=months,month=b,training_start=a,training_end_exclusive=b,selected=n,eligible_count=len(eligible),Bitcoin_cash=n=='nasdaq_only',explicit_whole_cash_policy=False))
    pd.DataFrame(decisions).to_csv(OUT/'monthly_choices.csv',index=False);wf=[];segments=[]
    for months in (3,6):
        schedule=[choices[(months,str(m.date()))] for m in monthlist]
        for s,c,d in STRESS:
            key,saved=r.continuous(schedule,s,c,d,months,pause_after_one=pause);whole=[t for segment in saved['segments'] for t in r.log(segment['call_ref'])];net=np.asarray([t['net_return'] for t in whole]);last=saved['segments'][-1]['state']
            wf.append(dict(months=months,scenario=s,start=DIAG[0],end_exclusive=DIAG[1],schedule_key=key,total_return=last['equity']/CFG.capital-1,rounds=len(whole),Nasdaq_rounds=sum(any(z in ('TQQQ','SQQQ') for z in t['bought_symbols']) for t in whole),Bitcoin_rounds=sum(any(z in ('IBIT','BITI') for z in t['bought_symbols']) for t in whole),win_rate=float(np.mean(net>0)) if len(net) else 0,max_drawdown=max(seg['max_drawdown'] for seg in saved['segments']),ever_halted=any(seg['mdd_halt'] for seg in saved['segments']),Bitcoin_cash_months=schedule.count('nasdaq_only'),actual_zero_trade_months=sum(seg['rounds']==0 for seg in saved['segments'])))
            segments.extend(dict(segment,months=months,scenario=s,schedule_key=key) for segment in saved['segments'])
    pd.DataFrame(wf).to_csv(OUT/'continuous_walkforward.csv',index=False);dump(OUT/'monthly_state_checkpoints.json',segments);r.save()
    prioruse=pd.DataFrame([x for x in r.ck['rows'] if x['call_ref'].startswith('old:')]);prioruse.to_csv(OUT/'prior_cache_reuse.csv',index=False)
    files=['scripts/venue_flow_signals_20261119.py','scripts/venue_flow_context_20261119.py','scripts/venue_flow_retry_20261119.py','tests/test_venue_flow_signals.py','src/autogrid/engine.py','configs/win60_search.yaml']
    dump(OUT/'manifest.json',dict(status='COMPLETE_VENUE_FLOW_RESEARCH',actual_new_calls=len(r.ck['calls']),reset_actual_calls=sum(c['kind']=='reset_window' for c in r.ck['calls']),continuous_actual_calls=sum(c['kind']=='continuous_month' for c in r.ck['calls']),logical_reset_cells=len(r.ck['rows']),prior_unique_calls_reused=len(r.ck['prior']),prior_logical_cells_reused=len(prioruse),logical_month_segments=len(segments),unique_month_schedule_paths=len(r.ck['monthly']),definitions=64,new_alpha_threshold_trials=32,shortlist=selection['shortlist'],diagnostic_pool=pool,development_screen_pass=selection['development_screen_pass'],approved=[],hashes={p:sha(Path(p)) for p in files},independent_validation=False,news_macro=False,orders=0,raw_upload='not attempted'));print(pd.DataFrame(wf).to_string(index=False));print('newactualcalls',len(r.ck['calls']))

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
