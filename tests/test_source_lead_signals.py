import sys
import unittest
from unittest.mock import patch
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from autogrid.data import MarketData
from source_lead_signals_20261119 import (
    FAMILIES, baseline_scores, candidates, decision_mask, feature_values, filter_scores,
)

SYMBOLS = ("TQQQ", "SQQQ", "IBIT", "BITI")


def fixture(days=2):
    dates = pd.bdate_range("2026-10-30", periods=days, tz="America/New_York")
    times = pd.DatetimeIndex([day + pd.Timedelta(minutes=570 + 5 * i)
                              for day in dates for i in range(78)]).tz_convert("UTC")
    p = np.tile(np.arange(78), days)
    logs = np.column_stack((.001 * p + .0002 * np.sin(p),
                            -.001 * p + .0002 * np.cos(p)))
    close = 100 * np.exp(logs)
    refs = np.stack((close, close * 1.0002, close * .9994, close), axis=2)
    etf = 100 * np.exp(np.column_stack((3 * logs[:, 0], -3 * logs[:, 0],
                                        logs[:, 1], -logs[:, 1])))
    data = MarketData(np.asarray(times), SYMBOLS, etf.copy(), etf * 1.0002,
                      etf * .9994, etf.copy(), np.ones_like(etf), bar_minutes=5)
    return data, times, refs


def subset(data, ix):
    return replace(data, timestamps=data.timestamps[ix], **{
        key: getattr(data, key)[ix] for key in ("open", "high", "low", "close", "volume")})


def candidate(family, lag=0):
    return next(c for c in candidates() if c["family"] == family and c["lag"] == lag)


