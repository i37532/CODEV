"""RI03 protocol/receipt negatives. All synthetic JSON lives only under /tmp.

No registration, build, simulator, parameter write, or flight is performed.
The qualification fixtures mock only the separate frozen-asset checker; their
synthetic receipts are never accepted by the actual launch environment.
"""
import ast
import copy
import hashlib
import importlib.util
import math
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_ri03_protocol_test_subject', HERE/'protocol.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
REPO = p.REPO


def save(path, value):
    path = Path(path)
    if Path('/tmp') not in path.resolve().parents:
        raise AssertionError('Synthetic test JSON must stay under /tmp')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(p.json.dumps(value, sort_keys=True, allow_nan=False)+'\n')


class ProtocolDesign(unittest.TestCase):
    def setUp(self):
        self.design = p.design()
        self.protocol = p.load_protocol()

    def test_budget_is_nine_new_attempts_without_historical_credit(self):
        self.assertEqual(p.budget(), dict(maximum_attempts=9, new_matrix_attempts=9,
            total_maximum_attempts=9, historical_attempts=0, required_pairs=6,
            required_replays=9, n_per_algorithm=3, logging_profile=3089))
        self.assertEqual(len(self.design['jobs']), 9)

    def test_only_gate_a_x_is_admitted(self):
        self.assertEqual(p.valid_gate('A'), dict(task='X', axes=1, test=1,
            duration=32, seeds=[81001, 81002, 81003]))
        for gate in ('B', 'C', 'D', 'X', 'H', 'V', '', None, 1):
            for operation in (p.valid_gate, p.budget, p.load_protocol, p.require_execution_authority):
                with self.subTest(gate=gate, operation=operation.__name__), self.assertRaises(ValueError):
                    operation(gate)

    def test_gate_copy_cannot_expand_the_next_request(self):
        gate = p.valid_gate('A'); gate['axes'] = 7; gate['seeds'].append(999999)
        self.assertEqual(p.valid_gate('A')['axes'], 1)
        self.assertEqual(p.valid_gate('A')['seeds'], [81001, 81002, 81003])

    def test_exact_counterbalanced_order_has_pid_first_in_each_block(self):
        expected = ['PID', 'RSTA', 'RISTA', 'PID', 'RISTA', 'RSTA', 'PID', 'RSTA', 'RISTA']
        self.assertEqual([j['candidate'] for j in self.design['jobs']], expected)
        self.assertEqual([j['id'] for j in self.design['jobs']], [f'run{i:03d}' for i in range(1, 10)])
        for block, seed in enumerate((81001, 81002, 81003), 1):
            rows = self.design['jobs'][(block-1)*3:block*3]
            self.assertEqual([r['seed'] for r in rows], [seed]*3)
            self.assertEqual([r['position'] for r in rows], [1, 2, 3])
            self.assertEqual([r['block'] for r in rows], [block]*3)
            self.assertEqual(rows[0]['mode'], 0)

    def test_each_algorithm_has_three_pairs_and_no_esta_group(self):
        counts = {name: sum(j['candidate'] == name for j in self.design['jobs'])
                  for name in ('PID', 'RSTA', 'RISTA', 'ESTA')}
        self.assertEqual(counts, dict(PID=3, RSTA=3, RISTA=3, ESTA=0))
        self.assertEqual(sum(j['mode'] != 0 for j in self.design['jobs']), 6)

    def test_complete_127_parameters_use_exact_ri00_source(self):
        frozen = p.read(p.SOURCE)['full_r03_parameters']
        self.assertEqual(len(frozen), 127)
        self.assertEqual(self.design['fixed_parameters'], frozen)
        for job in self.design['jobs']:
            self.assertEqual(len(job['parameters']), 127)
            self.assertEqual(job['parameters'], {**frozen, 'MPC_VC_MODE': job['mode'],
                'MPC_VC_AXES': job['axes'], 'MPC_VC_DIV': 1, 'MPC_VCT_TEST': 1})

    def test_modes_and_selected_axes_are_exact(self):
        for job in self.design['jobs']:
            self.assertEqual(job['mode'], {'PID': 0, 'RSTA': 3, 'RISTA': 4}[job['candidate']])
            self.assertEqual(job['axes'], 0 if job['mode'] == 0 else 1)
            self.assertEqual((job['gate'], job['task'], job['divisor'], job['main_duration_s']), ('A', 'X', 1, 32))

    def test_startup_is_complete_safe_pid_x_task_not_old_xyz_test8(self):
        startup = self.protocol['startup_overrides']
        for name, value in self.design['jobs'][0]['parameters'].items():
            self.assertEqual(startup[name], value, name)
        self.assertEqual([startup[k] for k in ('MPC_VC_MODE', 'MPC_VC_AXES', 'MPC_VCT_TEST')], [0, 0, 1])
        self.assertEqual(self.protocol['excitation']['parameter'], 1)

    def test_inner_pid_div1_and_old_takeoff_management_are_fixed(self):
        expected = dict(MC_RTC_MODE=0, MC_STA_AXES=0, MC_RTC_DIV=1,
                        MC_RATT_TEST=0, MC_STA_TKO_MGT=0, MPC_VC_DIV=1)
        for job in self.design['jobs']:
            self.assertEqual({k: job['parameters'][k] for k in expected}, expected)

    def test_common_gains_epsilon_limits_and_original_pid_are_frozen(self):
        fixed = self.design['fixed_parameters']
        for axis in 'XYZ':
            expected = (2, 1, .02, 4, 6) if axis == 'Z' else (.5, .1, .01, .4, .8)
            self.assertEqual(tuple(fixed[f'MPC_VC_{field}_{axis}'] for field in ('L1','L2','EPS','NU','A')), expected)
        self.assertEqual([fixed[f'MPC_XY_VEL_{x}_ACC'] for x in 'PID'], [2.16, .48, .24])
        self.assertEqual([fixed[f'MPC_Z_VEL_{x}_ACC'] for x in 'PID'], [4, 2, 0])

    def test_task_duration_settle_observation_and_relative_warmup(self):
        self.assertEqual(self.protocol['excitation']['duration_s'], 32)
        self.assertEqual(self.protocol['excitation']['settle_after_auto_loiter_s'], 12)
        self.assertEqual(self.protocol['height_task']['target_height_m'], 2.5)
        self.assertEqual(self.protocol['height_task']['observation_sim_s'], 90)
        self.assertEqual(self.protocol['height_task']['observation_accepted_duration_s'], [90, 92])
        self.assertEqual(self.protocol['post_logger_warmup_us'], 30000000)
        self.assertEqual(self.protocol['simulation_speed'], 1)

    def test_ax04_numerical_risk_thresholds_are_not_relaxed(self):
        original = p.read(p.OVERRIDES)['protocol_overrides']['pair_gate']
        metadata = {'maximum_candidate_flights_before_reauthorization', 'candidates', 'order', 'window', 'calculation'}
        for name in set(original)-metadata:
            self.assertEqual(self.protocol['pair_gate'][name], original[name], name)
        self.assertEqual(self.protocol['pair_gate']['relative_rmse_limit'], 1.25)
        self.assertEqual(self.protocol['pair_gate']['absolute_velocity_rmse_allowance_m_s'], [.02, .02, .01])
        self.assertEqual(self.protocol['pair_gate']['maximum_candidate_flights_before_reauthorization'], 9)

    def test_diagnostic_thresholds_only_adjust_original_x_duration(self):
        original = p.read(p.OVERRIDES)['protocol_overrides']['diagnostic_gate']
        expected = {**original, 'minimum_excitation_samples': 3190, 'minimum_excitation_span_s': 31.96}
        self.assertEqual(self.protocol['diagnostic_gate'], expected)
        self.assertEqual(expected['raw_dt_domain_s'], [.002, .04])
        self.assertEqual(expected['output_exact_minimum_coverage'], .8)
        self.assertEqual(expected['accepted_output_difference'], 0)

    def test_original_height_reset_and_full_log_rules_are_preserved(self):
        original = p.read(p.OVERRIDES)['protocol_overrides']
        self.assertEqual(self.protocol['height_task'], original['height_task'])
        self.assertEqual(self.protocol['data_gate'], original['data_gate'])
        self.assertEqual(self.protocol['data_gate']['maximum_ulog_dropouts'], 0)
        self.assertEqual(self.protocol['data_gate']['required_rate_sequence_missing'], 0)
        self.assertEqual(self.protocol['height_task']['reposition']['maximum_sends'], 1)

    def test_source_and_authorization_hashes_are_the_exact_frozen_inputs(self):
        self.assertEqual(p.fingerprint(p.SOURCE), p.SOURCE_SHA)
        self.assertEqual(p.fingerprint(p.OVERRIDES), p.OVERRIDES_SHA)
        self.assertEqual(p.fingerprint(p.AUTHORIZATION), p.AUTHORIZATION_SHA)
        self.assertEqual(self.design['entry_head'], 'e7fb67112e4cf605f5ddf362f120c320a64d2cf5')

    def test_changed_parameter_or_threshold_source_is_rejected(self):
        for name in ('SOURCE_SHA', 'OVERRIDES_SHA'):
            with self.subTest(name=name), patch.object(p, name, '0'*64), self.assertRaises(ValueError):
                p.design()

    def test_incomplete_parameter_source_is_rejected(self):
        original_read = p.read
        def incomplete(path):
            value = original_read(path)
            if Path(path) == p.SOURCE:
                value['full_r03_parameters'].pop('MPC_VC_EPS_X')
            return value
        with patch.object(p, 'read', side_effect=incomplete), self.assertRaises(ValueError):
            p.design()


