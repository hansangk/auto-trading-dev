import unittest
import numpy as np
import pandas as pd
from autogrid.data import MarketData
from autogrid.engine import run_backtest
from autogrid.config import ExecutionConfig,RiskConfig
from autogrid.strategy import StrategySpec

class ScaleTests(unittest.TestCase):
    def test_scaling_uses_only_signal_time_and_never_increases_leg(self):
        op=np.ones((3,2))*100
        cl=np.array([[100,100],[102,98],[102,98]],float)
        data=MarketData(pd.date_range('2025-01-02 14:30',periods=3,freq='h',tz='UTC').to_numpy(),('A','B'),op,np.maximum(op,cl),np.minimum(op,cl),cl,np.ones_like(op)*100)
        signal=np.zeros_like(op);signal[0]=[1,-1]
        spec=StrategySpec('s',(),(),1,1,1,100,3,0)
        scales=np.ones_like(op);scales[0]=[.5,1]
        args=(data,signal,spec,ExecutionConfig(0,0,0),RiskConfig(),100000)
        log=[]
        r=run_backtest(*args,exit_mode='fixed_close',asset_weight_scale=scales,trade_log=log)
        self.assertAlmostEqual(r.total_return,.003)
        self.assertAlmostEqual(log[0]['long_weight'],.05)
        scales[1:]=.1
        delayed=run_backtest(*args,exit_mode='fixed_close',asset_weight_scale=scales)
        self.assertEqual(r.to_dict(),delayed.to_dict())
        scales[0,0]=1.1
        with self.assertRaises(ValueError):run_backtest(*args,asset_weight_scale=scales)
