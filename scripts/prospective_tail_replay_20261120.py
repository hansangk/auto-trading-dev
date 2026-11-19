"""Replay immutable access payloads through strict quote quarantine; no new prices."""
from pathlib import Path
from collections import Counter
import json,csv,hashlib
from scripts.prospective_quote_tail_20261120 import classify_payload
from scripts.prospective_input_audit_20261119 import _etf_index
ROOT=Path('runs/prospective_tail_diagnosis_20261120_0300')
def main():
 out=ROOT/'actual_replay.json'
 if out.exists():raise RuntimeError('Existing replay protected')
 totals=Counter();versions=[];hashes={}
 for run,cutoff,n in [('prospective_access_retry_20261120_0100','2026-11-19T16:04:22Z',4),('prospective_append_retry_20261120_0200','2026-11-19T17:07:25Z',8)]:
  r=Path('runs')/run;completed=[];records=[]
  for p in sorted(r.glob('*_raw_LOCAL.json')):
   raw=p.read_bytes();hashes[str(p)]=hashlib.sha256(raw).hexdigest()
   result=classify_payload(json.loads(raw),cutoff)
   completed.extend(result['completed_rows'])
   records.append(dict(symbol=result['symbol'],counts=result['counts'],quarantined_records=result['quarantined_records']))
   totals.update(x['reason'] for x in result['quarantined_records'])
   assert result['terminal_backtest_allowed'] is False
  prior=_etf_index(list(csv.DictReader((r/'partial_ETF_LOCAL.csv').open())))
  assert _etf_index(completed)==prior and len(completed)==n
  versions.append(dict(run_id=run,cutoff=cutoff,completed_rows=n,completed_values_equal_original_csv=True,per_symbol=records))
 assert totals['METADATA_MATCHED_ZERO_VOLUME_LIVE_TAIL']==1
 assert totals['FUTURE_TIMESTAMP']==7 and totals['INCOMPLETE_REGULAR_BAR']==8
 result=dict(status='STRICT_LIVE_TAIL_DIAGNOSIS_VERIFIED_ON_SAME_PAYLOADS',versions=versions,source_raw_sha256=hashes,quarantine_totals=dict(totals),versioned_completed_rows=12,unique_completed_ETF_rows=8,new_price_requests=0,bar_price_modifications=0,timestamp_shifts=0,merges=0,original02_gate_preserved=True,qualified_input_continuation_allowed=False,full_session_qualified=False,terminal_backtest_allowed=False,account_state_initialized=False,engine_calls=0,orders=0,financial_metrics=None,new_independent_validation=False,limitation='Known narrow incomplete livequote pattern inferred from actualmetadata, not vendorwarranty. Oldraw/gates unchanged. Unknownoffclock rejects. Postclose/fullPIT/signalparity/FULLAccountState/execution remain separate.')
 with out.open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k not in ['versions','source_raw_sha256']},indent=2))
if __name__=='__main__':main()
