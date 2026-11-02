"""Offline collector wiring using frozen jobs and recorded CLI text.

The nested production topic/diagnostics/sample/verify_configuration functions are
compiled unchanged into a test closure. Only process/CLI/receipt boundaries are
stubbed; no simulator, subprocess, UDP or ROS is started. Stage mutations below
are explicitly synthetic, not a replay of unflown stages or flight acceptance.
"""
import ast
import copy
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import Mock, patch

import run
import runner_contract as contract

HERE = Path(__file__).resolve().parent
MANIFEST_PATH = HERE / 'results/batch02/manifest.json'
MANIFEST = json.loads(MANIFEST_PATH.read_text())
FIXTURE = json.loads((HERE / 'results/diagnostic_fix01/cli_fixture.json').read_text())
FROZEN = HERE / 'results/batch02/frozen_tools/run.py'


def job_for(system):
    return copy.deepcopy(next(job for job in MANIFEST['jobs'] if job['system'] == system))


class RecordedCLI:
    def __init__(self, system):
        self.row = copy.deepcopy(FIXTURE['systems'][system])
        self.core = copy.deepcopy(FIXTURE['systems']['STA2' if system == 'STA2' else 'PID'])
        self.calls, self.overrides = [], {}
        self.missing = set()
        self.phase = 'recover'

    @property
    def origin(self):
        return self.core['origin']

    def __call__(self, module, *args, **kwargs):
        self.calls.append((module, *args))
        if module == 'param':
            assert args == ('show', '-a')
            return self.row['parameter_lines']
        assert module == 'listener' and args[1:] == ('-n', '1')
        topic = args[0]
        if topic in self.missing:
            return 'never published\n'
        row = self.row['diagnostics'].get(topic, self.core['core'].get(topic))
        assert row is not None, topic
        text = row['stdout']
        mutations = {}
        if self.phase in ('warmup', 'prestream', 'landing'):
            if topic == 'vehicle_status':
                mutations = dict(arming_state=1, nav_state=18 if self.phase == 'landing' else 14)
            elif topic == 'vehicle_land_detected':
                mutations = dict(landed=True, ground_contact=True, maybe_landed=True)
            elif topic == 'vehicle_local_position':
                mutations = dict(z=self.origin['z'], vx=0, vy=0, vz=0)
        mutations.update(self.overrides.get(topic, {}))
        for field, value in mutations.items():
            if value is None:
                text = re.sub(r'^\s+' + re.escape(field) + r':.*\n', '', text, flags=re.M)
            else:
                text, count = re.subn(r'^(\s+' + re.escape(field) + r':\s+).*$',
                                     lambda match: match[1] + str(value), text, flags=re.M)
                assert count == 1, (topic, field)
        return text


