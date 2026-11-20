import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import numpy as np
import pandas as pd
from autogrid.data import MarketData
from signal_decay_labels_20261116 import label_paths
from direction_exhaustion_retry_20261116 import signals
class DecayLabelTests(unittest.TestCase):
 def test_labels_exclude_overnight_and_use_correct_delayed_signal(self):
  times=pd.DatetimeIndex(['2025-01-02T19:30Z','2025-01-02T20:30Z','2025-01-03T14:30Z','2025-01-03T15:30Z'])
  op=np.full((4,4),100.);cl=op.copy();cl[:,0]=[101,102,103,104]
  d=MarketData(times.to_numpy(),('TQQQ','SQQQ','IBIT','BITI'),op,np.maximum(op,cl),np.minimum(op,cl),cl,np.ones_like(op),bar_minutes=60)
  s=np.zeros((4,4));s[0,0]=1
  labels=label_paths(d,times,s)
  a=labels[(labels.delay==0)&(labels.hold==1)].iloc[0]
  self.assertAlmostEqual(a.gross_mean,.02);self.assertEqual(a.signal_index,0)
  self.assertFalse(((labels.delay==0)&(labels.hold>1)).any())
  b=labels[(labels.delay==1)&(labels.hold==1)].iloc[0]
  self.assertEqual(b.signal_index,0);self.assertAlmostEqual(b.gross_mean,.03)
 def test_real_inverse_swap_preserves_role_counts_and_is_involution(self):
  n=100;times=pd.date_range('2025-01-02T14:30Z',periods=n,freq='h');x=np.arange(n)
  close=np.column_stack([100*np.exp(.002*x),100*np.exp(-.002*x),100*np.exp(-.001*x),100*np.exp(.001*x)])
  d=MarketData(times.to_numpy(),('TQQQ','SQQQ','IBIT','BITI'),close,close,close,close,np.ones_like(close),bar_minutes=60)
  result=signals(d,times);anchor=result['single8'];inv=result['flip_all8']
  self.assertTrue(np.any(anchor));np.testing.assert_array_equal(inv[:,[1,0,3,2]],anchor)
  np.testing.assert_array_equal(np.count_nonzero(inv,axis=1),np.count_nonzero(anchor,axis=1))
