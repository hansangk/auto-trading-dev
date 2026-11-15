"""Exploratory pre-defined SPY/QQQ relative-value 15m/60m backtest."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from autogrid.config import load_config
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec

root=Path('runs/multiframe_pilot');out=Path('runs/paired_multiframe_experiment');out.mkdir(parents=True,exist_ok=True)
fast=load_market_data(root/'market_15m.csv',symbols=['SPY','QQQ']);slow=load_market_data(root/'market_60m.csv',symbols=['SPY','QQQ'])
cfg=load_config('configs/win60_search.yaml')
ft=pd.to_datetime(fast.timestamps,utc=True); st=pd.to_datetime(slow.timestamps,utc=True)
slow_close=st+pd.Timedelta(minutes=60); fast_close=ft+pd.Timedelta(minutes=15)
mapping=np.searchsorted(slow_close.asi8,fast_close.asi8,side='right')-1;valid=mapping>=0
assert np.all(slow_close.asi8[mapping[valid]]<=fast_close.asi8[valid])
spread=np.log(slow.close[:,0]/slow.close[:,1]); spread15=np.log(fast.close[:,0]/fast.close[:,1]);
fastchange=np.r_[0,np.diff(spread15)];cut=int(np.searchsorted(ft.asi8,pd.Timestamp('2026-01-01',tz='UTC').value)); rows=[]
for lookback in (20,40,60):
 series=pd.Series(spread);z=((series-series.rolling(lookback).mean())/series.rolling(lookback).std()).to_numpy(); aligned=np.full(len(ft),np.nan);aligned[valid]=z[mapping[valid]]
 for threshold in (1.,1.5,2.):
  # Buy underperformer only after its 15m relative return starts reverting.
  direction=np.where((aligned>threshold)&(fastchange<0),-1,np.where((aligned < -threshold)&(fastchange>0),1,0))
  score=np.column_stack([direction,-direction]).astype(float)
  for stop in (80.,150.):
   for hold in (3,6):
    sid=f'pair_spy_qqq_z{lookback}_t{threshold}_s{stop:g}_h{hold}'
    spec=StrategySpec(sid,(),(),1,1,hold,stop,1.5,3)
    for period,a,b in [('development',0,cut),('recent',cut,len(ft))]:
     for cost in (1.,2.):
      result=run_backtest(fast,score,spec,cfg.execution,cfg.risk,cfg.capital,a,b,cost)
      rows.append({'strategy_id':sid,'lookback':lookback,'threshold':threshold,'stop_bps':stop,'hold':hold,'period':period,'cost':cost,**result.to_dict()})
pd.DataFrame(rows).to_csv(out/'results.csv',index=False)
(out/'manifest.json').write_text(json.dumps({'pairs':['SPY','QQQ'],'candidate_count':36,'fast_minutes':15,'slow_minutes':60,'caveat':'preselected on known research results; no fresh holdout, IEX partial, no quote fill, pair beta-neutrality not estimated; existing two-leg execution'},indent=2))
print('candidate_count',36,'rows',len(rows))
