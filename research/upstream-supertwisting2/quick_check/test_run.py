import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import run


class EntryAndCleanupTests(unittest.TestCase):
    def test_default_entry_never_executes_or_starts_process(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / 'manifest.json'
            manifest.write_text('{}')
            contract = types.ModuleType('runner_contract')
            contract.validate_manifest = Mock(return_value=dict(id='O001', system='PID', task='position'))
            with patch.dict('sys.modules', {'runner_contract': contract}), patch.object(run, 'execute') as execute, \
                    patch.object(run.subprocess, 'Popen') as popen, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run.main(['--manifest', str(manifest), '--job', 'O001']), 0)
            execute.assert_not_called()
            popen.assert_not_called()

    def test_draft_rejected_before_any_runtime_check(self):
        with patch.object(run.subprocess, 'run') as command:
            with self.assertRaisesRegex(ValueError, 'not flight qualified'):
                run.check_frozen({'flight_qualified': False}, {})
        command.assert_not_called()

    def test_active_simulator_rejected_before_runtime(self):
        with patch.object(run, 'active_simulators', return_value=[[123, 'px4']]), \
                patch.object(run.subprocess, 'run') as command:
            with self.assertRaisesRegex(ValueError, 'active'):
                run.check_frozen({'flight_qualified': True}, {})
        command.assert_not_called()

    def test_own_process_group_only(self):
        process = Mock(pid=54321)
        with patch.object(run.os, 'killpg') as kill:
            run.terminate_owned(process)
        kill.assert_called_once_with(54321, run.signal.SIGTERM)
        process.wait.assert_called_once_with(timeout=10)

    def test_owned_timeout_escalates_only_own_group(self):
        process = Mock(pid=54321)
        process.wait.side_effect = [subprocess.TimeoutExpired('owned', 10), 0]
        with patch.object(run.os, 'killpg') as kill:
            run.terminate_owned(process)
        self.assertEqual([call.args for call in kill.call_args_list],
                         [(54321, run.signal.SIGTERM), (54321, run.signal.SIGKILL)])

    def test_absent_process_has_no_cleanup_side_effect(self):
        with patch.object(run.os, 'killpg') as kill:
            run.terminate_owned(None)
        kill.assert_not_called()


class FrozenAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.job = dict(bin='/tmp/frozen/bin', firmware_sha256='binary', repo='/tmp/frozen',
                       source_head='unchanged-head', source_assets={'controller.cpp': 'dirty-preserved'})
        self.manifest = dict(flight_qualified=True, assets={'/tmp/runner.py': 'tool'},
                             jobs=[self.job], runtime={'preflight': '/tmp/preflight.py'})
        self.hashes = {'/tmp/runner.py': 'tool', '/tmp/frozen/bin/px4': 'binary',
                       '/tmp/frozen/controller.cpp': 'dirty-preserved'}

    def contexts(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(run, 'active_simulators', return_value=[]))
        digest = stack.enter_context(patch.object(run, 'digest', side_effect=lambda path: self.hashes[str(path)]))
        head = stack.enter_context(patch.object(run.subprocess, 'check_output', return_value='unchanged-head\n'))
        preflight = stack.enter_context(patch.object(run.subprocess, 'run', return_value=types.SimpleNamespace(
            returncode=0, stdout='{"ready":true,"roundtrip_passed":true}')))
        return digest, head, preflight

    def test_matching_dirty_source_and_binary_are_accepted_without_git_mutation(self):
        digest, head, preflight = self.contexts()
        with patch.object(run.subprocess, 'Popen') as popen:
            result = run.check_frozen(self.manifest, self.job)
        self.assertEqual(result, {'ready': True, 'roundtrip_passed': True})
        head.assert_called_once_with(['git', 'rev-parse', 'HEAD'], cwd='/tmp/frozen', text=True)
        self.assertEqual({str(call.args[0]) for call in digest.call_args_list}, set(self.hashes))
        self.assertEqual(preflight.call_args.args[0], [run.sys.executable, '/tmp/preflight.py'])
        popen.assert_not_called()

    def test_changed_tool_blocks_before_firmware_or_runtime(self):
        unused, head, preflight = self.contexts()
        self.hashes['/tmp/runner.py'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'Frozen asset changed'):
            run.check_frozen(self.manifest, self.job)
        head.assert_not_called(); preflight.assert_not_called()

    def test_changed_firmware_blocks_before_runtime(self):
        unused, head, preflight = self.contexts()
        self.hashes['/tmp/frozen/bin/px4'] = 'rebuilt'
        with self.assertRaisesRegex(ValueError, 'Firmware changed'):
            run.check_frozen(self.manifest, self.job)
        head.assert_not_called(); preflight.assert_not_called()

    def test_changed_source_head_blocks_before_runtime(self):
        unused, head, preflight = self.contexts()
        head.return_value = 'new-head\n'
        with self.assertRaisesRegex(ValueError, 'HEAD changed'):
            run.check_frozen(self.manifest, self.job)
        preflight.assert_not_called()

    def test_changed_preexisting_dirty_file_blocks_before_runtime(self):
        unused, head, preflight = self.contexts()
        self.hashes['/tmp/frozen/controller.cpp'] = 'unexpected-edit'
        with self.assertRaisesRegex(ValueError, 'Source changed'):
            run.check_frozen(self.manifest, self.job)
        preflight.assert_not_called()

    def test_dependency_or_real_dds_failure_blocks(self):
        unused, head, preflight = self.contexts()
        for returncode, stdout in [(1, 'missing dependency'), (0, '{"ready":true,"roundtrip_passed":false}'),
                                   (0, '{"ready":true}'), (0, '{"ready":1,"roundtrip_passed":true}')]:
            preflight.return_value = types.SimpleNamespace(returncode=returncode, stdout=stdout)
            with self.subTest(returncode=returncode, stdout=stdout), self.assertRaises(ValueError):
                run.check_frozen(self.manifest, self.job)

    def test_dependency_timeout_cannot_fall_through_to_launch(self):
        unused, head, preflight = self.contexts()
        preflight.side_effect = subprocess.TimeoutExpired('preflight', 45)
        with patch.object(run.subprocess, 'Popen') as popen:
            with self.assertRaises(subprocess.TimeoutExpired):
                run.check_frozen(self.manifest, self.job)
        popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
