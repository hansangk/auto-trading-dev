"""Sixteen fixed information controls for Nasdaq night(5,.5), without fitting PnL.

The caller retains the 15% allocation, actual BUY execution and all protections.
Only TQQQ/SQQQ scores are emitted; zero means cash. The QQQ parent deliberately
retains the source family's common availability, including finite BTC fields.
It removes BTC predicates, not source-availability selection.

Session cash probability is fitted once from source/parent EVENT COUNTS over
2024-12-01..31 NY dates. Calibration is an untraded phase: prefixes inside it
may produce different fitted p. Decisions from 2025-01-01 onward are prefix
invariant once that fixed calibration window is observed. Shorter/truncated
datasets do not recover a missing calibration history and flag fallback p=.5.
No realized return, forward path, account result, or selected seed is an input.
"""
import hashlib

import numpy as np
import pandas as pd

from hourly_night_signals_20261119 import _array, _calendar, signals


SOURCE = dict(family="night_nasdaq", a=5, b=.5)
CALIBRATION_START = "2024-12-01"
CALIBRATION_END = "2024-12-31"
CONTROL_NAMES = (
    "source", "drop_strength", "drop_direction", "qqq_consensus",
    "qqq_gap_side", "opposite", "hash_side_0", "hash_side_1",
    "session_cash_0", "session_cash_1", "session_cash_2", "session_cash_3",
    "stale_1", "stale_2", "stale_3", "stale_5",
)


def _uniform(day, seed, purpose):
    payload = f"nasdaq-gate-20261119|{purpose}|{seed}|{day}".encode("ascii")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") / 2**64


def _onsets(days, common, desired, quotes, bull, bear):
    """Same valid-false rearming and missing/quote handling as old signals()."""
    out = np.zeros_like(quotes, dtype=float)
    previous_day, previous_direction = None, 0.
    for i, day in enumerate(days):
        if day != previous_day:
            previous_day, previous_direction = day, 0.
        if not common[i]:
            continue
        direction = desired[i]
        if direction == 0:
            previous_direction = 0.
            continue
        target = bull if direction > 0 else bear
        if direction != previous_direction and quotes[i, target]:
            out[i, target] = 1.
            previous_direction = direction
    return out