class SourceLeadSignalsTests(unittest.TestCase):
    def test_twelve_settings_and_exact_completed_clocks_through_dst(self):
        self.assertEqual(len(candidates()), 12)
        self.assertEqual(len({c["name"] for c in candidates()}), 12)
        data, times, refs = fixture()
        mask = decision_mask(times)
        self.assertEqual(mask.sum(), 32)
        expected = list(pd.date_range("2026-10-30 11:00", "2026-10-30 14:45", freq="15min").strftime("%H:%M"))
        for offset in (0, 78):
            ends = (times[offset:offset + 78] + pd.Timedelta(minutes=5)).tz_convert("America/New_York")
            self.assertEqual(list(ends[mask[offset:offset + 78]].strftime("%H:%M")), expected)
        self.assertEqual(times[0].hour, 13)
        self.assertEqual(times[78].hour, 14)
        with self.assertRaises(ValueError):
            decision_mask(times + pd.Timedelta(seconds=1))
        with self.assertRaises(ValueError):
            feature_values(data, times, refs, dict(family="wick_pressure", lag=2))
        with self.assertRaises(ValueError):
            feature_values(data, times, refs, candidates()[0], "bad")

    def test_baseline_reproduces_frozen_momentum_on_complete_input(self):
        from five_minute_grid_20261118 import signals
        data, times, _ = fixture()
        old = signals(data, times, dict(family="momentum", a=4, b=.5))
        old[~decision_mask(times)] = 0
        np.testing.assert_array_equal(baseline_scores(data, times), old)
        order = [3, 1, 0, 2]
        shuffled = replace(data, symbols=tuple(SYMBOLS[j] for j in order), **{
            key: getattr(data, key)[:, order] for key in ("open", "high", "low", "close", "volume")})
        np.testing.assert_array_equal(baseline_scores(shuffled, times), old[:, order])

    def test_prefix_and_future_mutation_for_all_settings_both_feeds(self):
        data, times, refs = fixture()
        for c in candidates():
            for feed in ("source", "ETF"):
                full = feature_values(data, times, refs, c, feed)
                for n in (18, 60, 85):
                    np.testing.assert_allclose(feature_values(subset(data, slice(n)), times[:n], refs[:n], c, feed), full[:n], equal_nan=True)
                changed_refs = refs.copy()
                changed_refs[60:] *= 1.1
                changed_data = replace(data, **{key: getattr(data, key).copy() for key in ("open", "high", "low", "close")})
                for key in ("open", "high", "low", "close"):
                    getattr(changed_data, key)[60:] *= 1.2
                changed = filter_scores(changed_data, times, changed_refs, c, feed)
                np.testing.assert_array_equal(changed[:60], filter_scores(data, times, refs, c, feed)[:60])

    def test_lag_exactly_shifts_feature_without_crossing_session(self):
        data, times, refs = fixture()
        for family in FAMILIES:
            for feed in ("source", "ETF"):
                base = feature_values(data, times, refs, candidate(family), feed)
                for lag in (1, 3):
                    shifted = feature_values(data, times, refs, candidate(family, lag), feed)
                    for start in (0, 78):
                        self.assertTrue(np.isnan(shifted[start:start + lag]).all())
                        np.testing.assert_allclose(shifted[start + lag:start + 78], base[start:start + 78 - lag], equal_nan=True)

    def test_missing_reference_clock_and_session_reset(self):
        data, times, refs = fixture()
        missing = refs.copy()
        missing[30, 0] = np.nan
        for family in FAMILIES:
            warmup = 2 if family == "wick_pressure" else 12
            c = candidate(family)
            values = feature_values(data, times, missing, c)
            self.assertTrue(np.isnan(values[30:31 + warmup, :2]).all())
            np.testing.assert_allclose(values[:, 2:], feature_values(data, times, refs, c)[:, 2:], equal_nan=True)
            self.assertTrue(np.isnan(values[78:78 + warmup]).all())
            ix = np.r_[np.arange(30), np.arange(31, len(times))]
            cut = feature_values(subset(data, ix), times[ix], refs[ix], c)
            self.assertTrue(np.isnan(cut[30:30 + warmup, :2]).all())
        # Lag3 does not consult newer, unused source OHLC at decision time.
        c = candidate("tail_energy", 3)
        np.testing.assert_allclose(feature_values(data, times, missing, c)[30], feature_values(data, times, refs, c)[30], equal_nan=True)
        ix = np.r_[np.arange(30), np.arange(31, len(times))]
        cut = feature_values(subset(data, ix), times[ix], refs[ix], candidate("wick_pressure", 3))
        self.assertTrue(np.isnan(cut[30:32]).all())

    def test_source_orientation_only_directional_and_native_etf_feed(self):
        data, times, refs = fixture()
        for family in FAMILIES:
            source = feature_values(data, times, refs, candidate(family))
            direction = -1 if family in ("wick_pressure", "tail_energy") else 1
            np.testing.assert_allclose(source[:, 0], direction * source[:, 1], equal_nan=True)
            np.testing.assert_allclose(source[:, 2], direction * source[:, 3], equal_nan=True)
        source = feature_values(data, times, refs, candidate("wick_pressure"))
        actual = feature_values(data, times, refs, candidate("wick_pressure"), "ETF")
        self.assertGreater(source[17, 0], 0)
        self.assertLess(source[17, 1], 0)
        self.assertGreater(actual[17, 1], 0)  # native actual BUY ETF candle

    def test_exact_feature_arithmetic_and_distinct_mechanisms(self):
        data, times, refs = fixture(days=1)
        returns = np.array([.001, -.002, .003, -.004, .005, -.006,
                            .007, -.008, .009, -.010, .011, -.012])
        close = 100 * np.exp(np.r_[0., returns.cumsum()])
        refs[:13, 0] = np.column_stack((close, close * 1.001, close * .997, close))
        at = lambda family, ref=refs: feature_values(data, times, ref, candidate(family))[12, 0]
        self.assertAlmostEqual(at("wick_pressure"), .5)
        self.assertAlmostEqual(at("path_chop"), 1.)
        self.assertAlmostEqual(at("vol_compression"), np.sqrt(np.mean(returns[8:] ** 2) / np.mean(returns[:8] ** 2)))
        self.assertAlmostEqual(at("tail_energy"), np.sum(returns * np.abs(returns)) / np.sum(returns ** 2))
        wick_changed = refs.copy()
        wick_changed[:13, 0, 1] = close * 1.003
        wick_changed[:13, 0, 2] = close * .999
        self.assertLess(at("wick_pressure", wick_changed), 0)
        for family in ("path_chop", "vol_compression", "tail_energy"):
            self.assertAlmostEqual(at(family), at(family, wick_changed))
        # Same signed-return multiset: tail energy unchanged, order/chop changes.
        ordered = np.r_[np.full(6, .001), np.full(6, -.001)]
        alternating = np.tile([.001, -.001], 6)
        values = []
        for pattern in (ordered, alternating):
            changed = refs.copy()
            price = 100 * np.exp(np.r_[0., pattern.cumsum()])
            changed[:13, 0] = np.column_stack((price, price * 1.001, price * .999, price))
            values.append([at(family, changed) for family in FAMILIES])
        self.assertAlmostEqual(values[0][3], values[1][3])
        self.assertLess(values[0][1], values[1][1])
        self.assertAlmostEqual(values[0][2], values[1][2])

    def test_fixed_threshold_boundaries_and_zero_return_denominator(self):
        data, times, refs = fixture(days=1)
        baseline = baseline_scores(data, times)
        boundaries = {"wick_pressure": (0., False), "path_chop": (1 / 3, True),
                      "vol_compression": (1., True), "tail_energy": (1 / 4, False)}
        for family, (threshold, inclusive) in boundaries.items():
            with patch("source_lead_signals_20261119.feature_values", return_value=np.full_like(baseline, threshold)):
                actual = filter_scores(data, times, refs, candidate(family))
                np.testing.assert_array_equal(actual, baseline if inclusive else np.zeros_like(baseline))
            with patch("source_lead_signals_20261119.feature_values", return_value=np.full_like(baseline, np.nan)):
                self.assertFalse(np.any(filter_scores(data, times, refs, candidate(family))))
        # Two flat returns remain eligible: zero-product pairs are not flips,
        # and the denominator stays11 rather than shrinking to nonzero pairs.
        pattern = np.array([.001, -.001, 0., .001, -.001, 0., .001, -.001, .001, -.001, .001, -.001])
        for zero_count in (2, 3):
            changed = refs.copy()
            if zero_count == 3:
                pattern[8] = 0.
            price = 100 * np.exp(np.r_[0., pattern.cumsum()])
            changed[:13, 0] = np.column_stack((price, price * 1.001, price * .999, price))
            value = feature_values(data, times, changed, candidate("path_chop"))[12, 0]
            if zero_count == 2:
                self.assertAlmostEqual(value, np.count_nonzero(pattern[1:] * pattern[:-1] < 0) / 11)
            else:
                self.assertTrue(np.isnan(value))

    def test_flat_and_missing_inputs_and_strict_filter_subset(self):
        data, times, refs = fixture()
        baseline = baseline_scores(data, times)
        self.assertGreater(np.count_nonzero(baseline), 0)
        for c in candidates():
            for feed in ("source", "ETF"):
                score = filter_scores(data, times, refs, c, feed)
                self.assertTrue(np.all((score == 0) | (score == baseline)))
                self.assertFalse(np.any(score[~decision_mask(times)]))
            self.assertFalse(np.any(filter_scores(data, times, np.full_like(refs, np.nan), c)))
            self.assertFalse(np.any(filter_scores(data, times, np.full_like(refs, 100.), c)))
        flat = feature_values(data, times, np.full_like(refs, 100.), candidate("path_chop"))
        self.assertTrue(np.isnan(flat).all())
        for invalid in (0., -1., np.inf):
            missing = refs.copy()
            missing[17, 0] = invalid
            self.assertFalse(np.any(filter_scores(data, times, missing, candidate("wick_pressure"))[17, :2]))
        # Missing current actual BUY quote cannot create a baseline action.
        broken = replace(data, close=data.close.copy())
        broken.close[17] = np.nan
        self.assertFalse(np.any(filter_scores(broken, times, refs, candidate("wick_pressure"))[17]))


if __name__ == "__main__":
    unittest.main()
