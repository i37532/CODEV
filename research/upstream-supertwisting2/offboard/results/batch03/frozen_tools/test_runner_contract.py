"""Offline admission and state checks; temporary receipts never launch anything."""

import copy
import json
import math
from pathlib import Path
import tempfile
import unittest

import runner_contract as r
from task_contract import BATCH_ORDER, ENTRY_LIMITS, PHASE_DURATION_S, SAFETY_LIMITS


ORIGIN = dict(x=0.0, y=0.0, z=0.0, heading=0.0)


def manifest(root='/tmp/codev-offboard-contract-unexecuted'):
    jobs = []
    for index, (task, system) in enumerate(BATCH_ORDER, 1):
        parameters = dict(MIS_TAKEOFF_ALT=2.5, SDLOG_MODE=1)
        if system != 'STA2':
            parameters.update(MPC_VC_MODE={'PID': 0, 'RSTA': 3, 'RISTA': 4}[system],
                MPC_VC_AXES=0 if system == 'PID' else 7, MPC_VC_DIV=1, MC_RTC_MODE=0,
                MC_STA_AXES=0, MC_RTC_DIV=1, MC_RATT_TEST=0, MPC_VCT_TEST=0)
        diagnostic = {'attitude_sta_status': {}} if system == 'STA2' else {
            'sta_velocity_ctrl_status': dict(effective_mode=parameters['MPC_VC_MODE'],
                                             effective_axes=parameters['MPC_VC_AXES']),
            'sta_rate_ctrl_status': dict(effective_mode=0, effective_axes=0)}
        hover = copy.deepcopy(diagnostic)
        if system != 'STA2':
            hover['sta_velocity_ctrl_status'].update(active_axes=parameters['MPC_VC_AXES'],
                                                    inner_mode=0, inner_axes=0, fault=0)
            hover['sta_rate_ctrl_status'].update(fault=0)
        jobs.append(dict(id='O%03d' % index, task=task, system=system,
            label='Upstream STA2' if system == 'STA2' else system,
            repo='/tmp/frozen-source-' + system, bin='/tmp/frozen-source-' + system + '/bin',
            rootfs='/tmp/frozen-source-' + system + '/rootfs',
            firmware_sha256='a' * 64, source_head='b' * 40,
            launch_command=['bash', '/tmp/frozen-launcher'], launch_env={},
            parameters=parameters, expected_parameters=dict(parameters),
            diagnostic_expectations=diagnostic, hover_diagnostic_expectations=hover))
    return dict(flight_qualified=True, max_attempts=8, data_root=root,
        order=[job['id'] for job in jobs], jobs=jobs, stop_on_first_failure=True,
        automatic_retry=False, retuning=False, phase_duration_s=dict(PHASE_DURATION_S),
        safety_limits=dict(SAFETY_LIMITS), entry_limits=dict(ENTRY_LIMITS),
        runtime=dict(launcher=['bash', '/tmp/runtime'], preflight='/tmp/preflight.py', environment={}),
        assets={'/tmp/frozen-launcher': 'c' * 64})


def state(system='PID', timestamp=1000000):
    mode = {'PID': 0, 'RSTA': 3, 'RISTA': 4, 'STA2': 0}[system]
    axes = 0 if system in ('PID', 'STA2') else 7
    velocity = dict(timestamp=timestamp, requested_mode=mode, requested_axes=axes,
        effective_mode=mode, effective_axes=axes, active_axes=axes,
        inner_mode=0, inner_axes=0, inner_divisor=1, inner_valid=True,
        valid=True, armed=True, enabled=True, landed=False, contact=False,
        failsafe=False, fault=False, pending=False, config_pending=False, timing=0,
        reset_bits=0, reject=0, first_fail=0, retry_result=0, excitation_fault=0,
        excitation=0, excitation_y=0, excitation_z=0)
    rate = dict(timestamp=timestamp, requested_mode=0, requested_axes=0, effective_mode=0,
        effective_axes=0, fault=0, pending=False, config_pending=False, config_valid=True,
        measurement_valid=True, output_valid=True, timing_status=0, abort_requested=False,
        termination=False, armed=True, rate_enabled=True, div_eff=1, div_ok=True)
    diagnostics = {'attitude_sta_status': dict(timestamp=timestamp)}
    if system != 'STA2':
        diagnostics = {'sta_velocity_ctrl_status': velocity, 'sta_rate_ctrl_status': rate}
    return dict(position=dict(timestamp=timestamp, timestamp_sample=timestamp,
        x=0.0, y=0.0, z=-2.5, vx=0.0, vy=0.0, vz=0.0,
        xy_valid=True, z_valid=True, v_xy_valid=True, v_z_valid=True),
        attitude=dict(timestamp=timestamp, q=[1.0, 0.0, 0.0, 0.0]),
        status=dict(timestamp=timestamp, nav_state=14, arming_state=2, failsafe=False,
                    failure_detector_status=0),
        land=dict(timestamp=timestamp, landed=False, ground_contact=False, maybe_landed=False),
        takeoff=dict(timestamp=timestamp, takeoff_state=5), diagnostics=diagnostics)


