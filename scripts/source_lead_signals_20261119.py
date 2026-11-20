"""Twelve fixed source-information controls, never learned alpha forecasts.

Times are five-minute bar STARTS; completed row k is known only at its end.
QQQ/BTC reference OHLC shape is (n,2,4), in O,H,L,C order. Source and ETF
arms differ only in feature feed. Baseline direction is current ETF momentum4/.5;
all controls admit that BUY role or cash at fixed 11:00..14:45 NY close ends.
No outcome labels, execution, fitting, price filling or cross-session history.
"""
from numbers import Integral

import numpy as np
import pandas as pd

SYMBOLS = ("TQQQ", "SQQQ", "IBIT", "BITI")
FAMILIES = ("wick_pressure", "path_chop", "vol_compression", "tail_energy")
LAGS = (0, 1, 3)
FIVE_NS = 300_000_000_000


def candidates():
    return [dict(name=f"{family}_lag{lag}", family=family, lag=lag)
            for family in FAMILIES for lag in LAGS]


def _calendar(times):
    calendar = pd.DatetimeIndex(pd.to_datetime(times, utc=True, errors="raise"))
    if calendar.hasnans or not calendar.is_monotonic_increasing or calendar.has_duplicates:
        raise ValueError("Times must be finite, unique and strictly increasing")
    local = calendar.tz_convert("America/New_York")
    minutes = local.hour.to_numpy() * 60 + local.minute.to_numpy()
    if np.any((minutes % 5 != 0) | (local.second.to_numpy() != 0)
              | (local.microsecond.to_numpy() != 0) | (local.nanosecond.to_numpy() != 0)):
        raise ValueError("Exact five-minute bar starts required")
    rth = (minutes >= 570) & (minutes < 960) & (local.dayofweek.to_numpy() < 5)
    return calendar, local, minutes, rth


def decision_mask(times):
    """Sixteen fixed wall-clock close ends: 11:00,11:15,...,14:45 NY."""
    _, _, minutes, rth = _calendar(times)
    ends = minutes + 5
    return rth & (ends >= 660) & (ends <= 885) & (ends % 15 == 0)


def _actual(data, times):
    calendar, local, minutes, rth = _calendar(times)
    if len(data.symbols) != 4 or set(data.symbols) != set(SYMBOLS):
        raise ValueError("Actual TQQQ/SQQQ/IBIT/BITI required")
    if not pd.DatetimeIndex(pd.to_datetime(data.timestamps, utc=True)).equals(calendar):
        raise ValueError("ETF timestamps must exactly match supplied times")
    bars = np.stack([np.asarray(getattr(data, key), float)
                     for key in ("open", "high", "low", "close")], axis=2)
    if bars.shape != (len(calendar), 4, 4):
        raise ValueError("ETF OHLC must have shape (n,4)")
    return calendar, local, minutes, rth, bars


def _valid(bars):
    o, h, l, c = (bars[..., k] for k in range(4))
    return (np.isfinite(bars).all(axis=-1) & (bars > 0).all(axis=-1)
            & (h >= np.maximum.reduce([o, l, c]))
            & (l <= np.minimum.reduce([o, h, c])))


def _segments(calendar, valid):
    days = calendar.tz_convert("America/New_York").date
    begin = None
    for i in range(len(calendar)):
        contiguous = (i > 0 and days[i] == days[i - 1]
                      and calendar.asi8[i] - calendar.asi8[i - 1] == FIVE_NS)
        if begin is not None and (not valid[i] or not contiguous):
            yield begin, i
            begin = None
        if valid[i] and begin is None:
            begin = i
    if begin is not None:
        yield begin, len(calendar)