class TemporaryRegistration(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='ri03_protocol_test_', dir='/tmp')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.stage = self.root/'stage'; self.stage.mkdir()
        self.data_root = self.root/'evidence'
        self.patch_here = patch.object(p, 'HERE', self.stage); self.patch_here.start(); self.addCleanup(self.patch_here.stop)
        self.patch_data = patch.object(p, 'DATA_ROOT', self.data_root); self.patch_data.start(); self.addCleanup(self.patch_data.stop)
        self.design = p.design()
        self.outcomes = [{k: j[k] for k in ('id','gate','task','seed','candidate','mode','axes')} |
            {'status': 'unattempted'} for j in self.design['jobs']]
        save(self.stage/'execution.json', self.design)
        save(self.stage/'manifest.json', self.design['jobs'])
        save(self.stage/'outcomes_unattempted.json', self.outcomes)


class RegisteredManifest(TemporaryRegistration):
    def test_exact_temporary_manifest_and_authority_pass(self):
        self.assertTrue(p.validate_manifest())
        receipt = p.require_execution_authority('A')
        self.assertTrue(receipt['approved']); self.assertEqual(receipt['maximum_attempts'], 9)
        self.assertEqual(receipt['authorization_sha256'], p.AUTHORIZATION_SHA)

    def test_changed_authorization_hash_refuses_even_valid_manifest(self):
        with patch.object(p, 'AUTHORIZATION_SHA', '0'*64), self.assertRaises(PermissionError):
            p.require_execution_authority('A')

    def test_mutated_execution_budget_order_mode_axes_test_and_parameter_are_rejected(self):
        changes = [lambda d: d.update(maximum_attempts=10),
            lambda d: d['jobs'].reverse(), lambda d: d['jobs'][0].update(mode=4),
            lambda d: d['jobs'][2].update(axes=7),
            lambda d: d['jobs'][2]['parameters'].update(MPC_VCT_TEST=8),
            lambda d: d['jobs'][2]['parameters'].pop('MPC_USE_HTE')]
        for mutate in changes:
            changed = copy.deepcopy(self.design); mutate(changed)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                p.validate_manifest(changed)

    def test_job_manifest_cannot_omit_duplicate_reorder_or_expand(self):
        jobs = self.design['jobs']
        for changed in (jobs[:-1], jobs+[jobs[-1]], list(reversed(jobs)), [jobs[0]]+jobs[:-1]):
            save(self.stage/'manifest.json', changed)
            with self.subTest(jobs=len(changed)), self.assertRaises(ValueError):
                p.validate_manifest()

    def test_initial_outcomes_cannot_be_claimed_as_attempted_or_accepted(self):
        for status in ('attempted', 'accepted', 'failed'):
            changed = copy.deepcopy(self.outcomes); changed[0]['status'] = status
            save(self.stage/'outcomes_unattempted.json', changed)
            with self.subTest(status=status), self.assertRaises(ValueError):
                p.validate_manifest()

    def test_prepare_refuses_existing_registration_before_any_history_scan(self):
        with patch.object(p, 'fresh_seeds') as history, self.assertRaises(ValueError):
            p.prepare()
        history.assert_not_called()


