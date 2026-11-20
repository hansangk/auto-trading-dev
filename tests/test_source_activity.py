import sys
import unittest
from pathlib import Path
from dataclasses import replace
from copy import deepcopy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import numpy as np
import pandas as pd
from autogrid.data import MarketData
from source_activity_signals_20261119 import candidates, signals


class SourceActivityTests(unittest.TestCase):
    def fixture(self, n=5):
        times=pd.date_range('2025-02-03 09:30',periods=n,freq='h',tz='America/New_York').tz_convert('UTC')
        ones=np.ones((n,4))
        data=MarketData(times.to_numpy(),('TQQQ','SQQQ','IBIT','BITI'),100*ones,105*ones,95*ones,101*ones,ones,bar_minutes=60)
        values={key:np.full(n,value) for key,value in {
            'open':100.,'high':104.,'low':99.,'close':103.,'rvol20':2.,'rvol40':2.,
            'prev_open':100.,'prev_high':105.,'prev_low':99.,'prev_close':104.,
            'prev_rvol20':2.,'prev_rvol40':2.}.items()}
        values['prev_contiguous']=np.ones(n,bool)
        return data,times,dict(valid=np.ones(n,bool),source=deepcopy(values),ETF=deepcopy(values))
    def candidate(self,family):
        return next(c for c in candidates() if c['family']==family)
    def test_bounded_unique_grid_and_boolean_parameters_rejected(self):
        d,t,ctx=self.fixture();grid=candidates()
        self.assertEqual(len(grid),32);self.assertEqual(len({c['name'] for c in grid}),32)
        for key in ('lookback','a','b'):
            c=grid[0].copy();c[key]=True
            with self.assertRaises(ValueError):signals(d,t,ctx,c)
    def test_actual_inverse_buy_column_respects_symbol_order(self):
        d,t,ctx=self.fixture()
        for f in ('source','ETF'):
            ctx[f]['open'][:]=103.;ctx[f]['close'][:]=100.
        c=self.candidate('participation_follow');score=signals(d,t,ctx,c)
        self.assertEqual(score[0].tolist(),[0,1,0,0])
        order=[3,1,0,2];reordered=replace(d,symbols=tuple(d.symbols[j] for j in order),**{k:getattr(d,k)[:,order] for k in ('open','high','low','close','volume')})
        other=signals(reordered,t,ctx,c)
        np.testing.assert_array_equal(other,score[:,order])
    def test_prefix_invariance_for_all_families_and_feeds(self):
        d,t,ctx=self.fixture()
        for f in ('source','ETF'):
            ctx[f]['close'][:]=[103.,103.5,101.,102.,100.]
            ctx[f]['rvol20'][:]=[2.,1.,2.,.8,2.]
            ctx[f]['rvol40'][:]=[2.,1.,2.,.8,2.]
        for c in candidates():
            for feed in ('source','ETF'):
                all_scores=signals(d,t,ctx,c,feed)
                for n in (1,3):
                    prefix=replace(d,timestamps=d.timestamps[:n],**{k:getattr(d,k)[:n] for k in ('open','high','low','close','volume')})
                    pc={'valid':ctx['valid'][:n],**{f:{k:v[:n] for k,v in ctx[f].items()} for f in ('source','ETF')}}
                    np.testing.assert_array_equal(signals(prefix,t[:n],pc,c,feed),all_scores[:n])
    def test_missing_does_not_rearm_but_observed_false_does(self):
        d,t,ctx=self.fixture()
        for f in ('source','ETF'):ctx[f]['rvol20'][:]=[2.,np.nan,2.,1.,2.]
        s=signals(d,t,ctx,self.candidate('participation_follow'))
        self.assertEqual(np.flatnonzero(s.any(axis=1)).tolist(),[0,4])
    def test_volume_removal_keeps_price_predicate_and_common_support(self):
        d,t,ctx=self.fixture();c=self.candidate('participation_follow')
        ctx['source']['rvol20'][:]=.8
        self.assertFalse(signals(d,t,ctx,c).any())
        self.assertTrue(signals(d,t,ctx,c,volume_removed=True)[0,0])
        ctx['source']['close'][:]=100.01 # Price condition still fails.
        self.assertFalse(signals(d,t,ctx,c,volume_removed=True).any())
        ctx['source']['close'][:]=103.;ctx['ETF']['rvol20'][:]=np.nan
        self.assertFalse(signals(d,t,ctx,c,volume_removed=True).any())
    def test_two_bar_patterns_require_actual_same_session_contiguity(self):
        d,t,ctx=self.fixture()
        for f in ('source','ETF'):
            ctx[f]['open'][:]=104.;ctx[f]['high'][:]=105.;ctx[f]['low'][:]=101.;ctx[f]['close'][:]=102.
            ctx[f]['prev_rvol20'][:]=.4
            ctx[f]['prev_contiguous'][:]=False
        c=self.candidate('thin_move_reversal')
        self.assertFalse(signals(d,t,ctx,c).any())
        for f in ('source','ETF'):ctx[f]['prev_contiguous'][:]=True
        self.assertEqual(signals(d,t,ctx,c)[0].tolist(),[0,1,0,0])
    def test_absorption_and_quiet_hold_have_distinct_price_mechanisms(self):
        d,t,ctx=self.fixture()
        for f in ('source','ETF'):
            ctx[f]['open'][:]=103.;ctx[f]['close'][:]=103.1
        absorption=signals(d,t,ctx,self.candidate('absorption_recovery'))
        self.assertEqual(absorption[0].tolist(),[1,0,0,0])
        for f in ('source','ETF'):
            ctx[f]['open'][:]=104.;ctx[f]['high'][:]=104.5;ctx[f]['low'][:]=102.5;ctx[f]['close'][:]=103.
            ctx[f]['rvol20'][:]=.8
        hold=signals(d,t,ctx,self.candidate('burst_quiet_hold'))
        self.assertEqual(hold[0].tolist(),[1,0,0,0])
        for f in ('source','ETF'):ctx[f]['close'][:]=102.
        # Preserve valid OHLC while breaking the maximum allowed retracement.
        for f in ('source','ETF'):ctx[f]['low'][:]=101.5
        self.assertFalse(signals(d,t,ctx,self.candidate('burst_quiet_hold')).any())
    def test_selected_quote_failure_does_not_consume_valid_episode(self):
        d,t,ctx=self.fixture();bad=d.close.copy();bad[0,0]=np.nan
        d=replace(d,close=bad)
        s=signals(d,t,ctx,self.candidate('participation_follow'))
        self.assertEqual(np.flatnonzero(s.any(axis=1)).tolist(),[1])


if __name__=='__main__':unittest.main()
