"""Exploratory, exclusive gap/volume routing motivated by the 2025 cohort audit.

The components are frozen: gap_absorption(.5 ATR, .6 close-location) and
volume_pressure(6 bars, 2 relative-volume). The audit found half-specific price
path complementarity, not a demonstrated portfolio edge. This grid changes
routing only; holds2/4 and targets2/3R are separate exit variants. Nothing here
raises position sizes, repeats a remembered gap as a new event, or creates an
event absent from the two source signals. Actual inverse ETFs remain purchases.

All ages count completed observed bars, with the first session bar age0. State
is independent per source asset and resets at every observed New York session.
Outputs use the just-completed bar and require next-bar execution by the caller.

* gap_reservation: emit the gap once. Suppress subsequent volume until either
  age>p1 (2/4 bars) or favorable close displacement from the gap-bar close is
  >=p2 (.25/.5) times the ATR14 available at the gap. Release is irreversible.
* pressure_takeover: emit the gap once; agreeing volume is allowed. Opposite
  volume is suppressed until p1 (2/3) opposite events occur in the last p2
  (3/6) completed same-session bars, including the current bar. At that event
  release the gap memory permanently and permit all remaining volume events.
* conflict_memory: remember the gap through age<=p1 (2/4). Opposite volume
  during this interval starts a p2 (1/3)-bar cash quarantine including the
  conflict bar. Further conflicts extend it. Agreeing volume passes outside
  quarantine; a quarantine may outlast the gap memory but never the session.
* daily_regime: E=abs(prior last close-prior first open)/(prior high-prior low).
  Route only gap if E<=p1-p2; only volume if E>=p1+p2; otherwise cash. p1 is
  .25/.4 and p2 is .05/.15. Zero prior range or no prior session means cash.
  The entire prior session statistic is released on the next observed session.

Exact signal aliases are expected for exit variants and possible for empirical
routing settings. Hash them before screening; 64 configs are not 64 independent
signal hypotheses. Sparse branches do not justify relaxing minimum samples.
"""
from hashlib import sha256
from itertools import product

import numpy as np
import pandas as pd

from microstructure_signals_20261117 import (
    _buy_roles, _prior_daily_stats, signals as component_signals,
)

FAMILIES = ("gap_reservation", "pressure_takeover", "conflict_memory", "daily_regime")
PARAMETERS = {
    "gap_reservation": ((2, 4), (.25, .5)),
    "pressure_takeover": ((2, 3), (3, 6)),
    "conflict_memory": ((2, 4), (1, 3)),
    "daily_regime": ((.25, .4), (.05, .15)),
}


def candidates():
    """64 bounded routing/exit configs, with the existing stop and capital caps."""
    return [dict(name=f"{family}_p{p1:g}_q{p2:g}_h{hold}_t{target}",
                 family=family, p1=p1, p2=p2, hold=hold, target=target,
                 stop_bps=60, max_etf_weight=.15)
            for family in FAMILIES
            for p1, p2, hold, target in product(*PARAMETERS[family], (2, 4), (2, 3))]


def signal_fingerprint(scores):
    """Exact array identity, including shape; callers retain all alias configs."""
    values = np.asarray(scores, dtype=np.int8)
    return sha256(str(values.shape).encode()+values.tobytes()).hexdigest()


def _directions(scores, symbols):
    return np.column_stack((scores[:, symbols.index("TQQQ")]-
                            scores[:, symbols.index("SQQQ")],
                            -scores[:, symbols.index("IBIT")]+
                            scores[:, symbols.index("BITI")]))


