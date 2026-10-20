"""Offline negative tests; temporary fixtures and mocked execution, never a flight/build.

XML parsing is the actual inherited checker. Main-path tests deliberately mock
commands/count inventories and prove only qualification/parameter-write guards.
"""
from contextlib import contextmanager, ExitStack, redirect_stdout
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_up08_test_verify', HERE/'verify.py')
v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
f, p = v.freeze, v.p
REAL_XML = v.helper.xml_inventory


class Scope(unittest.TestCase):
    def call(self, changed=(), untracked=(), assets=None, actual=None):
        assets = assets or {'src/immutable.cpp': 'fixed'}
        actual = assets if actual is None else actual
        def git(*args):
            return '\n'.join(changed if args[0] == 'diff' else untracked)
        with patch.object(f.p, 'git', side_effect=git), patch.object(f.p, 'read', return_value={'assets': assets}), \
                patch.object(f.p, 'fingerprint', side_effect=lambda path: actual[str(Path(path).relative_to(f.REPO))]):
            return f.scope()

    def test_exact_eleven_file_allowlist(self):
        self.assertEqual(len(f.ALLOWED), 11)
        self.assertEqual(self.call(changed=sorted(f.ALLOWED)), sorted(f.ALLOWED))
        self.assertNotIn('src/modules/ekf2/EKF2Selector.cpp', f.ALLOWED)
        self.assertNotIn('src/modules/mc_pos_control/PositionControl/PositionControl.cpp', f.ALLOWED)

    def test_unexpected_tracked_controller_change_rejected(self):
        with self.assertRaisesRegex(ValueError, 'scope exceeded'):
            self.call(changed=['src/modules/mc_pos_control/PositionControl/PositionControl.cpp'])

    def test_untracked_upstream_code_rejected(self):
        with self.assertRaisesRegex(ValueError, 'scope exceeded'):
            self.call(untracked=['src/modules/sensors/unapproved.cpp'])

    def test_frozen_old_research_asset_change_rejected(self):
        name = 'research/sta-velocity-control/regularized_sta/r03_revision06/analyzer.py'
        with self.assertRaisesRegex(ValueError, 'Immutable inherited asset'):
            self.call(assets={name: 'frozen'}, actual={name: 'modified'})

    def test_allowed_file_change_does_not_exempt_other_asset(self):
        allowed = 'src/modules/logger/params.c'
        with self.assertRaisesRegex(ValueError, 'Immutable inherited asset'):
            self.call(changed=[allowed], assets={allowed: 'old', 'src/immutable.cpp': 'old'},
                      actual={allowed: 'new', 'src/immutable.cpp': 'new'})

    def test_frozen_capture_rejects_changed_json_type(self):
        with patch.object(f.p, 'read', return_value={'new_flights': 0}), \
                patch.object(f, 'capture', return_value={'new_flights': False}):
            with self.assertRaisesRegex(ValueError, 'Frozen diagnostic'):
                f.check()

    def test_dirty_or_wrong_recursive_submodules_rejected(self):
        correct = [' a'*1 + str(i) for i in range(33)]
        for rows, dirty in [(correct[:32], ''), (['+'+correct[0][1:]]+correct[1:], ''), (correct, ' M file')]:
            with self.subTest(count=len(rows), dirty=dirty), \
                    patch.object(f.subprocess, 'check_output', return_value='\n'.join(rows)), \
                    patch.object(f.p, 'git', return_value=dirty):
                with self.assertRaises(ValueError): f.submodules()


