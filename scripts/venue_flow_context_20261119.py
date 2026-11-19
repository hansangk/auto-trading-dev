"""Immutable Binance reported taker-volume audit and causal exact-span joins.

Raw12-column30m API observations stay LOCAL. No interpolation or ETF price
replacement. One hour contains two actual adjacent30m bars starting at :30.
Single venue/USDT reported taker classification is not investor fund flow.
"""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from availability_runtime_20261119 import atomic_json as dump,sha

OUT=Path('runs/venue_flow_retry_20261119_1200')
BASE=Path('runs/hourly_clock_retry_20261119_0300')
ETF=BASE/'audit_v2/audited_ETF_LOCAL.csv.gz'
EXPECTED_ETF='163e532099c1465e951543680730951b7b29a6d16021ff3affe31c23fd77e3d7'

def load_prepared():
    assert sha(ETF)==EXPECTED_ETF
    data=load_market_data(ETF,['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True)
    with np.load(OUT/'context_LOCAL.npz') as f:
        ctx={k:f[k] for k in ('valid','history1','history4','history8','flow_mean4','flow_mean8')}
        for side in ('current','prior'):ctx[side]={k:f[side+'__'+k] for k in ('open','high','low','close','flow')}
    return data,times,ctx

def prepare():
    if (OUT/'context_manifest.json').exists():raise RuntimeError('Prepared context protected')
    paths=sorted(OUT.glob('BTCUSDT_30m_page_*_LOCAL.json'));assert len(paths)==36
    raw=[];hashes={str(p):sha(p) for p in paths}
    for p in paths:raw.extend(json.loads(p.read_text()))
    assert len(raw)==35040 and all(len(r)==12 for r in raw)
    a=np.asarray(raw,float);start=a[:,0].astype('int64');end=a[:,6].astype('int64')+1
    assert start[0]==pd.Timestamp('2024-11-14',tz='UTC').value//10**6
    assert end[-1]==pd.Timestamp('2026-11-14',tz='UTC').value//10**6
    assert np.all(np.diff(start)==1800000) and np.all(end-start==1800000)
    assert np.isfinite(a).all() and np.all(a[:,1:6]>0) and np.all(a[:,7:9]>0)
    assert np.all(a[:,2]>=np.max(a[:,[1,3,4]],axis=1)) and np.all(a[:,3]<=np.min(a[:,[1,2,4]],axis=1))
    assert np.all((a[:,9]>=0)&(a[:,9]<=a[:,5])) and np.all((a[:,10]>=0)&(a[:,10]<=a[:,7]))
    assert np.all(a[:,8]==np.floor(a[:,8]))
    sample=json.loads((OUT/'access_sample_LOCAL.json').read_text())
    if isinstance(sample,dict):sample=sample.get('result',sample)
    mapping={r[0]:r for r in raw};assert all(mapping[r[0]]==r for r in sample)
    bars=[]
    for i in range(1,len(raw)-1,2):
        x,y=a[i],a[i+1];assert int(x[0])%3600000==1800000 and int(y[0])==int(x[6])+1
        bars.append(dict(start=pd.Timestamp(int(x[0]),unit='ms',tz='UTC'),end=pd.Timestamp(int(y[6])+1,unit='ms',tz='UTC'),open=x[1],high=max(x[2],y[2]),low=min(x[3],y[3]),close=y[4],volume=x[5]+y[5],flow=2*(x[9]+y[9])/(x[5]+y[5])-1))
    f=pd.DataFrame(bars);ends=pd.DatetimeIndex(f.end)
    assert sha(ETF)==EXPECTED_ETF
    data=load_market_data(ETF,['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True)
    schedule=pd.read_csv(BASE/'calendar_schedule.csv',index_col='day');schedule['close']=pd.to_datetime(schedule['close'],utc=True)
    local=times.tz_convert('America/New_York');known=set(times);n=len(times)
    ctx={k:np.zeros(n,bool) for k in ('valid','history1','history4','history8')}
    ctx.update({k:np.full(n,np.nan) for k in ('flow_mean4','flow_mean8')})
    for side in ('current','prior'):ctx[side]={k:np.full(n,np.nan) for k in ('open','high','low','close','flow')}
    trace=[]
    for i,t in enumerate(times):
        day=str(local[i].date());decision=min(t+pd.Timedelta(hours=1),schedule.loc[day,'close'])
        j=int(ends.searchsorted(decision-pd.Timedelta(minutes=5),side='right')-1)
        if j<8:continue
        row=f.iloc[j];age=(decision-row.end).total_seconds()/60
        if not 5<=age<=65 or row.start not in known or row.end-row.start!=pd.Timedelta(hours=1) or str(row.start.tz_convert('America/New_York').date())!=day:continue
        ctx['valid'][i]=True
        for k in (1,4,8):ctx['history'+str(k)][i]=bool((np.diff(f.start.iloc[j-k:j+1].astype('int64'))==3600*10**9).all())
        for side,index in (('current',j),('prior',j-1)):
            for k in ctx[side]:ctx[side][k][i]=f[k].iloc[index]
        for k in (4,8):ctx['flow_mean'+str(k)][i]=f.flow.iloc[j-k:j].mean()
        trace.append(dict(index=i,decision=str(decision),source_start=str(row.start),source_end=str(row.end),available=str(row.end+pd.Timedelta(minutes=5)),age_minutes=age))
    np.savez_compressed(OUT/'context_LOCAL.npz',**{k:v for k,v in ctx.items() if not isinstance(v,dict)},**{side+'__'+k:v for side in ('current','prior') for k,v in ctx[side].items()})
    pd.DataFrame(trace).to_csv(OUT/'source_trace_LOCAL.csv',index=False)
    quality=dict(raw_rows=len(raw),first_open=str(pd.Timestamp(start[0],unit='ms',tz='UTC')),end_exclusive=str(pd.Timestamp(end[-1],unit='ms',tz='UTC')),missing=0,duplicate=0,positive_volume_fraction=1,all_OHLC_valid=True,taker_base_quote_bounds=True,sample_overlap_exact_rows=len(sample),source_hour_rows=len(f),valid_ETF_decision_rows=int(ctx['valid'].sum()),age_minutes=sorted(set(t['age_minutes'] for t in trace)),input_hashes=hashes,ETF_sha256=sha(ETF),calendar_sha256=sha(BASE/'calendar_schedule.csv'),context_sha256=sha(OUT/'context_LOCAL.npz'),source='Binance public spot BTCUSDT klines30m,12 columns,reported taker buy base volume; quoteUSDT,singlevenue',source_documentation='https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#klinecandlestick-data',release_assumption_minutes=5,raw_access='LOCAL only; previous public raw upload refusal respected',independent_validation=False,news_macro=False,orders=0)
    dump(OUT/'context_manifest.json',quality);print(json.dumps({k:v for k,v in quality.items() if k!='input_hashes'},indent=2))

if __name__=='__main__':prepare()
