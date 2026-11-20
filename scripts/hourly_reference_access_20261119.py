"""Access/clock inventory only; no hourly signals or validation claims."""
from pathlib import Path
import urllib.request,urllib.error,json,hashlib
import numpy as np
import pandas as pd
OUT=Path('runs/source_lead_audit_20261119_0200/hourly_access')

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'access_manifest.json').exists():raise SystemExit('Completed access inventory protected')
    result=[];cutoff=pd.Timestamp.now(tz='UTC')
    for symbol in ('QQQ','BTC-USD'):
        url=f'https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?range=2y&interval=1h&includePrePost=false'
        path=OUT/(symbol+'_raw_LOCAL.json')
        if path.exists():raise RuntimeError('Existingraw protected; inspect checkpoint, do not silently refetch')
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=30) as response:raw=response.read()
            with path.open('xb') as f:f.write(raw)
            body=json.loads(raw);x=body['chart']['result'][0];times=pd.to_datetime(x['timestamp'],unit='s',utc=True);q=x['indicators']['quote'][0]
            frame=pd.DataFrame({k:q[k] for k in ('open','high','low','close','volume')});finite=np.isfinite(frame.to_numpy(dtype=float)).all(axis=1)
            completed=np.asarray(times+pd.Timedelta(minutes=62)<=cutoff)&finite
            eligible=times[completed];minute=eligible.minute
            result.append(dict(symbol=symbol,status='DOWNLOADED_ACCESS_ONLY',url=url,raw_sha256=hashlib.sha256(raw).hexdigest(),fetched_utc=str(cutoff),raw_rows=len(times),null_rows=int((~finite).sum()),conservative_62min_aged_rows=int(completed.sum()),first=str(eligible.min()),last=str(eligible.max()),UTC_start_minute_histogram={str(k):int(v) for k,v in pd.Series(minute).value_counts().items()},vendor_timezone=x.get('meta',{}).get('exchangeTimezoneName'),raw_upload='Notattempted',execution_or_feature_use=False))
        except (urllib.error.URLError,ValueError,KeyError,TypeError,IndexError) as error:
            result.append(dict(symbol=symbol,status='ACCESS_FAILED',url=url,error=str(error),raw_upload='Notattempted',execution_or_feature_use=False))
        # Persist each successful or failed acquisition before moving to the next.
        (OUT/'access_checkpoint.json').write_text(json.dumps(result,indent=2))
    manifest=dict(status='ACCESS_AUDIT_ONLY',sources=result,independent_validation=False,hourly_backtests=0,clock_alignment_verified=False,next='Audit30minphase difference,barcompletion/sessioncutoffs,vintages andfrozenETFoverlap beforefeatures. Neverasof-fillpricebars orpretendexactclockmatch.')
    (OUT/'access_manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))
if __name__=='__main__':main()
