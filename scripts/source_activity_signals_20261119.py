"""Bounded Nasdaq reported-activity hypotheses; no execution or outcome access.

Exactly32 source hypotheses have32 matched TQQQ-feature controls. These are
not64 independent alphas. Caller supplies each ACTUALLY completed QQQ or TQQQ
bar at a common release clock; this module never shifts source timestamps,
builds/fills bars, fits parameters or reads future labels.

ctx = {'valid': bool[n], 'source': fields, 'ETF': fields}. Each feed requires
open/high/low/close, rvol20/rvol40. Two-bar families additionally require
prev_open/prev_high/prev_low/prev_close, prev_rvol20/prev_rvol40 and
prev_contiguous: bool[n]. Seasonal ratios use strictly preceding20/40 regular
calendar sessions at the SAME source-bar clock slot. Missing/nonpositive donor
volumes invalidate that ratio; the caller must not skip donors. Current and
prior volume are available only after the actual bar end+declared buffer.

Both feature feeds' family-specific support is intersected BEFORE either onset
stream is evaluated. Removing volume predicates retains that common data
support: it removes information predicates, not source-availability selection.
QQQ reported volume is an activity proxy, not observed investor flow, signed
order flow or liquidity. BTC-USD source-volume hypotheses are not implemented
here because the current data-quality audit blocked them.

All conditions are evaluated at observed caller decision rows. Missing rows do
not consume/rearm an onset; observed valid false rows do. Each NY day resets.
Nasdaq directions select actual TQQQ/SQQQ BUY columns only, independent of
column ordering. Bitcoin BUY policies remain the runner's separate frozen
component. Caller retains15% caps, cash, costs and all existing protections.
"""
from itertools import product
from numbers import Real, Integral

import numpy as np
import pandas as pd

SYMBOLS = ('TQQQ', 'SQQQ', 'IBIT', 'BITI')
LOOKBACKS = (20, 40)
PARAMS = {
    'participation_follow': ((1.25, 1.75), (.25, .5)),
    'absorption_recovery': ((1.25, 1.75), (.2, .4)),
    'thin_move_reversal': ((.5, .75), (.25, .5)),
    'burst_quiet_hold': ((1.5, 2.), (.25, .5)),
}
FAMILIES = tuple(PARAMS)


def candidates():
    return [dict(name=f'{family}_L{lookback}_a{a:g}_b{b:g}',
                 family=family, lookback=lookback, a=a, b=b)
            for family, axes in PARAMS.items()
            for lookback, a, b in product(LOOKBACKS, *axes)]


def _candidate(c):
    family = c.get('family')
    if family not in PARAMS:
        raise ValueError('Unknown activity family')
    lookback, a, b = (c.get(k) for k in ('lookback', 'a', 'b'))
    if (isinstance(lookback, (bool, np.bool_)) or not isinstance(lookback, Integral)
            or lookback not in LOOKBACKS):
        raise ValueError('Unknown fixed seasonal lookback')
    if any(isinstance(x, (bool, np.bool_)) or not isinstance(x, Real)
           for x in (a, b)):
        raise ValueError('Numeric bounded thresholds required')
    if a not in PARAMS[family][0] or b not in PARAMS[family][1]:
        raise ValueError('Unknown fixed activity thresholds')
    return family, int(lookback), float(a), float(b)


def _array(fields, key, n, boolean=False):
    value = np.asarray(fields[key])
    if value.shape != (n,):
        raise ValueError(f'{key} must have shape(n,)')
    if boolean:
        if value.dtype.kind != 'b':
            raise ValueError(f'{key} must be boolean')
        return value
    return np.asarray(value, float)


def _ohlc(fields, n, prefix=''):
    o, h, l, c = (_array(fields, prefix+k, n)
                  for k in ('open', 'high', 'low', 'close'))
    finite = np.isfinite(np.stack((o, h, l, c))).all(axis=0)
    valid = finite & (o > 0) & (h > 0) & (l > 0) & (c > 0)
    malformed = valid & ((h < np.maximum.reduce((o, l, c)))
                         | (l > np.minimum.reduce((o, h, c))))
    if malformed.any():
        raise ValueError('Malformed source/control OHLC')
    width = h-l
    valid &= width > 0
    body = c-o
    efficiency = np.divide(np.abs(body), width, out=np.full(n, np.nan), where=width > 0)
    clv = np.divide(2*c-h-l, width, out=np.full(n, np.nan), where=width > 0)
    return o, h, l, c, body, efficiency, clv, valid


