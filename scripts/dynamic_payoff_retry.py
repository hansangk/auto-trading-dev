"""Exit-parameter challenge of archived dynamic decisions, unchanged risk caps."""
import json
from pathlib import Path
from itertools import product
import numpy as np
import pandas as pd
from autogrid.strategy import StrategySpec
from autogrid.engine import run_backtest
from tqqq_bitcoin_pair_retry import context,pair_signal,CFG

OUT=Path('runs/dynamic_payoff_retry')

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    data,times,_=context()
    changes=pd.DataFrame(np.log(data.close)).diff(6)
    a,b=changes.iloc[:,0],changes.iloc[:,1]
    states=np.where((a>0)&(b>0),0,np.where((a<0)&(b<0),1,np.where((a>0)&(b<0),2,3)))
    states=np.where(changes.isna().any(axis=1)|(a==0)|(b==0),-1,states)
    root=Path('runs/dynamic_direction_retry')
    candidates=json.loads((root/'specialists.json').read_text())
    scores=[pair_signal(x) for x in candidates]
    schedule=np.full(len(times),-1,dtype=int)
    decisions=pd.read_csv(root/'decisions.csv')
    for row in decisions[decisions.minimum==10].itertuples():
        if pd.isna(row.specialist):continue
        month=pd.Timestamp(row.month)
        mask=(times>=month)&(times<month+pd.offsets.MonthBegin(1))&(states==row.state)
        schedule[mask]=int(row.specialist)
    results=[]
    grid=list(product(('all','aligned'),(1,-1),(30.,60.,100.,150.),(1.5,3.,6.,10.),(1,2,4,6)))
    for policy,direction,stop,tp,hold in grid:
        mapping={i:(StrategySpec(str(i),(x['mode'],),(1.,),1,1,hold,stop,tp,2),direction*scores[i]) for i,x in enumerate(candidates)}
        regimes=schedule if policy=='all' else np.where((states>=0)&(states<2),schedule,-1)
        for period,first,last in [('2025H2','2025-07-01','2026-01-01'),('2026','2026-01-01','2026-11-14')]:
            for cost,delay in [(1.,0),(2.,0),(1.,1)]:
                spec,score=mapping[0]
                r=run_backtest(data,score,spec,CFG.execution,CFG.risk,CFG.capital,
                    int(times.searchsorted(pd.Timestamp(first,tz='UTC'))),int(times.searchsorted(pd.Timestamp(last,tz='UTC'))),
                    cost,delay,regime_plan=(regimes,mapping))
                results.append(dict(policy=policy,direction=direction,stop=stop,tp=tp,hold=hold,period=period,cost=cost,delay=delay,**r.to_dict()))
    frame=pd.DataFrame(results)
    frame.to_csv(OUT/'results.csv',index=False)
    keys=['policy','direction','stop','tp','hold']
    rank=frame.query("period=='2025H2'").groupby(keys).total_return.min().sort_values(ascending=False)
    rank.rename('worst_2025H2').to_csv(OUT/'development_ranking.csv')
    frame.query("period=='2026' and cost==1 and delay==0").sort_values('total_return',ascending=False).head(30).to_csv(OUT/'posthoc_top30.csv',index=False)
    (OUT/'manifest.json').write_text(json.dumps(dict(candidates=len(grid),evaluations=len(frame),warning='Reused data; exit overrides applied to archived selector, not re-trained; posthoc results are exploratory',risk='unchanged'),indent=2))
    print('best development',rank.head(3).to_string())
    print('posthoc recent',frame.query("period=='2026' and cost==1 and delay==0").sort_values('total_return',ascending=False).head(5).to_string(index=False))

if __name__=='__main__':main()
