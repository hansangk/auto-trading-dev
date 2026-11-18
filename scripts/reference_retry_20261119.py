"""Preregistered external-reference pilot; all execution uses actual ETF prices."""
from pathlib import Path
from dataclasses import replace
import os,json,hashlib,gzip
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec
from inverse_etf_retry_20261116 import CFG
from five_minute_grid_20261118 import signals as momentum
from reference_signals_20261119 import candidates,signals
from session_signal_provenance import mask_session_signals
OUT=Path('runs/reference_retry_20261119')
ETF=Path('runs/extended_snapshot_20261118/refreshed_all_LOCAL.csv.gz')
DEV=[('2026-09-21','2026-10-01'),('2026-10-01','2026-10-19')]
DIAG=('2026-10-19','2026-11-18')
STRESS=(('base',1,0),('cost2',2,0),('delay1',1,1))

def prepare():
    assert hashlib.sha256(ETF.read_bytes()).hexdigest()=='ebbdc8b683532ba96bf5c1358f5656833d6c33fe6833268ce1e13a777254b851'
    source=OUT/'references_LOCAL.csv.gz'
    assert hashlib.sha256(source.read_bytes()).hexdigest()=='836d92f572b14bf0a622b637b7009ca6e261f09e7b567e36bec4ab206a689075'
    audit=json.loads((OUT/'reference_provenance.json').read_text());frame=pd.read_csv(ETF)
    frame['timestamp']=pd.to_datetime(frame.timestamp,utc=True)
    frame=frame[frame.timestamp.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d').isin(audit['aligned_complete_etf_dates'])]
    path=OUT/'aligned_ETF_LOCAL.csv.gz';path.write_bytes(gzip.compress(frame.to_csv(index=False).encode(),mtime=0))
    data=load_market_data(path,['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True)
    f=pd.read_csv(source);f['timestamp']=pd.to_datetime(f.timestamp,utc=True)
    refs=np.stack([f[f.symbol==s].set_index('timestamp').loc[times,['open','high','low','close']].to_numpy() for s in ('QQQ','BTC-USD')],axis=1)
    assert refs.shape==(len(times),2,4) and np.isfinite(refs).all()
    # Source starts match exactly; source ends equal starts+5min for every role.
    days=times.tz_convert('America/New_York').date
    for day,g in pd.Series(np.arange(len(times))).groupby(days):
        expected=pd.date_range(str(day)+' 09:30',periods=78,freq='5min',tz='America/New_York').tz_convert('UTC')
        assert times[g.to_numpy()].equals(expected)
    return data,times,refs,path

def main():
    if (OUT/'manifest.json').exists():raise SystemExit('Completed run protected')
    data,times,refs,path=prepare();grid=candidates();assert len(grid)==16
    score={c['name']:signals(data,times,refs,c) for c in grid}
    fields={k:np.repeat(refs[:,:,j],2,axis=1) for j,k in enumerate(('open','high','low','close'))}
    refdata=replace(data,**fields)
    score['ETF_momentum']=momentum(data,times,dict(family='momentum',a=4,b=.5))
    score['reference_momentum']=momentum(refdata,times,dict(family='momentum',a=4,b=.5))
    score['reference_agreement']=np.where(score['ETF_momentum']==score['reference_momentum'],score['ETF_momentum'],0)
    score['cash']=np.zeros_like(data.close)
    controls=['ETF_momentum','reference_momentum','reference_agreement','cash']
    # Development-only effective signal dedup precedes shortlist. Keep all aliases in ranking.
    devmask=times<pd.Timestamp(DIAG[0],tz='UTC');hashes={n:hashlib.sha256(s[devmask].tobytes()).hexdigest() for n,s in score.items() if n not in controls}
    representatives={};alias={}
    for c in grid:
        n=c['name'];alias[n]=representatives.setdefault(hashes[n],n)
    rows=[];cache={};ledgers={};usage=[]
    def evaluate(name,a,b,scenario='base',cost=1,delay=0):
        key=(name,a,b,scenario)
        if key not in cache:
            lo,hi=[int(times.searchsorted(pd.Timestamp(x,tz='UTC'))) for x in (a,b)];log=[]
            result=run_backtest(data,mask_session_signals(score[name],times,delay,0,'event'),StrategySpec(name,(),(),1,1,12,60,3,2),CFG.execution,CFG.risk,CFG.capital,lo,hi,cost,delay,trade_log=log,exit_mode='joint_close',funded_pair=True,funded_allow_single=True)
            assert np.isclose(np.prod([1+t['net_return'] for t in log])-1,result.total_return)
            assert all(0<w<=.150000001 for t in log for w in t['bought_weights'])
            row=dict(name=name,start=a,end_exclusive=b,scenario=scenario,**result.to_dict());rows.append(row);cache[key]=row;ledgers[key]=log
            for s in data.symbols:usage.append(dict(name=name,start=a,scenario=scenario,symbol=s,buys=sum(s in t['bought_symbols'] for t in log)))
        return cache[key]
    base=pd.DataFrame([evaluate(n,a,b) for n in representatives.values() for a,b in DEV])
    rank=base.groupby('name').agg(worst=('total_return','min'),mean=('total_return','mean'),min_rounds=('rounds','min')).sort_values(['worst','mean'],ascending=False)
    shortlist=rank[rank.min_rounds>=20].head(8).index.tolist()
    (OUT/'shortlist.json').write_text(json.dumps(dict(shortlist=shortlist,selection_data='development only',aliases=alias),indent=2))
    for n in shortlist+controls:
        for a,b in DEV:
            for scenario,cost,delay in STRESS:evaluate(n,a,b,scenario,cost,delay)
    eligible=[];passed=[];failures=[]
    for n in representatives.values():
        reason=[]
        if n not in shortlist:reason.append('base_min_rounds<20_or_below_top8')
        else:
            group=[cache[(n,a,b,s)] for a,b in DEV for s,_,_ in STRESS]
            if min(r['rounds'] for r in group)<20:reason.append('stress_min_rounds<20')
            else:eligible.append(n)
            if min(r['total_return'] for r in group)<=0:reason.append('nonpositive_development_cell')
            if any(r['mdd_halt'] or r['hard_halts'] for r in group):reason.append('halted')
            if any(cache[(n,a,b,s)]['total_return']<=cache[('ETF_momentum',a,b,s)]['total_return'] for a,b in DEV for s,_,_ in STRESS):reason.append('not_better_than_ETF_control_each_cell')
            if any(cache[(n,a,b,s)]['max_drawdown']>cache[('ETF_momentum',a,b,s)]['max_drawdown'] for a,b in DEV for s,_,_ in STRESS):reason.append('drawdown_worse_than_ETF_control')
            if not reason:passed.append(n)
        failures.append(dict(name=n,reasons=reason,independent_history_missing=True))
    # Predeclared descriptive diagnostic top<=3 sample-eligible entries; never all-grid diagnostic fitting.
    selected=[n for n in shortlist if n in eligible][:3]
    (OUT/'selection.json').write_text(json.dumps(dict(shortlist=shortlist,diagnostic_selected=selected,development_screen_pass=passed,approved=[],failures=failures),indent=2))
    for n in selected+controls:
        for scenario,cost,delay in STRESS:evaluate(n,*DIAG,scenario,cost,delay)
    # Frozen potential ETF events, not halted baseline ledger. Costs are per active role capital.
    labels=[];days=times.tz_convert('America/New_York').date
    for label,(a,b) in zip(('A','B'),DEV):
        for k in np.flatnonzero(np.any(score['ETF_momentum'],axis=1)):
            if not pd.Timestamp(a,tz='UTC')<=times[k]<pd.Timestamp(b,tz='UTC') or k+12>=len(times) or days[k]!=days[k+12]:continue
            chosen=np.flatnonzero(score['ETF_momentum'][k]);keep=np.flatnonzero(score['reference_agreement'][k])
            for delay in (0,1):
                for n,cols in [('original',chosen),('agreement',keep)]:
                    gross=.15*np.sum(data.close[k+12,cols]/data.open[k+1+delay,cols]-1);cost=.15*len(cols)*.00046
                    labels.append(dict(period=label,day=str(days[k]),event=k,delay=delay,policy=n,roles=len(cols),gross=gross,cost=cost,net=gross-cost))
    f=pd.DataFrame(labels);f.to_csv(OUT/'source_opportunities_LOCAL.csv',index=False)
    f.groupby(['period','delay','policy']).agg(events=('net','size'),role_events=('roles','sum'),mean_gross=('gross','mean'),mean_cost=('cost','mean'),mean_net=('net','mean')).to_csv(OUT/'fixed_opportunity.csv')
    pd.DataFrame(rows).to_csv(OUT/'account_replays.csv',index=False);pd.DataFrame(usage).to_csv(OUT/'ticker_usage.csv',index=False)
    allrank=[]
    for c in grid:allrank.append(dict(**c,representative=alias[c['name']],array_sha256=hashes[c['name']],**rank.loc[alias[c['name']]].to_dict()))
    pd.DataFrame(allrank).sort_values(['worst','mean'],ascending=False).to_csv(OUT/'ranking.csv',index=False)
    for (n,a,b,s),log in ledgers.items():
        # Local detail is reproducible, not public raw upload.
        pd.DataFrame(log).to_json(OUT/f'{n}_{a}_{s}_ledger_LOCAL.jsonl',orient='records',lines=True)
    daily=[];rng=np.random.default_rng(20261119)
    for label,(a,b) in zip(('A','B'),DEV):
        dates=sorted(set(str(d) for d,t in zip(days,times) if pd.Timestamp(a,tz='UTC')<=t<pd.Timestamp(b,tz='UTC')))
        for delay in (0,1):
            z=f[(f.period==label)&(f.delay==delay)].pivot(index=['day','event'],columns='policy',values='net')
            diff=(z.agreement-z.original).groupby('day').mean().reindex(dates,fill_value=0).to_numpy()
            draw=rng.choice(diff,size=(2000,len(diff)),replace=True).mean(axis=1)
            daily.append(dict(period=label,delay=delay,days=len(diff),daily_delta=float(diff.mean()),lower=float(np.quantile(draw,.025)),upper=float(np.quantile(draw,.975))))
    pd.DataFrame(daily).to_csv(OUT/'paired_daily.csv',index=False)
    files=['scripts/reference_retry_20261119.py','scripts/reference_signals_20261119.py','scripts/fetch_reference_20261119.py','scripts/five_minute_grid_20261118.py','scripts/session_signal_provenance.py','src/autogrid/engine.py','configs/win60_search.yaml','tests/test_reference_signals.py']
    manifest=dict(status='COMPLETE_RESEARCH_PILOT',engine_calls=len(rows),nominal_candidates=16,distinct_development_arrays=len(representatives),shortlist=shortlist,selected=selected,development_screen_pass=passed,approved=[],aligned_sessions=33,first=str(times[0]),last_bar_start=str(times[-1]),end_bar_completion=str(times[-1]+pd.Timedelta(minutes=5)),etf_source_sha256=hashlib.sha256(ETF.read_bytes()).hexdigest(),aligned_etf_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),reference_sha256=hashlib.sha256((OUT/'references_LOCAL.csv.gz').read_bytes()).hexdigest(),code_config_sha256={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files},independent_validation=False,recent3_fit='NOT_RUN_INSUFFICIENT_HISTORY',recent6_fit='NOT_RUN_INSUFFICIENT_HISTORY',monthly_3_6_walkforward='NOT_RUN_INSUFFICIENT_HISTORY',news_macro=False,orders=0,publication_latency_assumption='source t completes t+5min, next-open zeroadditionaldelay; delaystress+5min',calendar_verified=False)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2));print(rank.to_string());print(json.dumps(manifest,indent=2))
if __name__=='__main__':
    fd=os.open(OUT/'RUNNING.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
    try:main()
    finally:(OUT/'RUNNING.lock').unlink()
