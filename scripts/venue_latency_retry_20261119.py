"""Preregistered calendar-common latency/short-horizon decomposition.

Frozen .55/.10/L4 onsets, exact scheduled CLOSE durations120/180minutes.
Protective early exits remain active; realized holding may differ.
Duration60 is label-only because hold1 has no intermediate joint-close check.
"""
from pathlib import Path
from dataclasses import asdict
import hashlib,json,os,sys
import numpy as np
import pandas as pd
from autogrid.engine import run_backtest,AccountState
from autogrid.strategy import StrategySpec
from venue_flow_context_20261119 import load_prepared as load_context,BASE
from venue_latency_calendar_20261119 import common_mask
from venue_isolation_retry_20261119 import Runner as PriorRunner
from availability_runtime_20261119 import atomic_json as dump,restore_state,resume_state,sha,clean
from availability_guarded_research_20261119 import verify_prefix
from inverse_etf_retry_20261116 import CFG
from session_signal_provenance import mask_session_signals
OUT=Path('runs/venue_latency_retry_20261119_1400');PREV=Path('runs/venue_isolation_retry_20261119_1300');GRAND=Path('runs/venue_flow_retry_20261119_1200')
DEV=[('2025-01-01','2025-07-01'),('2025-07-01','2026-01-01')];DIAG=('2026-01-01','2026-11-14')
STRESS=(('base',1,0),('cost2',2,0),('delay1',1,1));MDD_SCREEN=.03

def candidates():return [dict(name=f'{family}__{arm}',family=family,duration=duration,arm=arm) for family,duration in (('legacy',None),('h60',60),('h120',120),('c120',120),('h180',180),('c180',180)) for arm in ('source','price')]
def pair(n):return n.replace('__source','__price')
def hold(n):
    if n.startswith('h60__'):raise ValueError('NO_INTERMEDIATE_PROTECTION_OBSERVATION: label-only')
    return int(n.split('__')[0][1:])//60 if n.startswith(('h120__','h180__')) else 4

def SPEC(n):return StrategySpec(n,(),(),1,1,hold(n),60,3,2)
def prepare():
    if (OUT/'prepared_manifest.json').exists():raise RuntimeError('Prepared output protected')
    data,times,ctx=load_context();days=times.tz_convert('America/New_York').strftime('%Y-%m-%d');calendar=pd.read_csv(BASE/'calendar_schedule.csv',index_col='day')
    for k in ('open','close'):calendar[k]=pd.to_datetime(calendar[k],utc=True)
    old=PriorRunner();scores={'cash':np.zeros_like(old.score['cash']),'nasdaq_only':old.score['nasdaq_only']};rows=[];checks=0;clockchecks=0
    for arm in ('source','price'):
        scores['full__'+arm]=old.score['full__body55__'+arm]
        original=old.score['coin__body55__'+arm]
        scores['legacy__'+arm]=original
        for d in (60,120,180):
            mask=common_mask(times,calendar,d);scores[f'h{d}__{arm}']=original*mask[:,None]
            if d in (120,180):scores[f'c{d}__{arm}']=original*mask[:,None]
            for n in (103,803,1803):np.testing.assert_array_equal(common_mask(times[:n],calendar,d),mask[:n]);checks+=1
            for i in np.flatnonzero(mask):
                for delay in (0,1):
                    entry=i+1+delay;last=entry+d//60-1;assert last<len(times) and days[last]==days[i]
                    assert times[entry]==times[i]+pd.Timedelta(hours=1+delay)
                    assert times[last]+pd.Timedelta(hours=1)==times[entry]+pd.Timedelta(minutes=d)
                    assert times[last]+pd.Timedelta(hours=1)<=calendar.loc[days[i],'close'];clockchecks+=1
        for c in [x for x in candidates() if x['arm']==arm]:
            s=mask_session_signals(scores[c['name']],times,0,0,'event');control=mask_session_signals((old.score['coin__body55__price'] if c['family']=='legacy' else old.score['coin__body55__price']*common_mask(times,calendar,c['duration'])[:,None]),times,0,0,'event')
            for a,b in DEV:
                m=(times>=pd.Timestamp(a,tz='UTC'))&(times<pd.Timestamp(b,tz='UTC'));changed=np.any(s!=control,axis=1)&m
                rows.append(dict(**c,start=a,end_exclusive=b,onset_upper_bound=int(np.any(s[m],axis=1).sum()),changed_vs_price=int(changed.sum()),changed_days=len(set(days[changed]))))
    frame=pd.DataFrame(rows);eligible=[];blocked=[]
    for c in candidates():
        g=frame[frame.name==c['name']];src=frame[frame.name==c['name'].replace('__price','__source')];reason=[]
        if c['family']=='legacy':reason.append('IMMUTABLE_REFERENCE_AND_SAMEEXIT_LABEL_ONLY')
        if c['family']=='h60':reason.append('NO_INTERMEDIATE_PROTECTION_OBSERVATION_LABEL_ONLY')
        if min(g.onset_upper_bound.min(),src.onset_upper_bound.min())<20:reason.append('OPPORTUNITY_UPPER_BOUND_LT20')
        if src.changed_vs_price.min()<20 or src.changed_days.min()<10:reason.append('PAIRED_FLOW_INTERVENTION_LT20_OR_LT10DAYS')
        if reason:blocked.append(dict(name=c['name'],reasons=reason))
        else:eligible.append(c['name'])
    frame.to_csv(OUT/'returnblind_preflight.csv',index=False);np.savez_compressed(OUT/'scores_LOCAL.npz',**scores)
    dump(OUT/'prepared_manifest.json',dict(status='PREPARED_BEFORE_PNL',definitions=candidates(),eligible_new=eligible,blocked=blocked,calendar_prefix_checks=checks,actual_scheduled_clock_checks=clockchecks,scores_sha256=sha(OUT/'scores_LOCAL.npz'),no_threshold_fit=True,original_scheduled_minutes_equal_after_delay_events=0,independent_validation=False,orders=0));print(frame.to_string(index=False));print('eligible',eligible)
