"""RI05 offline full-chain fixtures; no simulator or real parameter writes."""
import contextlib
import copy
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
import bindings

analyzer, runner, replay = [bindings.local(name) for name in ('analyzer', 'runner', 'replay')]
p = bindings.api()


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


def job(mode=4, gate='C'):
    return copy.deepcopy(next(j for j in p.jobs(gate) if j['mode'] == mode))


def metrics(j):
    return dict(accepted=True, job=copy.deepcopy(j), binding=dict(source_head='a' * 40),
        candidate_numeric_binding=bindings.source_binding(), handoff_dependency_binding=bindings.FINAL.HANDOFF_BINDING,
        position_clock_binding=bindings.FINAL.CLOCK_BINDING, prearm_preparation=dict(valid=True),
        post_logger_warmup=dict(valid=True), diagnostic=dict(error=dict(rmse=[.01] * 3),
        windows={w: dict(error=dict(rmse=[.01] * 3)) for w in ('first_half', 'second_half')}),
        position_rmse=[.02] * 3, yaw_rmse=.01)


def fixture(gate='C'):
    j = job(gate=gate)
    x, q, _, start, end = FIXTURES.fixture(j['axes'])
    x['inner_timestamp'] = x['timestamp_sample'].copy()
    x['inner_check_timestamp'] = x['timestamp_sample'].copy()
    x['inner_seq'] = x['publish_seq'].copy()
    x['inner_reads'] = np.ones(len(x['timestamp']), dtype=np.int32)
    x['hover_thrust'] = np.full(len(x['timestamp']), .5, dtype=np.float32)
    for axis in range(3):
        x[f'thrust[{axis}]'] = (x[f'a_proxy[{axis}]'] - (9.80665 if axis == 2 else 0)) * .5 / 9.80665
        q[f'ri_thrust_published[{axis}]'] = x[f'thrust[{axis}]'].copy()
    return x, q, j, start, end


class BindingTests(unittest.TestCase):
    def test_full_science_keeps_complete_checks(self):
        current = analyzer.full_analysis(lambda *args: {})
        original = bindings.FINAL.full_analysis(lambda *args: {}, lambda *args: None)
        self.assertIs(current.__globals__['check_components'], analyzer.components)
        for name in ('check_health', 'check_complete', 'height_evidence', 'exact_output_match', 'r02', 'ULog'):
            self.assertIs(current.__globals__[name], original.__globals__[name])
        self.assertIsNot(original.__globals__['check_components'], analyzer.components)

    def test_flight_body_unchanged_private_identity(self):
        self.assertIs(runner.flight_main.__code__, bindings.OLD_RUNNER.flight_main.__code__)
        self.assertIs(runner.flight_main.__globals__['local_module'], runner.local_module)
        self.assertEqual(Path(runner.flight_main.__globals__['__file__']), Path(runner.__file__))
        self.assertIs(runner.flight_main.__globals__['ram_log'], bindings.RAM_LOG)
        self.assertTrue(callable(bindings.RAM_LOG.release_archived))

    def test_lifecycle_class_unchanged(self):
        current, inherited = runner.execution_checks_class(), bindings.OLD_RUNNER.execution_checks_class()
        self.assertEqual([c.__name__ for c in current.__mro__[1:]], [c.__name__ for c in inherited.__mro__])

    def test_xy_actual_bound_components(self):
        x, q, j, start, end = fixture('C')
        result, _, _ = analyzer.components(x, q, j, start, end, True)
        self.assertTrue(result['cadence']['component_valid'])
        self.assertFalse(result['closed_cache_policy']['applicable'])

    def test_xyz_actual_bound_components_nonempty_hte(self):
        x, q, j, start, end = fixture('D')
        result, _, _ = analyzer.components(x, q, j, start, end, True)
        self.assertTrue(result['cadence']['component_valid'])
        self.assertGreater(result['closed_cache_hte']['eligible_pairs'], 700)
        self.assertTrue(np.all(x['pid_axes'] == 0))
        self.assertTrue(np.all(x['pid_calls'] == 1))

    def test_pid_rsta_delegate_unchanged(self):
        for gate in ('C', 'D'):
            for mode in (0, 3):
                with patch.object(bindings.FINAL, '_components', return_value='old') as call:
                    self.assertEqual(analyzer.components({}, {}, job(mode, gate), 1, 2), 'old')
                    self.assertEqual(call.call_args.args[2]['mode'], mode)

    def test_private_tools_do_not_change_ri02_bindings(self):
        self.assertIsNot(bindings.KERNEL.full_chain.analyzer, analyzer)
        self.assertIsNot(bindings.KERNEL.analyzer, analyzer)


