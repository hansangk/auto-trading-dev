import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from latency_schedules_20261119 import configurations, cohort_scores, schedule, rawpaired_labels, FUTURE_ALPHA_PROPOSALS


def fixture():
    days = pd.to_datetime(["2026-10-30", "2026-11-02"]).tz_localize("America/New_York")
    times = pd.DatetimeIndex([d + pd.Timedelta(minutes=570 + 60*i) for d in days for i in range(7)]).tz_convert("UTC")
    prices = np.full((14, 4), 100.)
    data = SimpleNamespace(timestamps=times, open=prices.copy(), close=prices.copy())
    return data, times


class LatencyScheduleTests(unittest.TestCase):
    def test_fixed_grid_and_unimplemented_metadata(self):
        grid = configurations()
        self.assertEqual(len(grid), 16)
        self.assertEqual(len({x['name'] for x in grid}), 16)
        self.assertEqual({f: sum(x['family'] == f for x in grid) for f in 'ABCD'}, dict.fromkeys('ABCD', 4))
        self.assertEqual(sum(x['cohort'] == 'common' for x in grid), 8)
        self.assertEqual(len(FUTURE_ALPHA_PROPOSALS), 4)
        self.assertTrue(all(x['status'] == 'UNIMPLEMENTED' and not x['actual_point_in_time_feeds'] for x in FUTURE_ALPHA_PROPOSALS))

    def test_calendar_mask_prefix_invariance_and_no_mutation(self):
        _, times = fixture()
        scores = np.ones((14, 4))
        common = cohort_scores(scores, times, 'common')
        self.assertEqual(np.flatnonzero(common[:, 0]).tolist(), [0, 1, 7, 8])
        for length in range(1, 15):
            np.testing.assert_array_equal(cohort_scores(scores[:length], times[:length], 'common'), common[:length])
        native = cohort_scores(scores, times, 'native')
        native[0, 0] = 9
        self.assertEqual(scores[0, 0], 1)
        with self.assertRaises(ValueError): cohort_scores(scores[:, :3], times, 'common')

    def test_dst_uses_ny_dates_and_actual_close(self):
        _, times = fixture()
        self.assertEqual((times[0].hour, times[7].hour), (13, 14))
        for k in [0, 7]:
            a = schedule(times, k, 4, 0)
            c = schedule(times, k, 3, 1)
            self.assertEqual(a['exit_time'], c['exit_time'])
            self.assertEqual(a['duration_minutes'], 240)
            self.assertEqual(c['duration_minutes'], 180)
        for k in [1, 8]:
            b = schedule(times, k, 4, 1)
            self.assertEqual(b['duration_minutes'], 210)
            self.assertTrue(b['full_bar_count'])
            self.assertFalse(b['full_hour_bars'])
            self.assertFalse(b['clipped'])
            self.assertEqual(b['exit_time'].tz_convert('America/New_York').strftime('%H:%M'), '16:00')

    def test_all_event_clock_support_flags(self):
        data, times = fixture()
        rows = [rawpaired_labels(data, times, k, 1) for k in range(7)]
        self.assertEqual([i for i, r in enumerate(rows) if r['equalwall4A_B']], [0])
        self.assertEqual([i for i, r in enumerate(rows) if r['equalbarsA_B']], [0, 1])
        self.assertEqual([i for i, r in enumerate(rows) if r['equalwall3D_C']], [0, 1])
        self.assertTrue(all(rows[k]['sameexitA_C'] for k in range(5)))
        self.assertIsNone(rows[5]['B'])
        self.assertIsNone(rows[6]['A'])
        self.assertIsNone(schedule(times, 5, 4, 1))
        self.assertTrue(schedule(times, 4, 4, 0)['clipped'])
        for row in rows:
            for name in 'ABCD':
                if row[name] is not None:
                    self.assertLessEqual(row[name]['exit_time'].tz_convert('America/New_York').hour, 16)

    def test_inverse_etf_is_actual_purchase_not_negative_bull(self):
        data, times = fixture()
        data.close[4, 0] = 110
        data.close[4, 1] = 103
        bull = rawpaired_labels(data, times, 0, 0)['A']['gross_return']
        inverse = rawpaired_labels(data, times, 0, 1)['A']['gross_return']
        self.assertAlmostEqual(bull, .10)
        self.assertAlmostEqual(inverse, .03)
        self.assertNotAlmostEqual(inverse, -bull)
        data.open[1, 1] = np.nan
        with self.assertRaises(ValueError): rawpaired_labels(data, times, 0, 1)

    def test_invalid_clocks_missing_bars_and_no_synthetic_completion(self):
        _, times = fixture()
        for bad in [times.delete(3), times.delete(0), times.delete(6), times[:6]]:
            with self.assertRaises(ValueError): schedule(bad, 0, 4, 0)
        bad = times.copy().to_list()
        bad[3] += pd.Timedelta(minutes=1)
        with self.assertRaises(ValueError): schedule(bad, 0, 4, 0)
        with self.assertRaises(ValueError): schedule(times, 0, 0, 0)
        with self.assertRaises(ValueError): schedule(times, 0, 4, -1)


if __name__ == '__main__':
    unittest.main()
