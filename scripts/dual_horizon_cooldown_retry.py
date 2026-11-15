"""Intraday dual horizon switch: fixed scalp anchor plus selective trend leg."""
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
OUT=Path('runs/dual_horizon_cooldown_retry');OUT.mkdir(parents=True,exist_ok=True);ROOT=Path('runs/multiframe_pilot');CFG=load_config('configs/win60_search.yaml');CACHE={}
def context():
 if CACHE:return CACHE['x']
 f=load_market_data(ROOT/'market_15m.csv');s=load_market_data(ROOT/'market_60m.csv');ft=pd.to_datetime(f.timestamps,utc=True);st=pd.to_datetime(s.timestamps,utc=True)
 ix=np.searchsorted((st+pd.Timedelta(minutes=60)).asi8,(ft+pd.Timedelta(minutes=15)).asi8,side='right')-1;valid=ix>=0
 local=ft.tz_convert('America/New_York');mins=np.asarray(local.hour*60+local.minute)
 valid &= ((mins>=600)&(mins<690))|((mins>=840)&(mins<930))
 fc=FeatureCache(f);sc=FeatureCache(s);fa=fc.cross_sectional_rank('ema_3_15');sb=np.zeros(f.shape,dtype=np.float32);sb[valid]=sc.cross_sectional_rank('stochrsi_14')[ix[valid]]
 base=.75*fa+.25*sb;v=np.sort(base,axis=1);agreement=(np.argmax(fa,axis=1)==np.argmax(sb,axis=1))&(np.argmin(fa,axis=1)==np.argmin(sb,axis=1))&(np.ptp(fa,axis=1)>0)&(np.ptp(sb,axis=1)>0)
 c=fc.cross_sectional_rank('stoch_14');long=np.argmax(base,axis=1);short=np.argmin(base,axis=1)
 gate=agreement&(v[:,-1]-v[:,-2]>=.1)&(v[:,1]-v[:,0]>=.1)&(c[np.arange(len(c)),long]>0)&(c[np.arange(len(c)),short]<0)
 scalp=base.copy();scalp[~(valid&gate)]=0
 # Strong directional alignment across both horizons, including actual 60m momentum.
 fr=fc.cross_sectional_rank('ema_5_20');sr=np.zeros(f.shape,dtype=np.float32);sr[valid]=sc.cross_sectional_rank('roc_10')[ix[valid]]
 trend=.5*fr+.5*sr;order=np.sort(trend,axis=1)
 agree=(np.argmax(fr,axis=1)==np.argmax(sr,axis=1))&(np.argmin(fr,axis=1)==np.argmin(sr,axis=1))&(np.ptp(sr,axis=1)>0)
 mag=np.zeros(f.shape);mag[valid]=np.abs(sc.get('roc_10')[ix[valid]])
 # threshold uses already completed 60m return of both chosen assets.
 strength=np.minimum(mag[np.arange(len(f.timestamps)),np.argmax(trend,axis=1)],mag[np.arange(len(f.timestamps)),np.argmin(trend,axis=1)])
 allow=valid&agree&(order[:,-1]-order[:,-2]>=.2)&(order[:,1]-order[:,0]>=.2)
 trend[~allow]=0
 CACHE['x']=(f,ft,scalp,trend,strength,allow);return CACHE['x']
def evaluate(task):
 x,period,cost,delay=task;f,ft,scalp,trend,strength,allow=context();regimes=np.zeros(len(ft),dtype=np.int8);active=allow&(strength>=x['threshold'])
 onset=active&~np.r_[False,active[:-1]]
 days=pd.factorize(ft.date)[0]
 last=-10
 for pos in np.flatnonzero(onset):
  if days[pos]-last>=5:
   regimes[pos]=1;last=days[pos]
 fast=StrategySpec('scalp',(),(),1,1,2,50.,1.25,3)
 long=StrategySpec('trend',(),(),1,1,x['hold'],x['stop'],x['tp'],3)
 a,b=[int(np.searchsorted(ft.asi8,pd.Timestamp(t,tz='UTC').value)) for t in {'development':('2024-01-01','2026-01-01'),'recent':('2026-01-01','2026-11-14')}[period]]
 z=run_backtest(f,scalp,fast,CFG.execution,CFG.risk,CFG.capital,a,b,cost_multiplier=cost,signal_delay_bars=delay,regime_plan=(regimes,{0:(fast,scalp),1:(long,trend)}))
 # Route count is precomputed eligible signal bars, not executed trades.
 return {**x,'period':period,'cost':cost,'delay':delay,'trend_signal_bars':int(np.sum(regimes[a:b])),'scalp_signal_bars':int(np.sum(np.ptp(scalp[a:b],axis=1)>0)),**z.to_dict()}
if __name__=='__main__':
 grid=[]
 for threshold,stop,tp,hold in product((.005,.01,.02),(40.,80.),(2.,4.),(6,12,18)):
  x=dict(threshold=threshold,stop=stop,tp=tp,hold=hold);x['id']=hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()[:12];grid.append(x)
 (OUT/'manifest.json').write_text(json.dumps({'grid':grid,'selection':'development return >=40 rounds top10 then reused recent','limit':'intraday only, no overnight swing, 2026 previously examined'},indent=2))
 with ProcessPoolExecutor(max_workers=6) as pool:
  dev=list(pool.map(evaluate,[(x,'development',1.,0) for x in grid],chunksize=4));d=pd.DataFrame(dev).sort_values(['total_return','id'],ascending=[False,True]);d.to_csv(OUT/'development.csv',index=False)
  ids=d[d.rounds>=40].head(10).id.tolist();(OUT/'selected_ids.json').write_text(json.dumps(ids));chosen=[x for x in grid if x['id'] in ids]
  recent=list(pool.map(evaluate,[(x,'recent',c,l) for x in chosen for c,l in ((1.,0),(2.,0),(1.,1))],chunksize=2));pd.DataFrame(recent).to_csv(OUT/'recent.csv',index=False)
 print('complete',len(dev)+len(recent),flush=True)
