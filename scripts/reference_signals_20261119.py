"""Sixteen causal source-reference signal proposals; no portfolio execution.

``refs`` contains exact-clock QQQ/BTC-USD OHLC, shape (rows, 2, 4).
Times identify five-minute bar STARTS. A score uses that row's completed close;
the caller must execute at the following bar open, plus any execution delay.
The nominal ETF coefficients below are signal approximations only: actual ETF
prices, allocations, protections and execution remain the runner's concern.

Missing source rows are never filled. Missing rows, clock gaps, session changes
and non-RTH rows reset the affected history and onset state. Fifteen-minute
bars are aligned to New York 09:30, not to positions in a filtered array.
"""

from itertools import product

import numpy as np
import pandas as pd


PARAMS = {
    "tracking_catchup": ((3, 6), (1., 2.)),
    "sweep_reclaim_15m": ((6, 12), (.65, .80)),
    "shock_exhaustion": ((1, 3), (1.5, 2.)),
    "cross_reference_sync": ((3, 6), (.5, 1.)),
}
FAMILIES = tuple(PARAMS)
SYMBOLS = ("TQQQ", "SQQQ", "IBIT", "BITI")
FIVE_MINUTES_NS = 300_000_000_000


def candidates():
    return [dict(name=f"{family}_{a}_{b:g}", family=family, a=a, b=b)
            for family, axes in PARAMS.items() for a, b in product(*axes)]


def _inputs(data, times, refs, c):
    family = c.get("family")
    if family not in PARAMS or c.get("a") not in PARAMS[family][0] or c.get("b") not in PARAMS[family][1]:
        raise ValueError("Unknown reference-signal family or parameters")
    calendar = pd.DatetimeIndex(pd.to_datetime(times, utc=True, errors="raise"))
    n = len(calendar)
    if calendar.hasnans or not calendar.is_monotonic_increasing or calendar.has_duplicates:
        raise ValueError("Times must be finite, strictly increasing and unique")
    if len(data.symbols) != 4 or set(data.symbols) != set(SYMBOLS):
        raise ValueError("Actual TQQQ/SQQQ/IBIT/BITI columns are required")
    actual = np.asarray(data.close, dtype=float)
    source = np.asarray(refs, dtype=float)
    if actual.shape != (n, 4) or source.shape != (n, 2, 4):
        raise ValueError("Expected ETF close (n,4) and reference OHLC (n,2,4)")
    if not np.isfinite(actual).all() or np.any(actual <= 0):
        raise ValueError("Actual ETF closes must be finite and positive")
    if not pd.DatetimeIndex(pd.to_datetime(data.timestamps, utc=True)).equals(calendar):
        raise ValueError("ETF data and supplied times must match exactly")
    finite = np.isfinite(source).all(axis=2)
    o, h, l, k = (source[:, :, j] for j in range(4))
    malformed = finite & ((source <= 0).any(axis=2) | (h < np.maximum.reduce([o, l, k]))
                          | (l > np.minimum.reduce([o, h, k])))
    if np.any(malformed):
        raise ValueError("Reference OHLC must be positive and internally consistent")
    local = calendar.tz_convert("America/New_York")
    minutes = local.hour.to_numpy() * 60 + local.minute.to_numpy()
    if np.any((minutes % 5 != 0) | (local.second.to_numpy() != 0)
              | (local.microsecond.to_numpy() != 0) | (local.nanosecond.to_numpy() != 0)):
        raise ValueError("Reference signals require exact five-minute bar starts")
    rth = (minutes >= 570) & (minutes < 960)
    finite &= rth[:, None]
    return calendar, minutes, actual, source, finite


def _segments(calendar, valid):
    """Contiguous valid same-session row ranges; no history bridges a gap."""
    days = calendar.tz_convert("America/New_York").date
    begin = None
    for i in range(len(calendar)):
        continuous = (i > 0 and days[i] == days[i - 1]
                      and calendar.asi8[i] - calendar.asi8[i - 1] == FIVE_MINUTES_NS)
        if begin is not None and (not valid[i] or not continuous):
            yield begin, i
            begin = None
        if valid[i] and begin is None:
            begin = i
    if begin is not None:
        yield begin, len(calendar)


