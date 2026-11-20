import sys
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from autogrid.data import MarketData
from episode_signals_20261118 import FAMILIES, _episode_start, candidates, signals

SYMBOLS = ("BITI", "SQQQ", "TQQQ", "IBIT")


def fixture(closes=None, days=1):
    dates = pd.bdate_range("2026-10-19", periods=days, tz="America/New_York")
    times = pd.DatetimeIndex([day + pd.Timedelta(minutes=570+5*i)
                              for day in dates for i in range(78)]).tz_convert("UTC")
    close = np.tile([37., 50., 100., 100.], (len(times), 1))
    if closes is not None:
        close[:len(closes)*3, 2] = np.repeat(closes, 3)
    return (MarketData(np.asarray(times), SYMBOLS, close.copy(), close+1,
                       close-1, close, np.ones_like(close), bar_minutes=5), times)


def candidate(family, a, b):
    return dict(family=family, a=a, b=b)


def prefix(data, n):
    return replace(data, timestamps=data.timestamps[:n], **{
        k: getattr(data, k)[:n] for k in ("open", "high", "low", "close", "volume")})


class EpisodeSignalsTests(unittest.TestCase):
    def test_unique_bounded_grid(self):
        grid = candidates()
        self.assertEqual(len(grid), 16)
        self.assertEqual(len({c["name"] for c in grid}), 16)
        for family in FAMILIES:
            self.assertEqual(sum(c["family"] == family for c in grid), 4)

    def test_completed_neutral_rearm_ignores_five_minute_zero_rows(self):
        data, times = fixture([100]*4 + [102]*5 + [104])
        one = signals(data, times, candidate("onset", 1, 0))
        two = signals(data, times, candidate("onset", 2, 0))
        # Momentum is persistent at 14/17/20/23, genuinely neutral at 26.
        self.assertEqual(np.flatnonzero(one[:, 2]).tolist()[:2], [14, 29])
        self.assertEqual(np.flatnonzero(two[:, 2]).tolist()[:1], [14])
        self.assertEqual(two[29, 2], 0)
        self.assertFalse(np.any(one[np.arange(len(times)) % 3 != 2]))
        state = dict(direction=0, neutral=0)
        self.assertTrue(_episode_start(1, state, 2))
        self.assertFalse(_episode_start(0, state, 2))
        self.assertFalse(_episode_start(1, state, 2))
        _episode_start(0, state, 2)
        _episode_start(0, state, 2)
        self.assertTrue(_episode_start(1, state, 2))

    def test_direction_flip_refractory_and_actual_inverse_buy(self):
        data, times = fixture([100]*4 + [102, 98])
        immediate = signals(data, times, candidate("onset", 1, 0))
        refractory = signals(data, times, candidate("onset", 1, 3))
        self.assertEqual(immediate[14, SYMBOLS.index("TQQQ")], 1)
        self.assertEqual(immediate[17, SYMBOLS.index("SQQQ")], 1)
        self.assertFalse(np.any(refractory[17]))
        # Bitcoin role carries -1 for either actual ETF, never a synthetic short.
        data.close[:, 3] = data.close[:, 2]
        data.high[:, 3] = data.high[:, 2]
        data.low[:, 3] = data.low[:, 2]
        score = signals(data, times, candidate("onset", 1, 0))
        self.assertEqual(score[14, SYMBOLS.index("IBIT")], -1)
        self.assertEqual(score[17, SYMBOLS.index("BITI")], -1)

    def test_retest_requires_earlier_bar_excursion_and_selected_etf_prices(self):
        data, times = fixture([100]*4 + [98]*5)
        data.low[15:, 1] = 49.8
        data.low[15, 1] = 49.4  # Crosses .25*2 below the real SQQQ anchor 50.
        quarter = signals(data, times, candidate("retest", .25, 1))
        half = signals(data, times, candidate("retest", .5, 1))
        self.assertFalse(np.any(quarter[15]))  # excursion+reclaim is ambiguous
        self.assertEqual(quarter[16, 1], 1)
        self.assertEqual(half[16, 1], 0)
        self.assertEqual(np.count_nonzero(quarter[14:26]), 1)
        data.close[16, 1] = 49.9
        self.assertEqual(signals(data, times, candidate("retest", .25, 1))[16, 1], 0)

    def test_retest_timeout_counts_completed_fifteen_minute_bars(self):
        data, times = fixture([100]*4 + [98]*5)
        data.low[15:, 1] = 49.8
        data.low[18, 1] = 49.4
        data.close[18, 1] = 49.4
        self.assertFalse(np.any(signals(data, times, candidate("retest", .25, 1))[14:21]))
        self.assertEqual(signals(data, times, candidate("retest", .25, 2))[19, 1], 1)

    def test_chase_wait_close_and_frozen_actual_etf_range(self):
        data, times = fixture([100]*4 + [98]*5)
        data.close[15, 1] = 50.6
        data.high[15, 1] = 51
        tight = signals(data, times, candidate("chasecancel", 1, .25))
        loose = signals(data, times, candidate("chasecancel", 1, .5))
        self.assertFalse(np.any(tight[14:26]))
        self.assertEqual(loose[15, 1], 1)
        self.assertEqual(signals(data, times, candidate("chasecancel", 3, .25))[17, 1], 1)
        # Changing the waiting bar high cannot enlarge the preceding frozen range.
        data.high[15, 1] = 500
        self.assertEqual(signals(data, times, candidate("chasecancel", 1, .25))[15, 1], 0)

    def test_compression_uses_prior_ranges_and_freezes_box(self):
        data, times = fixture()
        # Four broad reference bars, followed by two narrow bars.
        data.high[:12, 2] = 102
        data.low[:12, 2] = 98
        data.high[12:18, 2] = 100.5
        data.low[12:18, 2] = 99.5
        # Their mean range is 2: one range may exceed the threshold individually.
        data.high[15:18, 2] = 101.5
        data.low[15:18, 2] = 98.5
        # Current huge range cannot prevent a prior-feature compression setup.
        data.high[18:21, 2] = 120
        data.low[18:21, 2] = 80
        data.close[20, 2] = 100.2
        data.close[23, 2] = 102
        score = signals(data, times, candidate("compression", .5, 4))
        self.assertEqual(score[20, 2], 0)
        self.assertEqual(score[23, 2], 1)  # frozen 101.5 box, not current 120 high
        self.assertEqual(np.count_nonzero(score[:27]), 1)
        self.assertFalse(np.any(signals(data, times, candidate("compression", .5, 8))[:27]))

    def test_prefix_causality_all_candidates_and_session_resets(self):
        data, times = fixture(days=3)
        rng = np.random.default_rng(1811)
        close = 100*np.exp(np.cumsum(rng.normal(0, .004, data.close.shape), axis=0))
        data = replace(data, open=close.copy(), close=close,
                       high=close+rng.uniform(.1, .8, close.shape),
                       low=close-rng.uniform(.1, .8, close.shape))
        for c in candidates():
            full = signals(data, times, c)
            for n in (0, 1, 14, 15, 16, 77, 78, 79, 101, 157, 233):
                with self.subTest(c=c, n=n):
                    np.testing.assert_array_equal(signals(prefix(data, n), times[:n], c), full[:n])
            self.assertFalse(np.any(full[[77, 155, 233]]))
            start = 78
            session = replace(data, timestamps=data.timestamps[start:156], **{
                k: getattr(data, k)[start:156] for k in ("open", "high", "low", "close", "volume")})
            np.testing.assert_array_equal(signals(session, times[start:156], c), full[start:156])

    def test_symbol_order_independent_and_flat_is_cash(self):
        data, times = fixture([100]*4 + [98]*5)
        order = [2, 0, 3, 1]
        permuted = replace(data, symbols=tuple(SYMBOLS[j] for j in order), **{
            k: getattr(data, k)[:, order] for k in ("open", "high", "low", "close", "volume")})
        for c in candidates():
            np.testing.assert_array_equal(signals(permuted, times, c), signals(data, times, c)[:, order])
        flat, times = fixture()
        for c in candidates():
            self.assertFalse(np.any(signals(flat, times, c)))


if __name__ == "__main__":
    unittest.main()