def bind_runner(source, job, cli, output):
    """Execute the actual collector call sites, not retyped selection expressions."""
    tree = ast.parse(Path(source).read_text())
    execute = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'execute')
    names = ('topic', 'diagnostics', 'verify_configuration', 'sample')
    functions = [copy.deepcopy(node) for node in execute.body
                 if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(functions) == len(names)
    wrapper = ast.parse('def bound():\n    last_position = None\n    last_position_wall = None\n').body[0]
    wrapper.body += functions + [ast.Return(ast.Tuple([ast.Name(name, ast.Load()) for name in names], ast.Load()))]
    module = ast.fix_missing_locations(ast.Module(body=[wrapper], type_ignores=[]))
    env = dict(run.__dict__)
    env.update(job=job, cli=cli, output=output, proc=Mock(poll=Mock(return_value=None)),
               worker_errors=[], origin=cli.origin, samples=io.StringIO(), bridge_proc=None,
               receipt=Mock(), position_time_us=contract.position_time_us,
               check_active_state=contract.check_active_state)
    exec(compile(module, str(source), 'exec'), env)
    return dict(zip(names, env['bound']())), env


class SelectionTests(unittest.TestCase):
    def test_absent_override_inherits_base_without_mutation(self):
        job = job_for('STA2'); before = copy.deepcopy(job)
        self.assertNotIn('hover_diagnostic_expectations', job)
        for scored in (False, True):
            selected = contract.diagnostic_expectations(job, scored)
            self.assertEqual(selected, {'attitude_sta_status': {}})
            selected['attitude_sta_status']['changed'] = 123
            self.assertEqual(job, before)

    def test_all_four_actual_jobs_keep_existing_selected_requirements(self):
        for job in MANIFEST['jobs']:
            for scored in (False, True):
                old = job.get('hover_diagnostic_expectations', job['diagnostic_expectations']) if scored else job['diagnostic_expectations']
                self.assertEqual(contract.diagnostic_expectations(job, scored), old)

    def test_explicit_empty_null_or_wrong_type_never_means_fallback(self):
        for field in ('diagnostic_expectations', 'hover_diagnostic_expectations'):
            for value in ({}, None, [], '', 0, False):
                for scored in (False, True):
                    job = job_for('STA2'); job[field] = value
                    with self.subTest(field=field, value=value, scored=scored), self.assertRaises(ValueError):
                        contract.diagnostic_expectations(job, scored)

    def test_empty_field_map_is_not_empty_topic_configuration(self):
        self.assertEqual(contract.diagnostic_expectations(job_for('STA2'), True), {'attitude_sta_status': {}})

    def test_invalid_topics_fields_and_nonfinite_requirements_rejected(self):
        for value in ({'': {}}, {'bad/topic': {}}, {5: {}}, {'attitude_sta_status': None},
                      {'attitude_sta_status': []}, {'attitude_sta_status': {'': 0}},
                      {'attitude_sta_status': {'fault': float('nan')}},
                      {'attitude_sta_status': {'fault': float('inf')}},
                      {'attitude_sta_status': {'fault': 10 ** 1000}},
                      {'attitude_sta_status': {'fault': '0'}}):
            job = job_for('STA2'); job['diagnostic_expectations'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                contract.diagnostic_expectations(job)

    def test_manifest_rejects_bad_override_before_runtime(self):
        for value in ({}, None, [], {'attitude_sta_status': None}):
            m = copy.deepcopy(MANIFEST); m['jobs'][1]['hover_diagnostic_expectations'] = value
            with self.subTest(value=value), patch.object(run, 'execute') as execute, self.assertRaises(ValueError):
                contract.validate_manifest(m, 'O001')
            execute.assert_not_called()

    def test_manifest_diagnostic_requirements_cannot_change_between_tasks(self):
        m = copy.deepcopy(MANIFEST)
        m['jobs'][5]['diagnostic_expectations']['attitude_sta_status']['extra'] = 0
        with self.assertRaisesRegex(ValueError, 'diagnostics changed between tasks'):
            contract.validate_manifest(m, 'O001')

    def test_real_frozen_jobs_are_valid_with_absent_sta2_override(self):
        for job in MANIFEST['jobs']:
            self.assertEqual(contract.validate_manifest(MANIFEST, job['id']), job)


class CollectorWiringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.no_process = patch.object(run.subprocess, 'Popen', side_effect=AssertionError('No subprocess permitted'))
        self.no_process.start(); self.addCleanup(self.no_process.stop)

    def bind(self, system, source=None, job=None):
        cli = RecordedCLI(system)
        functions, env = bind_runner(source or HERE / 'run.py', job or job_for(system), cli, self.output)
        return cli, functions, env

    def test_fixture_manifest_fingerprint(self):
        self.assertEqual(hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest(), FIXTURE['manifest_sha256'])

    def test_frozen_runner_reproduces_original_failure_without_simulation(self):
        self.assertEqual(hashlib.sha256(FROZEN.read_bytes()).hexdigest(),
                         MANIFEST['assets'][str(HERE.parent / 'offboard/run.py')])
        cli, f, env = self.bind('STA2', FROZEN)
        f['verify_configuration']('frozen', airborne=True)
        self.assertEqual(json.loads((self.output / 'diagnostics_frozen.json').read_text()), {})
        cli.calls.clear()
        with self.assertRaisesRegex(ValueError, 'diagnostic attitude_sta_status must be a mapping'):
            f['sample']('hover', airborne=True)
        self.assertNotIn(('listener', 'attitude_sta_status', '-n', '1'), cli.calls)

    def test_fixed_sta2_collector_actually_reads_missing_override_topic(self):
        cli, f, env = self.bind('STA2')
        f['verify_configuration']('fixed', airborne=True)
        self.assertIn('attitude_sta_status', json.loads((self.output / 'diagnostics_fixed.json').read_text()))
        cli.calls.clear()
        state = f['sample']('hover', airborne=True)
        self.assertIn('attitude_sta_status', state['diagnostics'])
        self.assertEqual(cli.calls.count(('listener', 'attitude_sta_status', '-n', '1')), 1)

    def test_four_systems_all_stages_read_actual_cli_and_keep_pid_modes(self):
        for job in MANIFEST['jobs']:
            cli, f, env = self.bind(job['system'], job=job)
            task = ['step_up', 'step_down'] if job['task'] == 'position' else ['velocity']
            phases = ['warmup', 'prestream', 'climb', 'recover', 'hover', *task, 'recover', 'descend', 'landing']
            for phase in phases:
                with self.subTest(system=job['system'], task=job['task'], phase=phase):
                    cli.phase = phase; cli.calls.clear()
                    env['origin'] = None if phase == 'warmup' else cli.origin
                    state = f['sample'](phase, airborne=phase in contract.ACTIVE_PHASES)
                    expected = {} if phase == 'warmup' else contract.diagnostic_expectations(job, phase in contract.SCORED_PHASES)
                    actual_reads = [call[1] for call in cli.calls if call[0] == 'listener']
                    self.assertEqual(len(actual_reads), 5 + len(expected))
                    for topic in expected:
                        self.assertEqual(actual_reads.count(topic), 1)
                    if expected:
                        contract._check_diagnostics(state, job, phase in contract.SCORED_PHASES)

    def test_four_systems_parameter_verifier_and_sampler_collect_same_fields(self):
        for system in ('PID', 'STA2', 'RSTA', 'RISTA'):
            for scored in (False, True):
                cli, f, env = self.bind(system)
                f['verify_configuration']('agreement', airborne=scored)
                saved = json.loads((self.output / 'diagnostics_agreement.json').read_text())
                sampled = f['sample']('hover' if scored else 'recover')['diagnostics']
                self.assertEqual(saved, run.diagnostic_json(sampled))

    def test_main_three_system_snapshots_equal_old_collector(self):
        for system in ('PID', 'RSTA', 'RISTA'):
            for scored in (False, True):
                unused, old, unused_env = self.bind(system, FROZEN)
                unused, current, unused_env = self.bind(system)
                phase = 'hover' if scored else 'recover'
                self.assertEqual(run.diagnostic_json(old['sample'](phase)),
                                 run.diagnostic_json(current['sample'](phase)))

    def test_every_missing_topic_rejected_in_both_collection_paths(self):
        for system in ('PID', 'STA2', 'RSTA', 'RISTA'):
            for topic in job_for(system)['diagnostic_expectations']:
                for path in ('sample', 'verify_configuration'):
                    cli, f, env = self.bind(system); cli.missing.add(topic)
                    with self.subTest(system=system, topic=topic, path=path), self.assertRaisesRegex(ValueError, 'Missing native topic'):
                        f[path]('hover', airborne=True)

    def test_missing_or_invalid_timestamp_never_accepted(self):
        for value in (None, 0, -1, 'nan', 'inf', 1.5):
            for path in ('sample', 'verify_configuration'):
                cli, f, env = self.bind('STA2'); cli.overrides['attitude_sta_status'] = {'timestamp': value}
                with self.subTest(value=value, path=path), self.assertRaises(ValueError):
                    f[path]('hover', airborne=True)

    def test_each_scored_mode_axis_fault_field_is_checked_by_collector(self):
        for system in ('PID', 'RSTA', 'RISTA'):
            expected = job_for(system)['hover_diagnostic_expectations']
            for topic, fields in expected.items():
                for field, value in fields.items():
                    for path in ('sample', 'verify_configuration'):
                        cli, f, env = self.bind(system); cli.overrides[topic] = {field: value + 1}
                        with self.subTest(system=system, topic=topic, field=field, path=path), self.assertRaisesRegex(ValueError, 'Wrong diagnostic'):
                            f[path]('hover', airborne=True)

    def test_explicit_invalid_configuration_rejected_before_diagnostic_reads(self):
        for value in ({}, None, [], {'attitude_sta_status': None}):
            job = job_for('STA2'); job['hover_diagnostic_expectations'] = value
            cli, f, env = self.bind('STA2', job=job)
            with self.assertRaises(ValueError):
                f['verify_configuration']('invalid', airborne=True)
            self.assertFalse(any(call[0] == 'listener' for call in cli.calls))

    def test_no_cached_diagnostic_can_mask_later_missing_publication(self):
        cli, f, env = self.bind('STA2')
        f['sample']('recover')
        cli.missing.add('attitude_sta_status')
        with self.assertRaises(ValueError): f['sample']('hover')

    def test_ground_to_active_and_landing_use_phase_specific_requirements(self):
        cli, f, env = self.bind('RISTA')
        cli.overrides['sta_velocity_ctrl_status'] = {'active_axes': 0}
        for phase in ('prestream', 'climb', 'recover', 'descend', 'landing'):
            cli.phase = phase; f['sample'](phase)
        cli.phase = 'hover'
        with self.assertRaisesRegex(ValueError, 'active_axes'): f['sample']('hover')

    def test_failed_batch_and_old_asset_hash_cannot_be_reused(self):
        with self.assertRaisesRegex(ValueError, 'Previous attempt failed'):
            contract.check_order(MANIFEST, 'O003')
        with patch.object(run, 'active_simulators', return_value=[]), patch.object(run.subprocess, 'run') as preflight:
            with self.assertRaisesRegex(ValueError, 'Frozen asset changed'):
                run.check_frozen(MANIFEST, MANIFEST['jobs'][0])
            preflight.assert_not_called()


if __name__ == '__main__':
    unittest.main()
