"""Sixteen preregistered hourly night-information hypotheses; no execution/fitting.

``times`` are actual ETF bar STARTS, exactly aligned with ``data.timestamps``.
Each ctx row is computed by the caller at that bar's audited completion. The
caller owns PIT source joins (end+5min <= decision; dynamic age <=65min), actual
session calendars, complete history/missing-hour resets, and same-session NEXT
entry eligibility. This module never creates bars, interpolates prices or joins
QQQ :30 starts to BTC :00 starts. ``valid`` must include those common eligibility
requirements, identically for source/control arms. Prior-session regime and
frozen night-anchor ages are intentional and separately audited by the caller.

All return inputs are log returns. night_return is actual BTC prior official
ETF close -> latest actual BTC end <= current RTH open. night_scale is preceding
480-return RMS * sqrt(actual night hours). btc_vol480 is preceding 480-return
RMS at the decision. btc_trend24/48 span actual completed contiguous wall-clock
hours. btc_pullback1/3 contain only actual completed bars STARTING >= RTH open;
NaN until ready. qqq_regime5/10 use prior completed normal daily closes;
qqq_rth is the current session's latest completed QQQ hourly log return.
ibit_gap/qqq_gap are current actual first open / prior official ETF close.
same_day_first_ibit is the first completed IBIT bar's close/open log return.
first_btc_preopen_price is the BTC price at the frozen night endpoint.

F1: |night/scale|>=a, first IBIT return agrees, post-cutoff BTC retrace <=b.
F2: |night/scale|>=.5, signed IBIT gap captures >=a of night, BTC reverses >=b.
F3: trend L=a exceeds vol*sqrt(L), opposite pure-RTH b-hour pullback occupies
    [.25,.75] of |trend|, night agrees and accounts for >=.5 of |trend|.
F4: |night/scale|>=b, prior a-session QQQ regime and current QQQ hour agree.

Controls F1/F2 substitute IBIT gap for night_return; F4 substitutes QQQ gap.
The SAME source night_scale and all intraday inputs remain, so these are fixed
price-context proxies, not matched-risk ETF-only controls. F2 control capture
is mechanically one. F3 removes ONLY the night-confirmation predicate, retaining
source trend/pullback and common data availability. No control proves full
conditional independence from ETF history.

Only a NEW directional-condition episode emits a score. Repeated true rows
are suppressed; a valid false row rearms, a direction switch starts a new
episode, each NY day resets. Unavailable rows suppress without rearming; quote
failure does not consume an otherwise eligible onset. There is no daily cap.
Scores +1 for Nasdaq roles, -1 for Bitcoin roles select actual BUY ticker
columns; a negative score is never an instruction to short.
"""
import numpy as np
import pandas as pd

SYMBOLS = ("TQQQ", "SQQQ", "IBIT", "BITI")
FAMILIES = ("night_acceptance", "night_exhaustion", "trend_pullback", "night_nasdaq")
GRIDS = {
    "night_acceptance": ((.5, 1.), (.25, .5)),
    "night_exhaustion": ((.5, .8), (.25, .5)),
    "trend_pullback": ((24, 48), (1, 3)),
    "night_nasdaq": ((5, 10), (.5, 1.)),
}


def candidates():
    """Exactly sixteen unique fixed dictionaries; no fitted parameters."""
    return [dict(name=f"{family}_a{a:g}_b{b:g}", family=family, a=a, b=b)
            for family in FAMILIES for a in GRIDS[family][0]
            for b in GRIDS[family][1]]


def _calendar(data, times):
    calendar = pd.DatetimeIndex(pd.to_datetime(times, utc=True, errors="raise"))
    if calendar.hasnans or calendar.has_duplicates or not calendar.is_monotonic_increasing:
        raise ValueError("Times must be finite, unique and strictly increasing")
    if not pd.DatetimeIndex(pd.to_datetime(data.timestamps, utc=True)).equals(calendar):
        raise ValueError("ETF timestamps must exactly match supplied times")
    if len(data.symbols) != 4 or set(data.symbols) != set(SYMBOLS):
        raise ValueError("Actual TQQQ/SQQQ/IBIT/BITI required")
    bars = np.stack([np.asarray(getattr(data, key), float)
                     for key in ("open", "high", "low", "close")], axis=2)
    if bars.shape != (len(calendar), 4, 4):
        raise ValueError("ETF OHLC must have shape (n,4)")
    o, h, l, close = (bars[..., k] for k in range(4))
    quotes = (np.isfinite(bars).all(axis=-1) & (bars > 0).all(axis=-1)
              & (h >= np.maximum.reduce([o, l, close]))
              & (l <= np.minimum.reduce([o, h, close])))
    local = calendar.tz_convert("America/New_York")
    minutes = local.hour.to_numpy() * 60 + local.minute.to_numpy()
    rth = (minutes >= 570) & (minutes < 960) & (local.dayofweek.to_numpy() < 5)
    return local.date, rth, quotes