def _prior_efficiency(open_, high, low, close, times):
    """Previous observed-session range efficiency; partial current day unused."""
    days = times.tz_convert("America/New_York").strftime("%Y-%m-%d")
    result = []
    for j in range(2):
        bars = pd.DataFrame(dict(open=open_[:, j], high=high[:, j],
                                 low=low[:, j], close=close[:, j]), index=days)
        daily = bars.groupby(level=0, sort=False).agg(
            open=("open", "first"), high=("high", "max"),
            low=("low", "min"), close=("close", "last"))
        width = daily.high-daily.low
        efficiency = (daily.close-daily.open).abs()/width.where(width > 0)
        result.append(efficiency.shift(1).reindex(days).to_numpy())
    return np.column_stack(result)


def _route_directions(gap, volume, close, atr, first, efficiency, c):
    """Pure causal router on component directions; no execution/account state."""
    family, p1, p2 = c["family"], float(c["p1"]), float(c["p2"])
    if family == "daily_regime":
        return np.where(efficiency <= p1-p2, gap,
                        np.where(efficiency >= p1+p2, volume, 0.))
    result = np.zeros_like(gap)
    remembered = np.zeros(2)
    gap_index = np.full(2, -1, dtype=int)
    gap_close, gap_atr = np.zeros(2), np.zeros(2)
    blocked_until = np.full(2, -1, dtype=int)
    session_start = 0
    for i in range(len(gap)):
        if first[i]:
            remembered[:] = 0
            gap_index[:] = -1
            blocked_until[:] = -1
            session_start = i
        for j in range(2):
            g, v = gap[i, j], volume[i, j]
            if g:
                remembered[j] = g
                gap_index[j], gap_close[j], gap_atr[j] = i, close[i, j], atr[i, j]
                result[i, j] = g
                if family == "conflict_memory" and v == -g:
                    blocked_until[j] = i+int(p2)-1
                    result[i, j] = 0
                continue
            age = i-gap_index[j]
            if family == "gap_reservation" and remembered[j]:
                progress = remembered[j]*(close[i, j]-gap_close[j])
                if age > p1 or progress >= p2*gap_atr[j]:
                    remembered[j] = 0
                else:
                    continue
            elif family == "pressure_takeover" and remembered[j] and v == -remembered[j]:
                start = max(session_start, i-int(p2)+1)
                evidence = np.count_nonzero(volume[start:i+1, j] == -remembered[j])
                if evidence >= p1:
                    remembered[j] = 0
                else:
                    continue
            elif family == "conflict_memory":
                if remembered[j] and age > p1:
                    remembered[j] = 0
                if remembered[j] and v == -remembered[j]:
                    blocked_until[j] = i+int(p2)-1
                if i <= blocked_until[j]:
                    continue
            result[i, j] = v
    return result


def signals(data, times, c):
    """Return actual-ETF buy-role scores; caller uses next-bar funded execution."""
    family = c["family"]
    if family not in FAMILIES:
        raise ValueError(f"Unknown family: {family}")
    p1, p2 = float(c["p1"]), float(c["p2"])
    if p1 not in PARAMETERS[family][0] or p2 not in PARAMETERS[family][1]:
        raise ValueError("Routing parameters must belong to the bounded grid")
    # Component validation also checks symbol universe, timestamps and all OHLCV.
    times = pd.DatetimeIndex(pd.to_datetime(times, utc=True))
    gap_scores = component_signals(data, times,
                                  dict(family="gap_absorption", p1=.5, p2=.6))
    volume_scores = component_signals(data, times,
                                     dict(family="volume_pressure", p1=6, p2=2))
    if not len(times):
        return gap_scores
    symbols = tuple(data.symbols)
    source = [symbols.index("TQQQ"), symbols.index("IBIT")]
    open_, high, low, close = [np.asarray(getattr(data, k))[:, source]
                               for k in ("open", "high", "low", "close")]
    _, _, _, atr, first = _prior_daily_stats(open_, high, low, close, times)
    efficiency = _prior_efficiency(open_, high, low, close, times)
    routed = _route_directions(_directions(gap_scores, symbols),
                               _directions(volume_scores, symbols),
                               close, atr, first, efficiency, c)
    return _buy_roles(routed, symbols)
