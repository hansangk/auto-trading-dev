import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from fixed_role_attribution_20261117 import (decompose_union_legs,
    conditional_cash_permutations, session_block_bootstrap, STRATA)


class FixedRoleAttributionTests(unittest.TestCase):
    def fixture(self):
        times = pd.date_range('2025-01-02 15:30Z', periods=4, freq='D')
        scores = np.array([[1, 0, 0, 0], [0, 1, -1, 0],
                           [0, 0, -1, 0], [1, 0, -1, 0]], float)
        logs = []
        for i in range(4):
            logs.append(dict(signal_index=i, equity=1003., pnl=3.,
                             bought_symbols=['TQQQ', 'IBIT'], bought_weights=[.1, .2],
                             long_gross_return=.004, short_gross_return=.002,
                             gross_return=.006, cost_return=.003, net_return=.003,
                             entry=str(times[i]), end=str(times[i])))
        return decompose_union_legs(logs, scores, times, np.array([[.1, .7]]*4),
                                    ('TQQQ', 'SQQQ', 'IBIT', 'BITI'))

    def test_capital_role_accounting_proportional_cost(self):
        frame = self.fixture()
        for _, g in frame.groupby('round_id'):
            self.assertAlmostEqual(g.cost_return_contribution.sum(), .003)
            self.assertAlmostEqual(g.net_amount.sum(), 3.)
            np.testing.assert_allclose(g.cost_amount, [1., 2.])
            np.testing.assert_allclose(g.gross_amount, [4., 2.])

    def test_replacement_never_forges_inverse_pnl(self):
        frame = self.fixture()
        replacement = frame[(frame.round_id == 1) & (frame.role == 'equity')].iloc[0]
        self.assertEqual(replacement.status, 'replacement')
        self.assertEqual(replacement.candidate_etf, 'SQQQ')
        self.assertEqual(replacement.gross_amount, 4.)
        self.assertEqual(replacement.selected_gross_amount, 0.)
        self.assertEqual(frame.iloc[1].status, 'suppressed')

    def test_conditional_counts_weights_and_nonvarying_strata(self):
        frame = self.fixture()
        draw, support, expected = conditional_cash_permutations(frame, draws=41)
        for role, g in frame.groupby('role'):
            subset = draw[draw.role == role]
            self.assertTrue((subset.orders == g.retained.sum()).all())
            np.testing.assert_allclose(subset.weight, g.loc[g.retained, 'weight'].sum())
        self.assertTrue(support.varying.all())
        self.assertAlmostEqual(expected.contrast_net_amount.sum(),
                               frame.selected_net_amount.sum()-expected.expected_net_amount.sum())
        frame.loc[:, 'retained'] = True
        draw, support, _ = conditional_cash_permutations(frame, draws=8)
        self.assertFalse(support.varying.any())
        np.testing.assert_allclose(draw[draw.role == 'all'].net_amount, frame.net_amount.sum())

    def test_permutations_match_every_stratum_with_different_weights(self):
        frame = self.fixture()
        # Two hours, weights not assumed constant; each observed weight gets its
        # own exact count within a requested stratum, never approximate matching.
        frame.loc[frame.round_id >= 2, 'signal_hour_ny'] = 11
        frame.loc[frame.round_id == 3, 'weight'] *= .5
        _, support, _ = conditional_cash_permutations(frame, draws=13)
        self.assertEqual(int(support.retained.sum()), int(frame.retained.sum()))
        self.assertEqual(int(support.opportunities.sum()), len(frame))
        self.assertEqual(len(support), len(frame.groupby(STRATA+['weight'])))

    def test_day_bootstrap_joint_sessions_reproducible(self):
        frame = self.fixture()
        a, _, enriched = conditional_cash_permutations(frame, draws=31)
        b, _, _ = conditional_cash_permutations(frame, draws=31)
        pd.testing.assert_frame_equal(a, b)
        boot = session_block_bootstrap(enriched, draws=101)
        pd.testing.assert_frame_equal(boot, session_block_bootstrap(enriched, draws=101))
        gross = boot[(boot.role == 'all') & (boot.metric == 'gross_amount')].iloc[0]
        self.assertEqual(gross.sessions, 4)
        self.assertAlmostEqual(gross.estimate, enriched.contrast_gross_amount.sum())
        self.assertLessEqual(gross.lower_95, gross.upper_95)
        pd.testing.assert_frame_equal(session_block_bootstrap(enriched, draws=101, block_days=2),
                                      session_block_bootstrap(enriched, draws=101, block_days=2))


if __name__ == '__main__':
    unittest.main()
