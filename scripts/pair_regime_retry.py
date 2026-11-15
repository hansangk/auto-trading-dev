"""Recorded exploratory retry: pair-specific data, regime and edge filters.
All 2026 results are reused research data, NOT an untouched holdout.
"""
from pathlib import Path
from itertools import product
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
import json, hashlib, sys
import numpy as np
import pandas as pd
from autogrid.config import load_config
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec

OUT=Path('runs/pair_regime_retry'); OUT.mkdir(parents=True,exist_ok=True)
CFG=load_config('configs/win60_search.yaml')
CACHE={}

def prepare():
 raw=pd.concat([pd.read_csv(f'data/alpaca_iex/raw_{y}.csv') for y in (2024,2025,2026)],ignore_index=True)
 raw['timestamp']=pd.to_datetime(raw.timestamp,utc=True)
 local=raw.timestamp.dt.tz_convert('America/New_York')
 mins=local.dt.hour*60+local.dt.minute
 raw=raw[(mins>=570)&(mins<960)].copy()
 assert not raw.duplicated(['timestamp','symbol']).any()
 audit=[]
 for pair in [('SPY','QQQ'),('GLD','SLV'),('IBIT','BITX')]:
  for m in (15,30,60):
   parts=[]
   for symbol in pair:
    part=raw[raw.symbol==symbol].set_index('timestamp').resample(f'{m}min',origin='start_day',offset='30min',closed='left',label='left').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'})
    count=raw[raw.symbol==symbol].set_index('timestamp').resample(f'{m}min',origin='start_day',offset='30min').size()
    part['coverage']=count/m
    part=part.dropna();part['symbol']=symbol;parts.append(part.reset_index())
   frame=pd.concat(parts); counts=frame.groupby('timestamp').symbol.nunique();common=counts[counts==2].index
   frame=frame[frame.timestamp.isin(common)].sort_values(['timestamp','symbol'])
   path=OUT/f'{pair[0]}_{pair[1]}_{m}m.csv';frame.to_csv(path,index=False)
   audit.append({'pair':pair,'minutes':m,'common_bars':len(common),'mean_minute_coverage':float(frame.coverage.mean()),'start':str(common.min()),'end':str(common.max())})
 (OUT/'data_audit.json').write_text(json.dumps(audit,indent=2))

def signal(c):
 key=(c['pair'],c['minutes'])
 if key not in CACHE:
  p,m=key;data=load_market_data(OUT/f'{p}_{m}m.csv');slow=load_market_data(OUT/f'{p}_60m.csv')
  ft=pd.to_datetime(data.timestamps,utc=True);st=pd.to_datetime(slow.timestamps,utc=True)
  mapping=np.searchsorted((st+pd.Timedelta(minutes=60)).asi8,(ft+pd.Timedelta(minutes=m)).asi8,side='right')-1
  valid=mapping>=0
  cov=pd.read_csv(OUT/f'{p}_{m}m.csv').groupby('timestamp').coverage.min().to_numpy()
  CACHE[key]=(data,slow,ft,st,mapping,valid,cov)
 data,slow,ft,st,mapping,valid,cov=CACHE[key]
 spread=pd.Series(np.log(slow.close[:,0]/slow.close[:,1]));w=c['lookback']
 mean=spread.rolling(w).mean();std=spread.rolling(w).std();dev=(spread-mean).to_numpy()
 z=(spread-mean)/std
 efficiency=spread.diff(w).abs()/spread.diff().abs().rolling(w).sum()
 def align(a):
  b=np.full(len(ft),np.nan);b[valid]=np.asarray(a)[mapping[valid]];return b
 az=align(z);ae=align(efficiency);edge=align(np.abs(dev))*10000
 fastspread=np.log(data.close[:,0]/data.close[:,1]);change=np.r_[np.nan,np.diff(fastspread)]
 direction=np.where((az>c['threshold'])&(change<0),-1,np.where((az < -c['threshold'])&(change>0),1,0))
 # The full spread movement is a proxy, not a predicted realizable gain.
 eligible=valid & np.isfinite(az) & (cov>=.8) & (edge>=c['edge_multiple']*9.2)
 if c['efficiency_max']<1: eligible &= ae<=c['efficiency_max']
 # No overnight or gapped preceding fast bar; only signal-time observations.
 eligible &= np.r_[False,np.diff(ft.asi8)==c['minutes']*60*10**9]
 local=ft.tz_convert("America/New_York")
 eligible &= (local.hour*60+local.minute+c["minutes"])<960
 direction[~eligible]=0
 score=np.column_stack([direction,-direction]).astype(float)
 spec=StrategySpec(c['strategy_id'],(),(),1,1,c['hold'],100.,c['take_profit_multiple'],3)
 return data,score,spec,ft

