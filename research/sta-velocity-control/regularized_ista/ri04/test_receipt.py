"""RI04 raw receipt negatives; all synthetic artifacts stay in /tmp."""
import ast
import copy
import hashlib
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_ri04_receipt_test_subject', HERE/'receipt.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class Receipt(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ri04_receipt_', dir='/tmp')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root/'evidence.json'
        self.targets = {'unit-One', 'functional-Two'}
        self.expected = {
            'py00_fixture_test_one': ['python3', '-B', str(self.root/'test_one.py')],
            'py01_fixture_test_two': ['python3', '-B', str(self.root/'test_two.py')]}
        self.q = dict(counts=dict(cpp_unique_tests=4, cpp_targets=2, python_tests=5),
            cpp_test_targets=sorted(self.targets), commands=[], python_tests_executed=[], evidence_files={})
        for target in sorted(self.targets):
            self.write(target+'.xml', self.xml(target))
            self.add_command(target, [str(r.REPO/'build/px4_sitl_test'/target),
                '--gtest_output=xml:'+str(self.root/(target+'.xml'))], '[  PASSED  ] 2 tests.\n')
        for index, (name, argv) in enumerate(self.expected.items()):
            count = index+2
            self.add_command(name, argv, self.log(count))
            self.q['python_tests_executed'].append(dict(name=name, tests=count,
                log_sha256=self.q['evidence_files'][str(self.root/(name+'.log'))]))
        self.original = copy.deepcopy(self.q)

    @staticmethod
    def xml(suite='Suite'):
        return (f'<testsuites tests="2" failures="0" errors="0" disabled="0">'
            f'<testsuite name="{suite}" tests="2" failures="0" errors="0" disabled="0">'
            f'<testcase classname="{suite}" name="a" status="run"/>'
            f'<testcase classname="{suite}" name="b" status="run" result="completed"/>'
            '</testsuite></testsuites>')

    @staticmethod
    def log(count=2):
        return f'test leaves ... ok\n\n----------------------------------------------------------------------\nRan {count} tests in 0.001s\n\nOK\n'

    def write(self, name, value, *, rebind=True):
        path = self.root/name
        self.assertIn(Path('/tmp'), path.resolve().parents)
        path.write_bytes(value if isinstance(value, bytes) else value.encode())
        if rebind:
            self.q['evidence_files'][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return path

    def add_command(self, name, argv, log):
        path = self.write(name+'.log', log)
        self.q['commands'].append(dict(name=name, argv=argv, cwd=str(r.REPO), exit_code=0,
            log_sha256=self.q['evidence_files'][str(path)]))

    def replace_log(self, text, name='py00_fixture_test_one'):
        path = self.write(name+'.log', text)
        sha = self.q['evidence_files'][str(path)]
        for collection in ('commands', 'python_tests_executed'):
            for item in self.q[collection]:
                if item['name'] == name:
                    item['log_sha256'] = sha

    def check(self, minimum=5):
        return r.validate(self.q, self.path, self.targets, minimum, expected_python_commands=self.expected)

    def reject(self):
        with self.assertRaises(ValueError):
            self.check()

    def test_valid_raw_artifacts_are_recounted_without_mutating_receipt(self):
        self.assertEqual(self.check(), dict(cpp_unique_tests=4, executed_xml_cases=4,
            cpp_targets=2, python_tests=5, python_suites=2))
        self.assertEqual(self.q, self.original)

    def test_present_cpp_inventory_must_match_actual_unique_and_executed_counts(self):
        self.q['cpp_inventory'] = dict(unique_tests=4, executed_xml_cases=4)
        self.check()
        for field in ('unique_tests', 'executed_xml_cases'):
            for bad in (0, 5, True, '4'):
                self.q['cpp_inventory'] = dict(unique_tests=4, executed_xml_cases=4)
                self.q['cpp_inventory'][field] = bad
                with self.subTest(field=field, bad=bad): self.reject()

    def test_cross_executable_duplicate_identity_is_counted_only_once(self):
        self.write('unit-One.xml', self.xml('functional-Two'))
        self.q['counts']['cpp_unique_tests'] = 2
        self.assertEqual(self.check()['executed_xml_cases'], 4)
        self.q['counts']['cpp_unique_tests'] = 4
        self.reject()

    def test_single_suite_root_and_optional_legacy_result_are_supported(self):
        text = self.xml('unit-One')
        self.write('unit-One.xml', text[text.index('<testsuite name='):text.index('</testsuites>')])
        self.check()

    def test_default_inventory_cannot_be_selected_by_receipt(self):
        with self.assertRaises(ValueError):
            r.validate(self.q, self.path, self.targets, 5)
        with patch.object(r, 'python_commands', return_value=self.expected) as inventory:
            self.assertEqual(r.validate(self.q, self.path, self.targets, 5)['python_tests'], 5)
            inventory.assert_called_once_with()

    def test_missing_xml_is_rejected(self):
        (self.root/'unit-One.xml').unlink()
        self.reject()

    def test_unbound_xml_is_rejected(self):
        del self.q['evidence_files'][str(self.root/'unit-One.xml')]
        self.reject()

    def test_changed_xml_is_rejected_even_if_other_fields_still_match(self):
        self.write('unit-One.xml', self.xml('changed'), rebind=False)
        self.reject()

    def test_malformed_or_wrong_root_xml_is_rejected(self):
        for value in ('<testsuites>', '<not_a_test tests="0"/>'):
            self.write('unit-One.xml', value)
            with self.subTest(value=value): self.reject()

    def test_empty_or_false_declared_xml_counts_are_rejected(self):
        for value in ('<testsuites tests="0"/>', self.xml().replace('tests="2"', 'tests="3"', 1),
                      self.xml().replace('tests="2"', 'tests="-1"', 1),
                      self.xml().replace('tests="2"', 'tests="2.0"', 1)):
            self.write('unit-One.xml', value)
            with self.subTest(value=value): self.reject()

    def test_nested_suite_count_cannot_contradict_actual_cases(self):
        self.write('unit-One.xml', self.xml().replace('name="Suite" tests="2"', 'name="Suite" tests="1"'))
        self.reject()

    def test_summary_failure_error_disabled_or_skipped_rejects(self):
        for name in ('failures', 'errors', 'disabled', 'skipped'):
            value = self.xml().replace('<testsuites tests="2"', f'<testsuites skipped="1" tests="2"') if name == 'skipped' \
                else self.xml().replace(name+'="0"', name+'="1"', 1)
            self.write('unit-One.xml', value)
            with self.subTest(name=name): self.reject()

    def test_case_failure_error_or_skip_rejects_even_with_zero_summary(self):
        for tag in ('failure', 'error', 'skipped'):
            self.write('unit-One.xml', self.xml().replace('name="a" status="run"/>',
                f'name="a" status="run"><{tag}/></testcase>'))
            with self.subTest(tag=tag): self.reject()

    def test_unrun_incomplete_or_nameless_case_rejects(self):
        for before, after in [('status="run"', 'status="notrun"'),
                              ('result="completed"', 'result="suppressed"'),
                              ('name="a"', 'name=""'), ('classname="Suite"', 'classname=""')]:
            self.write('unit-One.xml', self.xml().replace(before, after, 1))
            with self.subTest(after=after): self.reject()

    def test_duplicate_case_in_one_xml_rejects(self):
        self.write('unit-One.xml', self.xml().replace('name="b"', 'name="a"'))
        self.reject()

    def test_missing_duplicate_or_extra_cpp_targets_reject(self):
        for targets in ([], ['unit-One'], ['unit-One', 'unit-One'], sorted(self.targets)+['unit-Extra']):
            self.q['cpp_test_targets'] = targets
            with self.subTest(targets=targets): self.reject()

    def test_false_cpp_or_python_totals_reject(self):
        for value in (None, [], 5, '5'):
            self.q['counts'] = value
            with self.subTest(counts=value): self.reject()
        for name in ('cpp_unique_tests', 'cpp_targets', 'python_tests'):
            for value in (0, None, True, False, '5', 5.0, 999):
                self.q['counts'] = copy.deepcopy(self.original['counts']); self.q['counts'][name] = value
                with self.subTest(name=name, value=value): self.reject()

    def test_minimum_python_applies_to_recount_not_claim(self):
        with self.assertRaises(ValueError): self.check(minimum=6)
        self.q['counts']['python_tests'] = 6
        with self.assertRaises(ValueError): self.check(minimum=6)

    def test_missing_duplicate_failed_or_noninteger_command_rejects(self):
        for change in ('missing', 'duplicate', 'failed', 'bool', 'string'):
            self.q['commands'] = copy.deepcopy(self.original['commands'])
            if change == 'missing': self.q['commands'].pop(0)
            elif change == 'duplicate': self.q['commands'].append(copy.deepcopy(self.q['commands'][0]))
            else: self.q['commands'][0]['exit_code'] = {'failed': 1, 'bool': False, 'string': '0'}[change]
            with self.subTest(change=change): self.reject()

    def test_wrong_cpp_binary_xml_destination_filter_or_cwd_rejects(self):
        for change in ('binary', 'xml', 'filter', 'cwd'):
            self.q['commands'] = copy.deepcopy(self.original['commands']); command = self.q['commands'][0]
            if change == 'binary': command['argv'][0] = '/tmp/not_the_test'
            elif change == 'xml': command['argv'][1] = '--gtest_output=xml:/tmp/foreign.xml'
            elif change == 'filter': command['argv'].append('--gtest_filter=One.*')
            else: command['cwd'] = '/tmp'
            with self.subTest(change=change): self.reject()

    def test_missing_cpp_or_python_command_log_rejects(self):
        for name in ('functional-Two', 'py00_fixture_test_one'):
            path = self.root/(name+'.log'); raw = path.read_bytes(); path.unlink()
            with self.subTest(name=name): self.reject()
            self.write(name+'.log', raw)

    def test_missing_or_forged_command_log_binding_rejects(self):
        for name in ('functional-Two', 'py00_fixture_test_one'):
            for value in (None, '0'*64):
                self.q['commands'] = copy.deepcopy(self.original['commands'])
                next(c for c in self.q['commands'] if c['name'] == name)['log_sha256'] = value
                with self.subTest(name=name, value=value): self.reject()

    def test_actual_log_tamper_is_not_hidden_by_unchanged_receipt_sha(self):
        self.write('py00_fixture_test_one.log', self.log(100), rebind=False)
        self.reject()

    def test_symlink_xml_or_log_is_rejected_even_with_same_bytes(self):
        for name in ('unit-One.xml', 'py00_fixture_test_one.log'):
            path = self.root/name; raw = path.read_bytes(); backing = self.write('backing', raw)
            path.unlink(); path.symlink_to(backing)
            with self.subTest(name=name): self.reject()
            path.unlink(); self.write(name, raw)

    def test_missing_empty_duplicate_or_extra_python_leaf_is_rejected(self):
        for leaves in (None, [], self.original['python_tests_executed'][:1],
                self.original['python_tests_executed']*2,
                self.original['python_tests_executed']+[dict(name='unknown', tests=1)]):
            self.q['python_tests_executed'] = copy.deepcopy(leaves)
            with self.subTest(leaves=leaves): self.reject()

    def test_missing_whole_suite_rejects_even_when_remaining_log_meets_minimum(self):
        self.q['python_tests_executed'].pop()
        self.q['python_tests_executed'][0]['tests'] = 5
        self.replace_log(self.log(5))
        self.reject()

    def test_false_leaf_count_or_leaf_sha_is_rejected(self):
        for field, values in [('tests', (0, True, None, '2', 2.0, 999)), ('log_sha256', (None, '0'*64))]:
            for value in values:
                self.q['python_tests_executed'] = copy.deepcopy(self.original['python_tests_executed'])
                self.q['python_tests_executed'][0][field] = value
                with self.subTest(field=field, value=value): self.reject()

    def test_wrong_python_script_or_extra_test_filter_is_rejected(self):
        for argv in (['python3', '-B', '/tmp/not_that_suite.py'],
                     self.expected['py00_fixture_test_one']+['SomeSpecificTest']):
            next(c for c in self.q['commands'] if c['name'] == 'py00_fixture_test_one')['argv'] = argv
            with self.subTest(argv=argv): self.reject()

    def test_zero_missing_duplicate_or_failed_unittest_summary_is_rejected(self):
        for value in (self.log(0), 'OK\n', 'Ran 2 tests in 0.001s\n', self.log()+self.log(),
                      self.log().replace('OK', 'FAILED (errors=1)'), self.log().replace('OK', 'OK (skipped=1)'),
                      self.log().replace('OK', 'OK (expected failures=1)')):
            self.replace_log(value)
            with self.subTest(value=value): self.reject()

    def test_invalid_encoding_or_nonleaf_summary_is_rejected(self):
        for value in (b'\xff', 'OK\n\nRan 2 tests in 0.001s\n', self.log().replace('\n\nOK', '\ninterposed result\nOK')):
            self.replace_log(value)
            with self.subTest(value=value): self.reject()

    def test_singular_unittest_summary_and_buffered_non_summary_output_are_supported(self):
        self.replace_log('Ran 1 test in 0.001s\n\nOK\nbuffered ordinary stdout\n')
        self.q['python_tests_executed'][0]['tests'] = 1; self.q['counts']['python_tests'] = 4
        self.assertEqual(self.check(minimum=4)['python_tests'], 4)


class Inventory(unittest.TestCase):
    def test_expected_python_inventory_matches_verifier_without_running_verifier(self):
        tree = ast.parse((HERE/'verify.py').read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'python_tests')
        def load_file(name, path):
            self.assertEqual(path, HERE/'receipt.py')
            return r
        namespace = dict(HERE=r.HERE, REPO=r.REPO, OLD=r.REPO/'research/sta-velocity-control/regularized_sta',
                         p=SimpleNamespace(load_file=load_file))
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<inventory-only>', 'exec'), namespace)
        self.assertEqual(namespace['python_tests'](), r.python_scripts())
        commands = r.python_commands()
        self.assertEqual(len(commands), len(r.python_scripts())+1)
        self.assertIn('r02_tools', commands)
        self.assertTrue(any(argv[-1] == str(HERE/'test_receipt.py') for argv in commands.values()))


if __name__ == '__main__':
    unittest.main(verbosity=2)