class Xml(unittest.TestCase):
    def check(self, body):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'tests.xml'; path.write_text(body)
            return REAL_XML([path])

    def test_zero_tests_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'Empty/inconsistent'):
            self.check('<testsuites tests="0" failures="0" disabled="0" errors="0"/>')

    def test_empty_inventory_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'Zero tests'): REAL_XML([])

    def test_declared_count_without_execution_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'Empty/inconsistent'):
            self.check('<testsuites tests="525"/>')

    def test_skipped_test_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'failed/skipped'):
            self.check('<testsuites tests="1"><testcase classname="X" name="a" status="run"><skipped/></testcase></testsuites>')

    def test_completed_identity_counts_once(self):
        body = '<testsuites tests="1"><testcase classname="X" name="a" status="run" result="completed"/></testsuites>'
        with tempfile.TemporaryDirectory() as tmp:
            files = [Path(tmp)/x for x in ('one.xml', 'two.xml')]
            for path in files: path.write_text(body)
            value = REAL_XML(files)
            self.assertEqual(value['unique_tests'], 1)
            self.assertEqual(value['executed_xml_cases'], 2)


class Qualification(unittest.TestCase):
    @contextmanager
    def evidence(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root = Path(tmp); evidence = root/'qualification01'; evidence.mkdir()
            log = evidence/'actual.log'; log.write_text('mock command evidence; not a real regression\n')
            path = evidence/'evidence.json'
            expected = dict(stage=p.STAGE, revision=p.REVISION, source_head='a'*40,
                            execution_sha256='new-execution', frozen_sha256='new-frozen',
                            firmware_sha256='new-binary', maximum_attempts=2,
                            total_maximum_attempts=54, logging_profile_after=3089)
            q = {**expected, 'success': True, 'clean': True,
                 'counts': {'cpp_unique_tests': 525, 'python_tests': 800},
                 'cpp_test_targets': ['functional-VehicleIMU', 'functional-EKF2SelectorTiming',
                                      'functional-EstimatorDiagnosticTopics'],
                 'evidence_files': {str(log): p.fingerprint(log)}}
            receipt = dict(approved=True, source_head='a'*40, qualification_sha256='receipt')
            def save():
                path.write_text(json.dumps(q)); (evidence/'authorization.json').write_text(json.dumps(receipt))
            save()
            stack.enter_context(patch.object(p, 'DATA_ROOT', root))
            stack.enter_context(patch.object(p, 'load_file', return_value=types.SimpleNamespace(check=lambda: {})))
            stack.enter_context(patch.object(p, 'qualification_binding', return_value=expected))
            stack.enter_context(patch.object(p, 'authorization_binding', return_value=dict(receipt)))
            stack.enter_context(patch.object(p, 'git', side_effect=lambda *args:
                'a'*40 if args[0]=='rev-parse' else ('research/sta-velocity-regularized' if args[0]=='branch' else '')))
            yield q, receipt, path, save, log

    def test_exact_new_fixture_passes_not_a_real_qualification(self):
        with self.evidence() as (q, _, path, _, __):
            self.assertEqual(p.require_qualification('a'*40, path), q)

    def test_old_revision_source_binary_and_logging_rejected(self):
        for key, value in [('revision', 'r03_revision06'), ('source_head', 'b'*40),
                           ('execution_sha256', 'old'), ('frozen_sha256', 'old'),
                           ('firmware_sha256', 'old'), ('logging_profile_after', 1041)]:
            with self.subTest(key=key), self.evidence() as (q, _, path, save, __):
                q[key] = value; save()
                with self.assertRaisesRegex(ValueError, 'Wrong clean'): p.require_qualification('a'*40, path)

    def test_dirty_current_checkout_cannot_borrow_clean_receipt(self):
        with self.evidence() as (_, __, path, ___, ____), \
                patch.object(p, 'git', side_effect=lambda *a: 'a'*40 if a[0]=='rev-parse' else ' M file'):
            with self.assertRaisesRegex(ValueError, 'current qualified clean'): p.require_qualification('a'*40, path)

    def test_zero_small_float_or_boolean_test_counts_rejected(self):
        for count in (0, 524, 525.0, True):
            with self.subTest(count=count), self.evidence() as (q, _, path, save, __):
                q['counts']['cpp_unique_tests'] = count; save()
                with self.assertRaisesRegex(ValueError, 'actual required'): p.require_qualification('a'*40, path)

    def test_missing_new_timing_target_rejected(self):
        with self.evidence() as (q, _, path, save, __):
            q['cpp_test_targets'].remove('functional-EKF2SelectorTiming'); save()
            with self.assertRaisesRegex(ValueError, 'upstream diagnostic test'): p.require_qualification('a'*40, path)

    def test_evidence_tampering_rejected(self):
        with self.evidence() as (_, __, path, ___, log):
            log.write_text('changed')
            with self.assertRaisesRegex(ValueError, 'evidence changed'): p.require_qualification('a'*40, path)

    def test_old_receipt_rejected(self):
        with self.evidence() as (_, receipt, path, save, __):
            receipt['source_head'] = 'b'*40; save()
            with self.assertRaisesRegex(ValueError, 'authorization receipt'): p.require_qualification('a'*40, path)


class MainSafety(unittest.TestCase):
    @contextmanager
    def harness(self, *, dirty=False, mutate_parameter=False, mutate_source=False, command_timeout=False):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            repo = Path(tmp)/'repo'; repo.mkdir(); data = Path(tmp)/'data'; data.mkdir()
            current = repo/'current'; current.mkdir(); (current/'test_dummy.py').write_text('# not executed\n')
            out = data/'qualification01'; parameter = repo/'parameters'; parameter.write_bytes(b'original bson fixture')
            source = repo/'frozen.py'; source.write_text('# frozen\n')
            metadata = repo/'build/px4_sitl_default/parameters.xml'; metadata.parent.mkdir(parents=True)
            metadata.write_text('<parameters><parameter name="SDLOG_PROFILE" default="1"><max>4095</max></parameter></parameters>')
            version = repo/'build/px4_sitl_default/src/lib/version/build_git_version.h'; version.parent.mkdir(parents=True)
            version.write_text('a'*40)
            snapshot = dict(assets={'frozen.py': p.fingerprint(source)}, external_assets={}, submodules=[' fixed']*33)
            calls = []
            def command(argv, **kwargs):
                calls.append(list(map(str, argv)))
                if argv[0] == 'python3' and '--historical-diagnostic' in argv:
                    target = Path(argv[argv.index('--output')+1]); target.mkdir()
                    number = int(Path(argv[2]).name[-3:])
                    (target/'evidence.json').write_text(json.dumps(dict(original_accepted=number!=30,
                        accepted=False, source_inputs_unchanged=True, new_flights=0)))
                elif argv[0] == 'python3' and '--output' in argv:
                    target = Path(argv[argv.index('--output')+1]); target.mkdir()
                    (target/'evidence.json').write_text('{"success":true}')
                if argv[0] == 'make':
                    if mutate_parameter: parameter.write_bytes(b'unexpected mutation')
                    if mutate_source: source.write_text('# unexpected source mutation\n')
                return types.SimpleNamespace(returncode=0)
            def popen(argv, **kwargs):
                result = command(argv, **kwargs)
                self.assertIs(kwargs.get('start_new_session'), True)
                if command_timeout:
                    waits = iter([v.subprocess.TimeoutExpired(argv, 1200), -15])
                    def wait(timeout):
                        value = next(waits)
                        if isinstance(value, BaseException): raise value
                        return value
                else:
                    wait = lambda timeout: result.returncode
                return types.SimpleNamespace(pid=424242, wait=wait)
            def inventory(paths):
                paths = list(paths)
                return {'unique_tests': 16 if len(paths)==1 and paths[0].name=='RegularizedVelocityRegression.xml' else 525}
            replacements = [(v, 'REPO', repo), (v, 'HERE', current), (v, 'EEPROM', parameter),
                (v, 'TARGETS', [('RegularizedVelocityRegression', 'unit')]), (p, 'DATA_ROOT', data)]
            for obj, key, value in replacements: stack.enter_context(patch.object(obj, key, value))
            stack.enter_context(patch.object(sys, 'argv', ['verify.py', '--output', str(out), '--qualify']))
            stack.enter_context(patch.object(p, 'git', side_effect=lambda *a:
                (' M file' if dirty else '') if a[0]=='status' else ('a'*40 if a[0]=='rev-parse' else 'research/sta-velocity-regularized')))
            stack.enter_context(patch.object(p, 'require_execution_authority', return_value={}))
            stack.enter_context(patch.object(v.freeze, 'check', return_value=snapshot))
            stack.enter_context(patch.object(v.freeze, 'scope', return_value=[]))
            stack.enter_context(patch.object(v.freeze, 'submodules', return_value=snapshot['submodules']))
            stack.enter_context(patch.object(v.R02, 'check_reference', return_value={}))
            stack.enter_context(patch.object(v.R02, 'check_metadata', return_value={}))
            stack.enter_context(patch.object(v.helper, 'xml_inventory', side_effect=inventory))
            stack.enter_context(patch.object(v.helper, 'python_leaf_counts', return_value={'tests': 800}))
            stack.enter_context(patch.object(p, 'qualification_binding', return_value={'stage': p.STAGE}))
            stack.enter_context(patch.object(p, 'authorization_binding', return_value={'approved': True}))
            stack.enter_context(patch.object(v.subprocess, 'run', side_effect=command))
            stack.enter_context(patch.object(v.subprocess, 'Popen', side_effect=popen))
            killed = stack.enter_context(patch.object(v.os, 'killpg'))
            stack.enter_context(redirect_stdout(io.StringIO()))
            yield out, parameter, calls, killed

    def test_dirty_qualification_rejected_before_command_or_output(self):
        with self.harness(dirty=True) as (out, parameter, calls, _):
            with self.assertRaisesRegex(ValueError, 'clean committed'): v.main()
            self.assertFalse(out.exists()); self.assertEqual(calls, [])
            self.assertEqual(parameter.read_bytes(), b'original bson fixture')

    def test_parameter_mutation_rejects_without_silent_restore_or_authority(self):
        with self.harness(mutate_parameter=True) as (out, parameter, calls, _):
            with self.assertRaisesRegex(ValueError, 'Submodule/EEPROM changed'): v.main()
            self.assertGreater(len(calls), 0)
            self.assertEqual(parameter.read_bytes(), b'unexpected mutation')
            evidence = json.loads((out/'evidence.json').read_text())
            self.assertIs(evidence['success'], False)
            self.assertNotEqual(evidence['eeprom_before'], evidence['eeprom_final'])
            self.assertFalse((out/'authorization.json').exists())

    def test_source_mutation_rejects_before_authority(self):
        with self.harness(mutate_source=True) as (out, _, __, ___):
            with self.assertRaisesRegex(ValueError, 'Input changed'): v.main()
            self.assertFalse((out/'authorization.json').exists())

    def test_mocked_success_leaves_parameter_unchanged(self):
        # Not real qualification evidence: every external command/count is mocked.
        with self.harness() as (out, parameter, calls, _):
            v.main()
            self.assertEqual(parameter.read_bytes(), b'original bson fixture')
            self.assertTrue((out/'authorization.json').is_file())
            self.assertGreater(len(calls), 0)
            self.assertFalse(any('--execute' in c for c in calls))

    def test_timeout_terminates_only_owned_group_and_never_authorizes(self):
        with self.harness(command_timeout=True) as (out, parameter, calls, killed):
            with self.assertRaisesRegex(ValueError, 'build_test_targets failed'): v.main()
            self.assertEqual(len(calls), 1)
            killed.assert_called_once_with(424242, v.signal.SIGTERM)
            self.assertFalse((out/'authorization.json').exists())
            self.assertEqual(parameter.read_bytes(), b'original bson fixture')
            self.assertEqual(json.loads((out/'evidence.json').read_text())['commands'][0]['exit_code'], 124)


if __name__ == '__main__': unittest.main(verbosity=2)
