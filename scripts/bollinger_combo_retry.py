"""Exploratory causal beta-hedged, jointly exited multiframe research."""
from pathlib import Path
from itertools import product
from concurrent.futures import ProcessPoolExecutor
import json,hashlib
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
ROOT=Path('runs/pair_regime_retry');OUT=Path('runs/bollinger_combo_retry');OUT.mkdir(parents=True,exist_ok=True)
CACHE={}

def features(pair,minutes,lookback):
 key=(pair,minutes,lookback)
 if key in CACHE:return CACHE[key]
 fast=load_market_data(ROOT/f'{pair}_{minutes}m.csv');slow=load_market_data(ROOT/f'{pair}_60m.csv')
 ft=pd.to_datetime(fast.timestamps,utc=True);st=pd.to_datetime(slow.timestamps,utc=True)
 ret=pd.DataFrame(np.log(slow.close)).diff(); beta=ret[0].rolling(lookback).cov(ret[1])/ret[1].rolling(lookback).var()
 corr=ret[0].rolling(lookback).corr(ret[1])
 # Lag beta for each realized residual: coefficients are known before that return.
 residual=ret[0]-beta.shift(1)*ret[1]
 cumulative=residual.fillna(0).cumsum();z=(cumulative-cumulative.rolling(lookback).mean())/cumulative.rolling(lookback).std()
 mapping=np.searchsorted((st+pd.Timedelta(minutes=60)).asi8,(ft+pd.Timedelta(minutes=minutes)).asi8,side='right')-1
 def align(x):
  v=np.full(len(ft),np.nan);ok=mapping>=0;v[ok]=np.asarray(x)[mapping[ok]];return v
 b=align(beta);c=align(corr);az=align(z)
 fr=np.vstack([np.full(2,np.nan),np.diff(np.log(fast.close),axis=0)])
 mom=fr[:,0]-b*fr[:,1]
 cov=pd.read_csv(ROOT/f'{pair}_{minutes}m.csv').groupby('timestamp').coverage.min().to_numpy()
 local=ft.tz_convert('America/New_York');minute=np.asarray(local.hour*60+local.minute)
 eligible=np.isfinite(b)&(b>=.25)&(b<=4)&np.isfinite(az)&(cov>=.8)&(minute+minutes<960)
 eligible &= np.r_[False,np.diff(ft.asi8)==minutes*60*10**9]
 resfast=fr[:,0]-np.r_[np.nan,b[:-1]]*fr[:,1]
 cumulative=pd.Series(np.nan_to_num(resfast,nan=0.)).cumsum()
 band={w:((cumulative-cumulative.rolling(w).mean())/cumulative.rolling(w).std()).to_numpy() for w in (20,40)}
 x=(fast,b,c,az,mom,eligible,ft,minute,band);CACHE[key]=x;return x

def simulate(data,signal,beta,ft,minute,minutes,a,b,hold,stop,tp,cost=1.,delay=0,equal=False):
 equity=peak=1.;mdd=0.;wins=0;pnls=[];costsum=0.;longsum=shortsum=0.;last_end=a-1
 day_start=1.;day=None;daily_halts=0;loss_streak=0;cooldown=-1
 entries=np.flatnonzero(signal)+1+delay
 for i in entries:
  if i<a or i>=b or i<=last_end or i<cooldown:continue
  si=i-1-delay
  # Execute only at the scheduled next bar: no stale/overnight/gapped signals.
  if ft.asi8[i]-ft.asi8[si]!=(1+delay)*minutes*60*10**9:continue
  if ft[i].date()!=day:day=ft[i].date();day_start=equity
  if equity/day_start-1<=-.005:daily_halts+=1;continue
  if mdd>=.05:break
  h=1. if equal else beta[si]
  weights=np.array([1.,-h])*signal[si]
  # Cap both asset weights at 15%; total gross <=20%.
  weights*=min(.2/(1+h),.15/max(1,h))
  entry=data.open[i];gross=np.abs(weights).sum();entrycost=gross*2.3e-4*cost
  exit_idx=i;exitprice=data.close[i]
  for j in range(i,min(b,i+hold)):
   mark=float(np.sum(weights*(data.close[j]/entry-1)))
   marked=equity*(1+mark-entrycost);peak=max(peak,marked);mdd=max(mdd,1-marked/peak)
   # Session/time exits at bar close. Both legs close together.
   exit_idx=j;exitprice=data.close[j]
   session_end=minute[j]+minutes>=960
   if session_end or j==min(b,i+hold)-1:break
   basket=mark/gross
   risk_exit=(marked/day_start-1<=-.005) or mdd>=.05
   if basket<=-stop/10000 or basket>=stop*tp/10000 or risk_exit:
    # Close-bar exit fills at next observed open, including missing-bar gaps.
    if j+1<b:
     exit_idx=j+1;exitprice=data.open[j+1]
    break
  rr=weights*(exitprice/entry-1)
  borrow=abs(weights[weights<0].sum())*.005*(exit_idx-i+1)*minutes/(252*390)*cost
  fees=gross*4.6e-4*cost+borrow
  net=float(rr.sum()-fees);base=equity;equity*=1+net;pnls.append(net)
  longsum+=base*float(rr[weights>0].sum());shortsum+=base*float(rr[weights<0].sum());costsum+=base*fees
  peak=max(peak,equity);mdd=max(mdd,1-equity/peak);last_end=exit_idx
  loss_streak=loss_streak+1 if net<0 else 0
  if loss_streak>=4:cooldown=exit_idx+3;loss_streak=0
 arr=np.asarray(pnls);neg=arr[arr<0].sum()
 return dict(total_return=equity-1,win_rate=float(np.mean(arr>0)) if len(arr) else 0.,rounds=len(arr),max_drawdown=mdd,costs_fraction=costsum,long_pnl_fraction=longsum,short_pnl_fraction=shortsum,profit_factor=float(arr[arr>0].sum()/-neg) if neg else None)

