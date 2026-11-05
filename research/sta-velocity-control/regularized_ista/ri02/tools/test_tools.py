#!/usr/bin/env python3
"""Offline fixtures and negative tests: these are NOT new flight samples."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

import analyzer
import configuration
import dependencies
import parameters
import run
import replay
import full_chain


def fixture(axes=1, count=720):
    profile = configuration.candidate(4, axes)
    p = profile['parameters']
    time = np.arange(1, count + 1, dtype=np.uint64) * 10000 + 1000000
    x, q = {}, {}
    for d in (x, q):
        d.update(timestamp=time.copy(), timestamp_sample=time.copy(), input_timestamp=time.copy(),
                 publish_seq=np.arange(1, count + 1, dtype=np.uint32))
        for key, value in dict(requested_mode=4, effective_mode=4, requested_axes=axes, effective_axes=axes,
                               pending=0, reject=0, armed=1, enabled=1, pid_calls=1).items():
            d[key] = np.full(count, value, dtype=np.int32)
    for key, value in dict(inner_mode=0, inner_axes=0, inner_divisor=1, inner_valid=1, fault=0,
                           failsafe=0, timing=0, sta_fault=0, config_pending=0, valid=1, active_axes=axes,
                           committed_axes=axes, pid_axes=7 ^ axes, reset_bits=0, constraint_bits=0,
                           config_generation=1, z_phase=3 if axes & 4 else 0, sta_flags=0).items():
        x[key] = np.full(count, value, dtype=np.int32)
    x['update_seq'] = np.arange(1, count + 1, dtype=np.uint32)
    for key in ('raw_dt', 'input_dt', 'used_dt'):
        x[key] = np.full(count, np.float32(.01), dtype=np.float32)
    x['z_hte_shift'] = np.zeros(count, dtype=np.float32)
    for key, value in dict(ri_version=1, variant_req=4, variant_eff=4, sta_pending=0, sta_reject=0,
                           div_req=1, div_eff=1, div_pending=0, div_reject=0, control_fault=0, clock=1,
                           control_updated=1, control_held=0, sta_gen=1, ri_valid=1,
                           ri_strict_axes=axes, ri_commit_axes=axes, ri_cache_valid=int(bool(axes & 4)),
                           interval_pos=0, interval_neg=0).items():
        q[key] = np.full(count, value, dtype=np.int32)
    q['control_seq'] = np.arange(1, count + 1, dtype=np.uint32)
    q['ri_h'] = x['raw_dt'].copy()
    q['h'] = x['used_dt'].copy()
    q['ri_seed_h'] = np.full(count, np.nan, dtype=np.float32)
    q['ri_cache_sample'] = time.copy() if axes & 4 else np.zeros(count, dtype=np.uint64)
    for key in ('path_ns', 'module_ns'):
        q[key] = np.full(count, 1000, dtype=np.uint64)
    for axis, suffix in enumerate('XYZ'):
        selected = axes & (1 << axis)
        l1, l2, epsilon = [np.float32(p[f'MPC_VC_{key}_{suffix}']) for key in ('L1', 'L2', 'EPS')]
        s, h = np.float32(.001), np.float32(.01)
        # Independent monotone bisection; no production analytic root copied.
        lo, hi = 0., float(s)
        for _ in range(100):
            mid = (lo + hi) * .5
            psi, rho = analyzer.shape(np.array([mid]), float(epsilon))
            if mid + float(h * l1) * psi[0] + float(h * h * l2) * rho[0] > float(s):
                hi = mid
            else:
                lo = mid
        root = np.float32((lo + hi) * .5)
        psi, rho = analyzer.shape(np.array([root], dtype=np.float64), float(epsilon))
        before, nxt, ideal = [], [], []
        nu = np.float32(.02)
        for _ in range(count):
            before.append(nu)
            nu = np.float32(nu - np.float32(h * l2 * np.float32(rho[0])))
            nxt.append(nu)
            ideal.append(np.float32(-l1 * np.float32(psi[0]) + nu))
        before, nxt, ideal = map(lambda a: np.asarray(a, dtype=np.float32), (before, nxt, ideal))
        correction = ideal if selected else np.full(count, .02, dtype=np.float32)
        ff = np.full(count, np.float32(.03), dtype=np.float32)
        actual = correction + ff
        for name, values in dict(s=np.full(count, s), v=np.full(count, s), v_sp=np.zeros(count),
                                  v_dot=np.zeros(count), nu_before=before, nu_ideal=nxt, nu_applied=nxt,
                                  a_sta=ideal, a_ff=ff, a_req=actual, a_proxy=actual,
                                  thrust=np.full(count, -.5 if axis == 2 else .001)).items():
            if not selected and name in ('nu_before', 'nu_ideal', 'nu_applied', 'a_sta'):
                values = np.full(count, np.nan)
            x[f'{name}[{axis}]'] = np.array(values, dtype=np.float32, copy=True)
        for name, values in dict(ri_p=np.full(count, root), ri_nu_candidate=nxt, ri_nu_applied=nxt,
                                  ri_a_ideal=ideal, ri_a_applied=correction,
                                  ri_acc_published=actual, ri_thrust_published=x[f'thrust[{axis}]']).items():
            if not selected and name not in ('ri_acc_published', 'ri_thrust_published', 'ri_a_applied'):
                values = np.full(count, np.nan)
            q[f'{name}[{axis}]'] = np.array(values, dtype=np.float32, copy=True)
        q[f'correction[{axis}]'] = correction.copy()
        q[f'eps_req[{axis}]'] = np.full(count, epsilon, dtype=np.float32)
        q[f'eps_eff[{axis}]'] = np.full(count, epsilon if selected else np.nan, dtype=np.float32)
    return x, q, profile, int(time[1]), int(time[-2])


class ConfigurationTests(unittest.TestCase):
    def test_all_three_algorithms_complete_profiles(self):
        for mode in (0, 3, 4):
            for axes in ((0,) if mode == 0 else (1, 4, 3, 7)):
                p = configuration.candidate(mode, axes)
                self.assertEqual(len(p['parameters']), 127)
                self.assertFalse(p['flight_authorized'])
                self.assertEqual(p['maximum_attempts'], 0)

    def test_bad_modes(self):
        for mode in (1, 2, -1, 5, True, 4.):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                configuration.candidate(mode, 1)

    def test_bad_axes(self):
        for axes in (0, 2, 5, 6, 8, -1, True):
            with self.subTest(axes=axes), self.assertRaises(ValueError):
                configuration.candidate(4, axes)

    def test_full_profile_required(self):
        p = configuration.candidate(4, 1)
        del p['parameters']['MPC_VC_L1_Z']
        with self.assertRaises(ValueError):
            configuration.validate(4, 1, p['parameters'])

    def test_invalid_gains(self):
        for value in (0, -1, float('nan'), float('inf'), True):
            p = configuration.candidate(4, 1)
            p['parameters']['MPC_VC_L1_X'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                configuration.validate(4, 1, p['parameters'])

    def test_inner_and_div_fixed(self):
        for key in configuration.RATE:
            p = configuration.candidate(4, 1)
            p['parameters'][key] += 1
            with self.subTest(key=key), self.assertRaises(ValueError):
                configuration.validate(4, 1, p['parameters'])

    def test_default_dry_run(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            self.assertEqual(run.main([]), 0)
        payload = json.loads(stream.getvalue())
        self.assertTrue(payload['dry_run'])
        self.assertFalse(payload['starts_simulator'])
        self.assertEqual(payload['mode'], 0)

    def test_execute_never_unlocked(self):
        with self.assertRaisesRegex(RuntimeError, 'OFFLINE ONLY'):
            run.main(['--execute', '--source-head', 'a' * 40, '--qualification', '/tmp/fake', '--manifest', '/tmp/fake'])


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.x, self.q, self.p, self.start, self.end = fixture()

    def check(self, steady=True):
        return analyzer.check(self.x, self.q, self.p, self.start, self.end, steady=steady)

    def test_compensated_candidate(self):
        result = self.check()
        self.assertTrue(result['component_valid'])
        self.assertFalse(result['flight_accepted'])

    def test_four_candidate_masks(self):
        for axes in (1, 4, 3, 7):
            self.x, self.q, self.p, self.start, self.end = fixture(axes)
            with self.subTest(axes=axes):
                self.check()

    def test_same_publication_two_distinct_samples(self):
        # Later sample timestamps retained. Equal publication must not dedup.
        for d in (self.x, self.q):
            for key in ('timestamp', 'input_timestamp'):
                d[key][20] = d[key][21]
        self.check()

    def test_duplicate_sample_rejected(self):
        for d in (self.x, self.q):
            d['timestamp_sample'][21] = d['timestamp_sample'][20]
        with self.assertRaises(ValueError):
            self.check()

    def test_backward_publication_rejected(self):
        self.q['timestamp'][21] = self.q['timestamp'][19]
        with self.assertRaises(ValueError):
            self.check()

    def test_future_sample_rejected(self):
        self.q['input_timestamp'][21] -= 1
        with self.assertRaises(ValueError):
            self.check()

    def test_gap_sequence_rejected(self):
        self.q['publish_seq'][21:] += 1
        with self.assertRaises(ValueError):
            self.check()

    def test_missing_selection_rejected(self):
        self.q = {k: np.delete(v, 21) for k, v in self.q.items()}
        with self.assertRaises(ValueError):
            self.check()

    def test_wrong_mode_rejected(self):
        self.q['effective_mode'][100] = self.x['effective_mode'][100] = 3
        with self.assertRaises(ValueError):
            self.check()

    def test_wrong_axes_rejected(self):
        self.q['effective_axes'][100] = self.x['effective_axes'][100] = 7
        with self.assertRaises(ValueError):
            self.check()

    def test_wrong_inner_rejected(self):
        for key, value in (('inner_mode', 1), ('inner_axes', 1), ('inner_divisor', 2), ('inner_valid', 0)):
            with self.subTest(key=key):
                old = self.x[key][100]
                self.x[key][100] = value
                with self.assertRaises(ValueError):
                    self.check()
                self.x[key][100] = old

    def test_raw_dt_and_kernel_dt(self):
        for key in ('raw_dt', 'ri_h', 'h'):
            d = self.x if key == 'raw_dt' else self.q
            old = d[key][100]
            d[key][100] = .012
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check()
            d[key][100] = old

    def test_host_clock_zero_or_negative_rejected(self):
        for key in ('path_ns', 'module_ns'):
            self.q[key] = self.q[key].astype(np.int64)
            for value in (0, -1):
                self.q[key][100] = value
                with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, 'host clock'):
                    self.check()
            self.q[key][100] = 1000

    def test_unaccepted_generation_rejected(self):
        self.q['sta_gen'][:] = self.x['config_generation'][:] = 0
        with self.assertRaisesRegex(ValueError, 'Generation'):
            self.check()

    def test_unselected_epsilon_or_legacy_state_rejected(self):
        for data, key in ((self.q, 'eps_eff[1]'), (self.x, 'nu_before[1]'),
                          (self.x, 'nu_ideal[1]'), (self.x, 'nu_applied[1]'), (self.x, 'a_sta[1]')):
            data[key][100] = 0
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'unselected|PID axis'):
                self.check()
            data[key][100] = np.nan

    def test_steady_lifecycle_flags_rejected(self):
        for bit in (1, 2, 4, 64, 128, 256):
            self.x['sta_flags'][100] = bit
            with self.subTest(bit=bit), self.assertRaisesRegex(ValueError, 'Steady'):
                self.check()

    def test_div1_invented_interval_bits_rejected(self):
        for key in ('interval_pos', 'interval_neg'):
            self.q[key][100] = 1
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'invented interval'):
                self.check()
            self.q[key][100] = 0

    def test_inactive_callback_cannot_claim_invocation(self):
        self.x['enabled'][100] = self.q['enabled'][100] = 0
        with self.assertRaisesRegex(ValueError, 'inactive invocation'):
            self.check(steady=False)

    def test_candidate_validity_is_bidirectional(self):
        self.x['sta_flags'][100] = 1
        self.x['committed_axes'][100] = self.q['ri_commit_axes'][100] = 0
        with self.assertRaisesRegex(ValueError, 'Candidate validity'):
            self.check(steady=False)
        self.x['committed_axes'][100] = self.q['ri_commit_axes'][100] = 1
        self.q['ri_valid'][100] = 0
        with self.assertRaisesRegex(ValueError, 'Candidate validity'):
            self.check(steady=False)

    def test_absent_candidate_payload_rejected(self):
        self.x['sta_flags'][100] = 1
        self.x['committed_axes'][100] = self.q['ri_commit_axes'][100] = 0
        self.q['ri_valid'][100] = self.q['ri_strict_axes'][100] = 0
        with self.assertRaisesRegex(ValueError, 'Absent candidate'):
            self.check(steady=False)
        self.q['ri_nu_candidate[0]'][100] = self.q['ri_a_ideal[0]'][100] = np.nan
        with self.assertRaisesRegex(ValueError, 'Absent candidate/seed carries root'):
            self.check(steady=False)

    def test_predecessor_reset_not_hidden(self):
        self.x['reset_bits'][0] = 1
        with self.assertRaisesRegex(ValueError, 'boundary'):
            self.check()

    def test_end_boundary_fault_not_hidden(self):
        self.x['fault'][-2] = 1
        with self.assertRaisesRegex(ValueError, 'boundary'):
            self.check()

    def test_missing_boundary(self):
        self.start = int(self.x['timestamp'][0])
        with self.assertRaises(ValueError):
            self.check()

    def test_steady_not_engaged(self):
        self.x['active_axes'][100] = 0
        with self.assertRaises(ValueError):
            self.check()

    def test_partial_atomic_commit(self):
        self.x, self.q, self.p, self.start, self.end = fixture(7)
        self.x['committed_axes'][100] = self.q['ri_commit_axes'][100] = 3
        with self.assertRaises(ValueError):
            self.check(steady=False)

    def test_old_nu_output_rejected(self):
        self.q['ri_a_ideal[0]'] += self.x['nu_before[0]'] - self.q['ri_nu_candidate[0]']
        with self.assertRaisesRegex(ValueError, 'candidate nu'):
            self.check()

    def test_wrong_implicit_root(self):
        self.q['ri_p[0]'][100] += .01
        with self.assertRaisesRegex(ValueError, 'root residual'):
            self.check()

    def test_wrong_candidate(self):
        self.q['ri_nu_candidate[0]'][100] += .01
        with self.assertRaises(ValueError):
            self.check()

    def test_foreign_applied_state(self):
        self.q['ri_nu_applied[0]'][100] += .01
        with self.assertRaises(ValueError):
            self.check()

    def test_ff_twice(self):
        self.x['a_req[0]'] += self.x['a_ff[0]']
        with self.assertRaisesRegex(ValueError, 'FF'):
            self.check()

    def test_wrong_published_output(self):
        for key in ('ri_acc_published[0]', 'ri_thrust_published[0]'):
            old = self.q[key][100]
            self.q[key][100] += .01
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check()
            self.q[key][100] = old

    def test_stale_nu(self):
        # Keep every current-row formula correct while breaking previous state.
        for key in ('nu_before[0]', 'nu_ideal[0]', 'nu_applied[0]'):
            self.x[key][100] += .1
        for key in ('ri_nu_candidate[0]', 'ri_nu_applied[0]', 'ri_a_ideal[0]', 'ri_a_applied[0]', 'correction[0]', 'ri_acc_published[0]'):
            self.q[key][100] += .1
        self.x['a_req[0]'][100] += .1
        with self.assertRaises(ValueError):
            self.check()

    def test_missing_schema(self):
        self.q['ri_version'][100] = 0
        with self.assertRaises(ValueError):
            self.check()

    def test_fake_strict_claim(self):
        self.q['ri_strict_axes'][100] = 7
        with self.assertRaises(ValueError):
            self.check()

    def test_invalid_cache_identity_and_boolean(self):
        self.q['ri_cache_sample'][100] = self.q['timestamp_sample'][100]
        with self.assertRaisesRegex(ValueError, 'cache sample'):
            self.check()
        self.q['ri_cache_sample'][100] = 0
        self.q['ri_valid'][100] = 2
        with self.assertRaisesRegex(ValueError, 'boolean'):
            self.check()

    def test_half_enabled_xy_rejected(self):
        self.x['v_sp[1]'][100] = np.nan
        self.x['s[1]'][100] = np.nan
        with self.assertRaisesRegex(ValueError, 'Half-enabled'):
            self.check()

    def test_constrained_pair_not_strict(self):
        self.x['constraint_bits'][100] = 1
        with self.assertRaisesRegex(ValueError, 'strict implicit'):
            self.check()
        self.q['ri_strict_axes'][100] = 0
        self.check()

    def test_ground_state_reset(self):
        x, q, p, _, _ = fixture(7)
        x, q = ({k: v[:1].copy() for k, v in d.items()} for d in (x, q))
        x['z_phase'][:] = 1
        x['sta_flags'][:] = 2
        x['active_axes'][:] = x['committed_axes'][:] = 0
        x['pid_axes'][:] = 7
        for i in range(3):
            q[f'ri_nu_applied[{i}]'][:] = 0
        analyzer.lifecycle(x, q, p)
        q['ri_nu_applied[2]'][:] = .1
        with self.assertRaisesRegex(ValueError, 'did not reset'):
            analyzer.lifecycle(x, q, p)

    def test_implicit_seed_inverse(self):
        x, q, p, _, _ = fixture(7)
        x, q = ({k: v[:1].copy() for k, v in d.items()} for d in (x, q))
        x['z_phase'][:] = 2
        x['sta_flags'][:] = 1
        x['active_axes'][:] = x['committed_axes'][:] = 0
        x['pid_axes'][:] = 7
        q['ri_seed_h'][:] = .01
        q['ri_valid'][:] = q['ri_strict_axes'][:] = 0
        for i, suffix in enumerate('XYZ'):
            psi, rho = analyzer.shape(q[f'ri_p[{i}]'], p['parameters']['MPC_VC_EPS_' + suffix])
            q[f'ri_nu_applied[{i}]'][:] = q[f'correction[{i}]'] + p['parameters']['MPC_VC_L1_' + suffix] * psi + q['ri_seed_h'] * p['parameters']['MPC_VC_L2_' + suffix] * rho
            q[f'ri_nu_candidate[{i}]'][:] = q[f'ri_a_ideal[{i}]'][:] = np.nan
        analyzer.lifecycle(x, q, p)
        q['ri_nu_applied[2]'] += .01
        with self.assertRaisesRegex(ValueError, 'seed inverse'):
            analyzer.lifecycle(x, q, p)

    def test_per_axis_lifecycle_hte_xy_z_xyz(self):
        for axes in (3, 4, 7):
            x, q, p, _, _ = fixture(axes, count=2)
            if axes & 4:
                x['z_hte_shift'][1] = np.float32(.01)
                x['nu_before[2]'][1] = np.float32(q['ri_nu_applied[2]'][0] + x['z_hte_shift'][1])
            with self.subTest(axes=axes):
                analyzer.lifecycle(x, q, p)
            for axis in range(3):
                if axes & (1 << axis):
                    original = x[f'nu_before[{axis}]'][1]
                    x[f'nu_before[{axis}]'][1] += np.float32(.01)
                    with self.subTest(axes=axes, axis=axis), self.assertRaisesRegex(ValueError, 'continuity/HTE'):
                        analyzer.lifecycle(x, q, p)
                    x[f'nu_before[{axis}]'][1] = original

    def test_xy_cannot_claim_z_hte(self):
        x, q, p, _, _ = fixture(3, count=2)
        x['z_hte_shift'][1] = np.float32(.01)
        with self.assertRaisesRegex(ValueError, 'Unselected Z lifecycle/HTE'):
            analyzer.lifecycle(x, q, p)

    def test_unavailable_mode4_evidence(self):
        for d in (self.x, self.q):
            d['effective_mode'][:] = d['effective_axes'][:] = 0
            d['reject'][:] = 2
        self.q['ri_valid'][:] = self.q['ri_commit_axes'][:] = 0
        for key in analyzer.RI_VECTORS:
            for i in range(3):
                self.q[f'ri_{key}[{i}]'][:] = np.nan
        self.assertTrue(analyzer.closed_admission(self.x, self.q)['valid'])
        self.q['effective_mode'][:] = self.x['effective_mode'][:] = 4
        with self.assertRaises(ValueError):
            analyzer.closed_admission(self.x, self.q)

    def test_complete_same_tick_output_groups(self):
        cb = dependencies.callbacks()
        a, b = cb.grouped_indices(np.array([1, 2, 2, 3]), np.array([1, 2, 2, 3]))
        self.assertEqual(a.tolist(), [0, 1, 2, 3])
        self.assertEqual(b.tolist(), [0, 1, 2, 3])

    def test_ambiguous_same_tick_group_rejected(self):
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            dependencies.callbacks().grouped_indices(np.array([1, 2, 2, 3]), np.array([1, 2, 3]))

    def test_ambiguous_yaw_rejected(self):
        d = dict(timestamp=np.array([1, 2, 2, 3]), yaw_body=np.array([0., .1, .2, .3]))
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            dependencies.callbacks().yaw_previous(d, np.array([2, 3]))


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.profile = configuration.candidate(4, 1)
        self.types = {k: 'Int32' if type(v) is int else 'Float' for k, v in self.profile['parameters'].items()}
        self.types['UNRELATED_TEST'] = 'Float'
        self.types['SDLOG_PROFILE'] = 'Int32'
        self.path = self.root / 'test.bson'
        self.original = dependencies.parameter_io().encode_bson(dict(UNRELATED_TEST=3.25, SDLOG_PROFILE=8192), self.types)
        self.path.write_bytes(self.original)
        self.store = parameters.FileStore(self.path, self.root)
        self.stopped = True

    def tearDown(self):
        self.tmp.cleanup()

    def transaction(self):
        return parameters.ParameterTransaction(self.store, self.types, {}, lambda: self.stopped, self.root / 'backup')

    def test_full_backup_restore_and_unrelated_logger_bits(self):
        with self.transaction() as t:
            values = t.apply(self.profile)
            self.assertEqual(values['UNRELATED_TEST'], 3.25)
            self.assertTrue(values['SDLOG_PROFILE'] & 8192)
            self.assertTrue(values['SDLOG_PROFILE'] & 1024)
            self.assertEqual((self.root / 'backup/original.bson').read_bytes(), self.original)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertTrue(t.receipt['restore_exact'])

    def test_exception_restores_exactly(self):
        with self.assertRaisesRegex(RuntimeError, 'test failure'):
            with self.transaction() as t:
                t.apply(self.profile)
                raise RuntimeError('test failure')
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_running_entry_refused(self):
        self.stopped = False
        with self.assertRaises(RuntimeError):
            with self.transaction():
                pass
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_running_exit_keeps_durable_backup(self):
        with self.assertRaisesRegex(RuntimeError, 'durable backup'):
            with self.transaction() as t:
                t.apply(self.profile)
                self.stopped = False
        self.assertEqual((self.root / 'backup/original.bson').read_bytes(), self.original)
        self.assertTrue(t.receipt['restore_deferred_running'])

    def test_missing_type_refused_before_write(self):
        del self.types['UNRELATED_TEST']
        with self.assertRaises(ValueError):
            with self.transaction() as t:
                t.apply(self.profile)
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_real_rootfs_backend_forbidden(self):
        with self.assertRaises(ValueError):
            parameters.FileStore(dependencies.REPO / 'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016', dependencies.REPO)

    def test_existing_backup_never_overwritten(self):
        (self.root / 'backup').mkdir()
        with self.assertRaises(FileExistsError):
            with self.transaction():
                pass

    def test_exact_types_required(self):
        self.types['MPC_VC_MODE'] = 'INT32'
        with self.assertRaisesRegex(ValueError, 'Exact PX4'):
            with self.transaction() as t:
                t.apply(self.profile)

    def test_runtime_request_refusal_and_parameter_readback(self):
        with self.transaction() as t:
            values = t.apply(self.profile)
            cli = lambda *args: '\n'.join(f'{k} [1] : {v}' for k, v in values.items())
            topics = dict(vehicle_status=dict(arming_state=1), vehicle_land_detected=dict(landed=True),
                          sta_rate_ctrl_status=dict(requested_mode=0, requested_axes=0, effective_mode=0,
                                                    effective_axes=0, div_req=1, div_eff=1, fault=0,
                                                    abort_requested=0, termination=0),
                          velocity_ctrl_selection=dict(requested_mode=4, requested_axes=1, effective_mode=0,
                                                        effective_axes=0, div_req=1, div_eff=1, pending=0,
                                                        reject=2, variant_req=4, ri_version=1, sta_gen=1,
                                                        variant_eff=0, sta_pending=0, sta_reject=0,
                                                        div_pending=0, div_reject=0, control_fault=0,
                                                        ri_valid=0, ri_commit_axes=0, eps_req=[.01, .01, .02],
                                                        eps_eff=[np.nan, np.nan, np.nan]))
            t.verify_readback(cli, topics.__getitem__, expected_rejected_mode4=True)
            self.assertTrue(t.receipt['mode4_rejection_verified'])
            for key, value in [('effective_mode', 4), ('reject', 0), ('ri_valid', 1), ('ri_commit_axes', 1),
                               ('ri_version', 0), ('eps_req', []), ('variant_eff', 3), ('sta_pending', 1),
                               ('eps_eff', [.01, np.nan, np.nan])]:
                q = topics['velocity_ctrl_selection']
                old = q[key]
                q[key] = value
                with self.subTest(key=key), self.assertRaises(RuntimeError):
                    t.verify_readback(cli, topics.__getitem__, expected_rejected_mode4=True)
                q[key] = old
            topics['sta_rate_ctrl_status']['effective_mode'] = 1
            with self.assertRaisesRegex(RuntimeError, 'Inner PID'):
                t.verify_readback(cli, topics.__getitem__, expected_rejected_mode4=True)

    def existing_topics(self, mode, axes):
        return dict(vehicle_status=dict(arming_state=1), vehicle_land_detected=dict(landed=True),
                    sta_rate_ctrl_status=dict(requested_mode=0, requested_axes=0, effective_mode=0,
                        effective_axes=0, div_req=1, div_eff=1, fault=0, abort_requested=0, termination=0),
                    velocity_ctrl_selection=dict(requested_mode=mode, requested_axes=axes,
                        effective_mode=mode, effective_axes=axes, div_req=1, div_eff=1, pending=0,
                        div_pending=0, div_reject=0, control_fault=0, reject=0, variant_req=mode,
                        variant_eff=mode, ri_version=1, sta_gen=int(mode != 0), sta_pending=0,
                        sta_reject=int(mode == 0), ri_valid=0, ri_commit_axes=0,
                        eps_req=[.01, .01, .02],
                        eps_eff=[eps if mode == 3 and axes & (1 << i) else np.nan
                                 for i, eps in enumerate((.01, .01, .02))]))

    def test_pid_effective_readback_and_unused_gain_reject(self):
        with self.transaction() as t:
            values = t.apply(configuration.candidate(0, 0))
            cli = lambda *args: '\n'.join(f'{k} [1] : {v}' for k, v in values.items())
            topics = self.existing_topics(0, 0)
            t.verify_readback(cli, topics.__getitem__)
            self.assertTrue(t.receipt['runtime_verified'])

    def test_rsta_effective_configuration_readback(self):
        with self.transaction() as t:
            values = t.apply(configuration.candidate(3, 3))
            cli = lambda *args: '\n'.join(f'{k} [1] : {v}' for k, v in values.items())
            topics = self.existing_topics(3, 3)
            t.verify_readback(cli, topics.__getitem__)
            q = topics['velocity_ctrl_selection']
            for key, wrong in [('variant_eff', 0), ('sta_pending', 1), ('sta_reject', 1),
                               ('sta_gen', 0), ('div_pending', 1), ('div_reject', 1),
                               ('eps_eff', [.02, .01, np.nan]), ('eps_eff', [.01, .01, .02])]:
                previous = q[key]
                q[key] = wrong
                with self.subTest(key=key), self.assertRaises(RuntimeError):
                    t.verify_readback(cli, topics.__getitem__)
                q[key] = previous

    def test_rejected_mode4_retained_rsta_requires_explicit_prior_profile(self):
        with self.transaction() as t:
            values = t.apply(self.profile)
            cli = lambda *args: '\n'.join(f'{k} [1] : {v}' for k, v in values.items())
            topics = self.existing_topics(3, 3)
            q = topics['velocity_ctrl_selection']
            q.update(requested_mode=4, requested_axes=1, variant_req=4, reject=2)
            with self.assertRaisesRegex(RuntimeError, 'retained configuration required'):
                t.verify_readback(cli, topics.__getitem__, expected_rejected_mode4=True)
            prior = configuration.candidate(3, 3)
            t.verify_readback(cli, topics.__getitem__, expected_rejected_mode4=True, retained_configuration=prior)
            prior['parameters']['MPC_VC_EPS_X'] = .02
            with self.assertRaisesRegex(RuntimeError, 'effective epsilon'):
                t.verify_readback(cli, topics.__getitem__, expected_rejected_mode4=True, retained_configuration=prior)


class FullChainTests(unittest.TestCase):
    def job(self, axes=1):
        job = configuration.candidate(4, axes)
        gate, task, test, duration = {1: ('A', 'X', 1, 32), 4: ('B', 'Z', 2, 32),
                                    3: ('C', 'H', 6, 64), 7: ('D', 'V', 8, 64)}[axes]
        job.update(gate=gate, task=task, divisor=1, main_duration_s=duration)
        job['parameters']['MPC_VCT_TEST'] = test
        return job

    def fixture(self):
        x, q, _, start, end = fixture()
        x['inner_timestamp'] = x['timestamp_sample'].copy()
        x['inner_check_timestamp'] = x['timestamp_sample'].copy()
        x['inner_seq'] = x['publish_seq'].copy()
        x['inner_reads'] = np.ones(len(x['timestamp']), dtype=np.int32)
        x['hover_thrust'] = np.full(len(x['timestamp']), .5, dtype=np.float32)
        for i in range(3):
            x[f'thrust[{i}]'] = (x[f'a_proxy[{i}]'] - (9.80665 if i == 2 else 0)) * .5 / 9.80665
            q[f'ri_thrust_published[{i}]'] = x[f'thrust[{i}]'].copy()
        return x, q, self.job(), start, end

    def test_real_bound_new_mode_components(self):
        x, q, job, start, end = self.fixture()
        result, _, _ = full_chain.components(x, q, job, start, end, True)
        self.assertTrue(result['cadence']['component_valid'])
        self.assertFalse(result['cadence']['flight_accepted'])

    def test_full_binding_retains_final_whole_chain(self):
        final = dependencies.final_analysis()
        original = final.full_analysis(lambda *args: {}, lambda *args: None)
        private = full_chain.build(lambda *args: {}, lambda *args: None)
        self.assertIs(private.__globals__['check_components'], full_chain.components)
        for name in ('height_evidence', 'check_complete', 'check_health', 'exact_output_match', 'ULog', 'r02'):
            self.assertIs(private.__globals__[name], original.__globals__[name])
        self.assertIs(private.__globals__['spec'], full_chain.spec)
        self.assertIsNot(original.__globals__['check_components'], full_chain.components)

    def test_target_mode_domain_only_private(self):
        for axes in (1, 4, 3, 7):
            job = self.job(axes)
            self.assertEqual(full_chain.spec(job)[1], axes)
            with self.assertRaises(ValueError):
                dependencies.final_analysis().targets.spec(job)
        bound = full_chain.targets()
        self.assertIs(bound.__globals__['spec'], full_chain.spec)
        for name in ('check_waveform', 'check_position_sum', 'attitude_match'):
            self.assertIs(bound.__globals__[name].__globals__['spec'], full_chain.spec)

    def test_new_chain_wrong_mode_axes_inner_time_missing_unengaged(self):
        cases = ('mode', 'axes', 'inner', 'time', 'missing', 'unengaged')
        for case in cases:
            x, q, job, start, end = self.fixture()
            if case == 'mode':
                x['effective_mode'][100] = q['effective_mode'][100] = 3
            elif case == 'axes':
                x['effective_axes'][100] = q['effective_axes'][100] = 7
            elif case == 'inner':
                x['inner_timestamp'][100] = 0
            elif case == 'time':
                x['timestamp_sample'][100] = x['timestamp_sample'][99]
            elif case == 'missing':
                q = {k: np.delete(v, 100) for k, v in q.items()}
            else:
                x['active_axes'][100] = 0
            with self.subTest(case=case), self.assertRaises(ValueError):
                full_chain.components(x, q, job, start, end, True)

    def test_no_old_batch_or_qualification_can_unlock_full_entry(self):
        with self.assertRaises(ValueError):
            full_chain.full_offline_analysis('/tmp/batch01/run001', '/tmp/new',
                dict(stage='RI02-offline', flight_authorized=False), self.job())
        with self.assertRaises(ValueError):
            full_chain.full_offline_analysis('/tmp/experiments/RI02/new', '/tmp/another',
                dict(stage='qualified', flight_authorized=True), self.job())

    def test_exact_float_nu_primitive_large_state(self):
        found = None
        old, h, l2, eps = map(np.float32, (4., .012, 1., .02))
        for p in np.linspace(-.02, -.001, 200, dtype=np.float32):
            rho = np.float32(p / eps)
            nxt = np.float32(old - np.float32(np.float32(h * l2) * rho))
            error = abs(float(nxt) - (float(old) - float(h) * float(l2) * float(p) / float(eps)))
            if error > 2e-7:
                found = (p, nxt)
                break
        self.assertIsNotNone(found, 'Fixture must expose fixed absolute-nu tolerance limitation')
        p, nxt = found
        analyzer.candidate_nu(p, h, 1., eps, old, nxt, .02)
        with self.assertRaises(ValueError):
            analyzer.candidate_nu(p, h, 1., eps, old, np.nextafter(nxt, np.float32(np.inf)), .02)

    def test_exact_description_only_whitelist(self):
        old = dict(attitude=dict(association='unique exact publication intersection', matched=20))
        new = dict(attitude=dict(association='complete equal-time groups in single-publisher order; exact payload and callback identity', matched=20))
        self.assertTrue(replay.science_equal('task_targets', new, old, 'r03_revision09'))
        self.assertFalse(replay.science_equal('task_targets', new, old, 'r03_revision11'))
        new['attitude']['matched'] = 20.
        self.assertFalse(replay.science_equal('task_targets', new, old, 'r03_revision09'))
        new['attitude']['matched'] = 19
        self.assertFalse(replay.science_equal('task_targets', new, old, 'r03_revision09'))

    def test_unknown_description_not_ignored(self):
        old = dict(attitude=dict(association='unexpected old'))
        new = dict(attitude=dict(association='unexpected new'))
        self.assertFalse(replay.science_equal('task_targets', new, old, 'r03_revision09'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
