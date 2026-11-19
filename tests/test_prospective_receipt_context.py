"""Synthetic context/receipt boundaries; no market request or account replay."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from autogrid.data import MarketData
from prospective_receipt_context_20261120 import build_context, receipt_gate


class ProspectiveReceiptContextTests(unittest.TestCase):
    def fixture(self):
        times = pd.date_range('2026-11-19T14:30:00Z', periods=7, freq='h')
        a = np.ones((7, 4))
        data = MarketData(times.to_numpy(), ('TQQQ', 'SQQQ', 'IBIT', 'BITI'),
                          100*a, 102*a, 99*a, 101*a, 500*a, bar_minutes=60)
        schedule = pd.DataFrame([dict(day='2026-11-19',
                                     open=pd.Timestamp('2026-11-19T14:30:00Z'),
                                     close=pd.Timestamp('2026-11-19T21:00:00Z'))]).set_index('day')
        rows = []
        for i, t in enumerate(pd.date_range('2026-11-19T06:30:00Z', periods=29, freq='30min')):
            start = t.value // 10**6
            volume = 10. + i
            buy = volume * (.2 if i % 2 == 0 else .8)
            rows.append([int(start), 100.+i, 102.+i, 99.+i, 101.+i,
                         volume, int(start+1800000-1), 100.*volume, 10,
                         buy, 100.*buy, 0])
        return data, rows, schedule

    def assert_context_equal(self, a, b):
        self.assertEqual(set(a), set(b))
        for key in a:
            if isinstance(a[key], dict):
                self.assertEqual(set(a[key]), set(b[key]))
                for field in a[key]:
                    np.testing.assert_array_equal(a[key][field], b[key][field])
            else:
                np.testing.assert_array_equal(a[key], b[key])

    def test_first_valid_row_requires_known_same_day_source_start(self):
        data, rows, schedule = self.fixture()
        ctx, trace = build_context(data, rows, schedule)
        np.testing.assert_array_equal(ctx['valid'], [False, True, True, True, True, True, True])
        self.assertEqual([r['index'] for r in trace], list(range(1, 7)))
        first = trace[0]
        self.assertEqual(pd.Timestamp(first['decision']), pd.Timestamp('2026-11-19T16:30:00Z'))
        self.assertEqual(pd.Timestamp(first['source_start']), pd.Timestamp('2026-11-19T14:30:00Z'))
        self.assertEqual(pd.Timestamp(first['source_end']), pd.Timestamp('2026-11-19T15:30:00Z'))
        self.assertEqual(len(first['required_source_starts']), 10)
        expected = pd.date_range('2026-11-19T10:30:00Z', periods=10, freq='30min')
        self.assertEqual([pd.Timestamp(t) for t in first['required_source_starts']], list(expected))
        for key in ('history1', 'history4', 'history8'):
            self.assertTrue(np.asarray(ctx[key])[1:].all())

    def test_contiguous_halfhours_use_volume_weighted_taker_ratio(self):
        data, rows, schedule = self.fixture()
        ctx, _ = build_context(data, rows, schedule)
        x, y = rows[16:18]
        self.assertEqual(ctx['current']['open'][1], x[1])
        self.assertEqual(ctx['current']['close'][1], y[4])
        self.assertEqual(ctx['current']['high'][1], max(x[2], y[2]))
        self.assertEqual(ctx['current']['low'][1], min(x[3], y[3]))
        self.assertEqual(ctx['current']['flow'][1], 2*(x[9]+y[9])/(x[5]+y[5])-1)
        self.assertNotAlmostEqual(ctx['current']['flow'][1], 0.)
        self.assertEqual(ctx['prior']['open'][1], rows[14][1])

    def test_prior_means_exclude_current_and_preserve_eight_hour_guard(self):
        data, rows, schedule = self.fixture()
        ctx, _ = build_context(data, rows, schedule)
        flows = [2*(rows[i][9]+rows[i+1][9])/(rows[i][5]+rows[i+1][5])-1
                 for i in range(0, 18, 2)]
        self.assertEqual(ctx['flow_mean4'][1], np.mean(flows[4:8]))
        self.assertEqual(ctx['flow_mean8'][1], np.mean(flows[:8]))
        shortened, _ = build_context(data, rows[8:], schedule)
        self.assertFalse(shortened['valid'][1])  # L4 alone would be available.
        self.assertFalse(shortened['valid'][4])
        self.assertTrue(shortened['valid'][5])

    def test_later_source_outlier_cannot_change_earlier_context(self):
        data, rows, schedule = self.fixture()
        baseline, _ = build_context(data, rows, schedule)
        changed = deepcopy(rows)
        for row in changed[24:]:
            row[1:5] = [1e6, 2e6, 5e5, 1.5e6]
            row[9], row[10] = row[5], row[7]
        actual, _ = build_context(data, changed, schedule)
        for key in baseline:
            if isinstance(baseline[key], dict):
                for field in baseline[key]:
                    np.testing.assert_array_equal(baseline[key][field][:5], actual[key][field][:5])
            else:
                np.testing.assert_array_equal(baseline[key][:5], actual[key][:5])

    def test_etf_prefix_preserves_previously_observable_context(self):
        data, rows, schedule = self.fixture()
        complete, _ = build_context(data, rows, schedule)
        for n in (1, 2, 4, 6):
            prefix = replace(data, timestamps=data.timestamps[:n],
                             **{k: getattr(data, k)[:n] for k in ('open', 'high', 'low', 'close', 'volume')})
            actual, _ = build_context(prefix, rows, schedule)
            expected = {k: ({f: a[:n] for f, a in v.items()} if isinstance(v, dict) else v[:n])
                        for k, v in complete.items()}
            self.assert_context_equal(expected, actual)

    def test_source_gaps_duplicates_bad_span_and_taker_bounds_reject(self):
        data, rows, schedule = self.fixture()
        cases = [rows[:5]+rows[6:], rows+[rows[-1]], deepcopy(rows), deepcopy(rows), deepcopy(rows)]
        cases[2][3][6] += 1
        cases[3][3][9] = cases[3][3][5]+1
        cases[4][3] = cases[4][3][:-1]
        for bad in cases:
            with self.subTest(rows=len(bad)), self.assertRaises(ValueError):
                build_context(data, bad, schedule)

    def gate(self, etf='2026-11-19T16:30:00Z', source='2026-11-19T16:30:00Z'):
        key = '2026-11-19T14:30:00+00:00'
        return receipt_gate('2026-11-19T16:30:00Z', [etf]*4, {key: source}, [key],
                            '2026-11-19T17:30:00Z')

    def test_receipt_exact_boundary_is_observed_but_never_engine_permission(self):
        got = self.gate()
        self.assertTrue(got['observed_by_decision'])
        self.assertTrue(got['observed_by_entry'])
        self.assertIs(got['terminal_backtest_allowed'], False)

    def test_later_receipt_cannot_backdate_original_decision(self):
        for etf, source in [('2026-11-19T16:30:00.000001Z', '2026-11-19T16:30:00Z'),
                            ('2026-11-19T16:30:00Z', '2026-11-19T16:30:00.000001Z'),
                            ('2026-11-19T17:07:35Z', '2026-11-19T16:06:22Z')]:
            with self.subTest(etf=etf, source=source):
                got = self.gate(etf, source)
                self.assertFalse(got['observed_by_decision'])
                self.assertTrue(got['observed_by_entry'])
                self.assertIs(got['terminal_backtest_allowed'], False)

    def test_receipt_after_entry_is_unobservable_for_both_deadlines(self):
        for etf, source in [('2026-11-19T17:30:00.000001Z', '2026-11-19T16:30:00Z'),
                            ('2026-11-19T16:30:00Z', '2026-11-19T17:30:00.000001Z')]:
            with self.subTest(etf=etf, source=source):
                got = self.gate(etf, source)
                self.assertFalse(got['observed_by_decision'])
                self.assertFalse(got['observed_by_entry'])

    def test_missing_empty_naive_and_nonstring_receipts_fail_closed(self):
        key = '2026-11-19T14:30:00+00:00'
        good = '2026-11-19T16:30:00Z'
        cases = [([], {key: good}, [key]), ([good]*4, {}, [key]),
                 (['2026-11-19T16:30:00']*4, {key: good}, [key]),
                 ([good]*4, {key: '2026-11-19T16:30:00'}, [key]),
                 ([pd.Timestamp(good)]*4, {key: good}, [key]),
                 ([good]*4, {key: pd.Timestamp(good)}, [key])]
        for etfs, source, starts in cases:
            with self.subTest(etfs=etfs, source=source), self.assertRaises(ValueError):
                receipt_gate(good, etfs, source, starts, '2026-11-19T17:30:00Z')


if __name__ == '__main__':
    unittest.main()
