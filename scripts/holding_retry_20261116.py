"""Preregistered single-factor hold ablation; refreshed input baseline."""
import hashlib,json,subprocess
from pathlib import Path
from dataclasses import replace
import numpy as np
import pandas as pd
import tqqq_bitcoin_pair_retry as base
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec
OUT=Path('runs/holding_retry_20261116')
def main():
    source=Path('runs/tqqq_bitcoin_retry/yahoo_1h.csv')
    expected='6cf724195d16ce30cd669e7388b8650b16d3088e5f5b35609c0fe6bfe96c535d'
    if hashlib.sha256(source.read_bytes()).hexdigest()!=expected:
        raise ValueError('Input snapshot changed: create a new experiment and refresh comparators')
    plan=json.loads((OUT/'preregistration.json').read_text())
    original,times,_=base.context(); local=times.tz_convert('America/New_York')
    keep=(local.minute==30)&(local.hour>=9)&(local.hour<16)
    data=replace(original,timestamps=original.timestamps[keep],**{k:getattr(original,k)[keep] for k in ('open','high','low','close','volume')})
    times=times[keep];ratio=pd.Series(np.log(data.close[:,0]/data.close[:,1]));base.CACHE['x']=data,times,ratio
    signal_config=dict(mode='dual_momentum',window=24,threshold=.75)
    score=base.pair_signal(signal_config)
    # Derived signal must not change when future observations are removed.
    for n in (100,800,1800):
        prefix=replace(data,timestamps=data.timestamps[:n],**{k:getattr(data,k)[:n] for k in ('open','high','low','close','volume')})
        base.CACHE['x']=prefix,times[:n],ratio[:n]
        np.testing.assert_array_equal(base.pair_signal(signal_config),score[:n])
    base.CACHE['x']=data,times,ratio
    bounds={'2025H1':('2025-01-01','2025-07-01'),'2025H2':('2025-07-01','2026-01-01'),'2026':('2026-01-01','2026-11-14')}
    rows=[]; ledgers=[]
    def evaluate(period,holds):
        a,b=[int(times.searchsorted(pd.Timestamp(x,tz='UTC'))) for x in bounds[period]]
        for cost,delay in [(1.,0),(2.,0),(1.,1)]:
            for hold in holds:
                spec=StrategySpec('hold'+str(hold),('dual_momentum',),(1.,),1,1,hold,60.,3.,2)
                log=[]
                r=run_backtest(data,score,spec,base.CFG.execution,base.CFG.risk,base.CFG.capital,a,b,cost,delay,exit_mode='joint_close',trade_log=log)
                assert np.isclose(np.prod([1+t['net_return'] for t in log])-1,r.total_return)
                for t in log:
                    assert np.isclose(t['long_gross_return']+t['short_gross_return']-t['cost_return'],t['net_return'])
                rows.append(dict(hold=hold,period=period,cost=cost,delay=delay,**r.to_dict()))
                for t in log:ledgers.append(dict(hold=hold,period=period,cost=cost,delay=delay,**t))
    for period in ('2025H1','2025H2'):evaluate(period,plan['holds'])
    dev=pd.DataFrame(rows);anchor=dev[dev.hold==4].set_index(['period','cost','delay'])
    dev['delta_anchor']=[r.total_return-anchor.loc[(r.period,r.cost,r.delay),'total_return'] for r in dev.itertuples()]
    dev['dd_delta']=[r.max_drawdown-anchor.loc[(r.period,r.cost,r.delay),'max_drawdown'] for r in dev.itertuples()]
    dev.to_csv(OUT/'development.csv',index=False)
    rank=dev[dev.hold!=4].groupby('hold').agg(worst=('total_return','min'),mean=('total_return','mean'),min_rounds=('rounds','min'),min_delta=('delta_anchor','min'),max_dd_delta=('dd_delta','max')).reset_index()
    rank['eligible']=rank.min_rounds>=20
    rank['pass']=rank.eligible&(rank.worst>0)&(rank.min_delta>0)&(rank.max_dd_delta<=0)
    rank=rank.sort_values(['eligible','worst','mean','hold'],ascending=[False,False,False,True]);rank.to_csv(OUT/'ranking.csv',index=False)
    chosen=rank[rank.eligible].head(1).hold.tolist()
    (OUT/'selection.json').write_text(json.dumps(dict(selected=chosen,approved=rank[rank['pass']].hold.tolist()),indent=2))
    evaluate('2026',[4]+chosen)
    diag=pd.DataFrame(rows);diag=diag[diag.period=='2026'];diag.to_csv(OUT/'diagnostic.csv',index=False)
    pd.DataFrame(ledgers).to_json(OUT/'ledger.jsonl',orient='records',lines=True)
    source=Path('runs/tqqq_bitcoin_retry/yahoo_1h.csv')
    manifest=dict(status='completed',evaluations=len(rows),development=30,diagnostic=len(diag),source='Yahoo chart 1h redownload 2026-11-16; Bitcoin represented by IBIT ETF',source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),input_period=[str(times[0]),str(times[-1])],periods=bounds,code_parent=plan['input_code'],signal=signal_config,config_sha256=hashlib.sha256(Path('configs/win60_search.yaml').read_bytes()).hexdigest(),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),prefix_checks=3,news_macro=False,independent_holdout=False)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(rank.to_string(index=False));print(diag[['hold','cost','delay','total_return','rounds','win_rate','max_drawdown','profit_factor']].to_string(index=False))
if __name__=='__main__':main()