class NegativeComponents(unittest.TestCase):
    pass


def negative_component(gate, case):
    def test(self):
        x, q, j, start, end = fixture(gate)
        k, axis = 100, 0 if gate == 'C' else 2
        if case == 'mode': x['effective_mode'][k] = q['effective_mode'][k] = 3
        elif case == 'axes': x['effective_axes'][k] = q['effective_axes'][k] = 1
        elif case == 'inner': x['inner_mode'][k] = 3
        elif case == 'inner_stale': x['inner_timestamp'][k] = 0
        elif case == 'duplicate_sample': x['timestamp_sample'][k] = x['timestamp_sample'][k - 1]
        elif case == 'backward_publication': x['timestamp'][k] = x['timestamp'][k - 1] - 1
        elif case == 'missing_selection': q = {key: np.delete(value, k) for key, value in q.items()}
        elif case == 'same_time_ambiguous': q['timestamp'][k] = q['timestamp'][k - 1]
        elif case == 'missing_update': q['control_seq'][k:] += 1
        elif case == 'not_taken_over': x['active_axes'][k] = 0
        elif case == 'partial_commit': q['ri_commit_axes'][k] = 1
        elif case == 'p': q[f'ri_p[{axis}]'][k] += .1
        elif case == 'nu_candidate': q[f'ri_nu_candidate[{axis}]'][k] += .1
        elif case == 'old_nu_output': q[f'ri_a_ideal[{axis}]'][k] += x[f'nu_before[{axis}]'][k] - x[f'nu_ideal[{axis}]'][k]
        elif case == 'applied': q[f'ri_a_applied[{axis}]'][k] += .1
        elif case == 'published': q[f'ri_acc_published[{axis}]'][k] += .1
        elif case == 'proxy': x[f'a_proxy[{axis}]'][k] += .1
        elif case == 'ff_twice': x[f'a_req[{axis}]'][k] += x[f'a_ff[{axis}]'][k]
        elif case == 'wrong_h': q['ri_h'][k] = .02
        elif case == 'legacy_clamp_h': q['h'][k] = .02
        elif case == 'zero_cost': q['path_ns'][k] = 0
        elif case == 'false_valid': q['ri_valid'][k] = 0
        elif case == 'selected_nan': q[f'ri_p[{axis}]'][k] = np.nan
        elif case == 'interval': q['interval_pos'][k] = 1
        elif case == 'reset': x['reset_bits'][k] = 1
        elif case == 'long_pause': x['raw_dt'][k] = q['ri_h'][k] = .5
        elif case == 'epsilon': q[f'eps_eff[{axis}]'][k] = .03
        elif case == 'generation': q['sta_gen'][k] = 0
        elif case == 'pid_axes': x['pid_axes'][k] = 7
        else: raise AssertionError(case)
        with self.assertRaises((ValueError, RuntimeError)):
            analyzer.components(x, q, j, start, end, True)
    return test


for _gate in ('C', 'D'):
    for _case in ('mode', 'axes', 'inner', 'inner_stale', 'duplicate_sample', 'backward_publication',
                 'missing_selection', 'same_time_ambiguous', 'missing_update', 'not_taken_over',
                 'partial_commit', 'p', 'nu_candidate', 'old_nu_output', 'applied', 'published', 'proxy',
                 'ff_twice', 'wrong_h', 'legacy_clamp_h', 'zero_cost', 'false_valid', 'selected_nan',
                 'interval', 'reset', 'long_pause', 'epsilon', 'generation', 'pid_axes'):
        setattr(NegativeComponents, 'test_' + _gate + '_' + _case, negative_component(_gate, _case))


