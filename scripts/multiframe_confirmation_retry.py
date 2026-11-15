"""Paired 15m/60m agreement gate and short exclusions, retrospective."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from autogrid.config import load_config
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.features import FeatureCache
from autogrid.strategy import StrategySpec

root=Path('runs/multiframe_pilot');out=Path('runs/multiframe_confirmation_retry');out.mkdir(parents=True,exist_ok=True)
fast=load_market_data(root/'market_15m.csv');slow=load_market_data(root/'market_60m.csv');cfg=load_config('configs/win60_search.yaml')
assert fast.symbols==slow.symbols
fc=FeatureCache(fast);sc=FeatureCache(slow)
ft=pd.to_datetime(fast.timestamps,utc=True);st=pd.to_datetime(slow.timestamps,utc=True)
closefast=ft+pd.Timedelta(minutes=15);closeslow=st+pd.Timedelta(minutes=60)
mapping=np.searchsorted(closeslow.asi8,closefast.asi8,side='right')-1;valid=mapping>=0
assert np.all(closeslow.asi8[mapping[valid]]<=closefast.asi8[valid])
combos=pd.read_csv(root/'all_development.csv').head(30)
cut=int(np.searchsorted(ft.asi8,pd.Timestamp('2026-01-01',tz='UTC').value))
rows=[]
for _,r in combos.iterrows():
 fr=fc.cross_sectional_rank(r.fast_feature);sr=np.zeros(fast.shape,dtype=np.float32);sr[valid]=sc.cross_sectional_rank(r.slow_feature)[mapping[valid]]
 score=r.weight_fast*fr+(1-r.weight_fast)*sr;score[~valid]=0
 # Require both fast and slow ranks to identify the same extreme long and short.
 agree=valid & (np.argmax(fr,axis=1)==np.argmax(sr,axis=1)) & (np.argmin(fr,axis=1)==np.argmin(sr,axis=1)) & (np.ptp(fr,axis=1)>0) & (np.ptp(sr,axis=1)>0)
 gated=score.copy();gated[~agree]=0
 spec=StrategySpec(r.strategy_id,(r.fast_feature,r.slow_feature),(r.weight_fast,1-r.weight_fast),1,1,int(r.hold),float(r.stop_bps),float(r.take_profit_multiple),3)
 for name,signal,excluded in [('baseline',score,frozenset()),('agreement',gated,frozenset()),('agreement_short_exclusion',gated,frozenset({'BITI','BITX'}))]:
  for period,a,b in [('development',0,cut),('recent',cut,len(ft))]:
   for cost in (1.,2.):
    z=run_backtest(fast,signal,spec,cfg.execution,cfg.risk,cfg.capital,a,b,cost_multiplier=cost,short_exclude_symbols=excluded)
    rows.append({'strategy_id':r.strategy_id,'rule':name,'period':period,'cost':cost,**z.to_dict()})
pd.DataFrame(rows).to_csv(out/'results.csv',index=False)
(out/'manifest.json').write_text(json.dumps({'grid':'top 30 previously chosen via development return','gating':'fast and last fully completed slow timeframe select same top and bottom asset','caveat':'both timeframes use common IEX bars; risk resets per period; period reused; exploratory not independent'},indent=2))
print('rows',len(rows))
