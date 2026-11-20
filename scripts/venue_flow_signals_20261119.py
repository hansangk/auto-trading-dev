"""Bounded, paired BTC spot taker-direction hypotheses; never places orders.

32 definitions (four mechanisms x eight) have 32 matched ``flow_removed``
controls. A control removes only the flow predicates: actual BTC price rules,
completed-history availability, release clock, and onset semantics remain.
There is no inferred ETF flow, investor identity, news, or macro input here.
``flow = 2 * sum(taker_buy_base_volume) / sum(base_volume) - 1`` describes
executed aggressor-side classification at one BTCUSDT venue, not net investment
or global BTC/USD flow. Sum actual contiguous 30m volumes before this ratio.

Caller must construct actual :30-start one-hour bars from two contiguous 30m
bars, exactly match source/ETF spans, enforce source end+5min <= ETF decision,
age <=65min and current RTH day. Do not shift bars or interpolate. Past 24/7
source history may contain actual overnight observations. Masks below attest
contiguous completed history, never forward-filled data. Past means exclude
current; ``prior`` is the immediately preceding source hour, not ETF row.

ctx: valid bool[n], current {open,high,low,close,flow}; trend additionally needs
history4/history8 bool[n] and flow_mean4/flow_mean8 float[n], selected by its
lookback. Other families need history1 bool[n] and prior {same fields}.
Source and control share finite-flow and history support, including controls
whose flow predicate is removed. Missing support does not consume/rearm onset;
valid false does. Each NY day resets onset. Actual target quote failure does
not consume onset. Output is n x four-symbol score: -1 on IBIT/BITI, the
engine's Bitcoin BUY-role marker, never a short sale. Caller adds the frozen
Nasdaq background and retains all allocation, stops, costs, and account risk.

Selection must be made in development only. Recent fit rankings are separate
from strict prior-3/6-month selection for next-month causal replay. Reused2026
is not independent validation. Signals alone establish no profitability.
"""
from itertools import product

import numpy as np
import pandas as pd

SYMBOLS = ('TQQQ', 'SQQQ', 'IBIT', 'BITI')
GRIDS = {
    'flow_trend': {'efficiency': (.35, .55), 'flow_threshold': (.10, .20),
                   'lookback': (4, 8)},
    'absorption_release': {'prior_efficiency': (.25, .40),
                           'flow_threshold': (.15, .25),
                           'efficiency': (.35, .55)},
    'flow_flip': {'efficiency': (.35, .55), 'flow_threshold': (.10, .20),
                  'prior_ceiling': (0., -.10)},
    'burst_hold': {'efficiency': (.35, .55), 'flow_threshold': (.15, .25),
                   'retention': (.50, .75)},
}


def candidates():
    """Return 32 preregistered configurations, in deterministic grid order."""
    result = []
    for family, grid in GRIDS.items():
        for values in product(*grid.values()):
            params = dict(zip(grid, values))
            name = family + '__' + '__'.join(f'{k}={v:g}' for k, v in params.items())
            result.append(dict(name=name, family=family, **params))
    return result


def _config(c):
    family = c.get('family')
    if family not in GRIDS:
        raise ValueError('Unknown taker-flow family')
    grid = GRIDS[family]
    if set(c) - {'family', 'name', *grid}:
        raise ValueError('Unexpected configuration key')
    for key, choices in grid.items():
        value = c.get(key)
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)):
            raise ValueError(f'{key} must be a preregistered numeric value')
        if value not in choices:
            raise ValueError(f'{key} outside preregistered grid')
    return family


def _array(fields, key, n, boolean=False):
    value = np.asarray(fields[key])
    if value.shape != (n,):
        raise ValueError(f'{key} must have shape(n,)')
    if boolean:
        if value.dtype.kind != 'b':
            raise ValueError(f'{key} must be boolean')
        return value
    if value.dtype.kind not in 'fiu':
        raise ValueError(f'{key} must be numeric')
    return np.asarray(value, float)


def _fields(fields, n):
    o, h, l, close = (_array(fields, key, n)
                       for key in ('open', 'high', 'low', 'close'))
    flow = _array(fields, 'flow', n)
    if (np.isfinite(flow) & (np.abs(flow) > 1.)).any():
        raise ValueError('Taker flow must lie in [-1,1]')
    finite = np.isfinite(np.stack((o, h, l, close))).all(axis=0)
    positive = finite & (o > 0) & (h > 0) & (l > 0) & (close > 0)
    if (positive & ((h < np.maximum.reduce((o, l, close)))
                    | (l > np.minimum.reduce((o, h, close))))).any():
        raise ValueError('Malformed completed BTC OHLC')
    width = h-l
    body = close-o
    efficiency = np.divide(np.abs(body), width, out=np.full(n, np.nan),
                           where=width > 0)
    valid = positive & (width > 0) & np.isfinite(flow)
    return dict(open=o, close=close, body=body, efficiency=efficiency,
                flow=flow, valid=valid)


