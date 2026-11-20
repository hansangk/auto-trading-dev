import sys,unittest
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from shadow_gate_retry import make_gate

class ShadowGateTests(unittest.TestCase):
    def test_future_outcome_cannot_change_past_gate(self):
        times=pd.date_range('2025-01-02',periods=8,freq='h',tz='UTC')
        log=[dict(end=str(times[2]),net_return=.01),dict(end=str(times[6]),net_return=-.02)]
        gate=make_gate(times,log,1,0)
        self.assertFalse(gate[2]);self.assertTrue(gate[3]);self.assertTrue(gate[6]);self.assertFalse(gate[7])
        log[1]['net_return']=.02
        changed=make_gate(times,log,1,0)
        self.assertEqual(gate[:7].tolist(),changed[:7].tolist())
