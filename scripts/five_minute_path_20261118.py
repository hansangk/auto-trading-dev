"""Freeze signal events; distinguish descriptive forward paths and account replay."""
from pathlib import Path
import json,hashlib,os
import pandas as pd
import numpy as np
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec
from five_minute_grid_20261118 import candidates,signals
from inverse_etf_retry_20261116 import CFG
from session_signal_provenance import mask_session_signals
OUT=Path('runs/five_minute_path_20261118')
INPUT=Path('runs/five_minute_grid_20261118/complete_sessions_LOCAL.csv.gz')
NAMES=['momentum_4_0.5','momentum_4_0.25','rangefade_2_0.8']

def main():
    if (OUT/'manifest.json').exists():raise SystemExit('Completed run protected')
    previous=json.loads(Path('runs/five_minute_grid_20261118/manifest.json').read_text())
    assert hashlib.sha256(INPUT.read_bytes()).hexdigest()==previous['complete_input_sha256']
    data=load_market_data(INPUT,['TQQQ','SQQQ','IBIT','BITI'])
    times=pd.to_datetime(data.timestamps,utc=True);days=times.tz_convert('America/New_York').date
    scores={c['name']:signals(data,times,c) for c in candidates() if c['name'] in NAMES}
    labels=[];gaps=[];coverage=[]
    for name,score in scores.items():
        counts={'name':name,'development_signal_events':0,'common_events':0}
        for k in np.flatnonzero(np.any(score,axis=1)):
            if times[k]>=pd.Timestamp('2026-11-14',tz='UTC'):continue
            counts['development_signal_events']+=1
            # Same cohort across all latency/horizon comparisons, no bar synthesis.
            if k+15>=len(times) or days[k]!=days[k+15]:continue
            counts['common_events']+=1
            chosen=np.flatnonzero(score[k]);period='A' if times[k]<pd.Timestamp('2026-11-01',tz='UTC') else 'B'
            gap=.15*np.sum(data.open[k+1,chosen]/data.close[k,chosen]-1)
            gaps.append(dict(name=name,period=period,day=str(days[k]),weighted_signal_close_to_open=gap,roles=len(chosen)))
            for delay in (0,1,3):
                entry=k+1+delay
                for horizon in (1,3,12):
                    for mode in ('same_exit','equal_hold'):
                        end=k+horizon if mode=='same_exit' else entry+horizon-1
                        # Same-exit horizon can precede a delayed fill; invalid cell omitted.
                        if end<entry:continue
                        gross=.15*np.sum(data.close[end,chosen]/data.open[entry,chosen]-1)
                        cost=.15*len(chosen)*.00046
                        labels.append(dict(name=name,period=period,day=str(days[k]),event=k,delay=delay,horizon=horizon,mode=mode,gross=gross,cost=cost,net=gross-cost))
        coverage.append(counts)
    frame=pd.DataFrame(labels)
    keys=['name','period','delay','horizon','mode']
    frame.groupby(keys).agg(events=('net','size'),mean_gross=('gross','mean'),mean_cost=('cost','mean'),mean_net=('net','mean')).to_csv(OUT/'matched_paths.csv')
    pd.DataFrame(gaps).groupby(['name','period']).agg(events=('roles','size'),mean_roles=('roles','mean'),mean_gap=('weighted_signal_close_to_open','mean')).to_csv(OUT/'signal_to_open.csv')
    pd.DataFrame(coverage).to_csv(OUT/'cohort_coverage.csv',index=False)
    # Paired daily aggregation keeps overlapping events within a session together.
    pairs=[];rng=np.random.default_rng(20261118)
    for name in NAMES:
        for period in ('A','B'):
            f=frame[(frame.name==name)&(frame.period==period)&(frame.horizon==12)&(frame['mode']=='same_exit')]
            pivot=f.pivot(index=['day','event'],columns='delay',values='net')
            for delay in (1,3):
                daily=(pivot[delay]-pivot[0]).groupby(level='day').mean()
                samples=rng.choice(daily.to_numpy(),size=(2000,len(daily)),replace=True).mean(axis=1)
                pairs.append(dict(name=name,period=period,delay=delay,sessions=len(daily),paired_mean=daily.mean(),lower=np.quantile(samples,.025),upper=np.quantile(samples,.975)))
    pd.DataFrame(pairs).to_csv(OUT/'paired_daily_latency.csv',index=False)
    results=[];ticker=[];reasons=[]
    for name,score in scores.items():
        for start,end in [('2026-10-19','2026-11-01'),('2026-11-01','2026-11-14'),('2026-11-16','2026-11-18')]:
            a,b=[int(times.searchsorted(pd.Timestamp(t,tz='UTC'))) for t in (start,end)]
            for cost in (1,2):
                for delay in (0,1,3):
                    log=[];s=mask_session_signals(score,times,delay,0,'event')
                    r=run_backtest(data,s,StrategySpec(name,(),(),1,1,12,60,3,2),CFG.execution,CFG.risk,CFG.capital,a,b,cost,delay,trade_log=log,exit_mode='joint_close',funded_pair=True,funded_allow_single=True)
                    assert np.isclose(np.prod([1+t['net_return'] for t in log])-1,r.total_return)
                    assert all(0<w<=.150000001 for t in log for w in t['bought_weights'])
                    results.append(dict(name=name,start=start,end_exclusive=end,cost=cost,delay=delay,**r.to_dict()))
                    for symbol in data.symbols:ticker.append(dict(name=name,start=start,cost=cost,delay=delay,symbol=symbol,buys=sum(symbol in t['bought_symbols'] for t in log)))
    pd.DataFrame(results).to_csv(OUT/'account_replays.csv',index=False)
    pd.DataFrame(ticker).to_csv(OUT/'ticker_usage.csv',index=False)
    frame.to_csv(OUT/'event_paths_LOCAL.csv',index=False)
    files=['scripts/five_minute_path_20261118.py','scripts/five_minute_grid_20261118.py','scripts/session_signal_provenance.py','src/autogrid/engine.py','configs/win60_search.yaml']
    (OUT/'manifest.json').write_text(json.dumps(dict(status='COMPLETE_DIAGNOSTIC_NO_PROMOTION',engine_calls=len(results),new_candidates=0,frozen_models=NAMES,input_sha256=previous['complete_input_sha256'],source_sha256=previous['input_sha256'],independent_validation=False,news_macro=False,orders=0,seed=20261118,bootstrap_draws=2000,hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files}),indent=2))
    print(pd.DataFrame(coverage).to_string(index=False));print('engine_calls',len(results))
if __name__=='__main__':
    fd=os.open(OUT/'RUNNING.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
    try:main()
    finally:(OUT/'RUNNING.lock').unlink()
