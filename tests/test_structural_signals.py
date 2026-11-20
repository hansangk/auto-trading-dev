import sys
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from autogrid.data import MarketData
from episode_signals_20261118 import signals as episode_signals
from structural_signals_20261118 import FAMILIES, candidates, signals

SYMBOLS = ("BITI", "SQQQ", "TQQQ", "IBIT")


def fixture(closes=None, days=1):
    dates = pd.bdate_range("2026-10-19", periods=days, tz="America/New_York")
    times = pd.DatetimeIndex([day + pd.Timedelta(minutes=570+5*i)
                              for day in dates for i in range(78)]).tz_convert("UTC")
    close = np.tile([37., 50., 100., 100.], (len(times), 1))
    if closes is not None:
        for start in range(0, len(times), 78):
            close[start:start+len(closes)*3, 2] = np.repeat(closes, 3)
    return (MarketData(np.asarray(times), SYMBOLS, close.copy(), close+1,
                       close-1, close, np.ones_like(close), bar_minutes=5), times)


def candidate(family, a, b):
    return dict(family=family, a=a, b=b)


def subset(data, ix):
    return replace(data, timestamps=data.timestamps[ix], **{
        key: getattr(data, key)[ix] for key in ("open", "high", "low", "close", "volume")})


def compression_fixture():
    data, times = fixture()
    data.high[:12, 2], data.low[:12, 2] = 102, 98
    data.high[12:, 2], data.low[12:, 2] = 100.5, 99.5
    return data, times


