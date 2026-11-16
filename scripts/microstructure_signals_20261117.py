"""Causal OHLCV research grid; caller executes after each completed bar.

All four actual ETF price paths are supplied and kept intact. TQQQ and IBIT
OHLCV are direction proxies; bullish/bearish directions select actual buys of
TQQQ/SQQQ (positive role) or IBIT/BITI (negative role). A negative role is not
a short. Either asset may independently remain in cash. Use next-bar execution,
funded_pair=True, funded_allow_single=True, fixed 60bp stops and <=15% per ETF.

Sessions are observed New York calendar dates. Daily high/low/last close and
true range are released only on the next observed session. ATR is the arithmetic
mean of the preceding 14 completed observed sessions' true ranges, requiring
14 valid true ranges (and an earlier close). Missing sessions are not invented;
source completeness and exchange-calendar validation remain caller concerns.

* gap_absorption: first completed bar only; abs(open-prior close)/prior ATR
  >=p1, opposing candle body, and reversal close-location >=p2. Fade the gap.
* volume_pressure: v/current prior-p1-bar mean volume is relative volume.
  Average (close-open)/(high-low)*relative volume over p1 completed bars;
  follow its sign if current relative volume >=p2 and current body agrees.
* cross_response: x=lag-p1 TQQQ log return, y=current IBIT log return. Fit an
  intercept and beta using only the preceding24 (x,y) pairs. Follow the sign of
  (predicted y-y)/prior residual std when its magnitude >=p2. Bitcoin role only.
* failed_breakout: prior-session high/low plus/minus p1*prior ATR arms a fade.
  A close inside the prior-session range on the penetration bar or within p2
  subsequent completed bars fires once. Timeout and arms reset each session;
  rearming requires a fresh threshold crossing, not persistent penetration.
  Simultaneous opposite rejection events are cash, avoiding arbitrary OHLC order.

Holds/targets affect exits only. No news, sentiment, current-session final OHLC,
future volumes, inverse-return synthesis, orders, or execution modifications.
"""
from itertools import product

import numpy as np
import pandas as pd

FAMILIES = ("gap_absorption", "volume_pressure", "cross_response", "failed_breakout")
PARAMETERS = {
    "gap_absorption": ((.5, 1.), (.6, .8)),
    "volume_pressure": ((6, 12), (1.5, 2.)),
    "cross_response": ((1, 2), (.75, 1.25)),
    "failed_breakout": ((.25, .5), (1, 2)),
}


def candidates() -> list[dict]:
    """Exactly64 preregistered combinations; no exit-dependent entry changes."""
    return [dict(name=f"{family}_p{p1:g}_q{p2:g}_h{hold}_t{target}",
                 family=family, p1=p1, p2=p2, hold=hold, target=target,
                 stop_bps=60, max_etf_weight=.15)
            for family in FAMILIES
            for p1, p2, hold, target in product(*PARAMETERS[family], (2, 4), (2, 3))]


def _buy_roles(directions, symbols):
    """Map directional beliefs to actual instruments, in supplied column order."""
    result = np.zeros((len(directions), len(symbols)), dtype=float)
    for j, (bull, bear, role) in enumerate((("TQQQ", "SQQQ", 1.),
                                          ("IBIT", "BITI", -1.))):
        result[directions[:, j] > 0, symbols.index(bull)] = role
        result[directions[:, j] < 0, symbols.index(bear)] = role
    return result


def _prior_daily_stats(open_, high, low, close, times):
    """Return previous observed-session close/high/low, ATR14 and first-bar mask."""
    days = times.tz_convert("America/New_York").strftime("%Y-%m-%d")
    prior = []
    for j in range(2):
        bars = pd.DataFrame(dict(high=high[:, j], low=low[:, j], close=close[:, j]),
                            index=days)
        daily = bars.groupby(level=0, sort=False).agg(
            high=("high", "max"), low=("low", "min"), close=("close", "last"))
        previous_close = daily.close.shift(1)
        true_range = pd.concat((daily.high-daily.low,
                                (daily.high-previous_close).abs(),
                                (daily.low-previous_close).abs()), axis=1).max(axis=1)
        # The first observed session has no prior close and is warmup only.
        true_range.loc[previous_close.isna()] = np.nan
        daily["atr"] = true_range.rolling(14, min_periods=14).mean()
        prior.append(daily.shift(1).reindex(days).to_numpy())
    values = np.stack(prior, axis=2)
    first = np.r_[True, np.asarray(days[1:] != days[:-1])]
    return values[:, 2], values[:, 0], values[:, 1], values[:, 3], first


def _cross_direction(close, lag, threshold):
    """OLS and residual scale use strictly prior24 complete response pairs."""
    returns = pd.DataFrame(np.log(close)).diff()
    x, y = returns[0].shift(lag), returns[1]
    prior_x, prior_y = x.shift(1), y.shift(1)
    mx, my = prior_x.rolling(24).mean(), prior_y.rolling(24).mean()
    vx = prior_x.rolling(24).var(ddof=0)
    vy = prior_y.rolling(24).var(ddof=0)
    covariance = prior_x.rolling(24).cov(prior_y, ddof=0)
    beta = covariance / vx.where(vx > 0)
    residual_variance = (vy-covariance*beta).clip(lower=0)
    scale = np.sqrt(residual_variance)
    # Avoid spurious huge z-scores from floating point cancellation of exact fits.
    scale = scale.where(residual_variance > np.maximum(vy, 1.e-30)*1.e-10)
    z = ((my + beta*(x-mx)-y)/scale).to_numpy()
    direction = np.zeros_like(close)
    direction[:, 1] = np.where(np.isfinite(z) & (np.abs(z) >= threshold),
                                np.sign(z), 0.)
    return direction


