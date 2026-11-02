"""Synthetic regression fixtures only; no synthetic record is a flight result."""

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import analyze as a
import ros_bridge as bridge
import task_contract as contract


ORIGIN = dict(x=0.0, y=0.0, z=0.0, heading=0.4)


def fixture(task='position', system='RSTA', array_layout=False):
    events, windows = [dict(name='control_change', timestamp_us=900000, generation=1, phase='prestream', enabled=False)], []
    cursor = 1000000
    for generation, phase in enumerate(contract.TASK_PHASES[task], 2):
        duration = contract.PHASE_DURATION_S.get(phase, 2 if phase == 'prestream' else 3)
        window = dict(phase=phase, generation=generation, start=cursor, end=cursor + int(duration * 1e6))
        windows.append(window)
        events.extend([dict(name='control_change', timestamp_us=window['start'], generation=generation, phase=phase, enabled=True),
                       dict(name=phase + '_start', timestamp_us=window['start'], generation=generation),
                       dict(name=phase + '_end', timestamp_us=window['end'], generation=generation)])
        cursor = window['end']
    land_command, final = cursor + 100000, cursor + 3000000
    events.extend([dict(name='land_command', timestamp_us=land_command, generation=windows[-1]['generation']),
                   dict(name='control_change', timestamp_us=land_command + 100000, generation=windows[-1]['generation'] + 1,
                        phase='descend', enabled=False),
                   dict(name='landed_disarmed', timestamp_us=final, status_timestamp_us=final + 50000,
                        land_timestamp_us=final + 10000, generation=windows[-1]['generation'] + 1)])
    t = np.arange(900000, final + 200000, 100000, dtype=np.int64)
    zeros = np.zeros(len(t))
    p = dict(timestamp=t.copy(), timestamp_sample=t.copy(), x=zeros.copy(), y=zeros.copy(), z=zeros.copy(),
             vx=zeros.copy(), vy=zeros.copy(), vz=zeros.copy())
    for key in ('xy_valid', 'z_valid', 'v_xy_valid', 'v_z_valid'):
        p[key] = np.ones(len(t), dtype=int)
    for key in ('xy_reset_counter', 'z_reset_counter', 'vxy_reset_counter', 'vz_reset_counter', 'heading_reset_counter'):
        p[key] = np.zeros(len(t), dtype=int)
    for i, timestamp in enumerate(t):
        for window in windows:
            if window['start'] <= timestamp < window['end']:
                elapsed = (timestamp - window['start']) / 1e6
                if window['phase'] == 'velocity':
                    height = 2.5 + contract.velocity_height_offset(elapsed)
                else:
                    height = contract.height_profile(window['phase'], elapsed)[0]
                p['z'][i] = -height
                break
    attitude = dict(timestamp=t.copy(), timestamp_sample=t.copy())
    for i in range(4):
        attitude['q[%d]' % i] = np.ones(len(t)) if i == 0 else zeros.copy()
    climb = windows[1]['start']
    status = dict(timestamp=np.asarray([900000, climb, land_command, final + 50000], dtype=np.int64),
                  arming_state=np.asarray([1, 2, 2, 1]), nav_state=np.asarray([0, 14, 18, 18]),
                  failsafe=np.zeros(4, dtype=int))
    land = dict(timestamp=np.asarray([900000, climb + 3000000, land_command + 500000, final + 10000], dtype=np.int64),
                landed=np.asarray([1, 0, 0, 1]), ground_contact=np.asarray([1, 0, 0, 1]),
                maybe_landed=np.asarray([1, 0, 0, 1]), freefall=np.zeros(4, dtype=int))
    takeoff = dict(timestamp=np.asarray([900000, climb, climb + 100000, climb + 3000000, final], dtype=np.int64),
                   takeoff_state=np.asarray([1, 2, 4, 5, 1]))
    sp = dict(timestamp=t.copy(), x=zeros.copy(), y=zeros.copy(), z=p['z'].copy(),
              vx=np.full(len(t), .25), vy=zeros.copy(), vz=zeros.copy())
    published, sent, trajectory_rows = [], [], []
    seq = 0
    for window in windows:
        control = dict(generation=window['generation'], phase=window['phase'], start_us=window['start'],
                       origin=ORIGIN, enabled=True)
        for timestamp in range(window['start'], window['end'], 100000):
            seq += 1
            now = 1000 + timestamp / 1e6
            telemetry = dict(time_boot_ms=timestamp // 1000, sim_us=timestamp, wall_stamp=now,
                             x=0., y=0., z=0., vx=0., vy=0., vz=0.)
            payload = bridge.make_envelope(control, telemetry, seq, now)
            digest = hashlib.sha256(bridge.canonical_json(payload).encode()).hexdigest()
            published.append(dict(payload, ros_sha256=digest))
            wire = bridge.wire_fields(payload['target'], timestamp)
            sent.append(dict(payload, ros_sha256=digest, wire_fields=wire, identity_verified=True,
                             peer=['127.0.0.1', 14580], source_system=245, source_component=191))
            is_velocity = window['phase'] == 'velocity'
            trajectory_rows.append([timestamp + 10000, wire['x'], wire['y'], np.nan if is_velocity else wire['z'],
                                    np.nan, np.nan, wire['vz'] if is_velocity else np.nan, wire['yaw']])
    raw = np.asarray(trajectory_rows)
    trajectory = {key: raw[:, i].copy() for i, key in enumerate(('timestamp', 'x', 'y', 'z', 'vx', 'vy', 'vz', 'yaw'))}
    trajectory['timestamp'] = trajectory['timestamp'].astype(np.int64)
    if array_layout:
        for i, scalar in enumerate(('x', 'y', 'z')):
            trajectory['position[%d]' % i] = trajectory.pop(scalar)
        for i, scalar in enumerate(('vx', 'vy', 'vz')):
            trajectory['velocity[%d]' % i] = trajectory.pop(scalar)
    topics = dict(vehicle_local_position=p, vehicle_attitude=attitude, vehicle_status=status,
                  vehicle_land_detected=land, takeoff_status=takeoff,
                  trajectory_setpoint=trajectory, vehicle_local_position_setpoint=sp)
    job = dict(task=task, system=system, expected_parameters={'TEST_GAIN': 1.0},
               diagnostic_expectations={}, hover_diagnostic_expectations={})
    for name, fields in a.diagnostic_contract(job).items():
        topics[name] = dict(timestamp=t.copy(), **{key: np.full(len(t), value) for key, value in fields.items()})
        if not fields:
            topics[name]['att_roll_torque'] = np.zeros(len(t))
    log = SimpleNamespace(data_list=[SimpleNamespace(name=name, multi_id=0, data=data) for name, data in topics.items()],
                          dropouts=[], file_corruption=False, initial_parameters={'TEST_GAIN': 1.0}, changed_parameters=[])
    return dict(events=events, windows=windows, topics=topics, log=log, job=job, sent=sent, published=published)


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'sent.jsonl'
        self.f = fixture()

    def audit(self, value=None):
        value = value or self.f
        for name, rows in [('sent.jsonl', value['sent']), ('ros_published.jsonl', value['published'])]:
            (self.path.parent / name).write_text(''.join(bridge.canonical_json(row) + '\n' for row in rows), encoding='utf-8')
        return a.audit_native_log('synthetic-not-a-flight.ulg', value['events'], ORIGIN, value['job'], self.path,
                                  ulog_class=lambda *args, **kwargs: value['log'])

    def test_valid_position_uses_actual_velocity_reference_not_ros_positions(self):
        result = self.audit()
        self.assertTrue(result['accepted'])
        self.assertEqual([row['phase'] for row in result['phase_metrics']], ['hover', 'step_up', 'step_down'])
        for row in result['phase_metrics']:
            np.testing.assert_allclose(row['velocity_tracking_rmse_xyz_m_s'], [.25, 0., 0.])
            self.assertEqual(row['actual_velocity_rms_xyz_m_s'], [0., 0., 0.])
        self.assertEqual(result['phase_metrics'][0]['seconds'], 10.)

    def test_valid_original_array_layout_and_velocity_task(self):
        for system in ('STA2', 'PID', 'RISTA'):
            with self.subTest(system=system):
                result = self.audit(fixture(task='velocity', system=system, array_layout=True))
                self.assertTrue(result['accepted'])
                self.assertEqual([row['phase'] for row in result['phase_metrics']], ['hover', 'velocity'])
                self.assertEqual(result['phase_metrics'][1]['seconds'], 12.)

    def test_final_native_status_receipt_can_follow_position_event(self):
        result = self.audit()
        self.assertTrue(result['accepted'])
        self.f['events'][-1].pop('status_timestamp_us')
        with self.assertRaisesRegex(ValueError, 'arming_state'):
            self.audit()

    def test_dropout_and_corruption_rejected(self):
        self.f['log'].dropouts = [object()]
        with self.assertRaisesRegex(ValueError, 'dropout'):
            self.audit()
        self.f['log'].dropouts = []
        self.f['log'].file_corruption = True
        with self.assertRaisesRegex(ValueError, 'corruption'):
            self.audit()

    def test_every_required_topic_is_mandatory(self):
        original = self.f['log'].data_list
        for name in a.BASE_TOPICS:
            self.f['log'].data_list = [entry for entry in original if entry.name != name]
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Missing required native topic'):
                self.audit()
        self.f['log'].data_list = original

    def test_duplicate_topic_instance_rejected(self):
        self.f['log'].data_list.append(self.f['log'].data_list[0])
        with self.assertRaisesRegex(ValueError, 'Ambiguous native topic'):
            self.audit()

    def test_publication_time_is_strict_even_for_attitude(self):
        for name in ('vehicle_local_position', 'vehicle_attitude', 'trajectory_setpoint'):
            value = fixture()
            value['topics'][name]['timestamp'][5] = value['topics'][name]['timestamp'][4]
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Non-increasing'):
                self.audit(value)

    def test_attitude_sample_resampling_is_allowed_with_strict_publication(self):
        self.f['topics']['vehicle_attitude']['timestamp_sample'][5:8] = self.f['topics']['vehicle_attitude']['timestamp_sample'][4]
        result = self.audit()
        self.assertGreater(result['native_resolutions']['vehicle_attitude']['timestamp_sample']['repeated_intervals'], 0)

    def test_repeated_position_sample_clock_is_rejected(self):
        p = self.f['topics']['vehicle_local_position']
        p['timestamp_sample'][5] = p['timestamp_sample'][4]
        with self.assertRaisesRegex(ValueError, 'Non-increasing'):
            self.audit()

    def test_position_gap_over_half_second_rejected(self):
        p = self.f['topics']['vehicle_local_position']
        for key in p:
            p[key] = np.delete(p[key], np.arange(40, 50))
        with self.assertRaisesRegex(ValueError, 'position gap'):
            self.audit()

    def test_each_estimator_reset_counter_is_mandatory_and_cannot_change(self):
        for key in ('xy_reset_counter', 'z_reset_counter', 'vxy_reset_counter', 'vz_reset_counter', 'heading_reset_counter'):
            value = fixture()
            value['topics']['vehicle_local_position'][key][100:] = 1
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'reset'):
                self.audit(value)

    def test_invalid_estimate_and_nonfinite_position_rejected(self):
        self.f['topics']['vehicle_local_position']['xy_valid'][100] = 0
        with self.assertRaisesRegex(ValueError, 'Invalid native estimate'):
            self.audit()
        self.f['topics']['vehicle_local_position']['xy_valid'][100] = 1
        self.f['topics']['vehicle_local_position']['z'][100] = np.nan
        with self.assertRaisesRegex(ValueError, 'Nonfinite native flight state'):
            self.audit()

    def test_full_flight_envelope_includes_unscored_climb(self):
        for key, value in [('z', -4.01), ('vz', 3.51), ('vx', 1.01), ('x', 2.01)]:
            item = fixture()
            item['topics']['vehicle_local_position'][key][100] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'safety envelope'):
                self.audit(item)

    def test_tilt_and_invalid_quaternion_rejected(self):
        q = self.f['topics']['vehicle_attitude']
        q['q[0]'][100] = np.cos(np.radians(16) / 2)
        q['q[1]'][100] = np.sin(np.radians(16) / 2)
        with self.assertRaisesRegex(ValueError, 'tilt safety'):
            self.audit()
        for i in range(4):
            q['q[%d]' % i][100] = 0
        with self.assertRaisesRegex(ValueError, 'quaternion'):
            self.audit()

    def test_hover_specific_envelope_is_preserved(self):
        hover = next(window for window in self.f['windows'] if window['phase'] == 'hover')
        p = self.f['topics']['vehicle_local_position']
        p['vz'][p['timestamp'] == hover['start'] + 1000000] = .61
        with self.assertRaisesRegex(ValueError, 'Hover safety'):
            self.audit()

    def test_old_nav4_cannot_pass_offboard_acceptance(self):
        self.f['topics']['vehicle_status']['nav_state'][1] = 4
        with self.assertRaisesRegex(ValueError, 'nav_state'):
            self.audit()

    def test_unarmed_contact_failsafe_and_takeoff_ramp_rejected(self):
        changes = [('vehicle_status', 'arming_state', 1, 1), ('vehicle_status', 'failsafe', 1, 1),
                   ('vehicle_land_detected', 'ground_contact', 1, 1), ('vehicle_land_detected', 'maybe_landed', 1, 1),
                   ('takeoff_status', 'takeoff_state', 3, 4)]
        for topic, field, index, replacement in changes:
            value = fixture()
            value['topics'][topic][field][index] = replacement
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                self.audit(value)

    def test_controller_active_axes_mode_and_rate_pid_are_actual_log_requirements(self):
        changes = [('sta_velocity_ctrl_status', 'active_axes', 3),
                   ('sta_velocity_ctrl_status', 'effective_mode', 4),
                   ('sta_velocity_ctrl_status', 'fault', 1),
                   ('sta_rate_ctrl_status', 'effective_mode', 1)]
        for topic, field, replacement in changes:
            value = fixture()
            value['topics'][topic][field][:] = replacement
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'Wrong active controller'):
                self.audit(value)

    def test_diagnostic_missing_field_or_gap_rejected(self):
        d = self.f['topics']['sta_velocity_ctrl_status']
        del d['active_axes']
        with self.assertRaisesRegex(ValueError, 'Missing native field'):
            self.audit()
        value = fixture()
        hover = next(window for window in value['windows'] if window['phase'] == 'hover')
        d = value['topics']['sta_velocity_ctrl_status']
        keep = ~((d['timestamp'] > hover['start'] + 1000000) & (d['timestamp'] < hover['start'] + 2000000))
        for key in d:
            d[key] = d[key][keep]
        with self.assertRaisesRegex(ValueError, 'gap over'):
            self.audit(value)

    def test_parameter_initial_mismatch_or_inflight_retune_rejected(self):
        self.f['log'].initial_parameters['TEST_GAIN'] = 2.0
        with self.assertRaisesRegex(ValueError, 'parameter mismatch'):
            self.audit()
        self.f['log'].initial_parameters['TEST_GAIN'] = 1.0
        self.f['log'].changed_parameters = [(10000000, 'TEST_GAIN', 2.0)]
        with self.assertRaisesRegex(ValueError, 'changed during flight'):
            self.audit()

    def test_position_trajectory_rejects_finite_velocity_feedforward(self):
        self.f['topics']['trajectory_setpoint']['vx'][:] = 0
        with self.assertRaisesRegex(ValueError, 'position trajectory shape'):
            self.audit()

    def test_velocity_trajectory_requires_nan_z_position_and_finite_vz(self):
        for field, replacement in [('z', 0.), ('vz', np.nan), ('vx', 0.)]:
            value = fixture(task='velocity')
            window = next(w for w in value['windows'] if w['phase'] == 'velocity')
            d = value['topics']['trajectory_setpoint']
            d[field][(d['timestamp'] > window['start']) & (d['timestamp'] < window['end'])] = replacement
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'mixed Z-velocity trajectory shape'):
                self.audit(value)

    def test_wrong_actual_trajectory_target_or_yaw_rejected(self):
        for field in ('x', 'z', 'yaw'):
            value = fixture()
            value['topics']['trajectory_setpoint'][field][100] += .01
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'no matching past'):
                self.audit(value)

    def test_past_wire_match_does_not_accept_future_or_too_old_targets(self):
        d = self.f['topics']['trajectory_setpoint']
        for offset in (-1000000000, 1000000000):
            sent = copy.deepcopy(self.f['sent'])
            for row in sent:
                row['sim_us'] += offset
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, 'no matching past'):
                a.audit_trajectory(d, sent, self.f['windows'])

    def test_half_second_phase_edges_only_excluded_from_target_matching(self):
        window = next(w for w in self.f['windows'] if w['phase'] == 'hover')
        d = self.f['topics']['trajectory_setpoint']
        d['z'][(d['timestamp'] >= window['start']) & (d['timestamp'] < window['start'] + 400000)] = -99
        result = self.audit()
        hover = result['phase_metrics'][0]
        self.assertEqual(hover['seconds'], 10.0)
        self.assertEqual(hover['window_us'], [window['start'], window['end']])

    def test_ros_to_wire_identity_or_publisher_join_corruption_rejected(self):
        for mutate in (lambda f: f['sent'][100]['wire_fields'].update(z=123),
                       lambda f: f['sent'][100].update(ros_sha256='bad'),
                       lambda f: f['sent'][100].update(identity_verified=False),
                       lambda f: f['published'][100]['target'].update(z=123)):
            value = fixture()
            mutate(value)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.audit(value)

    def test_end_of_phase_hold_uses_control_ownership_without_changing_metrics(self):
        # The publisher legitimately holds prestream/recover while runner checks
        # state/configuration. Their performance end is not a stop-publishing command.
        for event in self.f['events']:
            if event['name'] in ('prestream_end', 'recover_end'):
                event['timestamp_us'] -= 400000
        last_window = self.f['windows'][-1]
        timestamp = last_window['end'] + 100000
        control = dict(generation=last_window['generation'], phase='descend', start_us=last_window['start'],
                       origin=ORIGIN, enabled=True)
        telemetry = dict(time_boot_ms=timestamp // 1000, sim_us=timestamp, wall_stamp=2000.,
                         x=0., y=0., z=0., vx=0., vy=0., vz=0.)
        payload = bridge.make_envelope(control, telemetry, self.f['sent'][-1]['seq'] + 1, 2000.)
        digest = hashlib.sha256(bridge.canonical_json(payload).encode()).hexdigest()
        self.f['published'].append(dict(payload, ros_sha256=digest))
        self.f['sent'].append(dict(payload, ros_sha256=digest,
            wire_fields=bridge.wire_fields(payload['target'], timestamp), identity_verified=True,
            peer=['127.0.0.1', 14580], source_system=245, source_component=191))
        result = self.audit()
        self.assertTrue(result['accepted'])
        self.assertEqual(result['phase_metrics'][0]['seconds'], 10.)

    def test_missing_or_disabled_control_ownership_cannot_authorize_sent_targets(self):
        for mutate in (lambda events: events.clear(),
                       lambda events: next(event for event in events if event['name'] == 'control_change'
                                          and event.get('generation') == 3).update(enabled=False)):
            value = fixture()
            mutate(value['events'])
            with self.assertRaises(ValueError):
                self.audit(value)

    def test_missing_truncated_and_reordered_phase_events_rejected(self):
        def remove_end(events):
            events.remove(next(event for event in events if event['name'] == 'climb_end'))
        def truncate_climb(events):
            end = next(event for event in events if event['name'] == 'climb_end')
            end['timestamp_us'] -= 1
        def repeat_generation(events):
            for event in events:
                if event['name'] in ('hover_start', 'hover_end'):
                    event['generation'] = 3
        for mutate in (remove_end, truncate_climb, repeat_generation):
            events = copy.deepcopy(self.f['events'])
            mutate(events)
            with self.assertRaises(ValueError):
                a.phase_windows(events, 'position')

    def test_conflicting_declared_mode_cannot_weaken_required_mode(self):
        self.f['job']['hover_diagnostic_expectations'] = {'sta_velocity_ctrl_status': {'active_axes': 0}}
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            self.audit()

    def test_metrics_cannot_silently_use_stale_reference_or_partial_window(self):
        p, sp = self.f['topics']['vehicle_local_position'], self.f['topics']['vehicle_local_position_setpoint']
        window = next(w for w in self.f['windows'] if w['phase'] == 'hover')
        mask = (sp['timestamp'] < window['start'] + 1000000) | (sp['timestamp'] > window['start'] + 2000000)
        for key in sp:
            sp[key] = sp[key][mask]
        with self.assertRaisesRegex(ValueError, 'gap over'):
            a.tracking_metrics(p, sp, window['start'], window['end'], ORIGIN, 'hover')


if __name__ == '__main__':
    unittest.main()
