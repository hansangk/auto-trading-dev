"""Fresh fixed four-hour access via unchanged03partitioner; no orders/engine/PnL."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import argparse,json,csv,hashlib
from scripts.prospective_access_20261120 import collect
from scripts.prospective_quote_tail_20261120 import classify_payload
from scripts.prospective_input_audit_20261119 import _etf_index,_source_index,_prefix,timestamp
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--phase',choices=['fetch','audit'],required=True);p.add_argument('--cutoff',required=True);p.add_argument('--out',required=True);a=p.parse_args();r=Path(a.out);now=timestamp(a.cutoff)
 if a.phase=='fetch':
  if (r/'ETF_access_manifest.json').exists():raise RuntimeError('Existingfetch protected')
  with ThreadPoolExecutor(max_workers=4) as pool:out=list(pool.map(lambda s:collect(s,r,now),['TQQQ','SQQQ','IBIT','BITI']))
  meta=[m for m,_ in out]
  (r/'ETF_access_manifest.json').write_text(json.dumps(dict(sources=meta,scope='Rawacquisition only; inheritedcollector firsthourstrictstatus notqualification for4hours'),indent=2)+'\n')
  print(json.dumps(dict(HTTP200=sum(m.get('http_status')==200 for m in meta))));return
 output=r/'normalized_append_audit.json'
 if output.exists():raise RuntimeError('Existingaudit protected')
 meta=json.loads((r/'ETF_access_manifest.json').read_text())['sources'];complete=[];diagnostics=[];counts=Counter();failures=[]
 for m in meta:
  try:
   raw=Path(m['raw_path']);assert sha(raw)==m['raw_sha256']
   x=classify_payload(json.loads(raw.read_bytes()),a.cutoff);complete.extend(x['completed_rows']);diagnostics.append(dict(symbol=x['symbol'],counts=x['counts'],quarantine=x['quarantined_records']))
   counts.update(v['reason'] for v in x['quarantined_records'])
  except Exception as e:failures.append(dict(symbol=m['symbol'],error=type(e).__name__+': '+str(e)))
 if failures:
  output.write_text(json.dumps(dict(status='NORMALIZER_REJECTED_NO_CONTINUATION',failures=failures,engine_calls=0,orders=0,financial_metrics=None),indent=2)+'\n');print(json.dumps(failures));return
 idx=_etf_index(complete);expect={(s,timestamp('2026-11-19T'+t+'Z')) for s in ['TQQQ','SQQQ','IBIT','BITI'] for t in ['14:30:00','15:30:00','16:30:00','17:30:00']}
 assert set(idx)==expect
 source=json.loads((r/'Binance_connector_response_LOCAL.json').read_text())['structuredContent']['result'];src=_source_index(source,now)
 assert len(src)==24 and min(src)==timestamp('2026-11-19T06:30:00Z') and max(src)==timestamp('2026-11-19T18:00:00Z')
 comparisons={}
 for oldrun in ['prospective_access_retry_20261120_0100','prospective_append_retry_20261120_0200']:
  d=Path('runs')/oldrun;olde=_etf_index(list(csv.DictReader((d/'partial_ETF_LOCAL.csv').open())));olds=_source_index(json.loads((d/'BTCUSDT_30m_partial_LOCAL.json').read_text()),now)
  c={}
  for name,old,new in [('ETF',olde,idx),('source',olds,src)]:
   missing=sum(k not in new for k in old);changed=sum(k in new and old[k]!=new[k] for k in old)
   try:_prefix(old,new,name);ok=True
   except ValueError:ok=False
   c[name]=dict(prior_rows=len(old),missing=missing,changed=changed,unchanged=ok)
  comparisons[oldrun]=c
 with (r/'partial_ETF_LOCAL.csv').open('x',newline='') as f:
  w=csv.DictWriter(f,fieldnames=['symbol','timestamp','open','high','low','close','volume']);w.writeheader();w.writerows(complete)
 with (r/'BTCUSDT_30m_partial_LOCAL.json').open('x') as f:f.write(json.dumps(source,separators=(',',':'))+'\n')
 unchanged=all(v['unchanged'] for c in comparisons.values() for v in c.values())
 private=[*r.glob('*_raw_LOCAL.json'),r/'Binance_connector_response_LOCAL.json',r/'partial_ETF_LOCAL.csv',r/'BTCUSDT_30m_partial_LOCAL.json']
 result=dict(status='FRESH_PARTIAL_NORMALIZATION_PREFIX_PASS_NO_EXECUTION' if unchanged else 'REVISED_VINTAGE_NO_CONTINUATION',cutoff=a.cutoff,ETF_rows=len(idx),source_rows=len(src),new_unique_ETF_vs02=8,new_unique_source_vs02=4,ETF_period=['2026-11-19T14:30:00Z','2026-11-19T18:30:00Z'],source_period=['2026-11-19T06:30:00Z','2026-11-19T18:30:00Z'],quarantine_totals=dict(counts),per_symbol=diagnostics,prefix_comparisons=comparisons,private_sha256={str(p):sha(p) for p in private},classifier_sha256=sha(Path('scripts/prospective_quote_tail_20261120.py')),full_session_qualified=False,PIT_qualified=False,qualified_account_continuation=False,terminal_backtest_allowed=False,engine_calls=0,orders=0,financial_metrics=None,new_independent_validation=False,raw_public_upload='NOT_ATTEMPTED',limitation='Fresh ingestion test of unchangedclassifier, not independent financialvalidation. Laterreceipt nothistoricalavailability; metadata pattern not vendorwarranty. Fullcoverage/parity/NEW FULLAccountState/execution remainmissing.')
 output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['private_sha256','per_symbol']},indent=2))
if __name__=='__main__':main()
