import copy
from dataclasses import replace
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from autogrid.data import MarketData
from venue_flow_signals_20261119 import candidates, signals, support


class VenueFlowSignalTests(unittest.TestCase):
    def fixture(self):
        times = pd.DatetimeIndex([t for day in ('2025-01-02', '2025-01-03', '2025-01-06')
                                  for t in pd.date_range(day+' 09:30', periods=7,
                                                         freq='h', tz='America/New_York')]).tz_convert('UTC')
        n = len(times)
        ones = np.ones((n, 4))
        data = MarketData(times.to_numpy(), ('TQQQ', 'SQQQ', 'IBIT', 'BITI'),
                          100*ones, 102*ones, 99*ones, 101*ones, ones, bar_minutes=60)
        current = dict(open=np.full(n, 100.), high=np.full(n, 102.),
                       low=np.full(n, 99.), close=np.full(n, 101.8), flow=np.full(n, .4))
        prior = dict(open=np.full(n, 100.), high=np.full(n, 102.),
                     low=np.full(n, 98.), close=np.full(n, 100.2), flow=np.full(n, -.4))
        ctx = dict(valid=np.ones(n, bool), current=current, prior=prior,
                   history1=np.ones(n, bool), history4=np.ones(n, bool),
                   history8=np.ones(n, bool), flow_mean4=np.zeros(n), flow_mean8=np.zeros(n))
        return data, times, ctx

    def config(self, family):
        return next(c for c in candidates() if c['family'] == family)

    def prefix(self, data, times, ctx, n):
        prefix = replace(data, timestamps=data.timestamps[:n],
                         **{k: getattr(data, k)[:n] for k in ('open', 'high', 'low', 'close', 'volume')})
        pc = {k: ({j: v[:n] for j, v in value.items()} if isinstance(value, dict)
                   else value[:n]) for k, value in ctx.items()}
        return prefix, times[:n], pc

    def test_exact_bounded_grid_and_numeric_validation(self):
        cs = candidates()
        self.assertEqual(len(cs), 32)
        self.assertEqual(len({c['name'] for c in cs}), 32)
        for family in ('flow_trend', 'absorption_release', 'flow_flip', 'burst_hold'):
            self.assertEqual(sum(c['family'] == family for c in cs), 8)
        d, t, ctx = self.fixture()
        for bad in (dict(family='missing'), dict(self.config('flow_trend'), lookback=True),
                    dict(self.config('flow_trend'), flow_threshold=.123),
                    dict(self.config('flow_trend'), typo=4)):
            with self.assertRaises(ValueError):
                signals(d, t, ctx, bad)
        with self.assertRaises(ValueError):
            signals(d, t, ctx, cs[0], flow_removed=1)

    def test_mechanisms_emit_actual_coin_buy_roles(self):
        d, t, ctx = self.fixture()
        for family in ('flow_trend', 'absorption_release', 'flow_flip'):
            got = signals(d, t, ctx, self.config(family))
            self.assertEqual(got[0, 2], -1.)
            self.assertEqual(np.count_nonzero(got), 3)  # once per NY day
            np.testing.assert_array_equal(got[:, :2], 0.)
        ctx['prior']['close'][:] = 101.8
        ctx['prior']['high'][:] = 102.
        ctx['prior']['low'][:] = 99.
        ctx['prior']['flow'][:] = .4
        ctx['current']['open'][:] = 101.8
        ctx['current']['close'][:] = 101.2
        got = signals(d, t, ctx, self.config('burst_hold'))
        self.assertEqual(got[0, 2], -1.)
        # Mirror the complete source price/flow rules for a BITI BUY, no shorts.
        for fields in (ctx['current'], ctx['prior']):
            fields['open'][:] = 100.
            fields['close'][:] = 98.2
            fields['high'][:] = 101.
            fields['low'][:] = 98.
            fields['flow'][:] = -.4
        got = signals(d, t, ctx, self.config('flow_trend'))
        self.assertEqual(got[0, 3], -1.)
        ctx['current']['open'][:] = 98.2
        ctx['current']['close'][:] = 98.8
        got = signals(d, t, ctx, self.config('burst_hold'))
        self.assertEqual(got[0, 3], -1.)
        self.assertTrue(np.isin(got, [-1., 0.]).all())

    def test_each_flow_predicate_removal_preserves_price_direction(self):
        d, t, ctx = self.fixture()
        for family in ('flow_trend', 'absorption_release', 'flow_flip'):
            changed = copy.deepcopy(ctx)
            changed['current']['flow'][:] = -.4
            c = self.config(family)
            self.assertEqual(np.count_nonzero(signals(d, t, changed, c)), 0)
            self.assertEqual(signals(d, t, changed, c, True)[0, 2], -1.)
        ctx['prior']['close'][:] = 101.8
        ctx['prior']['low'][:] = 99.
        ctx['current']['open'][:] = 101.8
        ctx['current']['close'][:] = 101.2
        c = self.config('burst_hold')
        self.assertEqual(np.count_nonzero(signals(d, t, ctx, c)), 0)
        self.assertEqual(signals(d, t, ctx, c, True)[0, 2], -1.)

    def test_nontrivial_retention_and_actual_past_flow_mean(self):
        d, t, ctx = self.fixture()
        ctx['prior']['close'][:] = 101.8
        ctx['prior']['low'][:] = 99.
        ctx['prior']['flow'][:] = .4
        ctx['current']['open'][:] = 101.8
        ctx['current']['close'][:] = 101.2  # retains 2/3 of the prior body
        c = self.config('burst_hold')
        self.assertEqual(signals(d, t, ctx, c)[0, 2], -1.)
        self.assertEqual(np.count_nonzero(signals(d, t, ctx, dict(c, retention=.75))), 0)
        d, t, ctx = self.fixture()
        ctx['flow_mean4'][:] = .5
        ctx['flow_mean8'][:] = .1
        c = self.config('flow_trend')
        self.assertEqual(np.count_nonzero(signals(d, t, ctx, c)), 0)
        self.assertEqual(signals(d, t, ctx, dict(c, lookback=8))[0, 2], -1.)
        # A very small negative prior flow passes ceiling0 but not ceiling-.1.
        ctx['prior']['flow'][:] = -.05
        c = self.config('flow_flip')
        self.assertEqual(signals(d, t, ctx, c)[0, 2], -1.)
        self.assertEqual(np.count_nonzero(signals(d, t, ctx, dict(c, prior_ceiling=-.1))), 0)

    def test_independent_control_onsets_are_not_a_subset_assertion(self):
        d, t, ctx = self.fixture()
        c = self.config('flow_trend')
        ctx['current']['flow'][1] = -.4  # source valid false; control still true
        source, control = signals(d, t, ctx, c), signals(d, t, ctx, c, True)
        self.assertEqual(source[2, 2], -1.)
        self.assertEqual(control[2, 2], 0.)

    def test_prefix_invariance_all_64_definitions(self):
        d, t, ctx = self.fixture()
        ctx['current']['flow'][[1, 4, 10]] = -.4
        for n in (1, 2, 8, 17):
            dp, tp, cp = self.prefix(d, t, ctx, n)
            for c in candidates():
                for removed in (False, True):
                    np.testing.assert_array_equal(signals(dp, tp, cp, c, removed),
                                                  signals(d, t, ctx, c, removed)[:n])

    def test_symbol_order_and_exact_four_symbols(self):
        d, t, ctx = self.fixture()
        ix = [3, 1, 0, 2]
        reordered = replace(d, symbols=tuple(d.symbols[i] for i in ix),
                            **{k: getattr(d, k)[:, ix] for k in ('open', 'high', 'low', 'close', 'volume')})
        for c in candidates():
            for removed in (False, True):
                np.testing.assert_array_equal(signals(reordered, t, ctx, c, removed),
                                              signals(d, t, ctx, c, removed)[:, ix])
        with self.assertRaises(ValueError):
            signals(replace(d, symbols=('TQQQ', 'SQQQ', 'IBIT', 'IBIT')), t, ctx, candidates()[0])

    def test_missing_or_gap_support_shared_and_does_not_rearm(self):
        d, t, ctx = self.fixture()
        c = self.config('flow_trend')
        ctx['current']['flow'][1] = -.4
        ctx['history4'][1] = False
        for removed in (False, True):
            got = signals(d, t, ctx, c, removed)
            self.assertEqual(got[2, 2], 0.)
        ctx['current']['flow'][1] = np.nan
        ctx['history4'][1] = True
        self.assertFalse(support(d, t, ctx, c)[1])
        for removed in (False, True):
            self.assertEqual(signals(d, t, ctx, c, removed)[2, 2], 0.)
        # prior/history1 may be supplied from actual overnight source hours;
        # it is caller's completed-source gap flag, not prior ETF row.
        c = self.config('flow_flip')
        ctx['history1'][0] = False
        self.assertEqual(signals(d, t, ctx, c)[1, 2], 0.)  # current NaN row
        self.assertEqual(signals(d, t, ctx, c)[2, 2], -1.)

    def test_zero_flow_is_not_zero_volume_and_zero_volume_mask_fails_closed(self):
        d, t, ctx = self.fixture()
        c = self.config('flow_trend')
        ctx['current']['flow'][0] = 0.  # balanced positive-volume trades are valid
        self.assertTrue(support(d, t, ctx, c)[0])
        self.assertEqual(signals(d, t, ctx, c)[0, 2], 0.)
        self.assertEqual(signals(d, t, ctx, c, True)[0, 2], -1.)
        # Caller marks raw zero-volume denominator unavailable, never flow=0.
        ctx['valid'][0] = False
        for removed in (False, True):
            self.assertEqual(signals(d, t, ctx, c, removed)[0, 2], 0.)

    def test_only_selected_history_required_and_bounds_fail_closed(self):
        d, t, ctx = self.fixture()
        c = self.config('flow_trend')
        minimal = {k: ctx[k] for k in ('valid', 'current', 'history4', 'flow_mean4')}
        np.testing.assert_array_equal(signals(d, t, minimal, c), signals(d, t, ctx, c))
        for key in ('current', 'prior'):
            bad = copy.deepcopy(ctx)
            bad[key]['flow'][0] = 1.01
            family = 'flow_trend' if key == 'current' else 'flow_flip'
            for removed in (False, True):
                with self.assertRaises(ValueError):
                    signals(d, t, bad, self.config(family), removed)
        ctx['flow_mean4'][0] = -1.01
        with self.assertRaises(ValueError):
            signals(d, t, ctx, c)

    def test_shapes_boolean_masks_prices_and_timestamps(self):
        d, t, ctx = self.fixture()
        c = candidates()[0]
        for mutate in (lambda x: x.update(valid=np.ones(len(t))),
                       lambda x: x.update(history4=np.ones((len(t), 1), bool)),
                       lambda x: x['current'].update(flow=np.ones(len(t)-1)),
                       lambda x: x['current']['high'].__setitem__(0, 99.)):
            bad = copy.deepcopy(ctx)
            mutate(bad)
            with self.assertRaises(ValueError):
                signals(d, t, bad, c)
        with self.assertRaises(ValueError):
            signals(d, t[::-1], ctx, c)
        with self.assertRaises(ValueError):
            signals(d, t+pd.Timedelta(minutes=1), ctx, c)
        bad = copy.deepcopy(ctx)
        bad['current']['close'][0] = 0.
        self.assertFalse(support(d, t, bad, c)[0])

    def test_quote_failure_does_not_consume_and_rth_excludes_outside(self):
        d, t, ctx = self.fixture()
        c = candidates()[0]
        close = d.close.copy()
        close[0, 2] = np.nan
        got = signals(replace(d, close=close), t, ctx, c)
        self.assertEqual(got[0, 2], 0.)
        self.assertEqual(got[1, 2], -1.)
        shifted = t+pd.Timedelta(hours=8)
        outside = replace(d, timestamps=shifted.to_numpy())
        self.assertEqual(np.count_nonzero(signals(outside, shifted, ctx, c)), 0)


if __name__ == '__main__':
    unittest.main()
