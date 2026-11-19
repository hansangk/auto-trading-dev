"""Fail-closed input structure audit; never fetch prices or invoke an engine.

Passing this audit does not prove historical receipt/release times, vendor
authenticity, signal parity, or a complete carried AccountState.
"""
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
import argparse
import csv
import hashlib
import json

try:
    from scripts.prospective_shadow_guard_20261119 import NY, timestamp, validate_plan
except ModuleNotFoundError:
    from prospective_shadow_guard_20261119 import NY, timestamp, validate_plan

SYMBOLS = ('TQQQ', 'SQQQ', 'IBIT', 'BITI')
STEP_MS = 1800000
LAG = timedelta(minutes=5)
ETF_FIELDS = ('open', 'high', 'low', 'close', 'volume')


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def _number(value):
    if isinstance(value, bool):
        raise ValueError('Boolean is not a price/count')
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError('Invalid numeric input') from exc
    if not result.is_finite():
        raise ValueError('Nonfinite numeric input')
    return result


def _integer(value):
    result = _number(value)
    if result != result.to_integral_value():
        raise ValueError('Integer timestamp/count required')
    return int(result)


def _ohlcv(values):
    o, h, low, c, v = values
    if min(values) <= 0 or not low <= min(o, c) <= max(o, c) <= h:
        raise ValueError('Invalid positive OHLCV/bounds')


def _etf_index(rows):
    index = {}
    for row in rows:
        symbol = row['symbol']
        if symbol not in SYMBOLS:
            raise ValueError('Unknown ETF symbol')
        start = timestamp(row['timestamp'])
        values = tuple(_number(row[field]) for field in ETF_FIELDS)
        _ohlcv(values)
        key = (symbol, start)
        if key in index:
            raise ValueError('Duplicate ETF symbol-time')
        index[key] = values
    return index


def _source_index(rows, asof):
    index = {}
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != 12:
            raise ValueError('Actual Binance 12-column source rows required')
        values = tuple(_number(v) for v in row)
        start_ms, end_ms = _integer(row[0]), _integer(row[6])
        if start_ms % STEP_MS or end_ms + 1 - start_ms != STEP_MS:
            raise ValueError('Invalid source 30-minute span/alignment')
        # Datetime arithmetic from integer milliseconds avoids float rounding.
        start = timestamp('1970-01-01T00:00:00Z') + timedelta(milliseconds=start_ms)
        if start + timedelta(milliseconds=STEP_MS) + LAG > asof:
            raise ValueError('Future or assumed-unreleased source row')
        _ohlcv(values[1:6])
        if values[7] <= 0 or _integer(row[8]) <= 0:
            raise ValueError('Positive quote volume/trade count required')
        if not 0 <= values[9] <= values[5] or not 0 <= values[10] <= values[7]:
            raise ValueError('Invalid source taker volume bounds')
        if start in index:
            raise ValueError('Duplicate source open time')
        index[start] = values
    starts = sorted(index)
    if any(b-a != timedelta(minutes=30) for a, b in zip(starts, starts[1:])):
        raise ValueError('Source snapshot contains a gap; synthesis forbidden')
    return index


def _sessions(calendar_rows, frozen, asof):
    if not calendar_rows:
        raise ValueError('Verified normal-session calendar required')
    sessions, seen = [], set()
    for row in calendar_rows:
        day = row['day']
        opened, closed = timestamp(row['open']), timestamp(row['close'])
        op, cl = opened.astimezone(NY), closed.astimezone(NY)
        if day in seen or op.date().isoformat() != day or cl.date().isoformat() != day:
            raise ValueError('Calendar date/uniqueness mismatch')
        seen.add(day)
        if (op.weekday() > 4 or (op.hour, op.minute) != (9, 30)
                or (cl.hour, cl.minute) != (16, 0)
                or any((op.second, op.microsecond, cl.second, cl.microsecond))
                or closed-opened != timedelta(minutes=390)):
            raise ValueError('Verified normal NY 390-minute session required')
        if opened < frozen:
            raise ValueError('Cross-freeze/pre-freeze ETF session refused')
        if closed > asof:
            raise ValueError('Incomplete/future ETF session refused')
        sessions.append((day, opened, closed))
    return sorted(sessions, key=lambda x: x[1])


def _prefix(old, new, label):
    for key, values in old.items():
        if key not in new or new[key] != values:
            raise ValueError(label + ' snapshot revision/removal refused; separate vintage research required')


