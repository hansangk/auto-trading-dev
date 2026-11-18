"""Frozen latency controls and unprotected, same-event actual-ETF labels.

Calendar masks use only the original event clock. Price-path labels are neither
signals nor portfolio returns; account replay retains the existing protections.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SCHEDULES = {"A": (4, 0), "B": (4, 1), "C": (3, 1), "D": (3, 0)}
FUTURE_ALPHA_PROPOSALS = [
    {"name": "auction_repricing", "requires": "Actual opening-auction and contemporaneous quote histories"},
    {"name": "futures_cash_lead", "requires": "Synchronized completed Nasdaq-futures/cash feeds and release timestamps"},
    {"name": "macro_surprise", "requires": "Point-in-time releases and contemporaneous consensus histories"},
    {"name": "liquidity_timing", "requires": "Actual finer bars/quotes for spread and executable-delay attribution"},
]
for _proposal in FUTURE_ALPHA_PROPOSALS:
    _proposal.update(status="UNIMPLEMENTED", actual_point_in_time_feeds=False)


def configurations() -> list[dict]:
    """Sixteen controls, not sixteen independent alpha strategies."""
    return [dict(name=f"{family}_{policy}_{cohort}", family=family, hold=hold,
                 delay=delay, policy=policy, cohort=cohort)
            for family, (hold, delay) in SCHEDULES.items()
            for policy in ("source", "parent") for cohort in ("native", "common")]


def _calendar(times):
    utc = pd.DatetimeIndex(pd.to_datetime(times, utc=True))
    if utc.hasnans or utc.has_duplicates or not utc.is_monotonic_increasing:
        raise ValueError("Timestamps must be finite, unique and increasing")
    ny = utc.tz_convert("America/New_York")
    minutes = np.asarray(ny.hour * 60 + ny.minute)
    if np.any(~np.isin(minutes, np.arange(570, 931, 60))) or np.any(ny.second) or np.any(ny.microsecond) or np.any(ny.nanosecond):
        raise ValueError("Only exact normal-RTH hourly starts 09:30 through 15:30 are supported")
    days = np.asarray(ny.strftime("%Y-%m-%d"))
    for j in range(len(ny)):
        first = j == 0 or days[j] != days[j - 1]
        if first and minutes[j] != 570:
            raise ValueError("Missing opening bar in a normal session")
        if not first and minutes[j] != minutes[j - 1] + 60:
            raise ValueError("Missing hourly bar within a normal session")
        if first and j and minutes[j - 1] != 930:
            raise ValueError("Missing closing bar in an earlier normal session")
    return utc, ny, days, (minutes - 570) // 60


def cohort_scores(scores, times, cohort) -> np.ndarray:
    """Copy scores; common support is known at event time, including on prefixes.

    The normal-session calendar admits ordinals0/1. It does not inspect later
    rows, prices, or eventual session completeness. The input audit is responsible
    for excluding incomplete/short sessions before account replay.
    """
    values = np.asarray(scores)
    if values.shape != (len(times), 4):
        raise ValueError("Scores must have shape (number of timestamps, 4)")
    result = values.copy()
    if cohort == "native":
        return result
    if cohort not in {"common", "common_full4_delay", "commonfull4+delay"}:
        raise ValueError("Unknown cohort")
    _, _, _, ordinal = _calendar(times)
    result[ordinal > 1] = 0
    return result


def schedule(data_times, k, hold, delay) -> dict | None:
    """Actual open/close endpoints, clipped to the last bar of the same NY day.

    Missing or off-clock sessions raise rather than treating missing bars as
    shorter normal sessions. No delayed entry after the session is fabricated.
    """
    if not isinstance(hold, (int, np.integer)) or hold < 1 or not isinstance(delay, (int, np.integer)) or delay < 0:
        raise ValueError("Hold must be a positive integer and delay a nonnegative integer")
    utc, ny, days, _ = _calendar(data_times)
    return _schedule_from_calendar(utc, ny, days, k, hold, delay)


def _schedule_from_calendar(utc, ny, days, k, hold, delay):
    if not isinstance(k, (int, np.integer)) or not 0 <= k < len(utc):
        raise IndexError("Event index outside timestamps")
    positions = np.flatnonzero(days == days[k])
    if len(positions) != 7:
        raise ValueError("Price-path labels require all seven normal-session bars")
    last = int(positions[-1])
    entry = int(k + 1 + delay)
    if entry > last:
        return None
    requested_exit = entry + int(hold) - 1
    end = min(requested_exit, last)
    close_time = min(ny[end] + pd.Timedelta(hours=1), ny[end].normalize() + pd.Timedelta(hours=16))
    duration = float((close_time - ny[entry]).total_seconds() / 60)
    return dict(entry_index=entry, exit_index=int(end), entry_time=utc[entry],
                exit_time=close_time.tz_convert("UTC"), duration_minutes=duration,
                clipped=bool(end < requested_exit), full_bar_count=bool(end - entry + 1 == hold),
                bar_count=int(end - entry + 1), full_hour_bars=bool(duration == 60 * (end - entry + 1)))


def rawpaired_labels(data, times, k, symbol_index) -> dict:
    """Freeze one original ETF; never negate its bullish counterpart's return."""
    if np.shape(data.open) != np.shape(data.close) or len(data.open) != len(times):
        raise ValueError("Price arrays and timestamps must align")
    if not isinstance(symbol_index, (int, np.integer)) or not 0 <= symbol_index < data.open.shape[1]:
        raise IndexError("ETF symbol index outside price arrays")
    if not pd.DatetimeIndex(pd.to_datetime(data.timestamps, utc=True)).equals(pd.DatetimeIndex(pd.to_datetime(times, utc=True))):
        raise ValueError("Supplied timestamps differ from price timestamps")
    utc, ny, days, _ = _calendar(times)
    labels = {}
    for family, (hold, delay) in SCHEDULES.items():
        cell = _schedule_from_calendar(utc, ny, days, k, hold, delay)
        if cell is not None:
            entry = float(data.open[cell["entry_index"], symbol_index])
            exit_price = float(data.close[cell["exit_index"], symbol_index])
            if not np.isfinite([entry, exit_price]).all() or min(entry, exit_price) <= 0:
                raise ValueError("Actual ETF endpoint prices must be finite and positive")
            cell.update(gross_return=exit_price / entry - 1, entry_price=entry, exit_price=exit_price)
        labels[family] = cell
    a, b, c, d = (labels[x] for x in "ABCD")
    labels.update(
        sameexitA_C=bool(a is not None and c is not None and a["exit_time"] == c["exit_time"]),
        equalbarsA_B=bool(a is not None and b is not None and a["bar_count"] == b["bar_count"] == 4),
        equalwall4A_B=bool(a is not None and b is not None and a["duration_minutes"] == b["duration_minutes"] == 240),
        equalwall3D_C=bool(d is not None and c is not None and d["duration_minutes"] == c["duration_minutes"] == 180),
    )
    return labels
