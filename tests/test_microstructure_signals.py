import sys
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from autogrid.data import MarketData
from microstructure_signals_20261117 import (
    FAMILIES, PARAMETERS, _buy_roles, _prior_daily_stats, candidates, signals,
)

SYMBOLS = ("BITI", "SQQQ", "TQQQ", "IBIT")


def fixture(times, source_ohlcv=None):
    """Independent inverse ETF fixtures; never substitute negative source returns."""
    n = len(times)
    base = np.full((n, 2), 100.)
    if source_ohlcv is None:
        source_ohlcv = (base.copy(), base+1, base-1, base.copy(), base.copy())
    arrays = []
    for k, source in enumerate(source_ohlcv):
        inverse = np.column_stack((37+np.arange(n)*.001, 71+np.arange(n)*.002))
        if k == 1:
            inverse += .1
        elif k == 2:
            inverse -= .1
        elif k == 4:
            inverse[:] = 250.
        array = np.empty((n, 4))
        array[:, :2] = inverse
        array[:, 2:] = source
        arrays.append(array)
    return MarketData(np.asarray(times), SYMBOLS, *arrays)


def session_times(days=22, bars=4):
    dates = pd.bdate_range("2025-01-02", periods=days, tz="America/New_York")
    return pd.DatetimeIndex([d+pd.Timedelta(hours=9, minutes=30)+pd.Timedelta(hours=i)
                             for d in dates for i in range(bars)]).tz_convert("UTC")


def prefix(data, n):
    return replace(data, timestamps=data.timestamps[:n],
                   **{k: getattr(data, k)[:n] for k in
                      ("open", "high", "low", "close", "volume")})


def candidate(family, p1=None, p2=None):
    return dict(family=family, p1=PARAMETERS[family][0][0] if p1 is None else p1,
                p2=PARAMETERS[family][1][0] if p2 is None else p2)


