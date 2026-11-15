"""Anchored candidate refinement; all reported recent data are already viewed."""
from pathlib import Path
from itertools import product
from concurrent.futures import ProcessPoolExecutor
import hashlib,json
import numpy as np,pandas as pd
from autogrid.data import load_market_data
from autogrid.features import FeatureCache
from autogrid.config import load_config
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec
OUT=Path('runs/asymmetric_payoff_retry');OUT.mkdir(parents=True,exist_ok=True);ROOT=Path('runs/multiframe_pilot');CFG=load_config('configs/win60_search.yaml');CACHE={}
def context():
 if CACHE:return CACHE['x']
 f=load_market_data(ROOT/'market_15m.csv');s=load_market_data(ROOT/'market_60m.csv');ft=pd.to_datetime(f.timestamps,utc=True);st=pd.to_datetime(s.timestamps,utc=True)
 mapping=np.searchsorted((st+pd.Timedelta(minutes=60)).asi8,(ft+pd.Timedelta(minutes=15)).asi8,side='right')-1;valid=mapping>=0
 local=ft.tz_convert('America/New_York');mins=np.asarray(local.hour*60+local.minute);valid &= ((mins>=600)&(mins<690))|((mins>=840)&(mins<930))
 fc=FeatureCache(f);sc=FeatureCache(s);CACHE['x']=(f,fc,sc,ft,mapping,valid);return CACHE['x']
def eval_one(task):
 x,period,cost,delay=task;f,fc,sc,ft,mapping,valid=context();a=fc.cross_sectional_rank('ema_3_15');b=np.zeros(f.shape,dtype=np.float32);b[valid]=sc.cross_sectional_rank('stochrsi_14')[mapping[valid]]
 score=.75*a+.25*b;v=np.sort(score,axis=1)
 agreement=(np.argmax(a,axis=1)==np.argmax(b,axis=1))&(np.argmin(a,axis=1)==np.argmin(b,axis=1))&(np.ptp(a,axis=1)>0)&(np.ptp(b,axis=1)>0)
 gap=((v[:,-1]-v[:,-2])>=x['gap'])&((v[:,1]-v[:,0])>=x['gap'])
 cc=fc.cross_sectional_rank(x['confirm']);li=np.argmax(score,axis=1);si=np.argmin(score,axis=1)
 confirm=(cc[np.arange(len(cc)),li]>0)&(cc[np.arange(len(cc)),si]<0)
 score[~(valid&agreement&gap&confirm)]=0
 ss=StrategySpec(x['id'],('ema_3_15','stochrsi_14','confirm'),(.75,.25),1,1,x['hold'],x['stop'],x['tp'],3)
 bounds={'development':('2024-01-01','2026-01-01'),'2024':('2024-01-01','2025-01-01'),'2025':('2025-01-01','2026-01-01'),'recent':('2026-01-01','2026-11-14'),'Q1':('2026-01-01','2026-04-01'),'Q2':('2026-04-01','2026-07-01'),'Q3':('2026-07-01','2026-10-01'),'Q4_partial':('2026-10-01','2026-11-14')}
 start,end=[int(np.searchsorted(ft.asi8,pd.Timestamp(t,tz='UTC').value)) for t in bounds[period]]
 r=run_backtest(f,score,ss,CFG.execution,CFG.risk,CFG.capital,start,end,cost,delay)
 return {**x,'period':period,'cost':cost,'delay':delay,**r.to_dict()}
if __name__=='__main__':
 cand=[]
 for confirm,gap,stop,tp,hold in product(('rsi_14','roc_10'),(.2,.4),(20.,40.),(2.,4.,6.),(6,12)):
  x=dict(confirm=confirm,gap=gap,stop=stop,tp=tp,hold=hold);x['id']=hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()[:12];cand.append(x)
 anchor=next(x for x in cand if x['confirm']=='rsi_14' and x['gap']==.2 and x['stop']==40 and x['tp']==4 and x['hold']==12)
 (OUT/'manifest.json').write_text(json.dumps({'count':len(cand),'anchor':anchor,'selection':'2024-25 development >=20 rounds top10; all 2026 reused exploratory','candidates':cand},indent=2))
 with ProcessPoolExecutor(max_workers=6) as pool:
  dev=list(pool.map(eval_one,[(x,'development',1.,0) for x in cand],chunksize=8));df=pd.DataFrame(dev).sort_values(['total_return','id'],ascending=[False,True]);df.to_csv(OUT/'development.csv',index=False)
  ids=df[df.rounds>=20].head(10).id.tolist();(OUT/'selected_ids.json').write_text(json.dumps(ids));selected=[x for x in cand if x['id'] in ids];selected.append(anchor) if anchor['id'] not in ids else None
  print('development',len(cand),'selected',len(selected),flush=True)
  tasks=[(x,'recent',cost,delay) for x in selected for cost,delay in ((1.,0),(2.,0),(1.,1))]
  res=list(pool.map(eval_one,tasks,chunksize=3));pd.DataFrame(res).to_csv(OUT/'recent.csv',index=False)
  periods=list(pool.map(eval_one,[(anchor,p,1.,0) for p in ('2024','2025','Q1','Q2','Q3','Q4_partial')]))
  pd.DataFrame(periods).to_csv(OUT/'anchor_periods.csv',index=False)
 print('complete',len(dev)+len(res)+len(periods),flush=True)