def evaluate(task):
 c,period,cost,delay=task;data,score,spec,ft=signal(c)
 dates={'development':('2024-01-01','2026-01-01'),'recent':('2026-01-01','2026-11-14'),'Q1':('2026-01-01','2026-04-01'),'Q2':('2026-04-01','2026-07-01'),'Q3':('2026-07-01','2026-10-01'),'Q4_partial':('2026-10-01','2026-11-14')}
 a,b=[int(np.searchsorted(ft.asi8,pd.Timestamp(t,tz='UTC').value)) for t in dates[period]]
 execution=replace(CFG.execution,commission_bps=0,slippage_bps=0,short_borrow_bps_per_year=0) if cost==0 else CFG.execution
 r=run_backtest(data,score,spec,execution,CFG.risk,CFG.capital,a,b,cost,delay)
 return {**c,'period':period,'cost':cost,'delay':delay,**r.to_dict()}

if __name__=='__main__':
 if "--reuse-prepared" not in sys.argv: prepare()
 candidates=[]
 for pair,m,w,t,eff,edge,hold,tp in product(('SPY_QQQ','GLD_SLV','IBIT_BITX'),(15,30),(20,40),(1.,2.),(1.,.3),(0.,2.),(3,6),(.5,1.5)):
  c=dict(pair=pair,minutes=m,lookback=w,threshold=t,efficiency_max=eff,edge_multiple=edge,hold=hold,take_profit_multiple=tp)
  c['strategy_id']=hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest()[:12];candidates.append(c)
 (OUT/'manifest.json').write_text(json.dumps({'candidates':candidates,'selection':'development net return, >=100 paired rounds, top30; freeze before recent evaluation','costs_bps_per_leg_per_side':2.3,'capital':CFG.capital,'warning':'Previously viewed data; exploratory. IEX sparse prices, no quotes, equal dollar not beta neutral; no news archives.'},indent=2))
 with ProcessPoolExecutor(max_workers=6) as pool:
  dev=list(pool.map(evaluate,[(c,'development',1.,0) for c in candidates],chunksize=8))
  df=pd.DataFrame(dev).sort_values(['total_return','strategy_id'],ascending=[False,True]);df.to_csv(OUT/'development.csv',index=False)
  selected=df[df['rounds']>=100].head(30).strategy_id.tolist();chosen=[c for c in candidates if c['strategy_id'] in selected]
  (OUT/'selected_ids.json').write_text(json.dumps(selected))
  print('development complete',len(df),'selected',len(chosen),flush=True)
  tasks=[(c,'recent',cost,delay) for c in chosen for cost,delay in ((0.,0),(1.,0),(2.,0),(1.,1))]
  recent=list(pool.map(evaluate,tasks,chunksize=4));pd.DataFrame(recent).to_csv(OUT/'recent.csv',index=False)
  top=next(c for c in chosen if c['strategy_id']==selected[0])
  quarters=list(pool.map(evaluate,[(top,q,1.,0) for q in ('Q1','Q2','Q3','Q4_partial')]))
  pd.DataFrame(quarters).to_csv(OUT/'selected_quarters.csv',index=False)
 small_ids=set(df[(df.win_rate>=.6)&(df['rounds']>0)].strategy_id)
 diagnostic=[evaluate((c,'recent',cost,0)) for c in candidates if c['strategy_id'] in small_ids for cost in (1.,2.)]
 pd.DataFrame(diagnostic).to_csv(OUT/'small_sample_diagnostics.csv',index=False)
 print('complete',len(dev)+len(recent)+len(quarters)+len(diagnostic),flush=True)
