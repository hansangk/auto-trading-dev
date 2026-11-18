import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from autogrid.data import MarketData
from hourly_night_signals_20261119 import signals
from nasdaq_gate_controls_20261119 import CONTROL_NAMES, SOURCE, build_controls


def fixture(dates=None):
    dates = dates or ["2024-12-30", "2024-12-31", "2025-01-02", "2025-01-03",
                      "2025-01-06", "2025-01-07", "2025-01-08", "2025-01-09"]
    local = pd.to_datetime(dates).tz_localize("America/New_York")
    times = pd.DatetimeIndex([day + pd.Timedelta(minutes=570 + 60*i)
                              for day in local for i in range(7)]).tz_convert("UTC")
    n = len(times)
    price = np.full((n, 4), 100.)
    data = MarketData(np.asarray(times), ("TQQQ", "SQQQ", "IBIT", "BITI"),
                      price, price+1, price-1, price.copy(), np.ones_like(price), bar_minutes=60)
    value = lambda x: np.full(n, x, dtype=float)
    ctx = dict(night_return=value(.03), night_scale=value(.02), qqq_regime5=value(.02),
               qqq_rth=value(.002), qqq_gap=value(.01), valid=np.ones(n, dtype=bool))
    return data, times, ctx


def subset(data, end):
    return replace(data, timestamps=data.timestamps[:end], **{
        key: getattr(data, key)[:end] for key in ("open", "high", "low", "close", "volume")})


