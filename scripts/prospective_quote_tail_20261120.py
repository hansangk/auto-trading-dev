"""Pure Nov-19 snapshot partitioning; no acquisition, execution, or PnL.

A metadata-matched, flat, zero-volume final quote can be quarantined inside
an incomplete regular interval. This is a deliberately narrow structural
classification, not a vendor warranty or proof of historical availability.
No quarantined price is merged into, or used to alter, a completed bar.
"""
from datetime import timedelta

from scripts.prospective_input_audit_20261119 import (
    ETF_FIELDS, SYMBOLS, _etf_index, _number, timestamp,
)

OPENED = timestamp('2026-11-19T14:30:00Z')
CLOSED = timestamp('2026-11-19T21:00:00Z')
REGULAR_STARTS = frozenset(OPENED + timedelta(hours=k) for k in range(7))
EPOCH = timestamp('1970-01-01T00:00:00Z')


def _epoch(value):
    # Decoded Yahoo timestamps are integer seconds. Never round or shift them.
    if type(value) is not int:
        raise ValueError('Integer epoch seconds required')
    try:
        return EPOCH + timedelta(seconds=value)
    except OverflowError as exc:
        raise ValueError('Epoch seconds out of range') from exc


def _chart(payload):
    try:
        chart = payload['chart']
        results = chart['result']
        if chart.get('error') is not None:
            raise ValueError('Yahoo chart error refused')
        if not isinstance(results, list) or len(results) != 1:
            raise ValueError('Exactly one nonempty chart result required')
        data = results[0]
        meta = data['meta']
        if (meta['symbol'] not in SYMBOLS or meta['currency'] != 'USD'
                or meta['exchangeTimezoneName'] != 'America/New_York'):
            raise ValueError('Unexpected ETF symbol/currency/timezone')
        times = data['timestamp']
        quotes = data['indicators']['quote']
        if not isinstance(times, list) or not times:
            raise ValueError('Nonempty timestamp array required')
        if not isinstance(quotes, list) or len(quotes) != 1:
            raise ValueError('Exactly one quote array required')
        quote = quotes[0]
        if any(not isinstance(quote[field], list) or len(quote[field]) != len(times)
               for field in ETF_FIELDS):
            raise ValueError('Quote arrays must match timestamp length')
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError('Malformed Yahoo chart payload') from exc
    return data, meta, times, quote


def classify_payload(payload, cutoff):
    """Return completed_rows and quarantined_records for one decoded chart.

    ``cutoff`` uses the existing aware-string timestamp API. Future timestamp
    rows are quarantined before bar-clock checks; regular incomplete rows are
    also excluded. All raw timestamps must still be strictly increasing.
    Off-clock rows at/before cutoff fail unless every preregistered final-tail
    predicate holds. Completed OHLCV uses the existing ETF validator.

    This function neither qualifies full session coverage nor establishes PIT
    receipt, unchanged prior snapshots, signal parity, or AccountState lineage.
    """
    asof = timestamp(cutoff)
    _, meta, raw_times, quote = _chart(payload)
    starts = [_epoch(value) for value in raw_times]
    if any(right <= left for left, right in zip(starts, starts[1:])):
        raise ValueError('Duplicate or nonmonotonic timestamps refused')

    completed, quarantined = [], []
    for i, start in enumerate(starts):
        diagnostic = dict(row_index=i, timestamp=start.isoformat(),
                          raw_epoch_seconds=raw_times[i])
        if start > asof:
            diagnostic['reason'] = 'FUTURE_TIMESTAMP'
            quarantined.append(diagnostic)
            continue
        if start in REGULAR_STARTS:
            end = min(start + timedelta(hours=1), CLOSED)
            if end > asof:
                diagnostic.update(reason='INCOMPLETE_REGULAR_BAR',
                                  regular_end_exclusive=end.isoformat())
                quarantined.append(diagnostic)
                continue
            row = dict(symbol=meta['symbol'], timestamp=start.isoformat(),
                       **{field: quote[field][i] for field in ETF_FIELDS})
            _etf_index([row])
            completed.append(row)
            continue

        # This exception only quarantines; it never turns a quote into a bar.
        if i != len(starts)-1 or i == 0:
            raise ValueError('Unknown off-clock row at/before cutoff')
        previous = starts[i-1]
        end = min(previous + timedelta(hours=1), CLOSED)
        if (previous not in REGULAR_STARTS or not previous <= asof < end
                or not previous < start < end):
            raise ValueError('Off-clock tail lacks an incomplete regular predecessor')
        if _epoch(meta.get('regularMarketTime')) != start:
            raise ValueError('Off-clock tail does not match regularMarketTime')
        prices = tuple(_number(quote[field][i]) for field in ETF_FIELDS[:4])
        if min(prices) <= 0 or len(set(prices)) != 1 or _number(quote['volume'][i]) != 0:
            raise ValueError('Off-clock tail requires identical positive OHLC and zero volume')
        diagnostic.update(reason='METADATA_MATCHED_ZERO_VOLUME_LIVE_TAIL',
                          preceding_regular_start=previous.isoformat(),
                          regular_end_exclusive=end.isoformat())
        quarantined.append(diagnostic)

    # Keep duplicate protection tied to the existing validator as well.
    _etf_index(completed)
    return dict(symbol=meta['symbol'], cutoff_utc=asof.isoformat(),
                completed_rows=completed, quarantined_records=quarantined,
                counts=dict(raw=len(starts), completed=len(completed),
                            quarantined=len(quarantined)),
                terminal_backtest_allowed=False)
