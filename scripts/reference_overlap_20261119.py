"""Reproduce source-information intervention counts; no portfolio calls."""
from pathlib import Path
from dataclasses import replace
import hashlib,json
import pandas as pd
import numpy as np
from autogrid.data import load_market_data
from five_minute_grid_20261118 import signals

OUT=Path('runs/reference_retry_20261119')
def main():
    etf=OUT/'aligned_ETF_LOCAL.csv.gz';source=OUT/'references_LOCAL.csv.gz'
    assert hashlib.sha256(etf.read_bytes()).hexdigest()=='a672f4d76a6216e743270abb97fae31f421a955985fa718cd82c6c423430e99c'
    assert hashlib.sha256(source.read_bytes()).hexdigest()=='836d92f572b14bf0a622b637b7009ca6e261f09e7b567e36bec4ab206a689075'
    data=load_market_data(etf,['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True)
    f=pd.read_csv(source);f.timestamp=pd.to_datetime(f.timestamp,utc=True)
    r=np.stack([f[f.symbol==s].set_index('timestamp').loc[times,['open','high','low','close']].to_numpy() for s in ('QQQ','BTC-USD')],axis=1)
    c=dict(family='momentum',a=4,b=.5);x=signals(data,times,c)
    y=signals(replace(data,**{k:np.repeat(r[:,:,j],2,axis=1) for j,k in enumerate(('open','high','low','close'))}),times,c);out=[]
    for start,end in [('2026-09-21','2026-10-01'),('2026-10-01','2026-10-19'),('2026-10-19','2026-11-18')]:
        mask=(times>=pd.Timestamp(start,tz='UTC'))&(times<pd.Timestamp(end,tz='UTC'));a=x[mask];b=y[mask]
        out.append(dict(start=start,end_exclusive=end,ETF_role_events=int(np.count_nonzero(a)),reference_role_events=int(np.count_nonzero(b)),same_direction=int(np.count_nonzero((a==b)&(a!=0))),removed_roles=int(np.count_nonzero((a!=0)&(a!=b))),new_reference_roles=int(np.count_nonzero((b!=0)&(a!=b))),changed_clock_vectors=int(np.any(a!=b,axis=1).sum())))
    text=json.dumps(out,indent=2);path=OUT/'source_overlap.json'
    if path.exists():assert json.loads(path.read_text())==out,'Existing source overlap differs'
    else:path.write_text(text)
    print(text)
if __name__=='__main__':main()
