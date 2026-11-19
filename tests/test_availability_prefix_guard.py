import sys,tempfile,json,unittest
from pathlib import Path
from dataclasses import asdict
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from availability_guarded_research_20261119 import verify_prefix
from availability_runtime_20261119 import sha
from autogrid.engine import AccountState

class PrefixGuardTests(unittest.TestCase):
    def fixture(self,path):
        ledger=path/'call_1_ledger_LOCAL.jsonl';ledger.write_text(json.dumps({'net_return':.01,'equity':101.})+'\n')
        call=dict(call_id=1,kind='continuous_month',first_policy='coin_only',scenario='base',start='2026-01-01',end_exclusive='2026-02-01',ledger_sha256=sha(ledger),rounds=1,total_return=.01,max_drawdown=0)
        state=asdict(AccountState(equity=101.,peak=101.,daily_start=100.,current_date=date(2026,1,30),cooldown_until=-1,loss_streak=0,killed=False));state['current_date']=state['current_date'].isoformat()
        saved=dict(scenario='base',segments=[dict(month='2026-01-01',selected='coin_only',call_ref='new:1',state=state)])
        return ledger,call,saved
    def test_valid_prefix_reconciles_before_resume(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);_,call,s=self.fixture(out);self.assertEqual(verify_prefix(s,out,[call],100.),['new:1'])
    def test_lost_or_tampered_ledger_blocks_before_new_call(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);ledger,call,s=self.fixture(out);ledger.write_text('')
            with self.assertRaisesRegex(RuntimeError,'ledger'):verify_prefix(s,out,[call],100.)
            ledger.unlink()
            with self.assertRaisesRegex(RuntimeError,'ledger'):verify_prefix(s,out,[call],100.)
    def test_incomplete_risk_state_and_wrong_month_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);_,call,s=self.fixture(out);del s['segments'][0]['state']['cooldown_until']
            with self.assertRaisesRegex(RuntimeError,'Incomplete'):verify_prefix(s,out,[call],100.)
            _,call,s=self.fixture(out);call['start']='2026-02-01'
            with self.assertRaisesRegex(RuntimeError,'boundary'):verify_prefix(s,out,[call],100.)

if __name__=='__main__':unittest.main()
