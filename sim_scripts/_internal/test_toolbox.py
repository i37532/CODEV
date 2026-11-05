"""Boundary tests for the internal command layer; no simulator launched."""
import json
from contextlib import nullcontext
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
        for mode in (1, 2):
            valid.update(requested_mode=mode, effective_mode=mode)
            self.assertTrue(t.accepted(valid, mode, 7))
            for key, value in [('effective_mode', 0), ('effective_axes', 3), ('pending', True),
                               ('config_pending', True), ('config_valid', False), ('fault', 1),
                               ('armed', True), ('nu', [0, .1, 0])]:
                self.assertFalse(t.accepted(dict(valid, **{key: value}), mode, 7), key)

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

    def test_partial_failure_does_not_select_experiment(self):
        for mode in (1, 2):
            writes = []
            def write(name, value):
                writes.append((name, value))
                if name == 'MC_STA_L1_R':
                    raise RuntimeError('CLI write failed')
            with patch.object(t, 'set_parameter', side_effect=write), patch.object(t, 'wait_selection'):
                with self.assertRaises(RuntimeError):
                    t.apply_parameters(t.frozen_config(mode))
            self.assertNotIn(('MC_RTC_MODE', mode), writes)

    def test_environment_cannot_silently_change_experiment(self):
        with patch.dict('os.environ', {'M06_CONFIG': '/wrong.json', 'M06_YAW_ONLY': '1', 'M08_CONFIG': '/wrong-ista.json', 'M08_MODE': '1', 'HEADLESS': '1', 'NO_PXH': '1'}):
            env = t.environment()
        self.assertFalse(any(k in env for k in ('M06_CONFIG', 'M06_YAW_ONLY', 'M08_CONFIG', 'M08_MODE', 'HEADLESS', 'NO_PXH')))
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

    def test_ista_uses_accepted_candidate02_and_same_parameter_schema(self):
        esta, ista = t.frozen_config(1), t.frozen_config(2)
        self.assertEqual(ista['MC_RTC_MODE'], 2)
        self.assertEqual(ista['MC_STA_AXES'], 7)
        self.assertEqual(ista['MC_STA_L1_P'], 2.0)
        self.assertEqual(esta['MC_STA_L1_P'], 2.4)
        self.assertEqual(set(ista), set(esta))
        self.assertEqual({**esta, 'MC_RTC_MODE': 2, 'MC_STA_L1_P': 2.0}, ista)
        with self.assertRaises(ValueError):
            t.frozen_config(3)

    def test_ista_bad_fingerprint_refused_before_writes(self):
        index = {'accepted_configurations': {'iris_ista_rpy_candidate02.json': '0'*64}}
        with patch.object(t, 'ground'), patch.object(t, 'topic', return_value={'fault': 0, 'abort_requested': False}), \
                patch.object(t, 'load', return_value=index), patch.object(t, 'apply_parameters') as apply:
            with self.assertRaises(RuntimeError):
                t.switch(2, 7)
            apply.assert_not_called()

    def test_ista_switch_loads_candidate_and_ground_rejection_does_not_write(self):
        with patch.object(t, 'ground'), patch.object(t, 'topic', return_value={'fault': 0, 'abort_requested': False}), \
                patch.object(t, 'backup'), patch.object(t, 'apply_parameters') as apply, patch('builtins.print'):
            t.switch(2, 7)
            self.assertEqual(apply.call_args.args[0]['MC_RTC_MODE'], 2)
            self.assertEqual(apply.call_args.args[0]['MC_STA_L1_P'], 2.0)
        with patch.object(t, 'ground', side_effect=RuntimeError('armed')), patch.object(t, 'cli') as cli:
            with self.assertRaises(RuntimeError):
                t.switch(2, 7)
            cli.assert_not_called()

    def test_switch_cli_dispatches_three_algorithms(self):
        for name, mode in t.MODES.items():
            with patch('sys.argv', ['toolbox.py', 'switch', name]), patch.object(t, 'lock', return_value=nullcontext()), \
                    patch.object(t, 'switch') as switch:
                t.main()
                switch.assert_called_once_with(mode, 0 if mode == 0 else 7)

    def test_restore_accepts_original_ista_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'parameters-before.json'
            values = t.frozen_config(2)
            path.write_text(json.dumps({'parameters': values}))
            with patch.object(t, 'STATE', Path(directory)), patch.object(t, 'BACKUP', path), \
                    patch.object(t, 'ground'), patch.object(t, 'backup'), patch.object(t, 'apply_parameters') as apply, \
                    patch.object(t, 'cli') as cli, patch('builtins.print'):
                t.restore()
                apply.assert_called_once_with(values)
                cli.assert_called_once_with('param', 'save')
                self.assertFalse(path.exists())
                self.assertEqual(len(list(Path(directory).glob('restored-*.json'))), 1)


if __name__ == '__main__':
    unittest.main()
