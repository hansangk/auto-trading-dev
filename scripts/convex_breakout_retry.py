"""Convex payoff breakout: low win rate permitted, maximize net return."""
import json,hashlib
from pathlib import Path
from itertools import product
from concurrent.futures import ProcessPoolExecutor
import numpy as np,pandas as pd
from autogrid.data import load_market_data
from autogrid.features import FeatureCache
from autogrid.config import load_config
from autogrid.strategy import StrategySpec
from autogrid.engine import run_backtest
OUT=Path('runs/convex_breakout_retry');OUT.mkdir(parents=True,exist_ok=True);ROOT=Path('runs/multiframe_pilot');CFG=load_config('configs/win60_search.yaml');CACHE={}
FAST=('donchian_10','donchian_20','atrbreak_14','rangepos_20','macd_5_20_7','ema_5_20','roc_10','stoch_14','obv_20','cmf_20')
SLOW=('roc_10','ema_3_15','donchian_20','macd_5_20_7','atrbreak_14','volratio_60')
def context():
 if CACHE:return CACHE['x']
 f=load_market_data(ROOT/'market_15m.csv');s=load_market_data(ROOT/'market_60m.csv');ft=pd.to_datetime(f.timestamps,utc=True);st=pd.to_datetime(s.timestamps,utc=True);ix=np.searchsorted((st+pd.Timedelta(minutes=60)).asi8,(ft+pd.Timedelta(minutes=15)).asi8,side='right')-1;valid=ix>=0
 local=ft.tz_convert('America/New_York');minutes=np.asarray(local.hour*60+local.minute);valid &= ((minutes>=600)&(minutes<690))|((minutes>=840)&(minutes<930))
 fc=FeatureCache(f);sc=FeatureCache(s)
 for k in FAST:fc.cross_sectional_rank(k)
 for k in SLOW:sc.cross_sectional_rank(k)
 CACHE['x']=(f,ft,fc,sc,ix,valid);return CACHE['x']
def eval_one(task):
 x,period,cost,delay=task;f,ft,fc,sc,ix,valid=context();fr=fc.cross_sectional_rank(x['fast']);sr=np.zeros(f.shape,dtype=np.float32);sr[valid]=sc.cross_sectional_rank(x['slow'])[ix[valid]]
 score=.5*fr+.5*sr
 # Both timeframes must agree on both sides; avoid weak/tied scores.
 agree=(np.argmax(fr,axis=1)==np.argmax(sr,axis=1))&(np.argmin(fr,axis=1)==np.argmin(sr,axis=1))&(np.ptp(fr,axis=1)>0)&(np.ptp(sr,axis=1)>0)
 score[~(valid&agree)]=0
 spec=StrategySpec(x['id'],(x['fast'],x['slow']),(.5,.5),1,1,x['hold'],x['stop'],x['tp'],3)
 bounds={'development':('2024-01-01','2026-01-01'),'recent':('2026-01-01','2026-11-14'),'2024':('2024-01-01','2025-01-01'),'2025':('2025-01-01','2026-01-01')};a,b=[int(np.searchsorted(ft.asi8,pd.Timestamp(t,tz='UTC').value)) for t in bounds[period]]
 z=run_backtest(f,score,spec,CFG.execution,CFG.risk,CFG.capital,a,b,cost,delay);return {**x,'period':period,'cost':cost,'delay':delay,**z.to_dict()}
if __name__=='__main__':
 grid=[]
 for fast,slow,stop,tp,hold in product(FAST,SLOW,(20.,40.),(3.,6.),(4,12)):
  x=dict(fast=fast,slow=slow,stop=stop,tp=tp,hold=hold);x['id']=hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()[:12];grid.append(x)
 (OUT/'manifest.json').write_text(json.dumps({'grid_count':len(grid),'grid':grid,'criterion':'development net return >=80 rounds; no win-rate filter; top30','note':'intraday only, previously seen 2026'},indent=2))
 with ProcessPoolExecutor(max_workers=6) as pool:
  dev=list(pool.map(eval_one,[(x,'development',1.,0) for x in grid],chunksize=12));df=pd.DataFrame(dev).sort_values(['total_return','id'],ascending=[False,True]);df.to_csv(OUT/'development.csv',index=False)
  ids=df[df.rounds>=80].head(30).id.tolist();(OUT/'selected_ids.json').write_text(json.dumps(ids));selected=[x for x in grid if x['id'] in ids]
  print('development',len(grid),'selected',len(selected),flush=True)
  recent=list(pool.map(eval_one,[(x,'recent',cost,delay) for x in selected for cost,delay in ((1.,0),(2.,0),(1.,1))],chunksize=3));pd.DataFrame(recent).to_csv(OUT/'recent.csv',index=False)
 print('complete',len(dev)+len(recent),flush=True)
