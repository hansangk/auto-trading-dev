import unittest
import numpy as np
import pandas as pd
from autogrid.data import MarketData
from autogrid.engine import run_backtest
from autogrid.config import ExecutionConfig,RiskConfig
from autogrid.strategy import StrategySpec

class JointExitTests(unittest.TestCase):
    def test_close_trigger_fills_next_open_with_gap(self):
        op=np.array([[100,100],[100,100],[90,110],[100,100]],dtype=float)
        cl=np.array([[100,100],[95,105],[100,100],[100,100]],dtype=float)
        data=MarketData(pd.date_range('2025-01-02 14:30',periods=4,freq='h',tz='UTC').to_numpy(),('A','B'),op,np.maximum(op,cl),np.minimum(op,cl),cl,np.ones_like(op)*100,bar_minutes=60)
        score=np.zeros_like(op);score[0]=[1,-1]
        spec=StrategySpec('test',(),(),1,1,3,100,3,0)
        log=[]
        r=run_backtest(data,score,spec,ExecutionConfig(0,0,0),RiskConfig(),100000,exit_mode='joint_close',trade_log=log)
        self.assertEqual(r.rounds,1)
        self.assertAlmostEqual(r.total_return,-.02)
        self.assertEqual(log[0]['end'],str(data.timestamps[2]))
        fixed=run_backtest(data,score,spec,ExecutionConfig(0,0,0),RiskConfig(),100000,exit_mode='fixed_close')
        self.assertAlmostEqual(fixed.total_return,0)
