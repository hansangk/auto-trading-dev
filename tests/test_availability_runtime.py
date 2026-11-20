import sys,unittest,tempfile,json
from pathlib import Path
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from availability_runtime_20261119 import atomic_json,resume_state

class AvailabilityRuntimeTests(unittest.TestCase):
    def saved(self):
        return dict(schedule=['coin_only']*11,scenario='base',plan_hash='fixed',segments=[dict(selected='coin_only',state=dict(equity=123456789.12345679,peak=130000000.,daily_start=124000000.,current_date='2026-01-30',cooldown_until=1999,loss_streak=2,killed=False))])
    def test_complete_carried_risk_state_roundtrip_without_prefix_replay(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state.json';s=self.saved();atomic_json(p,s);restored,n=resume_state(json.loads(p.read_text()),['coin_only']*11,'base','fixed')
            self.assertEqual(n,1);self.assertEqual(restored.equity,123456789.12345679);self.assertEqual(restored.peak,130000000.)
            self.assertEqual(restored.current_date,date(2026,1,30));self.assertEqual(restored.cooldown_until,1999);self.assertEqual(restored.loss_streak,2);self.assertFalse(restored.killed)
    def test_changed_schedule_scenario_or_plan_cannot_resume(self):
        for schedule,scenario,plan in [(['other']*11,'base','fixed'),(['coin_only']*11,'cost2','fixed'),(['coin_only']*11,'base','changed')]:
            with self.assertRaises(RuntimeError):resume_state(self.saved(),schedule,scenario,plan)
    def test_strict_shared_json_keeps_full_precision_and_explicit_infinity(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state.json';atomic_json(p,dict(value=.12345678912345678,profit_factor=float('inf'),day=date(2026,1,30)))
            x=json.loads(p.read_text(),parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
            self.assertEqual(x['value'],.12345678912345678);self.assertEqual(x['profit_factor'],'Infinity');self.assertEqual(x['day'],'2026-01-30');self.assertFalse(p.with_name('state.json.tmp').exists())

if __name__=='__main__':unittest.main()
