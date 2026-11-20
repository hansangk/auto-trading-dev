"""Challenge winner-take-all selection with diverse family agreement."""
import json
from pathlib import Path
from itertools import product
import numpy as np
import pandas as pd
from tqqq_bitcoin_pair_retry import context,pair_signal,CFG
from autogrid.strategy import StrategySpec
from autogrid.engine import run_backtest

OUT=Path('runs/committee_retry')

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    data,times,ratio=context()
    # Fix exits for both training and deployment, unlike prior override experiments.
    spec=StrategySpec('committee',('committee',),(1.,),1,1,4,60.,3.,2)
    changes=pd.DataFrame(np.log(data.close)).diff(6)
    a,b=changes.iloc[:,0],changes.iloc[:,1]
    states=np.where((a>0)&(b>0),0,np.where((a<0)&(b<0),1,np.where((a>0)&(b<0),2,3)))
    states=np.where(changes.isna().any(axis=1)|(a==0)|(b==0),-1,states)
    signals=[]
    for mode,window,threshold in product(('momentum','mean_reversion','dual_momentum','macd'),(6,24),(.75,1.5)):
        x=dict(mode=mode,window=window,threshold=threshold)
        signals.append((x,pair_signal(x)))
    policies={key:np.zeros(data.shape,dtype=np.float32) for key in ('winner','committee2','committee3')}
    decisions=[]
    for month in pd.date_range('2025-07-01','2026-11-01',freq='MS',tz='UTC'):
        bounds=[int(times.searchsorted(month-pd.Timedelta(days=n))) for n in (180,90,0)]
        future=(times>=month)&(times<month+pd.offsets.MonthBegin(1))
        for state in range(4):
            winners={}
            for i,(x,score) in enumerate(signals):
                gate=score.copy();gate[states!=state]=0
                halves=[run_backtest(data,gate,spec,CFG.execution,CFG.risk,CFG.capital,l,r,2.,0) for l,r in zip(bounds[:-1],bounds[1:])]
                if not all(z.rounds>=5 and z.total_return>0 and z.profit_factor>1.1 for z in halves):continue
                value=min(z.total_return-.5*z.max_drawdown for z in halves)
                old=winners.get(x['mode'])
                if old is None or value>old[0]:winners[x['mode']]=(value,i)
            ids=[v[1] for v in winners.values()]
            mask=future&(states==state)
            if ids:
                best=max(winners.values())[1]
                policies['winner'][mask]=signals[best][1][mask]
                votes=np.stack([signals[i][1][:,0] for i in ids])
                for required in (2,3):
                    positive=(votes>0).sum(axis=0);negative=(votes<0).sum(axis=0)
                    direction=np.where((positive>=required)&(negative==0),1,np.where((negative>=required)&(positive==0),-1,0))
                    policies[f'committee{required}'][mask]=np.column_stack((direction,-direction))[mask]
            decisions.append(dict(month=str(month),state=state,members=ids,families=list(winners)))
    results=[]
    for policy,score in policies.items():
        for period,first,last in [('2025H2','2025-07-01','2026-01-01'),('2026','2026-01-01','2026-11-14')]:
            for cost,delay in ((1.,0),(2.,0),(1.,1)):
                r=run_backtest(data,score,spec,CFG.execution,CFG.risk,CFG.capital,int(times.searchsorted(pd.Timestamp(first,tz='UTC'))),int(times.searchsorted(pd.Timestamp(last,tz='UTC'))),cost,delay)
                results.append(dict(policy=policy,period=period,cost=cost,delay=delay,**r.to_dict()))
    pd.DataFrame(results).to_csv(OUT/'results.csv',index=False)
    (OUT/'decisions.json').write_text(json.dumps(decisions,indent=2))
    (OUT/'signals.json').write_text(json.dumps([x for x,_ in signals],indent=2))
    print(pd.DataFrame(results)[['policy','period','cost','delay','total_return','rounds','win_rate']].to_string(index=False))

if __name__=='__main__':main()