def _array(ctx, name, n, boolean=False):
    value = np.asarray(ctx[name])
    if value.shape != (n,):
        raise ValueError(f"ctx[{name!r}] must have shape (n,)")
    if boolean:
        if value.dtype.kind != "b":
            raise ValueError("ctx['valid'] must be a boolean array")
        return value
    return np.asarray(value, float)


def signals(data, times, ctx, c, control=False):
    """Return n×4 onset BUY-role scores, respecting actual symbol ordering."""
    if not isinstance(control, (bool, np.bool_)):
        raise ValueError("control must be boolean")
    if any(isinstance(c.get(key), (bool, np.bool_)) for key in ("a", "b")):
        raise ValueError("Unknown fixed candidate")
    matched = [x for x in candidates() if (x["family"], x["a"], x["b"]) ==
               (c.get("family"), c.get("a"), c.get("b"))]
    if not matched:
        raise ValueError("Unknown fixed candidate")
    family, a, b = (matched[0][key] for key in ("family", "a", "b"))
    days, rth, quotes = _calendar(data, times)
    n = len(days)
    common = _array(ctx, "valid", n, True) & rth
    required = {
        "night_acceptance": ("night_return", "night_scale", "btc_now",
                              "first_btc_preopen_price", "same_day_first_ibit", "ibit_gap"),
        "night_exhaustion": ("night_return", "night_scale", "btc_now",
                              "first_btc_preopen_price", "ibit_gap"),
        "trend_pullback": ("night_return", "btc_vol480", f"btc_trend{a}", f"btc_pullback{b}"),
        "night_nasdaq": ("night_return", "night_scale", f"qqq_regime{a}", "qqq_rth", "qqq_gap"),
    }[family]
    arrays = {key: _array(ctx, key, n) for key in required}
    for value in arrays.values():
        common &= np.isfinite(value)
    night = arrays["night_return"]
    if control and family in ("night_acceptance", "night_exhaustion", "night_nasdaq"):
        night = arrays["qqq_gap" if family == "night_nasdaq" else "ibit_gap"]
    direction = np.sign(night)
    if family != "trend_pullback":
        scale = arrays["night_scale"]
        common &= scale > 0
        strength = np.divide(np.abs(night), scale, out=np.zeros(n), where=scale > 0)
    if family in ("night_acceptance", "night_exhaustion"):
        now, preopen = arrays["btc_now"], arrays["first_btc_preopen_price"]
        positive = (now > 0) & (preopen > 0)
        common &= positive
        post = np.zeros(n)
        post[positive] = np.log(now[positive]) - np.log(preopen[positive])
        signed_post = direction * post
        if family == "night_acceptance":
            condition = ((strength >= a) & (direction * arrays["same_day_first_ibit"] > 0)
                         & (signed_post >= -b * np.abs(night)))
        else:
            # Signed inequality avoids division by a zero night return.
            condition = ((strength >= .5) & (direction * arrays["ibit_gap"] >= a * np.abs(night))
                         & (signed_post <= -b * np.abs(night)))
    elif family == "trend_pullback":
        trend, pullback, vol = arrays[f"btc_trend{a}"], arrays[f"btc_pullback{b}"], arrays["btc_vol480"]
        direction = np.sign(trend)
        common &= vol > 0
        condition = ((np.abs(trend) >= vol * np.sqrt(a)) & (direction * pullback < 0)
                     & (np.abs(pullback) >= .25 * np.abs(trend))
                     & (np.abs(pullback) <= .75 * np.abs(trend)))
        if not control:
            condition &= ((direction * night > 0) & (np.abs(night) >= .5 * np.abs(trend)))
    else:
        condition = ((strength >= b) & (direction * arrays[f"qqq_regime{a}"] > 0)
                     & (direction * arrays["qqq_rth"] > 0))
    if family == "night_exhaustion":
        direction = -direction  # Failed transfer buys the opposite actual ETF.
    desired = np.where(condition & (direction != 0), direction, 0.)
    result = np.zeros((n, 4))
    nasdaq = family == "night_nasdaq"
    bull, bear = ("TQQQ", "SQQQ") if nasdaq else ("IBIT", "BITI")
    jbull, jbear = data.symbols.index(bull), data.symbols.index(bear)
    score = 1. if nasdaq else -1.
    previous_day, previous_direction = None, 0.
    for i in range(n):
        if days[i] != previous_day:
            previous_day, previous_direction = days[i], 0.
        if not common[i]:
            continue
        value = desired[i]
        if value == 0:
            previous_direction = 0.
            continue
        target = jbull if value > 0 else jbear
        if value != previous_direction and quotes[i, target]:
            result[i, target] = score
            previous_direction = value
    return result
