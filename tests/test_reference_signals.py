import sys
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from autogrid.data import MarketData
from reference_signals_20261119 import FAMILIES, candidates, signals


SYMBOLS = ("BITI", "SQQQ", "TQQQ", "IBIT")


def fixture(days=2):
    dates = pd.bdate_range("2026-10-30", periods=days, tz="America/New_York")
    times = pd.DatetimeIndex([date + pd.Timedelta(minutes=570 + 5 * i)
                              for date in dates for i in range(78)]).tz_convert("UTC")
    p = np.tile(np.arange(78), days)
    logs = np.column_stack((.001 * p + .0002 * np.sin(p),
                            -.001 * p + .0002 * np.cos(p)))
    close = 100 * np.exp(logs)
    opening = close.copy()
    opening[1:] = close[:-1]
    opening[::78] = close[::78]
    refs = np.stack((opening, np.maximum(opening, close) * 1.001,
                     np.minimum(opening, close) * .999, close), axis=2)
    by_symbol = {"TQQQ": 3 * logs[:, 0], "SQQQ": -3 * logs[:, 0],
                 "IBIT": logs[:, 1], "BITI": -logs[:, 1]}
    etf = np.column_stack([100 * np.exp(by_symbol[s] + .0001 * np.sin(p * 1.7))
                           for s in SYMBOLS])
    data = MarketData(np.asarray(times), SYMBOLS, etf.copy(), etf * 1.001,
                      etf * .999, etf.copy(), np.ones_like(etf), bar_minutes=5)
    return data, times, refs


def subset(data, ix):
    return replace(data, timestamps=data.timestamps[ix], **{
        key: getattr(data, key)[ix] for key in ("open", "high", "low", "close", "volume")})


def candidate(family, a=None, b=None):
    return next(c for c in candidates() if c["family"] == family
                and (a is None or c["a"] == a) and (b is None or c["b"] == b))


