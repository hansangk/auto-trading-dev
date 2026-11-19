import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import numpy as np
from venue_isolation_signals_20261119 import intervene,candidates

class IsolationTests(unittest.TestCase):
    def test_partition_and_no_rearm(self):
        coin=np.zeros((8,4));coin[[0,1,4,7],[2,3,2,3]]=-1
        nas=np.zeros_like(coin);nas[[0,3,7],[0,1,0]]=1
        sync=intervene(coin,nas,'sync');other=intervene(coin,nas,'async')
        np.testing.assert_array_equal(sync+other,coin)
        self.assertEqual(list(np.flatnonzero(np.any(sync,axis=1))),[0,7])
        self.assertEqual(list(np.flatnonzero(np.any(other,axis=1))),[1,4])
        np.testing.assert_array_equal(intervene(coin,nas,'full'),coin+nas)
        np.testing.assert_array_equal(intervene(coin,nas,'coin'),coin)
    def test_prefix_and_no_mutation(self):
        coin=np.zeros((11,4));coin[[1,5,9],[2,3,2]]=-1;nas=np.zeros_like(coin);nas[5,0]=1
        original=coin.copy()
        for scope in ('full','coin','sync','async'):
            whole=intervene(coin,nas,scope)
            for n in range(12):np.testing.assert_array_equal(intervene(coin[:n],nas[:n],scope),whole[:n])
        np.testing.assert_array_equal(coin,original)
        self.assertEqual(len({x['name'] for x in candidates()}),16)
    def test_invalid(self):
        coin=np.zeros((2,4));nas=np.zeros_like(coin);coin[0,2]=-1;nas[0,2]=1
        with self.assertRaises(ValueError):intervene(coin,nas,'coin')
        for c,n,s in [(np.zeros((1,3)),np.zeros((1,3)),'full'),(np.zeros((1,4)),np.zeros((1,4)),'unknown')]:
            with self.assertRaises(ValueError):intervene(c,n,s)
