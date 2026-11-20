import unittest,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from latency_statistics_20261119 import paired_effect

class LatencyStatisticsTests(unittest.TestCase):
    def test_pooled_event_mean_not_equal_day_mean(self):
        r=paired_effect([1,3,5],['a','a','b'],['a','b','c']);self.assertEqual(r['mean'],3);self.assertEqual(r['events'],3);self.assertFalse(r['support_pass']);self.assertIsNone(r['block_lower'])
    def test_constant_effect_empty_calendar_days_and_scaling(self):
        days=[str(i) for i in range(40)];events=days[:24];r=paired_effect(np.full(24,.002),events,days,200,3)
        self.assertTrue(r['support_pass']);self.assertAlmostEqual(r['block_lower'],.002);self.assertAlmostEqual(r['day_upper'],.002);self.assertEqual(r['observed_days'],40)
        z=paired_effect(np.full(24,.006),events,days,200,3);self.assertAlmostEqual(z['mean'],3*r['mean'])
    def test_null_and_undefined_cases(self):
        days=[str(i) for i in range(24)];r=paired_effect(np.zeros(24),days,days,200,4);self.assertEqual(r['block_lower'],0);self.assertEqual(r['day_upper'],0)
        r=paired_effect([],[],days);self.assertIsNone(r['mean']);self.assertEqual(r['events'],0)
        with self.assertRaises(ValueError):paired_effect([float('nan')],['a'],['a'])

if __name__=='__main__':unittest.main()
