"""Frozen direction information controls, not a search for profitable seeds."""
from pathlib import Path
import hashlib,json,os
import pandas as pd
import numpy as np
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec
from inverse_etf_retry_20261116 import CFG
from five_minute_grid_20261118 import signals as momentum
from structural_signals_20261118 import signals as structural
from session_signal_provenance import mask_session_signals
OUT=Path('runs/direction_control_20261119')
INPUT=Path('runs/extended_snapshot_20261118/refreshed_all_LOCAL.csv.gz')
FAMILIES=('event_independent','event_shared','session_independent','session_shared')
STRESS=(('base',1,0),('cost2',2,0),('delay1',1,1))

def controlled_scores(source,times,family,seed):
    if family not in FAMILIES:raise ValueError('Unknown direction control')
    if source.shape!=(len(times),4):raise ValueError('Expected n by four actual ETF roles')
    result=np.zeros_like(source);times=pd.DatetimeIndex(times).tz_convert('America/New_York')
    for k in np.flatnonzero(np.any(source,axis=1)):
        clock=times[k].date().isoformat() if family.startswith('session') else times[k].isoformat()
        for role,(bull,bear,sign) in enumerate(((0,1,1),(2,3,-1))):
            if not np.any(source[k,[bull,bear]]):continue
            group=0 if family.endswith('shared') else role
            key=f'{family}|{seed}|{clock}|{group}'.encode()
            bullish=hashlib.sha256(key).digest()[0]%2==0
            result[k,bull if bullish else bear]=sign
    return result

