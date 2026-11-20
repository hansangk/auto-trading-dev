"""Separate base signal quality from retrospective selector effects."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from tqqq_bitcoin_pair_retry import context,pair_signal,CFG
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec

OUT=Path('runs/selector_ablation_retry')

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    data,times,_=context()
    signals=json.loads(Path('runs/committee_retry/signals.json').read_text())
    score_list=[pair_signal(x) for x in signals]
    spec=StrategySpec('fixed_compare',('pair',),(1.,),1,1,4,60.,3.,2)
    results=[]
    for i,(x,score) in enumerate(zip(signals,score_list)):
        for period,first,last in [('2025H2','2025-07-01','2026-01-01'),('2026','2026-01-01','2026-11-14')]:
            for cost,delay in ((1.,0),(2.,0),(1.,1)):
                # Independent equal-capital sleeves; no intra-period rebalancing.
                r=run_backtest(data,score,spec,CFG.execution,CFG.risk,CFG.capital/16,
                              int(times.searchsorted(pd.Timestamp(first,tz='UTC'))),int(times.searchsorted(pd.Timestamp(last,tz='UTC'))),cost,delay)
                results.append(dict(id=i,**x,period=period,cost=cost,delay=delay,**r.to_dict()))
    frame=pd.DataFrame(results)
    frame.to_csv(OUT/'fixed_signals.csv',index=False)
    equal=frame.groupby(['period','cost','delay']).agg(total_return=('total_return','mean'),rounds=('rounds','sum')).reset_index()
    equal['policy']='equal16_sleeves'
    # Fixed family averages preserve equal initial capital, without pooling risk limits.
    family=frame.groupby(['mode','period','cost','delay']).total_return.mean().reset_index()
    family.to_csv(OUT/'families.csv',index=False)
    dynamic=pd.read_csv('runs/committee_retry/results.csv')
    combined=pd.concat([equal,dynamic[['policy','period','cost','delay','total_return','rounds']]],ignore_index=True)
    combined.to_csv(OUT/'comparison.csv',index=False)
    # Select one fixed signal using only 2025H2 stress, then inspect its 2026 diagnostic.
    ranking=frame.query("period=='2025H2'").groupby('id').total_return.min().sort_values(ascending=False)
    ranking.rename('worst_development').to_csv(OUT/'development_rank.csv')
    chosen=int(ranking.index[0])
    frame[frame.id==chosen].to_csv(OUT/'selected_fixed.csv',index=False)
    (OUT/'manifest.json').write_text(json.dumps(dict(hypothesis='winner selection harms otherwise useful signal families',
        evaluations=len(frame),selected_fixed=chosen,comparison='same per-sleeve risk settings; aggregate portfolio halt not modeled',
        caveat='reused 2026; attribution is diagnostic, not causal proof'),indent=2))
    print(combined.to_string(index=False))
    print('FAMILIES',family.to_string(index=False))
    print('SELECTED',frame[frame.id==chosen][['mode','window','threshold','period','cost','delay','total_return']].to_string(index=False))

if __name__=='__main__':main()
