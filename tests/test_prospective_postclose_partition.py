"""SYNTHETIC_UNIT_ONLY: no acquisition, financial replay, or real orders."""
from copy import deepcopy
from datetime import timedelta
import unittest

from scripts.prospective_input_audit_20261119 import ETF_FIELDS, SYMBOLS, timestamp
from scripts.prospective_postclose_partition_20261120 import classify_postclose
from scripts.prospective_quote_tail_20261120 import classify_payload


def epoch(text):
    return (timestamp(text)-timestamp('1970-01-01T00:00:00Z')) // timedelta(seconds=1)


CLOSE = epoch('2026-11-19T21:00:00Z')
CUTOFF = '2026-11-19T21:04:07Z'


def payload(symbol='BITI', auxiliary=False):
    times = [epoch('2026-11-19T14:30:00Z') + k*3600 for k in range(7)]
    quote = dict(open=[100+k for k in range(7)], high=[102+k for k in range(7)],
                 low=[99+k for k in range(7)], close=[101+k for k in range(7)],
                 volume=[500+k for k in range(7)])
    if auxiliary:
        times.append(CLOSE)
        for field in ETF_FIELDS:
            quote[field].append(987 if field != 'volume' else 0)
    return dict(chart=dict(error=None, result=[dict(
        meta=dict(symbol=symbol, currency='USD', exchangeTimezoneName='America/New_York',
                  regularMarketTime=CLOSE+1), timestamp=times,
        indicators=dict(quote=[quote]))]))


def data(body):
    return body['chart']['result'][0]


def remove_row(body, index):
    del data(body)['timestamp'][index]
    for values in data(body)['indicators']['quote'][0].values():
        del values[index]


