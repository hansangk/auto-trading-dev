"""Selective short-hold technical combo, exploratory only."""
import json,hashlib
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np,pandas as pd
from autogrid.data import load_market_data
from autogrid.features import FeatureCache
from autogrid.config import load_config
from autogrid.strategy import StrategySpec
from autogrid.engine import run_backtest
BASE=Path('runs/multiframe_pilot');OLD=Path('runs/indicator_breadth_retry');OUT=Path('runs/stacked_confirm_retry');OUT.mkdir(parents=True,exist_ok=True);CFG=load_config('configs/win60_search.yaml');CACHE={}
def context():
 if CACHE:return CACHE['x']
 data=load_market_data(BASE/'market_15m.csv');slow=load_market_data(BASE/'market_60m.csv');ft=pd.to_datetime(data.timestamps,utc=True);st=pd.to_datetime(slow.timestamps,utc=True)
 ix=np.searchsorted((st+pd.Timedelta(minutes=60)).asi8,(ft+pd.Timedelta(minutes=15)).asi8,side='right')-1;ok=ix>=0
 local=ft.tz_convert('America/New_York');mins=np.asarray(local.hour*60+local.minute)
 # Pre-specified liquid regular session windows, no last-bar entries.
 window=((mins>=600)&(mins<690))|((mins>=840)&(mins<930));ok &=window
 CACHE['x']=(data,FeatureCache(data),FeatureCache(slow),ft,ix,ok,mins);return CACHE['x']
def evaluate(task):
 x,period,cost,delay=task;data,fc,sc,ft,ix,valid,mins=context()
 fast=fc.cross_sectional_rank(x['fast']);slow=np.zeros(data.shape,dtype=np.float32);slow[valid]=sc.cross_sectional_rank(x['slow'])[ix[valid]]
 score=x['weight']*fast+(1-x['weight'])*slow;ordered=np.sort(score,axis=1)
 agreement=(np.argmax(fast,axis=1)==np.argmax(slow,axis=1))&(np.argmin(fast,axis=1)==np.argmin(slow,axis=1))&(np.ptp(fast,axis=1)>0)&(np.ptp(slow,axis=1)>0)
 spread=((ordered[:,-1]-ordered[:,-2])>=.2)&((ordered[:,1]-ordered[:,0])>=.2)
 confirm=fc.cross_sectional_rank(x['confirm'])
 ci=np.argmax(score,axis=1);cj=np.argmin(score,axis=1)
 gate=agreement&spread&(np.take_along_axis(confirm,ci[:,None],axis=1)[:,0]>0)&(np.take_along_axis(confirm,cj[:,None],axis=1)[:,0]<0)
 score[~(valid&gate)]=0
 spec=StrategySpec(x['id'],(x['fast'],x['slow']),(x['weight'],1-x['weight']),1,1,x['hold'],x['stop'],x['tp'],3)
 a,b=[int(np.searchsorted(ft.asi8,pd.Timestamp(t,tz='UTC').value)) for t in ({'development':('2024-01-01','2026-01-01'),'recent':('2026-01-01','2026-11-14')}[period])]
 r=run_backtest(data,score,spec,CFG.execution,CFG.risk,CFG.capital,a,b,cost,delay)
 return {**x,'period':period,'cost':cost,'delay':delay,**r.to_dict()}
if __name__=='__main__':
 prev=pd.read_csv(OLD/'development.csv').head(30);candidates=[]
 for _,row in prev.iterrows():
  for confirm in ('stoch_14','rsi_14'):
   for stop in (20.,40.):
    for tp in (.5,1.):
     for hold in (1,2):
      x={k:row[k] for k in ('fast','slow','weight')}
      x.update(gate='stacked',confirm=confirm,stop=stop,tp=tp,hold=hold)
      x['id']=hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()[:12]
      candidates.append(x)
 (OUT/'manifest.json').write_text(json.dumps({'candidates':len(candidates),'selection':'development return >=30 rounds, top30; reused non-independent 2026','windows_NY_minutes':'10:00–11:30 and 14:00–15:30','candidates_spec':candidates},indent=2))
 with ProcessPoolExecutor(max_workers=6) as p:
  dev=list(p.map(evaluate,[(x,'development',1.,0) for x in candidates],chunksize=8));d=pd.DataFrame(dev).sort_values(['total_return','id'],ascending=[False,True]);d.to_csv(OUT/'development.csv',index=False)
  ids=d[d['rounds']>=30].head(30).id.tolist();(OUT/'selected_ids.json').write_text(json.dumps(ids));chosen=[x for x in candidates if x['id'] in ids]
  print('development',len(dev),'selected',len(chosen),flush=True)
  recent=list(p.map(evaluate,[(x,'recent',cost,delay) for x in chosen for cost,delay in ((1.,0),(2.,0),(1.,1))],chunksize=3));pd.DataFrame(recent).to_csv(OUT/'recent.csv',index=False)
 print('complete',len(dev)+len(recent),flush=True)