def _prior_vol(returns, i):
    """SD of exactly 12 returns ending at i-1, never including return i."""
    if i < 13:
        return 0.
    return float(np.std(returns[i - 12:i], ddof=0))


def signals(data, times, refs, c):
    calendar, minutes, actual, source, valid = _inputs(data, times, refs, c)
    result = np.zeros_like(actual)
    lookup = {symbol: data.symbols.index(symbol) for symbol in SYMBOLS}
    pairs = ((lookup["TQQQ"], lookup["SQQQ"]), (lookup["IBIT"], lookup["BITI"]))
    roles = (1., -1.)
    family, horizon, threshold = c["family"], c["a"], c["b"]

    if family == "cross_reference_sync":
        for start, end in _segments(calendar, valid.all(axis=1)):
            close = np.log(source[start:end, :, 3])
            returns = np.vstack((np.zeros((1, 2)), np.diff(close, axis=0)))
            previous = 0
            for p in range(end - start):
                state = 0
                if p >= max(13, horizon):
                    vol = np.array([_prior_vol(returns[:, j], p) for j in range(2)])
                    if np.all(vol > 1e-12):
                        z = (close[p] - close[p - horizon]) / (vol * np.sqrt(horizon))
                        state = 1 if np.all(z > threshold) else -1 if np.all(z < -threshold) else 0
                if state and state != previous:
                    for role, pair in zip(roles, pairs):
                        result[start + p, pair[0 if state > 0 else 1]] = role
                previous = state
        return result

    for reference, (pair, role) in enumerate(zip(pairs, roles)):
        for start, end in _segments(calendar, valid[:, reference]):
            bars = source[start:end, reference]
            close = np.log(bars[:, 3])
            returns = np.r_[0., np.diff(close)]
            if family == "tracking_catchup":
                # Fixed nominal sensitivities are not a leveraged-price proxy.
                exposure = np.array([3., -3.]) if reference == 0 else np.array([1., -1.])
                etf = np.log(actual[start:end][:, pair])
                q = np.full_like(etf, np.nan)
                q[horizon:] = ((close[horizon:] - close[:-horizon])[:, None] * exposure
                               - (etf[horizon:] - etf[:-horizon]))
                previous = -1
                for p in range(end - start):
                    chosen = -1
                    if p >= horizon + 48:
                        sd = np.std(q[p - 48:p], axis=0, ddof=0)
                        z = np.divide(q[p], sd, out=np.full(2, -np.inf), where=sd > 1e-12)
                        expected = (close[p] - close[p - horizon]) * exposure
                        z[(expected <= 0) | (z <= threshold)] = -np.inf
                        if np.isfinite(z).any():
                            chosen = int(np.argmax(z))
                    if chosen >= 0 and chosen != previous:
                        result[start + p, pair[chosen]] = role
                    previous = chosen
            elif family == "sweep_reclaim_15m":
                completed = []
                for p in range(end - start):
                    i = start + p
                    if p < 2 or (minutes[i] - 570) % 15 != 10:
                        continue
                    triple = bars[p - 2:p + 1]
                    high, low, last = triple[:, 1].max(), triple[:, 2].min(), triple[-1, 3]
                    if len(completed) >= horizon and high > low:
                        prior = completed[-horizon:]
                        top = max(bar[0] for bar in prior)
                        bottom = min(bar[1] for bar in prior)
                        location = (last - low) / (high - low)
                        bull = low < bottom < last and location >= threshold
                        bear = high > top > last and location <= 1 - threshold
                        if bull or bear:
                            result[i, pair[0 if bull else 1]] = role
                    completed.append((high, low))
            elif family == "shock_exhaustion":
                for p in range(max(13, horizon + 1), end - start):
                    # h completed return observations at t-h,...,t-1.
                    shock = close[p - 1] - close[p - horizon - 1]
                    vol = _prior_vol(returns, p)
                    reversal = close[p] - close[p - 1]
                    if (vol > 1e-12 and abs(shock) > threshold * vol * np.sqrt(horizon)
                            and shock * reversal < 0 and abs(reversal) >= .5 * abs(shock)):
                        result[start + p, pair[1 if shock > 0 else 0]] = role
    return result
