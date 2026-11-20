"""Replay immutable actual06 snapshots through a separately preregistered policy.
No acquisition, strategy selection, account initialization, engine or orders.
Run from repository root: PYTHONPATH=src:. python scripts/prospective_postclose_replay_20261120.py
Existing output is protected; never overwrite a completed checkpoint.
"""
import csv
import hashlib
import io
import json
from pathlib import Path
from scripts.prospective_input_audit_20261119 import audit_snapshot, _etf_index, _source_index, _prefix, timestamp
from scripts.prospective_shadow_guard_20261119 import validate_plan
from scripts.prospective_postclose_partition_20261120 import classify_postclose
from scripts.prospective_quote_tail_20261120 import classify_payload

ROOT = Path('runs/prospective_close_policy_20261120_0700')
OLD = Path('runs/prospective_postclose_access_20261120_0600')
PLAN = Path('runs/venue_latency_retry_20261119_1400/prospective_shadow_plan.json')
MANIFEST_SHA = '03d7fb7d2336f07016fec67187a026810ef0aa6dd7ca7046cb4b7b738364f920'
CUTOFF = '2026-11-19T21:04:07Z'
ASOF = '2026-11-19T21:05:51Z'
SYMBOLS = ('TQQQ', 'SQQQ', 'IBIT', 'BITI')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def rows(path):
    return list(csv.DictReader(Path(path).read_text().splitlines()))

