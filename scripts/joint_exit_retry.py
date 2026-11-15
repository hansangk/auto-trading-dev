"""Controlled exit ablation with hourly session-start sanity filtering."""
import json
from pathlib import Path
from dataclasses import replace
import numpy as np
import pandas as pd
import tqqq_bitcoin_pair_retry as base
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec

OUT=Path('runs/joint_exit_retry')

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    original,times,_=base.context()
    local=times.tz_convert('America/New_York')
    # Yahoo regular hourly bars start at :30. Remove :00 close snapshots;
    # not a full exchange-calendar audit and no current-bar volume filter.
    valid=(local.minute==30)&(local.hour>=9)&(local.hour<16)
    data=replace(original, timestamps=original.timestamps[valid],
                 **{k:getattr(original,k)[valid] for k in ('open','high','low','close','volume')})
    times=times[valid]
    ratio=pd.Series(np.log(data.close[:,0]/data.close[:,1]))
    base.CACHE['x']=(data,times,ratio)
    inputs=json.loads(Path('runs/committee_retry/signals.json').read_text())
    results=[]; logs=[]
    for sid,x in enumerate(inputs):
        score=base.pair_signal(x)
        spec=StrategySpec(str(sid),(x['mode'],),(1.,),1,1,4,60.,3.,2)
        for mode,reentry in [('independent',False),('fixed_close',False),('joint_close',False),('joint_close',True)]:
            for period,first,last in [('2025H2','2025-07-01','2026-01-01'),('2026','2026-01-01','2026-11-14')]:
                for cost,delay in [(1.,0),(2.,0),(1.,1)]:
                    ledger=[]
                    r=run_backtest(data,score,spec,base.CFG.execution,base.CFG.risk,base.CFG.capital,
                        int(times.searchsorted(pd.Timestamp(first,tz='UTC'))),int(times.searchsorted(pd.Timestamp(last,tz='UTC'))),
                        cost,delay,trade_log=ledger,exit_mode=mode,early_reentry=reentry)
                    assert np.isclose(np.prod([1+t['net_return'] for t in ledger])-1,r.total_return)
                    results.append(dict(id=sid,**x,exit_mode=mode,reentry=reentry,period=period,cost=cost,delay=delay,**r.to_dict()))
    frame=pd.DataFrame(results)
    frame.to_csv(OUT/'results.csv',index=False)
    paired=frame.pivot(index=['id','period','cost','delay'],columns=['exit_mode','reentry'],values='total_return')
    paired.to_csv(OUT/'paired.csv')
    (OUT/'manifest.json').write_text(json.dumps(dict(removed_common_bars=int((~valid).sum()),remaining_bars=len(times),evaluations=len(frame),
        caveats=['No full holiday calendar audit','Joint stop checks completed close and fills next open; no intrabar guarantee','Reentry occurs bar after exit','Fixed signals; no dynamic selector'] ),indent=2))
    print(frame.groupby(['exit_mode','reentry','period','cost','delay']).total_return.mean().to_string())
    print('best recent',frame.query("period=='2026' and cost==1 and delay==0").sort_values('total_return',ascending=False).head(4).to_string(index=False))

if __name__=='__main__':main()
