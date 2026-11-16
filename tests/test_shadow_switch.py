import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from shadow_switch_retry import reversion_signal, switch_signal


class ShadowSwitchTests(unittest.TestCase):
    def test_prefix_invariance(self):
        ratio = pd.Series(np.sin(np.arange(160) / 7) + np.arange(160) / 100)
        for confirm in (False, True):
            full = reversion_signal(ratio, 12, 1., confirm)
            np.testing.assert_array_equal(full[:100], reversion_signal(ratio[:100], 12, 1., confirm))
            np.testing.assert_array_equal(full[:, 0], -full[:, 1])
            if confirm:
                active = full[:, 0] != 0
                self.assertTrue(np.all(full[active, 0] * ratio.diff().to_numpy()[active] > 0))

    def test_routing_is_exclusive(self):
        trend = np.array([[1., -1.], [-1., 1.], [1., -1.]])
        alt = -trend
        actual = switch_signal(trend, alt, np.array([True, False, True]))
        np.testing.assert_array_equal(actual, np.array([[1., -1.], [1., -1.], [1., -1.]]))
