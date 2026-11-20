import sys
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from autogrid.data import MarketData
from hourly_night_signals_20261119 import FAMILIES, candidates, signals

SYMBOLS = ("TQQQ", "SQQQ", "IBIT", "BITI")


def fixture():
    dates = pd.to_datetime(["2026-10-30", "2026-11-02"]).tz_localize("America/New_York")
    times = pd.DatetimeIndex([day + pd.Timedelta(minutes=570 + 60 * i)
                              for day in dates for i in range(7)]).tz_convert("UTC")
    n = len(times)
    price = np.full((n, 4), 100.)
    data = MarketData(np.asarray(times), SYMBOLS, price.copy(), price + 1,
                      price - 1, price.copy(), np.ones_like(price), bar_minutes=60)
    value = lambda x: np.full(n, x, dtype=float)
    ctx = dict(night_return=value(.03), night_scale=value(.02), btc_now=value(100),
               btc_trend24=value(.04), btc_trend48=value(.04), btc_vol480=value(.001),
               btc_pullback1=value(-.015), btc_pullback3=value(-.015),
               qqq_regime5=value(.02), qqq_regime10=value(.02), qqq_rth=value(.002),
               ibit_gap=value(.025), qqq_gap=value(.02), same_day_first_ibit=value(.005),
               first_btc_preopen_price=value(100), valid=np.ones(n, dtype=bool))
    return data, times, ctx


def subset(data, ix):
    return replace(data, timestamps=data.timestamps[ix], **{
        key: getattr(data, key)[ix] for key in ("open", "high", "low", "close", "volume")})


def pick(family, a=None, b=None):
    return next(c for c in candidates() if c["family"] == family
                and (a is None or c["a"] == a) and (b is None or c["b"] == b))


