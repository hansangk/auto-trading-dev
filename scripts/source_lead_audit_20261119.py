"""Four information families, three fixed lags; no diagnostic fitting."""
from pathlib import Path
import hashlib,json,os
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec
from inverse_etf_retry_20261116 import CFG
from five_minute_grid_20261118 import signals as momentum
from source_lead_signals_20261119 import candidates,filter_scores,feature_values,baseline_scores,decision_mask
from session_signal_provenance import mask_session_signals
OUT=Path('runs/source_lead_audit_20261119_0200')
SOURCE=Path('runs/reference_retry_20261119')
DEV=[('2026-09-21','2026-10-01'),('2026-10-01','2026-10-19')]
DIAG=('2026-10-19','2026-11-18')
STRESS=(('base',1,0),('cost2',2,0),('delay1',1,1))

def load_inputs():
    etf=SOURCE/'aligned_ETF_LOCAL.csv.gz';source=SOURCE/'references_LOCAL.csv.gz'
    assert hashlib.sha256(etf.read_bytes()).hexdigest()=='a672f4d76a6216e743270abb97fae31f421a955985fa718cd82c6c423430e99c'
    assert hashlib.sha256(source.read_bytes()).hexdigest()=='836d92f572b14bf0a622b637b7009ca6e261f09e7b567e36bec4ab206a689075'
    data=load_market_data(etf,['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True)
    f=pd.read_csv(source);f.timestamp=pd.to_datetime(f.timestamp,utc=True)
    refs=np.stack([f[f.symbol==s].set_index('timestamp').loc[times,['open','high','low','close']].to_numpy() for s in ('QQQ','BTC-USD')],axis=1)
    assert refs.shape==(len(times),2,4) and np.isfinite(refs).all()
    for day,group in pd.Series(np.arange(len(times))).groupby(times.tz_convert('America/New_York').date):
        assert times[group.to_numpy()].equals(pd.date_range(str(day)+' 09:30',periods=78,freq='5min',tz='America/New_York').tz_convert('UTC'))
    return data,times,refs

def main():
    if (OUT/'manifest.json').exists():raise SystemExit('Completed output protected')
    data,times,refs=load_inputs();days=times.tz_convert('America/New_York').date;grid=candidates();assert len(grid)==12
    unrestricted=momentum(data,times,dict(family='momentum',a=4,b=.5));baseline=baseline_scores(data,times)
    np.testing.assert_array_equal(baseline,np.where(decision_mask(times)[:,None],unrestricted,0))
    score={'cohort_baseline':baseline,'unrestricted_baseline':unrestricted,'cash':np.zeros_like(baseline)};values={}
    for c in grid:
        for feed in ('source','ETF'):
            n=c['name']+'__'+feed;values[n]=feature_values(data,times,refs,c,feed);score[n]=filter_scores(data,times,refs,c,feed)
            assert np.all((score[n]==0)|(score[n]==baseline))
    # This block has no forward prices or account PnL. Freeze support first.
    support=[];events={}
    for c in grid:
        n=c['name'];events[n]={}
        for a,b in DEV:
            potential=[(k,j) for k,j in zip(*np.nonzero(baseline)) if pd.Timestamp(a,tz='UTC')<=times[k]<pd.Timestamp(b,tz='UTC') and k+12<len(times) and days[k]==days[k+12]]
            valid=[(k,j) for k,j in potential if np.isfinite(values[n+'__source'][k,j]) and np.isfinite(values[n+'__ETF'][k,j])]
            keep=sum(score[n+'__source'][k,j]!=0 for k,j in valid);changed=[(k,j) for k,j in valid if bool(score[n+'__source'][k,j])!=bool(score[n+'__ETF'][k,j])]
            changed_days=len({str(days[k]) for k,j in changed});passed=len(changed)>=20 and keep>=20 and len(valid)-keep>=20 and changed_days>=3
            support.append(dict(name=n,start=a,potential_roles=len(potential),common_valid_roles=len(valid),source_admitted=keep,source_rejected=len(valid)-keep,ETF_admitted=sum(score[n+'__ETF'][k,j]!=0 for k,j in valid),changed_roles=len(changed),changed_days=changed_days,support_pass=bool(passed)));events[n][a]=valid
    pd.DataFrame(support).to_csv(OUT/'return_blind_support.csv',index=False)
    supportpass=[c['name'] for c in grid if all(x['support_pass'] for x in support if x['name']==c['name'])]
    (OUT/'support_checkpoint.json').write_text(json.dumps(dict(status='PRE_PERFORMANCE_SUPPORT_FROZEN',passing=supportpass,candidates=12,thresholds='>=20changed,>=20admit/reject,>=3changedNYdays EACHwindow'),indent=2))
    # Outcome labels become accessible only after the above return-blind checkpoint.
    labels=[];summary=[];information=[];rng=np.random.default_rng(20261119)
    for c in grid:
        n=c['name']
        for a,b in DEV:
            dates=sorted(set(str(d) for d,t in zip(days,times) if pd.Timestamp(a,tz='UTC')<=t<pd.Timestamp(b,tz='UTC')))
            for delay in (0,1):
                current=[]
                for k,j in events[n][a]:
                    gross=.15*(data.close[k+12,j]/data.open[k+1+delay,j]-1);cost=.15*.00046;net=gross-cost
                    gs=int(score[n+'__source'][k,j]!=0);ge=int(score[n+'__ETF'][k,j]!=0)
                    row=dict(name=n,start=a,delay=delay,day=str(days[k]),event=k,symbol=data.symbols[j],source_admit=gs,ETF_admit=ge,gross=gross,cost=cost,net=net,source_net=gs*net,ETF_net=ge*net,delta=(gs-ge)*net);current.append(row);labels.append(row)
                f=pd.DataFrame(current)
                if len(f):summary.append(dict(name=n,start=a,delay=delay,role_events=len(f),mean_original_gross=f.gross.mean(),mean_original_cost=f.cost.mean(),mean_original_net=f.net.mean(),mean_source_gross=(f.gross*f.source_admit).mean(),mean_source_cost=(f.cost*f.source_admit).mean(),mean_source_net=f.source_net.mean(),mean_ETF_net=f.ETF_net.mean(),mean_paired_delta=f.delta.mean(),source_admitted_mean=f.loc[f.source_admit==1,'net'].mean(),ETF_admitted_mean=f.loc[f.ETF_admit==1,'net'].mean()))
                lower=None;mean=None;passed=False
                if n in supportpass and len(f):
                    daily=f.groupby('day').delta.mean().reindex(dates,fill_value=0).to_numpy();draw=rng.choice(daily,size=(2000,len(daily)),replace=True).mean(axis=1)
                    mean=float(daily.mean());lower=float(np.quantile(draw,.05/48));passed=mean>0 and lower>0
                information.append(dict(name=n,start=a,delay=delay,status='EVALUATED' if n in supportpass else 'NOT_TESTED_SUPPORT',daily_delta=mean,lower=lower,pass_information=passed))
    pd.DataFrame(summary).to_csv(OUT/'fixed_opportunity.csv',index=False);pd.DataFrame(information).to_csv(OUT/'information_gate.csv',index=False);pd.DataFrame(labels).to_csv(OUT/'event_labels_LOCAL.csv',index=False)
    informationpass=[n for n in supportpass if all(x['pass_information'] for x in information if x['name']==n)]
    rows=[];calls=[];actual_cache={};logical_cache={};logs={};usage=[]
    def evaluate(n,a,b,scenario='base',cost=1,delay=0):
        key=(n,a,b,scenario)
        if key not in logical_cache:
            lo,hi=[int(times.searchsorted(pd.Timestamp(x,tz='UTC'))) for x in (a,b)];masked=mask_session_signals(score[n],times,delay,0,'event')
            digest=hashlib.sha256(masked[max(0,lo-1-delay):hi].tobytes()).hexdigest();cachekey=(a,b,scenario,digest)
            if cachekey not in actual_cache:
                log=[];result=run_backtest(data,masked,StrategySpec(n,(),(),1,1,12,60,3,2),CFG.execution,CFG.risk,CFG.capital,lo,hi,cost,delay,trade_log=log,exit_mode='joint_close',funded_pair=True,funded_allow_single=True)
                assert np.isclose(np.prod([1+t['net_return'] for t in log])-1,result.total_return)
                assert all(0<w<=.150000001 for t in log for w in t['bought_weights'])
                ident=len(calls)+1;call=dict(call_id=ident,first_policy=n,start=a,end_exclusive=b,scenario=scenario,array_sha256=digest,**result.to_dict());calls.append(call);actual_cache[cachekey]=call;logs[ident]=log
            call=actual_cache[cachekey];ident=call['call_id'];row=dict(name=n,start=a,end_exclusive=b,scenario=scenario,call_id=ident,**{k:v for k,v in call.items() if k not in ('first_policy','array_sha256','start','end_exclusive','scenario','call_id')});rows.append(row);logical_cache[key]=row
            for s in data.symbols:usage.append(dict(name=n,start=a,scenario=scenario,call_id=ident,symbol=s,buys=sum(s in t['bought_symbols'] for t in logs[ident])))
        return logical_cache[key]
    base=[]
    for c in grid:
        for a,b in DEV:
            base.append(evaluate(c['name']+'__source',a,b))
            evaluate(c['name']+'__ETF',a,b)
    f=pd.DataFrame(base);rank=f.groupby('name').agg(worst=('total_return','min'),mean=('total_return','mean'),min_rounds=('rounds','min')).sort_values(['worst','mean'],ascending=False)
    devmask=times<pd.Timestamp(DIAG[0],tz='UTC');reps={};aliases={}
    for c in grid:
        n=c['name'];digest=hashlib.sha256(score[n+'__source'][devmask].tobytes()).hexdigest();aliases[n]=reps.setdefault(digest,n)
    shortlist=[]
    for n in rank.index:
        plain=n.removesuffix('__source')
        if plain in informationpass and rank.loc[n,'min_rounds']>=20 and aliases[plain]==plain:shortlist.append(plain)
    shortlist=shortlist[:8]
    (OUT/'shortlist.json').write_text(json.dumps(dict(shortlist=shortlist,selection='support and information and developmentbase only',aliases=aliases),indent=2))
    controls=['cohort_baseline','unrestricted_baseline','cash']
    for n in controls+[name+'__'+feed for name in shortlist for feed in ('source','ETF')]:
        for a,b in DEV:
            for s,cost,delay in STRESS:evaluate(n,a,b,s,cost,delay)
    selected=[];passed=[];failures=[]
    for c in grid:
        n=c['name'];reason=[]
        if n not in supportpass:reason.append('INADEQUATE_SOURCE_VS_ETF_INTERVENTION_SUPPORT')
        elif n not in informationpass:reason.append('NO_REPLICATED_INCREMENTAL_LABEL_EVIDENCE')
        if rank.loc[n+'__source','min_rounds']<20:reason.append('BASE_MIN20_ROUNDS_FAILED')
        if aliases[n]!=n:reason.append('DEVELOPMENT_SCORE_ALIAS_OF_'+aliases[n])
        if n in shortlist:
            group=[logical_cache[(n+'__source',a,b,s)] for a,b in DEV for s,_,_ in STRESS]
            if min(x['rounds'] for x in group)<20:reason.append('STRESS_MIN20_ROUNDS_FAILED')
            else:selected.append(n)
            if min(x['total_return'] for x in group)<=0:reason.append('NONPOSITIVE_DEVELOPMENT_CELL')
            if any(x['mdd_halt'] or x['hard_halts'] for x in group):reason.append('HALTED')
            for comparator in ('cohort_baseline',n+'__ETF'):
                if any(logical_cache[(n+'__source',a,b,s)]['total_return']<=logical_cache[(comparator,a,b,s)]['total_return'] for a,b in DEV for s,_,_ in STRESS):reason.append('NO_UNIFORM_RETURN_IMPROVEMENT_VS_'+comparator)
            if any(logical_cache[(n+'__source',a,b,s)]['max_drawdown']>logical_cache[('cohort_baseline',a,b,s)]['max_drawdown'] for a,b in DEV for s,_,_ in STRESS):reason.append('MDD_WORSE_THAN_COHORT_CONTROL')
            if not reason:passed.append(n)
        failures.append(dict(**c,reasons=reason,independent_history_missing=True))
    selected=selected[:3]
    # Only fixedcontrols and development-selected candidates can enter diagnosis.
    for n in controls+[name+'__'+feed for name in selected for feed in ('source','ETF')]:
        for s,cost,delay in STRESS:evaluate(n,*DIAG,s,cost,delay)
    (OUT/'selection.json').write_text(json.dumps(dict(support_passing=supportpass,information_passing=informationpass,shortlist=shortlist,diagnostic_selected=selected,development_screen_pass=passed,approved=[],failures=failures),indent=2))
    rank.to_csv(OUT/'ranking.csv');pd.DataFrame(rows).to_csv(OUT/'account_results.csv',index=False);pd.DataFrame(calls).to_csv(OUT/'actual_calls.csv',index=False);pd.DataFrame(usage).to_csv(OUT/'ticker_usage.csv',index=False)
    for ident,log in logs.items():pd.DataFrame(log).to_json(OUT/f'call_{ident}_ledger_LOCAL.jsonl',orient='records',lines=True)
    prior=pd.read_csv(SOURCE/'account_replays.csv');reg=[]
    for a,b in DEV+[DIAG]:
        for s,_,_ in STRESS:
            x=logical_cache[('unrestricted_baseline',a,b,s)];y=prior[(prior.name=='ETF_momentum')&(prior.start==a)&(prior.scenario==s)].iloc[0]
            keys=['total_return','max_drawdown','rounds','win_rate','costs','trades'];assert all(np.isclose(x[k],y[k]) for k in keys);reg.append(dict(start=a,scenario=s,passed=True,fields=keys))
    (OUT/'regression.json').write_text(json.dumps(reg,indent=2))
    files=['scripts/source_lead_audit_20261119.py','scripts/source_lead_signals_20261119.py','tests/test_source_lead_signals.py','scripts/five_minute_grid_20261118.py','scripts/session_signal_provenance.py','src/autogrid/engine.py','configs/win60_search.yaml']
    manifest=dict(status='COMPLETE_INFORMATION_AUDIT',engine_calls=len(calls),logical_policy_cells=len(rows),cached_identical_cells=len(rows)-len(calls),source_filter_settings=12,paired_ETF_feature_controls=12,new_full_strategy_grid=0,distinct_development_source_arrays=len(reps),support_passing=supportpass,information_passing=informationpass,shortlist=shortlist,diagnostic_selected=selected,approved=[],development_screen_pass=passed,sessions=33,ETF_sha256=hashlib.sha256((SOURCE/'aligned_ETF_LOCAL.csv.gz').read_bytes()).hexdigest(),reference_sha256=hashlib.sha256((SOURCE/'references_LOCAL.csv.gz').read_bytes()).hexdigest(),source_provenance='runs/reference_retry_20261119/reference_provenance.json',code_config_sha256={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files},independent_validation=False,recent3_6_fit='NOT_RUN_INSUFFICIENT_HISTORY',causal_monthly_3_6='NOT_RUN_INSUFFICIENT_HISTORY',news_macro=False,orders=0,raw_upload='Not attempted',publication_latency='zeroadditionalassumed; stress+5min',calendar_verified=False)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2));print(pd.DataFrame(support).to_string(index=False));print(rank.to_string());print(json.dumps(manifest,indent=2))
if __name__=='__main__':
    fd=os.open(OUT/'RUNNING.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
    try:main()
    finally:(OUT/'RUNNING.lock').unlink()
