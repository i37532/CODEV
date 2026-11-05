"""Verify inventory, source isolation and non-flight authority boundaries."""
import ast
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_hte_fix_verify_tested', HERE/'verify.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class Inventory(unittest.TestCase):
    def test_48_actual_required_targets_preserved(self):
        self.assertEqual(len(v.TARGETS), 48)
        self.assertEqual(set(v.TARGETS), v.old.p.REQUIRED_TARGETS)

    def test_all_original_36_python_suites_preserved(self):
        original, new = v.receipt.python_commands(), v.python_commands()
        self.assertEqual(len(original), 36)
        self.assertTrue(original.items() <= new.items())
        self.assertEqual(set(new)-set(original), {'hte_test_fixture','hte_test_verify'})

    def test_original_matlab_package_and_replay_targets_retained(self):
        source = (HERE/'verify.py').read_text()
        self.assertIn("sha256sum','--check','SHA256SUMS.txt", source)
        self.assertIn("('X',(1,2,3)), ('Z',(10,11,12))", source)
        self.assertIn("HERE.parent/'ri03/tools/analyzer.py'", source)
        self.assertIn("old.OLD/'r03_position11/audit.py'", source)

    def test_no_new_freeze_qualification_or_flight_call(self):
        tree = ast.parse((HERE/'verify.py').read_text())
        calls = [ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)]
        forbidden = ('capture','qualification_binding','require_qualification','authorization_binding',
                     'require_execution_authority','flight_main','run_one','finalize')
        self.assertFalse(any(x.split('.')[-1] in forbidden for x in calls))
        source = (HERE/'verify.py').read_text()
        self.assertNotIn("add_argument('--qualify'", source)
        self.assertIn("flight_authorized=False", source)
        self.assertIn("approved=False", source)
        self.assertIn("new_budget=0", source)

    def test_new_directory_only_output(self):
        with patch('sys.argv', ['verify.py','--output','/tmp/not-a-flight-output']), \
                self.assertRaisesRegex(ValueError, 'new offline evidence'):
            v.main()

    def test_source_allowlist_is_only_the_authorized_three_files(self):
        self.assertEqual(v.ALLOWED, {
            'src/modules/mc_pos_control/PositionControl/PositionControl.cpp',
            'src/modules/mc_pos_control/PositionControl/RegularizedIstaPositionTest.cpp',
            'src/modules/mc_pos_control/RegularizedIstaVelocityModuleTest.cpp'})

    def snapshot(self, name, current='new', external='old'):
        frozen = {'assets': {name:'old'}, 'external_assets': {'/external/model':'old'}}
        def digest(path):
            return external if str(path) == '/external/model' else current
        with patch.object(v, 'read', return_value=frozen), patch.object(v, 'sha', side_effect=digest), \
                patch.object(v.old.freeze, 'submodules', return_value=['unchanged']):
            return v.input_snapshot()

    def test_changed_production_file_explicitly_bound(self):
        name = 'src/modules/mc_pos_control/PositionControl/PositionControl.cpp'
        snapshot = self.snapshot(name)
        self.assertEqual(snapshot['changed_from_ri04_flight_source'][name],
                         {'old_sha256':'old','new_sha256':'new'})

    def test_unknown_production_or_old_tool_change_rejected(self):
        for name in ('src/modules/ekf2/EKF2.cpp', 'research/sta-velocity-control/regularized_ista/ri04/tools/analyzer.py'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Unexpected inherited'):
                self.snapshot(name)

    def test_changed_external_model_rejected(self):
        with self.assertRaisesRegex(ValueError, 'External model'):
            self.snapshot('src/modules/mc_pos_control/PositionControl/PositionControl.cpp', external='changed')

    def test_false_empty_unittest_receipt_rejected(self):
        for text in (b'Ran 0 tests in 0.0s\n\nOK\n', b'Ran 22 tests in 1s\n\nFAILED\n'):
            with self.assertRaises(ValueError):
                v.receipt.unittest_count(text, 'fixture')


if __name__ == '__main__':
    unittest.main(verbosity=2)