def _prepare(data, times, ctx, c):
    family = _config(c)
    calendar = pd.DatetimeIndex(pd.to_datetime(times, utc=True, errors='raise'))
    n = len(calendar)
    if calendar.hasnans or calendar.has_duplicates or not calendar.is_monotonic_increasing:
        raise ValueError('Finite unique increasing timestamps required')
    if not pd.DatetimeIndex(pd.to_datetime(data.timestamps, utc=True)).equals(calendar):
        raise ValueError('ETF timestamps must exactly match supplied times')
    if len(data.symbols) != 4 or set(data.symbols) != set(SYMBOLS):
        raise ValueError('Actual TQQQ/SQQQ/IBIT/BITI columns required')
    current = _fields(ctx['current'], n)
    common = _array(ctx, 'valid', n, True).copy() & current['valid']
    local = calendar.tz_convert('America/New_York')
    minutes = local.hour.to_numpy()*60+local.minute.to_numpy()
    common &= ((minutes >= 570) & (minutes < 960)
               & (local.dayofweek.to_numpy() < 5))
    prior, mean = None, None
    if family == 'flow_trend':
        lookback = c['lookback']
        common &= _array(ctx, f'history{lookback}', n, True)
        mean = _array(ctx, f'flow_mean{lookback}', n)
        if (np.isfinite(mean) & (np.abs(mean) > 1.)).any():
            raise ValueError('Past mean flow must lie in [-1,1]')
        common &= np.isfinite(mean)
    else:
        prior = _fields(ctx['prior'], n)
        common &= _array(ctx, 'history1', n, True) & prior['valid']
    return calendar, common, current, prior, mean


def support(data, times, ctx, c):
    """Return identical source/control support before any onset updates."""
    return _prepare(data, times, ctx, c)[1]


def signals(data, times, ctx, c, flow_removed=False):
    """Actual IBIT/BITI BUY-role onsets, with independent matched controls."""
    if not isinstance(flow_removed, (bool, np.bool_)):
        raise ValueError('flow_removed must be boolean')
    calendar, common, now, prior, mean = _prepare(data, times, ctx, c)
    n = len(calendar)
    bars = np.stack([np.asarray(getattr(data, key), float)
                     for key in ('open', 'high', 'low', 'close')], axis=2)
    if bars.shape != (n, 4, 4):
        raise ValueError('Actual ETF OHLC must have shape(n,4,4)')
    o, h, l, close = (bars[..., k] for k in range(4))
    quotes = (np.isfinite(bars).all(axis=-1) & (bars > 0).all(axis=-1)
              & (h >= np.maximum.reduce((o, l, close)))
              & (l <= np.minimum.reduce((o, h, close))))
    family = c['family']
    direction = np.sign(now['body'])
    if family == 'flow_trend':
        price = now['efficiency'] >= c['efficiency']
        flow = ((direction*now['flow'] >= c['flow_threshold'])
                & (direction*(now['flow']-mean) > 0))
    elif family == 'absorption_release':
        price = ((prior['efficiency'] <= c['prior_efficiency'])
                 & (now['efficiency'] >= c['efficiency'])
                 & (direction*(now['close']-prior['close']) > 0))
        flow = ((-direction*prior['flow'] >= c['flow_threshold'])
                & (direction*now['flow'] > 0))
    elif family == 'flow_flip':
        price = ((now['efficiency'] >= c['efficiency'])
                 & (direction*(now['close']-prior['close']) > 0))
        flow = ((direction*now['flow'] >= c['flow_threshold'])
                & (direction*prior['flow'] <= c['prior_ceiling']))
    else:
        direction = np.sign(prior['body'])
        retained = direction*(now['close']-prior['open'])
        # A shallow counterbody/doji keeps retention nontrivial for contiguous
        # BTC prices. Requiring another same-direction body would make both
        # .50/.75 retention settings effectively identical (usually >=1).
        price = ((prior['efficiency'] >= c['efficiency'])
                 & (direction*now['body'] <= 0)
                 & (retained >= c['retention']*np.abs(prior['body'])))
        flow = ((direction*prior['flow'] >= c['flow_threshold'])
                & (direction*now['flow'] > 0))
    desired = np.where(price & (direction != 0) & (True if flow_removed else flow),
                       direction, 0.)
    output = np.zeros((n, 4))
    bull, bear = data.symbols.index('IBIT'), data.symbols.index('BITI')
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
            output[i, target] = -1.
            previous_direction = value
    return output
