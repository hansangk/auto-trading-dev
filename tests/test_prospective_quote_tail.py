"""SYNTHETIC_UNIT_ONLY: no market acquisition, account replay, or orders."""
from copy import deepcopy
from datetime import timedelta
import unittest

from scripts.prospective_input_audit_20261119 import SYMBOLS, timestamp
from scripts.prospective_quote_tail_20261120 import classify_payload


def epoch(text):
    return (timestamp(text)-timestamp('1970-01-01T00:00:00Z')) // timedelta(seconds=1)


def payload(symbol='BITI', tail='2026-11-19T17:05:37Z'):
    times = [epoch('2026-11-19T14:30:00Z'), epoch('2026-11-19T15:30:00Z'),
             epoch('2026-11-19T16:30:00Z'), epoch(tail)]
    quote = dict(open=[100, 110, 120, 987], high=[102, 112, 122, 987],
                 low=[99, 109, 119, 987], close=[101, 111, 121, 987],
                 volume=[500, 600, 700, 0])
    return dict(chart=dict(error=None, result=[dict(
        meta=dict(symbol=symbol, currency='USD', exchangeTimezoneName='America/New_York',
                  regularMarketTime=times[-1]), timestamp=times,
        indicators=dict(quote=[quote]))]))


def data(body):
    return body['chart']['result'][0]


def remove_tail(body):
    result = deepcopy(body)
    data(result)['timestamp'].pop()
    for values in data(result)['indicators']['quote'][0].values():
        values.pop()
    return result