def evaluate(task):
 c,period,cost,delay,equal=task
 data,beta,corr,z,mom,eligible,ft,minute,band=features(c['pair'],c['minutes'],c['lookback'])
 direction=np.where(z>c['threshold'],-1,np.where(z < -c['threshold'],1,0))
 if c['mode']=='continuation':direction=-direction
 bb=band[c['band_window']]
 valid=eligible&(corr>=.3)&(mom*direction>0)&(np.abs(bb)>=c['band_sigma'])&(np.sign(bb)==np.sign(z))
 direction[~valid]=0
 dates={'development':('2024-01-01','2026-01-01'),'recent':('2026-01-01','2026-11-14'),'2024':('2024-01-01','2025-01-01'),'2025':('2025-01-01','2026-01-01'),'Q1':('2026-01-01','2026-04-01'),'Q2':('2026-04-01','2026-07-01'),'Q3':('2026-07-01','2026-10-01'),'Q4_partial':('2026-10-01','2026-11-14')}
 a,b=[int(np.searchsorted(ft.asi8,pd.Timestamp(x,tz='UTC').value)) for x in dates[period]]
 result=simulate(data,direction,beta,ft,minute,c['minutes'],a,b,c['hold'],c['stop'],c['tp'],cost,delay,equal)
 return {**c,'period':period,'cost':cost,'delay':delay,'equal_weights':equal,**result}

if __name__=='__main__':
 candidates=[]
 for pair,m,w,t,mode,band_window,band_sigma,hold in product(('SPY_QQQ','GLD_SLV','IBIT_BITX'),(15,30),(20,60),(.5,1.),('reversion','continuation'),(20,40),(1.,2.),(3,6)):
  c=dict(pair=pair,minutes=m,lookback=w,threshold=t,mode=mode,band_window=band_window,band_sigma=band_sigma,stop=60.,tp=1.5,hold=hold)
  c['strategy_id']=hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest()[:12];candidates.append(c)
 (OUT/'manifest.json').write_text(json.dumps({'candidate_count':len(candidates),'candidates':candidates,'selection':'development >=100 rounds, net return descending top30; not fresh holdout','engine':'beta-joint-close-observed-next-open; time exits at close','source':'existing pair_regime_retry resampled partial IEX'},indent=2))
 with ProcessPoolExecutor(max_workers=6) as pool:
  dev=list(pool.map(evaluate,[(c,'development',1.,0,False) for c in candidates],chunksize=16))
  d=pd.DataFrame(dev).sort_values(['total_return','strategy_id'],ascending=[False,True]);d.to_csv(OUT/'development.csv',index=False)
  ids=d[d['rounds']>=100].head(30).strategy_id.tolist();(OUT/'selected_ids.json').write_text(json.dumps(ids))
  chosen=[c for c in candidates if c['strategy_id'] in ids];print('development',len(dev),'selected',len(chosen),flush=True)
  tasks=[(c,'recent',cost,delay,equal) for c in chosen for cost,delay,equal in ((1.,0,False),(2.,0,False),(0.,0,False),(1.,1,False),(1.,0,True))]
  rows=list(pool.map(evaluate,tasks,chunksize=4));pd.DataFrame(rows).to_csv(OUT/'recent.csv',index=False)
  top=next(c for c in chosen if c['strategy_id']==ids[0]);periods=('2024','2025','Q1','Q2','Q3','Q4_partial')
  checks=list(pool.map(evaluate,[(top,p,1.,0,False) for p in periods]));pd.DataFrame(checks).to_csv(OUT/'periods.csv',index=False)
 print('complete',len(dev)+len(rows)+len(checks),flush=True)
