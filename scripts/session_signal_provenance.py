"""Calendar-only signal eligibility for the engine's delayed entry mapping."""

from numbers import Integral

import numpy as np
import pandas as pd


def mask_session_signals(scores, times, delay, origin_lag=0, policy="score"):
    """Return a copy with signals unable to execute in their session zeroed.

    Score row ``k`` executes at row ``k + 1 + delay``.  With ``policy='score'``,
    those two rows must share a New York date.  With ``policy='event'``, the
    original event row ``k - origin_lag`` must also exist and share that date.
    ``origin_lag`` describes a signal-array shift, independently of engine delay.

    Only timestamps are inspected; no future OHLCV is used.  Rows whose entry
    is outside the supplied calendar are zeroed.  Thus appending timestamps can
    change the old trailing ``1 + delay`` rows, whose executions were unknown;
    decisions with an already-known entry row remain prefix invariant.
    """
    for name, value in (("delay", delay), ("origin_lag", origin_lag)):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral) or value < 0:
            raise ValueError(f"{name} must be a nonnegative integer")
    if policy not in {"score", "event"}:
        raise ValueError("policy must be 'score' or 'event'")
    result = np.array(scores, copy=True)
    if result.ndim != 2:
        raise ValueError("scores must be a two-dimensional array")
    calendar = np.asarray(times)
    if calendar.ndim != 1 or len(calendar) != len(result):
        raise ValueError("times must be one-dimensional and match score rows")
    timestamps = pd.DatetimeIndex(pd.to_datetime(times, utc=True, errors="raise"))
    if timestamps.hasnans:
        raise ValueError("times must not contain missing timestamps")
    days = timestamps.tz_convert("America/New_York").date
    known = max(0, len(result) - 1 - int(delay))
    keep = np.zeros(len(result), dtype=bool)
    indices = np.arange(known)
    keep[indices] = days[indices] == days[indices + 1 + int(delay)]
    if policy == "event":
        origins = indices - int(origin_lag)
        valid = origins >= 0
        event_keep = np.zeros(len(result), dtype=bool)
        event_keep[indices[valid]] = days[origins[valid]] == days[indices[valid]]
        keep &= event_keep
    result[~keep] = 0
    return result
