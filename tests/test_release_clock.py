import unittest
from dataclasses import replace
import numpy as np
import pandas as pd
from autogrid.data import MarketData
from release_clock_20261119 import first_hour_return,decision_mask,policy_scores
from release_clock_retry_20261119 import scores_with_full_horizon,paired_events

class ReleaseClockTests(unittest.TestCase):
    def fixture(self):
        times=pd.date_range('2026-09-01 09:30',periods=78,freq='5min',tz='America/New_York').tz_convert('UTC')
        ones=np.ones((78,4));data=MarketData(times.to_numpy(),('TQQQ','SQQQ','IBIT','BITI'),100*ones,102*ones,99*ones,101*ones,ones,bar_minutes=5)
        return data,times
    def test_first_hour_needs_completion_and_buffer(self):
        d,t=self.fixture();ix=np.arange(78)
        self.assertTrue(np.isnan(first_hour_return(d,t,ix,t[12])))
        self.assertAlmostEqual(first_hour_return(d,t,ix,t[13]),np.log(1.01))
    def test_first_hour_cannot_be_manufactured_from_partial_prefix(self):
        d,t=self.fixture()
        self.assertTrue(np.isnan(first_hour_return(d,t,np.arange(11),t[13])))
        bad=t.delete(6)
        self.assertTrue(np.isnan(first_hour_return(d,bad,np.arange(12),t[13])))
    def test_source_available_between_coarse_decisions_does_not_consume_onset(self):
        d,t=self.fixture();n=len(t)
        ctx={k:np.ones(n)*.01 for k in ('night_return','night_scale','qqq_regime5','qqq_gap','ibit_gap','same_day_first_ibit','qqq_rth')}
        ctx['btc_now']=np.ones(n)*100;ctx['first_btc_preopen_price']=np.ones(n)*100
        ctx['valid']=np.ones(n,bool);ctx['qqq_rth'][:12]=np.nan
        fine=policy_scores(d,t,ctx,'release5')['nasdaq_source'];coarse=policy_scores(d,t,ctx,'coarse60')['nasdaq_source']
        self.assertEqual(np.flatnonzero(fine.any(axis=1)).tolist(),[12])
        self.assertEqual(np.flatnonzero(coarse.any(axis=1)).tolist(),[23])
        self.assertFalse(np.any(fine[decision_mask(t,'coarse60')]))
    def test_longest_stress_fits_actual_session(self):
        d,t=self.fixture();s=np.zeros(d.shape);s[:,0]=1
        filtered=scores_with_full_horizon(s,t,240)
        for signal in np.flatnonzero(filtered.any(axis=1)):
            entry=signal+2;end=entry+47
            self.assertLess(end,len(t))
            self.assertEqual(t[end]+pd.Timedelta(minutes=5)-t[entry],pd.Timedelta(minutes=240))
    def test_pairing_requires_actual_used_dependency_not_same_day_alone(self):
        d,t=self.fixture();scores={}
        from release_clock_20261119 import POLICIES
        for p in POLICIES:
            for clock in ('coarse60','release5'):scores[f'{p}_{clock}_240']=np.zeros(d.shape)
        # Current BTC IDs differ: Bitcoin snapshots are unmatched. Nasdaq uses
        # the SAME QQQ dependency and frozen daily night; unused BTC age differs.
        for p,target in [('nasdaq_source',0),('btc_acceptance',2)]:
            scores[f'{p}_coarse60_240'][23,target]=1
            scores[f'{p}_release5_240'][12,target]=1
        trace=pd.DataFrame(dict(day=['2026-09-01']*78,qqq_index=np.ones(78,int),btc_index=np.arange(78)))
        pairs=paired_events(scores,t,trace,240)
        self.assertEqual(pairs.policy.tolist(),['nasdaq_source'])

if __name__=='__main__':unittest.main()