def _failed_direction(high, low, close, prior_high, prior_low, atr, first, p1, timeout):
    result = np.zeros_like(close)
    armed = np.full((2, 2), -1, dtype=int)  # source, upper/lower; -1=unarmed
    was_beyond = np.zeros((2, 2), dtype=bool)
    for i in range(len(close)):
        if first[i]:
            armed[:] = -1
            was_beyond[:] = False
        for j in range(2):
            valid = np.isfinite(atr[i, j]) and atr[i, j] > 0
            if not valid:
                continue
            beyond = np.array([high[i, j] >= prior_high[i, j]+p1*atr[i, j],
                               low[i, j] <= prior_low[i, j]-p1*atr[i, j]])
            expired = (armed[j] >= 0) & (i-armed[j] > timeout)
            armed[j, expired] = -1
            fresh = beyond & ~was_beyond[j] & (armed[j] < 0)
            armed[j, fresh] = i
            inside = prior_low[i, j] <= close[i, j] <= prior_high[i, j]
            fired = (armed[j] >= 0) & inside
            if fired.sum() == 1:
                result[i, j] = -1. if fired[0] else 1.
            armed[j, fired] = -1
            was_beyond[j] = beyond
    return result


def signals(data, times, c) -> np.ndarray:
    """Return n×4 buy-role scores in data.symbols order, using completed bars."""
    symbols = tuple(data.symbols)
    if len(symbols) != 4 or set(symbols) != {"TQQQ", "SQQQ", "IBIT", "BITI"}:
        raise ValueError("Exactly the four actual TQQQ/SQQQ/IBIT/BITI ETFs required")
    family = c["family"]
    if family not in FAMILIES:
        raise ValueError(f"Unknown family: {family}")
    p1, p2 = float(c["p1"]), float(c["p2"])
    if p1 not in PARAMETERS[family][0] or p2 not in PARAMETERS[family][1]:
        raise ValueError("Signal parameters must belong to the bounded family grid")
    times = pd.DatetimeIndex(pd.to_datetime(times, utc=True))
    if len(times) != len(data.close):
        raise ValueError("times and close lengths differ")
    if not times.is_monotonic_increasing or times.has_duplicates or times.hasnans:
        raise ValueError("Unique increasing completed-bar timestamps required")
    arrays = [np.asarray(getattr(data, key), dtype=float)
              for key in ("open", "high", "low", "close", "volume")]
    if any(a.shape != (len(times), 4) for a in arrays):
        raise ValueError("OHLCV must share the n×4 shape")
    if any(not np.isfinite(a).all() for a in arrays):
        raise ValueError("Finite OHLCV required")
    if any(np.any(a <= 0) for a in arrays[:4]) or np.any(arrays[4] < 0):
        raise ValueError("Positive prices and nonnegative volume required")
    if np.any(arrays[1] < np.maximum.reduce(arrays[:4])) or np.any(
            arrays[2] > np.minimum.reduce(arrays[:4])):
        raise ValueError("Invalid OHLC ranges")
    if not len(times):
        return np.zeros((0, 4), dtype=float)
    source = [symbols.index("TQQQ"), symbols.index("IBIT")]
    open_, high, low, close, volume = [a[:, source] for a in arrays]
    if family == "cross_response":
        direction = _cross_direction(close, int(p1), p2)
    elif family == "volume_pressure":
        denominator = pd.DataFrame(volume).shift(1).rolling(int(p1)).mean()
        relative = pd.DataFrame(volume)/denominator.where(denominator > 0)
        body = np.divide(close-open_, high-low, out=np.zeros_like(close),
                         where=high > low)
        pressure = (pd.DataFrame(body)*relative).rolling(int(p1)).mean().to_numpy()
        direction = np.where((relative.to_numpy() >= p2) &
                             np.isfinite(pressure) & (pressure*body > 0),
                             np.sign(pressure), 0.)
    else:
        prior_close, prior_high, prior_low, atr, first = _prior_daily_stats(
            open_, high, low, close, times)
        if family == "gap_absorption":
            gap = open_-prior_close
            location = np.divide(close-low, high-low, out=np.full_like(close, np.nan),
                                 where=high > low)
            valid = first[:, None] & np.isfinite(atr) & (atr > 0)
            down = valid & (gap <= -p1*atr) & (close > open_) & (location >= p2)
            up = valid & (gap >= p1*atr) & (close < open_) & (location <= 1-p2)
            direction = down.astype(float)-up.astype(float)
        else:
            direction = _failed_direction(high, low, close, prior_high, prior_low,
                                          atr, first, p1, int(p2))
    return _buy_roles(direction, symbols)
