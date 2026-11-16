"""Past-completed shadow trade gate; live-account risk limits unchanged."""
import json
from pathlib import Path
from dataclasses import replace
import numpy as np
import pandas as pd
import tqqq_bitcoin_pair_retry as base
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec

OUT=Path('runs/shadow_gate_retry')

def make_gate(times,log,window,threshold):
    # Conservatively release every result after its recorded end bar.
    events=sorted((int(times.searchsorted(pd.Timestamp(t['end'])))+1,t['net_return']) for t in log)
    gate=np.zeros(len(times),bool); history=[]; cursor=0
    for i in range(len(times)):
        while cursor<len(events) and events[cursor][0]<=i:
            history.append(events[cursor][1]);cursor+=1
        if len(history)>=window:
            gate[i]=np.mean(history[-window:])>threshold
    return gate

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    original,times,_=base.context()
    local=times.tz_convert('America/New_York')
    keep=(local.minute==30)&(local.hour>=9)&(local.hour<16)
    data=replace(original,timestamps=original.timestamps[keep],**{k:getattr(original,k)[keep] for k in ('open','high','low','close','volume')})
    times=times[keep];ratio=pd.Series(np.log(data.close[:,0]/data.close[:,1]))
    base.CACHE['x']=(data,times,ratio)
    score=base.pair_signal(dict(mode='dual_momentum',window=24,threshold=.75))
    spec=StrategySpec('shadow_anchor',('dual_momentum',),(1.,),1,1,4,60.,3.,2)
    # Shadow is a signal observer, never the account equity or reported return.
    observer_risk=replace(base.CFG.risk,daily_soft_loss=1.,daily_hard_loss=1.,max_drawdown=1.,max_loss_streak=10**9)
    rows=[];events=[]
    for cost,delay in [(1.,0),(2.,0),(1.,1)]:
        shadow=[]
        run_backtest(data,score,spec,base.CFG.execution,observer_risk,base.CFG.capital,
                     cost_multiplier=cost,signal_delay_bars=delay,exit_mode='joint_close',trade_log=shadow)
        for t in shadow:events.append(dict(cost=cost,delay=delay,**t))
        for window,threshold in [(0,0),(6,0),(12,0),(24,0),(12,.0001),(24,.0001)]:
            gate=np.ones(len(times),bool) if window==0 else make_gate(times,shadow,window,threshold)
            gated=score.copy();gated[~gate]=0
            for period,first,last in [('2025H2','2025-07-01','2026-01-01'),('2026','2026-01-01','2026-11-14')]:
                a=int(times.searchsorted(pd.Timestamp(first,tz='UTC')));b=int(times.searchsorted(pd.Timestamp(last,tz='UTC')))
                actual=[]
                r=run_backtest(data,gated,spec,base.CFG.execution,base.CFG.risk,base.CFG.capital,a,b,cost,delay,exit_mode='joint_close',trade_log=actual)
                assert np.isclose(np.prod([1+t['net_return'] for t in actual])-1,r.total_return)
                rows.append(dict(window=window,threshold=threshold,period=period,cost=cost,delay=delay,enabled_fraction=float(gate[a:b].mean()),**r.to_dict()))
    frame=pd.DataFrame(rows);frame.to_csv(OUT/'results.csv',index=False)
    pd.DataFrame(events).to_json(OUT/'shadow_ledger.jsonl',orient='records',lines=True)
    (OUT/'manifest.json').write_text(json.dumps(dict(evaluations=len(rows),observer_runs=3,live_risk='unchanged',
         warning='Shadow limits disabled for observation only. Reused 2026, no independent holdout; outcomes released one bar after recorded end.'),indent=2))
    print(frame[['window','threshold','period','cost','delay','total_return','rounds']].to_string(index=False))

if __name__=='__main__':main()