def build_controls(data, times, ctx):
    """Return exactly sixteen n×4 BUY score arrays and JSON-safe metadata.

    ``times``/``ctx`` must be the caller's audited normal-session timeline.
    Stale lags count every observed NY ETF session, including unavailable donor
    sessions; a missing donor is not skipped, interpolated or carried forward.
    The first available valid night feature in a CLOSED donor session is used.
    """
    days, rth, quotes = _calendar(data, times)
    n = len(days)
    values = {key: _array(ctx, key, n) for key in (
        "night_return", "night_scale", "qqq_regime5", "qqq_rth", "qqq_gap")}
    valid = _array(ctx, "valid", n, True)
    common = valid & rth
    for value in values.values():
        common &= np.isfinite(value)
    common &= values["night_scale"] > 0
    bull, bear = data.symbols.index("TQQQ"), data.symbols.index("SQQQ")
    regime = np.sign(values["qqq_regime5"])
    night_direction = np.sign(values["night_return"])
    strength = np.divide(np.abs(values["night_return"]), values["night_scale"],
                         out=np.zeros(n), where=values["night_scale"] > 0)
    parent_condition = (regime != 0) & (regime * values["qqq_rth"] > 0)
    direction_gate = night_direction * regime > 0
    strength_gate = strength >= .5

    def emit(condition, support=common):
        return _onsets(days, support, np.where(condition, regime, 0.), quotes, bull, bear)

    scores = {"source": signals(data, times, ctx, SOURCE)}
    scores["drop_strength"] = emit(parent_condition & direction_gate)
    scores["drop_direction"] = emit(parent_condition & strength_gate)
    scores["qqq_consensus"] = emit(parent_condition)
    reconstructed = emit(parent_condition & direction_gate & strength_gate)
    if not np.array_equal(reconstructed, scores["source"]):
        raise AssertionError("Source reconstruction differs from frozen old signals")

    # Side interventions retain the original source event clocks exactly. A
    # replacement quote failure suppresses that event without creating a retry.
    source_events = np.any(scores["source"] != 0, axis=1)
    source_direction = scores["source"][:, bull] - scores["source"][:, bear]
    definitions = {
        "source": "Frozen old night_nasdaq(5,.5) source",
        "drop_strength": "QQQ consensus plus BTC night sign agreement only",
        "drop_direction": "QQQ consensus plus BTC night strength >=.5 only",
        "qqq_consensus": "QQQ5 regime/current completed-hour agreement; common source validity retained",
        "qqq_gap_side": "Source event clock; actual ETF chosen by QQQ gap sign; zero is cash",
        "opposite": "Source event clock; opposite actual ETF BUY",
        "hash_side_0": "Source event clock; NY-day hash side seed0",
        "hash_side_1": "Source event clock; NY-day hash side seed1",
    }
    side_options = {
        "qqq_gap_side": np.sign(values["qqq_gap"]),
        "opposite": -source_direction,
        **{f"hash_side_{seed}": np.asarray([
            1. if _uniform(day.isoformat(), seed, "side") < .5 else -1.
            for day in days]) for seed in (0, 1)},
    }
    for name, sides in side_options.items():
        out = np.zeros((n, 4))
        for i in np.flatnonzero(source_events & (sides != 0)):
            target = bull if sides[i] > 0 else bear
            if quotes[i, target]:
                out[i, target] = 1.
        scores[name] = out

    day_labels = np.asarray([day.isoformat() for day in days])
    calibration_mask = ((day_labels >= CALIBRATION_START)
                        & (day_labels <= CALIBRATION_END))
    parent_events = np.any(scores["qqq_consensus"] != 0, axis=1)
    parent_count = int(np.count_nonzero(parent_events & calibration_mask))
    source_count = int(np.count_nonzero(source_events & calibration_mask))
    calibrated = parent_count >= 20
    probability = min(1., source_count / parent_count) if calibrated else .5
    for seed in range(4):
        name = f"session_cash_{seed}"
        keep = np.asarray([_uniform(day, seed, "cash") < probability for day in day_labels])
        scores[name] = scores["qqq_consensus"] * keep[:, None]
        definitions[name] = f"QQQ parent session keep by NY-day hash seed{seed}; fixed count-only probability"

    # Donors are fixed by OBSERVED ETF-day position, never by available-feature
    # position. Entire-day unavailable features therefore block their own lags.
    observed_days = list(dict.fromkeys(days))
    donor_features = {}
    for day in observed_days:
        ix = np.flatnonzero((days == day) & valid & rth
                            & np.isfinite(values["night_return"])
                            & np.isfinite(values["night_scale"])
                            & (values["night_scale"] > 0))
        donor_features[day] = (values["night_return"][ix[0]],
                               values["night_scale"][ix[0]]) if len(ix) else None
    for lag in (1, 2, 3, 5):
        gate = np.zeros(n, dtype=bool)
        donor_valid = np.zeros(n, dtype=bool)
        for position, day in enumerate(observed_days):
            if position < lag:
                continue
            donor = donor_features[observed_days[position - lag]]
            if donor is None:
                continue
            night, scale = donor
            ix = days == day
            donor_valid[ix] = True
            gate[ix] = (abs(night) / scale >= .5) & (np.sign(night) * regime[ix] > 0)
        name = f"stale_{lag}"
        scores[name] = emit(parent_condition & gate, common & donor_valid)
        definitions[name] = f"QQQ parent with BTC night gate from {lag} earlier observed normal ETF sessions"

    # A day-gate identity needs frozen nightly fields; the event-direction
    # identity holds even on a malformed context with intraday changing nights.
    frozen_fields = ("night_return", "night_scale", "qqq_regime5")
    frozen = all(all(len(np.unique(values[key][(days == day) & common])) <= 1
                     for key in frozen_fields) for day in observed_days)
    gated_parent = scores["qqq_consensus"] * (direction_gate & strength_gate)[:, None]
    identity = bool(np.array_equal(gated_parent, scores["source"]))
    if frozen and not identity:
        raise AssertionError("Frozen session day-gate identity failed")
    regime_identity = bool(np.all(source_direction[source_events] == regime[source_events]))
    hour_identity = bool(np.all(source_direction[source_events] == np.sign(values["qqq_rth"][source_events])))
    metadata = {
        "definitions": definitions,
        "families": {"A": list(CONTROL_NAMES[:4]), "B": list(CONTROL_NAMES[4:8]),
                     "C": list(CONTROL_NAMES[8:12]), "D": list(CONTROL_NAMES[12:])},
        "calibration": {"start_ny": CALIBRATION_START, "end_ny": CALIBRATION_END,
                        "parent_event_count": parent_count, "source_event_count": source_count,
                        "probability": probability, "calibrated": calibrated,
                        "uncalibrated": not calibrated, "fallback_probability": .5,
                        "minimum_parent_events": 20, "outcomes_used": False,
                        "trade_start_ny": "2025-01-01",
                        "prefix_caveat": "Calibration-phase p may change; calibration is not traded"},
        "identities": {"old_source_array_exact": True, "session_fields_frozen": frozen,
                       "source_equals_day_gated_parent": identity,
                       "qqq_regime_side_equals_source": regime_identity,
                       "qqq_hour_side_equals_source": hour_identity,
                       "aliases_not_additional_controls": ["qqq_regime_side", "qqq_hour_side"]},
        "allocation": "Caller-fixed15percent; actual TQQQ/SQQQ BUY only; unused capital cash",
        "stale_session_definition": "Every observed ETF NY day counts; no skipped missing donors or forward fill",
        "seed_policy": "Fixed controls; never rank/promote seeds by returns",
    }
    if set(scores) != set(CONTROL_NAMES) or set(definitions) != set(CONTROL_NAMES):
        raise AssertionError("Expected exactly sixteen control definitions")
    return {name: scores[name] for name in CONTROL_NAMES}, metadata