def _features(fields, n, family, lookback):
    o, h, l, c, body, efficiency, clv, valid = _ohlc(fields, n)
    rv = _array(fields, f'rvol{lookback}', n)
    # A reported zero is not interpreted as evidence of a thin market. Source
    # quality/availability rules apply even in the volume-removed comparator.
    valid &= np.isfinite(rv) & (rv > 0)
    result = dict(close=c, body=body, efficiency=efficiency, clv=clv, rvol=rv)
    if family in ('thin_move_reversal', 'burst_quiet_hold'):
        po, ph, pl, pc, pb, pe, pv, prior_valid = _ohlc(fields, n, 'prev_')
        prv = _array(fields, f'prev_rvol{lookback}', n)
        contiguous = _array(fields, 'prev_contiguous', n, True)
        valid &= prior_valid & contiguous & np.isfinite(prv) & (prv > 0)
        result.update(prev_close=pc, prev_body=pb, prev_efficiency=pe, prev_rvol=prv)
    return result, valid


def signals(data, times, ctx, c, feed='source', volume_removed=False):
    """Return n×4 Nasdaq BUY-role scores; no PnL or learned thresholds.

    F1: high same-clock seasonal relative volume and efficient current body;
        follow its sign.
    F2: high seasonal relative volume, small current body, |CLV|>=.6;
        follow close-location sign (an OHLC recovery proxy, not order-flow).
    F3: prior efficient body on low seasonal volume; current opposite body
        recovers >=b of that prior body; follow the completed reversal.
    F4: prior efficient high-volume body, current quieter opposing/flat body
        retaining its close within b of the prior body; follow prior direction.
    """
    family, lookback, a, b = _candidate(c)
    if feed not in ('source', 'ETF'):
        raise ValueError('feed must be source or ETF')
    if not isinstance(volume_removed, (bool, np.bool_)):
        raise ValueError('volume_removed must be boolean')
    calendar = pd.DatetimeIndex(pd.to_datetime(times, utc=True, errors='raise'))
    n = len(calendar)
    if calendar.hasnans or calendar.has_duplicates or not calendar.is_monotonic_increasing:
        raise ValueError('Finite unique increasing timestamps required')
    if not pd.DatetimeIndex(pd.to_datetime(data.timestamps, utc=True)).equals(calendar):
        raise ValueError('ETF timestamps must exactly match supplied times')
    if len(data.symbols) != 4 or set(data.symbols) != set(SYMBOLS):
        raise ValueError('Actual TQQQ/SQQQ/IBIT/BITI required')
    bars = np.stack([np.asarray(getattr(data, key), float)
                     for key in ('open', 'high', 'low', 'close')], axis=2)
    if bars.shape != (n, 4, 4):
        raise ValueError('Actual ETF OHLC must have shape(n,4,4)')
    o, h, l, close = (bars[..., k] for k in range(4))
    quotes = (np.isfinite(bars).all(axis=-1) & (bars > 0).all(axis=-1)
              & (h >= np.maximum.reduce((o, l, close)))
              & (l <= np.minimum.reduce((o, h, close))))
    local = calendar.tz_convert('America/New_York')
    minutes = local.hour.to_numpy()*60+local.minute.to_numpy()
    common = _array(ctx, 'valid', n, True).copy()
    common &= (minutes >= 570) & (minutes < 960) & (local.dayofweek.to_numpy() < 5)
    values = {}
    for key in ('source', 'ETF'):
        values[key], support = _features(ctx[key], n, family, lookback)
        common &= support
    f = values[feed]
    if family == 'participation_follow':
        direction = np.sign(f['body'])
        price = f['efficiency'] >= b
        volume = f['rvol'] >= a
    elif family == 'absorption_recovery':
        direction = np.sign(f['clv'])
        price = (f['efficiency'] <= b) & (np.abs(f['clv']) >= .6)
        volume = f['rvol'] >= a
    elif family == 'thin_move_reversal':
        direction = -np.sign(f['prev_body'])
        price = ((f['prev_efficiency'] >= .5) & (direction*f['body'] > 0)
                 & (direction*(f['close']-f['prev_close']) >= b*np.abs(f['prev_body'])))
        volume = f['prev_rvol'] <= a
    else:
        direction = np.sign(f['prev_body'])
        recovery = -direction*(f['close']-f['prev_close'])
        price = ((f['prev_efficiency'] >= .5) & (direction*f['body'] <= 0)
                 & (recovery >= 0) & (recovery <= b*np.abs(f['prev_body'])))
        volume = (f['prev_rvol'] >= a) & (f['rvol'] <= 1.)
    desired = np.where(price & (volume | bool(volume_removed)) & (direction != 0), direction, 0.)
    output = np.zeros((n, 4))
    bull, bear = data.symbols.index('TQQQ'), data.symbols.index('SQQQ')
    previous_day, previous_direction = None, 0.
    for i, day in enumerate(local.date):
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
