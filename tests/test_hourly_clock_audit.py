import sys,json,hashlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import hourly_clock_audit_20261119 as audit

class HourlyClockAuditTests(unittest.TestCase):
    def test_end_buffer_phase_staleness_and_future_prefix(self):
        ends=pd.date_range('2026-03-09 13:00',periods=4,freq='h',tz='UTC')
        self.assertEqual(audit.completed_index(ends,pd.Timestamp('2026-03-09 14:00',tz='UTC')),0)
        self.assertEqual(audit.completed_index(ends,pd.Timestamp('2026-03-09 14:05',tz='UTC')),1)
        self.assertEqual(audit.completed_index(ends,pd.Timestamp('2026-03-09 14:30',tz='UTC')),1)
        self.assertEqual(audit.completed_index(ends[:2],pd.Timestamp('2026-03-09 14:30',tz='UTC')),1)
        self.assertEqual(audit.completed_index(ends[:2],pd.Timestamp('2026-03-09 15:06',tz='UTC')),-1)
        self.assertEqual(audit.completed_index(ends,pd.Timestamp('2026-03-09 12:59',tz='UTC')),-1)

    def test_wall_clock_returns_reject_missing_hours(self):
        f=pd.DataFrame(dict(end=pd.date_range('2026-01-01',periods=6,freq='h',tz='UTC'),close=np.exp(np.arange(6)*.01)))
        self.assertAlmostEqual(audit.trailing_return(f,5,3),.03)
        self.assertAlmostEqual(audit.trailing_rms(f,5,3),.01)
        f.loc[3,'end']+=pd.Timedelta(minutes=1)
        self.assertTrue(np.isnan(audit.trailing_return(f,5,3)))
        self.assertTrue(np.isnan(audit.trailing_rms(f,5,3)))

    def test_early_close_partial_bar_and_null_placeholder(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);starts=pd.date_range('2024-11-29 14:30',periods=4,freq='h',tz='UTC').append(pd.DatetimeIndex([pd.Timestamp('2024-11-29 18:00',tz='UTC')]))
            body={'chart':{'result':[{'timestamp':[int(t.timestamp()) for t in starts],'indicators':{'quote':[dict(open=[100]*4+[None],high=[101]*4+[None],low=[99]*4+[None],close=[100.5]*4+[None],volume=[1]*4+[None])]} }]}}
            raw=json.dumps(body).encode();(root/'QQQ_raw_LOCAL.json').write_bytes(raw);(root/'access_manifest.json').write_text(json.dumps({'sources':[{'fetched_utc':'2024-11-29 19:00:00+00:00'}]}))
            schedule=pd.DataFrame({'open':[starts[0]],'close':[pd.Timestamp('2024-11-29 18:00',tz='UTC')]},index=['2024-11-29'])
            with patch.object(audit,'RAW',root),patch.dict(audit.HASH,{'QQQ':hashlib.sha256(raw).hexdigest()}):f,m=audit.parse_source('QQQ',schedule)
            self.assertEqual(len(f),4);self.assertEqual(m['null_rows'],1)
            self.assertEqual(f.iloc[-1]['end']-f.iloc[-1]['start'],pd.Timedelta(minutes=30))
            self.assertTrue((f.end<=schedule.iloc[0]['close']).all())

if __name__=='__main__':unittest.main()
