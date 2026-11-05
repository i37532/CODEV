#!/usr/bin/env python3
"""RI03 offline integration fixtures. No simulator or real EEPROM access."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import numpy as np

import bindings
analyzer, runner, replay = [bindings.local(name) for name in ('analyzer', 'runner', 'replay')]


def old_fixtures():
    names = ('dependencies', 'configuration', 'analyzer', 'full_chain', 'parameters', 'run', 'replay')
    previous = {name: sys.modules.get(name) for name in names}
    try:
        for name in names:
            module = getattr(bindings.KERNEL, name, None)
            sys.modules[name] = module or bindings.load('fixture_' + name, bindings.RI02 / (name + '.py'))
        return bindings.load('ri02_fixtures', bindings.RI02 / 'test_tools.py')
    finally:
        for name, value in previous.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


FIXTURES = old_fixtures()


def job(mode=4, index=1, seed=71):
    result = bindings.KERNEL.configuration.candidate(mode, 1 if mode else 0)
    result.update(id=f'run{index:03d}', revision='ri03', gate='A', task='X', seed=seed,
        candidate={0: 'PID', 3: 'RSTA', 4: 'RISTA'}[mode], divisor=1, main_duration_s=32)
    result['parameters']['MPC_VCT_TEST'] = 1
    return result


def protocol(root='/tmp/ri03-offline-placeholder'):
    jobs = [job(mode, i * 3 + n + 1, 71 + i) for i in range(3) for n, mode in enumerate((0, 3, 4))]
    return dict(revision='ri03', stage='RI03-A', gate='A', maximum_attempts=9,
        new_matrix_attempts=9, total_maximum_attempts=9, historical_attempts=0, jobs=jobs,
        artifacts=dict(new_run_root=str(Path(root) / 'A/batch01')))


def metrics(j):
    return dict(accepted=True, job=copy.deepcopy(j), binding=dict(source_head='a' * 40),
        candidate_numeric_binding=bindings.source_binding(), handoff_dependency_binding=bindings.FINAL.HANDOFF_BINDING,
        position_clock_binding=bindings.FINAL.CLOCK_BINDING, prearm_preparation=dict(valid=True),
        post_logger_warmup=dict(valid=True), diagnostic=dict(error=dict(rmse=[.01] * 3),
        windows={w: dict(error=dict(rmse=[.01] * 3)) for w in ('first_half', 'second_half')}),
        position_rmse=[.02] * 3, yaw_rmse=.01)


def fixture():
    x, q, _, start, end = FIXTURES.FullChainTests().fixture()
    return x, q, job(), start, end


class BindingTests(unittest.TestCase):
    def test_private_new_full_science_has_actual_mode4_math(self):
        current = analyzer.full_analysis(lambda *args: {})
        original = bindings.FINAL.full_analysis(lambda *args: {}, lambda *args: None)
        self.assertIs(current.__globals__['check_components'], analyzer.components)
        for name in ('check_health', 'check_complete', 'height_evidence', 'exact_output_match', 'r02', 'ULog'):
            self.assertIs(current.__globals__[name], original.__globals__[name])
        self.assertIsNot(original.__globals__['check_components'], analyzer.components)
        self.assertIsNot(bindings.KERNEL.analyzer, analyzer)
        self.assertIsNot(bindings.KERNEL.full_chain.analyzer, analyzer)

    def test_actual_flight_body_unchanged_new_identity_and_authority_only(self):
        self.assertIs(runner.flight_main.__code__, bindings.OLD_RUNNER.flight_main.__code__)
        self.assertIs(runner.flight_main.__globals__['local_module'], runner.local_module)
        self.assertEqual(Path(runner.flight_main.__globals__['__file__']), Path(runner.__file__))
        self.assertNotEqual(runner.flight_main.__globals__['__file__'], bindings.OLD_RUNNER.flight_main.__globals__['__file__'])
        self.assertIs(runner.flight_main.__globals__['ram_log'], bindings.RAM_LOG)
        self.assertTrue(callable(bindings.RAM_LOG.release_archived))

    def test_existing_chain_class_composition_preserved(self):
        current = runner.execution_checks_class()
        inherited = bindings.OLD_RUNNER.execution_checks_class()
        self.assertEqual([c.__name__ for c in current.__mro__[1:]], [c.__name__ for c in inherited.__mro__])
        for name in ('relative_warmup', 'prearm', 'wait_landed'):
            if hasattr(inherited, name):
                self.assertIs(getattr(current, name).__code__, getattr(inherited, name).__code__)

    def test_actual_bound_mode4_valid_fixture(self):
        x, q, j, start, end = fixture()
        result, _, _ = analyzer.components(x, q, j, start, end, True)
        self.assertTrue(result['cadence']['component_valid'])
        self.assertFalse(result['cadence']['flight_accepted'])

    def test_pid_and_rsta_delegation_unchanged(self):
        for mode in (0, 3):
            called = []
            with patch.object(bindings.FINAL, '_components', side_effect=lambda *args: called.append(args) or 'old'):
                j = job(mode)
                self.assertEqual(analyzer.components({}, {}, j, 10, 20), 'old')
                self.assertEqual(called[0][2]['mode'], mode)


class ComponentNegativeTests(unittest.TestCase):
    pass


def negative_component(case):
    def test(self):
        x, q, j, start, end = fixture()
        k = 100
        if case == 'wrong_mode': x['effective_mode'][k] = q['effective_mode'][k] = 3
        elif case == 'wrong_axes': x['effective_axes'][k] = q['effective_axes'][k] = 7
        elif case == 'wrong_inner': x['inner_mode'][k] = 3
        elif case == 'inner_stale': x['inner_timestamp'][k] = 0
        elif case == 'sample_duplicate': x['timestamp_sample'][k] = x['timestamp_sample'][k - 1]
        elif case == 'publication_backward': x['timestamp'][k] = x['timestamp'][k - 1] - 1
        elif case == 'missing_selection': q = {key: np.delete(value, k) for key, value in q.items()}
        elif case == 'same_time_ambiguous': q['timestamp'][k] = q['timestamp'][k - 1]
        elif case == 'missing_update': q['control_seq'][k:] += 1
        elif case == 'no_admission': x['active_axes'][k] = 0
        elif case == 'missing_commit': q['ri_commit_axes'][k] = 0
        elif case == 'wrong_p': q['ri_p[0]'][k] += .1
        elif case == 'wrong_nu_candidate': q['ri_nu_candidate[0]'][k] += .1
        elif case == 'old_nu_current_output': q['ri_a_ideal[0]'][k] += x['nu_before[0]'][k] - x['nu_ideal[0]'][k]
        elif case == 'wrong_applied': q['ri_a_applied[0]'][k] += .1
        elif case == 'wrong_published': q['ri_acc_published[0]'][k] += .1
        elif case == 'wrong_proxy': x['a_proxy[0]'][k] += .1
        elif case == 'ff_twice': x['a_req[0]'][k] += x['a_ff[0]'][k]
        elif case == 'wrong_sample_h': q['ri_h'][k] = .02
        elif case == 'clamped_legacy_h': q['h'][k] = .02
        elif case == 'zero_cost': q['path_ns'][k] = 0
        elif case == 'false_valid_candidate': q['ri_valid'][k] = 0
        elif case == 'selected_nan': q['ri_p[0]'][k] = np.nan
        elif case == 'unselected_state': q['ri_nu_candidate[1]'][k] = 0
        elif case == 'nonzero_interval': q['interval_pos'][k] = 1
        elif case == 'reset_during_steady': x['reset_bits'][k] = 1
        elif case == 'dt_long_pause': x['raw_dt'][k] = q['ri_h'][k] = .5
        elif case == 'wrong_epsilon': q['eps_eff[0]'][k] = .02
        elif case == 'unselected_epsilon': q['eps_eff[1]'][k] = .01
        elif case == 'zero_generation': q['sta_gen'][k] = 0
        else: raise AssertionError(case)
        with self.assertRaises((ValueError, RuntimeError)):
            analyzer.components(x, q, j, start, end, True)
    return test


for _case in ('wrong_mode', 'wrong_axes', 'wrong_inner', 'inner_stale', 'sample_duplicate',
    'publication_backward', 'missing_selection', 'same_time_ambiguous', 'missing_update',
    'no_admission', 'missing_commit', 'wrong_p', 'wrong_nu_candidate', 'old_nu_current_output',
    'wrong_applied', 'wrong_published', 'wrong_proxy', 'ff_twice', 'wrong_sample_h', 'clamped_legacy_h',
    'zero_cost', 'false_valid_candidate', 'selected_nan', 'unselected_state', 'nonzero_interval',
    'reset_during_steady', 'dt_long_pause', 'wrong_epsilon', 'unselected_epsilon', 'zero_generation'):
    setattr(ComponentNegativeTests, 'test_' + _case, negative_component(_case))


class ScopeTests(unittest.TestCase):
    def test_nine_exact_pairs(self):
        runner.validate_scope(protocol())
        for j in protocol()['jobs']: analyzer.validate_job(j)

    def test_other_axes_and_modes_not_unlocked(self):
        for key, values in dict(mode=(1, 2, 5, True, 4.), axes=(2, 3, 4, 7), gate=('B', 'C', 'D'),
                                divisor=(2, 4), revision=('ri02', 'revision11')).items():
            for value in values:
                j = job(); j[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError): analyzer.validate_job(j)

    def test_parameter_mode_and_inner_mismatch_rejected(self):
        for name, value in dict(MPC_VC_MODE=3, MPC_VC_AXES=3, MPC_VC_DIV=2, MC_RTC_MODE=1,
                                MC_STA_AXES=1, MC_RTC_DIV=2, MC_RATT_TEST=1, MPC_VCT_TEST=8).items():
            j = job(); j['parameters'][name] = value
            with self.subTest(name=name), self.assertRaises(ValueError): analyzer.validate_job(j)

    def test_extra_budget_old_budget_duplicate_and_old_esta_rejected(self):
        for change in ('extra', 'old', 'duplicate', 'esta', 'order', 'pid_first'):
            p = protocol()
            if change == 'extra': p['maximum_attempts'] = 10
            elif change == 'old': p['historical_attempts'] = 97
            elif change == 'duplicate': p['jobs'][1] = copy.deepcopy(p['jobs'][0])
            elif change == 'esta': p['jobs'][1]['mode'] = 1
            elif change == 'order': p['jobs'][0], p['jobs'][1] = p['jobs'][1], p['jobs'][0]
            else: p['jobs'][0]['mode'] = 4
            with self.subTest(change=change), self.assertRaises((ValueError, RuntimeError)): runner.validate_scope(p)

    def test_default_dry_run_never_calls_execution(self):
        fake = types.SimpleNamespace(validate_manifest=lambda: None, load_protocol=lambda gate: protocol())
        with patch.object(runner, 'api', return_value=fake), patch.object(runner, 'execute_gate') as execute, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main([]), 0)
            execute.assert_not_called()

    def test_explicit_execute_needs_full_sha_and_qualification(self):
        fake = types.SimpleNamespace(validate_manifest=lambda: None, load_protocol=lambda gate: protocol())
        for argv in (['--execute'], ['--execute', '--source-head', 'a' * 40], ['--execute', '--source-head', 'short', '--qualification', '/tmp/q']):
            with patch.object(runner, 'api', return_value=fake), patch.object(runner, 'execute_gate') as execute, contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(RuntimeError): runner.main(argv)
                execute.assert_not_called()

    def test_noncanonical_runtime_protocol_rejected_before_mutation(self):
        canonical = protocol(); altered = copy.deepcopy(canonical); altered['jobs'][1]['parameters']['MPC_VC_L1_X'] += .1
        fake = types.SimpleNamespace(require_execution_authority=lambda gate: None, load_protocol=lambda gate: canonical)
        with patch.object(runner, 'api', return_value=fake), patch.object(runner, '_execute_gate') as execute:
            with self.assertRaisesRegex(RuntimeError, 'canonical'): runner.execute_gate(altered, 'a' * 40, Path('/tmp/q'))
            execute.assert_not_called()


class ScheduleTests(unittest.TestCase):
    def schedule(self, fail_at=None, rejected_at=None, risk_at=None):
        p, ledger, calls, events = protocol(), dict(attempts=[], pairs=[], success=False), [], []
        def perform(j, index):
            calls.append(index)
            if index == fail_at: raise RuntimeError('synthetic backend error before takeoff')
            result = metrics(j)
            if index == rejected_at: result['accepted'] = False
            if index == risk_at: result['yaw_rmse'] = 1.
            return result, dict(metrics_sha256='b' * 64)
        return p, ledger, calls, events, perform

    def test_success_nine_attempts_six_pairs(self):
        p, ledger, calls, events, perform = self.schedule()
        runner.run_ordered(p, perform, analyzer.compare, ledger, events.append)
        self.assertEqual(calls, list(range(1, 10))); self.assertTrue(ledger['success'])
        self.assertEqual(len(ledger['pairs']), 6); self.assertEqual(ledger['unattempted'], [])

    def test_first_backend_failure_consumes_attempt_and_stops(self):
        p, ledger, calls, events, perform = self.schedule(fail_at=1)
        with self.assertRaises(RuntimeError): runner.run_ordered(p, perform, analyzer.compare, ledger, events.append)
        self.assertEqual(calls, [1]); self.assertEqual(len(ledger['attempts']), 1)
        self.assertEqual(ledger['attempts'][0]['status'], 'failed'); self.assertEqual(len(ledger['unattempted']), 8)

    def test_third_invalid_log_stops_no_replacement(self):
        p, ledger, calls, events, perform = self.schedule(rejected_at=3)
        with self.assertRaises(RuntimeError): runner.run_ordered(p, perform, analyzer.compare, ledger, events.append)
        self.assertEqual(calls, [1, 2, 3]); self.assertEqual(len(ledger['unattempted']), 6)

    def test_pair_failure_stops_before_next_seed(self):
        p, ledger, calls, events, perform = self.schedule(risk_at=3)
        with self.assertRaises(RuntimeError): runner.run_ordered(p, perform, analyzer.compare, ledger, events.append)
        self.assertEqual(calls, [1, 2, 3]); self.assertFalse(ledger['success'])
        self.assertFalse(ledger['attempts'][-1]['paired_checks_at_stop'][0]['accepted'])

    def test_admission_failure_latches_and_no_restart(self):
        p = protocol(); a = runner.Admission(p, analyzer.compare)
        with self.assertRaises(RuntimeError): a.accept(p['jobs'][0], dict(accepted=False))
        with self.assertRaises(RuntimeError): a.before(p['jobs'][0])


class ComparisonTests(unittest.TestCase):
    def test_two_independent_decisions_exact(self):
        for mode in (3, 4):
            p, c = metrics(job(0)), metrics(job(mode))
            self.assertEqual(analyzer.compare(p, c), replay.paired_decision(p, c))
            self.assertEqual(len(analyzer.compare(p, c)['checks']), 13)

    def test_inherited_risk_need_not_win(self):
        p, c = metrics(job(0)), metrics(job())
        c['yaw_rmse'] = .02
        self.assertTrue(analyzer.compare(p, c)['accepted'])
        c['yaw_rmse'] = .1
        self.assertFalse(analyzer.compare(p, c)['accepted'])

    def test_nonfinite_negative_or_false_zero_metrics_rejected(self):
        for value in (float('nan'), float('inf'), -.01, False, '0'):
            p, c = metrics(job(0)), metrics(job()); c['diagnostic']['error']['rmse'][0] = value
            for function in (analyzer.compare, replay.paired_decision):
                with self.subTest(value=value, function=function.__name__), self.assertRaises(ValueError): function(p, c)

    def test_bad_pair_metadata_rejected(self):
        for case in ('seed', 'binding', 'parameters', 'prearm', 'warmup', 'numeric', 'mode'):
            p, c = metrics(job(0)), metrics(job())
            if case == 'seed': c['job']['seed'] += 1
            elif case == 'binding': c['binding']['source_head'] = 'b' * 40
            elif case == 'parameters': c['job']['parameters']['MPC_VC_L1_X'] += .1
            elif case == 'prearm': c['prearm_preparation']['valid'] = False
            elif case == 'warmup': c['post_logger_warmup']['valid'] = False
            elif case == 'numeric': c['candidate_numeric_binding']['implicit_mode'] = 3
            else: c['job']['mode'] = 1
            with self.subTest(case=case), self.assertRaises(ValueError): analyzer.compare(p, c)

    def test_exact_retains_json_type_difference(self):
        self.assertFalse(bindings.exact({'a': 1}, {'a': 1.}))
        self.assertFalse(bindings.exact({'a': [1, 2]}, {'a': [2, 1]}))


class ConfigurationTests(unittest.TestCase):
    def checks(self, mode=4):
        cls = runner.execution_checks_class(); checks = object.__new__(cls)
        checks.job = job(mode); checks.expected = checks.job['parameters']
        return checks

    def selection(self, mode=4):
        return dict(requested_mode=mode, effective_mode=mode, requested_axes=int(bool(mode)),
            effective_axes=int(bool(mode)), pending=0, reject=0, div_req=1, div_eff=1, div_pending=0,
            div_reject=0, control_fault=0, variant_req=mode, variant_eff=mode, sta_pending=0,
            sta_gen=int(bool(mode)), sta_reject=int(not mode), ri_version=1)

    def test_real_mode4_selection_not_old_rejected_mode(self):
        c = self.checks(); c.selection(self.selection())
        for name, value in dict(effective_mode=0, effective_axes=0, reject=2, sta_reject=1, sta_gen=0,
                                div_eff=2, variant_eff=3, pending=1).items():
            q = self.selection(); q[name] = value
            with self.subTest(name=name), self.assertRaises(RuntimeError): c.selection(q)

    def test_live_configuration_epsilon_and_actual_inner_pid(self):
        for mode in (0, 3, 4):
            c = self.checks(mode); q = self.selection(mode)
            requested = [c.expected['MPC_VC_EPS_' + suffix] for suffix in 'XYZ']
            values = dict(eps_req=requested, eps_eff=[requested[0] if mode else np.nan, np.nan, np.nan])
            inner = dict(requested_mode=0, requested_axes=0, effective_mode=0, effective_axes=0,
                div_req=1, div_eff=1, fault=0, abort_requested=0, termination=0)
            with tempfile.TemporaryDirectory() as tmp, patch.object(bindings.OLD_RUNNER, 'scalars', return_value=q), \
                    patch.object(runner.historical.base, 'arrays', side_effect=lambda raw, key: values[key]):
                c.configuration(lambda *args: 'read-only mocked listener', lambda name: inner, Path(tmp), 'prearm')
                values['eps_eff'][1] = .01
                with self.assertRaisesRegex(RuntimeError, 'Unselected'): c.configuration(lambda *args: '', lambda name: inner, Path(tmp), 'prearm')
                values['eps_eff'][1] = np.nan; inner['effective_mode'] = 1
                with self.assertRaises(RuntimeError): c.configuration(lambda *args: '', lambda name: inner, Path(tmp), 'prearm')


class ParameterTransactionTests(unittest.TestCase):
    def backend(self, failure):
        with tempfile.TemporaryDirectory(prefix='ri03-offline-') as tmp:
            root = Path(tmp); rootfs = root / 'rootfs'; (rootfs / 'eeprom').mkdir(parents=True)
            binary = root / 'bin'; binary.mkdir(); (binary / 'px4').write_bytes(b'fake qualification binary; not executable')
            p = protocol(root); p.update(startup_overrides=copy.deepcopy(p['jobs'][0]['parameters']),
                plugins=str(root / 'plugins'), execution_path=str(root / 'execution.json'), config_dir=str(root / 'config'))
            param = rootfs / 'eeprom/parameters_10016'
            original_values = {**p['jobs'][0]['parameters'], 'SDLOG_PROFILE': 1, 'UNRELATED_USER': 7.5}
            table = {name: 'Int32' if type(value) is int else 'Float' for name, value in original_values.items()}
            original = runner.historical.encode_bson(original_values, table); param.write_bytes(original)
            definitions = root / 'build/px4_sitl_default/parameters.json'; definitions.parent.mkdir(parents=True)
            bindings.save(definitions, dict(parameters=[dict(name=k, type=table[k], default=v) for k, v in original_values.items()]))
            qualification = root / 'qualification/evidence.json'; qualification.parent.mkdir()
            qualified = dict(firmware_sha256=bindings.digest(binary / 'px4'))
            bindings.save(qualification, qualified); bindings.save(qualification.parent / 'authorization.json', dict(approved=True))
            fake_api = types.SimpleNamespace(require_qualification=lambda *args: qualified)
            calls = []
            class FakeChecks:
                def __init__(self, proto, expected, j, *args):
                    self.job = j; self.log_root = root / 'not-a-real-tmpfs-log'
            def fake_flight(run, checks, scenario):
                calls.append(checks.job['id']); run.mkdir()
                current = runner.historical.persisted_bson(param.read_bytes())
                self.assertEqual(current['UNRELATED_USER'], 7.5); self.assertEqual(current['SDLOG_PROFILE'], 3089)
                self.assertEqual(current['MPC_VC_MODE'], checks.job['mode'])
                if failure == 'backend': raise RuntimeError('synthetic startup failure')
                if failure == 'write': param.write_bytes(b'mutated by mocked PX4')
            def fake_analyze(run, proto, j):
                self.assertEqual(param.read_bytes(), original)
                result = metrics(j)
                if failure == 'analysis': result['accepted'] = False
                bindings.save(run / 'r03_metrics.json', result)
                return result
            safe_restore = bindings.clone(bindings.OLD_RUNNER.restore_parameters, active_simulators=lambda: [])
            fake_git = lambda *args: '' if args[0] == 'status' else 'a' * 40
            fake_noise = lambda run: np.array([float(p['jobs'][int(run.name[3:]) - 1]['seed'])])
            with contextlib.ExitStack() as stack:
                for name, value in dict(ROOTFS=rootfs, BIN=binary, REPO=root, api=lambda: fake_api,
                    active_simulators=lambda: [], restore_parameters=safe_restore,
                    execution_checks_class=lambda: FakeChecks).items(): stack.enter_context(patch.object(runner, name, value))
                stack.enter_context(patch.object(runner, 'precheck', return_value=(qualified, dict(control_parameters=original_values), dict(accepted=True))))
                stack.enter_context(patch.object(runner.historical, 'git', side_effect=fake_git))
                stack.enter_context(patch.object(runner.historical, 'noise_prefix', side_effect=fake_noise))
                stack.enter_context(patch.object(runner.historical.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=30 * 1024**3)))
                stack.enter_context(patch.object(bindings.RAM_LOG, 'release_archived'))
                if failure in ('backend', 'analysis'):
                    with self.assertRaises(RuntimeError): runner._execute_gate(p, 'a' * 40, qualification, single_flight=fake_flight, analyze=fake_analyze, compare=analyzer.compare)
                else:
                    self.assertTrue(runner._execute_gate(p, 'a' * 40, qualification, single_flight=fake_flight, analyze=fake_analyze, compare=analyzer.compare)['success'])
            self.assertEqual(param.read_bytes(), original)
            ledger = bindings.read(Path(p['artifacts']['new_run_root']) / 'ledger.json')
            self.assertTrue(ledger['parameter_restore_exact']); self.assertEqual(ledger['remaining_simulators'], [])
            self.assertEqual(len(calls), 1 if failure in ('backend', 'analysis') else 9)
            self.assertEqual(len(ledger['unattempted']), 8 if failure in ('backend', 'analysis') else 0)

    def test_actual_runtime_transaction_success(self): self.backend(None)
    def test_actual_runtime_startup_failure_stops_restores(self): self.backend('backend')
    def test_actual_runtime_analysis_failure_stops_restores(self): self.backend('analysis')
    def test_actual_runtime_rewrites_are_restored_each_attempt(self): self.backend('write')

    def test_active_owned_process_blocks_unsafe_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); param = root / 'parameters'; param.write_bytes(b'changed'); run = root / 'run001'; run.mkdir()
            restore = bindings.clone(bindings.OLD_RUNNER.restore_parameters, active_simulators=lambda: ['owned process still alive'])
            with self.assertRaises(RuntimeError): restore(param, b'original', run, root / 'backup', 'a' * 40, job())
            self.assertEqual(param.read_bytes(), b'changed')
            self.assertFalse(bindings.read(run / 'parameter_restore.json')['stopped_before_restore'])


class ReplayTests(unittest.TestCase):
    def ledger(self):
        p = protocol(); ledger = dict(stage='RI03-A', revision='ri03', gate='A', planned=9, total_budget=9,
            new_planned=9, prior_attempts=0, parameter_restore_exact=True, remaining_simulators=[],
            source_head='a' * 40, firmware_sha256='b' * 64, attempts=[], pairs=[], success=False)
        runner.run_ordered(p, lambda j, i: (metrics(j), dict(metrics_sha256='c' * 64)), analyzer.compare, ledger, lambda e: None)
        return p, ledger

    def test_complete_ledger_and_independent_six_pairs(self):
        p, ledger = self.ledger(); replay.validate_ledger(ledger, p)
        self.assertEqual(len(replay.recompute_pairs(ledger, {j['id']: metrics(j) for j in p['jobs']})), 6)

    def test_incomplete_failed_reordered_or_forged_pair_rejected(self):
        for case in ('missing', 'failed', 'order', 'pair', 'cleanup', 'old_budget', 'old_mode'):
            p, ledger = self.ledger()
            if case == 'missing': ledger['attempts'].pop()
            elif case == 'failed': ledger['attempts'][0]['status'] = 'failed'
            elif case == 'order': ledger['attempts'][0], ledger['attempts'][1] = ledger['attempts'][1], ledger['attempts'][0]
            elif case == 'pair': ledger['pairs'][0]['checks']['yaw'] = False
            elif case == 'cleanup': ledger['parameter_restore_exact'] = False
            elif case == 'old_budget': ledger['prior_attempts'] = 97
            else: ledger['attempts'][1]['job']['mode'] = 1
            with self.subTest(case=case), self.assertRaises((ValueError, RuntimeError)): replay.validate_ledger(ledger, p)

    def test_replay_does_not_trust_stored_pair_success(self):
        p, ledger = self.ledger(); data = {j['id']: metrics(j) for j in p['jobs']}; data['run003']['yaw_rmse'] = 1.
        with self.assertRaises(ValueError): replay.recompute_pairs(ledger, data)

    def test_snapshot_read_only_and_byte_changes_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp); (p / 'raw.ulg').write_bytes(b'fixture'); before = replay.snapshot(p)
            self.assertEqual(before, replay.snapshot(p)); (p / 'raw.ulg').write_bytes(b'changed')
            self.assertNotEqual(before, replay.snapshot(p))


class ReplayAuthorityWiringTests(unittest.TestCase):
    """Real copying + real full-engine provenance, stop before ULog science.

    Fake qualification/prearm services isolate this offline test from real
    frozen flight admission. The real composed analyze body is executed until
    its existing verify_model call, AFTER provenance, then deliberately stops.
    No opaque fixture bytes are presented as successfully decoded ULogs.
    """
    @contextlib.contextmanager
    def archive(self):
        with tempfile.TemporaryDirectory(prefix='ri03-replay-wiring-') as tmp:
            root = Path(tmp); canonical = protocol(root); j = canonical['jobs'][2]
            source = Path(canonical['artifacts']['new_run_root']) / j['id']; source.mkdir(parents=True)
            destination = root / 'A/replay01' / j['id']
            qpath = root / 'A/qualification02/evidence.json'; qpath.parent.mkdir()
            config = root / 'config'; config.mkdir(); bindings.save(config / 'frozen.json', {})
            execution = root / 'execution.json'; bindings.save(execution, {})
            canonical.update(qualification_path=str(qpath), config_dir=str(config), execution_path=str(execution),
                plugins=str(root / 'plugins'), startup_overrides=canonical['jobs'][0]['parameters'])
            saved = {**canonical, 'startup_overrides': {**canonical['startup_overrides'], **j['parameters']}}
            qualified = dict(revision='ri03', stage='RI03-A', gate='A', source_head='a' * 40,
                firmware_sha256='b' * 64, execution_sha256=bindings.digest(execution),
                frozen_sha256=bindings.digest(config / 'frozen.json'), maximum_attempts=9,
                new_matrix_attempts=9, historical_attempts=0, total_maximum_attempts=9,
                execution_authorized=True, flight_authorized=True, execution_ready=True)
            bindings.save(qpath, qualified)
            approval = dict(qualified, approved=True, qualification_sha256=bindings.digest(qpath))
            bindings.save(qpath.parent / 'authorization.json', approval)
            bindings.save(source / 'authorization.json', approval)
            bindings.save(source / 'qualification.json', qualified)
            bindings.save(source / 'qualification_reference.json', dict(path=str(qpath), sha256=bindings.digest(qpath)))
            bindings.save(source / 'run_protocol.json', saved); bindings.save(source / 'job.json', j)
            raw = source / 'opaque_fixture.ulg'; raw.write_bytes(b'NOT A REAL ULOG: stop before decoding')
            record = dict(source_head='a' * 40, binary_sha256='b' * 64,
                runner_sha256=bindings.digest(Path(runner.__file__)), scenario_sha256=bindings.digest(execution),
                scenario_path=str(execution), branch='research/ista-velocity-regularized', success=False,
                logs=[dict(archive=str(raw), bytes=raw.stat().st_size, sha256=bindings.digest(raw))])
            bindings.save(source / 'result.json', record)
            backup = source / 'original_parameters.bson'; backup.write_bytes(b'offline opaque parameter snapshot')
            bindings.save(source / 'parameter_restore.json', dict(parameter_restore_exact=True, remaining_simulators=[],
                stopped_before_restore=True, source_head='a' * 40, gate='A', job_id=j['id'],
                original_parameter_sha256=bindings.digest(backup), restored_parameter_sha256=bindings.digest(backup)))
            (source / 'commands.jsonl').write_text('{}\n')
            calls = []
            def qualified_read(gate, head, path):
                self.assertEqual((gate, head, path), ('A', 'a' * 40, qpath))
                calls.append('archive_qualification')
                return bindings.read(path)
            fake_api = types.SimpleNamespace(load_protocol=lambda gate: canonical,
                require_execution_authority=lambda gate: calls.append('authority_binding_only'),
                archive_qualification=qualified_read)
            actual_full = analyzer.full_analysis
            def stop_after_provenance(*args, **kwargs):
                calls.append('actual_full_engine_after_provenance')
                raise ValueError('OFFLINE_STOP_AFTER_REAL_PROVENANCE_BEFORE_ULOG')
            def real_engine(provenance):
                return bindings.clone(actual_full(provenance), verify_model=stop_after_provenance)
            with patch.object(analyzer, 'api', return_value=fake_api), \
                 patch.object(analyzer, 'full_analysis', side_effect=real_engine), \
                 patch.object(bindings.FINAL, 'prearm_evidence', return_value=dict(valid=True)), \
                 patch.object(bindings.FINAL, 'warmup_evidence', return_value=dict(valid=True)):
                yield types.SimpleNamespace(source=source, destination=destination, job=j, protocol=saved,
                    qpath=qpath, calls=calls, root=root)

    def copy(self, f):
        bindings.FINAL._handoff.copy_sidecars(f.source, f.destination)
        bindings.FINAL._handoff.copied_input_binding(f.source, f.destination)
        return bindings.digest(f.source / 'authorization.json')

    def provenance(self, f, sha):
        return analyzer.provenance(f.destination, f.protocol, f.job,
            original_source=f.source, authorization_sha256=sha)

    def test_real_copy_excludes_authority_live_and_replay_binding_identical(self):
        with self.archive() as f:
            live = analyzer.provenance(f.source, f.protocol, f.job)
            sha = self.copy(f)
            self.assertFalse((f.destination / 'authorization.json').exists())
            self.assertEqual(live, self.provenance(f, sha))
            self.assertEqual(live['authorization_receipt_sha256'], sha)

    def test_actual_replay_new_actual_full_engine_provenance_without_copying_authority(self):
        with self.archive() as f:
            original = analyzer.analyze(f.source, f.protocol, f.job)
            self.assertEqual(original['error'], 'OFFLINE_STOP_AFTER_REAL_PROVENANCE_BEFORE_ULOG')
            before = replay.snapshot(f.source)
            repeated = analyzer.replay_new(f.source, f.destination)
            self.assertEqual(repeated, original)
            self.assertEqual(f.calls.count('actual_full_engine_after_provenance'), 2)
            self.assertFalse(repeated['accepted'])
            self.assertEqual(before, replay.snapshot(f.source))
            self.assertFalse((f.destination / 'authorization.json').exists())
            self.assertFalse((f.destination / 'gate_pass.json').exists())

    def test_copy_completeness_checked_before_full_engine_output(self):
        with self.archive() as f:
            sha = self.copy(f); (f.destination / 'commands.jsonl').write_text('tampered\n')
            with self.assertRaisesRegex(ValueError, 'sidecar copy'):
                analyzer.analyze(f.destination, f.protocol, f.job, original_source=f.source, authorization_sha256=sha)
            self.assertNotIn('actual_full_engine_after_provenance', f.calls)
            self.assertFalse((f.destination / 'r03_metrics.json').exists())

    def test_missing_extra_changed_sidecar_rejected(self):
        for kind in ('missing', 'extra', 'changed', 'symlink'):
            with self.archive() as f:
                sha = self.copy(f)
                if kind == 'missing': (f.destination / 'commands.jsonl').unlink()
                elif kind == 'extra': (f.destination / 'extra.txt').write_text('extra')
                elif kind == 'changed': (f.destination / 'commands.jsonl').write_text('changed')
                else: (f.destination / 'foreign').symlink_to('/tmp/nonexistent-ri03-offline-fixture')
                with self.subTest(kind=kind), self.assertRaises(ValueError): self.provenance(f, sha)

    def test_missing_tampered_original_authorization_rejected(self):
        for kind in ('missing', 'changed', 'symlink'):
            with self.archive() as f:
                sha = self.copy(f); auth = f.source / 'authorization.json'
                if kind == 'missing': auth.unlink()
                elif kind == 'changed': auth.write_text('{}\n')
                else:
                    auth.unlink(); auth.symlink_to(f.qpath.parent / 'authorization.json')
                with self.subTest(kind=kind), self.assertRaises(ValueError): self.provenance(f, sha)

    def test_fake_destination_authority_and_gate_receipts_rejected(self):
        for name in ('authorization.json', 'gate_pass.json'):
            with self.archive() as f:
                sha = self.copy(f); bindings.save(f.destination / name, dict(approved=True, accepted=True))
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'authority'):
                    self.provenance(f, sha)

    def test_other_source_and_missing_fingerprint_rejected(self):
        with self.archive() as f:
            sha = self.copy(f)
            with self.assertRaisesRegex(ValueError, 'canonical'):
                analyzer.provenance(f.destination, f.protocol, f.job,
                    original_source=f.source.parent / 'run004', authorization_sha256=sha)
            with self.assertRaisesRegex(ValueError, 'fingerprint'):
                analyzer.provenance(f.destination, f.protocol, f.job, original_source=f.source)
            with self.assertRaisesRegex(ValueError, 'canonical'):
                analyzer.provenance(f.destination, f.protocol, f.job)

    def test_qualification_authorization_substitution_rejected(self):
        with self.archive() as f:
            sha = self.copy(f)
            approval = bindings.read(f.qpath.parent / 'authorization.json'); approval['source_head'] = 'c' * 40
            bindings.save(f.qpath.parent / 'authorization.json', approval)
            with self.assertRaisesRegex(ValueError, 'Original authorization changed'):
                self.provenance(f, sha)

    def test_replay_new_detects_copy_hook_tampering_before_science(self):
        with self.archive() as f:
            original_copy = bindings.FINAL._handoff.copy_sidecars
            def changed(source, dest):
                result = original_copy(source, dest)
                (dest / 'commands.jsonl').write_text('tampered')
                return result
            with patch.object(bindings.FINAL._handoff, 'copy_sidecars', side_effect=changed):
                with self.assertRaisesRegex(ValueError, 'sidecar copy'): analyzer.replay_new(f.source, f.destination)
            self.assertNotIn('actual_full_engine_after_provenance', f.calls)

    def test_authorization_changed_during_replay_is_not_silently_accepted(self):
        with self.archive() as f:
            original_copy = bindings.FINAL._handoff.copy_sidecars
            def changed(source, dest):
                result = original_copy(source, dest)
                (source / 'authorization.json').write_text('{}\n')
                return result
            with patch.object(bindings.FINAL._handoff, 'copy_sidecars', side_effect=changed):
                with self.assertRaisesRegex(ValueError, 'Original replay inputs changed'):
                    analyzer.replay_new(f.source, f.destination)


if __name__ == '__main__':
    unittest.main(verbosity=2)
