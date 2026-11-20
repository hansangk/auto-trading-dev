import sys
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from structure_mtf_retry import structure, route


class StructureTests(unittest.TestCase):
    def test_completed_frames_prefix_invariance(self):
        times = pd.DatetimeIndex([d+pd.Timedelta(hours=h,minutes=30) for d in pd.date_range('2025-01-06',periods=12,tz='America/New_York') for h in range(9,16)]).tz_convert('UTC')
        ratio = pd.Series(np.sin(np.arange(len(times))/4)+np.arange(len(times))*.02)
        full = structure(times,ratio)
        for n in range(8,len(times)):
            prefix = structure(times[:n],ratio[:n])
            for a,b in zip(full,prefix):
                np.testing.assert_allclose(a[:n],b)
        # 09:30 cannot update a completed 2h block; daily direction stays fixed all session.
        for i in range(7,len(times),7):
            self.assertEqual(full[0][i],full[0][i-1])
            np.testing.assert_equal(full[1][i:i+7],full[1][i])

    def test_router_separates_regimes(self):
        trend=np.array([[1.,-1.]]*3); mr=-trend
        out,state=route(trend,mr,np.array([1,1,-1]),np.array([1,-1,1]),np.array([.5,.05,.3]),.2,True,True)
        np.testing.assert_equal(state,[1,2,0])
        np.testing.assert_equal(out,np.array([[1,-1],[-1,1],[0,0]]))
