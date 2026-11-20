"""Observe actualpostclose payloads with unchanged classifier; no PnL/orders."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse,json,csv,hashlib
from scripts.prospective_access_20261120 import collect
from scripts.prospective_quote_tail_20261120 import classify_payload
from scripts.prospective_input_audit_20261119 import _etf_index,_source_index,_prefix,timestamp,audit_snapshot
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--phase',choices=['fetch','audit'],required=True);p.add_argument('--cutoff',required=True);p.add_argument('--out',required=True);a=p.parse_args();r=Path(a.out);now=timestamp(a.cutoff)
 if a.phase=='fetch':
  if (r/'ETF_access_manifest.json').exists():raise RuntimeError('Existingfetch protected')
  with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda s:collect(s,r,now),['TQQQ','SQQQ','IBIT','BITI']))
  meta=[m for m,_ in results];rows=[x for _,xs in results for x in xs]
  with (r/'regular_candidates_ETF_LOCAL.csv').open('x',newline='') as f:
   w=csv.DictWriter(f,fieldnames=['symbol','timestamp','open','high','low','close','volume']);w.writeheader();w.writerows(rows)
  (r/'ETF_access_manifest.json').write_text(json.dumps(dict(sources=meta,candidate_rows=len(rows),candidate_rows_are_not_wholepayload_qualification=True),indent=2)+'\n')
  print(json.dumps(dict(HTTP200=sum(m.get('http_status')==200 for m in meta),candidate_rows=len(rows))));return
 out=r/'postclose_audit.json'
 if out.exists():raise RuntimeError('Existingaudit protected')
 meta=json.loads((r/'ETF_access_manifest.json').read_text())['sources'];candidate=list(csv.DictReader((r/'regular_candidates_ETF_LOCAL.csv').open()));idx=_etf_index(candidate)
 expect={(s,timestamp('2026-11-19T'+t+'Z')) for s in ['TQQQ','SQQQ','IBIT','BITI'] for t in ['14:30:00','15:30:00','16:30:00','17:30:00','18:30:00','19:30:00','20:30:00']}
 coverage=set(idx)==expect;gate=[];classified=[]
 for m in meta:
  p=Path(m['raw_path']);assert sha(p)==m['raw_sha256'];payload=json.loads(p.read_bytes());x=payload['chart']['result'][0];q=x['indicators']['quote'][0]
  fact=dict(symbol=m['symbol'],raw_rows=len(x['timestamp']),last_epoch=x['timestamp'][-1],meta_market_time=x['meta'].get('regularMarketTime'),tail_volume=q['volume'][-1],tail_OHLC_equal=len({q[k][-1] for k in ['open','high','low','close']})==1)
  try:
   result=classify_payload(payload,a.cutoff);classified.extend(result['completed_rows']);fact.update(classifier_passed=True,completed_rows=len(result['completed_rows']),quarantines=result['quarantined_records'])
  except ValueError as e:fact.update(classifier_passed=False,error=str(e))
  gate.append(fact)
 body=json.loads((r/'Binance_connector_response_LOCAL.json').read_text());rows=body['structuredContent']['result']
 with (r/'BTCUSDT_30m_LOCAL.json').open('x') as f:f.write(json.dumps(rows,separators=(',',':'))+'\n')
 src=_source_index(rows,now);fullsource=len(src)==29 and max(src)==timestamp('2026-11-19T20:30:00Z')
 assert len(src) in (28,29) and min(src)==timestamp('2026-11-19T06:30:00Z')
 comparisons={}
 for oldrun,ep,sp in [('prospective_access_retry_20261120_0100','partial_ETF_LOCAL.csv','BTCUSDT_30m_partial_LOCAL.json'),('prospective_five_hour_append_20261120_0500','partial_ETF_LOCAL.csv','BTCUSDT_30m_partial_LOCAL.json')]:
  old=Path('runs')/oldrun;c={}
  for name,prior,new in [('ETF',_etf_index(list(csv.DictReader((old/ep).open()))),idx),('source',_source_index(json.loads((old/sp).read_text()),now),src)]:
   c[name]=dict(prior_rows=len(prior),missing=sum(k not in new for k in prior),changed=sum(k in new and prior[k]!=new[k] for k in prior))
  comparisons[oldrun]=c
 rawpass=all(x['classifier_passed'] for x in gate)
 fullpassed=False;fullerror=None
 if rawpass and coverage and fullsource:
  try:
   audit_snapshot(classified,rows,[dict(day='2026-11-19',open='2026-11-19T14:30:00Z',close='2026-11-19T21:00:00Z')],'2026-11-19T05:20:49Z',a.cutoff)
   fullpassed=True
  except ValueError as e:fullerror=str(e)
 private=[*r.glob('*_raw_LOCAL.json'),r/'Binance_connector_response_LOCAL.json',r/'regular_candidates_ETF_LOCAL.csv',r/'BTCUSDT_30m_LOCAL.json']
 result=dict(status='POSTCLOSE_RAW_GATE_REJECTED_NO_EXECUTION' if not rawpass else 'POSTCLOSE_STRUCTURAL_CHECK_ONLY_NO_EXECUTION',cutoff=a.cutoff,regular_ETF_candidate_rows=len(idx),regular_ETF_exact28_coverage=coverage,actual_source_rows=len(src),source_full29=fullsource,raw_classifier_all_passed=rawpass,per_symbol=gate,prefix_comparisons=comparisons,full_structural_audit_passed=fullpassed,full_structural_error=fullerror,full_qualifier_skipped_for_raw_rejection=not rawpass,private_sha256={str(p):sha(p) for p in private},PIT_qualified=False,AccountState_initialized=False,qualified_account_continuation=False,terminal_backtest_allowed=False,engine_calls=0,orders=0,financial_metrics=None,new_independent_validation=False,raw_public_upload='NOT_ATTEMPTED',limitation='Regularcandidatecoverage is not rawgate/PIT/accountpermission; unknownpostclosetails notdeleted/shifted. Futurepolicy needs actual evidence, frozen03unchanged.')
 out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='private_sha256'},indent=2))
if __name__=='__main__':main()