class StructuralSignalsTests(unittest.TestCase):
    def test_exact_bounded_grid(self):
        grid = candidates()
        self.assertEqual(len(grid), 16)
        self.assertEqual(len({c["name"] for c in grid}), 16)
        self.assertEqual(set(FAMILIES), {c["family"] for c in grid})
        for family in FAMILIES:
            self.assertEqual(sum(c["family"] == family for c in grid), 4)
        data, times = fixture()
        with self.assertRaises(ValueError):
            signals(data, times, candidate("adverse_chase", 2, .25))

    def test_expiry_counts_completed_decisions_without_same_compression_rearm(self):
        data, times = compression_fixture()
        data.close[26, 2] = 101
        baseline = episode_signals(data, times, candidate("compression", .75, 4))
        short = signals(data, times, candidate("compression_expiry", 1, 0))
        long = signals(data, times, candidate("compression_expiry", 3, 0))
        self.assertEqual(baseline[26, 2], 1)
        self.assertEqual(long[26, 2], 1)  # arm20, then23,26 are its three decisions
        self.assertFalse(np.any(short[:27]))  # cannot rearm23 or26 in same compression
        data.close[26, 2] = 100
        data.close[29, 2] = 101
        self.assertEqual(episode_signals(data, times, candidate("compression", .75, 4))[29, 2], 1)
        self.assertEqual(signals(data, times, candidate("compression_expiry", 3, 0))[29, 2], 0)

    def test_expiry_one_allows_original_arm_close_breakout(self):
        data, times = compression_fixture()
        data.close[20, 2] = 101
        for invalidate in (0, 1):
            self.assertEqual(signals(data, times, candidate("compression_expiry", 1, invalidate))[20, 2], 1)

    def test_decompression_invalidates_frozen_box_before_breakout(self):
        data, times = compression_fixture()
        data.high[18:24, 2], data.low[18:24, 2] = 102, 98
        data.close[26, 2] = 101
        self.assertEqual(signals(data, times, candidate("compression_expiry", 3, 0))[26, 2], 1)
        self.assertEqual(signals(data, times, candidate("compression_expiry", 3, 1))[26, 2], 0)

    def test_adverse_lower_bound_uses_frozen_actual_inverse_etf_range(self):
        data, times = fixture([100]*4 + [98]*5)
        data.close[15, 1] = 49
        original = episode_signals(data, times, candidate("chasecancel", 1, .25))
        self.assertEqual(original[15, 1], 1)
        tight = signals(data, times, candidate("adverse_chase", 1, .25))
        loose = signals(data, times, candidate("adverse_chase", 1, .75))
        self.assertFalse(np.any(tight[14:26]))
        self.assertEqual(loose[15, 1], 1)
        self.assertEqual(np.count_nonzero(loose[14:26]), 1)
        data.low[15, 1] = 1  # waiting-bar range cannot enlarge the original range
        self.assertEqual(signals(data, times, candidate("adverse_chase", 1, .25))[15, 1], 0)
        data.close[15, 1] = 50.6
        self.assertEqual(signals(data, times, candidate("adverse_chase", 1, .75))[15, 1], 0)
        data.close[17, 1] = 50.8
        self.assertEqual(signals(data, times, candidate("adverse_chase", 3, .25))[17, 1], 1)
        data.close[17, 1] = 49
        self.assertEqual(signals(data, times, candidate("adverse_chase", 3, .25))[17, 1], 0)

    def test_confirmation_filters_original_decision_and_actual_selected_etf(self):
        data, times = fixture([100]*4 + [98]*5)
        # Source falls, but actual inverse ETF also falls: reject its own weakness.
        data.open[12:15, 1] = 51
        self.assertFalse(np.any(signals(data, times, candidate("own_confirmation", 3, 0))[14]))
        data.open[14, 1] = 49.8
        self.assertEqual(signals(data, times, candidate("own_confirmation", 1, 0))[14, 1], 1)
        self.assertEqual(signals(data, times, candidate("own_confirmation", 1, .25))[14, 1], 0)
        data.open[12, 1] = 49.4
        self.assertEqual(signals(data, times, candidate("own_confirmation", 3, .25))[14, 1], 1)
        self.assertFalse(np.any(signals(data, times, candidate("own_confirmation", 3, .25))[15:17]))
        # A zero preceding inverse range still permits the specified nonnegative check.
        data.high[9:12, 1], data.low[9:12, 1] = 50, 50
        self.assertEqual(signals(data, times, candidate("own_confirmation", 3, .25))[14, 1], 1)

    def test_participation_strict_shifted_history_actual_etf_and_same_slot(self):
        data, times = fixture([100]*4 + [98]*5, days=7)
        # Preceding selected inverse-ETF dollar volumes: [1500,150,300,450,600].
        for day, volume in enumerate((10, 1, 2, 3, 4, 9, 9)):
            data.volume[day*78+12:day*78+15, 1] = volume
        data.volume[5*78+12:5*78+15, 1] = 2.5  # 375 > q20=270, < q40=390
        data.volume[5*78+12:5*78+15, 2] = 1e9  # wrong ETF must not affect acceptance
        low = signals(data, times, candidate("participation", 5, .2))
        high = signals(data, times, candidate("participation", 5, .4))
        self.assertFalse(np.any(low[:5*78]))
        self.assertEqual(low[5*78+14, 1], 1)
        self.assertEqual(high[5*78+14, 1], 0)
        self.assertFalse(np.any(signals(data, times, candidate("participation", 10, .2))))
        # Including current and dropping oldest would lower q40 to345 and admit375.
        self.assertGreater(375, np.quantile([150, 300, 450, 600, 375], .4))
        # Missing the slot in one of the preceding observed sessions blocks it.
        keep = np.arange(len(times)) != 12
        sparse = subset(data, keep)
        sparse_times = times[keep]
        i = sparse_times.get_loc(times[5*78+14])
        self.assertEqual(signals(sparse, sparse_times, candidate("participation", 5, .2))[i, 1], 0)

    def test_prefix_causality_every_candidate_and_symbol_order(self):
        data, times = fixture(days=12)
        rng = np.random.default_rng(181118)
        close = 100*np.exp(np.cumsum(rng.normal(0, .004, data.close.shape), axis=0))
        data = replace(data, open=close*np.exp(rng.normal(0, .002, close.shape)), close=close,
                       high=close+rng.uniform(.1, .8, close.shape),
                       low=close-rng.uniform(.1, .8, close.shape),
                       volume=rng.uniform(1, 1000, close.shape))
        order = [2, 0, 3, 1]
        permuted = replace(data, symbols=tuple(SYMBOLS[j] for j in order), **{
            key: getattr(data, key)[:, order] for key in ("open", "high", "low", "close", "volume")})
        for c in candidates():
            full = signals(data, times, c)
            for n in (0, 1, 14, 15, 16, 77, 78, 79, 389, 404, 779, 803, 935):
                with self.subTest(c=c, n=n):
                    np.testing.assert_array_equal(signals(subset(data, slice(n)), times[:n], c), full[:n])
            self.assertFalse(np.any(full[np.arange(77, len(times), 78)]))
            np.testing.assert_array_equal(signals(permuted, times, c), full[:, order])
            for symbol, role in (("TQQQ", 1), ("SQQQ", 1), ("IBIT", -1), ("BITI", -1)):
                self.assertTrue(set(full[:, SYMBOLS.index(symbol)]).issubset({0, role}))


if __name__ == "__main__":
    unittest.main()
