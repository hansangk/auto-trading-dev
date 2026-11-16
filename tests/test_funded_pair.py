import unittest
import numpy as np
import pandas as pd
from autogrid.data import MarketData
from autogrid.engine import run_backtest
from autogrid.config import ExecutionConfig,RiskConfig
from autogrid.strategy import StrategySpec
class FundedPairTests(unittest.TestCase):
 def data(self, op, cl):
  op=np.array(op,float);cl=np.array(cl,float)
  return MarketData(pd.date_range('2025-01-02 14:30',periods=len(op),freq='h',tz='UTC').to_numpy(),('TQQQ','BITI'),op,np.maximum(op,cl),np.minimum(op,cl),cl,np.ones_like(op)*100,bar_minutes=60)
 def test_both_etfs_gain_and_no_borrow(self):
  d=self.data([[100,100]]*3,[[100,100],[101,102],[100,100]])
  score=np.array([[1,-1],[0,0],[0,0]],float);sp=StrategySpec('x',(),(),1,1,1,100,3,0)
  log=[];r=run_backtest(d,score,sp,ExecutionConfig(0,0,99999),RiskConfig(),100000,funded_pair=True,trade_log=log,exit_mode='joint_close')
  self.assertAlmostEqual(r.total_return,.003);self.assertEqual(log[0]['bought_symbols'],['TQQQ','BITI']);self.assertEqual(log[0]['cost_return'],0)
 def test_joint_stop_fills_next_open_gap(self):
  d=self.data([[100,100],[100,100],[90,90],[100,100]],[[100,100],[95,95],[100,100],[100,100]])
  score=np.zeros((4,2));score[0]=[1,-1];sp=StrategySpec('x',(),(),1,1,3,100,3,0)
  r=run_backtest(d,score,sp,ExecutionConfig(0,0,0),RiskConfig(),100000,funded_pair=True,exit_mode='joint_close')
  self.assertAlmostEqual(r.total_return,-.02)