def main():
    if (OUT/'manifest.json').exists():raise SystemExit('Completed run protected')
    assert hashlib.sha256(INPUT.read_bytes()).hexdigest()=='ebbdc8b683532ba96bf5c1358f5656833d6c33fe6833268ce1e13a777254b851'
    data=load_market_data(INPUT,['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True);days=times.tz_convert('America/New_York').date
    source=momentum(data,times,dict(family='momentum',a=4,b=.5))
    controls={f'{f}_{seed}':controlled_scores(source,times,f,seed) for f in FAMILIES for seed in range(16)}
    scores={'baseline':source,'cash':np.zeros_like(source),'opposite':source[:,[1,0,3,2]],'expiry_reference':structural(data,times,dict(family='compression_expiry',a=1,b=0)),**controls}
    # Fixed stress seeds; no ranking or fitting chooses a random winner.
    stress_ids=[f'{f}_{seed}' for f in FAMILIES for seed in (0,1)]
    fixed=['baseline','cash','opposite','expiry_reference'];rows=[];ticker=[];logs={};cache={}
    def evaluate(name,start,end,scenario,cost,delay):
        key=(name,start,end,scenario)
        if key not in cache:
            a,b=[int(times.searchsorted(pd.Timestamp(t,tz='UTC'))) for t in (start,end)];log=[]
            result=run_backtest(data,mask_session_signals(scores[name],times,delay,0,'event'),StrategySpec(name,(),(),1,1,12,60,3,2),CFG.execution,CFG.risk,CFG.capital,a,b,cost,delay,trade_log=log,exit_mode='joint_close',funded_pair=True,funded_allow_single=True)
            assert np.isclose(np.prod([1+t['net_return'] for t in log])-1,result.total_return)
            assert all(0<w<=.150000001 for t in log for w in t['bought_weights'])
            row=dict(name=name,start=start,end_exclusive=end,scenario=scenario,**result.to_dict());rows.append(row);cache[key]=row;logs[key]=log
            for symbol in data.symbols:ticker.append(dict(name=name,start=start,scenario=scenario,symbol=symbol,buys=sum(symbol in t['bought_symbols'] for t in log)))
        return cache[key]
    periods=[('2026-08-25','2026-09-20'),('2026-09-20','2026-10-19')]
    for a,b in periods:
        for name in controls:evaluate(name,a,b,*STRESS[0])
        for name in stress_ids+fixed:
            for stress in STRESS:evaluate(name,a,b,*stress)
    for name in stress_ids+fixed:
        for stress in STRESS:evaluate(name,'2026-10-19','2026-11-18',*stress)
    # All potential source events, common support for both raw entry latencies.
    labels=[];coverage=[];contributions=[]
    for period,(a,b) in zip(('A','B'),periods):
        count=volume_excluded=late=0
        for k in np.flatnonzero(np.any(source,axis=1)):
            if not pd.Timestamp(a,tz='UTC')<=times[k]<pd.Timestamp(b,tz='UTC'):continue
            count+=1
            if k+12>=len(times) or days[k]!=days[k+12]:late+=1;continue
            active=[role for role,cols in enumerate(((0,1),(2,3))) if np.any(source[k,list(cols)])]
            if any(np.any(data.volume[k,[2*role,2*role+1]]<=0) for role in active):volume_excluded+=1;continue
            cost=.15*len(active)*.00046
            for delay in (0,1):
                entry=k+1+delay;end=k+12
                for name in ['baseline','opposite']+list(controls):
                    chosen=np.flatnonzero(scores[name][k]);gross=.15*np.sum(data.close[end,chosen]/data.open[entry,chosen]-1)
                    labels.append(dict(period=period,day=str(days[k]),event=k,delay=delay,name=name,gross=gross,cost=cost,net=gross-cost))
                    if name=='baseline':
                        for j in chosen:contributions.append(dict(period=period,delay=delay,symbol=data.symbols[j],gross=.15*(data.close[end,j]/data.open[entry,j]-1),cost=.15*.00046))
        coverage.append(dict(period=period,potential_events=count,late_excluded=late,volume_excluded=volume_excluded))
    frame=pd.DataFrame(labels)
    frame.groupby(['period','delay','name']).agg(events=('net','size'),gross=('gross','mean'),cost=('cost','mean'),net=('net','mean')).to_csv(OUT/'fixed_opportunity.csv')
    pd.DataFrame(contributions).groupby(['period','delay','symbol']).agg(role_events=('gross','size'),mean_gross=('gross','mean'),mean_cost=('cost','mean')).to_csv(OUT/'role_contributions.csv')
    # Average seeds within each same event before clustering by day, including zero-opportunity days.
    paired=[];rng=np.random.default_rng(20261119)
    for period,(a,b) in zip(('A','B'),periods):
        all_days=sorted(set(str(d) for d,t in zip(days,times) if pd.Timestamp(a,tz='UTC')<=t<pd.Timestamp(b,tz='UTC')))
        for delay in (0,1):
            f=frame[(frame.period==period)&(frame.delay==delay)];idx=['day','event']
            base=f[f.name=='baseline'].set_index(idx).net
            average=f[f.name.isin(controls)].groupby(idx).net.mean()
            difference=(base-average).groupby(level='day').mean().reindex(all_days,fill_value=0)
            draws=rng.choice(difference.to_numpy(),size=(2000,len(all_days)),replace=True).mean(axis=1)
            paired.append(dict(period=period,delay=delay,days=len(all_days),events=len(base),daily_mean_delta=difference.mean(),lower=np.quantile(draws,.025),upper=np.quantile(draws,.975)))
    pd.DataFrame(paired).to_csv(OUT/'paired_daily.csv',index=False)
    pd.DataFrame(coverage).to_csv(OUT/'coverage.csv',index=False)
    pd.DataFrame(rows).to_csv(OUT/'account_replays.csv',index=False);pd.DataFrame(ticker).to_csv(OUT/'ticker_usage.csv',index=False)
    control_rows=pd.DataFrame(rows);control_rows=control_rows[control_rows.name.isin(stress_ids)].groupby(['start','scenario']).agg(seed_count=('name','size'),mean_return=('total_return','mean'),min_return=('total_return','min'),max_return=('total_return','max'),mean_rounds=('rounds','mean'),mean_drawdown=('max_drawdown','mean'))
    control_rows.to_csv(OUT/'control_summary.csv')
    frame.to_csv(OUT/'potential_paths_LOCAL.csv',index=False)
    hashes={n:hashlib.sha256(s[times<pd.Timestamp('2026-10-19',tz='UTC')].tobytes()).hexdigest() for n,s in controls.items()}
    files=['scripts/direction_control_20261119.py','scripts/five_minute_grid_20261118.py','scripts/session_signal_provenance.py','src/autogrid/engine.py','configs/win60_search.yaml']
    (OUT/'manifest.json').write_text(json.dumps(dict(status='COMPLETE_DIRECTION_AUDIT',engine_calls=len(rows),new_alpha_candidates=0,control_configs=64,distinct_arrays=len(set(hashes.values())),seed_range=[0,15],stress_seeds=[0,1],stress_ids=stress_ids,approved=[],input_sha256=hashlib.sha256(INPUT.read_bytes()).hexdigest(),independent_validation=False,news_macro=False,orders=0,bootstrap_seed=20261119,hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files}),indent=2))
    print(pd.DataFrame(paired).to_string(index=False));print('calls',len(rows))
if __name__=='__main__':
    fd=os.open(OUT/'RUNNING.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
    try:main()
    finally:(OUT/'RUNNING.lock').unlink()
