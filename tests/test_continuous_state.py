from dataclasses import replace
import unittest

import numpy as np
import pandas as pd

from autogrid.config import ExecutionConfig, RiskConfig
from autogrid.data import MarketData
from autogrid.engine import AccountState, run_backtest
from autogrid.strategy import StrategySpec


class ContinuousStateTests(unittest.TestCase):
    capital = 100_000.0
    execution = ExecutionConfig(0, 0, 0)
    risk = RiskConfig(gross_exposure=1, max_asset_weight=.5,
                      risk_per_trade=.5, daily_soft_loss=.5,
                      daily_hard_loss=.6, max_drawdown=.5, max_loss_streak=100)
    spec = StrategySpec('continuous', (), (), 1, 1, 1, 5000, 2, 3)

    def data(self, days, moves):
        times = pd.to_datetime(days, utc=True).to_numpy()
        moves = np.asarray(moves)
        open_ = np.full((len(times), 2), 100.0)
        close = open_ * (1 + np.column_stack([moves, -moves]))
        return MarketData(times, ('A', 'B'), open_, np.maximum(open_, close),
                          np.minimum(open_, close), close, np.ones_like(close))

    def run_segment(self, data, **kwargs):
        return run_backtest(data, np.tile([1., -1.], (len(data.timestamps), 1)),
                            kwargs.pop('spec', self.spec), self.execution,
                            kwargs.pop('risk', self.risk), self.capital, **kwargs)

    def test_default_and_initial_state_are_identical(self):
        data = self.data(['2025-01-31 14:30', '2025-01-31 15:30',
                          '2025-02-03 14:30', '2025-02-03 15:30'],
                         [0, .02, -.01, .01])
        legacy_log, state_log = [], []
        legacy = self.run_segment(data, trade_log=legacy_log)
        state = AccountState()
        continuous = self.run_segment(data, account_state=state, trade_log=state_log)
        self.assertEqual(legacy.to_dict(), continuous.to_dict())
        self.assertEqual(legacy_log, state_log)
        self.assertEqual(state.equity, state_log[-1]['equity'])
        self.assertEqual(state.current_date, pd.Timestamp('2025-02-03').date())

    def test_session_splits_match_unsplit_ledger_and_account(self):
        days = [f'{day} {hour}:30' for day in ('2025-01-31', '2025-02-03', '2025-03-03')
                for hour in (14, 15, 16, 17)]
        data = self.data(days, [0, .02, -.01, .01, -.02, .01, .03, -.01, .01, -.01, .02, .01])
        # A holding interval ends at each daily close, including the split days.
        spec = replace(self.spec, hold_bars=3)
        for delay in (0, 1):
            for exit_mode in ('independent', 'joint_close', 'fixed_close'):
                with self.subTest(delay=delay, exit_mode=exit_mode):
                    whole_state, split_state = AccountState(), AccountState()
                    whole_log, split_log = [], []
                    whole = self.run_segment(data, spec=spec, account_state=whole_state,
                                             trade_log=whole_log, signal_delay_bars=delay,
                                             exit_mode=exit_mode)
                    segments = [self.run_segment(data, spec=spec, start=a, stop=b,
                                                 account_state=split_state, trade_log=split_log,
                                                 signal_delay_bars=delay, exit_mode=exit_mode)
                                for a, b in ((0, 4), (4, 8), (8, 12))]
                    self.assertEqual(whole_log, split_log)
                    self.assertEqual(whole_state, split_state)
                    self.assertAlmostEqual(np.prod([1 + r.total_return for r in segments]) - 1,
                                           whole.total_return)
                    self.assertAlmostEqual(max(r.max_drawdown for r in segments), whole.max_drawdown)
                    self.assertEqual(sum(r.rounds for r in segments), whole.rounds)
                    self.assertAlmostEqual(sum(r.costs for r in segments), whole.costs)

    def test_drawdown_halt_carries_across_months_and_cannot_restart(self):
        data = self.data(['2025-01-31 14:30', '2025-01-31 15:30',
                          '2025-02-03 14:30', '2025-02-03 15:30',
                          '2025-03-03 14:30', '2025-03-03 15:30'],
                         [0, -.02, -.02, .10, .10, .10])
        risk = replace(self.risk, max_drawdown=.03)
        state, ledger = AccountState(), []
        first = self.run_segment(data, stop=2, risk=risk, account_state=state, trade_log=ledger)
        self.assertFalse(first.mdd_halt)
        second = self.run_segment(data, start=2, stop=4, risk=risk, account_state=state, trade_log=ledger)
        self.assertTrue(second.mdd_halt)
        self.assertAlmostEqual(second.total_return, -.02)
        self.assertAlmostEqual(second.max_drawdown, 1 - .98 ** 2)
        equity_after_halt = state.equity
        third = self.run_segment(data, start=4, risk=risk, account_state=state, trade_log=ledger)
        self.assertTrue(third.mdd_halt)
        self.assertEqual(third.rounds, 0)
        self.assertEqual(third.total_return, 0)
        self.assertEqual(state.equity, equity_after_halt)
        self.assertAlmostEqual(third.max_drawdown, second.max_drawdown)
        whole_log = []
        whole = self.run_segment(data, risk=risk, trade_log=whole_log)
        self.assertEqual(whole_log, ledger)
        self.assertAlmostEqual(whole.total_return, state.equity / self.capital - 1)
        # A resetting control trades the recovery, demonstrating the prior bug.
        reset = self.run_segment(data, start=2, stop=4, risk=risk)
        self.assertFalse(reset.mdd_halt)
        self.assertGreater(reset.rounds, second.rounds)

    def test_peak_is_carried_and_segment_return_uses_starting_equity(self):
        data = self.data(['2025-01-31 14:30', '2025-01-31 15:30',
                          '2025-02-03 14:30', '2025-02-03 15:30'],
                         [0, .10, -.02, -.02])
        state = AccountState()
        self.run_segment(data, stop=2, account_state=state)
        inherited_peak = state.peak
        second = self.run_segment(data, start=2, account_state=state)
        self.assertEqual(state.peak, inherited_peak)
        self.assertAlmostEqual(second.total_return, .98 ** 2 - 1)
        self.assertAlmostEqual(second.max_drawdown, 1 - .98 ** 2)
        self.assertAlmostEqual(state.equity, self.capital * 1.1 * .98 ** 2)

    def test_loss_streak_and_cooldown_are_not_reset_by_new_segment(self):
        data = self.data(['2025-01-31 14:30', '2025-01-31 15:30',
                          '2025-02-03 14:30', '2025-02-03 15:30',
                          '2025-02-03 16:30', '2025-02-03 17:30'],
                         [0, -.01, -.01, .02, .02, .02])
        state, split_log = AccountState(), []
        risk = replace(self.risk, max_loss_streak=2)
        self.run_segment(data, stop=2, risk=risk, account_state=state, trade_log=split_log)
        self.assertEqual(state.loss_streak, 1)
        second = self.run_segment(data, start=2, risk=risk, account_state=state, trade_log=split_log)
        self.assertEqual([row['signal_index'] for row in split_log], [0, 1, 4])
        self.assertEqual(second.rounds, 2)
        self.assertEqual(state.cooldown_until, 5)
        self.assertEqual(state.loss_streak, 0)
        whole_log = []
        self.run_segment(data, risk=risk, trade_log=whole_log)
        self.assertEqual(whole_log, split_log)

    def test_daily_limits_reset_on_new_session_but_not_account_peak(self):
        data = self.data(['2025-01-31 14:30', '2025-01-31 15:30', '2025-01-31 16:30',
                          '2025-02-03 14:30', '2025-02-03 15:30'],
                         [0, -.02, .10, .01, .01])
        risk = replace(self.risk, daily_soft_loss=.01, daily_hard_loss=.015)
        state, ledger = AccountState(), []
        first = self.run_segment(data, stop=3, risk=risk, account_state=state, trade_log=ledger)
        self.assertEqual(first.hard_halts, 1)
        self.assertEqual(state.daily_start, self.capital)
        next_daily_start = state.equity
        self.run_segment(data, start=3, risk=risk, account_state=state, trade_log=ledger)
        self.assertEqual(state.daily_start, next_daily_start)
        whole_log = []
        whole = self.run_segment(data, risk=risk, trade_log=whole_log)
        self.assertEqual(whole_log, ledger)
        self.assertAlmostEqual(whole.total_return, state.equity / self.capital - 1)

    def test_inactive_segment_preserves_risk_and_prior_drawdown(self):
        data = self.data(['2025-02-03 14:30', '2025-02-03 15:30'], [0, .1])
        state = AccountState(equity=98_000., peak=105_000., daily_start=99_000.,
                             current_date=pd.Timestamp('2025-01-31').date(),
                             cooldown_until=50, loss_streak=2, killed=True)
        result = self.run_segment(data, account_state=state)
        self.assertEqual(result.rounds, 0)
        self.assertTrue(result.mdd_halt)
        self.assertEqual(state.equity, 98_000.)
        self.assertEqual(state.peak, 105_000.)
        self.assertEqual(state.loss_streak, 2)
        self.assertAlmostEqual(result.max_drawdown, 1 - 98_000 / 105_000)

    def test_mid_session_stop_is_rejected_before_mutating_state(self):
        data = self.data(['2025-01-31 14:30', '2025-01-31 15:30',
                          '2025-01-31 16:30'], [0, .01, .01])
        state = AccountState()
        with self.assertRaisesRegex(ValueError, 'session boundary'):
            self.run_segment(data, stop=2, account_state=state)
        self.assertEqual(state, AccountState())


if __name__ == '__main__':
    unittest.main()