class Runner:
    def __init__(self):
        self.data,self.times,self.ctx=load_context();self.days=self.times.tz_convert('America/New_York').strftime('%Y-%m-%d')
        self.plan=json.loads((OUT/'preregistered_plan.json').read_text());self.plan_hash=sha(OUT/'preregistered_plan.json')
        for p,h in self.plan['hashes'].items():assert sha(Path(p))==h,p
        with np.load(OUT/'scores_LOCAL.npz') as f:self.score={k:f[k] for k in f.files}
        checkpoint=OUT/'checkpoint_LOCAL.json';self.ck=json.loads(checkpoint.read_text()) if checkpoint.exists() else dict(calls=[],rows=[],actual={},logical={},prior={},monthly={})
        if (OUT/'call_intent_LOCAL.json').exists():raise RuntimeError('In-flight intent exists; verify commit/ledger/state before any replay')
        self.old=PriorRunner();self.oldrows=pd.DataFrame(self.old.ck['rows'])
        
    def save(self):
        dump(OUT/'checkpoint_LOCAL.json',self.ck);pd.DataFrame(self.ck['calls']).to_csv(OUT/'actual_calls.csv',index=False);pd.DataFrame(self.ck['rows']).to_csv(OUT/'reset_window_results.csv',index=False)
        dump(OUT/'monthly_progress.json',self.ck['monthly'])
    def bounds(self,a,b):return [int(self.times.searchsorted(pd.Timestamp(x,tz='UTC'))) for x in (a,b)]
    def log(self,ref):
        path=OUT/f'call_{ref.split(":")[1]}_ledger_LOCAL.jsonl' if ref.startswith('new:') else Path(self.ck['prior'][ref]['ledger_path'])
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
        if n=='nasdaq_only':name=n
        elif n.startswith('full__'):name=n.replace('full__','full__body55__',1)
        elif n.startswith('legacy__'):name=n.replace('legacy__','coin__body55__',1)
        else:return None
        q=self.oldrows[(self.oldrows.name==name)&(self.oldrows.start==a)&(self.oldrows.end_exclusive==b)&(self.oldrows.scenario==scenario)]
        if len(q)!=1:raise RuntimeError('Missing immutable reference cache; NEVER rerun closed failure')
        lo,hi=self.bounds(a,b);delay=int(scenario=='delay1');prior=mask_session_signals(self.old.score[name],self.times,delay,0,'event')
        if not np.array_equal(prior[max(0,lo-1-delay):hi],s[max(0,lo-1-delay):hi]):raise RuntimeError('Prior array mismatch')
        old=q.iloc[0].to_dict();oldref=old['call_ref'];call=self.old.call(oldref);path=(PREV if oldref.startswith('new:') else GRAND)/f"call_{oldref.split(':')[1]}_ledger_LOCAL.jsonl";assert sha(path)==call['ledger_sha256']
        ref='prior:'+oldref;self.ck['prior'][ref]=dict(call,first_policy=name,kind='verified_prior_reset',ledger_path=str(path));return ref
    def evaluate(self,n,a,b,scenario='base',cost=1,delay=0,purpose='development'):
        if n.startswith('h60__'):raise ValueError('Label-only60min cannot call protected engine')
        if (cost,delay)!={key:(c,d) for key,c,d in STRESS}[scenario]:raise ValueError('Scenario/cost/delay mismatch; cache rejected')
        lk=json.dumps([n,a,b,scenario])
        if lk in self.ck['logical']:return self.ck['rows'][self.ck['logical'][lk]]
        lo,hi=self.bounds(a,b);s=mask_session_signals(self.score[n],self.times,delay,0,'event');digest=hashlib.sha256(s[max(0,lo-1-delay):hi].tobytes()).hexdigest();key=json.dumps([a,b,scenario,cost,delay,hold(n),60,3,2,'joint_close',digest])
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
    r=Runner();prepared=json.loads((OUT/'prepared_manifest.json').read_text());base=[]
    for n in prepared['eligible_new']:
        for a,b in DEV:base.append(r.evaluate(n,a,b))
    frame=pd.DataFrame(base);rank=frame.groupby('name').agg(worst=('total_return','min'),mean=('total_return','mean'),min_Bitcoin_rounds=('Bitcoin_rounds','min'),any_halt=('mdd_halt','max'),max_hard_halts=('hard_halts','max'),max_mdd=('max_drawdown','max')).reset_index().sort_values(['worst','mean','name'],ascending=[False,False,True]);shortlist=[]
    for x in rank.itertuples():
        if not x.name.endswith('__source'):continue
        q=rank[rank.name==pair(x.name)].iloc[0]
        if min(x.min_Bitcoin_rounds,q.min_Bitcoin_rounds)<20 or x.any_halt or q.any_halt or x.max_hard_halts or q.max_hard_halts or max(x.max_mdd,q.max_mdd)>MDD_SCREEN:continue
        if len(shortlist)+2<=8:shortlist.extend([x.name,pair(x.name)])
    for n in shortlist:
        for a,b in DEV:
            for s,c,d in STRESS:r.evaluate(n,a,b,s,c,d)
    for n in ['nasdaq_only']+['legacy__source','legacy__price','full__source','full__price']:
        for a,b in DEV:
            for s,c,d in STRESS:
                row=r.evaluate(n,a,b,s,c,d,purpose='immutable_full_reference');assert row['call_ref'].startswith('prior:'),'Reference missing cache; do not rerun oldfailure'
    pool=[];passed=[];failure=list(prepared['blocked'])
    for n in prepared['eligible_new']:
        reason=[]
        if n not in shortlist:reason.append('BASE_MIN20_HALT_MDD_OR_TOP8_FAILED')
        else:
            g=[r.evaluate(n,a,b,s,c,d) for a,b in DEV for s,c,d in STRESS]
            supported=min(x['Bitcoin_rounds'] for x in g)>=20 and not any(x['mdd_halt'] or x['hard_halts'] for x in g) and max(x['max_drawdown'] for x in g)<=MDD_SCREEN
            if not supported:reason.append('STRESS_MIN20_HALT_OR_ABSOLUTE_MDD_FAILED')
            if min(x['total_return'] for x in g)<=0:reason.append('NONPOSITIVE_DEVELOPMENT_STRESS')
            if n.endswith('__source'):
                control=[r.evaluate(pair(n),a,b,s,c,d) for a,b in DEV for s,c,d in STRESS]
                if supported and min(x['Bitcoin_rounds'] for x in control)>=20 and not any(x['mdd_halt'] or x['hard_halts'] for x in control) and max(x['max_drawdown'] for x in control)<=MDD_SCREEN:pool.append(n)
                if any(x['total_return']<=y['total_return'] or x['max_drawdown']>y['max_drawdown'] for x,y in zip(g,control)):reason.append('NO_UNIFORM_FLOW_INCREMENT_VS_SAME15PCT_PRICE')
                if not reason:passed.append(n)
        failure.append(dict(name=n,reasons=reason,independent_history_missing=True))
    rank.to_csv(OUT/'ranking.csv',index=False);dump(OUT/'selection.json',dict(shortlist=shortlist,diagnostic_pool=pool,development_screen_pass=passed,approved=[],failures=failure));dump(OUT/'development_checkpoint.json',dict(new_calls=len(r.ck['calls']),logical_cells=len(r.ck['rows']),prior_unique_cells=len(r.ck['prior']),pool=pool));print(rank.to_string(index=False));print('pool',pool,'passed',passed)