class NasdaqGateControlsTests(unittest.TestCase):
    def test_sixteen_actual_buy_arrays_and_identity(self):
        data, times, ctx = fixture()
        ctx["night_return"][7:14] = -.03
        ctx["night_return"][14:21] = .005
        scores, meta = build_controls(data, times, ctx)
        self.assertEqual(tuple(scores), CONTROL_NAMES)
        self.assertEqual(len(meta["definitions"]), 16)
        self.assertTrue(all(len(v) == 4 for v in meta["families"].values()))
        np.testing.assert_array_equal(scores["source"], signals(data, times, ctx, SOURCE))
        self.assertTrue(all(meta["identities"][key] for key in (
            "old_source_array_exact", "session_fields_frozen", "source_equals_day_gated_parent",
            "qqq_regime_side_equals_source", "qqq_hour_side_equals_source")))
        self.assertEqual(np.flatnonzero(scores["source"][:, 0]).tolist(), [0,21,28,35,42,49])
        self.assertTrue(scores["drop_strength"][14,0])
        self.assertTrue(scores["drop_direction"][7,0])
        for array in scores.values():
            self.assertEqual(array.shape, (len(times),4))
            self.assertTrue(np.isin(array, [0.,1.]).all())
            self.assertFalse(np.any(array[:,2:]))
            self.assertTrue((np.count_nonzero(array, axis=1) <= 1).all())
        json.dumps(meta)

    def test_onset_missing_false_quote_and_session_dst_rules(self):
        data, times, ctx = fixture(["2026-10-30", "2026-11-02"])
        ctx["qqq_rth"][[2,4]] = 0
        ctx["valid"][2] = False  # missing false must not rearm
        broken = replace(data, close=data.close.copy())
        broken.close[0,0] = np.nan  # quote failure does not consume onset
        scores, _ = build_controls(broken, times, ctx)
        self.assertEqual(np.flatnonzero(scores["source"][:,0]).tolist(), [1,5,7])
        self.assertEqual(np.flatnonzero(scores["qqq_consensus"][:,0]).tolist(), [1,5,7])
        self.assertEqual((times[0].hour, times[7].hour), (13,14))

    def test_bearish_source_is_sqqq_buy_and_opposite_is_tqqq_buy(self):
        data,times,ctx = fixture()
        for key in ("night_return","qqq_regime5","qqq_rth","qqq_gap"):
            ctx[key] *= -1
        scores,meta = build_controls(data,times,ctx)
        self.assertTrue(scores["source"][0,1])
        self.assertTrue(scores["qqq_gap_side"][0,1])
        self.assertTrue(scores["opposite"][0,0])
        self.assertTrue(meta["identities"]["source_equals_day_gated_parent"])
        for name in ("source","drop_strength","drop_direction","qqq_consensus","stale_1"):
            self.assertFalse(np.any(scores[name][:,0]))
            self.assertFalse(np.any(scores[name] < 0))

    def test_side_controls_rechoose_real_tickers_at_original_clocks(self):
        data, times, ctx = fixture()
        ctx["qqq_gap"][:7] = -.01
        ctx["qqq_gap"][7:14] = 0
        broken = replace(data, close=data.close.copy())
        broken.close[14,1] = np.nan  # opposite quote failure: suppress, no later retry
        scores, _ = build_controls(broken,times,ctx)
        self.assertTrue(scores["qqq_gap_side"][0,1])
        self.assertFalse(np.any(scores["qqq_gap_side"][7:14]))
        self.assertFalse(np.any(scores["opposite"][14:21]))
        source_events = np.any(scores["source"],axis=1)
        for name in CONTROL_NAMES[4:8]:
            self.assertFalse(np.any(np.any(scores[name],axis=1) & ~source_events))
        order = [3,1,0,2]
        reordered = replace(data, symbols=tuple(data.symbols[j] for j in order), **{
            key:getattr(data,key)[:,order] for key in ("open","high","low","close","volume")})
        original, _ = build_controls(data,times,ctx)
        changed, _ = build_controls(reordered,times,ctx)
        for name in CONTROL_NAMES:
            np.testing.assert_array_equal(changed[name], original[name][:,order])

    def test_cash_calibration_counts_not_returns_and_same_session_keep(self):
        data,times,ctx = fixture(["2024-12-30", "2024-12-31", "2025-01-02"])
        ctx["qqq_rth"][:] = np.tile([.002,0,.002,0,.002,0,.002],3)
        _, meta = build_controls(data,times,ctx)
        self.assertTrue(meta["calibration"]["uncalibrated"])
        self.assertEqual(meta["calibration"]["probability"],.5)
        dates = pd.bdate_range("2024-12-02", periods=21).strftime("%Y-%m-%d").tolist()
        data,times,ctx = fixture(dates+["2025-01-02"])
        ctx["night_return"][:7*7] = -.03
        ctx["qqq_rth"][-7:] = [.002,0,.002,0,.002,0,.002]
        scores,meta = build_controls(data,times,ctx)
        self.assertTrue(meta["calibration"]["calibrated"])
        self.assertEqual(meta["calibration"]["parent_event_count"],21)
        self.assertEqual(meta["calibration"]["source_event_count"],14)
        self.assertAlmostEqual(meta["calibration"]["probability"],2/3)
        # Alter valid future price levels, preserving quote validity; count p is unchanged.
        changed = replace(data, close=data.close.copy())
        changed.close[:] = 99.5
        _, changed_meta = build_controls(changed,times,ctx)
        self.assertEqual(meta["calibration"],changed_meta["calibration"])
        for name in CONTROL_NAMES[8:12]:
            for i in range(0,len(times),7):
                self.assertTrue(np.array_equal(scores[name][i:i+7],scores["qqq_consensus"][i:i+7])
                                or not np.any(scores[name][i:i+7]))

    def test_stale_observed_day_lags_missing_not_skipped(self):
        data,times,ctx = fixture()
        ctx["night_return"][7:14] = -.03
        ctx["valid"][14:21] = False
        scores,_ = build_controls(data,times,ctx)
        self.assertFalse(np.any(scores["stale_1"][:7]))
        self.assertTrue(scores["stale_1"][7,0])
        self.assertFalse(np.any(scores["stale_1"][21:28])) # donor day2 unavailable; no skip
        self.assertFalse(scores["stale_2"][21,0]) # donor day1 bearish
        self.assertTrue(scores["stale_3"][21,0]) # donor day0 bullish
        self.assertTrue(scores["stale_5"][35,0])
        changed = {k:v.copy() for k,v in ctx.items()}
        changed["night_scale"][0:7] = np.nan
        mutated,_ = build_controls(data,times,changed)
        self.assertFalse(np.any(mutated["stale_5"][35:42]))

    def test_prefix_and_future_mutations_after_calibration(self):
        data,times,ctx = fixture()
        ctx["qqq_rth"][3] = 0
        complete,_ = build_controls(data,times,ctx)
        for end in (15,18,22,29,43):
            prefix,_ = build_controls(subset(data,end),times[:end],{k:v[:end] for k,v in ctx.items()})
            for name in CONTROL_NAMES:
                np.testing.assert_array_equal(prefix[name],complete[name][:end])
            changed = {k:v.copy() for k,v in ctx.items()}
            for key in changed:
                if key != "valid": changed[key][end:] *= -17
            changed["valid"][end:] = False
            mutated,_ = build_controls(data,times,changed)
            for name in CONTROL_NAMES:
                np.testing.assert_array_equal(mutated[name][:end],complete[name][:end])

    def test_fitted_probability_prefix_stays_fixed_after_cutoff(self):
        dates = pd.bdate_range("2024-12-02", periods=21).strftime("%Y-%m-%d").tolist()
        data,times,ctx = fixture(dates+["2025-01-02","2025-01-03","2025-01-06"])
        ctx["night_return"][:7*7] = -.03
        full,metadata = build_controls(data,times,ctx)
        self.assertTrue(metadata["calibration"]["calibrated"])
        for end in (148,153,158,164):
            prefix,meta = build_controls(subset(data,end),times[:end],{k:v[:end] for k,v in ctx.items()})
            self.assertEqual(meta["calibration"],metadata["calibration"])
            for name in CONTROL_NAMES:
                np.testing.assert_array_equal(prefix[name],full[name][:end])

    def test_common_support_and_input_contracts(self):
        data,times,ctx = fixture()
        for key in ("night_return","night_scale","qqq_gap"):
            changed = {k:v.copy() for k,v in ctx.items()}
            changed[key][:] = np.nan
            scores,_ = build_controls(data,times,changed)
            self.assertFalse(any(np.any(v) for v in scores.values()))
        with self.assertRaises(ValueError):
            build_controls(data,times,dict(ctx,valid=np.ones(len(times))))
        with self.assertRaises(ValueError):
            build_controls(data,times[::-1],ctx)


if __name__ == "__main__":
    unittest.main()
