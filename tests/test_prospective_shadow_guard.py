import sys,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prospective_shadow_guard_20261119 import readiness,observation_class

class ShadowReadinessTests(unittest.TestCase):
    def setUp(self):
        self.plan=dict(real_orders=0,news_macro=False,frozen_at_utc='2026-11-19T05:20:49Z',models=[dict(name=n,body_efficiency=.55,directional_taker_pressure=.1,prior_flow_mean_hours=4,calendar_common_duration_minutes=d,hold_eligible_bars=h) for n,d,h in [('h120__source',120,2),('c180__source',180,4)]])
        self.calendar=[dict(day='2026-11-19',open='2026-11-19T14:30:00Z',close='2026-11-19T21:00:00Z')]
    def test_preopen_is_waiting_not_backtest(self):
        r=readiness(self.plan,self.calendar,'2026-11-19T08:00:00Z');self.assertEqual(r['status'],'WAITING_FOR_COMPLETED_SHADOW_BARS');self.assertEqual(r['expected_completed_postfreeze_ETF_bars'],0);self.assertFalse(r['terminal_backtest_allowed']);self.assertIsNone(r['profit_metrics'])
    def test_hour_completion_boundary(self):
        for time,count in [('15:29:59',0),('15:30:00',1)]:
            r=readiness(self.plan,self.calendar,f'2026-11-19T{time}Z');self.assertEqual(r['expected_completed_postfreeze_ETF_bars'],count);self.assertFalse(r['terminal_backtest_allowed'])
    def test_completed_calendar_does_not_prove_price_access(self):
        r=readiness(self.plan,self.calendar,'2026-11-19T21:01:00Z');self.assertEqual(r['status'],'CALENDAR_WINDOW_COMPLETE_INPUTS_NOT_AUDITED');self.assertEqual(r['expected_completed_postfreeze_ETF_bars'],7);self.assertFalse(r['price_coverage_audit_complete']);self.assertFalse(r['terminal_backtest_allowed'])
    def test_crossing_freeze_and_incomplete(self):
        f='2026-11-19T05:20:49Z'
        self.assertEqual(observation_class('2026-11-19T05:00Z','2026-11-19T05:30Z','2026-11-19T05:30Z',f,'2026-11-19T08:00Z'),'CROSSING_FREEZE_WARMUP_ONLY')
        self.assertEqual(observation_class('2026-11-19T08:00Z','2026-11-19T08:30Z','2026-11-19T08:30Z',f,'2026-11-19T08:01Z'),'INCOMPLETE_NO_LOOKAHEAD')
    def test_release_boundary(self):
        args=('2026-11-19T14:30Z','2026-11-19T15:30Z','2026-11-19T15:35Z','2026-11-19T05:20:49Z')
        self.assertEqual(observation_class(*args,'2026-11-19T15:34:59Z'),'NOT_RELEASED')
        self.assertTrue(observation_class(*args,'2026-11-19T15:35:00Z').startswith('POTENTIAL_NEW'))
    def test_scope_and_calendar_fail_closed(self):
        bad=copy.deepcopy(self.plan);bad['models'][0]['hold_eligible_bars']=1
        with self.assertRaises(ValueError):readiness(bad,self.calendar,'2026-11-19T08:00Z')
        short=copy.deepcopy(self.calendar);short[0]['close']='2026-11-19T18:00Z'
        with self.assertRaises(ValueError):readiness(self.plan,short,'2026-11-19T08:00Z')
        with self.assertRaises(ValueError):readiness(self.plan,self.calendar,'2026-11-19T08:00')
    def test_expired_snapshot_does_not_guess_next_day(self):
        self.assertEqual(readiness(self.plan,self.calendar,'2026-11-20T14:30Z')['status'],'NEEDS_CALENDAR_EXTENSION')
