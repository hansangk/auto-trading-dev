import sys,json,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from source_activity_resume_guard_20261119 import validate_resume

class ResumeGuardTests(unittest.TestCase):
    def setup_files(self,out):
        (out/'preregistered_plan.json').write_text('{}');(out/'selection.json').write_text('{}')
    def test_partial_month_cannot_repeat_completed_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);self.setup_files(out);(out/'execution_checkpoint_LOCAL.json').write_text(json.dumps({'calls':[{'kind':'continuous_month','call_id':9}]}))
            with self.assertRaisesRegex(RuntimeError,'PARTIAL_CONTINUOUS'):validate_resume(out,'research')
    def test_reset_only_checkpoint_can_use_existing_exact_cache(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);self.setup_files(out);(out/'execution_checkpoint_LOCAL.json').write_text(json.dumps({'calls':[{'kind':'reset_window'}]}))
            self.assertTrue(validate_resume(out,'research'))
    def test_completed_manifest_never_replayed(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);self.setup_files(out);(out/'manifest.json').write_text('{}')
            with self.assertRaisesRegex(RuntimeError,'COMPLETE'):validate_resume(out,'research')
    def test_live_lock_is_not_cleared(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);self.setup_files(out);lock=out/'RUNNING.lock';lock.touch()
            with self.assertRaisesRegex(RuntimeError,'RUNNING'):validate_resume(out,'research')
            self.assertTrue(lock.exists())

if __name__=='__main__':unittest.main()
