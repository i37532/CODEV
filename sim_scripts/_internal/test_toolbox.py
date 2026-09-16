"""Boundary tests for the internal command layer; no simulator launched."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import toolbox as t


class ToolboxTests(unittest.TestCase):
    def test_airborne_or_armed_refused_before_any_parameter_write(self):
        for armed, landed in [(2, True), (1, False)]:
            def topic(name):
                return {'arming_state': armed} if name == 'vehicle_status' else {'landed': landed}
            with patch.object(t, 'parameter', return_value=10016), patch.object(t, 'topic', side_effect=topic), patch.object(t, 'cli') as cli:
                with self.assertRaises(RuntimeError):
                    t.set_parameter('MC_RTC_MODE', 1)
                cli.assert_not_called()

    def test_wrong_airframe_refused(self):
        with patch.object(t, 'parameter', return_value=4065), patch.object(t, 'cli') as cli:
            with self.assertRaises(RuntimeError):
                t.set_parameter('MC_RTC_MODE', 1)
            cli.assert_not_called()

    def test_stale_and_missing_topics_rejected(self):
        for text in ('timestamp: 123 (2.0 seconds ago)', 'landed: True'):
            with patch.object(t, 'cli', return_value=text):
                with self.assertRaises(RuntimeError):
                    t.topic('vehicle_status')

    def test_request_is_not_effective_acknowledgement(self):
        valid = dict(requested_mode=1, requested_axes=7, effective_mode=1, effective_axes=7,
                     fault=0, abort_requested=False, pending=False, config_pending=False,
                     config_valid=True, armed=False, nu=[0, 0, 0])
        self.assertTrue(t.accepted(valid, 1, 7))
        for key, value in [('effective_mode', 0), ('effective_axes', 3), ('pending', True),
                           ('config_pending', True), ('config_valid', False), ('fault', 1),
                           ('armed', True), ('nu', [0, .1, 0])]:
            self.assertFalse(t.accepted(dict(valid, **{key: value}), 1, 7), key)

    def test_existing_backup_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'before.json'
            with patch.object(t, 'BACKUP', path), patch.object(t, 'parameter', return_value=0):
                t.backup()
                initial = path.read_bytes()
                with patch.object(t, 'parameter', side_effect=AssertionError('backup reread')):
                    t.backup()
                self.assertEqual(initial, path.read_bytes())
                data = json.loads(initial); data['repository'] = '/different/repo'
                path.write_text(json.dumps(data))
                with self.assertRaises(RuntimeError):
                    t.backup()

    def test_partial_failure_does_not_select_esta(self):
        writes = []
        def write(name, value):
            writes.append((name, value))
            if name == 'MC_STA_L1_R':
                raise RuntimeError('CLI write failed')
        with patch.object(t, 'set_parameter', side_effect=write), patch.object(t, 'wait_selection'):
            with self.assertRaises(RuntimeError):
                t.apply_parameters(t.frozen_config())
        self.assertNotIn(('MC_RTC_MODE', 1), writes)

    def test_environment_cannot_silently_change_experiment(self):
        with patch.dict('os.environ', {'M06_CONFIG': '/wrong.json', 'M06_YAW_ONLY': '1', 'HEADLESS': '1', 'NO_PXH': '1'}):
            env = t.environment()
        self.assertFalse(any(k in env for k in ('M06_CONFIG', 'M06_YAW_ONLY', 'HEADLESS', 'NO_PXH')))
        self.assertEqual(env['PX4_SITL_WORLD'], str(t.ROOT / 'sitl/worlds/empty_grey.world'))

    def test_shutdown_disconnected_client_only_succeeds_when_processes_exit(self):
        with patch.object(t, 'ground'), patch.object(t, 'cli', side_effect=RuntimeError('socket closed')), patch('builtins.print'):
            with patch.object(t, 'processes', return_value=[]):
                t.stop_simulator()
            with patch.object(t, 'processes', return_value=[Path('/proc/123')]), patch.object(t.time, 'monotonic', side_effect=[0, 0, 20]), patch.object(t.time, 'sleep'):
                with self.assertRaises(RuntimeError):
                    t.stop_simulator()

    def test_compare_dispatches_six_runs_and_analysis_then_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'experiment with spaces'
            with patch.object(t, 'no_simulator'), patch.object(t.subprocess, 'run') as run, patch('builtins.print'):
                t.experiment('compare', output)
            calls = run.call_args_list
            flights = [c for c in calls if 'run_m06.py' in c.args[0][1]]
            analyses = [c for c in calls if 'analyze_m06.py' in c.args[0][1]]
            self.assertEqual([c.kwargs['env']['M06_MODE'] for c in flights], ['0'] * 3 + ['1'] * 3)
            self.assertEqual(len(analyses), 6)
            self.assertTrue(calls[-1].args[0][1].endswith('compare_m06.py'))
            with patch.object(t, 'no_simulator'), patch.object(t.subprocess, 'run'):
                with self.assertRaises(FileExistsError):
                    t.experiment('pid', output)


if __name__ == '__main__':
    unittest.main()
