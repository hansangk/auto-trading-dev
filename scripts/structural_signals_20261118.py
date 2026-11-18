"""Sixteen causal structural repairs, on actual five-minute ETF buy roles.

Compression uses the original .75 / four-reference-bar box, with a bounded
lifetime (including its arm decision) and optional decompression invalidation.
Adverse chase retains the original one-event pending state and caps; its new
floor is tested at the same waiting close. Confirmation and participation only
filter the frozen momentum(4, .5) decision, never move its timestamp. Execution
remains the caller's next open. Participation needs complete same-slot history
in the preceding N observed sessions; the current session never enters it.
"""
from itertools import product

import numpy as np
import pandas as pd

from episode_signals_20261118 import (
    PAIRS, _episode_start, _momentum_direction, signals as episode_signals,
)

PARAMETERS = {
    "compression_expiry": ((1, 3), (0, 1)),
    "adverse_chase": ((1, 3), (.25, .75)),
    "own_confirmation": ((1, 3), (0., .25)),
    "participation": ((5, 10), (.2, .4)),
}
FAMILIES = tuple(PARAMETERS)


def candidates():
    return [dict(name=f"{family}_{a}_{b}", family=family, a=a, b=b)
            for family, values in PARAMETERS.items() for a, b in product(*values)]


def signals(data, times, c):
    family, a, b = c["family"], c["a"], c["b"]
    if (family not in PARAMETERS or a not in PARAMETERS[family][0]
            or b not in PARAMETERS[family][1]):
        raise ValueError("Unknown structural candidate")
    times = pd.DatetimeIndex(times)
    if times.tz is None or not times.is_monotonic_increasing or times.has_duplicates:
        raise ValueError("Unique increasing timezone-aware timestamps required")
    symbols = tuple(data.symbols)
    if len(symbols) != 4 or set(symbols) != {"TQQQ", "SQQQ", "IBIT", "BITI"}:
        raise ValueError("Actual TQQQ/SQQQ/IBIT/BITI inputs required")
    shape = (len(times), len(symbols))
    if any(getattr(data, field).shape != shape
           for field in ("open", "high", "low", "close", "volume")):
        raise ValueError("OHLCV and timestamp shapes differ")
    result = np.zeros(shape, dtype=float)
    local = times.tz_convert("America/New_York")
    slots = (local.hour * 60 + local.minute - 570) // 5
    if np.any((slots < 0) | (slots >= 78) | (local.minute % 5 != 0)):
        raise ValueError("Regular-session five-minute starts required")
    pairs = [(symbols.index(up), symbols.index(down), role)
             for up, down, role in PAIRS]
    history = []  # Prior observed sessions only: {completed slot: dollar volume[4]}.
    for _, group in pd.Series(np.arange(len(times))).groupby(local.date):
        ix = group.to_numpy()
        bars = []
        session_volume = {}
        states = [dict(direction=0, neutral=0, pending=None, box=None,
                       box_age=0, compression_ready=True) for _ in pairs]
        for pos, i in enumerate(ix):
            slot = int(slots[i])
            decision = (slot % 3 == 2 and pos >= 2 and
                        np.array_equal(np.asarray(slots[ix[pos-2:pos+1]]),
                                       np.arange(slot-2, slot+1)))
            current = None
            if decision:
                triple = ix[pos-2:pos+1]
                current = (data.high[triple].max(axis=0),
                           data.low[triple].min(axis=0), data.close[i])
                session_volume[slot] = (data.close[triple] * data.volume[triple]).sum(axis=0)
            for state, (up, down, role) in zip(states, pairs):
                if decision:
                    if family == "compression_expiry":
                        compact = False
                        if len(bars) >= 6:
                            reference = np.median([x[0][up]-x[1][up]
                                                   for x in bars[-6:-2]])
                            compact = (reference > 0 and np.mean([
                                x[0][up]-x[1][up] for x in bars[-2:]]) <= .75 * reference)
                        if not compact:
                            state["compression_ready"] = True
                        if state["box"] is not None:
                            state["box_age"] += 1
                            if state["box_age"] >= a or (b and not compact):
                                state["box"] = None
                        if state["box"] is None and compact and state["compression_ready"]:
                            state["box"] = (max(x[0][up] for x in bars[-2:]),
                                            min(x[1][up] for x in bars[-2:]))
                            state["box_age"] = 0
                            state["compression_ready"] = False
                        if state["box"] is not None:
                            top, bottom = state["box"]
                            direction = int(data.close[i, up] > top) - int(data.close[i, up] < bottom)
                            if direction:
                                if slot < 77:
                                    result[i, up if direction > 0 else down] = role
                                state["box"] = None
                    else:
                        direction = _momentum_direction(bars, data.close[i, up], up)
                        if family == "adverse_chase":
                            if _episode_start(direction, state):
                                selected = up if direction > 0 else down
                                state["pending"] = dict(symbol=selected, start=slot,
                                    anchor=data.close[i, selected],
                                    width=bars[-1][0][selected]-bars[-1][1][selected])
                        elif direction and slot < 77:
                            selected = up if direction > 0 else down
                            if family == "own_confirmation":
                                width = bars[-1][0][selected]-bars[-1][1][selected]
                                admitted = (data.close[i, selected]
                                            - data.open[ix[pos-int(a)+1], selected] >= b * width)
                            else:
                                prior = history[-int(a):]
                                admitted = False
                                if len(prior) == a and all(slot in day for day in prior):
                                    threshold = np.quantile([day[slot][selected] for day in prior], b)
                                    admitted = session_volume[slot][selected] >= threshold
                            if admitted:
                                result[i, selected] = role
                pending = state["pending"]
                if pending is not None and slot > pending["start"]:
                    age = slot-pending["start"]
                    if age >= a:
                        selected, width = pending["symbol"], pending["width"]
                        upper = .25 if a == 1 else .5
                        if (age == a and width > 0 and slot < 77
                                and pending["anchor"]-b*width <= data.close[i, selected]
                                <= pending["anchor"]+upper*width):
                            result[i, selected] = role
                        state["pending"] = None
            if current is not None:
                bars.append(current)
        history.append(session_volume)
        # Only the largest prespecified window is needed; no future day enters it.
        if len(history) > 10:
            del history[0]
    return result
