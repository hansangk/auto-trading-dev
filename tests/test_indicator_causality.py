import unittest
from dataclasses import replace
import numpy as np
from autogrid.features import FeatureCache
from test_core import CoreTests

class IndicatorCausalityTests(unittest.TestCase):
 def test_new_indicators_do_not_change_with_later_prices(self):
  data=CoreTests()._data();names=('stoch_5','williams_5','stochrsi_5','macd_3_7_3','cci_5','mfi_5','bbwidth_5','keltner_5','bb_rsi_5','macd_volume_5')
  before=FeatureCache(data)
  altered=replace(data,close=data.close.copy(),high=data.high.copy(),low=data.low.copy(),volume=data.volume.copy())
  altered.close[10:]*=2;altered.high[10:]*=3;altered.low[10:]*=.5;altered.volume[10:]*=10
  after=FeatureCache(altered)
  for name in names:
   with self.subTest(name=name):np.testing.assert_array_equal(before.get(name)[:10],after.get(name)[:10])