class ReferenceSignalsTests(unittest.TestCase):
    def test_exact_sixteen_and_input_validation(self):
        grid = candidates()
        self.assertEqual(len(grid), 16)
        self.assertEqual(len({c["name"] for c in grid}), 16)
        for family in FAMILIES:
            self.assertEqual(sum(c["family"] == family for c in grid), 4)
        data, times, refs = fixture()
        c = grid[0]
        for bad in (refs[:, :, :3], refs[:-1]):
            with self.assertRaises(ValueError):
                signals(data, times, bad, c)
        with self.assertRaises(ValueError):
            signals(data, times + pd.Timedelta(minutes=5), refs, c)
        with self.assertRaises(ValueError):
            signals(replace(data, symbols=("QQQ", "SQQQ", "IBIT", "BITI")), times, refs, c)
        with self.assertRaises(ValueError):
            signals(data, times, refs, dict(family="tracking_catchup", a=99, b=1.))
        malformed = refs.copy()
        malformed[5, 0, 1] = .1
        with self.assertRaises(ValueError):
            signals(data, times, malformed, c)
        duplicate = times.to_list()
        duplicate[10] = duplicate[9]
        with self.assertRaises(ValueError):
            signals(data, duplicate, refs, c)
        irregular = times + pd.Timedelta(seconds=1)
        with self.assertRaises(ValueError):
            signals(replace(data, timestamps=np.asarray(irregular)), irregular, refs, c)

    def test_prefix_invariance_and_future_mutation_all_candidates(self):
        data, times, refs = fixture()
        # Exercise warmup boundaries, incomplete 15m bars and the DST transition.
        for c in candidates():
            full = signals(data, times, refs, c)
            for n in (1, 13, 20, 38, 51, 55, 77, 78, 79, 131):
                np.testing.assert_array_equal(signals(subset(data, slice(n)), times[:n], refs[:n], c), full[:n])
            changed_refs = refs.copy()
            changed_refs[55:] *= np.exp(np.arange(len(times) - 55)[:, None, None] * .02)
            changed_data = replace(data, close=data.close.copy())
            changed_data.close[55:] *= 1.1
            changed = signals(changed_data, times, changed_refs, c)
            np.testing.assert_array_equal(changed[:55], full[:55])
        self.assertEqual(str(times[0].tz_convert("America/New_York")), "2026-10-30 09:30:00-04:00")
        self.assertEqual(str(times[78].tz_convert("America/New_York")), "2026-11-02 09:30:00-05:00")

    def test_tracking_prior_48_and_actual_inverse_buy_roles(self):
        data, times, refs = fixture()
        for offset in (0, 78):
            data.close[offset + 55:offset + 58, SYMBOLS.index("TQQQ")] *= .995
            data.close[offset + 55:offset + 58, SYMBOLS.index("BITI")] *= .995
        c = candidate("tracking_catchup", 3, 2.)
        score = signals(data, times, refs, c)
        self.assertFalse(np.any(score[:51]))
        np.testing.assert_array_equal(score[55], [-1, 0, 1, 0])
        self.assertFalse(np.any(score[56:58]))  # onset, not repeated state
        self.assertFalse(np.any(score[78:129]))  # no overnight warmup carry
        np.testing.assert_array_equal(score[133], [-1, 0, 1, 0])
        # Current q cannot affect its own SD: an enormous residual stays eligible.
        data.close[55, SYMBOLS.index("TQQQ")] *= .5
        self.assertEqual(signals(data, times, refs, c)[55, SYMBOLS.index("TQQQ")], 1)
        # Coefficients do not transform or mutate the execution dataset.
        original = data.close.copy()
        signals(data, times, refs, c)
        np.testing.assert_array_equal(data.close, original)

    def test_completed_wall_clock_15m_sweep_only_and_inverse_roles(self):
        data, times, refs = fixture(days=1)
        refs[:] = [100, 101, 99, 100]
        for lookback in (6, 12):
            changed = refs.copy()
            p = lookback * 3
            changed[p:p + 3, 0] = [100, 101, 98, 100.8]
            changed[p:p + 3, 1] = [100, 102, 99, 99.2]
            for threshold in (.65, .8):
                c = candidate("sweep_reclaim_15m", lookback, threshold)
                score = signals(data, times, changed, c)
                self.assertFalse(np.any(score[:p + 2]))
                np.testing.assert_array_equal(score[p + 2], [-1, 0, 1, 0])
                self.assertTrue(np.all(np.flatnonzero(np.any(score, axis=1)) % 3 == 2))
                # Removing 09:30 must not move the 15m grid to 09:35.
                cut = signals(subset(data, slice(1, None)), times[1:], changed[1:], c)
                self.assertFalse(np.any(cut[:p + 2]))  # one complete prior bar is missing
                # A partial triple cannot emit a completed reference feature.
                self.assertFalse(np.any(signals(subset(data, slice(p + 2)), times[:p + 2], changed[:p + 2], c)))

    def test_shock_exhaustion_uses_previous_shock_and_current_reversal(self):
        data, times, refs = fixture(days=1)
        logs = .0001 * np.sin(np.arange(78))
        logs[20] = .01
        logs[21:] = .002
        close = 100 * np.exp(np.column_stack((logs, -logs)))
        refs[:, :, 0] = close
        refs[:, :, 1] = close * 1.001
        refs[:, :, 2] = close * .999
        refs[:, :, 3] = close
        c = candidate("shock_exhaustion", 1, 2.)
        score = signals(data, times, refs, c)
        np.testing.assert_array_equal(score[21], [0, 1, 0, -1])
        # Shock alone is insufficient; the source's next completed close matters.
        refs[21, :, :] = refs[20, :, :]
        self.assertFalse(np.any(signals(data, times, refs, c)[21]))

    def test_synchronization_onset_shifted_vol_and_session_reset(self):
        data, times, refs = fixture()
        p = np.tile(np.arange(78), 2)
        logs = .001 * p + .0001 * np.sin(p)
        close = 100 * np.exp(np.column_stack((logs, logs)))
        refs[:, :, 0] = close
        refs[:, :, 1] = close * 1.001
        refs[:, :, 2] = close * .999
        refs[:, :, 3] = close
        c = candidate("cross_reference_sync", 3, 1.)
        score = signals(data, times, refs, c)
        self.assertFalse(np.any(score[:13]))
        np.testing.assert_array_equal(score[13], [0, 0, 1, -1])
        self.assertFalse(np.any(score[14:78]))
        self.assertFalse(np.any(score[78:91]))
        np.testing.assert_array_equal(score[91], [0, 0, 1, -1])
        opposite = refs.copy()
        opposite[:, :, 0] = 10000 / refs[:, :, 0]
        opposite[:, :, 1] = 10000 / refs[:, :, 2]
        opposite[:, :, 2] = 10000 / refs[:, :, 1]
        opposite[:, :, 3] = 10000 / refs[:, :, 3]
        np.testing.assert_array_equal(signals(data, times, opposite, c)[13], [-1, 1, 0, 0])

    def test_missing_source_and_missing_clock_reset_without_fill(self):
        data, times, refs = fixture(days=1)
        data.close[55:58, SYMBOLS.index("TQQQ")] *= .995
        c = candidate("tracking_catchup", 3, 2.)
        self.assertEqual(signals(data, times, refs, c)[55, SYMBOLS.index("TQQQ")], 1)
        missing = refs.copy()
        missing[40, 0] = np.nan
        self.assertFalse(np.any(signals(data, times, missing, c)[:, [1, 2]]))
        ix = np.r_[np.arange(40), np.arange(41, len(times))]
        self.assertFalse(np.any(signals(subset(data, ix), times[ix], refs[ix], c)[:, [1, 2]]))
        # Entirely absent references mean cash, never a synthesized price path.
        missing[:] = np.nan
        for c in candidates():
            self.assertFalse(np.any(signals(data, times, missing, c)))

    def test_flat_reference_cash_and_no_two_directions_per_role(self):
        data, times, refs = fixture()
        for c in candidates():
            score = signals(data, times, refs, c)
            self.assertTrue(np.all(np.count_nonzero(score[:, [1, 2]], axis=1) <= 1))
            self.assertTrue(np.all(np.count_nonzero(score[:, [0, 3]], axis=1) <= 1))
            self.assertTrue(np.all(score[:, [1, 2]] >= 0))
            self.assertTrue(np.all(score[:, [0, 3]] <= 0))
            flat = np.full_like(refs, 100.)
            self.assertFalse(np.any(signals(data, times, flat, c)))


if __name__ == "__main__":
    unittest.main()
