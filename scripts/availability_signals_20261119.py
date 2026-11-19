"""Fixed price-body signal under four explicit volume-support definitions.

Eight definitions are source/ETF x none/current/L20/L40. They are execution
and availability controls, not eight new independent alphas. The efficiency
threshold is fixed at .5; no outcome-based parameter search is performed.

Caller supplies actual completed QQQ and exactly matched TQQQ OHLC at the
same source start/end and release clock. ``valid`` must enforce actual source
end+publication-buffer <= decision, age, and current RTH day. This module
never shifts bars, fills prices, computes donor histories, or executes orders.

ctx = {'valid': bool[n], 'source': OHLCfields, 'ETF': OHLCfields,
       'current_positive': bool[n], 'history20': bool[n], 'history40': bool[n]}.
Only the selected support mask is read. In particular gate='none' is independent
of volume data and does not require ANY volume mask or volume history. Caller
computes current_positive from the raw CURRENT source and matched-ETF volumes,
never from the presence of a seasonal ratio. history20/40 match the old shared
finite-positive source/ETF seasonal-ratio availability, without ratio thresholds.

Both feed price-valid supports are always intersected. The chosen volume mask
is applied BEFORE onset state updates. Missing observations do not rearm or
consume an episode; valid price-condition-false observations rearm it. Each NY
day resets. The output selects actual TQQQ/SQQQ BUY columns; Bitcoin is the
caller's separately frozen background and all risk/execution remains unchanged.
"""
from itertools import product

import numpy as np
import pandas as pd

SYMBOLS = ('TQQQ', 'SQQQ', 'IBIT', 'BITI')
FEEDS = ('source', 'ETF')
GATES = ('none', 'current', 'L20', 'L40')
EFFICIENCY = .5


def candidates():
    return [dict(name=f'{feed}__{gate}', feed=feed, gate=gate)
            for feed, gate in product(FEEDS, GATES)]


def _array(fields, key, n, boolean=False):
    value = np.asarray(fields[key])
    if value.shape != (n,):
        raise ValueError(f'{key} must have shape(n,)')
    if boolean:
        if value.dtype.kind != 'b':
            raise ValueError(f'{key} must be boolean')
        return value
    return np.asarray(value, float)


def _price(fields, n):
    o, h, l, c = (_array(fields, key, n)
                  for key in ('open', 'high', 'low', 'close'))
    finite = np.isfinite(np.stack((o, h, l, c))).all(axis=0)
    positive = finite & (o > 0) & (h > 0) & (l > 0) & (c > 0)
    malformed = positive & ((h < np.maximum.reduce((o, l, c)))
                            | (l > np.minimum.reduce((o, h, c))))
    if malformed.any():
        raise ValueError('Malformed completed source/control OHLC')
    width = h-l
    valid = positive & (width > 0)
    body = c-o
    efficiency = np.divide(np.abs(body), width, out=np.full(n, np.nan),
                           where=width > 0)
    return body, efficiency, valid


def support(data, times, ctx, gate):
    """Past-observation support, independent of signal direction and returns."""
    if gate not in GATES:
        raise ValueError('Unknown fixed support gate')
    calendar = pd.DatetimeIndex(pd.to_datetime(times, utc=True, errors='raise'))
    n = len(calendar)
    if calendar.hasnans or calendar.has_duplicates or not calendar.is_monotonic_increasing:
        raise ValueError('Finite unique increasing timestamps required')
    if not pd.DatetimeIndex(pd.to_datetime(data.timestamps, utc=True)).equals(calendar):
        raise ValueError('ETF timestamps must exactly match supplied times')
    if len(data.symbols) != 4 or set(data.symbols) != set(SYMBOLS):
        raise ValueError('Actual TQQQ/SQQQ/IBIT/BITI columns required')
    common = _array(ctx, 'valid', n, True).copy()
    local = calendar.tz_convert('America/New_York')
    minutes = local.hour.to_numpy()*60+local.minute.to_numpy()
    common &= ((minutes >= 570) & (minutes < 960)
               & (local.dayofweek.to_numpy() < 5))
    for feed in FEEDS:
        common &= _price(ctx[feed], n)[2]
    if gate != 'none':
        key = {'current': 'current_positive', 'L20': 'history20',
               'L40': 'history40'}[gate]
        common &= _array(ctx, key, n, True)
    return common