class ProspectiveQuoteTailTests(unittest.TestCase):
    cutoff = '2026-11-19T17:07:25Z'

    def test_at_or_before_cutoff_tail_all_symbols_and_input_unchanged(self):
        for symbol in SYMBOLS:
            for tail in ('2026-11-19T17:05:37Z', self.cutoff):
                with self.subTest(symbol=symbol, tail=tail):
                    body = payload(symbol, tail)
                    before = deepcopy(body)
                    result = classify_payload(body, self.cutoff)
                    self.assertEqual(result['counts'], dict(raw=4, completed=2, quarantined=2))
                    self.assertEqual([r['reason'] for r in result['quarantined_records']],
                                     ['INCOMPLETE_REGULAR_BAR',
                                      'METADATA_MATCHED_ZERO_VOLUME_LIVE_TAIL'])
                    self.assertEqual(body, before)
                    self.assertFalse(result['terminal_backtest_allowed'])

    def test_future_row_is_separate_before_offclock_predicates(self):
        body = payload(tail='2026-11-19T17:07:35Z')
        data(body)['meta'].pop('regularMarketTime')
        for values in data(body)['indicators']['quote'][0].values():
            values[-1] = None
        result = classify_payload(body, self.cutoff)
        self.assertEqual(result['quarantined_records'][-1]['reason'], 'FUTURE_TIMESTAMP')
        self.assertEqual(len(result['completed_rows']), 2)

    def test_complete_prefix_identical_with_and_without_tail_no_merge(self):
        body = payload()
        with_tail = classify_payload(body, self.cutoff)['completed_rows']
        without_tail = classify_payload(remove_tail(body), self.cutoff)['completed_rows']
        self.assertEqual(with_tail, without_tail)
        self.assertEqual(with_tail, [
            dict(symbol='BITI', timestamp='2026-11-19T14:30:00+00:00',
                 open=100, high=102, low=99, close=101, volume=500),
            dict(symbol='BITI', timestamp='2026-11-19T15:30:00+00:00',
                 open=110, high=112, low=109, close=111, volume=600)])

    def test_tail_metadata_timestamp_required_exact(self):
        for value in (None, epoch('2026-11-19T17:05:38Z'),
                      float(epoch('2026-11-19T17:05:37Z')), True):
            body = payload()
            data(body)['meta']['regularMarketTime'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                classify_payload(body, self.cutoff)

    def test_each_tail_price_and_volume_predicate(self):
        for field, value in [('open', 986), ('high', 988), ('low', 986), ('close', 988),
                             ('open', 0), ('open', -1), ('open', float('nan')),
                             ('high', float('inf')), ('low', None), ('close', True),
                             ('volume', 1), ('volume', -1), ('volume', None),
                             ('volume', float('nan')), ('volume', False)]:
            body = payload()
            data(body)['indicators']['quote'][0][field][-1] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                classify_payload(body, self.cutoff)
        body = payload()
        for field in ('open', 'high', 'low', 'close'):
            data(body)['indicators']['quote'][0][field][-1] = 0
        with self.assertRaises(ValueError):
            classify_payload(body, self.cutoff)

    def test_tail_requires_nonempty_exact_regular_predecessor(self):
        body = payload()
        for remove in (1, 3):
            bad = deepcopy(body)
            del data(bad)['timestamp'][-1-remove:-1]
            for values in data(bad)['indicators']['quote'][0].values():
                del values[-1-remove:-1]
            with self.subTest(remove=remove), self.assertRaises(ValueError):
                classify_payload(bad, self.cutoff)
        bad = deepcopy(body)
        data(bad)['timestamp'][-2] += 1
        with self.assertRaises(ValueError):
            classify_payload(bad, self.cutoff)

    def test_predecessor_must_still_be_incomplete_at_cutoff(self):
        for cutoff in ('2026-11-19T17:30:00Z', '2026-11-19T18:00:00Z'):
            with self.subTest(cutoff=cutoff), self.assertRaises(ValueError):
                classify_payload(payload(), cutoff)

    def test_tail_strictly_inside_interval(self):
        for tail in ('2026-11-19T17:30:01Z', '2026-11-19T20:59:59Z',
                     '2026-11-19T21:00:00Z'):
            with self.subTest(tail=tail), self.assertRaises(ValueError):
                classify_payload(payload(tail=tail), tail)
        # The final regular bar is 30 minutes, ending exactly at 21:00 UTC.
        body = payload(tail='2026-11-19T20:59:59Z')
        data(body)['timestamp'][-2] = epoch('2026-11-19T20:30:00Z')
        result = classify_payload(body, '2026-11-19T20:59:59Z')
        self.assertEqual(result['quarantined_records'][-1]['reason'],
                         'METADATA_MATCHED_ZERO_VOLUME_LIVE_TAIL')
        with self.assertRaises(ValueError):
            classify_payload(body, '2026-11-19T21:00:00Z')

    def test_offclock_middle_fails_even_with_matching_metadata(self):
        body = payload()
        row = data(body)
        row['timestamp'].append(epoch('2026-11-19T18:30:00Z'))
        for field, values in row['indicators']['quote'][0].items():
            values.append(100 if field != 'volume' else 500)
        with self.assertRaises(ValueError):
            classify_payload(body, self.cutoff)

    def test_duplicate_complete_and_nonmonotonic_including_future(self):
        for change in ('duplicate', 'reverse', 'future_duplicate', 'fractional', 'boolean'):
            body = payload()
            times = data(body)['timestamp']
            if change == 'duplicate': times[1] = times[0]
            elif change == 'reverse': times[0], times[1] = times[1], times[0]
            elif change == 'future_duplicate':
                times[-2:] = [epoch('2026-11-19T18:00:00Z')]*2
            elif change == 'fractional': times[-1] += 0.5
            else: times[-1] = True
            with self.subTest(change=change), self.assertRaises(ValueError):
                classify_payload(body, self.cutoff)

    def test_complete_regular_bar_values_use_existing_validator(self):
        for field, value in [('open', 0), ('high', 100), ('low', 102),
                             ('close', None), ('volume', 0), ('volume', float('inf'))]:
            body = payload()
            data(body)['indicators']['quote'][0][field][0] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                classify_payload(body, self.cutoff)

    def test_regular_completion_at_end_and_final_half_hour(self):
        body = remove_tail(payload())
        result = classify_payload(body, '2026-11-19T17:30:00Z')
        self.assertEqual(len(result['completed_rows']), 3)
        data(body)['timestamp'][-1] = epoch('2026-11-19T20:30:00Z')
        self.assertEqual(len(classify_payload(body, '2026-11-19T20:59:59Z')['completed_rows']), 2)
        self.assertEqual(len(classify_payload(body, '2026-11-19T21:00:00Z')['completed_rows']), 3)

    def test_payload_errors_empty_and_wrong_metadata_fail_closed(self):
        cases = [None, {}, {'chart': {'result': [], 'error': None}}]
        for field, value in [('symbol', 'BTCUSDT'), ('currency', 'usd'),
                             ('exchangeTimezoneName', 'EST')]:
            body = payload()
            data(body)['meta'][field] = value
            cases.append(body)
        for kind in ('error', 'empty_times', 'mismatched_array', 'null_result',
                     'multiple_results', 'missing_quote'):
            body = payload()
            if kind == 'error': body['chart']['error'] = {'code': 'Not Found'}
            elif kind == 'empty_times': data(body)['timestamp'] = []
            elif kind == 'mismatched_array': data(body)['indicators']['quote'][0]['open'].pop()
            elif kind == 'null_result': body['chart']['result'] = None
            elif kind == 'multiple_results': body['chart']['result'] *= 2
            else: data(body)['indicators'].pop('quote')
            cases.append(body)
        for i, body in enumerate(cases):
            with self.subTest(case=i), self.assertRaises(ValueError):
                classify_payload(body, self.cutoff)
        with self.assertRaises(ValueError):
            classify_payload(payload(), '2026-11-19T17:07:25')


if __name__ == '__main__':
    unittest.main()
