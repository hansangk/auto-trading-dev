import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from anchor_filter_audit import masks,attribute


class FilterAuditTests(unittest.TestCase):
    def test_attribution_conserves_rounds_and_returns(self):
        log=[dict(signal_index=0,net_return=.02),dict(signal_index=2,net_return=-.01)]
        result=attribute(log,np.array([True,False,False]))
        self.assertEqual(sum(r['rounds'] for r in result),2)
        self.assertAlmostEqual(sum(r['sum_net_return'] for r in result),.01)
        self.assertEqual(result[0]['wins'],1)

    def test_efficiency_partition_and_direction_neutral(self):
        f=masks(np.array([1,-1,0]),np.array([1,1,0]),np.array([-1,-1,0]),np.array([.1,.3,.5]))
        np.testing.assert_equal(f['eff_low'].astype(int)+f['eff_mid']+f['eff_high'],np.ones(3))
        self.assertFalse((f['two_agree']&f['two_oppose']).any())
        self.assertFalse(f['daily_agree'][-1])
