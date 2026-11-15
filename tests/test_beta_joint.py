import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import unittest
import numpy as np
import pandas as pd
from autogrid.data import MarketData
from beta_joint_retry import simulate

class JointTests(unittest.TestCase):
 def make(self):
  ft=pd.date_range('2026-01-05 14:30',periods=6,freq='15min',tz='UTC')
  op=np.full((6,2),100.);op[2:,0]=98
  cl=op.copy();cl[1,0]=99
  data=MarketData(ft.to_numpy(),('A','B'),op,np.maximum(op,cl),np.minimum(op,cl),cl,np.ones((6,2)),bar_minutes=15)
  return data,ft
 def test_joint_stop_fills_next_open_and_includes_gap(self):
  data,ft=self.make();signal=np.array([1,0,0,0,0,0]);beta=np.ones(6)
  r=simulate(data,signal,beta,ft,np.arange(6)*15+570,15,0,6,6,30,1.5,0)
  self.assertEqual(r['rounds'],1)
  self.assertAlmostEqual(r['total_return'],-.002)
  self.assertAlmostEqual(r['long_pnl_fraction'],-.002)
  self.assertEqual(r['short_pnl_fraction'],0)
 def test_future_prices_after_exit_do_not_change_trade(self):
  data,ft=self.make();signal=np.array([1,0,0,0,0,0]);args=(signal,np.ones(6),ft,np.arange(6)*15+570,15,0,6,6,30,1.5,0)
  before=simulate(data,*args)
  data.close[3:]=1000;data.open[3:]=1
  self.assertEqual(before,simulate(data,*args))
 def test_stale_entry_is_skipped(self):
  data,ft=self.make();ft=pd.DatetimeIndex([ft[0],*[v+pd.Timedelta(minutes=15) for v in ft[1:]]])
  r=simulate(data,np.array([1,0,0,0,0,0]),np.ones(6),ft,np.arange(6)*15+570,15,0,6,6,30,1.5,0)
  self.assertEqual(r['rounds'],0)
