"""Offline positive/negative tests. No real EEPROM, PX4 or Gazebo access."""
import copy
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import unittest
import numpy as np
from config import candidate, validate, REPO
import analyzer
from legacy import clock_policy, initialize, parameter_io, task_checks
from parameters import ParameterTransaction
import run


def fixture(mode=3, axes=7, n=900):
    job = candidate(mode, axes)
    t = np.arange(n, dtype=np.int64) * 10000 + 1000000
    d = {k: np.zeros(n, dtype=np.int64) for k in ('pending', 'reject', 'inner_mode', 'inner_axes',
         'fault', 'failsafe', 'timing', 'sta_fault', 'config_pending', 'sta_flags', 'constraint_bits', 'reset_bits')}
    for k in ('timestamp', 'timestamp_sample', 'input_timestamp', 'inner_timestamp', 'inner_check_timestamp'):
        d[k] = t.copy()
    for k in ('publish_seq', 'update_seq', 'inner_seq'):
        d[k] = np.arange(n)
    for k in ('pid_calls', 'enabled', 'armed', 'valid', 'inner_valid', 'inner_divisor', 'inner_reads'):
        d[k] = np.ones(n, dtype=int)
    for k, v in dict(requested_mode=mode, effective_mode=mode, requested_axes=axes, effective_axes=axes,
                     pid_axes=7 ^ axes, active_axes=axes, committed_axes=axes, z_phase=3 if axes & 4 else 0).items():
        d[k] = np.full(n, v)
    for k in ('raw_dt', 'used_dt', 'input_dt'):
        d[k] = np.full(n, .01)
    d['hover_thrust'] = np.full(n, .5); d['z_hte_shift'] = np.zeros(n)
    d['config_generation'] = np.ones(n, dtype=np.uint32)
    q = {k: d[k].copy() for k in ('timestamp', 'timestamp_sample', 'input_timestamp', 'publish_seq', 'pid_calls',
         'enabled', 'armed', 'requested_mode', 'effective_mode', 'requested_axes', 'effective_axes', 'pending', 'reject')}
    for k, v in dict(div_req=1, div_eff=1, div_pending=0, div_reject=0, control_fault=0, clock=1,
                     control_updated=1, control_held=0, path_ns=100, module_ns=200, interval_pos=0, interval_neg=0,
                     variant_req=mode, variant_eff=mode, sta_gen=1, sta_pending=0, sta_reject=0).items():
        q[k] = np.full(n, v)
    q['h'] = np.full(n, .01); q['control_seq'] = np.arange(n) + 1
    for axis, suffix in enumerate('XYZ'):
        eps = job['parameters']['MPC_VC_EPS_' + suffix]
        q[f'eps_req[{axis}]'] = np.full(n, eps)
        q[f'eps_eff[{axis}]'] = np.full(n, eps if mode == 3 and axes & (1 << axis) else np.nan)
        s = np.where(np.arange(n) % 2, 1., -1.) * (axis + 1) * .0001
        d[f's[{axis}]'] = s; d[f'v[{axis}]'] = s.copy(); d[f'v_sp[{axis}]'] = np.zeros(n)
        d[f'v_dot[{axis}]'] = np.zeros(n)
        d[f'a_ff[{axis}]'] = np.full(n, .001 * (axis + 1)); q[f'integral[{axis}]'] = np.zeros(n)
        for name in ('nu_before', 'nu_ideal', 'nu_applied', 'a_sta'):
            d[f'{name}[{axis}]'] = np.full(n, np.nan)
        c = np.zeros(n)
        if axes & (1 << axis):
            l1 = job['parameters']['MPC_VC_L1_' + suffix]; l2 = job['parameters']['MPC_VC_L2_' + suffix]
            # Deliberately direct piecewise reference, not analyzer.nonlinear().
            if mode == 3:
                rho = np.clip(s / eps, -1, 1)
                psi = np.where(abs(s) <= eps, s / np.sqrt(eps), np.sign(s) * np.sqrt(abs(s)))
            else:
                rho = np.sign(s); psi = np.sign(s) * np.sqrt(abs(s))
            post = np.cumsum(-.01 * l2 * rho); before = np.r_[0., post[:-1]]
            c = -l1 * psi + before
            for name, value in dict(nu_before=before, nu_ideal=post, nu_applied=post, a_sta=c).items():
                d[f'{name}[{axis}]'] = value.copy()
        q[f'correction[{axis}]'] = c; d[f'a_req[{axis}]'] = c + d[f'a_ff[{axis}]']
        d[f'a_proxy[{axis}]'] = d[f'a_req[{axis}]'].copy()
        d[f'thrust[{axis}]'] = (d[f'a_req[{axis}]'] - (9.80665 if axis == 2 else 0)) * .5 / 9.80665
    return d, q, job


