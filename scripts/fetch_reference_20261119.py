"""Local-only references; align observed timestamp-started5min bars exactly."""
from pathlib import Path
import urllib.request,json,hashlib,gzip
import pandas as pd
import numpy as np
OUT=Path('runs/reference_retry_20261119')

def main():
    if (OUT/'reference_provenance.json').exists():raise SystemExit('Frozen references exist')
    cutoff=pd.Timestamp.now(tz='UTC');sources=[];frames=[]
    for symbol in ('QQQ','BTC-USD'):
        url=f'https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?range=60d&interval=5m&includePrePost=false'
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=30) as response:raw=response.read()
        with (OUT/(symbol+'_raw_LOCAL.json')).open('xb') as f:f.write(raw)
        x=json.loads(raw)['chart']['result'][0];q=x['indicators']['quote'][0]
        frame=pd.DataFrame(dict(timestamp=pd.to_datetime(x['timestamp'],unit='s',utc=True),symbol=symbol,**{k:q[k] for k in ('open','high','low','close','volume')}));nulls=int(frame.isna().any(axis=1).sum());frame=frame.dropna()
        local=frame.timestamp.dt.tz_convert('America/New_York');minute=local.dt.hour*60+local.dt.minute
        eligible=(local.dt.weekday<5)&(minute>=570)&(minute<960)&(local.dt.minute%5==0)&(local.dt.second==0)&(frame.timestamp+pd.Timedelta(minutes=7)<=cutoff)
        frame=frame[eligible];assert not frame.duplicated('timestamp').any()
        assert np.isfinite(frame[['open','high','low','close','volume']]).all().all()
        assert (frame[['open','high','low','close']]>0).all().all();assert (frame.volume>=0).all()
        assert (frame.high>=frame[['open','close','low']].max(axis=1)).all();assert (frame.low<=frame[['open','close','high']].min(axis=1)).all()
        frames.append(frame);sources.append(dict(symbol=symbol,url=url,sha256=hashlib.sha256(raw).hexdigest(),null_rows=nulls,accepted=len(frame),first=str(frame.timestamp.min()),last=str(frame.timestamp.max()),vendor_timezone=x.get('meta',{}).get('exchangeTimezoneName')))
    frame=pd.concat(frames).sort_values(['timestamp','symbol']);path=OUT/'references_LOCAL.csv.gz';path.write_bytes(gzip.compress(frame.to_csv(index=False).encode(),mtime=0))
    etf=pd.read_csv('runs/extended_snapshot_20261118/refreshed_all_LOCAL.csv.gz');etf['timestamp']=pd.to_datetime(etf.timestamp,utc=True);dates=etf.timestamp.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d');eligible_dates=[];missing=[]
    for day,g in etf.assign(day=dates).groupby('day'):
        stamps=set(g.timestamp)
        counts={s:len(stamps-set(frame[frame.symbol==s].timestamp)) for s in ('QQQ','BTC-USD')}
        if not any(counts.values()):eligible_dates.append(day)
        else:missing.append(dict(day=day,missing=counts))
    result=dict(cutoff_utc=str(cutoff),sources=sources,input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),aligned_complete_etf_dates=eligible_dates,missing_by_day=missing,calendar_verified=False,independent_validation=False,raw_upload='Not attempted')
    (OUT/'reference_provenance.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
