import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import common
import run
import analyze
import test_v04_protocol09 as inherited_tests


class Protocol17(unittest.TestCase):
    def test_only_declared_common_scenario_changes(self):
        old = common.old_protocol(); new = common.load_protocol()
        changed = {'stage', 'seeds', 'maximum_attempts', 'jobs', 'startup_overrides', 'artifacts'}
        self.assertEqual({k:v for k,v in old.items() if k not in changed},
                         {k:v for k,v in new.items() if k not in changed})
        self.assertEqual(new['startup_overrides'], {**old['startup_overrides'], 'MPC_Z_VEL_MAX_DN': .55, 'MPC_LAND_SPEED': .6})
        self.assertEqual(len(new['jobs']), 6)
        for job in new['jobs']:
            self.assertEqual(job['parameters'], {**old['candidate'], 'MPC_VC_MODE':job['mode'], 'MPC_VC_AXES':job['mode']})

    def test_flight_guards_identical(self):
        old = (common.REPO / 'research/sta-velocity-control/scripts/run_v04_flight12.py').read_text()
        expected = old.replace('#!/usr/bin/env python3\n', '#!/usr/bin/env python3\nfrom common import REPO\n', 1).replace(
            'parents[3]', 'parents[4]').replace(
            'from v04_protocol10 import CONFIG, load_protocol, require_authorization',
            'from common import CONFIG, load_protocol, require_authorization')
        expected = expected.replace('from v04_task04 import scalars, entry_ok, EntryGate',
            'from v04_task04 import scalars, entry_ok, EntryGate\nfrom v04_entry14 import advance_entry')
        expected = expected.replace("            if gate.update(p[\"timestamp_sample\"], valid, diagnostic):", "            readiness = advance_entry(gate, p[\"timestamp_sample\"], valid, diagnostic,\n                                      checks.live.read, ref, p[\"timestamp\"])\n            with (output / \"entry_raw_gate.jsonl\").open(\"a\") as stream:\n                stream.write(json.dumps(readiness) + \"\\n\")\n            if readiness[\"ready\"]:")
        self.assertEqual((common.CONFIG / 'flight.py').read_text(), expected)

    def test_analyzer_guards_identical(self):
        old = (common.REPO / 'research/sta-velocity-control/scripts/analyze_v04_protocol10.py').read_text()
        expected = old.replace('#!/usr/bin/env python3\n', '#!/usr/bin/env python3\nfrom common import REPO\n', 1).replace(
            'from v04_protocol10 import load_protocol, CONFIG, fingerprint',
            'from common import load_protocol, CONFIG, fingerprint').replace('v04_protocol10_metrics.json', 'v04_protocol17_metrics.json')
        expected = expected.replace('from analyze_v04_height_protocol09 import height_evidence',
            'from analyze_v04_height16 import height_evidence')
        self.assertEqual((common.CONFIG / 'analyze.py').read_text(), expected)

    def test_only_prearm_monitor_binding_changes(self):
        old=(common.CONFIG.parent/'protocol16/run.py').read_text()
        self.assertEqual((common.CONFIG/'run.py').read_text(), old.replace(
            'from v04_monitor10 import Checks as LandingChecks', 'from v04_monitor17 import Checks as LandingChecks'))

    def test_baseline_and_runtime_parameter_snapshots(self):
        root = json.loads((common.CONFIG / 'frozen.json').read_text())
        self.assertEqual(root['control_parameters']['MPC_Z_VEL_MAX_DN'], 1)
        for mode in ('pid', 'esta'):
            old = json.loads((common.CONFIG.parent / 'protocol10' / mode / 'frozen.json').read_text())
            new = json.loads((common.CONFIG / mode / 'frozen.json').read_text())
            old['control_parameters']['MPC_Z_VEL_MAX_DN'] = .55
            old['control_parameters']['MPC_LAND_SPEED'] = .6
            self.assertEqual(new, old)
            self.assertEqual(new['control_parameters']['MPC_LAND_SPEED'], .6)

    def test_authorization_binding(self):
        p = common.load_protocol()
        good = dict(approved=True, stage=p['stage'], source_head='test-head', maximum_attempts=6,
            execution_sha256=common.fingerprint(common.CONFIG / 'execution.json'),
            basis='standing user authorization for ordinary repairs and new SITL batches')
        with tempfile.TemporaryDirectory() as tmp, patch.object(common.subprocess, 'check_output', return_value='test-head\n'):
            path = Path(tmp) / 'receipt.json'; path.write_text(json.dumps(good))
            self.assertEqual(common.require_authorization(str(path), p), good)
            for k, v in [('approved', False), ('source_head', 'wrong'), ('stage', 'wrong'),
                         ('maximum_attempts', 7), ('execution_sha256', 'wrong'), ('basis', 'wrong')]:
                path.write_text(json.dumps({**good, k:v}))
                with self.assertRaises(RuntimeError): common.require_authorization(str(path), p)
        with self.assertRaises(RuntimeError): common.require_authorization('', p)

    def batch(self, **kwargs):
        with patch.object(inherited_tests, 'runner', run), patch.object(inherited_tests, 'load_protocol', common.load_protocol):
            return inherited_tests.Protocol09Test.batch(self, **kwargs)

    def test_six_mock_flights_three_pairs_and_restore(self):
        calls, ledger = self.batch()
        self.assertEqual(len(calls), 6); self.assertEqual(len(ledger['pairs']), 3)
        self.assertTrue(ledger['success']); self.assertEqual(ledger['applied_profile'], 1171)

    def test_failures_stop_without_retry(self):
        for n in (1, 2, 6):
            calls, ledger = self.batch(fail_at=n)
            self.assertEqual(len(calls), n); self.assertFalse(ledger['success'])
        calls, ledger = self.batch(reject=True)
        self.assertEqual(len(calls), 1); self.assertFalse(ledger['success'])

    def test_reject_historical_job_and_missing_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze.analyze(Path(tmp), common.load_protocol(), common.old_protocol()['jobs'][0])
            self.assertFalse(result['accepted']); self.assertIn('historical results', result['error'])
            (Path(tmp) / 'result.json').write_text('{}')
            result = analyze.analyze(Path(tmp), common.load_protocol(), common.load_protocol()['jobs'][0])
            self.assertFalse(result['accepted']); self.assertIn('authorization.json', result['error'])


if __name__ == '__main__': unittest.main()
