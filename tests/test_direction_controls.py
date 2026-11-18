from pathlib import Path
import sys,unittest
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from direction_control_20261119 import controlled_scores,FAMILIES

class DirectionControlsTests(unittest.TestCase):
    def setUp(self):
        self.times=pd.date_range('2026-09-01T13:30Z',periods=8,freq='5min')
        self.source=np.zeros((8,4));self.source[[0,2,4],0]=1;self.source[[0,2],2]=-1
    def test_deterministic_and_inactive_roles_stay_cash(self):
        original=self.source.copy()
        for f in FAMILIES:
            a=controlled_scores(self.source,self.times,f,3)
            np.testing.assert_array_equal(a,controlled_scores(self.source,self.times,f,3))
            np.testing.assert_array_equal(np.any(a[:,:2],axis=1),np.any(self.source[:,:2],axis=1))
            np.testing.assert_array_equal(np.any(a[:,2:],axis=1),np.any(self.source[:,2:],axis=1))
        np.testing.assert_array_equal(original,self.source)
    def test_shared_roles_have_same_direction(self):
        for f in ('event_shared','session_shared'):
            result=controlled_scores(self.source,self.times,f,2)
            for i in (0,2):self.assertEqual(result[i,0]!=0,result[i,2]!=0)
    def test_session_direction_fixed(self):
        for f in ('session_shared','session_independent'):
            result=controlled_scores(self.source,self.times,f,5)
            self.assertEqual(np.argmax(abs(result[0,:2])),np.argmax(abs(result[4,:2])))
            self.assertEqual(np.argmax(abs(result[0,2:])),np.argmax(abs(result[2,2:])))
    def test_prefix_causality_and_rejection(self):
        for f in FAMILIES:
            full=controlled_scores(self.source,self.times,f,7)
            np.testing.assert_array_equal(controlled_scores(self.source[:3],self.times[:3],f,7),full[:3])
        with self.assertRaises(ValueError):controlled_scores(self.source,self.times,'unknown',0)
