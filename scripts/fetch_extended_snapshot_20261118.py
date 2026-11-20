"""Separately versioned local-only input. Never publish raw market records."""
from pathlib import Path
import hashlib,json,urllib.request,gzip
import pandas as pd
OUT=Path('runs/extended_snapshot_20261118')
def main():
 if (OUT/'five_minute_provenance.json').exists():raise SystemExit('Snapshot already frozen')
 cutoff=pd.Timestamp.now(tz='UTC');frames=[];sources=[]
 for symbol in ('TQQQ','SQQQ','IBIT','BITI'):
  url=f'https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?range=60d&interval=5m&includePrePost=false'
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=25) as r:raw=r.read()
  with (OUT/(symbol+'_5m_LOCAL.json')).open('xb') as f:f.write(raw)
  x=json.loads(raw)['chart']['result'][0];q=x['indicators']['quote'][0]
  frame=pd.DataFrame(dict(timestamp=pd.to_datetime(x['timestamp'],unit='s',utc=True),symbol=symbol,**{k:q[k] for k in ('open','high','low','close','volume')}))
  original=len(frame);frame=frame.dropna();ny=frame.timestamp.dt.tz_convert('America/New_York');minutes=ny.dt.hour*60+ny.dt.minute
  mask=(ny.dt.weekday<5)&(minutes>=570)&(minutes<960)&(ny.dt.minute%5==0)&(ny.dt.second==0)&(frame.timestamp+pd.Timedelta(minutes=7)<=cutoff)
  frame=frame[mask];assert not frame.duplicated(['timestamp','symbol']).any();assert (frame.high>=frame[['open','close','low']].max(axis=1)).all();assert (frame.low<=frame[['open','close','high']].min(axis=1)).all();frames.append(frame)
  sources.append(dict(symbol=symbol,url=url,sha256=hashlib.sha256(raw).hexdigest(),original_rows=original,accepted_rows=len(frame),first=str(frame.timestamp.min()),last=str(frame.timestamp.max())))
 allrows=pd.concat(frames);counts=allrows.groupby('timestamp').symbol.nunique();common=allrows[allrows.timestamp.isin(counts[counts==4].index)].sort_values(['timestamp','symbol']);path=OUT/'five_minute_common_LOCAL.csv.gz';path.write_bytes(gzip.compress(common.to_csv(index=False).encode(),mtime=0))
 dates=common.timestamp.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d');byday=common.assign(day=dates).groupby('day').timestamp.nunique().to_dict()
 result=dict(cutoff_utc=str(cutoff),sources=sources,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),common_starts=int(common.timestamp.nunique()),noncommon_rows=len(allrows)-len(common),starts_by_day=byday,new_dates_after_archived_end=[d for d in byday if d>'2026-11-13'],calendar_verified=False,independent_validation=False,publication='raw local only',bar_minutes=5)
 (OUT/'five_minute_provenance.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