class MicrostructureSignalsTests(unittest.TestCase):
    def test_complete_unique_grid_and_risk_parameters(self):
        grid = candidates()
        self.assertEqual(len(grid), 64)
        self.assertEqual(len({c["name"] for c in grid}), 64)
        self.assertEqual(len({tuple(sorted(c.items())) for c in grid}), 64)
        self.assertEqual({c["stop_bps"] for c in grid}, {60})
        self.assertEqual({c["max_etf_weight"] for c in grid}, {.15})
        for family in FAMILIES:
            subset = [c for c in grid if c["family"] == family]
            self.assertEqual(len(subset), 16)
            self.assertEqual({c["hold"] for c in subset}, {2, 4})
            self.assertEqual({c["target"] for c in subset}, {2, 3})

    def test_actual_buy_roles_with_independent_optional_assets(self):
        directions = np.array([[1, 1], [-1, -1], [1, -1], [-1, 1],
                               [0, 1], [-1, 0], [0, 0]])
        expected = [[0, 0, 1, -1], [-1, 1, 0, 0], [-1, 0, 1, 0],
                    [0, 1, 0, -1], [0, 0, 0, -1], [0, 1, 0, 0], [0, 0, 0, 0]]
        np.testing.assert_array_equal(_buy_roles(directions, SYMBOLS), expected)
        permutation = (2, 3, 0, 1)
        np.testing.assert_array_equal(
            _buy_roles(directions, tuple(SYMBOLS[i] for i in permutation)),
            np.asarray(expected)[:, permutation])

    def test_prior_daily_atr_and_no_current_session_final_information(self):
        times = session_times()
        data = fixture(times)
        source = [2, 3]
        stats = _prior_daily_stats(*(getattr(data, k)[:, source]
                                    for k in ("open", "high", "low", "close")), times)
        prior_close, prior_high, prior_low, atr, first = stats
        self.assertTrue(np.isnan(atr[:60]).all())
        np.testing.assert_allclose(atr[60:], 2.)
        np.testing.assert_allclose(prior_high[4:], 101.)
        np.testing.assert_allclose(prior_low[4:], 99.)
        np.testing.assert_allclose(prior_close[4:], 100.)
        self.assertEqual(int(first.sum()), 22)
        changed = replace(data, high=data.high.copy(), close=data.close.copy())
        changed.high[-1, 2:] = 400
        changed.close[-1, 2:] = 300
        altered = _prior_daily_stats(*(getattr(changed, k)[:, source]
                                      for k in ("open", "high", "low", "close")), times)
        for old, new in zip(stats, altered):
            np.testing.assert_allclose(old, new, equal_nan=True)

    def test_gap_fades_only_confirmed_first_completed_bar(self):
        times = session_times()
        data = fixture(times)
        i = 60  # 15 prior observed sessions, 14 valid true ranges
        data.open[i, 2:] = [98, 102]
        data.high[i, 2:] = [100, 103]
        data.low[i, 2:] = [97, 100]
        data.close[i, 2:] = [99.8, 100.2]
        c = candidate("gap_absorption", .5, .8)
        score = signals(data, times, c)
        np.testing.assert_array_equal(score[i], [-1, 0, 1, 0])
        self.assertFalse(np.any(score[:i]))
        self.assertFalse(np.any(score[i+1:i+4]))
        # Same first-bar gap without enough close-location reversal stays cash.
        data.close[i, 2:] = [98.5, 101.5]
        self.assertFalse(np.any(signals(data, times, c)[i]))
        # A non-first bar cannot create an overnight-gap event.
        data.open[i+1, 2:] = [98, 102]
        data.high[i+1, 2:] = [100, 103]
        data.low[i+1, 2:] = [97, 100]
        data.close[i+1, 2:] = [99.8, 100.2]
        self.assertFalse(np.any(signals(data, times, c)[i+1]))

    def test_volume_pressure_requires_current_volume_and_body_agreement(self):
        times = pd.date_range("2025-01-06 14:30", periods=40, freq="h", tz="UTC")
        data = fixture(times)
        data.open[:, 2:] = [99, 101]
        data.close[:, 2:] = [101, 99]
        data.volume[30, 2:] = 180
        c = candidate("volume_pressure", 6, 1.5)
        score = signals(data, times, c)
        np.testing.assert_array_equal(score[30], [-1, 0, 1, 0])
        self.assertFalse(np.any(signals(data, times, candidate("volume_pressure", 6, 2))[30]))
        self.assertFalse(np.any(score[:30]))
        data.open[30, 2:] = [101, 99]
        data.close[30, 2:] = [99, 101]
        self.assertFalse(np.any(signals(data, times, c)[30]))

    def test_cross_response_only_bitcoin_and_prior_fitted_residual(self):
        n = 100
        times = pd.date_range("2025-01-06 14:30", periods=n, freq="h", tz="UTC")
        t = np.arange(n)
        x = .001*np.sin(t*.73)+.0007*np.cos(t*.13)
        y = .4*np.r_[0., x[:-1]]+.0003*np.sin(t*1.13)
        for shock, expected in ((-.03, [0, 0, 0, -1]), (.03, [-1, 0, 0, 0])):
            observed_y = y.copy()
            observed_y[-1] = shock
            close = 100*np.exp(np.cumsum(np.column_stack((x, observed_y)), axis=0))
            data = fixture(times, (close.copy(), close+.1, close-.1,
                                   close, np.full_like(close, 100.)))
            score = signals(data, times, candidate("cross_response", 1, 1.25))
            np.testing.assert_array_equal(score[-1], expected)
            self.assertFalse(np.any(score[:, 1:3]))
            # Inverse prices are real input paths, not produced by negating proxies.
            inverse_before = data.close[:, :2].copy()
            altered = replace(data, **{k: getattr(data, k).copy() for k in
                                      ("open", "high", "low", "close")})
            for k in ("open", "high", "low", "close"):
                getattr(altered, k)[:, :2] *= 3
            np.testing.assert_array_equal(signals(altered, times, candidate("cross_response", 1, 1.25)), score)
            np.testing.assert_array_equal(data.close[:, :2], inverse_before)

    def test_failed_breakout_penetration_timeout_and_no_persistent_rearm(self):
        times = session_times()
        data = fixture(times)
        i = 60
        data.high[i:i+2, 2:] = [101.6, 99]
        data.low[i:i+2, 2:] = [101.1, 98.4]
        data.open[i:i+2, 2:] = [101.4, 98.6]
        data.close[i:i+2, 2:] = [101.5, 98.5]
        # Re-enter on the second subsequent bar; timeout1 must already expire.
        score1 = signals(data, times, candidate("failed_breakout", .25, 1))
        score2 = signals(data, times, candidate("failed_breakout", .25, 2))
        self.assertFalse(np.any(score1[i:i+4]))
        np.testing.assert_array_equal(score2[i+2], [0, 1, 0, -1])
        self.assertFalse(np.any(score2[i:i+2]))
        self.assertFalse(np.any(signals(data, times, candidate("failed_breakout", .5, 2))[i:i+4]))
        # Same-bar rejection is observable and emits once, with persistent
        # penetration not rearming another copy of the same excursion.
        data.close[i, 2:] = [100, 100]
        data.open[i, 2:] = 100
        data.low[i, 2] = 99
        data.high[i, 3] = 101
        np.testing.assert_array_equal(signals(data, times, candidate("failed_breakout"))[i], [0, 1, 0, -1])

    def test_ambiguous_two_sided_breakout_is_cash(self):
        times = session_times()
        data = fixture(times)
        data.high[60, 2:] = 103
        data.low[60, 2:] = 97
        self.assertFalse(np.any(signals(data, times, candidate("failed_breakout"))[60]))

    def test_prefix_invariance_including_partial_sessions_all_signal_settings(self):
        times = session_times(24, 7)
        n = len(times)
        rng = np.random.default_rng(717)
        close = 100*np.exp(np.cumsum(rng.normal(0, .004, (n, 2)), axis=0))
        open_ = close*np.exp(rng.normal(0, .003, (n, 2)))
        high = np.maximum(open_, close)+rng.uniform(.1, .9, (n, 2))
        low = np.minimum(open_, close)-rng.uniform(.1, .9, (n, 2))
        volume = rng.lognormal(5, 1, (n, 2))
        data = fixture(times, (open_, high, low, close, volume))
        for c in candidates()[::4]:
            full = signals(data, times, c)
            for length in (0, 1, 36, 104, 105, 108, 145, n-1):
                with self.subTest(family=c["family"], p1=c["p1"], p2=c["p2"], n=length):
                    np.testing.assert_array_equal(
                        signals(prefix(data, length), times[:length], c), full[:length])
            # Exit variants cannot change the event definition.
            np.testing.assert_array_equal(signals(data, times, dict(c, hold=99, target=99)), full)

    def test_flat_zero_volume_is_cash_and_bad_inputs_rejected(self):
        times = session_times()
        data = fixture(times)
        data.volume[:] = 0
        for c in candidates()[::4]:
            self.assertFalse(np.any(signals(data, times, c)))
        with self.assertRaises(ValueError):
            signals(data, times[::-1], candidate("gap_absorption"))
        with self.assertRaises(ValueError):
            signals(data, times, candidate("cross_response", 3))
        with self.assertRaises(ValueError):
            signals(replace(data, symbols=("QQQ",)+SYMBOLS[1:]), times,
                    candidate("volume_pressure"))


if __name__ == "__main__":
    unittest.main()