def check(d, q, job):
    return analyzer.check_components(d, q, job, 1000000, 1000000 + 900 * 10000, steady=True)


class Configuration(unittest.TestCase):
    def test_complete_traceable_configurations(self):
        for mode, axes in [(0, 0)] + [(1, a) for a in range(1, 8)] + [(3, a) for a in (1, 4, 3, 7)]:
            c = candidate(mode, axes)
            self.assertEqual(len(c['parameters']), 127)
            self.assertTrue(validate(mode, axes, c['parameters']))
            self.assertFalse(c['flight_authorized']); self.assertEqual(c['maximum_attempts'], 0)

    def test_invalid_modes_axes_and_no_default_x(self):
        for mode, axes in [(2, 1), (4, 1), (-1, 0), (True, 1), (0, 1), (1, 0), (1, 8), (3, 0), (3, 2), (3, 5), (3, 6), (3, 8)]:
            with self.subTest(mode=mode, axes=axes), self.assertRaises(ValueError):
                candidate(mode, axes)

    def test_epsilon_domain_and_independent_axes(self):
        self.assertEqual(candidate(3, 7, (.001, 1, .02))['new_parameters']['MPC_VC_EPS_Y'], 1)
        for bad in (0, .00099, 1.01, float('nan'), float('inf'), True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                candidate(3, 1, (bad, .01, .02))

    def test_fixed_inner_div_and_numeric_limits(self):
        for key, value in [('MC_RTC_MODE', 1), ('MC_STA_AXES', 1), ('MC_RTC_DIV', 2), ('MC_RATT_TEST', 1),
                           ('MC_STA_TKO_MGT', 1), ('MPC_VC_DIV', 2), ('MPC_VCT_TEST', 6), ('MPC_VC_L1_X', -1),
                           ('MPC_VC_L1_X', True), ('MPC_VC_NU_Z', float('nan'))]:
            c = candidate(3, 7); c['parameters'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate(3, 7, c['parameters'])

    def test_missing_unrelated_parameter_is_not_full_configuration(self):
        c = candidate(3, 1); del c['parameters']['MPC_XY_P']
        with self.assertRaisesRegex(ValueError, 'Incomplete full parameter'): validate(3, 1, c['parameters'])

    def test_dryrun_and_hard_execute_denial(self):
        with contextlib.redirect_stdout(io.StringIO()) as stream:
            self.assertEqual(run.main(['--mode', '3', '--axes', '1']), 0)
        self.assertIn('DRY RUN', stream.getvalue())
        with self.assertRaisesRegex(RuntimeError, 'R02 is offline-only'):
            run.main(['--execute', '--manifest', '/forged.json', '--source-head', 'forged', '--authorization', 'approved'])


class Components(unittest.TestCase):
    def test_all_supported_old_and_new_components(self):
        for mode, axes in [(0, 0)] + [(1, a) for a in range(1, 8)] + [(3, a) for a in (1, 4, 3, 7)]:
            with self.subTest(mode=mode, axes=axes):
                result = check(*fixture(mode, axes))
                self.assertTrue(result['component_valid']); self.assertFalse(result['flight_accepted'])

    def test_piecewise_boundaries_not_hypot(self):
        eps = .01; s = np.array([-1., -eps, -.005, 0, .005, eps, 1.])
        psi, rho = analyzer.nonlinear(s, eps)
        np.testing.assert_allclose(rho, [-1, -1, -.5, 0, .5, 1, 1], rtol=0, atol=1e-15)
        np.testing.assert_allclose(psi, [-1, -.1, -.05, 0, .05, .1, 1], rtol=0, atol=1e-15)

    def test_exact_duplicate_or_missing_selection(self):
        for field in ('publish_seq', 'timestamp_sample', 'input_timestamp'):
            d, q, j = fixture(); q[field][300] = q[field][299]
            with self.subTest(field=field), self.assertRaises(ValueError): check(d, q, j)
        d, q, j = fixture(); q = {k: np.delete(v, 300) for k, v in q.items()}
        with self.assertRaises(ValueError): check(d, q, j)

    def test_wrong_modes_axes_pending_and_inner(self):
        for field, value in [('effective_mode', 1), ('requested_mode', 2), ('effective_axes', 1), ('requested_axes', 4),
                             ('pending', 1), ('reject', 1), ('inner_mode', 1), ('inner_axes', 1), ('inner_divisor', 2),
                             ('inner_valid', 0), ('inner_timestamp', 1), ('fault', 1), ('sta_fault', 1), ('timing', 2)]:
            d, q, j = fixture(); d[field][200] = value
            with self.subTest(field=field), self.assertRaises(ValueError): check(d, q, j)

    def test_clocks_gaps_raw_dt_and_full_edges(self):
        for field in ('timestamp', 'timestamp_sample', 'input_timestamp', 'publish_seq', 'update_seq'):
            d, q, j = fixture(); d[field][200] = d[field][199]
            with self.subTest(field=field), self.assertRaises(ValueError): check(d, q, j)
        for field in ('raw_dt', 'used_dt', 'input_dt'):
            d, q, j = fixture(); d[field][200] = .04
            with self.subTest(field=field), self.assertRaises(ValueError): check(d, q, j)
        for sl in (slice(5, None), slice(None, -5), slice(None, 500)):
            d, q, j = fixture(); d = {k: v[sl] for k, v in d.items()}
            with self.assertRaises(ValueError): check(d, q, j)

    def test_metadata_effective_epsilon_generation(self):
        for field, value in [('variant_req', 1), ('variant_eff', 1), ('sta_gen', 2), ('sta_pending', 1),
                             ('sta_reject', 1), ('eps_eff[0]', .02), ('eps_req[1]', .02)]:
            d, q, j = fixture(); q[field][400] = value
            with self.subTest(field=field), self.assertRaises(ValueError): check(d, q, j)
        d, q, j = fixture(3, 1); q['eps_eff[1]'][:] = .01
        with self.assertRaises(ValueError): check(d, q, j)
        d, q, j = fixture()
        with self.assertRaises(ValueError): analyzer.check_components(d, q, j, 1000000, 10000000, steady=True, new_metadata=False)

    def test_no_engagement_reset_partial_commit_and_pid_axes(self):
        for field, value in [('active_axes', 0), ('committed_axes', 1), ('pid_axes', 7), ('sta_flags', 1),
                             ('reset_bits', 1), ('z_phase', 2), ('enabled', 0), ('armed', 0)]:
            d, q, j = fixture(); d[field][300] = value
            with self.subTest(field=field), self.assertRaises(ValueError): check(d, q, j)

    def test_old_nu_candidate_applied_and_cross_axis(self):
        for field in ('nu_before[0]', 'nu_ideal[1]', 'nu_applied[2]', 'a_sta[0]'):
            d, q, j = fixture(); d[field][300] += .001
            with self.subTest(field=field), self.assertRaises(ValueError): check(d, q, j)
        d, q, j = fixture(3, 1); d['nu_applied[2]'][:] = 0
        with self.assertRaises(ValueError): check(d, q, j)

    def test_ff_once_actual_proxy_and_sensor_h(self):
        for field in ('a_ff[0]', 'a_req[0]', 'a_proxy[2]', 'thrust[2]'):
            d, q, j = fixture(); d[field][300] += .001
            with self.subTest(field=field), self.assertRaises(ValueError): check(d, q, j)
        d, q, j = fixture(); d['nu_ideal[0]'][:] = d['nu_before[0]'] - .012 * .1 * np.clip(d['s[0]'] / .01, -1, 1)
        with self.assertRaises(ValueError): check(d, q, j)

    def test_real_h_not_selection_pid_h(self):
        d, q, j = fixture(); n = len(d['timestamp'])
        h = np.where(np.arange(n) % 2, .012, .008)
        t = 1000000 + np.r_[0, np.cumsum((h[1:] * 1e6).astype(np.int64))]
        for data in (d, q):
            for key in ('timestamp', 'timestamp_sample', 'input_timestamp'): data[key] = t.copy()
        for key in ('inner_timestamp', 'inner_check_timestamp'): d[key] = t.copy()
        d['raw_dt'] = h
        for axis, suffix in enumerate('XYZ'):
            p = j['parameters']; s = d[f's[{axis}]']; eps = p['MPC_VC_EPS_' + suffix]
            post = np.cumsum(-h * p['MPC_VC_L2_' + suffix] * np.clip(s / eps, -1, 1))
            before = np.r_[0, post[:-1]]; c = before - p['MPC_VC_L1_' + suffix] * s / np.sqrt(eps)
            for k, v in dict(nu_before=before, nu_ideal=post, nu_applied=post, a_sta=c).items(): d[f'{k}[{axis}]'] = v.copy()
            q[f'correction[{axis}]'] = c; d[f'a_req[{axis}]'] = c + d[f'a_ff[{axis}]']
            d[f'a_proxy[{axis}]'] = d[f'a_req[{axis}]'].copy()
            d[f'thrust[{axis}]'] = (d[f'a_req[{axis}]'] - (9.80665 if axis == 2 else 0)) * .5 / 9.80665
        self.assertTrue(check(d, q, j)['component_valid'])

    def test_hte_selected_z_and_wrong_unselected(self):
        d, q, j = fixture(3, 4); d['z_hte_shift'][400] = .001
        for key in ('nu_before[2]', 'nu_ideal[2]', 'nu_applied[2]', 'a_sta[2]', 'a_req[2]', 'a_proxy[2]'): d[key][400:] += .001
        q['correction[2]'][400:] += .001; d['thrust[2]'][400:] += .001 * .5 / 9.80665
        self.assertTrue(check(d, q, j)['component_valid'])
        d['z_hte_shift'][400] = 0
        with self.assertRaises(ValueError): check(d, q, j)

    def test_missing_fullflight_events_cannot_accept_component(self):
        with self.assertRaises(KeyError): analyzer.whole_flight_components(None, Path('/not-used'), candidate(3, 1), {})

    def test_first_sample_dt_and_retry_fail_closed(self):
        for field, value in [('raw_dt', 0), ('raw_dt', .041), ('raw_dt', float('nan')), ('pid_calls', 2)]:
            d, q, j = fixture(); d[field][0] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError): check(d, q, j)

    def test_pid_unused_sta_reject_is_not_mode_rejection(self):
        d, q, j = fixture(0, 0); q['sta_reject'][:] = 1
        self.assertTrue(check(d, q, j)['component_valid'])

    def test_nonsteady_lifecycle_illegal_pid_or_handover(self):
        for key, value in [('pid_axes', 7), ('z_phase', 2), ('active_axes', 0), ('committed_axes', 0)]:
            d, q, j = fixture(); d[key][300] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                analyzer.check_components(d, q, j, 1000000, 10000000, steady=False)

    def test_nonsteady_nu_continuity_without_reset(self):
        d, q, j = fixture(); d['nu_before[0]'][300] += .001
        with self.assertRaises(ValueError): analyzer.check_lifecycle(d, q, j)

    def test_ground_single_handover_normal_and_acceleration_only_masks(self):
        d, q, j = fixture(3, 7, 4)
        d['z_phase'][:] = [1, 2, 3, 4]; d['sta_flags'][:] = [130, 129, 0, 0]
        d['active_axes'][:] = [0, 0, 7, 3]; d['committed_axes'][:] = [0, 0, 7, 3]
        d['pid_axes'][:] = [7, 7, 0, 0]; d['v_sp[2]'][3] = np.nan
        for axis in range(3):
            d[f'nu_before[{axis}]'][:] = 0; d[f'nu_applied[{axis}]'][:] = 0
            q[f'correction[{axis}]'][1] = -j['parameters']['MPC_VC_L1_' + 'XYZ'[axis]] * d[f's[{axis}]'][1] / np.sqrt(j['parameters']['MPC_VC_EPS_' + 'XYZ'[axis]])
        analyzer.check_lifecycle(d, q, j)
        for axis in range(3): d[f'v_sp[{axis}]'][0] = np.nan
        d['pid_axes'][0] = 0  # Actual not-taken-off acceleration-only suppression.
        analyzer.check_lifecycle(d, q, j)
        d['z_phase'][2] = 2; d['sta_flags'][2] = 129; d['pid_axes'][2] = 7; d['active_axes'][2] = 0; d['committed_axes'][2] = 0
        with self.assertRaisesRegex(ValueError, 'one priming'): analyzer.check_lifecycle(d, q, j)


class InheritedBoundaries(unittest.TestCase):
    def attitude(self):
        # A tied publication group retains two distinct sensor samples.
        p = np.array([100000, 110000, 110000, 120000, 130000], dtype=np.int64)
        s = np.array([99000, 105000, 109000, 119000, 129000], dtype=np.int64)
        d = dict(timestamp=p, timestamp_sample=s, quat_reset_counter=np.array([0, 0, 1, 1, 1]))
        for stem in ('q', 'delta_q_reset'):
            for axis in range(4): d[f'{stem}[{axis}]'] = np.full(5, 1. if axis == 0 else 0.)
        return d

    def test_attitude_whitelist_and_tied_ambiguity(self):
        cp = clock_policy(); p = cp.AttitudeClockPolicy(); d = self.attitude()
        p.validate(d); self.assertEqual(p.reset_indices(d, 110000, 120000).tolist(), [2])
        with self.assertRaises(ValueError): p.unique_index(d, 110000)
        with self.assertRaises(ValueError): cp.strict_clock(d['timestamp'])

    def test_all_tied_boundary_rows_and_reset(self):
        p = clock_policy().AttitudeClockPolicy(); d = self.attitude()
        self.assertEqual(p.window(d, 110000, 110000).tolist(), [0, 1, 2])
        d['timestamp_sample'][2] = d['timestamp_sample'][1]
        with self.assertRaises(ValueError): p.validate(d)

    def test_consumed_target_exact_no_nearest(self):
        src = {'timestamp': np.array([100, 110, 120], dtype=np.int64)}
        x = dict(timestamp=np.array([111, 121]), input_timestamp=np.array([109, 119]), setpoint_timestamp=np.array([110, 120]))
        j, age = task_checks().consumed_targets(src, x)
        self.assertEqual(j.tolist(), [1, 2])
        x['setpoint_timestamp'][0] = 109
        with self.assertRaises(ValueError): task_checks().consumed_targets(src, x)

    def test_duplicate_consumed_target_source_rejected(self):
        src = {'timestamp': np.array([100, 110, 110], dtype=np.int64)}
        x = dict(timestamp=np.array([111, 121]), input_timestamp=np.array([109, 119]), setpoint_timestamp=np.array([110, 110]))
        with self.assertRaises(ValueError): task_checks().consumed_targets(src, x)

    def test_imu_only_ties_and_sealed_end_boundary(self):
        initialize()
        from imu_health import bounds, clock
        p = np.array([100000, 104000, 108000, 108000, 112000, 116000, 120000], dtype=np.int64)
        s = np.array([99000, 103000, 105000, 107000, 111000, 115000, 119000], dtype=np.int64)
        d = dict(timestamp=p, timestamp_sample=s)
        self.assertIsNotNone(bounds(d, 104000, 111000))
        with self.assertRaises(ValueError): bounds(d, 104000, 119000)
        d['timestamp_sample'][3] = d['timestamp_sample'][2]
        with self.assertRaises(ValueError): clock(d)

    def test_landing_incomplete_or_reversed_context_rejected(self):
        initialize()
        from landing import validate_context
        good = dict(hover_start_us=1000000, hover_end_us=91000000, command_lower_us=92000000, cli_success=True)
        validate_context(good)
        for key, value in [('command_lower_us', 90000000), ('hover_end_us', 90000000), ('cli_success', False)]:
            with self.subTest(key=key), self.assertRaises(ValueError): validate_context({**good, key: value})


class MemoryStore:
    def __init__(self, value): self.value = bytes(value); self.writes = []
    def read(self): return self.value
    def write(self, value): self.value = bytes(value); self.writes.append(self.value)


class Transactions(unittest.TestCase):
    def setup_transaction(self, mode=3, axes=7):
        c = candidate(mode, axes); types = {k: 'Int32' if type(v) is int else 'Float' for k, v in c['parameters'].items()}
        types['UNRELATED'] = 'Int32'; types['SDLOG_PROFILE'] = 'Int32'
        raw = parameter_io().encode_bson({'UNRELATED': 923, 'SDLOG_PROFILE': 8192}, types)
        store = MemoryStore(raw); transaction = ParameterTransaction(store, types, {}, lambda: True)
        return c, raw, store, transaction

    def test_full_archive_success_and_unrelated_profile_retained(self):
        c, raw, store, tx = self.setup_transaction()
        with tx:
            expected = tx.apply(c); values = parameter_io().persisted_bson(store.read())
            self.assertEqual(values['UNRELATED'], 923)
            self.assertEqual(int(values['SDLOG_PROFILE']) & 8192, 8192)
            self.assertEqual(len(expected), 129)
        self.assertEqual(store.read(), raw); self.assertTrue(tx.receipt['restore_exact'])

    def test_failed_operation_still_restores_all_bytes(self):
        c, raw, store, tx = self.setup_transaction()
        with self.assertRaisesRegex(RuntimeError, 'injected'):
            with tx:
                tx.apply(c); raise RuntimeError('injected failure')
        self.assertEqual(store.read(), raw)

    def test_runtime_fakecli_actual_inner_and_unengaged_mode(self):
        c, raw, store, tx = self.setup_transaction()
        with tx:
            expected = tx.apply(c)
            def cli(*args):
                self.assertEqual(args, ('param', 'show', '-a'))
                return '\n'.join(f'{k} [0,0] : {v}' for k, v in expected.items())
            inner = dict(requested_mode=0, effective_mode=0, requested_axes=0, effective_axes=0, div_req=1, div_eff=1,
                         fault=0, abort_requested=0, termination=0, armed=False)
            selection = dict(requested_mode=3, effective_mode=3, requested_axes=7, effective_axes=7, div_req=1, div_eff=1, pending=0, reject=0,
                             variant_req=3, variant_eff=3, sta_pending=False, sta_reject=False, sta_gen=1,
                             eps_req=[.01, .01, .02], eps_eff=[.01, .01, .02])
            topics = {'vehicle_status': {'arming_state': 1}, 'vehicle_land_detected': {'landed': True},
                      'sta_rate_ctrl_status': inner, 'velocity_ctrl_selection': selection}
            tx.verify_runtime(cli, topics.__getitem__)
            for field in ('variant_req', 'variant_eff', 'sta_pending', 'sta_reject', 'sta_gen', 'eps_req', 'eps_eff'):
                original = selection.pop(field)
                with self.subTest(missing=field), self.assertRaises(RuntimeError): tx.verify_runtime(cli, topics.__getitem__)
                selection[field] = original
            for field, value in [('sta_pending', None), ('sta_reject', 2), ('sta_gen', -1), ('sta_gen', 0),
                                 ('sta_gen', True), ('sta_gen', 1.5), ('eps_req', [.01]), ('eps_eff', []),
                                 ('eps_eff', ['.01', .01, .02])]:
                original = selection[field]; selection[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(RuntimeError): tx.verify_runtime(cli, topics.__getitem__)
                selection[field] = original
            selection['eps_eff'][0] = .02
            with self.assertRaises(RuntimeError): tx.verify_runtime(cli, topics.__getitem__)
            selection['eps_eff'][0] = .01
            inner['effective_mode'] = 1
            with self.assertRaises(RuntimeError): tx.verify_runtime(cli, topics.__getitem__)
            inner['effective_mode'] = 0; selection['effective_mode'] = 0
            with self.assertRaises(RuntimeError): tx.verify_runtime(cli, topics.__getitem__)
        self.assertEqual(store.read(), raw)

    def test_reject_live_eeprom_or_armed_switch(self):
        c, raw, store, tx = self.setup_transaction(); tx.is_stopped = lambda: False
        with self.assertRaises(RuntimeError): tx.__enter__()
        self.assertEqual(store.writes, [])

    def test_pid_metadata_is_required_but_unused_gain_reject_is_allowed(self):
        c, raw, store, tx = self.setup_transaction(0, 0)
        with tx:
            expected = tx.apply(c)
            cli = lambda *args: '\n'.join(f'{k} [0,0] : {v}' for k, v in expected.items())
            inner = dict(requested_mode=0, effective_mode=0, requested_axes=0, effective_axes=0, div_req=1, div_eff=1,
                         fault=0, abort_requested=0, termination=0, armed=False)
            selection = dict(requested_mode=0, effective_mode=0, requested_axes=0, effective_axes=0, div_req=1, div_eff=1,
                             pending=0, reject=0, variant_req=0, variant_eff=0, sta_pending=0, sta_reject=1,
                             sta_gen=0, eps_req=[.01, .01, .02], eps_eff=[float('nan')] * 3)
            topics = {'vehicle_status': {'arming_state': 1}, 'vehicle_land_detected': {'landed': True},
                      'sta_rate_ctrl_status': inner, 'velocity_ctrl_selection': selection}
            tx.verify_runtime(cli, topics.__getitem__)
            selection['sta_gen'] = 5; tx.verify_runtime(cli, topics.__getitem__)
            del selection['eps_eff']
            with self.assertRaisesRegex(RuntimeError, 'Missing runtime'): tx.verify_runtime(cli, topics.__getitem__)
        self.assertEqual(store.read(), raw)

    def test_restore_deferred_while_running_keeps_backup(self):
        c, raw, store, tx = self.setup_transaction()
        with self.assertRaisesRegex(RuntimeError, 'still running'):
            with tx:
                tx.apply(c); tx.is_stopped = lambda: False
        self.assertEqual(tx.original, raw); self.assertNotEqual(store.read(), raw)
        self.assertTrue(tx.receipt['restore_deferred_running'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