def audit_snapshot(etf_rows, source_rows, calendar_rows, freeze, asof,
                   previous_etf_rows=None, previous_source_rows=None):
    """Audit supplied actual-format snapshots, raising ValueError on any failure.

    ETF timestamps are bar STARTs, including the final 30-minute RTH bar.
    Source end+5m is an assumed availability floor, not observed PIT receipt.
    Source warmup may cross freeze; ETF evaluation sessions may not.
    The caller must independently verify the calendar's official provenance.
    Every supplied source row must form one contiguous snapshot: appending a
    later session therefore requires actual overnight/weekend bars as well.
    """
    etf_rows, source_rows, calendar_rows = list(etf_rows), list(source_rows), list(calendar_rows)
    if previous_etf_rows is not None:
        previous_etf_rows = list(previous_etf_rows)
    if previous_source_rows is not None:
        previous_source_rows = list(previous_source_rows)
    frozen, now = timestamp(freeze), timestamp(asof)
    if now < frozen:
        raise ValueError('Clock predates freeze')
    sessions = _sessions(calendar_rows, frozen, now)
    etfs, sources = _etf_index(etf_rows), _source_index(source_rows, now)
    expected_etfs, required_sources, rth_sources = set(), set(), set()
    for _, opened, closed in sessions:
        expected_etfs.update((symbol, opened+timedelta(hours=k))
                             for symbol in SYMBOLS for k in range(7))
        start = opened-timedelta(hours=8)
        while start < closed:
            required_sources.add(start)
            if start >= opened:
                rth_sources.add(start)
            start += timedelta(minutes=30)
    if set(etfs) != expected_etfs:
        raise ValueError('ETF exact coverage failed: missing, extra, future, or warmup row')
    if not required_sources <= set(sources):
        raise ValueError('Missing actual source warmup/RTH coverage')
    if previous_etf_rows is not None:
        _prefix(_etf_index(previous_etf_rows), etfs, 'ETF')
    if previous_source_rows is not None:
        _prefix(_source_index(previous_source_rows, now), sources, 'Source')
    result = dict(
        status='INPUTS_AUDITED_SIGNAL_PARITY_AND_ACCOUNT_STATE_STILL_REQUIRED',
        input_audited=True, terminal_backtest_allowed=False, engine_calls=0,
        real_orders=0, metrics=None, profit_metrics=None, new_independent_validation=False,
        calendar_provenance_independently_required=True,
        actual_price_authenticity_independently_required=True,
        point_in_time_receipt_provenance_independently_required=True,
        frozen_at_utc=frozen.isoformat(), asof_utc=now.isoformat(),
        verified_calendar_days=[x[0] for x in sessions],
        rows={'etf': len(etfs), 'source': len(sources)},
        counts={'sessions': len(sessions), 'etf_rows_per_session': 28,
                'etf_rows_per_symbol': {s: sum(k[0] == s for k in etfs) for s in SYMBOLS},
                'required_source_rows': len(required_sources),
                'required_source_rows_per_session': 29},
        period={'etf_first_bar_start_utc': min(k[1] for k in etfs).isoformat(),
                'etf_last_session_close_utc': sessions[-1][2].isoformat(),
                'source_first_open_utc': min(sources).isoformat(),
                'source_last_end_exclusive_utc': (max(sources)+timedelta(minutes=30)).isoformat()},
        warmup={'required_hours_before_each_session': 8,
                'required_source_warmup_rows': len(required_sources-rth_sources),
                'additional_source_rows': len(set(sources)-required_sources),
                'etf_warmup_rows_in_evaluation': 0,
                'source_warmup_may_cross_freeze': True},
        source_snapshot_requires_contiguous_actual_overnight_and_weekend_bars=True,
        snapshot_prefix_checked={'etf': previous_etf_rows is not None,
                                 'source': previous_source_rows is not None},
        input_raw_hashes={'etf_rows_sha256': _hash(etf_rows),
                          'source_rows_sha256': _hash(source_rows),
                          'calendar_rows_sha256': _hash(calendar_rows),
                          'previous_etf_rows_sha256': (_hash(previous_etf_rows)
                                                       if previous_etf_rows is not None else None),
                          'previous_source_rows_sha256': (_hash(previous_source_rows)
                                                          if previous_source_rows is not None else None)},
        price_audit_limitation=(
            'Structure and supplied snapshot coverage only. Calendar hours do not prove actual '
            'price acquisition, vendor authenticity, official-calendar provenance, or PIT receipt. '
            'Source end+5 minutes is an assumed minimum availability; ETF bar start timestamps '
            'do not establish publication/receipt times. Actual versioned acquisition provenance, '
            'signal parity, new FULL AccountState per model/control/stress, and engine integration '
            'remain required. No source bars synthesized or interpolated.'),
    )
    result['output_audit_sha256'] = _hash(result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ('etf-csv', 'source-json', 'calendar', 'plan', 'plan-blob-sha1', 'now', 'out'):
        p.add_argument('--'+arg, required=True)
    a = p.parse_args()
    out = Path(a.out)
    if out.exists():
        raise RuntimeError('Existing audit output protected; use a new checkpoint')
    for filename in ('RUNNING.lock', 'call_intent_LOCAL.json'):
        if (out.parent/filename).exists():
            raise RuntimeError('Unresolved local worker/intent')
    raw = {name: Path(path).read_bytes() for name, path in (
        ('plan', a.plan), ('etf', a.etf_csv), ('source', a.source_json), ('calendar', a.calendar))}
    blob = hashlib.sha1(b'blob '+str(len(raw['plan'])).encode()+b'\0'+raw['plan']).hexdigest()
    if blob != a.plan_blob_sha1:
        raise RuntimeError('Frozen plan differs from expected Git blob')
    plan = json.loads(raw['plan'])
    validate_plan(plan)
    dependencies = plan['code_dependency_hashes']
    if len(dependencies) != 17:
        raise RuntimeError('Expected 17 frozen dependencies')
    for filename, want in dependencies.items():
        if hashlib.sha256(Path(filename).read_bytes()).hexdigest() != want:
            raise RuntimeError('Frozen dependency mismatch: '+filename)
    result = audit_snapshot(list(csv.DictReader(raw['etf'].decode().splitlines())),
                            json.loads(raw['source']),
                            list(csv.DictReader(raw['calendar'].decode().splitlines())),
                            plan['frozen_at_utc'], a.now)
    result.pop('output_audit_sha256')
    result.update(input_file_sha256={k: hashlib.sha256(v).hexdigest() for k, v in raw.items()},
                  plan_git_blob_sha1=blob, frozen_dependency_hashes=dependencies,
                  audit_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    result['output_audit_sha256'] = _hash(result)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x') as f:
        f.write(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
