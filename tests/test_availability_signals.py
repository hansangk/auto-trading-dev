import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import unittest
from dataclasses import replace
import numpy as np
import pandas as pd
from autogrid.data import MarketData
from availability_signals_20261119 import candidates,signals,support
from source_activity_signals_20261119 import signals as old_signals


class AvailabilitySignalTests(unittest.TestCase):
    def fixture(self):
        times=pd.DatetimeIndex([t for d in ('2025-01-02','2025-01-03','2025-01-06')
                               for t in pd.date_range(d+' 09:30',periods=7,freq='h',tz='America/New_York')]).tz_convert('UTC')
        n=len(times);ones=np.ones((n,4))
        data=MarketData(times.to_numpy(),('TQQQ','SQQQ','IBIT','BITI'),100*ones,102*ones,99*ones,101*ones,ones,bar_minutes=60)
        close=np.array([101.8,100.,101.8,98.2,98.2,100.,101.8]*3)
        fields=dict(open=np.full(n,100.),high=np.full(n,102.),low=np.full(n,98.),close=close.copy())
        # Efficiency is .45 by default; use tighter widths for intended .6 cases.
        fields['high']=np.where(close<100,101.,102.)
        fields['low']=np.where(close>100,99.,98.)
        src={k:v.copy() for k,v in fields.items()};etf={k:v.copy() for k,v in fields.items()}
        for x in (src,etf):
            x['rvol20']=np.ones(n);x['rvol40']=np.ones(n)
        src['rvol20'][1]=np.nan;src['rvol40'][1:3]=np.nan
        ctx=dict(valid=np.ones(n,bool),source=src,ETF=etf,current_positive=np.ones(n,bool),
                 history20=np.isfinite(src['rvol20']),history40=np.isfinite(src['rvol40']))
        return data,times,ctx

    def test_exact_eight_fixed_definitions(self):
        cs=candidates();self.assertEqual(len(cs),8)
        self.assertEqual(len({(c['feed'],c['gate']) for c in cs}),8)
        d,t,ctx=self.fixture()
        with self.assertRaises(ValueError):signals(d,t,ctx,dict(feed='source',gate=True))
    def test_none_requires_no_volume_fields_or_masks(self):
        d,t,ctx=self.fixture()
        minimal={'valid':ctx['valid'],'source':{k:ctx['source'][k] for k in ('open','high','low','close')},
                 'ETF':{k:ctx['ETF'][k] for k in ('open','high','low','close')}}
        got=signals(d,t,minimal,dict(feed='source',gate='none'))
        for key in ('current_positive','history20','history40'):ctx[key]=np.zeros(len(t),bool)
        np.testing.assert_array_equal(got,signals(d,t,ctx,dict(feed='source',gate='none')))
    def test_current_mask_is_independent_of_history_availability(self):
        d,t,ctx=self.fixture();ctx['current_positive'][0]=False
        self.assertFalse(support(d,t,ctx,'current')[0])
        self.assertTrue(support(d,t,ctx,'current')[1])
        self.assertFalse(support(d,t,ctx,'L20')[1])
        ctx['history20']=np.ones(len(t))
        with self.assertRaises(ValueError):support(d,t,ctx,'L20')
    def test_legacy_volume_removed_arrays_exact_for_both_feeds(self):
        d,t,ctx=self.fixture()
        for feed in ('source','ETF'):
            for lookback in (20,40):
                c=dict(family='participation_follow',lookback=lookback,a=1.25,b=.5)
                expected=old_signals(d,t,ctx,c,feed,True)
                got=signals(d,t,ctx,dict(feed=feed,gate='L'+str(lookback)))
                np.testing.assert_array_equal(got,expected)
    def test_missing_support_does_not_rearm_onset(self):
        d,t,ctx=self.fixture()
        none=signals(d,t,ctx,dict(feed='source',gate='none'))
        old=signals(d,t,ctx,dict(feed='source',gate='L20'))
        self.assertEqual(none[2,0],1.)
        self.assertEqual(old[2,0],0.)
    def test_prefix_invariance_all_definitions(self):
        d,t,ctx=self.fixture()
        for n in (2,8,17):
            prefix=replace(d,timestamps=d.timestamps[:n],**{k:getattr(d,k)[:n] for k in ('open','high','low','close','volume')})
            pc={k:({j:v[:n] for j,v in value.items()} if isinstance(value,dict) else value[:n]) for k,value in ctx.items()}
            for c in candidates():np.testing.assert_array_equal(signals(prefix,t[:n],pc,c),signals(d,t,ctx,c)[:n])
    def test_actual_symbol_order_is_respected(self):
        d,t,ctx=self.fixture();ix=[3,1,0,2]
        reordered=replace(d,symbols=tuple(d.symbols[i] for i in ix),**{k:getattr(d,k)[:,ix] for k in ('open','high','low','close','volume')})
        for c in candidates():np.testing.assert_array_equal(signals(reordered,t,ctx,c),signals(d,t,ctx,c)[:,ix])
    def test_price_support_is_shared_and_current_quote_failure_not_consumed(self):
        d,t,ctx=self.fixture();ctx['ETF']['close'][0]=np.nan
        self.assertFalse(support(d,t,ctx,'none')[0])
        # The first otherwise true source decision cannot execute a missing
        # target quote. A later same-direction decision must still emit.
        ctx['ETF']['close'][0]=101.8;ctx['source']['close'][1]=101.8;ctx['ETF']['close'][1]=101.8
        ctx['source']['low'][1]=99.;ctx['ETF']['low'][1]=99.
        close=d.close.copy();close[0,0]=np.nan
        bad=replace(d,close=close)
        s=signals(bad,t,ctx,dict(feed='source',gate='none'))
        self.assertEqual(s[0,0],0.)
        self.assertEqual(s[1,0],1.)


if __name__=='__main__':unittest.main()
