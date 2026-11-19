"""Partition actual partial snapshots by frozen bar-end cutoff; never compute PnL."""
from pathlib import Path
from datetime import timedelta
import json,hashlib
from scripts.prospective_input_audit_20261119 import _etf_index,_source_index,audit_snapshot,timestamp
ROOT=Path('runs/prospective_access_retry_20261120_0100')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    out=ROOT/'session_access_audit.json'
    if out.exists():raise RuntimeError('Existing access audit protected')
    access=json.loads((ROOT/'ETF_access_manifest.json').read_text())
    source=json.loads((ROOT/'source_access_manifest.json').read_text())
    cutoff=timestamp(access['fixed_bar_end_cutoff_utc'])
    opened=timestamp('2026-11-19T14:30:00Z');closed=timestamp('2026-11-19T21:00:00Z')
    expected_starts={opened+timedelta(hours=k) for k in range(7)}
    rows=[];parts=[];rawhash={}
    for info in access['sources']:
        p=Path(info['raw_path']);assert sha(p)==info['raw_sha256'];rawhash[str(p)]=sha(p)
        x=json.loads(p.read_bytes())['chart']['result'][0]
        assert x['meta']['symbol']==info['symbol'] and x['meta']['currency']=='USD'
        assert x['meta']['exchangeTimezoneName']=='America/New_York'
        q=x['indicators']['quote'][0];times=x['timestamp']
        assert all(len(q[k])==len(times) for k in ('open','high','low','close','volume'))
        counts=dict(completed=0,incomplete=0,start_after_cutoff=0)
        for i,t in enumerate(times):
            start=timestamp('1970-01-01T00:00:00Z')+timedelta(seconds=t)
            # Predeclared no-future rule: future timestamps are excluded before bar-clock classification.
            if start>cutoff:
                counts['start_after_cutoff']+=1;continue
            if start not in expected_starts:raise ValueError('Off-clock row at/before cutoff')
            end=min(start+timedelta(hours=1),closed)
            if end>cutoff:
                counts['incomplete']+=1;continue
            row=dict(symbol=info['symbol'],timestamp=start.isoformat(),**{k:q[k][i] for k in ('open','high','low','close','volume')})
            _etf_index([row]);rows.append(row);counts['completed']+=1
        assert counts==dict(completed=1,incomplete=1,start_after_cutoff=1)
        parts.append(dict(symbol=info['symbol'],raw_rows=len(times),partition_counts=counts,
                          received_host_utc=info['received_host_utc']))
    index=_etf_index(rows)
    assert set(index)=={(s,opened) for s in ('TQQQ','SQQQ','IBIT','BITI')}
    p=ROOT/'BTCUSDT_30m_partial_LOCAL.json';rawhash[str(p)]=sha(p)
    source_rows=json.loads(p.read_bytes());source_index=_source_index(source_rows,cutoff)
    assert len(source_index)==18 and min(source_index)==opened-timedelta(hours=8)
    assert max(source_index)+timedelta(minutes=30)==opened+timedelta(hours=1)
    calendar=[dict(day='2026-11-19',open=opened.isoformat(),close=closed.isoformat())]
    # Actual partial snapshots cannot pass the existing full-session qualifier.
    try:audit_snapshot(rows,source_rows,calendar,'2026-11-19T05:20:49Z',cutoff.isoformat())
    except ValueError as error:
        full_rejection=str(error)
        assert full_rejection=='Incomplete/future ETF session refused',full_rejection
    else:raise AssertionError('Partial session unexpectedly qualified')
    result=dict(status='PARTIAL_REAL_INPUTS_OBSERVED_NOT_EXECUTABLE',fixed_bar_end_cutoff_utc=cutoff.isoformat(),
                per_symbol=sorted(parts,key=lambda x:x['symbol']),completed_ETF_rows=len(index),source_rows=len(source_index),
                ETF_period_start_utc=opened.isoformat(),ETF_period_end_exclusive_utc=(opened+timedelta(hours=1)).isoformat(),
                source_period_start_utc=min(source_index).isoformat(),source_period_end_exclusive_utc='2026-11-19T15:30:00+00:00',
                raw_local_sha256=rawhash,original_strict_collector_status_preserved=True,
                original_strict_successful_requests=access['successful_requests'],actual_HTTP200_ETF_responses=4,
                classification_note='Original collector marked post-cutoff off-clock tails as strict invalid coverage. This derived audit separates future timestamp rows before clock checks under the original no-future criterion; raw files and original manifest unchanged. No future OHLC values enter rows.',
                observation_limitation='ETF receipts occur after the fixed cutoff; source receipt only bracketed by verified clocks. These observations do not prove availability at cutoff, historical close or assumed release floors.',
                full_session_audit_attempts_this_invocation=1,prior_failed_attempts=1,prior_failure='First adapter passed datetime where the existing API requires aware string; attempt1log preserved, no newpricefetch or engine.',full_session_audits_passed=0,full_session_rejection=full_rejection,
                terminal_backtest_allowed=False,engine_calls=0,orders=0,financial_metrics=None,new_independent_validation=False,
                frozen_models_unchanged=True,first_snapshot_mode=True,raw_public_upload='NOT_ATTEMPTED',
                remaining='Authentic vendor/vintage/PIT qualification; full actual session coverage; signal parity; NEW FULL AccountState and protected execution integration')
    with out.open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('per_symbol','raw_local_sha256')},indent=2))
if __name__=='__main__':main()
