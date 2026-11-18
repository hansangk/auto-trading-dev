"""Sixteen causal event-entry variants on actual five-minute ETF OHLC.

Inputs are regular-session five-minute starts; the runner supplies complete 78-row
sessions. Prefixes are also supported for causality checks. Fifteen-minute bars
are observable only at their third five-minute close. Every nonzero score is a
buy of the named ETF (including SQQQ/BITI), for execution at the next open.
"""
from itertools import product

import numpy as np
import pandas as pd

PARAMETERS = {
    "onset": ((1, 2), (0, 3)),
    "retest": ((.25, .5), (1, 2)),
    "compression": ((.5, .75), (4, 8)),
    "chasecancel": ((1, 3), (.25, .5)),
}
FAMILIES = tuple(PARAMETERS)
PAIRS = (("TQQQ", "SQQQ", 1), ("IBIT", "BITI", -1))


def candidates():
    return [dict(name=f"{family}_{a}_{b}", family=family, a=a, b=b)
            for family, values in PARAMETERS.items() for a, b in product(*values)]


def _episode_start(direction, state, neutral_rearm=1):
    """Call only on completed decisions: unobserved five-minute gaps are not neutral."""
    if direction == 0:
        state["neutral"] += 1
        return False
    fresh = (state["direction"] != direction or
             state["neutral"] >= neutral_rearm)
    state["direction"] = direction
    state["neutral"] = 0
    return fresh


def _momentum_direction(prior, close, source):
    if len(prior) < 4:
        return 0
    width = np.mean([bar[0][source] - bar[1][source] for bar in prior[-4:]])
    if width <= 0:
        return 0
    move = close - prior[-4][2][source]
    return int(move > .5 * width) - int(move < -.5 * width)


def signals(data, times, c):
    family, a, b = c["family"], c["a"], c["b"]
    if family not in PARAMETERS or a not in PARAMETERS[family][0] or b not in PARAMETERS[family][1]:
        raise ValueError("Unknown episode candidate")
    times = pd.DatetimeIndex(times)
    if times.tz is None or not times.is_monotonic_increasing or times.has_duplicates:
        raise ValueError("Unique increasing timezone-aware timestamps required")
    symbols = tuple(data.symbols)
    if set(symbols) != {"TQQQ", "SQQQ", "IBIT", "BITI"} or len(symbols) != 4:
        raise ValueError("Actual TQQQ/SQQQ/IBIT/BITI inputs required")
    shape = (len(times), len(symbols))
    if any(getattr(data, field).shape != shape for field in ("open", "high", "low", "close")):
        raise ValueError("OHLC and timestamp shapes differ")
    result = np.zeros(shape, dtype=float)
    local = times.tz_convert("America/New_York")
    slots = (local.hour * 60 + local.minute - 570) // 5
    if np.any((slots < 0) | (slots >= 78) | (local.minute % 5 != 0)):
        raise ValueError("Regular-session five-minute starts required")
    pairs = [(symbols.index(up), symbols.index(down), role) for up, down, role in PAIRS]
    for _, group in pd.Series(np.arange(len(times))).groupby(local.date):
        ix = group.to_numpy()
        bars = []  # (high[4], low[4], close[4]), all completed and same session
        states = [dict(direction=0, neutral=0, last=-1000, pending=None,
                       box=None, compression_ready=True) for _ in pairs]
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
            for state, (up, down, role) in zip(states, pairs):
                if decision:
                    if family == "compression":
                        lookback = int(b)
                        compact = False
                        if len(bars) >= lookback + 2:
                            reference = np.median([x[0][up]-x[1][up]
                                                   for x in bars[-lookback-2:-2]])
                            compact = (reference > 0 and np.mean([
                                x[0][up]-x[1][up] for x in bars[-2:]]) <= a * reference)
                        if not compact:
                            state["compression_ready"] = True
                        if state["box"] is None and compact and state["compression_ready"]:
                            state["box"] = (max(x[0][up] for x in bars[-2:]),
                                            min(x[1][up] for x in bars[-2:]))
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
                        fresh = _episode_start(direction, state, int(a) if family == "onset" else 1)
                        if fresh:
                            selected = up if direction > 0 else down
                            if family == "onset":
                                # Refractory N blocks the next N five-minute bars.
                                if slot - state["last"] > b and slot < 77:
                                    result[i, selected] = role
                                    state["last"] = slot
                            else:
                                width = bars[-1][0][selected] - bars[-1][1][selected]
                                state["pending"] = dict(symbol=selected, start=slot,
                                                        anchor=data.close[i, selected],
                                                        width=width, armed=False)
                pending = state["pending"]
                if pending is not None and slot > pending["start"]:
                    age = slot - pending["start"]
                    selected = pending["symbol"]
                    if family == "chasecancel":
                        if age >= a:
                            if age == a and pending["width"] > 0 and slot < 77 and data.close[i, selected] <= pending["anchor"] + b * pending["width"]:
                                result[i, selected] = role
                            state["pending"] = None
                    elif family == "retest":
                        if age > 3 * b or pending["width"] <= 0:
                            state["pending"] = None
                        else:
                            # A bar that first touches the excursion AND reclaims
                            # is ambiguous: its intrabar ordering is unknown.
                            if pending["armed"] and data.close[i, selected] >= pending["anchor"]:
                                if slot < 77:
                                    result[i, selected] = role
                                state["pending"] = None
                            elif data.low[i, selected] <= pending["anchor"] - a * pending["width"]:
                                pending["armed"] = True
            if current is not None:
                bars.append(current)
    return result
