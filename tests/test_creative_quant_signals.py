import sys
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from autogrid.data import MarketData
from creative_quant_signals_20261116 import (
    FAMILIES, _buy_roles, _daily_score, candidates, signals,
)


def market(log_paths, times, symbols=("BITI", "SQQQ", "TQQQ", "IBIT")):
    paths = {"TQQQ": log_paths[:, 0], "SQQQ": -log_paths[:, 0],
             "IBIT": log_paths[:, 1], "BITI": -log_paths[:, 1]}
    close = np.column_stack([100 * np.exp(paths[s]) for s in symbols])
    return MarketData(np.asarray(times), symbols, close.copy(), close.copy(),
                      close.copy(), close, np.ones_like(close))


class CreativeQuantTests(unittest.TestCase):
    def test_complete_grid_and_fixed_protections(self):
        grid = candidates()
        self.assertEqual(len(grid), 64)
        self.assertEqual(len({c["name"] for c in grid}), 64)
        for family in FAMILIES:
            self.assertEqual(sum(c["family"] == family for c in grid), 16)
        self.assertEqual({c["stop_bps"] for c in grid}, {60})
        self.assertEqual({c["max_etf_weight"] for c in grid}, {.15})

    def test_all_direction_roles_and_independent_cash(self):
        symbols = ("BITI", "SQQQ", "TQQQ", "IBIT")
        direction = np.array([[1, 1], [-1, -1], [1, -1], [-1, 1],
                              [0, 1], [-1, 0], [0, 0]])
        expected = [[0, 0, 1, -1], [-1, 1, 0, 0], [-1, 0, 1, 0],
                    [0, 1, 0, -1], [0, 0, 0, -1], [0, 1, 0, 0], [0, 0, 0, 0]]
        np.testing.assert_array_equal(_buy_roles(direction, symbols), expected)

    def test_trend_buys_actual_inverse_instruments(self):
        n = 180
        t = np.arange(n)
        paths = np.column_stack((.002*t + .0004*np.sin(t),
                                 -.002*t + .0004*np.cos(t)))
        times = pd.date_range("2025-01-06 14:30", periods=n, freq="min", tz="UTC")
        data = market(paths, times)
        candidate = next(c for c in candidates() if c["family"] == "volatility_trend")
        score = signals(data, times, candidate)
        np.testing.assert_array_equal(score[-1], [-1, 0, 1, 0])
        opposite = market(-paths, times)
        np.testing.assert_array_equal(signals(opposite, times, candidate)[-1], [0, 1, 0, -1])

    def test_reversion_fades_a_price_shock(self):
        t = np.arange(80)
        paths = np.column_stack((.001*np.sin(t), .001*np.cos(t)))
        paths[-1] = [.03, -.03]
        times = pd.date_range("2025-01-06 14:30", periods=len(t), freq="min", tz="UTC")
        candidate = next(c for c in candidates() if c["family"] == "zscore_reversion")
        np.testing.assert_array_equal(signals(market(paths, times), times, candidate)[-1],
                                      [0, 1, 0, -1])

    def test_channel_retains_breakout_until_opposite_break(self):
        x = np.r_[.001*np.sin(np.arange(70)), .01, .009, .008, .007, -.01]
        times = pd.date_range("2025-01-06 14:30", periods=len(x), freq="min", tz="UTC")
        candidate = dict(family="channel_state", window=12, threshold=.75)
        score = signals(market(np.column_stack((x, -x)), times), times, candidate)
        # The retreat bars are below the previous maximum; no fresh breakout.
        np.testing.assert_array_equal(score[-5:-1], np.tile([-1, 0, 1, 0], (4, 1)))
        np.testing.assert_array_equal(score[-1], [0, 1, 0, -1])

    def test_completed_daily_regime_is_fixed_within_session(self):
        dates = pd.bdate_range("2025-01-02", periods=40, tz="America/New_York")
        times = pd.DatetimeIndex([d + pd.Timedelta(hours=9, minutes=30 + 5*i)
                                  for d in dates for i in range(12)]).tz_convert("UTC")
        t = np.arange(len(times))
        paths = np.column_stack((.0006*t + .006*np.sin(t/19),
                                 -.0004*t + .007*np.cos(t/17)))
        x = pd.DataFrame(paths)
        full = _daily_score(x, times, 12)
        self.assertTrue(np.isfinite(full[-12:]).all())
        for start in range(0, len(times), 12):
            np.testing.assert_allclose(full[start:start+12],
                                       np.tile(full[start], (12, 1)), equal_nan=True)
        changed = x.copy()
        changed.iloc[-1] += [2., -2.]
        np.testing.assert_allclose(_daily_score(changed, times, 12), full, equal_nan=True)
        # Prefixes deliberately cut sessions, including immediately before close.
        data = market(paths, times)
        for family in FAMILIES:
            for window in (12, 24):
                candidate = dict(family=family, window=window, threshold=.75)
                score = signals(data, times, candidate)
                for n in (1, 57, 167, 335, 479):
                    prefix = replace(data, timestamps=data.timestamps[:n],
                                     **{k: getattr(data, k)[:n] for k in
                                        ("open", "high", "low", "close", "volume")})
                    np.testing.assert_array_equal(signals(prefix, times[:n], candidate), score[:n])

    def test_exit_grid_does_not_change_entry_logic_and_flat_is_cash(self):
        times = pd.date_range("2025-01-06 14:30", periods=80, freq="min", tz="UTC")
        data = market(np.zeros((len(times), 2)), times)
        for candidate in candidates():
            score = signals(data, times, candidate)
            self.assertTrue(np.isfinite(score).all())
            self.assertFalse(np.any(score))
            alternate = dict(candidate, hold=99, target=99)
            np.testing.assert_array_equal(score, signals(data, times, alternate))


if __name__ == "__main__":
    unittest.main()