class HourlyNightSignalsTests(unittest.TestCase):
    def test_exact_sixteen_settings(self):
        self.assertEqual(len(candidates()), 16)
        self.assertEqual(len({c["name"] for c in candidates()}), 16)
        for family in FAMILIES:
            self.assertEqual(sum(c["family"] == family for c in candidates()), 4)
        expected = {"night_acceptance": {(a,b) for a in (.5,1.) for b in (.25,.5)},
                    "night_exhaustion": {(a,b) for a in (.5,.8) for b in (.25,.5)},
                    "trend_pullback": {(a,b) for a in (24,48) for b in (1,3)},
                    "night_nasdaq": {(a,b) for a in (5,10) for b in (.5,1.)}}
        for family, settings in expected.items():
            self.assertEqual({(c["a"],c["b"]) for c in candidates() if c["family"]==family}, settings)

    def test_actual_buy_orientation_and_symbol_reordering(self):
        data, times, ctx = fixture()
        for family in FAMILIES:
            active = {k:v.copy() for k,v in ctx.items()}
            if family == "night_exhaustion":
                active["btc_now"][:] = 100*np.exp(-.02)
            for direction in (1, -1):
                oriented = {k:v.copy() for k,v in active.items()}
                if direction == -1:
                    for key in ("night_return", "btc_trend24", "btc_trend48", "btc_pullback1",
                                "btc_pullback3", "qqq_regime5", "qqq_regime10", "qqq_rth",
                                "ibit_gap", "qqq_gap", "same_day_first_ibit"):
                        oriented[key] *= -1
                    if family == "night_exhaustion":
                        oriented["btc_now"][:] = 100*np.exp(.02)
                out = signals(data,times,oriented,pick(family))
                action = -direction if family == "night_exhaustion" else direction
                symbol = ("TQQQ" if action>0 else "SQQQ") if family=="night_nasdaq" else ("IBIT" if action>0 else "BITI")
                j = SYMBOLS.index(symbol)
                self.assertEqual(np.flatnonzero(out[:,j]).tolist(), [0,7])
                self.assertTrue(np.all(out[[0,7],j] == (1 if family=="night_nasdaq" else -1)))
                self.assertEqual(np.count_nonzero(out), 2)
                order = [3,1,0,2]
                shuffled = replace(data, symbols=tuple(SYMBOLS[j] for j in order), **{
                    key:getattr(data,key)[:,order] for key in ("open","high","low","close","volume")})
                np.testing.assert_array_equal(signals(shuffled,times,oriented,pick(family)),out[:,order])

    def test_episode_onsets_rearm_direction_switch_and_ny_dst_reset(self):
        data,times,ctx = fixture()
        ctx["valid"][2] = False  # missing availability must not manufacture onset
        ctx["same_day_first_ibit"][4] = 0  # valid false rearms
        out = signals(data,times,ctx,pick("night_acceptance"))
        self.assertEqual(np.flatnonzero(out[:,2]).tolist(), [0,5,7])
        self.assertEqual(times[0].hour,13)
        self.assertEqual(times[7].hour,14)
        # A sign change is its own episode, not a synthetic short of IBIT.
        for key in ("night_return","same_day_first_ibit"):
            ctx[key][5:7] *= -1
        out = signals(data,times,ctx,pick("night_acceptance"))
        self.assertEqual(np.flatnonzero(out[:,3]).tolist(), [5])

    def test_prefix_and_future_mutation_all_candidates_both_arms(self):
        data,times,ctx = fixture()
        for c in candidates():
            for control in (False,True):
                full = signals(data,times,ctx,c,control)
                for n in (1,4,8,12):
                    truncated = {k:v[:n] for k,v in ctx.items()}
                    np.testing.assert_array_equal(signals(subset(data,slice(n)),times[:n],truncated,c,control),full[:n])
                changed = {k:v.copy() for k,v in ctx.items()}
                for key in changed:
                    if key != "valid": changed[key][5:] *= -17
                changed["valid"][5:] = False
                mutated = replace(data, close=data.close.copy())
                mutated.close[5:] = np.nan
                np.testing.assert_array_equal(signals(mutated,times,changed,c,control)[:5],full[:5])

    def test_acceptance_thresholds_and_zero_first_return(self):
        data,times,ctx=fixture()
        c=pick("night_acceptance",.5,.25)
        ctx["night_return"][:] = .01
        ctx["night_scale"][:] = .02 # exactly minimum strength
        self.assertTrue(signals(data,times,ctx,c)[0,2])
        self.assertFalse(np.any(signals(data,times,ctx,pick("night_acceptance",1.,.25))))
        ctx["btc_now"][:] = 100*np.exp(-.003)
        self.assertFalse(np.any(signals(data,times,ctx,c))) # retrace .30 > .25
        self.assertTrue(signals(data,times,ctx,pick("night_acceptance",.5,.5))[0,2])
        ctx["same_day_first_ibit"][:] = 0
        self.assertFalse(np.any(signals(data,times,ctx,pick("night_acceptance",.5,.5))))

    def test_exhaustion_capture_and_reversal_are_separate(self):
        data,times,ctx=fixture()
        ctx["ibit_gap"][:] = .018 # .60 capture
        ctx["btc_now"][:] = 100*np.exp(-.01) # one-third reversal
        self.assertTrue(signals(data,times,ctx,pick("night_exhaustion",.5,.25))[0,3])
        self.assertFalse(np.any(signals(data,times,ctx,pick("night_exhaustion",.8,.25))))
        self.assertFalse(np.any(signals(data,times,ctx,pick("night_exhaustion",.5,.5))))
        ctx["ibit_gap"][:] *= -1
        self.assertFalse(np.any(signals(data,times,ctx,pick("night_exhaustion"))))

    def test_f1_f2_gap_controls_keep_source_scale_and_intraday_context(self):
        data,times,ctx=fixture()
        c=pick("night_acceptance",1.,.25)
        ctx["ibit_gap"][:] = .009 # gap/unchanged .02 scale fails1; source passes
        self.assertTrue(signals(data,times,ctx,c)[0,2])
        self.assertFalse(np.any(signals(data,times,ctx,c,True)))
        # F2 source capture=.60 fails .8; control capture is exactly1.
        ctx["ibit_gap"][:] = .018
        ctx["btc_now"][:] = 100*np.exp(-.01)
        c=pick("night_exhaustion",.8,.25)
        self.assertFalse(np.any(signals(data,times,ctx,c)))
        self.assertTrue(signals(data,times,ctx,c,True)[0,3])
        ctx["night_scale"][:] = 0
        self.assertFalse(np.any(signals(data,times,ctx,c,True)))

    def test_f3_pure_rth_readiness_and_only_night_confirmation_ablated(self):
        data,times,ctx=fixture()
        c=pick("trend_pullback",24,3)
        ctx["btc_pullback3"][:3]=np.nan # caller's actual 3h RTH history unavailable
        self.assertEqual(np.flatnonzero(signals(data,times,ctx,c)[:,2]).tolist(),[3,7])
        ctx["night_return"][:]=-.03
        self.assertFalse(np.any(signals(data,times,ctx,c)))
        self.assertTrue(signals(data,times,ctx,c,True)[3,2])
        ctx["btc_trend24"][:]=.001 # trend gate still enforced under control
        self.assertFalse(np.any(signals(data,times,ctx,c,True)))
        ctx["btc_trend24"][:]=.04
        for boundary in (-.01,-.03):
            ctx["btc_pullback3"][:]=boundary
            self.assertTrue(signals(data,times,ctx,c,True)[0,2])
        ctx["btc_pullback3"][:]=-.031
        self.assertFalse(np.any(signals(data,times,ctx,c,True)))

    def test_f4_nasdaq_regime_hour_and_gap_proxy(self):
        data,times,ctx=fixture()
        c=pick("night_nasdaq",5,1.)
        self.assertTrue(signals(data,times,ctx,c)[0,0])
        ctx["qqq_gap"][:]=.009
        self.assertFalse(np.any(signals(data,times,ctx,c,True)))
        ctx["qqq_regime5"][:]=-.01
        self.assertFalse(np.any(signals(data,times,ctx,c)))
        ctx["qqq_regime5"][:]=.01
        ctx["qqq_rth"][:]=0
        self.assertFalse(np.any(signals(data,times,ctx,c)))

    def test_missing_common_fields_do_not_create_control_only_support(self):
        data,times,ctx=fixture()
        for c in candidates():
            broken={k:v.copy() for k,v in ctx.items()}
            broken["night_return"][:]=np.nan
            for control in (False,True):
                self.assertFalse(np.any(signals(data,times,broken,c,control)))
        for bad in (0.,-1.,np.nan,np.inf):
            broken={k:v.copy() for k,v in ctx.items()}
            broken["first_btc_preopen_price"][:]=bad
            self.assertFalse(np.any(signals(data,times,broken,pick("night_acceptance"))))
        ctx["valid"][:]=False
        self.assertFalse(np.any(signals(data,times,ctx,pick("trend_pullback"),True)))

    def test_invalid_quote_does_not_consume_onset_and_next_entry_mask_is_common(self):
        data,times,ctx=fixture()
        broken=replace(data,close=data.close.copy())
        broken.close[0,2]=np.nan
        self.assertEqual(np.flatnonzero(signals(broken,times,ctx,pick("night_acceptance"))[:,2]).tolist(),[1,7])
        ctx["valid"][:]=False
        ctx["valid"][[2,9]]=True # externally audited entry eligibility
        self.assertEqual(np.flatnonzero(signals(data,times,ctx,pick("night_acceptance"))[:,2]).tolist(),[2,9])

    def test_strict_contract_errors_and_numeric_alias(self):
        data,times,ctx=fixture()
        for c in ({"family":"bad","a":1,"b":1},dict(pick("night_acceptance"),a=True)):
            with self.assertRaises(ValueError): signals(data,times,ctx,c)
        with self.assertRaises(ValueError): signals(data,times,ctx,pick("night_acceptance"),"source")
        for bad in (np.ones(len(times)),np.ones(len(times)-1,dtype=bool)):
            with self.assertRaises(ValueError): signals(data,times,dict(ctx,valid=bad),pick("night_acceptance"))
        with self.assertRaises(ValueError): signals(data,times[::-1],ctx,pick("night_acceptance"))
        with self.assertRaises(ValueError): signals(data,times+pd.Timedelta(minutes=1),ctx,pick("night_acceptance"))
        c=dict(pick("trend_pullback"),a=24.,b=1.)
        np.testing.assert_array_equal(signals(data,times,ctx,c),signals(data,times,ctx,pick("trend_pullback",24,1)))


if __name__ == "__main__":
    unittest.main()