def research(pause=False):
    if (OUT/'manifest.json').exists():raise SystemExit('Completed output protected')
    r=Runner();selection=json.loads((OUT/'selection.json').read_text());pool=selection['diagnostic_pool'];recent=[]
    for n in ['cash']+list(dict.fromkeys(pool+[pair(n) for n in pool])):
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
            a=str((month-pd.DateOffset(months=months)).date());b=str(month.date());eligible=[]
            for n in pool:
                group=[r.evaluate(n,a,b,s,c,d,purpose=f'prior{months}m_train') for s,c,d in STRESS]
                bg=[r.evaluate(pair(n),a,b,s,c,d,purpose='training_same15pct_price_benchmark') for s,c,d in STRESS]
                if min(x['Bitcoin_rounds'] for x in group+bg)>=20 and max(x['max_drawdown'] for x in group+bg)<=MDD_SCREEN and not any(x['mdd_halt'] or x['hard_halts'] for x in bg) and min(x['total_return'] for x in group)>0 and not any(x['mdd_halt'] or x['hard_halts'] for x in group) and all(x['total_return']>y['total_return'] and x['max_drawdown']<=y['max_drawdown'] for x,y in zip(group,bg)):
                    eligible.append((min(x['total_return'] for x in group),np.mean([x['total_return'] for x in group]),n))
            n=max(eligible)[2] if eligible else 'cash';choices[(months,b)]=n;decisions.append(dict(months=months,month=b,training_start=a,training_end_exclusive=b,selected=n,eligible_count=len(eligible),Bitcoin_cash=n=='cash',explicit_whole_cash_policy=True))
    pd.DataFrame(decisions).to_csv(OUT/'monthly_choices.csv',index=False);wf=[];segments=[]
    for months in (3,6):
        schedule=[choices[(months,str(m.date()))] for m in monthlist]
        for s,c,d in STRESS:
            key,saved=r.continuous(schedule,s,c,d,months,pause_after_one=pause);whole=[t for segment in saved['segments'] for t in r.log(segment['call_ref'])];net=np.asarray([t['net_return'] for t in whole]);last=saved['segments'][-1]['state']
            wf.append(dict(months=months,scenario=s,start=DIAG[0],end_exclusive=DIAG[1],schedule_key=key,total_return=last['equity']/CFG.capital-1,rounds=len(whole),Nasdaq_rounds=sum(any(z in ('TQQQ','SQQQ') for z in t['bought_symbols']) for t in whole),Bitcoin_rounds=sum(any(z in ('IBIT','BITI') for z in t['bought_symbols']) for t in whole),win_rate=float(np.mean(net>0)) if len(net) else 0,max_drawdown=max(seg['max_drawdown'] for seg in saved['segments']),ever_halted=any(seg['mdd_halt'] for seg in saved['segments']),Bitcoin_cash_months=schedule.count('cash'),actual_zero_trade_months=sum(seg['rounds']==0 for seg in saved['segments'])))
            segments.extend(dict(segment,months=months,scenario=s,schedule_key=key) for segment in saved['segments'])
    pd.DataFrame(wf).to_csv(OUT/'continuous_walkforward.csv',index=False);dump(OUT/'monthly_state_checkpoints.json',segments);r.save()
    prioruse=pd.DataFrame([x for x in r.ck['rows'] if x['call_ref'].startswith('prior:')]);prioruse.to_csv(OUT/'prior_cache_reuse.csv',index=False)
    files=['scripts/venue_latency_calendar_20261119.py','scripts/venue_latency_retry_20261119.py','src/autogrid/engine.py','configs/win60_search.yaml']
    dump(OUT/'manifest.json',dict(status='COMPLETE_VENUE_LATENCY_RESEARCH',actual_new_calls=len(r.ck['calls']),reset_actual_calls=sum(c['kind']=='reset_window' for c in r.ck['calls']),continuous_actual_calls=sum(c['kind']=='continuous_month' for c in r.ck['calls']),logical_reset_cells=len(r.ck['rows']),prior_unique_calls_reused=len(r.ck['prior']),prior_logical_cells_reused=len(prioruse),logical_month_segments=len(segments),unique_month_schedule_paths=len(r.ck['monthly']),definitions=12,new_alpha_threshold_trials=0,shortlist=selection['shortlist'],diagnostic_pool=pool,development_screen_pass=selection['development_screen_pass'],approved=[],hashes={p:sha(Path(p)) for p in files},independent_validation=False,news_macro=False,orders=0,raw_upload='not attempted'));print(pd.DataFrame(wf).to_string(index=False));print('newactualcalls',len(r.ck['calls']))

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
