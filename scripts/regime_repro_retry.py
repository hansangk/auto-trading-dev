"""Regime gated breakout with year-by-year robustness review."""
from pathlib import Path
from itertools import product
from concurrent.futures import ProcessPoolExecutor
import json,hashlib
import numpy as np,pandas as pd
from autogrid.data import load_market_data
from autogrid.features import FeatureCache
from autogrid.config import load_config
from autogrid.strategy import StrategySpec
from autogrid.engine import run_backtest
ROOT=Path('runs/multiframe_pilot');OUT=Path('runs/regime_repro_retry');OUT.mkdir(parents=True,exist_ok=True);CFG=load_config('configs/win60_search.yaml');CACHE={}
def context():
 if CACHE:return CACHE['x']
 f=load_market_data(ROOT/'market_15m.csv');s=load_market_data(ROOT/'market_60m.csv');ft=pd.to_datetime(f.timestamps,utc=True);st=pd.to_datetime(s.timestamps,utc=True)
 ix=np.searchsorted((st+pd.Timedelta(minutes=60)).asi8,(ft+pd.Timedelta(minutes=15)).asi8,side='right')-1;valid=ix>=0
 local=ft.tz_convert('America/New_York');mins=np.asarray(local.hour*60+local.minute);valid &= ((mins>=600)&(mins<690))|((mins>=840)&(mins<930))
 sc=FeatureCache(s);fc=FeatureCache(f)
 returns=pd.DataFrame(np.log(s.close)).diff();vol=returns.rolling(20).std().mean(axis=1)
 history=vol.rolling(60,min_periods=60);q25=history.quantile(.25);q75=history.quantile(.75)
 # Fully closed 60m indices only. Stress moving volatility and cross-market trend states.
 qqq=s.symbols.index('QQQ');trend=(np.abs(sc.get('roc_10')[:,qqq])/returns.iloc[:,qqq].rolling(20).std().replace(0,np.nan)).to_numpy()
 state={}
 for name,mask in [('vol_low',vol<=q25),('vol_high',vol>=q75),('trend_low',trend<=2),('trend_high',trend>=2)]:
  a=np.zeros(len(ft),dtype=bool);a[valid]=np.asarray(mask)[ix[valid]];state[name]=a
 CACHE['x']=(f,ft,fc,sc,ix,valid,state);return CACHE['x']
def evaluate(task):
 x,period,cost,delay=task;f,ft,fc,sc,ix,valid,state=context();fast=fc.cross_sectional_rank(x['fast']);slow=np.zeros(f.shape,dtype=np.float32);slow[valid]=sc.cross_sectional_rank(x['slow'])[ix[valid]]
 score=.5*fast+.5*slow;agree=(np.argmax(fast,axis=1)==np.argmax(slow,axis=1))&(np.argmin(fast,axis=1)==np.argmin(slow,axis=1))&(np.ptp(fast,axis=1)>0)&(np.ptp(slow,axis=1)>0)
 margin=np.sort(score,axis=1);gap=(margin[:,-1]-margin[:,-2]>=x['gap'])&(margin[:,1]-margin[:,0]>=x['gap'])
 score[~(valid&agree&gap&state[x['regime']])]=0
 spec=StrategySpec(x['id'],(x['fast'],x['slow']),(.5,.5),1,1,x['hold'],x['stop'],x['tp'],3)
 bounds={'development':('2024-01-01','2026-01-01'),'2024':('2024-01-01','2025-01-01'),'2025':('2025-01-01','2026-01-01'),'recent':('2026-01-01','2026-11-14')}
 a,b=[int(np.searchsorted(ft.asi8,pd.Timestamp(t,tz='UTC').value)) for t in bounds[period]]
 r=run_backtest(f,score,spec,CFG.execution,CFG.risk,CFG.capital,a,b,cost,delay)
 return {**x,'period':period,'cost':cost,'delay':delay,**r.to_dict()}
if __name__=='__main__':
 old=pd.read_csv('runs/convex_breakout_retry/development.csv').head(30);grid=[]
 for _,row in old.iterrows():
  for regime,gap in product(('vol_low','vol_high','trend_low','trend_high'),(0.,.2)):
   x={k:row[k] for k in ('fast','slow','stop','tp','hold')};x.update(regime=regime,gap=gap);x['id']=hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()[:12];grid.append(x)
 (OUT/'manifest.json').write_text(json.dumps({'grid_count':len(grid),'grid':grid,'selection':'development return >=40 rounds top30, inspect 2024/25; recent already inspected, exploratory'},indent=2))
 with ProcessPoolExecutor(max_workers=6) as pool:
  dev=list(pool.map(evaluate,[(x,'development',1.,0) for x in grid],chunksize=8));df=pd.DataFrame(dev).sort_values(['total_return','id'],ascending=[False,True]);df.to_csv(OUT/'development.csv',index=False)
  ids=df[df.rounds>=40].head(30).id.tolist();(OUT/'selected_ids.json').write_text(json.dumps(ids));picked=[x for x in grid if x['id'] in ids]
  years=list(pool.map(evaluate,[(x,p,1.,0) for x in picked for p in ('2024','2025')],chunksize=4));pd.DataFrame(years).to_csv(OUT/'year_splits.csv',index=False)
  recent=list(pool.map(evaluate,[(x,'recent',cost,delay) for x in picked for cost,delay in ((1.,0),(2.,0),(1.,1))],chunksize=3));pd.DataFrame(recent).to_csv(OUT/'recent.csv',index=False)
 print('complete',len(dev)+len(years)+len(recent),flush=True)