class Qualification(TemporaryRegistration):
    def setUp(self):
        super().setUp()
        self.head = 'a'*40; self.firmware = 'b'*64
        save(self.stage/'gates/A/frozen.json', {'synthetic_fixture_only': True})
        self.path = self.data_root/'A/qualification/evidence.json'
        self.path.parent.mkdir(parents=True)
        self.log = self.path.parent/'actual_log.json'
        save(self.log, {'synthetic_fixture_only': True})
        self.freeze = SimpleNamespace(archive_check=Mock(), check=Mock())
        original_load = p.load_file
        def load(name, path):
            return self.freeze if Path(path) == self.stage/'freeze.py' else original_load(name, path)
        self.loader = patch.object(p, 'load_file', side_effect=load); self.loader.start(); self.addCleanup(self.loader.stop)
        self.q = {**p.qualification_binding('A', self.head, self.firmware),
            'success': True, 'clean': True, 'approved': True,
            'counts': {'cpp_unique_tests': p.MIN_CPP, 'python_tests': p.MIN_PYTHON},
            'cpp_test_targets': sorted(p.REQUIRED_TARGETS),
            'commands': [dict(name=name, exit_code=0) for name in sorted(p.REQUIRED_TARGETS)],
            'evidence_files': {str(self.log): p.fingerprint(self.log)}}
        self.write(self.q)

    def write(self, value):
        save(self.path, value)
        save(self.path.parent/'authorization.json', p.authorization_binding(value, self.path))

    def test_complete_synthetic_receipt_passes_only_with_mocked_freeze(self):
        self.assertEqual(p.archive_qualification('A', self.head, self.path), self.q)
        self.freeze.archive_check.assert_called_once_with('A', self.head, self.q['frozen_sha256'])

    def test_required_targets_include_actual_waveform_and_every_control_layer(self):
        required = {'unit-StaVelocityProtection', 'unit-RegularizedIstaNonSitl',
            'unit-RegularizedIstaPosition', 'unit-RegularizedIstaProtection',
            'unit-RegularizedIstaRegression', 'unit-RegularizedIstaVelocityControl',
            'functional-RegularizedIstaVelocityModule', 'functional-RegularizedIstaVelocityParam',
            'unit-PositionControl', 'unit-ControlMath', 'unit-Takeoff', 'unit-RateControl',
            'functional-VehicleIMU', 'functional-EKF2Selector', 'functional-EKF2SelectorTiming',
            'functional-EstimatorDiagnosticTopics'}
        self.assertTrue(required.issubset(p.REQUIRED_TARGETS), required-p.REQUIRED_TARGETS)

    def test_missing_any_required_target_is_rejected(self):
        for target in p.REQUIRED_TARGETS:
            changed = copy.deepcopy(self.q); changed['cpp_test_targets'].remove(target); self.write(changed)
            with self.subTest(target=target), self.assertRaises(ValueError):
                p.archive_qualification('A', self.head, self.path)

    def test_declared_but_unexecuted_required_target_is_rejected(self):
        for target in p.REQUIRED_TARGETS:
            changed = copy.deepcopy(self.q)
            changed['commands'] = [c for c in changed['commands'] if c['name'] != target]; self.write(changed)
            with self.subTest(target=target), self.assertRaises(ValueError):
                p.archive_qualification('A', self.head, self.path)

    def test_missing_zero_false_noninteger_or_insufficient_counts_are_rejected(self):
        for key, minimum in (('cpp_unique_tests', p.MIN_CPP), ('python_tests', p.MIN_PYTHON)):
            for value in (None, 0, False, True, minimum-1, float(minimum), str(minimum)):
                changed = copy.deepcopy(self.q)
                if value is None:
                    changed['counts'].pop(key)
                else:
                    changed['counts'][key] = value
                self.write(changed)
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    p.archive_qualification('A', self.head, self.path)

    def test_failed_or_missing_commands_are_rejected(self):
        for commands in ([], [dict(name='only_failure', exit_code=1)]):
            changed = copy.deepcopy(self.q); changed['commands'] = commands; self.write(changed)
            with self.subTest(commands=commands), self.assertRaises(ValueError):
                p.archive_qualification('A', self.head, self.path)

    def test_wrong_identity_authority_budget_or_success_is_rejected(self):
        for field, wrong in (('stage','RI02'), ('revision','ri02'), ('source_head','c'*40),
                ('execution_sha256','d'*64), ('frozen_sha256','e'*64), ('authorization_sha256','f'*64),
                ('maximum_attempts',10), ('success',False), ('clean',False), ('approved',False), ('new_flights',1)):
            changed = copy.deepcopy(self.q); changed[field] = wrong; self.write(changed)
            with self.subTest(field=field), self.assertRaises(ValueError):
                p.archive_qualification('A', self.head, self.path)

    def test_foreign_qualification_directory_is_rejected(self):
        foreign = self.root/'foreign/evidence.json'; save(foreign, self.q)
        with self.assertRaises(ValueError):
            p.archive_qualification('A', self.head, foreign)

    def test_missing_or_changed_evidence_file_is_rejected(self):
        changed = copy.deepcopy(self.q); changed['evidence_files'] = {}; self.write(changed)
        with self.assertRaises(ValueError): p.archive_qualification('A', self.head, self.path)
        self.write(self.q); save(self.log, {'tampered': True})
        with self.assertRaises(ValueError): p.archive_qualification('A', self.head, self.path)

    def test_nonlocal_evidence_is_rejected_even_with_matching_digest(self):
        foreign = self.root/'foreign.json'; save(foreign, {'not_local': True})
        changed = copy.deepcopy(self.q); changed['evidence_files'] = {str(foreign): p.fingerprint(foreign)}; self.write(changed)
        with self.assertRaises(ValueError): p.archive_qualification('A', self.head, self.path)

    def test_receipt_binds_exact_evidence_bytes(self):
        receipt = p.read(self.path.parent/'authorization.json'); receipt['qualification_sha256'] = '0'*64
        save(self.path.parent/'authorization.json', receipt)
        with self.assertRaises(ValueError): p.archive_qualification('A', self.head, self.path)

    def test_dirty_wrong_head_wrong_branch_and_binary_cannot_launch(self):
        cases = [('dirty', self.head, 'research/ista-velocity-regularized', self.firmware),
            ('', 'c'*40, 'research/ista-velocity-regularized', self.firmware),
            ('', self.head, 'main', self.firmware), ('', self.head, 'research/ista-velocity-regularized', 'c'*64)]
        real_fingerprint = p.fingerprint
        for status, head, branch, firmware in cases:
            def git(*args):
                return {('status','--porcelain'):status, ('rev-parse','HEAD'):head,
                        ('branch','--show-current'):branch}[args]
            def fingerprint(path):
                return firmware if Path(path) == REPO/'build/px4_sitl_default/bin/px4' else real_fingerprint(path)
            with self.subTest(status=status, head=head, branch=branch), patch.object(p, 'git', side_effect=git), \
                    patch.object(p, 'fingerprint', side_effect=fingerprint), self.assertRaises(ValueError):
                p.require_qualification('A', self.head, self.path)
        self.freeze.check.assert_not_called()


class ExistingWaveformAndModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.targets = p.load_file('_ri03_original_x_waveform', REPO/'research/sta-velocity-control/regularized_sta/r03/targets.py')
        cls.model = p.load_file('_ri03_existing_independent_model', HERE.parent/'ri01/model/check.py')
        cls.np = cls.targets.np

    def test_original_x_waveform_has_exact_window_endpoints_and_no_extra_axes(self):
        np = self.np
        points = np.array([-1., 0., 32., 33.])
        self.assertTrue(np.array_equal(self.targets.waveform(points, .2), np.zeros(4)))
        self.assertEqual(self.targets.SPECS['A'], ('X', 1, 1, 32))
        self.assertEqual(p.valid_gate('A')['test'], self.targets.SPECS['A'][2])

    def test_original_x_waveform_is_bounded_smooth_and_zero_integral(self):
        np = self.np; t = np.linspace(0., 32., 32001); u = self.targets.waveform(t, .2)
        self.assertLessEqual(float(np.max(np.abs(u))), .2)
        self.assertAlmostEqual(float(np.trapz(u, t)), 0., delta=1e-12)
        self.assertLess(float(np.max(np.abs(u+self.targets.waveform(32.-t, .2)))), 2e-15)
        near = self.targets.waveform(np.array([1e-4, 32.-1e-4]), .2)
        self.assertLess(float(np.max(np.abs(near/1e-4))), 1e-8)

    def test_actual_ri00_cadence_is_preserved_for_independent_model(self):
        cadence = p.read(self.model.CADENCE); delta = cadence['delta_us']
        self.assertEqual(len(delta), 6399); self.assertEqual(set(delta), {8000, 12000})
        digest = hashlib.sha256(struct.pack('<'+'q'*len(delta), *delta)).hexdigest()
        self.assertEqual(digest, cadence['delta_sha256'])
        self.assertEqual(digest, '1bec48156a508a1834849738072437dad847f75d37e47f6bd3ad7f1cd867885b')

    def test_ri01_independent_bisection_and_existing_lag_object_keep_ned_x_sign(self):
        k1, k2, eps, _ = self.model.GAINS['XY']
        for h in (.008, .012):
            for target in (-.03, .03):
                result = self.model.oracle(-target, h, k1, k2, eps, 0.)
                self.assertGreater(result[4]*target, 0.)
                self.assertLess(self.model.residual(result, k1, k2, eps), 2e-12)
                velocity, first, second = self.model.lag_step(0., 0., 0., result[4], 0., h)
                self.assertGreater(velocity*target, 0.); self.assertGreater(first*target, 0.)
                self.assertGreater(second*target, 0.); self.assertLess(abs(second), abs(first))

    def test_qualification_reuses_full_ri01_model_without_running_it_inside_this_test(self):
        tree = ast.parse((HERE/'verify.py').read_text())
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == 'run'
                 and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == 'model_reference']
        self.assertEqual(len(calls), 1)
        constants = [node.value for node in ast.walk(calls[0]) if isinstance(node, ast.Constant)]
        self.assertIn('ri01/model/check.py', constants); self.assertIn('--output', constants)
        self.assertEqual(self.model.GAINS['XY'], (.5, .1, .01, .4))
        self.assertIn('two_stage_lag', {row['kind'] for row in self.model.scenario_list()})
        self.assertIn('lag_and_noise', {row['kind'] for row in self.model.scenario_list()})


if __name__ == '__main__':
    unittest.main(verbosity=2)