class ProspectivePostclosePartitionTests(unittest.TestCase):
    def test_regular_only_all_symbols_frozen03_equivalence_and_last_half_hour(self):
        for symbol in SYMBOLS:
            with self.subTest(symbol=symbol):
                body = payload(symbol)
                before = deepcopy(body)
                result = classify_postclose(body, '2026-11-19T21:00:00Z')
                self.assertEqual(result, classify_payload(body, '2026-11-19T21:00:00Z'))
                self.assertEqual(result['counts'], dict(raw=7, completed=7, quarantined=0))
                self.assertEqual(result['completed_rows'][-1], dict(
                    symbol=symbol, timestamp='2026-11-19T20:30:00+00:00',
                    open=106, high=108, low=105, close=107, volume=506))
                self.assertFalse(result['terminal_backtest_allowed'])
                self.assertEqual(body, before)

    def test_auxiliary_preserves_all_regular_values_and_input_all_symbols(self):
        for symbol in SYMBOLS:
            with self.subTest(symbol=symbol):
                body = payload(symbol, auxiliary=True)
                before = deepcopy(body)
                result = classify_postclose(body, CUTOFF)
                expected = classify_payload(payload(symbol), CUTOFF)['completed_rows']
                self.assertEqual(result['completed_rows'], expected)
                self.assertEqual(result['counts'], dict(raw=8, completed=7, quarantined=1))
                diagnostic, = result['quarantined_records']
                self.assertEqual(diagnostic['row_index'], 7)
                self.assertEqual(diagnostic['timestamp'], '2026-11-19T21:00:00+00:00')
                self.assertEqual(diagnostic['reason'], 'POSTCLOSE_ZERO_VOLUME_BOUNDARY_AUXILIARY')
                self.assertNotIn('close', diagnostic)
                self.assertFalse(result['terminal_backtest_allowed'])
                self.assertEqual(body, before)

    def test_metadata_bounds_inclusive_and_no_fitted_one_second_tolerance(self):
        # A metadata time far beyond one second is valid inside the fixed
        # calendar/cutoff interval. No equality to timestamp or price is used.
        for market_time in (CLOSE, CLOSE+1, CLOSE+120, epoch(CUTOFF)):
            body = payload(auxiliary=True)
            data(body)['meta']['regularMarketTime'] = market_time
            data(body)['meta']['regularMarketPrice'] = -123
            with self.subTest(market_time=market_time):
                self.assertEqual(len(classify_postclose(body, CUTOFF)['completed_rows']), 7)
        body = payload(auxiliary=True)
        data(body)['meta']['regularMarketTime'] = CLOSE
        self.assertEqual(classify_postclose(body, '2026-11-19T21:00:00Z')['counts']['completed'], 7)

    def test_auxiliary_metadata_strict_integer_type_and_bounds(self):
        for value in (None, True, False, str(CLOSE), float(CLOSE), CLOSE-1,
                      epoch(CUTOFF)+1, float('nan'), float('inf'), 10**100):
            body = payload(auxiliary=True)
            data(body)['meta']['regularMarketTime'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                classify_postclose(body, CUTOFF)
        body = payload(auxiliary=True)
        del data(body)['meta']['regularMarketTime']
        with self.assertRaises(ValueError):
            classify_postclose(body, CUTOFF)

    def test_missing_any_regular_start_refused_even_with_auxiliary(self):
        for auxiliary in (False, True):
            for index in range(7):
                body = payload(auxiliary=auxiliary)
                remove_row(body, index)
                with self.subTest(auxiliary=auxiliary, index=index), self.assertRaises(ValueError):
                    classify_postclose(body, CUTOFF)

    def test_duplicate_nonmonotonic_and_offclock_regular_starts_refused(self):
        for index in range(7):
            for shift in (-1, 1, 3600, -3600, 86400):
                body = payload(auxiliary=True)
                data(body)['timestamp'][index] += shift
                with self.subTest(index=index, shift=shift), self.assertRaises(ValueError):
                    classify_postclose(body, CUTOFF)
        body = payload()
        data(body)['timestamp'][0:2] = reversed(data(body)['timestamp'][0:2])
        with self.assertRaises(ValueError):
            classify_postclose(body, CUTOFF)

    def test_only_one_auxiliary_at_exact_close_no_future_or_offclock_exception(self):
        for extra_time in (CLOSE-1, CLOSE+1, epoch(CUTOFF)+1, CLOSE+86400):
            body = payload(auxiliary=True)
            data(body)['timestamp'][-1] = extra_time
            with self.subTest(extra_time=extra_time), self.assertRaises(ValueError):
                classify_postclose(body, CUTOFF)
        body = payload(auxiliary=True)
        data(body)['timestamp'].append(CLOSE)
        for field in ETF_FIELDS:
            data(body)['indicators']['quote'][0][field].append(987 if field != 'volume' else 0)
        with self.assertRaises(ValueError):
            classify_postclose(body, CUTOFF)

    def test_each_auxiliary_ohlc_must_be_finite_positive_and_identical(self):
        for field in ETF_FIELDS[:4]:
            for value in (986, 988, 0, -1, None, True, float('nan'), float('inf')):
                body = payload(auxiliary=True)
                data(body)['indicators']['quote'][0][field][-1] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    classify_postclose(body, CUTOFF)
        for common in (0, -1, float('nan'), float('inf')):
            body = payload(auxiliary=True)
            for field in ETF_FIELDS[:4]:
                data(body)['indicators']['quote'][0][field][-1] = common
            with self.subTest(common=common), self.assertRaises(ValueError):
                classify_postclose(body, CUTOFF)

    def test_auxiliary_volume_exactly_zero(self):
        for value in (1, -1, '0.0000000001', None, False, True, float('nan'), float('inf')):
            body = payload(auxiliary=True)
            data(body)['indicators']['quote'][0]['volume'][-1] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                classify_postclose(body, CUTOFF)

    def test_existing_regular_ohlcv_validator_including_last_bar(self):
        for index in (0, 6):
            for field, value in (('open', 0), ('high', 1), ('low', 999),
                                 ('close', float('nan')), ('volume', 0)):
                body = payload(auxiliary=True)
                data(body)['indicators']['quote'][0][field][index] = value
                with self.subTest(index=index, field=field), self.assertRaises(ValueError):
                    classify_postclose(body, CUTOFF)

    def test_cutoff_must_be_aware_and_reach_close(self):
        for cutoff in ('2026-11-19T20:59:59Z', '2026-11-18T21:05:00Z',
                       '2026-11-19T21:04:07', 'bad'):
            with self.subTest(cutoff=cutoff), self.assertRaises(ValueError):
                classify_postclose(payload(), cutoff)

    def test_timestamp_seconds_strict_integer(self):
        for index in (0, 6, 7):
            for value in (True, float(CLOSE), str(CLOSE), None):
                body = payload(auxiliary=True)
                data(body)['timestamp'][index] = value
                with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                    classify_postclose(body, CUTOFF)

    def test_malformed_core_metadata_and_chart_refused(self):
        cases = [None, {}, {'chart': {'result': [], 'error': None}}]
        for field, value in (('symbol', 'BTCUSDT'), ('currency', 'usd'),
                             ('exchangeTimezoneName', 'EST')):
            for auxiliary in (False, True):
                body = payload(auxiliary=auxiliary)
                data(body)['meta'][field] = value
                cases.append(body)
        for kind in ('missing_meta', 'null_meta', 'error', 'short_array', 'missing_field'):
            body = payload(auxiliary=True)
            if kind == 'missing_meta': del data(body)['meta']
            elif kind == 'null_meta': data(body)['meta'] = None
            elif kind == 'error': body['chart']['error'] = {'code': 'Bad'}
            elif kind == 'short_array': data(body)['indicators']['quote'][0]['open'].pop()
            else: del data(body)['indicators']['quote'][0]['volume']
            cases.append(body)
        for index, body in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(ValueError):
                classify_postclose(body, CUTOFF)

    def test_rejection_does_not_mutate_input(self):
        body = payload(auxiliary=True)
        data(body)['indicators']['quote'][0]['volume'][-1] = 1
        before = deepcopy(body)
        with self.assertRaises(ValueError):
            classify_postclose(body, CUTOFF)
        self.assertEqual(body, before)

    def test_frozen03_still_rejects_postclose_auxiliary_payload(self):
        with self.assertRaisesRegex(ValueError, 'incomplete regular predecessor'):
            classify_payload(payload(auxiliary=True), CUTOFF)


if __name__ == '__main__':
    unittest.main()
