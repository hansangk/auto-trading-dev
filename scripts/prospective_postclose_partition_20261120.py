"""Pure postclose partition for the verified Nov-19 NY normal session only.

This separately versioned policy preserves the frozen intraday classifier.
It can quarantine one flat zero-volume row exactly at calendar close, after
seven exact regular starts. It never merges prices, shifts clocks, or proves
vendor semantics, PIT availability, signal parity, or AccountState lineage.
"""
from copy import deepcopy
from datetime import timedelta

from scripts.prospective_input_audit_20261119 import ETF_FIELDS, _number, timestamp
from scripts.prospective_quote_tail_20261120 import _chart, _epoch, classify_payload

# Verified calendar scope is this session, not a general exchange calendar.
OPENED = timestamp('2026-11-19T14:30:00Z')
CLOSED = timestamp('2026-11-19T21:00:00Z')
REGULAR_STARTS = tuple(OPENED + timedelta(hours=k) for k in range(7))


def classify_postclose(payload, cutoff):
    """Return seven unchanged completed bars and zero or one diagnostic row.

    ``cutoff`` follows the existing aware-string API and must reach close.
    Seven regular rows are required in order; the 20:30 row ends at 21:00,
    so it is a valid final 30-minute bar and is never dropped. An eighth row
    is accepted only exactly at 21:00 with positive finite identical OHLC,
    exact numeric zero volume, and strict integer regularMarketTime between
    close and cutoff inclusive. No price-to-metadata equality or tolerance
    is inferred. The regular-only path retains frozen03 metadata behavior.

    Structure alone never authorizes terminal backtesting or execution.
    """
    asof = timestamp(cutoff)
    if asof < CLOSED:
        raise ValueError('Postclose cutoff must reach verified Nov-19 NY close')
    _, meta, raw_times, quote = _chart(payload)
    starts = tuple(_epoch(value) for value in raw_times)
    if len(starts) not in (7, 8) or starts[:7] != REGULAR_STARTS:
        raise ValueError('Exact ordered seven Nov-19 regular starts required')

    quarantined = []
    if len(starts) == 8:
        if starts[7] != CLOSED:
            raise ValueError('Only exact calendar-close auxiliary timestamp allowed')
        market_time = _epoch(meta.get('regularMarketTime'))
        if not CLOSED <= market_time <= asof:
            raise ValueError('Auxiliary regularMarketTime must be within close and cutoff')
        prices = tuple(_number(quote[field][7]) for field in ETF_FIELDS[:4])
        if min(prices) <= 0 or len(set(prices)) != 1 or _number(quote['volume'][7]) != 0:
            raise ValueError('Auxiliary requires identical positive OHLC and zero volume')
        quarantined.append(dict(
            row_index=7, timestamp=CLOSED.isoformat(), raw_epoch_seconds=raw_times[7],
            reason='POSTCLOSE_ZERO_VOLUME_BOUNDARY_AUXILIARY',
            regular_market_time_utc=market_time.isoformat(),
            preceding_regular_start=REGULAR_STARTS[-1].isoformat(),
            regular_end_exclusive=CLOSED.isoformat()))

    # Never mutate the supplied raw payload; validate the exact regular values
    # through frozen03 and its existing OHLCV validator, including last 30min.
    cleaned = deepcopy(payload)
    regular_data = cleaned['chart']['result'][0]
    regular_data['timestamp'] = regular_data['timestamp'][:7]
    for field in ETF_FIELDS:
        regular_data['indicators']['quote'][0][field] = quote[field][:7]
    result = classify_payload(cleaned, cutoff)
    result['quarantined_records'] = quarantined
    result['counts'] = dict(raw=len(starts), completed=7, quarantined=len(quarantined))
    result['terminal_backtest_allowed'] = False
    return result
