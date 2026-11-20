"""Second-hour access/prefix research only; no engine, orders or PnL."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse,json,csv,hashlib
from scripts.prospective_access_20261120 import collect
from scripts.prospective_input_audit_20261119 import _etf_index,_source_index,_prefix,timestamp
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--phase',choices=['fetch','audit'],required=True);p.add_argument('--asof',required=True);p.add_argument('--out',required=True);a=p.parse_args();r=Path(a.out);r.mkdir(exist_ok=True);now=timestamp(a.asof)
 if a.phase=='fetch':
  if (r/'ETF_access_manifest.json').exists():raise RuntimeError('Existingfetch protected')
  with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda s:collect(s,r,now),['TQQQ','SQQQ','IBIT','BITI']))
  rows=[];meta=[]
  for m,x in results:meta.append(m);rows.extend(x)
  with (r/'partial_ETF_LOCAL.csv').open('x',newline='') as f:
   w=csv.DictWriter(f,fieldnames=['symbol','timestamp','open','high','low','close','volume']);w.writeheader();w.writerows(rows)
  (r/'ETF_access_manifest.json').write_text(json.dumps(dict(sources=meta,rows=len(rows),receipt_limitation='Observation after cutoff does not prove availability at cutoff. Parentcollector strictfirsthour status is not this twohour audit.',raw_public_upload='NOT_ATTEMPTED'),indent=2)+'\n')
  print(json.dumps(dict(ETFrows=len(rows),HTTP200=sum(m.get('http_status')==200 for m in meta))))
  return
 if (r/'append_audit.json').exists():raise RuntimeError('Existingaudit protected')
 proof=json.loads(Path('runs/prospective_access_retry_20261120_0100/prefix_snapshot_integrity.json').read_text())
 oldetf=Path(proof['trusted_prefix_ETF']['path']);oldsrc=Path(proof['trusted_prefix_source']['path'])
 assert sha(oldetf)==proof['trusted_prefix_ETF']['sha256'] and sha(oldsrc)==proof['trusted_prefix_source']['sha256']
 etf=_etf_index(list(csv.DictReader((r/'partial_ETF_LOCAL.csv').open())))
 expected={(s,timestamp(t)) for s in ['TQQQ','SQQQ','IBIT','BITI'] for t in ['2026-11-19T14:30:00Z','2026-11-19T15:30:00Z']}
 assert set(etf)==expected
 body=json.loads((r/'Binance_connector_response_LOCAL.json').read_text());rows=body['structuredContent']['result']
 with (r/'BTCUSDT_30m_partial_LOCAL.json').open('x') as f:f.write(json.dumps(rows,separators=(',',':'))+'\n')
 src=_source_index(rows,now);assert len(src)==20 and min(src)==timestamp('2026-11-19T06:30:00Z') and max(src)==timestamp('2026-11-19T16:00:00Z')
 olde=_etf_index(list(csv.DictReader(oldetf.open())));olds=_source_index(json.loads(oldsrc.read_text()),now)
 results={}
 for label,old,new in [('ETF',olde,etf),('source',olds,src)]:
  missing=[k for k in old if k not in new];changed=[k for k in old if k in new and old[k]!=new[k]]
  try:_prefix(old,new,label);ok=True;error=None
  except ValueError as e:ok=False;error=str(e)
  results[label]=dict(previous_rows=len(old),current_rows=len(new),missing_old_keys=len(missing),changed_old_values=len(changed),unchanged=ok,error=error)
 ok=all(x['unchanged'] for x in results.values())
 private=[*r.glob('*_raw_LOCAL.json'),r/'Binance_connector_response_LOCAL.json',r/'BTCUSDT_30m_partial_LOCAL.json',r/'partial_ETF_LOCAL.csv']
 result=dict(status='PARTIAL_APPEND_PREFIX_UNCHANGED' if ok else 'SEPARATE_REVISED_VINTAGE_NO_CONTINUATION',asof_bar_end_cutoff=a.asof,ETF_rows=len(etf),source_rows=len(src),ETF_end_exclusive='2026-11-19T16:30:00Z',source_start='2026-11-19T06:30:00Z',source_end_exclusive='2026-11-19T16:30:00Z',prefix_comparisons=results,new_private_hashes={str(p):sha(p) for p in private},previous_trusted_prefixes=proof,raw_public_upload='NOT_ATTEMPTED',terminal_backtest_allowed=False,engine_calls=0,orders=0,financial_metrics=None,new_independent_validation=False,full_session_qualified=False,account_state_initialized=False,limitation='Partialprice structures only. Preserve original collector tails/errors and actualreceipt. Source serializedconnector is not HTTPwirebytes. No retrospectivePIT claim; signalparity/FULLAccountState/execution integration stillmissing.')
 (r/'append_audit.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k not in ['new_private_hashes','previous_trusted_prefixes']},indent=2))
if __name__=='__main__':main()