def baseline_scores(data, times):
    """Original momentum4/.5 restricted to the fixed opportunity clock.

    Uses four prior completed 15-minute bullish-ETF bars, current completed
    15-minute close, and mean prior H-L. Histories reset on missing clocks.
    Actual input symbol order is respected, including inverse BUY columns.
    """
    calendar, _, minutes, rth, bars = _actual(data, times)
    result = np.zeros((len(calendar), 4))
    valid = _valid(bars) & rth[:, None]
    clock = decision_mask(times)
    for bull, bear, role in (("TQQQ", "SQQQ", 1.), ("IBIT", "BITI", -1.)):
        j, inverse = data.symbols.index(bull), data.symbols.index(bear)
        for start, end in _segments(calendar, valid[:, j]):
            completed = []
            for i in range(start, end):
                if i - start < 2 or (minutes[i] + 5) % 15:
                    continue
                triple = bars[i - 2:i + 1, j]
                high, low, close = triple[:, 1].max(), triple[:, 2].min(), triple[-1, 3]
                if len(completed) >= 4 and clock[i]:
                    prior = completed[-4:]
                    width = np.mean([p[0] - p[1] for p in prior])
                    move = close - prior[0][2]
                    if width > 0 and abs(move) > .5 * width:
                        target = j if move > 0 else inverse
                        if valid[i, target]:
                            result[i, target] = role
                completed.append((high, low, close))
    return result


def feature_values(data, times, refs, c, feed="source"):
    """Past-only n×4 feature values in each actual BUY ticker's orientation.

    CLV and tail-energy reverse source sign for inverse tickers; chop and
    compression are direction neutral. ETF feed always uses native ETF OHLC.
    A missing endpoint/history yields NaN. Lag applies identically to both arms.
    """
    if (c.get("family") not in FAMILIES or not isinstance(c.get("lag"), Integral)
            or c.get("lag") not in LAGS or isinstance(c.get("lag"), (bool, np.bool_))):
        raise ValueError("Unknown fixed family/lag")
    if feed not in ("source", "ETF"):
        raise ValueError("feed must be source or ETF")
    calendar, local, _, rth, actual = _actual(data, times)
    source = np.asarray(refs, float)
    if source.shape != (len(calendar), 2, 4):
        raise ValueError("Reference OHLC must have shape (n,2,4)")
    family, lag = c["family"], c["lag"]
    out = np.full((len(calendar), 4), np.nan)
    days = local.date
    for j, symbol in enumerate(data.symbols):
        reference = 0 if symbol in ("TQQQ", "SQQQ") else 1
        bars = source[:, reference] if feed == "source" else actual[:, j]
        orientation = -1. if feed == "source" and symbol in ("SQQQ", "BITI") else 1.
        valid = _valid(bars) & rth
        for start, end in _segments(calendar, valid):
            for u in range(start, end):
                target = u + lag
                if (target >= len(calendar) or not rth[target] or days[target] != days[u]
                        or calendar.asi8[target] - calendar.asi8[u] != lag * FIVE_NS):
                    continue
                if family == "wick_pressure":
                    if u - start < 2:
                        continue
                    window = bars[u - 2:u + 1]
                    width = window[:, 1] - window[:, 2]
                    clv = np.divide(2 * window[:, 3] - window[:, 1] - window[:, 2], width,
                                    out=np.zeros(3), where=width > 0)
                    value = orientation * float(clv.mean())
                else:
                    if u - start < 12:
                        continue
                    returns = np.diff(np.log(bars[u - 12:u + 1, 3]))
                    if family == "path_chop":
                        if np.count_nonzero(returns) < 10:
                            continue
                        # Fixed denominator11: a zero product is not a reversal.
                        value = float(np.count_nonzero(returns[1:] * returns[:-1] < 0) / 11)
                    elif family == "vol_compression":
                        denominator = np.mean(returns[:8] ** 2)
                        if denominator <= 0:
                            continue
                        value = float(np.sqrt(np.mean(returns[8:] ** 2) / denominator))
                    else:
                        denominator = np.sum(returns ** 2)
                        if denominator <= 0:
                            continue
                        value = orientation * float(np.sum(returns * np.abs(returns)) / denominator)
                out[target, j] = value
    return out


def filter_scores(data, times, refs, c, feed="source"):
    values = feature_values(data, times, refs, c, feed)
    family = c["family"]
    if family == "wick_pressure":
        admit = values > 0
    elif family == "path_chop":
        admit = values <= 1 / 3
    elif family == "vol_compression":
        admit = values <= 1
    else:
        admit = values > 1 / 4
    return np.where(np.isfinite(values) & admit, baseline_scores(data, times), 0.)
