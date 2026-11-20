"""Access-only snapshots: no orders, signals, engine or PnL. Raw files stay LOCAL."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
from concurrent.futures import ThreadPoolExecutor,as_completed
import urllib.request,urllib.error,urllib.parse
import argparse,json,hashlib,csv
from scripts.prospective_input_audit_20261119 import _etf_index,timestamp
UTC=timezone.utc
SYMBOLS=('TQQQ','SQQQ','IBIT','BITI')
def clock():return datetime.now(UTC).isoformat()
def sha(b):return hashlib.sha256(b).hexdigest()
def collect(symbol,root,asof):
    opened=timestamp('2026-11-19T14:30:00Z')
    query=urllib.parse.urlencode(dict(period1=int(opened.timestamp()),period2=int(asof.timestamp()),interval='1h',includePrePost='false'))
    url='https://query2.finance.yahoo.com/v8/finance/chart/'+symbol+'?'+query
    meta=dict(symbol=symbol,url=url,request_started_host_utc=clock(),raw_public_upload='NOT_ATTEMPTED',execution_or_feature_use=False)
    path=root/(symbol+'_raw_LOCAL.json')
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=15) as response:
            raw=response.read();meta.update(http_status=response.status,received_host_utc=clock())
        with path.open('xb') as f:f.write(raw)
        meta.update(raw_path=str(path),raw_sha256=sha(raw),raw_bytes=len(raw))
        body=json.loads(raw);x=body['chart']['result'][0];v=x.get('meta',{})
        meta['vendor_metadata']={k:v.get(k) for k in ('symbol','currency','instrumentType','exchangeTimezoneName','exchangeName','dataGranularity')}
        if v.get('symbol')!=symbol or v.get('exchangeTimezoneName')!='America/New_York' or v.get('currency')!='USD':
            raise ValueError('Vendor symbol/timezone/currency mismatch')
        times=x.get('timestamp',[]);quotes=x['indicators']['quote'][0]
        if any(len(quotes[k])!=len(times) for k in ('open','high','low','close','volume')):raise ValueError('Quote-array lengths mismatch')
        rows=[];rejected=[];incomplete=0
        for i,sec in enumerate(times):
            start=datetime.fromtimestamp(sec,UTC)
            if start<opened or start>=timestamp('2026-11-19T21:00:00Z'):
                rejected.append(dict(reason='OFF_SESSION',timestamp=start.isoformat()));continue
            if start not in {opened+timedelta(hours=k) for k in range(7)}:
                rejected.append(dict(reason='OFF_CLOCK',timestamp=start.isoformat()));continue
            end=min(start+timedelta(hours=1),timestamp('2026-11-19T21:00:00Z'))
            if end>asof:incomplete+=1;continue
            row=dict(symbol=symbol,timestamp=start.isoformat(),**{k:quotes[k][i] for k in ('open','high','low','close','volume')})
            try:_etf_index([row])
            except (ValueError,TypeError,KeyError) as e:
                rejected.append(dict(reason='INVALID_OHLCV',timestamp=start.isoformat(),error=str(e)));continue
            rows.append(row)
        index=_etf_index(rows)
        exact=set(index)=={(symbol,opened)}
        meta.update(status='COMPLETED_FIRST_HOUR_ACCESS_ONLY' if exact and not rejected else 'INCOMPLETE_OR_INVALID_COVERAGE',raw_rows=len(times),incomplete_rows_excluded=incomplete,rejected_rows=rejected,completed_rows=len(rows),completed_starts_utc=[r['timestamp'] for r in rows],fixed_bar_end_cutoff_utc=asof.isoformat(),historical_release_or_asof_availability_proven=False)
        return meta,rows
    except urllib.error.HTTPError as e:
        errorraw=e.read()
        errorpath=root/(symbol+'_http_error_LOCAL.bin')
        with errorpath.open('xb') as f:f.write(errorraw)
        meta.update(status='ACCESS_FAILED',http_status=e.code,error=str(e),error_response_sha256=sha(errorraw),error_response_bytes=len(errorraw),error_response_path=str(errorpath),received_host_utc=clock())
    except Exception as e:
        meta.update(status='ACCESS_FAILED',error=type(e).__name__+': '+str(e),received_host_utc=clock())
    return meta,[]
def main():
    p=argparse.ArgumentParser();p.add_argument('--asof',required=True);p.add_argument('--out-dir',required=True);a=p.parse_args()
    root=Path(a.out_dir);root.mkdir(parents=True,exist_ok=True);asof=timestamp(a.asof)
    if (root/'ETF_access_manifest.json').exists() or any(root.glob('*_raw_LOCAL.json')) or any(root.glob('*_http_error_LOCAL.bin')):raise RuntimeError('Existing acquisition protected')
    manifest=dict(status='ACCESS_ONLY_NO_ENGINE',fixed_bar_end_cutoff_utc=asof.isoformat(),collector_started_host_utc=clock(),sources=[],engine_calls=0,orders=0,financial_metrics=None,new_independent_validation=False,raw_public_upload='NOT_ATTEMPTED',receipt_limitation='Later first observation does not prove availability at the fixed bar-end cutoff, historical close or assumed release floor.')
    allrows=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs=[pool.submit(collect,s,root,asof) for s in SYMBOLS]
        for future in as_completed(jobs):
            meta,rows=future.result();manifest['sources'].append(meta);allrows.extend(rows)
            (root/'ETF_access_checkpoint.json').write_text(json.dumps(manifest,indent=2)+'\n')
    manifest['sources'].sort(key=lambda x:x['symbol']);manifest['collector_finished_host_utc']=clock()
    manifest['successful_requests']=sum(x['status']=='COMPLETED_FIRST_HOUR_ACCESS_ONLY' for x in manifest['sources'])
    manifest['completed_etf_rows']=len(allrows);manifest['all_four_first_hour_rows_exact']=manifest['successful_requests']==4
    if allrows:
        path=root/'partial_ETF_LOCAL.csv'
        with path.open('x',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=['symbol','timestamp','open','high','low','close','volume']);writer.writeheader();writer.writerows(sorted(allrows,key=lambda x:(x['timestamp'],x['symbol'])))
        manifest['normalized_local_csv_sha256']=sha(path.read_bytes())
    (root/'ETF_access_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({k:v for k,v in manifest.items() if k!='sources'},indent=2))
    print(json.dumps([{k:x.get(k) for k in ('symbol','status','http_status','completed_rows','error','raw_sha256')} for x in manifest['sources']],indent=2))
if __name__=='__main__':main()