class ScopeTests(unittest.TestCase):
    def test_complete18_and_tasks(self):
        self.assertEqual(len(p.design()['jobs']), 18)
        for gate, task, axes, test in [('C', 'H', 3, 6), ('D', 'V', 7, 8)]:
            runner.validate_scope(p.load_protocol(gate))
            for j in p.jobs(gate):
                self.assertEqual(analyzer.validate_job(j), (task, axes, test, 64))

    def test_reject_other_modes_axes_tasks(self):
        for key, values in dict(mode=(1, 2, 5, True, 4.), axes=(0, 1, 2, 4, 5, 6, 7),
                                gate=('A', 'B', 'E'), divisor=(2, 4), main_duration_s=(32, 90)).items():
            for value in values:
                j = job(); j[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError): analyzer.validate_job(j)

    def test_wrong_actual_parameter_profile(self):
        for name, value in dict(MPC_VC_MODE=3, MPC_VC_AXES=7, MPC_VC_DIV=2, MC_RTC_MODE=1,
                                MC_STA_AXES=1, MC_RTC_DIV=2, MC_RATT_TEST=1, MPC_VCT_TEST=3).items():
            j = job(); j['parameters'][name] = value
            with self.subTest(name=name), self.assertRaises(ValueError): analyzer.validate_job(j)

    def test_budget_order_duplicate_rejected(self):
        for change in ('extra', 'old', 'duplicate', 'esta', 'order'):
            value = p.load_protocol('C')
            if change == 'extra': value['maximum_attempts'] = 10
            elif change == 'old': value['historical_attempts'] = 3
            elif change == 'duplicate': value['jobs'][1] = copy.deepcopy(value['jobs'][0])
            elif change == 'esta': value['jobs'][1]['mode'] = 1
            else: value['jobs'][0], value['jobs'][1] = value['jobs'][1], value['jobs'][0]
            with self.subTest(change=change), self.assertRaises((ValueError, RuntimeError)): runner.validate_scope(value)

    def test_default_dryrun_never_executes(self):
        with patch.object(p, 'validate_manifest'), patch.object(runner, 'execute_gate') as execute, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main([]), 0)
            self.assertEqual(runner.main(['--gate', 'D']), 0)
            execute.assert_not_called()

    def test_execute_requires_explicit_full_identity(self):
        for argv in (['--execute'], ['--execute', '--source-head', 'a' * 40],
                     ['--execute', '--source-head', 'short', '--qualification', '/tmp/q']):
            with patch.object(p, 'validate_manifest'), patch.object(runner, 'execute_gate') as execute, contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(RuntimeError): runner.main(argv)
                execute.assert_not_called()

    def test_noncanonical_protocol_rejected_before_mutation(self):
        changed = p.load_protocol('C'); changed['jobs'][1]['parameters']['MPC_VC_L1_X'] += .1
        with patch.object(p, 'require_execution_authority'), patch.object(runner, '_execute_gate') as execute:
            with self.assertRaisesRegex(RuntimeError, 'canonical'): runner.execute_gate(changed, 'a'*40, Path('/tmp/q'))
            execute.assert_not_called()


class ScheduleTests(unittest.TestCase):
    def run_fixture(self, gate='C', fail=None, invalid=None, risk=None):
        protocol, ledger, calls = p.load_protocol(gate), dict(attempts=[], pairs=[], success=False), []
        def perform(j, index):
            calls.append(index)
            if index == fail: raise RuntimeError('synthetic preflight backend failure')
            m = metrics(j)
            if index == invalid: m['accepted'] = False
            if index == risk: m['yaw_rmse'] = 1.
            return m, dict(metrics_sha256='b'*64)
        return protocol, ledger, calls, perform

    def test_both_gates_exact_nine_six(self):
        for gate in ('C', 'D'):
            protocol, ledger, calls, perform = self.run_fixture(gate)
            runner.run_ordered(protocol, perform, analyzer.compare, ledger, lambda event: None)
            self.assertEqual(calls, list(range(1, 10))); self.assertTrue(ledger['success'])
            self.assertEqual(len(ledger['pairs']), 6); self.assertEqual(ledger['unattempted'], [])
            self.assertTrue(all(pair['gate'] == gate for pair in ledger['pairs']))

    def test_first_backend_failure_consumes_one(self):
        protocol, ledger, calls, perform = self.run_fixture(fail=1)
        with self.assertRaises(RuntimeError): runner.run_ordered(protocol, perform, analyzer.compare, ledger, lambda event: None)
        self.assertEqual(calls, [1]); self.assertEqual(len(ledger['unattempted']), 8)
        self.assertEqual(ledger['attempts'][0]['status'], 'failed')

    def test_invalid_log_stops_no_replacement(self):
        protocol, ledger, calls, perform = self.run_fixture(invalid=3)
        with self.assertRaises(RuntimeError): runner.run_ordered(protocol, perform, analyzer.compare, ledger, lambda event: None)
        self.assertEqual(calls, [1, 2, 3]); self.assertEqual(len(ledger['unattempted']), 6)

    def test_pair_risk_stops_before_next_seed(self):
        protocol, ledger, calls, perform = self.run_fixture(risk=3)
        with self.assertRaises(RuntimeError): runner.run_ordered(protocol, perform, analyzer.compare, ledger, lambda event: None)
        self.assertEqual(calls, [1, 2, 3]); self.assertFalse(ledger['success'])

    def test_failure_latches(self):
        protocol = p.load_protocol('C'); a = runner.Admission(protocol, analyzer.compare)
        with self.assertRaises(RuntimeError): a.accept(protocol['jobs'][0], dict(accepted=False))
        with self.assertRaises(RuntimeError): a.before(protocol['jobs'][0])


