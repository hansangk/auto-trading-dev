"""Challenge the joint-exit anchor using prespecified economic state filters."""
import json,hashlib
from pathlib import Path
from dataclasses import replace
import numpy as np
import pandas as pd
import tqqq_bitcoin_pair_retry as base
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec

OUT=Path('runs/joint_balance_retry')

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    original,times,_=base.context()
    local=times.tz_convert('America/New_York')
    keep=(local.minute==30)&(local.hour>=9)&(local.hour<16)
    data=replace(original,timestamps=original.timestamps[keep],**{k:getattr(original,k)[keep] for k in ('open','high','low','close','volume')})
    times=times[keep]
    prices=pd.DataFrame(np.log(data.close))
    ratio=prices[0]-prices[1]
    base.CACHE['x']=(data,times,ratio)
    ret=prices.diff()
    corr=ret[0].rolling(40).corr(ret[1])
    vol=ret.std(axis=1).rolling(40).mean()
    median=vol.shift(1).rolling(120).median()
    trend=prices.diff(24)
    aligned=trend[0]*trend[1]>0
    ratio_ret=ratio.diff()
    shock=ratio_ret.abs()/ratio_ret.rolling(40).std().shift(1)
    sigma=ret.rolling(40).std()
    balanced=sigma.min(axis=1).to_numpy()[:,None]/sigma.to_numpy()
    balanced=np.clip(np.nan_to_num(balanced,nan=1.,posinf=1.),.01,1.)
    # Uniform shrinkage controls for the same total initial exposure.
    uniform=np.repeat(balanced.mean(axis=1)[:,None],2,axis=1)
    filters={'anchor':None,'risk_balance':balanced,'uniform_same_gross':uniform}
    x=dict(mode='dual_momentum',window=24,threshold=.75)
    score=base.pair_signal(x)
    spec=StrategySpec('joint_anchor',('dual_momentum',),(1.,),1,1,4,60.,3.,2)
    rows=[];ledger=[]
    for name,scales in filters.items():
        gated=score.copy()
        for period,first,last in [('2025H2','2025-07-01','2026-01-01'),('2026','2026-01-01','2026-11-14')]:
            for cost,delay in ((1.,0),(2.,0),(1.,1)):
                log=[]
                r=run_backtest(data,gated,spec,base.CFG.execution,base.CFG.risk,base.CFG.capital,
                    int(times.searchsorted(pd.Timestamp(first,tz='UTC'))),int(times.searchsorted(pd.Timestamp(last,tz='UTC'))),
                    cost,delay,exit_mode='joint_close',trade_log=log,asset_weight_scale=scales)
                rows.append(dict(filter=name,period=period,cost=cost,delay=delay,**r.to_dict()))
                if name=='anchor' and cost==1 and delay==0:
                    for t in log:
                        idx=t['signal_index']
                        ledger.append(dict(period=period,positive_corr=bool(corr.iloc[idx]>.3),quiet=bool(vol.iloc[idx]<=median.iloc[idx]),aligned=bool(aligned.iloc[idx]),shock=float(shock.iloc[idx]),**t))
    df=pd.DataFrame(rows);df.to_csv(OUT/'results.csv',index=False)
    pd.DataFrame(ledger).to_json(OUT/'anchor_ledger.jsonl',orient='records',lines=True)
    ranking=df.query("period=='2025H2'").groupby('filter').total_return.min().sort_values(ascending=False)
    ranking.rename('worst_development').to_csv(OUT/'development_ranking.csv')
    (OUT/'manifest.json').write_text(json.dumps(dict(evaluations=len(rows),filters=list(filters),selected=ranking.index[0],
       source_sha256=hashlib.sha256(Path('runs/tqqq_bitcoin_retry/yahoo_1h.csv').read_bytes()).hexdigest(),
       note='2026 reused diagnostic. Anchor previously selected using 2026. Close-based joint stop, not intrabar guarantee.'),indent=2))
    print(df[['filter','period','cost','delay','total_return','rounds']].to_string(index=False))
    print('selected',ranking.index[0])

if __name__=='__main__':main()
