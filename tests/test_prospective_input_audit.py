"""SYNTHETIC_UNIT_ONLY: no actual prices, acquisition, performance or execution."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest

from scripts.prospective_input_audit_20261119 import audit_snapshot, timestamp, SYMBOLS


class ProspectiveInputAuditTests(unittest.TestCase):
    def setUp(self):
        self.freeze = '2026-11-19T05:20:49Z'
        self.now = '2026-11-19T21:05:00Z'
        self.calendar = [{'day': '2026-11-19', 'open': '2026-11-19T14:30:00Z',
                          'close': '2026-11-19T21:00:00Z'}]
        opened = timestamp(self.calendar[0]['open'])
        self.etfs = [dict(symbol=s, timestamp=(opened+timedelta(hours=k)).isoformat(),
                          open='100', high='102', low='99', close='101', volume='500')
                     for s in SYMBOLS for k in range(7)]
        self.source = []
        epoch = timestamp('1970-01-01T00:00:00Z')
        for k in range(29):
            start = opened-timedelta(hours=8)+timedelta(minutes=30*k)
            ms = (start-epoch)//timedelta(milliseconds=1)
            self.source.append([ms, '100', '102', '99', '101', '500', ms+1799999,
                                '50000', 20, '250', '25000', '0'])

    def audit(self, **kw):
        args = dict(etf_rows=self.etfs, source_rows=self.source,
                    calendar_rows=self.calendar, freeze=self.freeze, asof=self.now)
        args.update(kw)
        return audit_snapshot(**args)

    def test_full_completed_session_synthetic_unit_only(self):
        result = self.audit(etf_rows=list(reversed(self.etfs)), source_rows=list(reversed(self.source)))
        self.assertTrue(result['input_audited'])
        self.assertEqual(result['rows'], {'etf': 28, 'source': 29})
        self.assertEqual(result['warmup']['required_source_warmup_rows'], 16)
        self.assertFalse(result['terminal_backtest_allowed'])
        self.assertEqual(result['engine_calls'], 0)
        self.assertIsNone(result['metrics'])
        self.assertEqual(len(result['output_audit_sha256']), 64)

    def test_preclose_and_source_assumed_release(self):
        for now in ('2026-11-19T20:59:59Z', '2026-11-19T21:00:00Z', '2026-11-19T21:04:59Z'):
            with self.subTest(now=now), self.assertRaises(ValueError):
                self.audit(asof=now)

    def test_missing_ticker_bar_and_source_gap(self):
        with self.assertRaises(ValueError):
            self.audit(etf_rows=self.etfs[:-1])
        with self.assertRaises(ValueError):
            self.audit(source_rows=self.source[:5]+self.source[6:])
        with self.assertRaises(ValueError):
            self.audit(source_rows=self.source[1:])

    def test_etf_bad_values(self):
        for field, value in (('open', '0'), ('high', '100'), ('low', '102'),
                             ('volume', '-1'), ('close', 'NaN'), ('symbol', 'BTCUSDT')):
            rows = deepcopy(self.etfs)
            rows[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.audit(etf_rows=rows)

    def test_source_bad_values(self):
        for col, value in ((2, '100'), (5, '0'), (7, '0'), (8, 1.5), (8, 0),
                           (9, '501'), (9, '-1'), (10, '50001'), (1, 'Infinity'),
                           (6, self.source[0][6]+1), (0, self.source[0][0]+1)):
            rows = deepcopy(self.source)
            rows[0][col] = value
            with self.subTest(col=col, value=value), self.assertRaises(ValueError):
                self.audit(source_rows=rows)
        with self.assertRaises(ValueError):
            self.audit(source_rows=[self.source[0][:-1]]+self.source[1:])

    def test_duplicates_future_extra_and_crossfreeze(self):
        cases = [dict(etf_rows=self.etfs+[self.etfs[0]]),
                 dict(source_rows=self.source+[self.source[0]]),
                 dict(freeze='2026-11-19T14:30:01Z')]
        rows = deepcopy(self.etfs)
        rows[0]['timestamp'] = '2026-11-20T14:30:00Z'
        cases.append(dict(etf_rows=rows))
        source = deepcopy(self.source)
        row = deepcopy(source[-1])
        row[0] += 1800000
        row[6] += 1800000
        cases.append(dict(source_rows=source+[row]))
        for kw in cases:
            with self.subTest(kw=list(kw)), self.assertRaises(ValueError):
                self.audit(**kw)

    def test_calendar_validation(self):
        for changed in ({'close': '2026-11-19T18:00:00Z'},
                        {'open': '2026-11-19T14:30:00'}, {'day': '2026-11-20'}):
            calendar = deepcopy(self.calendar)
            calendar[0].update(changed)
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.audit(calendar_rows=calendar)
        with self.assertRaises(ValueError):
            self.audit(calendar_rows=self.calendar+self.calendar)

    def test_append_only_prefix(self):
        result = self.audit(previous_etf_rows=self.etfs[:8], previous_source_rows=self.source[:10])
        self.assertEqual(result['snapshot_prefix_checked'], {'etf': True, 'source': True})
        old_etf = deepcopy(self.etfs[:1])
        old_etf[0]['close'] = '100.5'
        with self.assertRaises(ValueError):
            self.audit(previous_etf_rows=old_etf)
        old_source = deepcopy(self.source[:1])
        old_source[0][9] = '249'
        with self.assertRaises(ValueError):
            self.audit(previous_source_rows=old_source)
        old_etf = deepcopy(self.etfs[:1])
        old_etf[0]['timestamp'] = '2026-11-18T14:30:00Z'
        with self.assertRaises(ValueError):
            self.audit(previous_etf_rows=old_etf)
        old_source = deepcopy(self.source[:1])
        old_source[0][0] -= 1800000
        old_source[0][6] -= 1800000
        with self.assertRaises(ValueError):
            self.audit(previous_source_rows=old_source)

    def test_additional_contiguous_source_warmup(self):
        row = deepcopy(self.source[0])
        row[0] -= 1800000
        row[6] -= 1800000
        result = self.audit(source_rows=[row]+self.source)
        self.assertEqual(result['warmup']['additional_source_rows'], 1)
        row[0] -= 1800000
        row[6] -= 1800000
        with self.assertRaises(ValueError):
            self.audit(source_rows=[row]+self.source)

    def test_cli_synthetic_unit_only_and_protected_output(self):
        script = Path(__file__).resolve().parents[1]/'scripts/prospective_input_audit_20261119.py'
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_UNIT_ONLY_') as directory:
            root = Path(directory)
            for name, rows in (('etf.csv', self.etfs), ('calendar.csv', self.calendar)):
                with (root/name).open('w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
            (root/'source.json').write_text(json.dumps(self.source))
            dependencies = {}
            for k in range(17):
                name = 'SYNTHETIC_UNIT_ONLY_dependency_'+str(k)
                payload = ('SYNTHETIC_UNIT_ONLY '+str(k)).encode()
                (root/name).write_bytes(payload)
                dependencies[name] = hashlib.sha256(payload).hexdigest()
            plan = dict(real_orders=0, news_macro=False, frozen_at_utc=self.freeze,
                        code_dependency_hashes=dependencies, models=[
                            dict(name=name, body_efficiency=.55, directional_taker_pressure=.1,
                                 prior_flow_mean_hours=4, calendar_common_duration_minutes=duration,
                                 hold_eligible_bars=hold)
                            for name, duration, hold in (('h120__source', 120, 2), ('c180__source', 180, 4))])
            payload = json.dumps(plan).encode()
            (root/'plan.json').write_bytes(payload)
            blob = hashlib.sha1(b'blob '+str(len(payload)).encode()+b'\0'+payload).hexdigest()
            args = [sys.executable, str(script), '--etf-csv', 'etf.csv', '--source-json',
                    'source.json', '--calendar', 'calendar.csv', '--plan', 'plan.json',
                    '--plan-blob-sha1', blob, '--now', self.now, '--out', 'audit.json']
            good = subprocess.run(args, cwd=root, capture_output=True, text=True)
            self.assertEqual(good.returncode, 0, good.stderr)
            result = json.loads((root/'audit.json').read_text())
            self.assertEqual(len(result['frozen_dependency_hashes']), 17)
            self.assertFalse(result['terminal_backtest_allowed'])
            self.assertTrue(result['calendar_provenance_independently_required'])
            self.assertEqual(result['engine_calls'], 0)
            self.assertIsNone(result['metrics'])
            original = (root/'audit.json').read_bytes()
            again = subprocess.run(args, cwd=root, capture_output=True, text=True)
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual((root/'audit.json').read_bytes(), original)
            args[-1] = 'bad_audit.json'
            (root/'SYNTHETIC_UNIT_ONLY_dependency_0').write_text('changed')
            bad = subprocess.run(args, cwd=root, capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0)
            self.assertFalse((root/'bad_audit.json').exists())


if __name__ == '__main__':
    unittest.main()