def receipt():
    return dict(status='running', dry_run=False, wall_stamp=100.0, telemetry_age=0.05,
        native_clock_age=0.02, publisher_count=1, subscriber_count=1, sent_count=31,
        last_sent_generation=2, last_sent_phase='hover', last_sent_seq=34,
        last_sent_sim_us=32000000, latest_native_sim_us=32020000,
        generation=999, phase='velocity')


class ManifestTests(unittest.TestCase):
    def test_heading_policy_requires_uniform_explicit_refreeze(self):
        m = manifest()
        m['jobs'][0]['heading_reset_policy'] = r.HEADING_POLICY
        with self.assertRaisesRegex(ValueError, 'heading reset policy'):
            r.validate_manifest(m, 'O001')
        m['heading_reset_policy'] = r.HEADING_POLICY
        with self.assertRaisesRegex(ValueError, 'heading reset policy'):
            r.validate_manifest(m, 'O001')
        for job in m['jobs']:
            job['heading_reset_policy'] = r.HEADING_POLICY
        self.assertIs(r.validate_manifest(m, 'O001'), m['jobs'][0])
        m['heading_reset_policy'] = 'allow_all'
        with self.assertRaisesRegex(ValueError, 'Unknown heading'):
            r.validate_manifest(m, 'O001')

    def test_frozen_batch_selects_each_exact_job(self):
        m = manifest()
        for job in m['jobs']:
            self.assertIs(r.validate_manifest(m, job['id']), job)

    def test_draft_or_truthy_qualification_is_rejected(self):
        for qualified in (False, None, 1, 'true'):
            m = manifest(); m['flight_qualified'] = qualified
            with self.subTest(qualified=qualified), self.assertRaises(ValueError):
                r.validate_manifest(m, 'O001')

    def test_budget_and_batch_policies_cannot_change(self):
        for field, value in [('max_attempts', 9), ('max_attempts', 8.0), ('max_attempts', True),
                             ('stop_on_first_failure', False), ('automatic_retry', True), ('retuning', True)]:
            m = manifest(); m[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                r.validate_manifest(m, 'O001')

    def test_exact_ids_order_task_and_system(self):
        for mutate in (lambda m: m['order'].reverse(), lambda m: m['jobs'].reverse(),
                       lambda m: m['jobs'][0].update(id='S304'),
                       lambda m: m['jobs'][0].update(task='hover'),
                       lambda m: m['jobs'][0].update(system='RISTA'),
                       lambda m: m['jobs'][1].update(label='STA2')):
            m = manifest(); mutate(m)
            with self.assertRaises(ValueError): r.validate_manifest(m, 'O001')
        with self.assertRaises(ValueError): r.validate_manifest(manifest(), 'S304')

    def test_old_result_paths_or_evidence_cannot_be_imported(self):
        for field in ('result_path', 'result', 'results', 'logs', 'events', 'success', 'independent_replay_passed'):
            m = manifest(); m['jobs'][0][field] = '/tmp/old-result'
            with self.subTest(field=field), self.assertRaises(ValueError):
                r.validate_manifest(m, 'O001')
        for field in ('pid_addition', 'preserved_results', 'prior_results'):
            m = manifest(); m[field] = {}
            with self.assertRaises(ValueError): r.validate_manifest(m, 'O001')

    def test_old_data_tree_and_parent_cannot_be_reused(self):
        for root in (str(r._OLD_ROOT), str(r._OLD_ROOT / 'new'), str(r._OLD_ROOT.parent), '/', 'relative'):
            with self.subTest(root=root), self.assertRaises(ValueError):
                r.validate_manifest(manifest(root), 'O001')

    def test_traversal_and_already_attempted_status_rejected(self):
        for field, value in [('repo', '/tmp/source/../old'), ('bin', 'relative'),
                             ('rootfs', None), ('status', 'completed')]:
            m = manifest(); m['jobs'][0][field] = value
            with self.assertRaises(ValueError): r.validate_manifest(m, 'O001')

    def test_all_controller_selection_axes_divisors_and_tasks_frozen(self):
        for job_index in (0, 2, 3, 4, 6, 7):
            for field in ('MPC_VC_MODE', 'MPC_VC_AXES', 'MPC_VC_DIV', 'MC_RTC_MODE',
                          'MC_STA_AXES', 'MC_RTC_DIV', 'MC_RATT_TEST', 'MPC_VCT_TEST'):
                m = manifest()
                m['jobs'][job_index]['parameters'][field] = 9
                m['jobs'][job_index]['expected_parameters'][field] = 9
                with self.subTest(job=job_index, field=field), self.assertRaises(ValueError):
                    r.validate_manifest(m, 'O001')

    def test_original_cannot_enable_an_internal_task(self):
        m = manifest(); m['jobs'][1]['parameters']['MPC_VCT_TEST'] = 5
        m['jobs'][1]['expected_parameters']['MPC_VCT_TEST'] = 5
        with self.assertRaises(ValueError): r.validate_manifest(m, 'O001')

    def test_nonfinite_boolean_or_unexpected_parameter_rejected(self):
        for value in (float('nan'), float('inf'), True, '1'):
            m = manifest(); m['jobs'][0]['parameters']['SDLOG_MODE'] = value
            m['jobs'][0]['expected_parameters']['SDLOG_MODE'] = value
            with self.assertRaises(ValueError): r.validate_manifest(m, 'O001')
        m = manifest(); del m['jobs'][0]['expected_parameters']['SDLOG_MODE']
        with self.assertRaises(ValueError): r.validate_manifest(m, 'O001')

    def test_same_system_cannot_change_gains_between_tasks(self):
        m = manifest(); m['jobs'][4]['parameters']['NEW_GAIN'] = 3
        m['jobs'][4]['expected_parameters']['NEW_GAIN'] = 3
        with self.assertRaisesRegex(ValueError, 'between tasks'): r.validate_manifest(m, 'O001')

    def test_missing_firmware_runtime_or_assets_rejected(self):
        for mutate in (lambda m: m['jobs'][0].update(firmware_sha256='old'),
                       lambda m: m['jobs'][0].update(source_head='unknown'),
                       lambda m: m.update(runtime={}), lambda m: m.update(assets={}),
                       lambda m: m['jobs'][0].update(launch_command='bash launcher')):
            m = manifest(); mutate(m)
            with self.assertRaises(ValueError): r.validate_manifest(m, 'O001')

    def test_task_durations_and_all_limits_cannot_change(self):
        for group in ('phase_duration_s', 'safety_limits', 'entry_limits'):
            m = manifest(); field = next(iter(m[group])); m[group][field] = 999
            with self.subTest(group=group), self.assertRaises(ValueError):
                r.validate_manifest(m, 'O001')
        m = manifest(); m['safety_limits']['xy_speed_m_s'] = True
        with self.assertRaises(ValueError): r.validate_manifest(m, 'O001')

    def test_json_roundtrip_limits_and_integral_numeric_limits_accepted(self):
        m = json.loads(json.dumps(manifest()))
        m['safety_limits']['tilt_deg'] = 15
        self.assertEqual(r.validate_manifest(m, 'O001')['id'], 'O001')


class OrderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.manifest = manifest(self.temporary.name)

    def write_result(self, index=0, **overrides):
        job = self.manifest['jobs'][index]
        path = Path(self.temporary.name) / 'runs' / job['id'] / 'result.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        value = {key: job[key] for key in ('id', 'task', 'system')}
        value.update(success=True, independent_replay_passed=True)
        value.update(overrides)
        path.write_text(json.dumps(value))
        return path

    def test_first_attempt_allowed_without_writes(self):
        expected = Path(self.temporary.name) / 'runs/O001'
        self.assertEqual(r.check_order(self.manifest, 'O001'), expected)
        self.assertFalse(expected.exists())

    def test_previous_success_and_independent_replay_required(self):
        self.write_result()
        self.assertEqual(r.check_order(self.manifest, 'O002').name, 'O002')
        for key, value in [('success', False), ('independent_replay_passed', False),
                           ('success', 1), ('independent_replay_passed', 'true')]:
            self.write_result(**{key: value})
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                r.check_order(self.manifest, 'O002')

    def test_cannot_rerun_even_empty_attempt(self):
        path = Path(self.temporary.name) / 'runs/O001'; path.mkdir(parents=True)
        with self.assertRaises(ValueError): r.check_order(self.manifest, 'O001')

    def test_missing_previous_or_premature_later_output_stops(self):
        with self.assertRaises(ValueError): r.check_order(self.manifest, 'O002')
        path = Path(self.temporary.name) / 'runs/O004'; path.mkdir(parents=True)
        with self.assertRaises(ValueError): r.check_order(self.manifest, 'O001')

    def test_old_or_other_task_result_cannot_unlock_next_attempt(self):
        for key, value in [('id', 'S304'), ('task', 'velocity'), ('system', 'STA2')]:
            self.write_result(**{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                r.check_order(self.manifest, 'O002')

    def test_invalid_json_and_result_symlink_rejected(self):
        path = self.write_result(); path.write_text('{')
        with self.assertRaises(ValueError): r.check_order(self.manifest, 'O002')
        path.unlink(); path.symlink_to(Path(self.temporary.name) / 'missing-result')
        with self.assertRaises(ValueError): r.check_order(self.manifest, 'O002')

    def test_output_symlink_cannot_escape_or_mask_existing_attempt(self):
        runs = Path(self.temporary.name) / 'runs'; runs.mkdir()
        (runs / 'O001').symlink_to(Path(self.temporary.name) / 'nonexistent')
        with self.assertRaises(ValueError): r.check_order(self.manifest, 'O001')


class StableTests(unittest.TestCase):
    def test_continuous_three_seconds_and_boundary(self):
        since, ready = r.stable_gate(state(timestamp=1000000), ORIGIN, 1000000)
        self.assertEqual((since, ready), (1000000, False))
        since, ready = r.stable_gate(state(timestamp=3999999), ORIGIN, 1000000, since)
        self.assertFalse(ready)
        self.assertTrue(r.stable_gate(state(timestamp=4000000), ORIGIN, 1000000, since)[1])

    def test_unstable_sample_resets_continuous_interval(self):
        s = state(timestamp=3000000); s['position']['vz'] = 0.2
        since, ready = r.stable_gate(s, ORIGIN, 1000000, 1000000)
        self.assertEqual((since, ready), (None, False))
        self.assertEqual(r.stable_gate(state(timestamp=4000000), ORIGIN, 1000000, since), (4000000, False))

    def test_height_inclusive_velocity_strict_boundaries(self):
        for height, velocity, expected in [(2.2, 0.19999, True), (2.8, -0.19999, True),
                                           (2.1999, 0, False), (2.8001, 0, False),
                                           (2.5, 0.2, False), (2.5, -0.2, False)]:
            s = state(); s['position'].update(z=-height, vz=velocity)
            with self.subTest(height=height, velocity=velocity):
                self.assertEqual(r.stable_entry_ok(s, ORIGIN), expected)

    def test_gate_requires_actual_offboard_airborne_state(self):
        for group, key, value in [('status', 'nav_state', 4), ('status', 'arming_state', 1),
            ('status', 'failsafe', True), ('land', 'landed', True), ('land', 'ground_contact', True),
            ('land', 'maybe_landed', True), ('takeoff', 'takeoff_state', 4), ('position', 'z_valid', False)]:
            s = state(); s[group][key] = value
            with self.subTest(group=group, key=key): self.assertFalse(r.stable_entry_ok(s, ORIGIN))

    def test_bounded_fifteen_second_wait_and_exact_completion(self):
        s = state(timestamp=16000000)
        self.assertTrue(r.stable_gate(s, ORIGIN, 1000000, 13000000)[1])
        with self.assertRaises(TimeoutError): r.stable_gate(s, ORIGIN, 1000000)
        with self.assertRaises(TimeoutError): r.stable_gate(state(timestamp=16000001), ORIGIN, 1000000, 1000000)

    def test_repeated_native_sample_does_not_accumulate_duration(self):
        s = state(timestamp=1000000); s['position']['timestamp'] = 10000000
        self.assertEqual(r.stable_gate(s, ORIGIN, 1000000, 1000000), (1000000, False))

    def test_gate_history_and_nonfinite_timestamps_rejected(self):
        for start, since in [(2000000, None), (1000000, 999999), (1000000, 1000001), (float('nan'), None)]:
            with self.assertRaises(ValueError): r.stable_gate(state(), ORIGIN, start, since)
        s = state(); s['position']['timestamp_sample'] = 1000001
        with self.assertRaises(ValueError): r.position_time_us(s)


class StateTests(unittest.TestCase):
    def job(self, system):
        return next(j for j in manifest()['jobs'] if j['system'] == system)

    def test_all_four_systems_pass_scored_state(self):
        for system in ('PID', 'STA2', 'RSTA', 'RISTA'):
            for phase in r.SCORED_PHASES:
                with self.subTest(system=system, phase=phase):
                    self.assertEqual(r.check_active_state(state(system), self.job(system), phase, ORIGIN), 2.5)

    def test_recover_may_converge_without_scored_takeover(self):
        s = state('RSTA'); s['position'].update(z=-1.6, vz=0.3)
        s['diagnostics']['sta_velocity_ctrl_status'].update(active_axes=0, valid=False)
        self.assertEqual(r.check_active_state(s, self.job('RSTA'), 'recover', ORIGIN), 1.6)
        self.assertFalse(r.stable_entry_ok(s, ORIGIN))

    def test_ground_takeoff_transition_not_falsely_scored(self):
        s = state('RISTA'); s['position']['z'] = 0
        s['land'].update(landed=True, ground_contact=True); s['takeoff']['takeoff_state'] = 2
        s['diagnostics']['sta_velocity_ctrl_status'].update(active_axes=0, valid=False, reset_bits=32)
        self.assertEqual(r.check_active_state(s, self.job('RISTA'), 'climb', ORIGIN), 0)
        with self.assertRaises(ValueError): r.check_active_state(s, self.job('RISTA'), 'hover', ORIGIN)

    def test_full_flight_limits_remain_inclusive(self):
        for values in [dict(z=0.5), dict(z=-4), dict(vz=3.5), dict(vz=-3.5), dict(vx=1), dict(x=2)]:
            s = state(); s['position'].update(values)
            r.check_active_state(s, self.job('PID'), 'climb', ORIGIN)

    def test_full_flight_limit_violation_rejected(self):
        for values in [dict(z=0.50001), dict(z=-4.00001), dict(vz=3.50001), dict(vz=-3.50001),
                       dict(vx=1.00001), dict(x=2.00001), dict(vx=0.8, vy=0.8), dict(x=1.5, y=1.5)]:
            s = state(); s['position'].update(values)
            with self.subTest(values=values), self.assertRaises(ValueError):
                r.check_active_state(s, self.job('PID'), 'climb', ORIGIN)

    def test_tilt_and_invalid_estimate_rejected(self):
        s = state(); angle = math.radians(15.01)
        s['attitude']['q'] = [math.cos(angle / 2), math.sin(angle / 2), 0, 0]
        with self.assertRaises(ValueError): r.check_active_state(s, self.job('PID'), 'hover', ORIGIN)
        for key in ('xy_valid', 'z_valid', 'v_xy_valid', 'v_z_valid'):
            s = state(); s['position'][key] = False
            with self.assertRaises(ValueError): r.check_active_state(s, self.job('PID'), 'hover', ORIGIN)

    def test_active_mode_and_failsafe_do_not_pass_recovery(self):
        for key, value in [('nav_state', 4), ('arming_state', 1), ('failsafe', True), ('failure_detector_status', 1)]:
            s = state(); s['status'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                r.check_active_state(s, self.job('PID'), 'recover', ORIGIN)

    def test_scored_windows_require_airborne_and_takeoff_flight(self):
        for group, key, value in [('land', 'ground_contact', True), ('land', 'landed', True),
                                  ('land', 'maybe_landed', True), ('takeoff', 'takeoff_state', 4)]:
            s = state(); s[group][key] = value
            with self.assertRaises(ValueError): r.check_active_state(s, self.job('PID'), 'step_up', ORIGIN)

    def test_frozen_actual_controller_expectations_rejected_on_mismatch(self):
        for topic, field, value in [('sta_velocity_ctrl_status', 'active_axes', 0),
            ('sta_velocity_ctrl_status', 'effective_mode', 0), ('sta_velocity_ctrl_status', 'inner_mode', 3),
            ('sta_velocity_ctrl_status', 'fault', True), ('sta_rate_ctrl_status', 'fault', 1),
            ('sta_rate_ctrl_status', 'effective_mode', 1)]:
            s = state('RISTA'); s['diagnostics'][topic][field] = value
            with self.subTest(topic=topic, field=field), self.assertRaises(ValueError):
                r.check_active_state(s, self.job('RISTA'), 'velocity', ORIGIN)

    def test_missing_actual_diagnostics_cannot_be_invented(self):
        s = state('STA2'); del s['diagnostics']['attitude_sta_status']['timestamp']
        with self.assertRaises(ValueError): r.check_active_state(s, self.job('STA2'), 'hover', ORIGIN)
        s = state(); s['diagnostics'] = {}
        with self.assertRaises(ValueError): r.check_active_state(s, self.job('PID'), 'climb', ORIGIN)

    def test_no_unvalidated_additional_diagnostic_gate(self):
        s = state('RISTA')
        expected = self.job('RISTA')['hover_diagnostic_expectations']
        s['diagnostics'] = {topic: dict(fields, timestamp=1000000) for topic, fields in expected.items()}
        self.assertEqual(r.check_active_state(s, self.job('RISTA'), 'hover', ORIGIN), 2.5)
        s['diagnostics']['sta_velocity_ctrl_status'].update(reset_bits=16, timing=1, valid=False)
        self.assertEqual(r.check_active_state(s, self.job('RISTA'), 'hover', ORIGIN), 2.5)

    def test_landed_disarmed_tail_is_accepted_without_active_takeover(self):
        s = state(); s['status'].update(arming_state=1, nav_state=18)
        s['land'].update(landed=True, ground_contact=True); s['position']['z'] = 0
        s['diagnostics']['sta_velocity_ctrl_status']['valid'] = False
        self.assertEqual(r.check_active_state(s, self.job('PID'), 'landing', ORIGIN), 0)
        s['land']['landed'] = False
        with self.assertRaises(ValueError): r.check_active_state(s, self.job('PID'), 'landing', ORIGIN)


class ReceiptTests(unittest.TestCase):
    def ready(self, value, **kwargs):
        defaults = dict(generation=2, phase='hover', before_sent_count=30, now_wall_s=100.1)
        defaults.update(kwargs)
        return r.receipt_ready(value, **defaults)

    def test_handshake_uses_actual_sent_generation_not_control_metadata(self):
        self.assertTrue(self.ready(receipt()))
        value = receipt(); value.update(generation=2, phase='hover', last_sent_generation=1)
        self.assertFalse(self.ready(value))

    def test_count_must_advance_by_required_amount(self):
        self.assertFalse(self.ready(receipt(), before_sent_count=31))
        self.assertFalse(self.ready(receipt(), min_new_sent=2))
        self.assertTrue(self.ready(receipt(), before_sent_count=1, min_new_sent=30))

    def test_no_actual_sends_cannot_satisfy_handshake(self):
        value = receipt(); value.update(sent_count=0, last_sent_generation=None, last_sent_seq=None)
        self.assertFalse(self.ready(value, before_sent_count=0))

    def test_stale_native_receipt_and_clock_rejected(self):
        for field, value in [('telemetry_age', 0.50001), ('native_clock_age', 0.50001),
                             ('wall_stamp', 99.5), ('wall_stamp', 100.102)]:
            actual = receipt(); actual[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.ready(actual)

    def test_exact_freshness_boundaries_accepted(self):
        value = receipt(); value.update(telemetry_age=0.5, native_clock_age=0.5, wall_stamp=99.6)
        self.assertTrue(self.ready(value))

    def test_bad_counts_phase_generation_and_native_sample_rejected(self):
        for field, value in [('sent_count', 29), ('last_sent_generation', 3), ('last_sent_phase', 'velocity'),
            ('last_sent_seq', 30), ('last_sent_sim_us', 32020001), ('latest_native_sim_us', 32500001),
            ('last_sent_generation', True), ('sent_count', 31.0)]:
            actual = receipt(); actual[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.ready(actual)

    def test_fatal_dryrun_and_incomplete_ros_graph_rejected(self):
        for field, value in [('status', 'fatal'), ('dry_run', True), ('publisher_count', 2), ('subscriber_count', 0)]:
            actual = receipt(); actual[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.ready(actual)

    def test_nonfinite_and_missing_evidence_rejected(self):
        for field in ('wall_stamp', 'telemetry_age', 'native_clock_age', 'last_sent_sim_us', 'latest_native_sim_us'):
            for value in (float('nan'), float('inf'), None, True):
                actual = receipt(); actual[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError): self.ready(actual)


if __name__ == '__main__':
    unittest.main()
