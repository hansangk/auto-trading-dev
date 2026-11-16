import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import numpy as np
from event_entry_retry_20261116 import event_mask
class EventEntryTests(unittest.TestCase):
 def test_new_active_direction_and_missing_role(self):
  s=np.array([[0,0,0,0],[1,0,0,0],[1,0,0,0],[1,0,0,-1],[1,0,0,0],[0,1,0,0],[0,0,0,0],[0,0,-1,0]],float)
  np.testing.assert_array_equal(event_mask(s),[False,True,False,True,False,True,False,True])
 def test_prefix_and_zero_history(self):
  s=np.array([[1,0,0,-1],[1,0,0,-1],[0,1,-1,0]],float)
  self.assertTrue(event_mask(s)[0]);np.testing.assert_array_equal(event_mask(s[:2]),event_mask(s)[:2])
