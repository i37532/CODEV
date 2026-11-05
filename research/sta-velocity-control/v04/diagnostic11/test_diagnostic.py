import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import common


class Diagnostic(unittest.TestCase):
    def test_task_parameters_and_gates_unchanged(self):
        p = common.load_protocol(); old = common.inherited_protocol()
        changed = {'stage', 'maximum_attempts', 'seeds', 'jobs', 'formal_acceptance', 'diagnostic'}
        self.assertEqual({k: v for k, v in p.items() if k not in changed},
                         {k: v for k, v in old.items() if k not in changed})
        self.assertEqual(len(p['jobs']), 1); self.assertEqual(p['jobs'][0]['mode'], 0)

    def test_flight_safety_body_is_identical(self):
        old = (common.REPO / 'research/sta-velocity-control/scripts/run_v04_flight12.py').read_text()
        expected = old.replace('Protocol10 authorized landing10 integration',
            'Single-attempt PID diagnostic; inherited landing10 integration').replace('parents[3]', 'parents[4]').replace(
            'from v04_protocol10 import CONFIG, load_protocol, require_authorization',
            'from common import CONFIG, load_protocol, require_authorization').replace(
            'Wrong protocol10 scenario binding', 'Wrong diagnostic11 scenario binding')
        self.assertEqual((common.CONFIG / 'flight.py').read_text(), expected)

    def test_receipt_requires_correct_head_hash_and_budget(self):
        p = common.load_protocol()
        good = dict(approved=True, stage=p['stage'], source_head='test-head', maximum_attempts=1,
            execution_sha256=common.digest(common.CONFIG / 'execution.json'),
            basis='standing user authorization for ordinary repairs and new SITL batches')
        with tempfile.TemporaryDirectory() as d, patch.object(common.subprocess, 'check_output', return_value='test-head\n'):
            path = Path(d) / 'receipt.json'; path.write_text(json.dumps(good))
            self.assertEqual(common.require_authorization(str(path), p), good)
            for field, wrong in [('approved', False), ('source_head', 'other'), ('stage', 'other'),
                                 ('execution_sha256', 'other'), ('maximum_attempts', 6), ('basis', 'other')]:
                path.write_text(json.dumps({**good, field: wrong}))
                with self.assertRaises(RuntimeError): common.require_authorization(str(path), p)

    def test_missing_receipt_denied(self):
        with self.assertRaises(RuntimeError): common.require_authorization('', common.load_protocol())


if __name__ == '__main__': unittest.main()
