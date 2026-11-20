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

    def write_csv(self, root, name, rows, fieldnames=None):
        with (root/name).open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames or list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def cli_args(self, root):
        """Write synthetic CLI inputs, including a synthetic frozen plan."""
        script = Path(__file__).resolve().parents[1]/'scripts/prospective_input_audit_20261119.py'
        self.write_csv(root, 'etf.csv', self.etfs)
        self.write_csv(root, 'calendar.csv', self.calendar)
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
        return [sys.executable, str(script), '--etf-csv', 'etf.csv', '--source-json',
                'source.json', '--calendar', 'calendar.csv', '--plan', 'plan.json',
                '--plan-blob-sha1', blob, '--now', self.now, '--out', 'audit.json']

    def input_bytes(self, root):
        return {path.name: path.read_bytes() for path in root.iterdir() if path.is_file()}

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
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_UNIT_ONLY_') as directory:
            root = Path(directory)
            args = self.cli_args(root)
            inputs = self.input_bytes(root)
            good = subprocess.run(args, cwd=root, capture_output=True, text=True)
            self.assertEqual(good.returncode, 0, good.stderr)
            result = json.loads((root/'audit.json').read_text())
            self.assertEqual(len(result['frozen_dependency_hashes']), 17)
            self.assertFalse(result['terminal_backtest_allowed'])
            self.assertTrue(result['calendar_provenance_independently_required'])
            self.assertEqual(result['engine_calls'], 0)
            self.assertIsNone(result['metrics'])
            self.assertIsNone(result['profit_metrics'])
            self.assertEqual(result['snapshot_prefix_checked'], {'etf': False, 'source': False})
            for key in ('previous_etf', 'previous_source'):
                self.assertNotIn(key, result['input_file_sha256'])
                self.assertIsNone(result['input_raw_hashes'][key+'_rows_sha256'])
            self.assertEqual(inputs, {name: (root/name).read_bytes() for name in inputs})
            original = (root/'audit.json').read_bytes()
            again = subprocess.run(args, cwd=root, capture_output=True, text=True)
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual((root/'audit.json').read_bytes(), original)
            args[-1] = 'bad_audit.json'
            (root/'SYNTHETIC_UNIT_ONLY_dependency_0').write_text('changed')
            bad = subprocess.run(args, cwd=root, capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0)
            self.assertFalse((root/'bad_audit.json').exists())

    def test_cli_previous_snapshots_unchanged_prefix_and_raw_hashes(self):
        for include_etf, include_source in ((True, True), (True, False), (False, True)):
            with self.subTest(etf=include_etf, source=include_source), \
                    tempfile.TemporaryDirectory(prefix='SYNTHETIC_UNIT_ONLY_') as directory:
                root = Path(directory)
                args = self.cli_args(root)
                if include_etf:
                    # Ordering/number formatting may differ; prefix comparison uses normalized values.
                    previous = deepcopy(list(reversed(self.etfs[:8])))
                    previous[0]['close'] = '101.000'
                    self.write_csv(root, 'previous_etf.csv', previous)
                    args += ['--previous-etf-csv', 'previous_etf.csv']
                if include_source:
                    previous = deepcopy(list(reversed(self.source[:10])))
                    previous[0][1] = '100.000'
                    (root/'previous_source.json').write_text(json.dumps(previous, indent=2)+'\n')
                    args += ['--previous-source-json', 'previous_source.json']
                inputs = self.input_bytes(root)
                run = subprocess.run(args, cwd=root, capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)
                result = json.loads((root/'audit.json').read_text())
                self.assertEqual(result['snapshot_prefix_checked'],
                                 {'etf': include_etf, 'source': include_source})
                self.assertEqual(result, json.loads(run.stdout))
                for key, included, filename in (
                        ('previous_etf', include_etf, 'previous_etf.csv'),
                        ('previous_source', include_source, 'previous_source.json')):
                    if included:
                        self.assertEqual(result['input_file_sha256'][key],
                                         hashlib.sha256(inputs[filename]).hexdigest())
                        self.assertEqual(len(result['input_raw_hashes'][key+'_rows_sha256']), 64)
                    else:
                        self.assertNotIn(key, result['input_file_sha256'])
                        self.assertIsNone(result['input_raw_hashes'][key+'_rows_sha256'])
                self.assertFalse(result['terminal_backtest_allowed'])
                self.assertEqual(result['engine_calls'], 0)
                self.assertEqual(result['real_orders'], 0)
                self.assertIsNone(result['metrics'])
                self.assertIsNone(result['profit_metrics'])
                self.assertFalse(result['new_independent_validation'])
                self.assertEqual(inputs, {name: (root/name).read_bytes() for name in inputs})

    def test_cli_previous_revisions_and_removals_refused_before_output(self):
        for kind, change in (('etf', 'revision'), ('source', 'revision'),
                             ('etf', 'removal'), ('source', 'removal')):
            with self.subTest(kind=kind, change=change), \
                    tempfile.TemporaryDirectory(prefix='SYNTHETIC_UNIT_ONLY_') as directory:
                root = Path(directory)
                args = self.cli_args(root)
                if kind == 'etf':
                    self.write_csv(root, 'previous_etf.csv', self.etfs)
                    args += ['--previous-etf-csv', 'previous_etf.csv']
                    current = deepcopy(self.etfs)
                    if change == 'revision':
                        current[0]['close'] = '100.5'
                    else:
                        # A structurally complete later session has dropped the actual old ETF rows.
                        for row in current:
                            row['timestamp'] = (timestamp(row['timestamp'])+timedelta(days=1)).isoformat()
                        calendar = [{'day': '2026-11-20', 'open': '2026-11-20T14:30:00Z',
                                     'close': '2026-11-20T21:00:00Z'}]
                        self.write_csv(root, 'calendar.csv', calendar)
                        source = deepcopy(self.source)
                        for row in source:
                            row[0] += 86400000
                            row[6] += 86400000
                        (root/'source.json').write_text(json.dumps(source))
                        args[args.index('--now')+1] = '2026-11-20T21:05:00Z'
                    self.write_csv(root, 'etf.csv', current)
                else:
                    previous = deepcopy(self.source)
                    if change == 'revision':
                        current = deepcopy(self.source)
                        current[0][9] = '249'
                        (root/'source.json').write_text(json.dumps(current))
                    else:
                        # Old warmup was actually supplied, but is absent from otherwise valid new coverage.
                        old = deepcopy(previous[0])
                        old[0] -= 1800000
                        old[6] -= 1800000
                        previous.insert(0, old)
                    (root/'previous_source.json').write_text(json.dumps(previous))
                    args += ['--previous-source-json', 'previous_source.json']
                inputs = self.input_bytes(root)
                run = subprocess.run(args, cwd=root, capture_output=True, text=True)
                self.assertNotEqual(run.returncode, 0)
                self.assertIn(('ETF' if kind == 'etf' else 'Source')+
                              ' snapshot revision/removal refused', run.stderr)
                self.assertEqual(run.stdout, '')
                self.assertFalse((root/'audit.json').exists())
                self.assertEqual(inputs, self.input_bytes(root))

    def test_cli_supplied_empty_previous_snapshot_refused(self):
        for kind in ('etf', 'source'):
            with self.subTest(kind=kind), \
                    tempfile.TemporaryDirectory(prefix='SYNTHETIC_UNIT_ONLY_') as directory:
                root = Path(directory)
                args = self.cli_args(root)
                if kind == 'etf':
                    self.write_csv(root, 'previous_etf.csv', [], fieldnames=list(self.etfs[0]))
                    args += ['--previous-etf-csv', 'previous_etf.csv']
                else:
                    (root/'previous_source.json').write_text('[]\n')
                    args += ['--previous-source-json', 'previous_source.json']
                inputs = self.input_bytes(root)
                run = subprocess.run(args, cwd=root, capture_output=True, text=True)
                self.assertNotEqual(run.returncode, 0)
                self.assertIn('snapshot must contain rows', run.stderr)
                self.assertEqual(run.stdout, '')
                self.assertFalse((root/'audit.json').exists())
                self.assertEqual(inputs, self.input_bytes(root))


if __name__ == '__main__':
    unittest.main()
