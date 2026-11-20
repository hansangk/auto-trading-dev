import sys,unittest
from pathlib import Path
import pandas as pd
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from nasdaq_gate_statistics_20261119 import matched_effect

class NasdaqGateStatisticsTests(unittest.TestCase):
    def fixture(self):
        days=pd.bdate_range('2025-01-01',periods=24).strftime('%Y-%m-%d').tolist()
        f=pd.DataFrame([dict(day=d,stratum='up_gapup_early',admit=a,net=.001 if a else -.001) for d in days for a in (0,1)])
        return f,days
    def test_constant_day_block_contrast_and_affine_invariance(self):
        f,d=self.fixture();r=matched_effect(f,d,200,123)
        self.assertTrue(r['information_pass']);self.assertAlmostEqual(r['contrast'],.002);self.assertAlmostEqual(r['block_lower'],.002);self.assertEqual(r['block_valid_draws'],200)
        g=f.copy();g.net=3*g.net+2;z=matched_effect(g,d,200,123)
        self.assertAlmostEqual(z['contrast'],3*r['contrast']);self.assertAlmostEqual(z['day_lower'],3*r['day_lower'])
    def test_sparse_unmatched_strata_do_not_create_evidence(self):
        f,d=self.fixture();extra=pd.DataFrame([dict(day=d[0],stratum='sparse',admit=1,net=1000)])
        r=matched_effect(pd.concat([f,extra],ignore_index=True),d,200,123)
        self.assertEqual(r['matched_events'],48);self.assertEqual(r['total_events'],49);self.assertAlmostEqual(r['contrast'],.002)
        r=matched_effect(f.iloc[:8],d,200,123);self.assertFalse(r['support_pass']);self.assertIsNone(r['contrast']);self.assertFalse(r['information_pass'])
    def test_null_and_future_unused_outcomes_do_not_change_membership(self):
        f,d=self.fixture();f.net=0;r=matched_effect(f,d,200,123)
        self.assertEqual(r['contrast'],0);self.assertEqual(r['block_lower'],0);self.assertFalse(r['information_pass'])
        f.loc[f.admit==1,'net']=9;z=matched_effect(f,d,200,123)
        self.assertEqual(z['matched_events'],r['matched_events']);self.assertEqual(z['strata'],r['strata'])

if __name__=='__main__':unittest.main()
