import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('r02_verifier', Path(__file__).with_name('verify.py'))
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class AuditTest(unittest.TestCase):
    def test_frozen_reference_matches_git_not_worktree(self):
        result = v.check_reference()
        self.assertEqual(len(result), 5)
        self.assertTrue(all(len(x) == 64 for x in result.values()))

    def test_actual_admission_remains_closed(self):
        result = v.check_closed_admission()
        self.assertFalse(result['private_default'])
        self.assertEqual(len(result['source_consumers']), 5)

    def test_unexpected_gate_consumer_rejected(self):
        with patch.object(v.subprocess, 'check_output', return_value='src/unexpected.cpp\n'):
            with self.assertRaisesRegex(RuntimeError, 'Unexpected admission consumer'):
                v.check_closed_admission()

    def test_allowed_production_scope_excludes_upstream_model_and_core(self):
        for name in ('src/modules/ekf2/EKF2.cpp', 'src/modules/sensors/sensors.cpp',
                     'msg/sta_velocity_ctrl_status.msg', v.POS + 'RegularizedStaVelocityControl.cpp',
                     v.POS + 'StaVelocityControl.cpp', v.POS + 'ControlMath.cpp'):
            self.assertNotIn(name, v.ALLOWED)
        self.assertEqual(len(v.ALLOWED), 15)

    def test_xml_rejects_zero_and_failed_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'test.xml'
            p.write_text('<testsuites tests="0" failures="0" errors="0" disabled="0"/>')
            with self.assertRaises(RuntimeError):
                v.helper.xml_inventory([p])
            p.write_text('<testsuites tests="1" failures="1"><testsuite><testcase name="n" classname="c" status="run">'
                         '<failure/></testcase></testsuite></testsuites>')
            with self.assertRaises(RuntimeError):
                v.helper.xml_inventory([p])


if __name__ == '__main__':
    unittest.main()
