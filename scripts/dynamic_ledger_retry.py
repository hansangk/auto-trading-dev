"""Replay archived causal decisions with state ablations and a round ledger."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from tqqq_bitcoin_pair_retry import context, pair_signal, CFG
from autogrid.strategy import StrategySpec
from autogrid.engine import run_backtest

ROOT=Path('runs/dynamic_direction_retry')
OUT=Path('runs/dynamic_ledger_retry')

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    data,times,_=context()
    changes=pd.DataFrame(np.log(data.close)).diff(6)
    a,b=changes.iloc[:,0],changes.iloc[:,1]
    states=np.where((a>0)&(b>0),0,np.where((a<0)&(b<0),1,np.where((a>0)&(b<0),2,3)))
    states=np.where(changes.isna().any(axis=1)|(a==0)|(b==0),-1,states)
    candidates=json.loads((ROOT/'specialists.json').read_text())
    mapping={}
    for i,x in enumerate(candidates):
        spec=StrategySpec(str(i),(x['mode'],),(1.,),1,1,x['hold'],x['stop'],x['tp'],2)
        mapping[i]=(spec,pair_signal(x))
    schedule=np.full(len(times),-1,dtype=int)
    decisions=pd.read_csv(ROOT/'decisions.csv')
    for row in decisions[decisions.minimum==10].itertuples():
        if pd.isna(row.specialist): continue
        month=pd.Timestamp(row.month)
        mask=(times>=month)&(times<month+pd.offsets.MonthBegin(1))&(states==row.state)
        schedule[mask]=int(row.specialist)
    policies={'dynamic_all':schedule,'dynamic_aligned':np.where(states<2,schedule,-1),
              'dynamic_opposed':np.where(states>=2,schedule,-1),'cash':np.full(len(times),-1)}
    anchor=dict(mode='macd',window=6,threshold=.75,hold=6,stop=60.,tp=3.)
    mapping[128]=(StrategySpec('fixed_macd6',('macd',),(1.,),1,1,6,60.,3.,2),pair_signal(anchor))
    policies['fixed_macd6']=np.full(len(times),128)
    results=[]; ledger=[]
    for policy,regimes in policies.items():
        for period,first,last in [('2025H2','2025-07-01','2026-01-01'),('2026','2026-01-01','2026-11-14')]:
            for cost,delay in [(1.,0),(2.,0),(1.,1)]:
                log=[]
                spec,score=mapping[0]
                r=run_backtest(data,score,spec,CFG.execution,CFG.risk,CFG.capital,
                    int(times.searchsorted(pd.Timestamp(first,tz='UTC'))),int(times.searchsorted(pd.Timestamp(last,tz='UTC'))),
                    cost,delay,regime_plan=(regimes,mapping),trade_log=log)
                # Verify the ledger reproduces the returned account result.
                compounded=float(np.prod([1+t['net_return'] for t in log])-1)
                assert np.isclose(compounded,r.total_return,atol=1e-12)
                results.append(dict(policy=policy,period=period,cost=cost,delay=delay,**r.to_dict()))
                for t in log:
                    ledger.append(dict(policy=policy,period=period,cost=cost,delay=delay,state=int(states[t['signal_index']]),**t))
    pd.DataFrame(results).to_csv(OUT/'results.csv',index=False)
    pd.DataFrame(ledger).to_json(OUT/'round_ledger.jsonl',orient='records',lines=True)
    base=pd.DataFrame(ledger).query('cost==1 and delay==0')
    attribution=base.groupby(['policy','period','state']).agg(rounds=('pnl','size'),pnl=('pnl','sum'),mean_net=('net_return','mean'),worst=('net_return','min'))
    attribution.to_csv(OUT/'attribution.csv')
    print(pd.DataFrame(results)[['policy','period','cost','delay','total_return','win_rate','rounds']].to_string(index=False))

if __name__=='__main__': main()
