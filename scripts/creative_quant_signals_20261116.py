"""Fixed, causal four-family research grid; no orders or execution changes.

volatility_trend follows a window return scaled by realized volatility, but
requires directional efficiency >= 0.25 to avoid noisy oscillating paths.
zscore_reversion fades unusual log-price deviations from their rolling mean.
channel_state buys breakouts of the prior close channel plus a volatility
buffer, retaining direction until price crosses the channel midpoint.
daily_hybrid follows aligned intraday momentum in a strong completed-daily
trend, and fades intraday deviations in a quiet completed-daily regime.

Daily statistics use the last observed close of each New York session and are
released at the first observed bar of the NEXT session. An incomplete first
session is therefore only a warmup observation. No current-session final close
enters its own regime. All other features include the current completed bar;
the caller must retain the engine's next-bar execution and delay semantics.

Positive scores designate the Nasdaq BUY role (TQQQ or SQQQ), and negative
scores designate the Bitcoin BUY role (IBIT or BITI). Score signs never request
borrowed shorts. Zero means cash; either role may independently be absent.
The caller must use funded_pair=True, funded_allow_single=True and enforce the
fixed 60bp stop and <=15% capital allocation per ETF. Holds/targets are exit
parameters and deliberately do not change entries. Reused 2026 is research
diagnostic data, including rolling recent-three/six-month evaluations.
"""
from itertools import product

import numpy as np
import pandas as pd


FAMILIES = ("volatility_trend", "zscore_reversion", "channel_state", "daily_hybrid")


def candidates() -> list[dict]:
    """Deterministic complete 4 x 2 x 2 x 2 x 2 grid, without random search."""
    return [
        dict(name=f"{family}_w{window}_z{threshold:g}_h{hold}_t{target}",
             family=family, window=window, threshold=threshold, hold=hold,
             target=target, stop_bps=60, max_etf_weight=.15)
        for family, window, threshold, hold, target in product(
            FAMILIES, (12, 24), (.75, 1.25), (2, 4), (2, 3))
    ]


def _daily_score(log_close: pd.DataFrame, times, window: int) -> np.ndarray:
    """Completed observed-session momentum, forward released one session later."""
    days = pd.DatetimeIndex(pd.to_datetime(times, utc=True)).tz_convert(
        "America/New_York").strftime("%Y-%m-%d")
    daily = log_close.groupby(days, sort=True).last()
    volatility = daily.diff().rolling(window).std(ddof=0).replace(0, np.nan)
    score = daily.diff(window) / (volatility * np.sqrt(window))
    return score.shift(1).reindex(days).to_numpy()


def _threshold_direction(score: np.ndarray, threshold: float) -> np.ndarray:
    return np.where(np.isfinite(score) & (np.abs(score) >= threshold),
                    np.sign(score), 0.)


def _buy_roles(directions: np.ndarray, symbols) -> np.ndarray:
    score = np.zeros((len(directions), len(symbols)), dtype=float)
    for j, (bull, bear, role) in enumerate((("TQQQ", "SQQQ", 1.),
                                           ("IBIT", "BITI", -1.))):
        score[directions[:, j] > 0, symbols.index(bull)] = role
        score[directions[:, j] < 0, symbols.index(bear)] = role
    return score


def signals(data, times, candidate) -> np.ndarray:
    """Return completed-bar independent asset directions as actual ETF buy roles."""
    symbols = tuple(data.symbols)
    if not {"TQQQ", "SQQQ", "IBIT", "BITI"}.issubset(symbols):
        raise ValueError("Actual TQQQ/SQQQ/IBIT/BITI bars are required")
    if len(times) != len(data.close):
        raise ValueError("times and close lengths differ")
    family = candidate["family"]
    if family not in FAMILIES:
        raise ValueError(f"Unknown family: {family}")
    window, threshold = int(candidate["window"]), float(candidate["threshold"])
    if window < 2 or not np.isfinite(threshold) or threshold <= 0:
        raise ValueError("window >= 2 and finite positive threshold required")
    if not len(data.close):
        return np.zeros_like(data.close, dtype=float)
    times = pd.DatetimeIndex(pd.to_datetime(times, utc=True))
    if not times.is_monotonic_increasing or times.has_duplicates:
        raise ValueError("Unique increasing completed-bar timestamps required")
    price = np.asarray(data.close)[:, [symbols.index("TQQQ"), symbols.index("IBIT")]]
    if not (np.isfinite(price).all() and (price > 0).all()):
        raise ValueError("Finite positive source closes required")
    x = pd.DataFrame(np.log(price))
    returns = x.diff()
    volatility = returns.rolling(max(48, 2 * window)).std(ddof=0).replace(0, np.nan)
    momentum = (x.diff(window) / (volatility * np.sqrt(window))).to_numpy()
    zscore = ((x - x.rolling(window).mean()) /
              x.rolling(window).std(ddof=0).replace(0, np.nan)).to_numpy()
    if family == "volatility_trend":
        efficiency = (x.diff(window).abs() /
                      returns.abs().rolling(window).sum().replace(0, np.nan)).to_numpy()
        direction = np.where(efficiency >= .25,
                             _threshold_direction(momentum, threshold), 0.)
    elif family == "zscore_reversion":
        direction = -_threshold_direction(zscore, threshold)
    elif family == "channel_state":
        upper = x.shift(1).rolling(window).max().to_numpy()
        lower = x.shift(1).rolling(window).min().to_numpy()
        middle = (upper + lower) / 2
        buffer = threshold * volatility.to_numpy()
        values = x.to_numpy()
        direction = np.zeros_like(values)
        state = np.zeros(2)
        for i in range(len(values)):
            valid = np.isfinite(buffer[i]) & np.isfinite(middle[i])
            state = np.where(valid, state, 0.)
            state = np.where((state > 0) & (values[i] < middle[i]), 0., state)
            state = np.where((state < 0) & (values[i] > middle[i]), 0., state)
            state = np.where(valid & (values[i] > upper[i] + buffer[i]), 1., state)
            state = np.where(valid & (values[i] < lower[i] - buffer[i]), -1., state)
            direction[i] = state
    else:
        daily = _daily_score(x, times, window)
        trend = _threshold_direction(momentum, threshold)
        strong = np.isfinite(daily) & (np.abs(daily) >= threshold)
        aligned = trend == np.sign(daily)
        quiet = np.isfinite(daily) & ~strong
        direction = np.where(strong & aligned, trend,
                             np.where(quiet, -_threshold_direction(zscore, threshold), 0.))
    return _buy_roles(direction, symbols)
