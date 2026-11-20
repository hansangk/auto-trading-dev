import unittest
import numpy as np
import pandas as pd
from autogrid.data import MarketData
from autogrid.engine import run_backtest
from autogrid.config import ExecutionConfig,RiskConfig
from autogrid.strategy import StrategySpec
class SingleFundedTests(unittest.TestCase):
 def setup_data(self,op,cl):
  op=np.array(op,float);cl=np.array(cl,float)
  return MarketData(pd.date_range('2025-01-02 14:30',periods=len(op),freq='h',tz='UTC').to_numpy(),('TQQQ','SQQQ','IBIT','BITI'),op,np.maximum(op,cl),np.minimum(op,cl),cl,np.ones_like(op)*100,bar_minutes=60)
 def test_each_role_buys_single_without_phantom_or_redistribution(self):
  d=self.setup_data([[100]*4]*3,[[100]*4,[101]*4,[100]*4]);sp=StrategySpec('x',(),(),1,1,1,60,3,0)
  for col,sign in [(0,1),(1,1),(2,-1),(3,-1)]:
   score=np.zeros((3,4));score[0,col]=sign;log=[]
   r=run_backtest(d,score,sp,ExecutionConfig(1,1,99999),RiskConfig(),100000,funded_pair=True,funded_allow_single=True,exit_mode='joint_close',trade_log=log)
   self.assertEqual(r.trades,1);self.assertEqual(log[0]['bought_symbols'],[d.symbols[col]])
   self.assertEqual(log[0]['bought_weights'],[.15]);self.assertAlmostEqual(r.total_return,.15*(.01-.0004))
 def test_single_joint_stop_next_open_gap(self):
  d=self.setup_data([[100]*4,[100]*4,[90]*4,[100]*4],[[100]*4,[95]*4,[100]*4,[100]*4]);s=np.zeros((4,4));s[0,3]=-1
  sp=StrategySpec('x',(),(),1,1,3,100,3,0)
  r=run_backtest(d,s,sp,ExecutionConfig(0,0,0),RiskConfig(),100000,funded_pair=True,funded_allow_single=True,exit_mode='joint_close')
  self.assertEqual(r.trades,1);self.assertAlmostEqual(r.total_return,-.01)
 def test_zero_cash_and_reject_ambiguous_multiple_roles(self):
  d=self.setup_data([[100]*4]*3,[[100]*4]*3);sp=StrategySpec('x',(),(),1,1,1,60,3,0)
  r=run_backtest(d,np.zeros((3,4)),sp,ExecutionConfig(),RiskConfig(),100000,funded_pair=True,funded_allow_single=True)
  self.assertEqual(r.rounds,0);self.assertEqual(r.total_return,0)
  s=np.zeros((3,4));s[0,:2]=1
  with self.assertRaises(ValueError):run_backtest(d,s,sp,ExecutionConfig(),RiskConfig(),100000,funded_pair=True,funded_allow_single=True)
