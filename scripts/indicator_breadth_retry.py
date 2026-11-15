"""Exploratory paired 15m/60m broad technical-indicator grid."""
import json,hashlib
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from autogrid.features import FeatureCache
from autogrid.config import load_config
from autogrid.strategy import StrategySpec
from autogrid.engine import run_backtest
BASE=Path('runs/multiframe_pilot');OUT=Path('runs/indicator_breadth_retry');OUT.mkdir(parents=True,exist_ok=True)
CFG=load_config('configs/win60_search.yaml');CACHE={}
FAST=['stoch_14','stoch_28','williams_14','stochrsi_14','macd_5_20_7','macd_8_30_9','cci_20','mfi_14','bbwidth_20','keltner_20','bb_rsi_14','bb_rsi_20','macd_volume_20','ema_3_15','ema_5_20','roc_10','roc_30','rsi_7','rsi_14','bollinger_20','bollinger_40','vwapdev_20','donchian_20','atrbreak_14','volumez_20','obv_20','cmf_20','atrpct_14','volratio_60','macro_risk']
SLOW=['stoch_14','stochrsi_14','macd_5_20_7','cci_20','mfi_14','bbwidth_20','keltner_20','bb_rsi_20','macd_volume_20','ema_3_15','roc_10','rsi_14','bollinger_20','vwapdev_20','donchian_20','atrbreak_14','volratio_60','macro_risk']

def context():
 if CACHE:return CACHE['data']
 fast=load_market_data(BASE/'market_15m.csv');slow=load_market_data(BASE/'market_60m.csv')
 assert fast.symbols==slow.symbols
 ft=pd.to_datetime(fast.timestamps,utc=True);st=pd.to_datetime(slow.timestamps,utc=True)
 mapping=np.searchsorted((st+pd.Timedelta(minutes=60)).asi8,(ft+pd.Timedelta(minutes=15)).asi8,side='right')-1
 valid=mapping>=0;local=ft.tz_convert('America/New_York');minute=np.asarray(local.hour*60+local.minute)
 valid &= minute+15<960
 fc=FeatureCache(fast);sc=FeatureCache(slow)
 for f in FAST:fc.cross_sectional_rank(f)
 for f in SLOW:sc.cross_sectional_rank(f)
 CACHE['data']=(fast,fc,sc,mapping,valid,ft);return CACHE['data']

def evaluate(t):
 spec,period,cost,delay=t
 data,fc,sc,mapping,valid,ft=context();sl=np.zeros(data.shape,dtype=np.float32);sl[valid]=sc.cross_sectional_rank(spec['slow'])[mapping[valid]]
 fr=fc.cross_sectional_rank(spec['fast']);score=spec['weight']*fr+(1-spec['weight'])*sl
 score[~valid]=0
 if spec['gate']=='agree':
  match=(np.argmax(fr,axis=1)==np.argmax(sl,axis=1))&(np.argmin(fr,axis=1)==np.argmin(sl,axis=1))&(np.ptp(sl,axis=1)>0)&(np.ptp(fr,axis=1)>0)
  score[~match]=0
 ss=StrategySpec(spec['id'],(spec['fast'],spec['slow']),(spec['weight'],1-spec['weight']),1,1,spec['hold'],spec['stop'],spec['tp'],3)
 bounds={'development':('2024-01-01','2026-01-01'),'recent':('2026-01-01','2026-11-14')}
 a,b=[int(np.searchsorted(ft.asi8,pd.Timestamp(v,tz='UTC').value)) for v in bounds[period]]
 r=run_backtest(data,score,ss,CFG.execution,CFG.risk,CFG.capital,a,b,cost,delay)
 return {**spec,'period':period,'cost':cost,'delay':delay,**r.to_dict()}
if __name__=='__main__':
 # 30x18 feature pairs; 2 weights; 2 hold periods; all seven symbols.
 cand=[]
 for f in FAST:
  for s in SLOW:
   for weight in (.5,.75):
    for hold in (3,6):
     x=dict(fast=f,slow=s,weight=weight,hold=hold,stop=100.,tp=1.5,gate='none');x['id']=hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()[:12];cand.append(x)
 (OUT/'manifest.json').write_text(json.dumps({'candidates':len(cand),'fast':FAST,'slow':SLOW,'selection':'development net-return >=100 rounds top30; exploratory reused recent','specs':cand},indent=2))
 with ProcessPoolExecutor(max_workers=6) as pool:
  dev=list(pool.map(evaluate,[(x,'development',1.,0) for x in cand],chunksize=32))
  d=pd.DataFrame(dev).sort_values(['total_return','id'],ascending=[False,True]);d.to_csv(OUT/'development.csv',index=False)
  ids=d[d['rounds']>=100].head(30).id.tolist();(OUT/'selected_ids.json').write_text(json.dumps(ids));chosen=[x for x in cand if x['id'] in ids]
  print('development',len(dev),'selected',len(chosen),flush=True)
  tasks=[(x,'recent',cost,delay) for x in chosen for cost,delay in ((1.,0),(2.,0),(1.,1))]
  recent=list(pool.map(evaluate,tasks,chunksize=3));pd.DataFrame(recent).to_csv(OUT/'recent.csv',index=False)
 print('complete',len(dev)+len(recent),flush=True)