def signals(data, times, ctx, c):
    """Return n×4 actual Nasdaq ETF BUY-role scores with a fixed .5 body rule."""
    feed, gate = c.get('feed'), c.get('gate')
    if feed not in FEEDS or gate not in GATES:
        raise ValueError('Unknown fixed feed/support definition')
    common = support(data, times, ctx, gate)
    calendar = pd.DatetimeIndex(pd.to_datetime(times, utc=True))
    n = len(calendar)
    bars = np.stack([np.asarray(getattr(data, key), float)
                     for key in ('open', 'high', 'low', 'close')], axis=2)
    if bars.shape != (n, 4, 4):
        raise ValueError('Actual ETF OHLC must have shape(n,4,4)')
    o, h, l, close = (bars[..., k] for k in range(4))
    quotes = (np.isfinite(bars).all(axis=-1) & (bars > 0).all(axis=-1)
              & (h >= np.maximum.reduce((o, l, close)))
              & (l <= np.minimum.reduce((o, h, close))))
    body, efficiency, _ = _price(ctx[feed], n)
    direction = np.sign(body)
    desired = np.where((efficiency >= EFFICIENCY) & (direction != 0),
                       direction, 0.)
    output = np.zeros((n, 4))
    bull, bear = data.symbols.index('TQQQ'), data.symbols.index('SQQQ')
    previous_day, previous_direction = None, 0.
    for i, day in enumerate(calendar.tz_convert('America/New_York').date):
        if day != previous_day:
            previous_day, previous_direction = day, 0.
        if not common[i]:
            continue
        value = desired[i]
        if value == 0:
            previous_direction = 0.
            continue
        target = bull if value > 0 else bear
        if value != previous_direction and quotes[i, target]:
            output[i, target] = 1.
            previous_direction = value
    return output


# Proposed only: actual required histories are not present in this experiment.
# No grid below was implemented or executed. Each needs PIT/changed-event gates
# and matched price-only controls BEFORE its bounded parameter grid is opened.
FUTURE_HYPOTHESES = [
    dict(id='constituent_breadth_diffusion',
         mechanism='PIT Nasdaq constituent breadth may distinguish broad participation from a narrow QQQ price move',
         requires='Historical membership and actual completed constituent OHLCV with availability timestamps',
         parameters=dict(breadth_hours=[1, 3], breadth_z=[1., 2.],
                         confirmation_hours=[1, 2], hold_hours=[2, 4]),
         maximum_combinations=16, status='PROPOSED_ONLY_MISSING_PIT_CONSTITUENTS',
         reject='Survivorship/revised membership, absent timestamps, or fewer than20 changed events per development window'),
    dict(id='cross_venue_basis_reconvergence',
         mechanism='Observed BTC cross-venue premium reconvergence may add information beyond a common spot return',
         requires='Actual synchronized exchange BTC/USD and BTC/USDT quotes, USD/USDT conversion and receipt clocks',
         parameters=dict(basis_history_hours=[24, 72], basis_z=[1.5, 2.5],
                         confirmation_hours=[1, 2], hold_hours=[2, 4]),
         maximum_combinations=16, status='PROPOSED_ONLY_MISSING_VENUE_QUOTES',
         reject='Assumed quote synchronization, missing stablecoin conversion, feed gaps treated as zero basis, or insufficient interventions'),
    dict(id='volatility_term_state',
         mechanism='An actual volatility term-structure state may condition price continuation without enlarging position risk',
         requires='Vintaged volatility-index/term-contract marks and actual release clocks',
         parameters=dict(history_sessions=[20, 60], slope_threshold=[0., .05],
                         completed_hour_confirmations=[1, 2], hold_hours=[2, 4]),
         maximum_combinations=16, status='PROPOSED_ONLY_MISSING_TERM_HISTORY',
         reject='Backfilled/revised index history, maturity lookahead, price-only alias, or inadequate changed-event support'),
    dict(id='finalized_exchange_flow_shock',
         mechanism='Newly finalized, timestamped on-chain exchange transfer shocks may identify BTC pressure beyond price/volume',
         requires='Historically vintaged address labels, block/publication/receipt times and transfer revisions',
         parameters=dict(block_confirmations=[6, 12], history_days=[30, 90],
                         shock_z=[1.5, 2.5], post_release_wait_hours=[1, 3]),
         maximum_combinations=16, status='PROPOSED_ONLY_MISSING_VINTAGED_CHAIN_LABELS',
         reject='Retroactive address labels, unknown publication latency, transfer/flow semantics not established, or inadequate support'),
]
