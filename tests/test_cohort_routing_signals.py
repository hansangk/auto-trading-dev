import sys
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from autogrid.data import MarketData
from cohort_routing_signals_20261117 import (
    FAMILIES, PARAMETERS, _directions, _prior_efficiency, _route_directions,
    candidates, signal_fingerprint, signals,
)
from microstructure_signals_20261117 import _buy_roles, signals as component_signals

SYMBOLS = ("BITI", "SQQQ", "TQQQ", "IBIT")


def times_fixture(days=24, bars=7):
    dates = pd.bdate_range("2025-01-02", periods=days, tz="America/New_York")
    return pd.DatetimeIndex([d+pd.Timedelta(hours=9, minutes=30)+pd.Timedelta(hours=i)
                             for d in dates for i in range(bars)]).tz_convert("UTC")


def data_fixture(times):
    n = len(times)
    rng = np.random.default_rng(731)
    close = 100*np.exp(np.cumsum(rng.normal(0, .006, (n, 4)), axis=0))
    open_ = close*np.exp(rng.normal(0, .004, (n, 4)))
    high = np.maximum(open_, close)+rng.uniform(.1, .9, (n, 4))
    low = np.minimum(open_, close)-rng.uniform(.1, .9, (n, 4))
    return MarketData(np.asarray(times), SYMBOLS, open_, high, low, close,
                      rng.lognormal(5, 1, (n, 4)))


def candidate(family, p1=None, p2=None):
    return dict(family=family,
                p1=PARAMETERS[family][0][0] if p1 is None else p1,
                p2=PARAMETERS[family][1][0] if p2 is None else p2)


def route(family, gap, volume, p1=None, p2=None, close=None, first=None):
    gap = np.column_stack((gap, np.zeros(len(gap))))
    volume = np.column_stack((volume, np.zeros(len(volume))))
    n = len(gap)
    close = np.full((n, 2), 100.) if close is None else np.column_stack((close, np.full(n, 100.)))
    first = np.r_[True, np.zeros(n-1, dtype=bool)] if first is None else np.asarray(first)
    return _route_directions(gap, volume, close, np.full((n, 2), 2.), first,
                             np.full((n, 2), .3), candidate(family, p1, p2))[:, 0]