def main():
    for name in ('actual_replay.json', 'normalized_ETF_LOCAL.csv'):
        if (ROOT/name).exists():
            raise RuntimeError('Existing checkpoint protected: '+name)
    manifest_path = OLD/'analysis_manifest.json'
    if sha(manifest_path) != MANIFEST_SHA:
        raise ValueError('Pinned06manifest mismatch')
    m = json.loads(manifest_path.read_text())
    verified = {}
    for key in ('artifact_sha256','original_data_hashes','private01hashes','private02hashes','private04hashes','private05hashes','private06hashes','frozen17_dependency_sha256'):
        for name, want in m[key].items():
            if sha(name) != want:
                raise ValueError('Immutable hash mismatch: '+name)
            verified[name] = want
    frozen = Path('scripts/prospective_quote_tail_20261120.py')
    if sha(frozen) != '133c2c642725f13dea1aef968226668af69a4b84e83f73cf552587d8302d44b9':
        raise ValueError('Frozen03classifier changed')
    pbytes = PLAN.read_bytes()
    blob = hashlib.sha1(b'blob '+str(len(pbytes)).encode()+b'\0'+pbytes).hexdigest()
    if blob != '3595a3d7fc07401252a205f615f5fd743e77ab49':
        raise ValueError('FrozenplanGitblob mismatch')
    plan = json.loads(pbytes)
    validate_plan(plan)
    if len(plan['code_dependency_hashes']) != 17:
        raise ValueError('Frozen17dependency count')
    completed, per_symbol, original03_replay = [], {}, {}
    for symbol in SYMBOLS:
        path = OLD/(symbol+'_raw_LOCAL.json')
        raw = path.read_bytes()
        payload = json.loads(raw)
        before = json.dumps(payload, sort_keys=True, allow_nan=False)
        try:
            baseline = classify_payload(payload, CUTOFF)
        except ValueError as exc:
            original03_replay[symbol] = dict(status='REJECTED', error=str(exc))
        else:
            original03_replay[symbol] = dict(status='PARSED',completed_rows=len(baseline['completed_rows']))
        result = classify_postclose(payload, CUTOFF)
        if json.dumps(payload, sort_keys=True, allow_nan=False) != before or path.read_bytes() != raw:
            raise ValueError('Input mutation')
        if result['terminal_backtest_allowed'] is not False:
            raise ValueError('Unexpected permission')
        completed.extend(result['completed_rows'])
        per_symbol[symbol] = {k:v for k,v in result.items() if k != 'completed_rows'}
    if {s for s,r in original03_replay.items() if r['status']=='REJECTED'} != {'TQQQ','SQQQ','IBIT'}:
        raise ValueError('Original03 rejection pattern changed')
    candidate = rows(OLD/'regular_candidates_ETF_LOCAL.csv')
    if _etf_index(completed) != _etf_index(candidate) or len(completed) != 28:
        raise ValueError('Original06candidatevalues changed')
    source = json.loads((OLD/'BTCUSDT_30m_LOCAL.json').read_text())
    prefixes = {}
    for label, folder, etfname, srcname in (
        ('01', 'prospective_access_retry_20261120_0100', 'partial_ETF_LOCAL.csv', 'BTCUSDT_30m_partial_LOCAL.json'),
        ('05', 'prospective_five_hour_append_20261120_0500', 'partial_ETF_LOCAL.csv', 'BTCUSDT_30m_partial_LOCAL.json')):
        ep, sp = Path('runs')/folder/etfname, Path('runs')/folder/srcname
        if str(ep) not in verified or str(sp) not in verified:
            raise ValueError('Untrusted prior snapshot')
        er, sr = rows(ep), json.loads(sp.read_text())
        _prefix(_etf_index(er), _etf_index(completed), 'ETF'+label)
        _prefix(_source_index(sr, timestamp(ASOF)), _source_index(source, timestamp(ASOF)), 'Source'+label)
        prefixes[label] = dict(etf_rows=len(er),source_rows=len(sr),missing=0,changed=0,etf_raw_sha256=sha(ep),source_raw_sha256=sha(sp))
    prior = Path('runs/prospective_access_retry_20261120_0100')
    calendar = Path('runs/prospective_readiness_retry_20261119_1700/calendar_20261119.csv')
    audit = audit_snapshot(completed, source, rows(calendar), plan['frozen_at_utc'], ASOF,
        previous_etf_rows=rows(prior/'partial_ETF_LOCAL.csv'),
        previous_source_rows=json.loads((prior/'BTCUSDT_30m_partial_LOCAL.json').read_text()))
    text = io.StringIO(newline='')
    writer = csv.DictWriter(text, fieldnames=('symbol','timestamp','open','high','low','close','volume'))
    writer.writeheader()
    writer.writerows(completed)
    normalized = text.getvalue().encode()
    result = dict(status='ACTUAL06_SAME_PAYLOAD_PARTITION_AND_FULL_STRUCTURE_PASS_NO_EXECUTION',
        original06_manifest_sha256=MANIFEST_SHA, verified_immutable_hash_count=len(verified),
        frozen17_dependency_sha256=plan['code_dependency_hashes'], frozen_plan_git_blob=blob,
        per_symbol=per_symbol, original03_same_payload_replay=original03_replay, raw_unchanged=True, regular_values_equal_original06_candidates=True,
        prefix_comparisons=prefixes, full_structural_audit=audit,
        private_input_sha256=m['private06hashes'], calendar_local_sha256=sha(calendar),
        normalized_etf_local_sha256=hashlib.sha256(normalized).hexdigest(),
        normalized_local_path=str(ROOT/'normalized_ETF_LOCAL.csv'),
        new_market_requests=0, engine_calls=0, real_orders=0, account_trades=0,
        financial_metrics=None, terminal_backtest_allowed=False, PIT_qualified=False,
        signal_parity_verified=False, new_full_AccountState_initialized=False,
        new_independent_validation=False, models_adopted=[],
        source_receipt_host_bracket=m['source_host_bracket'],
        ETF_host_receipt_range=m['ETF_host_receipt_range'],
        limitation='Same actual06payload diagnostic after observed failure, not independent financial validation or vendor warranty. Receipt cannot be backdated to bar cutoff. Source envelope is serialized connector result, not original HTTP body bytes. Full input structure pass does not grant PIT/signal parity/AccountState/engine permission. No performance period exists for current cycle.')
    with (ROOT/'normalized_ETF_LOCAL.csv').open('xb') as f:
        f.write(normalized)
    with (ROOT/'actual_replay.json').open('x') as f:
        f.write(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k:result[k] for k in ('status','verified_immutable_hash_count','new_market_requests','engine_calls','account_trades','financial_metrics')}))

if __name__ == '__main__':
    main()
