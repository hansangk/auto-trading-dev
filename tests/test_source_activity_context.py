import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import unittest
import numpy as np
import pandas as pd
from source_activity_context_20261119 import seasonal_features,previous_bar

class SeasonalContextTests(unittest.TestCase):
    def fixture(self,n=45):
        dates=pd.bdate_range('2025-01-02',periods=n)
        opens=pd.DatetimeIndex([pd.Timestamp(str(d.date())+' 09:30',tz='America/New_York').tz_convert('UTC') for d in dates])
        schedule=pd.DataFrame({'open':opens,'close':opens+pd.Timedelta(minutes=390)},index=dates.strftime('%Y-%m-%d'))
        f=pd.DataFrame({'day':schedule.index,'start':opens,'end':opens+pd.Timedelta(hours=1),'open':100.,'high':102.,'low':99.,'close':101.,'volume':10.})
        return f,schedule
    def test_current_donor_excluded_and_future_mutation_cannot_rewrite(self):
        f,s=self.fixture();f.loc[20,'volume']=100
        full=seasonal_features(f,s)
        self.assertEqual(full['rvol20'][20],10)
        future=f.copy();future.loc[21:,'volume']=1000000
        np.testing.assert_allclose(seasonal_features(future,s)['rvol20'][:21],full['rvol20'][:21],equal_nan=True)
        np.testing.assert_allclose(seasonal_features(f.iloc[:21],s)['rvol20'],full['rvol20'][:21],equal_nan=True)
    def test_missing_or_zero_calendar_donor_not_skipped(self):
        f,s=self.fixture();f.loc[10,'volume']=0
        self.assertTrue(np.isnan(seasonal_features(f,s)['rvol20'][25]))
        missing=f.drop(index=10).reset_index(drop=True)
        target=missing.index[missing.day==f.day.iloc[25]][0]
        self.assertTrue(np.isnan(seasonal_features(missing,s)['rvol20'][target]))
        self.assertEqual(seasonal_features(f,s)['rvol20'][31],1)
    def test_same_slot_not_adjacent_daily_open_and_no_overnight_pair(self):
        f,s=self.fixture();self.assertEqual(previous_bar(f,1),-1)
        f=f.iloc[:2].copy();f.loc[1,'day']=f.loc[0,'day'];f.loc[1,'start']=f.loc[0,'end'];f.loc[1,'end']=f.loc[1,'start']+pd.Timedelta(hours=1)
        self.assertEqual(previous_bar(f,1),0)
        f.loc[1,'start']+=pd.Timedelta(minutes=5)
        self.assertEqual(previous_bar(f,1),-1)

if __name__=='__main__':unittest.main()