class CohortRoutingSignalsTests(unittest.TestCase):
    def test_complete_bounded_grid_and_fixed_risk(self):
        grid = candidates()
        self.assertEqual(len(grid), 64)
        self.assertEqual(len({c["name"] for c in grid}), 64)
        for family in FAMILIES:
            subset = [c for c in grid if c["family"] == family]
            self.assertEqual(len(subset), 16)
            self.assertEqual({c["p1"] for c in subset}, set(PARAMETERS[family][0]))
            self.assertEqual({c["p2"] for c in subset}, set(PARAMETERS[family][1]))
        self.assertEqual({c["hold"] for c in grid}, {2, 4})
        self.assertEqual({c["target"] for c in grid}, {2, 3})
        self.assertEqual({c["stop_bps"] for c in grid}, {60})
        self.assertEqual({c["max_etf_weight"] for c in grid}, {.15})

    def test_gap_reservation_time_and_favorable_progress_release(self):
        g, v = [1, 0, 0, 0, 0, 0], [1, -1, 1, -1, 1, -1]
        np.testing.assert_array_equal(route("gap_reservation", g, v, 2, .25),
                                      [1, 0, 0, -1, 1, -1])
        np.testing.assert_array_equal(route("gap_reservation", g, v, 4, .25),
                                      [1, 0, 0, 0, 0, -1])
        close = [100, 100.6, 99, 99, 99, 99]
        # Favorable .6 move releases .25*ATR2, irreversibly even after reversal.
        np.testing.assert_array_equal(route("gap_reservation", g, v, 4, .25, close), v)
        np.testing.assert_array_equal(route("gap_reservation", g, v, 4, .5, close),
                                      [1, 0, 0, 0, 0, -1])

    def test_takeover_requires_bounded_evidence_and_is_irreversible(self):
        g, v = [1, 0, 0, 0, 0, 0, 0], [1, -1, 0, 0, -1, 1, -1]
        np.testing.assert_array_equal(route("pressure_takeover", g, v, 2, 3),
                                      [1, 0, 0, 0, 0, 1, -1])
        np.testing.assert_array_equal(route("pressure_takeover", g, v, 2, 6),
                                      [1, 0, 0, 0, -1, 1, -1])
        np.testing.assert_array_equal(route("pressure_takeover", g, v, 3, 6),
                                      [1, 0, 0, 0, 0, 1, -1])

    def test_conflict_memory_veto_quarantine_and_expiration(self):
        g, v = [1, 0, 0, 0, 0, 0, 0], [1, 1, -1, 1, 1, -1, 1]
        np.testing.assert_array_equal(route("conflict_memory", g, v, 2, 1),
                                      [1, 1, 0, 1, 1, -1, 1])
        np.testing.assert_array_equal(route("conflict_memory", g, v, 2, 3),
                                      [1, 1, 0, 0, 0, -1, 1])
        np.testing.assert_array_equal(route("conflict_memory", g, v, 4, 1),
                                      [1, 1, 0, 1, 1, -1, 1])
        # Another conflict during memory extends the quarantine to its own end.
        v[4] = -1
        np.testing.assert_array_equal(route("conflict_memory", g, v, 4, 3),
                                      [1, 1, 0, 0, 0, 0, 0])

    def test_every_session_resets_reservation_takeover_and_quarantine(self):
        g, v = [1, 0, 0, 0, 0, 0], [1, -1, -1, -1, -1, -1]
        first = [True, False, False, True, False, False]
        for family in FAMILIES[:3]:
            actual = route(family, g, v, first=first)
            np.testing.assert_array_equal(actual[3:], [-1, -1, -1])
        # Prior-session opposite observations cannot count toward a fresh gap.
        g = [1, 0, 0, 1, 0, 0]
        v[3] = 1
        actual = route("pressure_takeover", g, v, 3, 6, first=first)
        np.testing.assert_array_equal(actual[3:], [1, 0, 0])

    def test_daily_regime_exact_deadband_and_prior_release(self):
        g = np.ones((5, 2))
        v = -np.ones((5, 2))
        efficiency = np.repeat(np.array([np.nan, .1, .2, .3, .6])[:, None], 2, axis=1)
        result = _route_directions(g, v, g, g, np.zeros(5), efficiency,
                                   candidate("daily_regime", .25, .05))
        np.testing.assert_array_equal(result[:, 0], [0, 1, 1, -1, -1])
        times = times_fixture(3, 2)
        open_ = np.full((6, 2), 100.)
        close = np.full((6, 2), 101.)
        high, low = np.full((6, 2), 102.), np.full((6, 2), 98.)
        prior = _prior_efficiency(open_, high, low, close, times)
        self.assertTrue(np.isnan(prior[:2]).all())
        np.testing.assert_allclose(prior[2:], .25)
        close[-1] = 102
        np.testing.assert_allclose(_prior_efficiency(open_, high, low, close, times),
                                   prior, equal_nan=True)

    def test_actual_buy_mapping_and_routing_never_manufacture_events(self):
        times = times_fixture()
        data = data_fixture(times)
        gap = component_signals(data, times, dict(family="gap_absorption", p1=.5, p2=.6))
        volume = component_signals(data, times, dict(family="volume_pressure", p1=6, p2=2))
        gd, vd = _directions(gap, SYMBOLS), _directions(volume, SYMBOLS)
        directions = np.array([[1, 1], [-1, -1], [1, -1], [-1, 1], [0, 0]])
        expected = [[0, 0, 1, -1], [-1, 1, 0, 0], [-1, 0, 1, 0], [0, 1, 0, -1], [0, 0, 0, 0]]
        np.testing.assert_array_equal(_buy_roles(directions, SYMBOLS), expected)
        np.testing.assert_array_equal(_directions(_buy_roles(directions, SYMBOLS), SYMBOLS), directions)
        for c in candidates()[::4]:
            scores = signals(data, times, c)
            routed = _directions(scores, SYMBOLS)
            self.assertTrue(np.all((routed == 0) | (routed == gd) | (routed == vd)))
            self.assertTrue(np.all(np.count_nonzero(scores, axis=1) <= 2))
            self.assertTrue(np.all(np.isin(scores, [-1, 0, 1])))
            self.assertTrue(np.all(scores[:, :2] * np.array([-1, 1]) >= 0))
            perm = [2, 3, 0, 1]
            other = replace(data, symbols=tuple(SYMBOLS[i] for i in perm),
                            **{k: getattr(data, k)[:, perm] for k in
                               ("open", "high", "low", "close", "volume")})
            np.testing.assert_array_equal(signals(other, times, c), scores[:, perm])

    def test_prefix_invariance_all_settings_and_partial_sessions(self):
        times = times_fixture()
        data = data_fixture(times)
        for c in candidates()[::4]:
            full = signals(data, times, c)
            for n in (0, 1, 104, 105, 108, 145, len(times)-1):
                truncated = replace(data, timestamps=data.timestamps[:n],
                                    **{k: getattr(data, k)[:n] for k in
                                       ("open", "high", "low", "close", "volume")})
                with self.subTest(family=c["family"], p1=c["p1"], p2=c["p2"], n=n):
                    np.testing.assert_array_equal(signals(truncated, times[:n], c), full[:n])

    def test_alias_identity_exit_variants_and_flat_empirical_aliases(self):
        times = times_fixture()
        data = data_fixture(times)
        for c in candidates()[::4]:
            scores = signals(data, times, c)
            alternate = signals(data, times, dict(c, hold=99, target=99))
            self.assertEqual(signal_fingerprint(scores), signal_fingerprint(alternate))
        # Flat data are a concrete counterexample to asserting16 distinct signals.
        flat = replace(data, **{k: np.full_like(getattr(data, k), 100.) for k in
                               ("open", "high", "low", "close", "volume")})
        hashes = {signal_fingerprint(signals(flat, times, c)) for c in candidates()[::4]}
        self.assertEqual(len(hashes), 1)
        self.assertNotEqual(signal_fingerprint(np.zeros((1, 4))),
                            signal_fingerprint(np.zeros((2, 4))))

    def test_invalid_settings_and_input_are_rejected(self):
        times = times_fixture()
        data = data_fixture(times)
        with self.assertRaises(ValueError):
            signals(data, times, candidate("gap_reservation", 99))
        with self.assertRaises(ValueError):
            signals(data, times, dict(family="unknown", p1=2, p2=1))
        with self.assertRaises(ValueError):
            signals(data, times[::-1], candidate("daily_regime"))
        with self.assertRaises(ValueError):
            signals(replace(data, symbols=("QQQ",)+SYMBOLS[1:]), times,
                    candidate("pressure_takeover"))


if __name__ == "__main__":
    unittest.main()
