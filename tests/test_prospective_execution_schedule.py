import inspect
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prospective_execution_schedule_20261120 import plan_event, qualify_marks


class ProspectiveExecutionScheduleTests(unittest.TestCase):
    def plan(self, **changes):
        fields = dict(event_start='2026-11-19T15:30:00Z',
                      source_end='2026-11-19T15:30:00Z',
                      ready='2026-11-19T17:07:35.656109Z',
                      opened='2026-11-19T14:30:00Z',
                      closed='2026-11-19T21:00:00Z', hold_bars=2)
        fields.update(changes)
        return plan_event(**fields)

    def assertClock(self, actual, expected):
        self.assertIsInstance(actual, str)
        parsed = pd.Timestamp(actual)
        self.assertIsNotNone(parsed.tzinfo)
        self.assertEqual(parsed, pd.Timestamp(expected))

    def test_receipt_late_event_has_one_equal_120_minute_pair(self):
        p = self.plan()
        self.assertTrue(p['common_full_hold_support'])
        for field, expected in dict(base_entry_utc='17:30', delayed_entry_utc='18:30',
                                    base_exit_utc='19:30', delayed_exit_utc='20:30').items():
            self.assertClock(p[field], '2026-11-19T' + expected + ':00Z')
        self.assertFalse(p['terminal_backtest_allowed'])
        self.assertFalse(p['source_fresh_at_receipt'])
        self.assertAlmostEqual(p['source_age_at_receipt_minutes'], 97 + 35.656109 / 60)
        self.assertClock(p['event_start_utc'], '2026-11-19T15:30:00Z')
        self.assertClock(p['source_end_utc'], '2026-11-19T15:30:00Z')
        self.assertClock(p['original_event_decision_utc'], '2026-11-19T16:30:00Z')

    def test_strict_future_open_when_receipt_equals_clock(self):
        p = self.plan(ready='2026-11-19T17:30:00Z')
        self.assertClock(p['base_entry_utc'], '2026-11-19T18:30:00Z')
        self.assertClock(p['delayed_entry_utc'], '2026-11-19T19:30:00Z')
        self.assertFalse(p['common_full_hold_support'])
        self.assertIsNone(p['delayed_exit_utc'])

    def test_freshness_is_independent_of_calendar_support(self):
        p = self.plan(source_end='2026-11-19T16:30:00Z')
        self.assertTrue(p['source_fresh_at_receipt'])
        self.assertTrue(p['common_full_hold_support'])
        self.assertFalse(p['terminal_backtest_allowed'])
        self.assertEqual(p['base_entry_utc'], self.plan()['base_entry_utc'])

    def test_freshness_five_and_65_minute_boundaries(self):
        for source, ready, expected, minutes in (
                ('15:30:00', '15:35:00', True, 5),
                ('15:30:00', '15:34:59', False, 4 + 59 / 60),
                ('14:30:00', '15:35:00', True, 65),
                ('14:30:00', '15:35:01', False, 65 + 1 / 60)):
            with self.subTest(source=source, ready=ready):
                p = self.plan(event_start='2026-11-19T14:30:00Z',
                              source_end='2026-11-19T' + source + 'Z',
                              ready='2026-11-19T' + ready + 'Z')
                self.assertEqual(p['source_fresh_at_receipt'], expected)
                self.assertAlmostEqual(p['source_age_at_receipt_minutes'], minutes)

    def test_before_completion_and_future_source_are_rejected(self):
        for changes in ({'ready': '2026-11-19T16:29:59Z'},
                        {'source_end': '2026-11-19T16:30:01Z'}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    self.plan(**changes)

    def test_four_bar_hold_is_240_minutes_and_not_c180(self):
        p = self.plan(event_start='2026-11-19T14:30:00Z',
                      source_end='2026-11-19T14:30:00Z',
                      ready='2026-11-19T15:30:00Z', hold_bars=4)
        self.assertFalse(p['common_full_hold_support'])
        self.assertClock(p['base_entry_utc'], '2026-11-19T16:30:00Z')
        self.assertClock(p['base_exit_utc'], '2026-11-19T20:30:00Z')
        self.assertEqual(pd.Timestamp(p['base_exit_utc']) - pd.Timestamp(p['base_entry_utc']),
                         pd.Timedelta(minutes=240))
        self.assertIsNone(p['delayed_exit_utc'])

    def test_four_bar_pair_supported_only_with_full_bars(self):
        p = self.plan(event_start='2026-11-19T14:30:00Z',
                      source_end='2026-11-19T14:30:00Z',
                      ready='2026-11-19T15:30:00Z', hold_bars=4)
        self.assertFalse(p['common_full_hold_support'])
        self.assertTrue(p['rejection_reasons'])
        # Later receipts cannot clip four bars into a shorter final position.
        late = self.plan(hold_bars=4)
        self.assertFalse(late['common_full_hold_support'])
        self.assertIsNone(late['base_exit_utc'])
        self.assertIsNone(late['delayed_exit_utc'])

    def test_two_bar_hold_may_end_2030_but_not_use_half_hour_tail(self):
        p = self.plan(ready='2026-11-19T18:29:59Z')
        self.assertClock(p['base_exit_utc'], '2026-11-19T20:30:00Z')
        self.assertIsNone(p['delayed_exit_utc'])
        self.assertFalse(p['common_full_hold_support'])
        p = self.plan(ready='2026-11-19T19:29:59Z')
        self.assertIsNone(p['base_exit_utc'])
        self.assertIsNone(p['delayed_exit_utc'])
        self.assertTrue(all(isinstance(x, str) for x in p['rejection_reasons']))

    def test_close_or_later_receipts_do_not_roll_to_next_day(self):
        for ready in ('2026-11-19T21:00:00Z', '2026-11-20T15:00:00Z'):
            with self.subTest(ready=ready):
                p = self.plan(ready=ready)
                self.assertFalse(p['common_full_hold_support'])
                for key in ('base_entry_utc', 'delayed_entry_utc', 'base_exit_utc', 'delayed_exit_utc'):
                    self.assertIsNone(p[key])
                self.assertTrue(p['rejection_reasons'])

    def test_only_exact_seven_regular_starts_are_events(self):
        for event in ('2026-11-19T14:00:00Z', '2026-11-19T14:31:00Z',
                      '2026-11-19T21:00:00Z', '2026-11-20T14:30:00Z'):
            with self.subTest(event=event):
                with self.assertRaises(ValueError):
                    self.plan(event_start=event, ready='2026-11-20T22:00:00Z')

    def test_normal_ny_calendar_required(self):
        for changes in ({'closed': '2026-11-19T20:00:00Z'},
                        {'opened': '2026-11-19T14:00:00Z'},
                        {'closed': '2026-11-20T21:00:00Z'},
                        {'opened': '2026-11-21T14:30:00Z',
                         'closed': '2026-11-21T21:00:00Z',
                         'event_start': '2026-11-21T14:30:00Z',
                         'source_end': '2026-11-21T14:30:00Z',
                         'ready': '2026-11-21T15:35:00Z'}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    self.plan(**changes)

    def test_aware_inputs_and_strict_hold_integer_required(self):
        for field in ('event_start', 'source_end', 'ready', 'opened', 'closed'):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    self.plan(**{field: '2026-11-19T16:30:00'})
        for hold in (True, False, 2.0, '2', None, 1, 3, 0, -2):
            with self.subTest(hold=hold):
                with self.assertRaises(ValueError):
                    self.plan(hold_bars=hold)

    def test_scheduler_requires_no_prices_and_timezone_changes_no_clock(self):
        self.assertEqual(set(inspect.signature(plan_event).parameters),
                         {'event_start', 'source_end', 'ready', 'opened', 'closed', 'hold_bars'})
        p = self.plan(ready='2026-11-19T12:07:35.656109-05:00')
        self.assertEqual(p, self.plan())

    def test_protective_marks_are_intermediate_actual_bar_ends(self):
        p = self.plan()
        self.assertEqual(len(p['base_protective_marks']), 1)
        self.assertEqual(len(p['delayed_protective_marks']), 1)
        self.assertClock(p['base_protective_marks'][0], '2026-11-19T18:30:00Z')
        self.assertClock(p['delayed_protective_marks'][0], '2026-11-19T19:30:00Z')
        p = self.plan(event_start='2026-11-19T14:30:00Z',
                      source_end='2026-11-19T14:30:00Z',
                      ready='2026-11-19T15:30:00Z', hold_bars=4)
        self.assertEqual([pd.Timestamp(x).hour for x in p['base_protective_marks']], [17, 18, 19])

    def test_exact_deadline_protection_passes_but_one_microsecond_late_fails(self):
        marks = ['2026-11-19T18:30:00+00:00', '2026-11-19T19:30:00+00:00']
        receipts = {marks[0]: marks[0], marks[1]: '2026-11-19T19:29:59Z'}
        p = qualify_marks(marks, receipts)
        self.assertTrue(p['all_marks_observed_by_deadline'])
        self.assertEqual(p['late_or_missing'], [])
        receipts[marks[0]] = '2026-11-19T18:30:00.000001Z'
        p = qualify_marks(marks, receipts)
        self.assertFalse(p['all_marks_observed_by_deadline'])
        self.assertEqual(len(p['late_or_missing']), 1)

    def test_missing_and_actual_late_protection_are_not_observations(self):
        marks = self.plan()['base_protective_marks']
        for receipts in ({}, {marks[0]: '2026-11-19T19:07:20.487713Z'}):
            with self.subTest(receipts=receipts):
                p = qualify_marks(marks, receipts)
                self.assertFalse(p['all_marks_observed_by_deadline'])
                self.assertEqual(len(p['late_or_missing']), 1)

    def test_no_protective_marks_does_not_vacuously_qualify(self):
        p = qualify_marks([], {})
        self.assertFalse(p['all_marks_observed_by_deadline'])
        self.assertTrue(p['late_or_missing'])

    def test_naive_protective_marks_keys_or_receipts_rejected(self):
        mark = '2026-11-19T18:30:00+00:00'
        for marks, receipts in ((['2026-11-19T18:30:00'], {}),
                                ([mark], {mark: '2026-11-19T18:30:00'}),
                                ([mark], {'2026-11-19T18:30:00': mark})):
            with self.subTest(marks=marks, receipts=receipts):
                with self.assertRaises(ValueError):
                    qualify_marks(marks, receipts)


if __name__ == '__main__':
    unittest.main()
