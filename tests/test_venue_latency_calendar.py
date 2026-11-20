import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from venue_latency_calendar_20261119 import common_mask


def normal_calendar(days):
    records = []
    for day in days:
        opened = pd.Timestamp(day + ' 09:30', tz='America/New_York').tz_convert('UTC')
        closed = pd.Timestamp(day + ' 16:00', tz='America/New_York').tz_convert('UTC')
        records.append(dict(open=opened, close=closed))
    return pd.DataFrame(records, index=days)


def starts(schedule, day):
    return pd.date_range(schedule.loc[day, 'open'], periods=7, freq='h')


class VenueLatencyCalendarTests(unittest.TestCase):
    def test_exact_target_closes_and_last_partial(self):
        s = normal_calendar(['2025-01-06'])
        t = starts(s, '2025-01-06')
        np.testing.assert_array_equal(common_mask(t, s, 60), [True, True, True, True, False, False, False])
        np.testing.assert_array_equal(common_mask(t, s, 120), [True, True, True, False, False, False, False])
        np.testing.assert_array_equal(common_mask(t, s, 180), [True, True, False, False, False, False, False])
        # 13:30 signal: delay entry15:30 plus60min would be16:30, not16:00.
        self.assertFalse(common_mask(t, s, 60)[4])
        self.assertFalse(common_mask(t, s, 120)[-1])

    def test_prefix_uses_no_future_etf_rows(self):
        s = normal_calendar(['2025-01-06', '2025-01-07'])
        t = starts(s, '2025-01-06').append(starts(s, '2025-01-07'))
        for duration in (60, 120, 180):
            whole = common_mask(t, s, duration)
            for n in range(len(t) + 1):
                np.testing.assert_array_equal(common_mask(t[:n], s, duration), whole[:n])
        # Only signal09:30 is present, yet both future-entry clocks are eligible.
        self.assertTrue(common_mask(t[:1], s, 180)[0])

    def test_dst_preserves_ny_eligibility(self):
        s = normal_calendar(['2025-03-07', '2025-03-10', '2025-10-31', '2025-11-03'])
        expected = [True, True, True, False, False, False, False]
        self.assertEqual(s.loc['2025-03-07', 'open'].hour, 14)
        self.assertEqual(s.loc['2025-03-10', 'open'].hour, 13)
        for day in s.index:
            t = starts(s, day)
            np.testing.assert_array_equal(common_mask(t, s, 120), expected)
            np.testing.assert_array_equal(common_mask(t.tz_convert('America/New_York'), s, 120), expected)

    def test_duration_rejects_boolean_noninteger_and_unsupported(self):
        s = normal_calendar(['2025-01-06']); t = starts(s, '2025-01-06')
        for value in (True, np.bool_(False), 120., 120.5, '120', None, np.array(120), [120], -1, 0, 90, 240):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    common_mask(t, s, value)
        np.testing.assert_array_equal(common_mask(t, s, np.int64(120)), common_mask(t, s, 120))

    def test_calendar_mismatch_and_short_referenced_session(self):
        s = normal_calendar(['2025-01-06']); t = starts(s, '2025-01-06')
        for field, change in [('open', pd.Timedelta(days=1)), ('close', pd.Timedelta(minutes=-30))]:
            bad = s.copy(); bad.loc['2025-01-06', field] += change
            with self.assertRaises(ValueError):common_mask(t, bad, 120)
        bad = s.copy(); bad.loc['2025-01-06', 'close'] = pd.Timestamp('2025-01-06 18:00Z')
        with self.assertRaises(ValueError):common_mask(t, bad, 120)
        # Other known calendar rows do not require future ETF price rows.
        extra = pd.DataFrame([dict(open=pd.Timestamp('2025-11-28 14:30Z'), close=pd.Timestamp('2025-11-28 18:00Z'))], index=['2025-11-28'])
        np.testing.assert_array_equal(common_mask(t, pd.concat([s, extra]), 120), common_mask(t, s, 120))

    def test_bad_timestamp_inputs_and_schedule_schema(self):
        s = normal_calendar(['2025-01-06']); t = starts(s, '2025-01-06')
        bad_times = [t.tz_localize(None), t[::-1], t.append(t[:1]), [pd.NaT], [t[0] + pd.Timedelta(minutes=1)], t[0]]
        for times in bad_times:
            with self.assertRaises(ValueError):common_mask(times, s, 120)
        for schedule in (None, 2, s.drop(columns='close'), pd.concat([s, s]), s.rename(index={'2025-01-06': '2025-01-07'})):
            with self.assertRaises(ValueError):common_mask(t, schedule, 120)
        bad = s.astype(object); bad.loc['2025-01-06', 'open'] = bad.loc['2025-01-06', 'open'].tz_localize(None)
        with self.assertRaises(ValueError):common_mask(t, bad, 120)


if __name__ == '__main__':unittest.main()
