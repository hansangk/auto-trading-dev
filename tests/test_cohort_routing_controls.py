import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import numpy as np
from cohort_routing_controls_20261117 import source_union
class SourceUnionTests(unittest.TestCase):
 def test_gap_role_priority_and_other_volume_role_preserved(self):
  g=np.array([[1,0,0,0],[0,0,-1,0],[0,0,0,0]],float);v=np.array([[0,1,0,-1],[1,0,0,-1],[0,1,-1,0]],float)
  result=source_union(g,v);np.testing.assert_array_equal(result,[[1,0,0,-1],[1,0,-1,0],[0,1,-1,0]])
  self.assertTrue((np.count_nonzero(result,axis=1)<=2).all())
 def test_reject_shape(self):
  with self.assertRaises(ValueError):source_union(np.zeros((3,3)),np.zeros((3,3)))
