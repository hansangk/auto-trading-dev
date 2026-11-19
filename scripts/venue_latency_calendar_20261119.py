"""Known-calendar support for fixed-minute latency comparisons.

The mask sees scheduled exchange clocks only, never future ETF rows or quotes.
At actual ETF bar start ``t`` its completed decision is min(t+60min, close),
the base entry is t+60min and delayed entry t+120min. Both planned exits use
the CLOSE of a scheduled bar and must be exactly ``duration_minutes`` after
their respective OPEN entries. Target price existence is a separate audit.

60 minutes is supported for path labels ONLY: the existing hold=1 joint_close
engine has zero intermediate protective observations. Replay authorization
belongs to the caller and is limited to 120/180 minutes in this experiment.
"""
from datetime import date, datetime
from numbers import Integral

import numpy as np
import pandas as pd

NY = 'America/New_York'
MINUTE = pd.Timedelta(minutes=1)
HOUR = pd.Timedelta(hours=1)
SUPPORTED_MINUTES = (60, 120, 180)


def _day_key(value):
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise ValueError('Schedule index must contain canonical NY dates') from exc
        if parsed.isoformat() != value:
            raise ValueError('Schedule dates must use YYYY-MM-DD')
        return value
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (pd.Timestamp, datetime)):
        parsed = pd.Timestamp(value)
        if parsed.tzinfo is not None or parsed != parsed.normalize():
            raise ValueError('Schedule date index must be timezone-free midnight')
        return parsed.date().isoformat()
    raise ValueError('Schedule index must contain NY dates')


def _aware(value, field):
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f'Schedule {field} must be a timestamp') from exc
    if pd.isna(parsed) or parsed.tzinfo is None:
        raise ValueError(f'Schedule {field} must be timezone-aware and finite')
    return parsed.tz_convert('UTC')


def common_mask(times, schedule, duration_minutes):
    """Return a boolean mask using only each timestamp and its known calendar.

    Times must be unique, increasing, timezone-aware actual RTH starts on the
    normal hourly grid. Referenced sessions must be 09:30--16:00 NY (390min).
    Unreferenced short-day calendar rows are permitted; no actual future row
    is needed, so truncating ETF ``times`` cannot change an earlier mask.
    """
    if (isinstance(duration_minutes, (bool, np.bool_))
            or not isinstance(duration_minutes, Integral)
            or int(duration_minutes) not in SUPPORTED_MINUTES):
        raise ValueError('duration_minutes must be an integer 60, 120 or 180')
    if not isinstance(schedule, pd.DataFrame) or not {'open', 'close'} <= set(schedule):
        raise ValueError('Schedule must be a DataFrame with open/close columns')
    keys = [_day_key(key) for key in schedule.index]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate NY calendar dates')
    lookup = dict(zip(keys, range(len(keys))))
    if isinstance(times, (str, bytes, pd.Timestamp, datetime, np.datetime64)):
        raise ValueError('Times must be a one-dimensional timezone-aware sequence')
    try:
        calendar = pd.DatetimeIndex(times)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('Invalid ETF timestamp sequence') from exc
    if (calendar.hasnans or calendar.has_duplicates
            or not calendar.is_monotonic_increasing or calendar.tz is None):
        raise ValueError('Times must be finite, unique, increasing and timezone-aware')
    calendar = calendar.tz_convert('UTC')
    result = np.zeros(len(calendar), dtype=bool)
    duration = int(duration_minutes) * MINUTE
    parsed = {}
    for i, t in enumerate(calendar):
        day = t.tz_convert(NY).date().isoformat()
        if day not in lookup:
            raise ValueError(f'Missing known exchange calendar for {day}')
        if day not in parsed:
            row = schedule.iloc[lookup[day]]
            opened, closed = _aware(row['open'], 'open'), _aware(row['close'], 'close')
            op_ny, cl_ny = opened.tz_convert(NY), closed.tz_convert(NY)
            if (op_ny.date().isoformat() != day or cl_ny.date().isoformat() != day
                    or op_ny.weekday() > 4 or op_ny.hour != 9 or op_ny.minute != 30
                    or op_ny.second or op_ny.microsecond or op_ny.nanosecond
                    or cl_ny.hour != 16 or cl_ny.minute or cl_ny.second
                    or cl_ny.microsecond or cl_ny.nanosecond
                    or closed - opened != 390 * MINUTE):
                raise ValueError(f'Referenced calendar session is not normal NY RTH: {day}')
            # Six complete hours followed by the real planned 30-minute tail.
            starts = {opened + k * HOUR for k in range(7)}
            close_phases = {min(start + HOUR, closed) for start in starts}
            parsed[day] = opened, closed, starts, close_phases
        opened, closed, starts, close_phases = parsed[day]
        if t not in starts:
            raise ValueError(f'ETF timestamp is not a scheduled actual bar start: {t}')
        decision = min(t + HOUR, closed)
        base_entry, delayed_entry = t + HOUR, t + 2 * HOUR
        base_exit, delayed_exit = base_entry + duration, delayed_entry + duration
        result[i] = bool(
            decision <= base_entry
            and base_entry in starts and delayed_entry in starts
            and opened <= base_entry < closed and opened <= delayed_entry < closed
            and base_exit <= closed and delayed_exit <= closed
            and base_exit in close_phases and delayed_exit in close_phases
        )
    return result