class ComparisonTests(unittest.TestCase):
    def test_two_independent_risk_calculations(self):
        for gate in ('C', 'D'):
            for mode in (3, 4):
                pid, other = metrics(job(0, gate)), metrics(job(mode, gate))
                self.assertEqual(analyzer.compare(pid, other), replay.paired_decision(pid, other))
                self.assertEqual(len(analyzer.compare(pid, other)['checks']), 13)

    def test_not_required_to_win(self):
        pid, other = metrics(job(0)), metrics(job()); other['yaw_rmse'] = .02
        self.assertTrue(analyzer.compare(pid, other)['accepted'])
        other['yaw_rmse'] = .1; self.assertFalse(analyzer.compare(pid, other)['accepted'])

    def test_nonfinite_bad_type_metrics_rejected(self):
        for value in (float('nan'), float('inf'), -.01, False, '0'):
            pid, other = metrics(job(0)), metrics(job()); other['diagnostic']['error']['rmse'][0] = value
            for fn in (analyzer.compare, replay.paired_decision):
                with self.subTest(value=value), self.assertRaises(ValueError): fn(pid, other)

    def test_different_gate_not_paired(self):
        with self.assertRaises(ValueError): analyzer.compare(metrics(job(0, 'C')), metrics(job(4, 'D')))

    def test_pair_parameter_change_rejected(self):
        pid, other = metrics(job(0)), metrics(job()); other['job']['parameters']['MPC_VC_L1_X'] += .1
        with self.assertRaises(ValueError): analyzer.compare(pid, other)


class HteTests(unittest.TestCase):
    def test_xyz_nonzero_shift_is_checked_not_empty_subset(self):
        x, q, j, _, _ = fixture('D')
        x['hover_thrust'][100:] = np.float32(.51)
        expected = (np.float32(.5)/np.float32(.51)-np.float32(1)) * (q['correction[2]'][99]+x['a_ff[2]'][99]-np.float32(9.80665))
        x['z_hte_shift'][100] = expected
        result = analyzer.closed_cache_hte(x, q, j)
        self.assertEqual(result['eligible_pairs'], len(x['timestamp'])-1)
        self.assertEqual(result['nonzero_shifts_checked'], 1)
        x['z_hte_shift'][100] += .01
        with self.assertRaisesRegex(ValueError, 'shift differs'): analyzer.closed_cache_hte(x, q, j)

    def test_xy_fake_z_cache_rejected(self):
        x, q, j, start, end = fixture('C'); q['ri_cache_valid'][100] = 1
        with self.assertRaises(ValueError): analyzer.components(x, q, j, start, end, True)

    def test_xyz_wrong_previous_cache_rejected(self):
        x, q, j, start, end = fixture('D'); q['ri_cache_valid'][100] = 0
        with self.assertRaises(ValueError): analyzer.components(x, q, j, start, end, True)

    def test_xyz_wrong_cache_sample_rejected(self):
        x, q, j, start, end = fixture('D'); q['ri_cache_sample'][100] -= 1
        with self.assertRaises(ValueError): analyzer.components(x, q, j, start, end, True)

    def test_state_limit_only_cache_remains_valid(self):
        x, q, _, _, _ = fixture('D'); x['sta_flags'][100] = 8
        result = analyzer.closed_cache_policy(x, q)
        self.assertEqual(result['state_limit_only_cached'], 1)

    def test_output_limit_cache_rejected(self):
        x, q, _, _, _ = fixture('D'); x['sta_flags'][100] = 16
        with self.assertRaises(ValueError): analyzer.closed_cache_policy(x, q)


if __name__ == '__main__':
    unittest.main()
