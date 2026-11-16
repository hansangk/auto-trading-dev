import sys
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from session_clock_retry import clock_mask

class SessionClockTests(unittest.TestCase):
    def test_clock_gate_uses_order_hour_under_delay_and_overnight(self):
        times=pd.DatetimeIndex(['2025-01-06 15:30','2025-01-07 09:30','2025-01-07 10:30','2025-01-07 11:30'],tz='America/New_York').tz_convert('UTC')
        for delay in (0,1):
            for hours in ((9,),(10,11)):
                mask=clock_mask(times,hours,delay)
                for entry in range(1+delay,len(times)):
                    self.assertEqual(mask[entry-1-delay],times[entry].tz_convert('America/New_York').hour in hours)
        np.testing.assert_equal(clock_mask(times,(9,),0),[True,False,False,False])
