"""Download real inverse ETF bars without replacing earlier input snapshots."""
import gzip
import json, urllib.request, urllib.parse, hashlib
from pathlib import Path
import pandas as pd
OUT=Path('runs/inverse_etf_retry_20261116'); frames=[]; provenance=[]
for symbol in ('TQQQ','SQQQ','IBIT','BITI'):
 url='https://query2.finance.yahoo.com/v8/finance/chart/'+symbol+'?'+urllib.parse.urlencode(dict(range='2y',interval='1h',includePrePost='false',events='div,splits'))
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=60) as response: raw=response.read()
 (OUT/(symbol+'_raw.json')).write_bytes(raw)
 r=json.loads(raw)['chart']['result'][0]; q=r['indicators']['quote'][0]
 f=pd.DataFrame(dict(timestamp=pd.to_datetime(r['timestamp'],unit='s',utc=True),symbol=symbol,**{k:q[k] for k in ('open','high','low','close','volume')})).dropna()
 frames.append(f);provenance.append(dict(symbol=symbol,url=url,raw_sha256=hashlib.sha256(raw).hexdigest(),rows=len(f)))
f=pd.concat(frames);counts=f.groupby('timestamp').symbol.nunique();f=f[f.timestamp.isin(counts[counts==4].index)]
t=f.timestamp.dt.tz_convert('America/New_York');f=f[(t.dt.minute==30)&(t.dt.hour>=9)&(t.dt.hour<16)]
f=f[f.timestamp<pd.Timestamp('2026-11-14',tz='UTC')].sort_values(['timestamp','symbol']);(OUT/'market.csv.gz').write_bytes(gzip.compress(f.to_csv(index=False).encode(),mtime=0))
(OUT/'source.json').write_text(json.dumps(dict(downloaded_utc=pd.Timestamp.now(tz='UTC').isoformat(),source='Yahoo 1h actual ETF OHLCV; IBIT spot Bitcoin proxy, BITI inverse futures ETF, not identical spot hedge',files=provenance,sha256=hashlib.sha256((OUT/'market.csv.gz').read_bytes()).hexdigest(),first=str(f.timestamp.min()),last=str(f.timestamp.max())),indent=2))
print(f.groupby('symbol').timestamp.agg(['min','max','count']).to_string())
