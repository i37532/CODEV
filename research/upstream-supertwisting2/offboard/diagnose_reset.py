#!/usr/bin/env python3
"""Read-only post-failure diagnostics; never acceptance, retries or array repair.

The frozen audit is rerun unchanged and its failure retained. Independent
components provide context only. This script does not write into an attempt,
change result.json, patch an audit function, modify logged values, or fly.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

import analyze as audit


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def plain(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(item) for item in value]
    return value


def run_diagnosis(attempt):
    from pyulog import ULog
    attempt = Path(attempt).resolve()
    result_path = attempt / 'result.json'
    original = json.loads(result_path.read_text())
    job = json.loads((attempt / 'job.json').read_text())
    origin = json.loads((attempt / 'origin.json').read_text())
    archived = max(original['logs'], key=lambda item: item['bytes'])
    log_path = Path(archived['archive'])
    if not log_path.is_absolute():
        log_path = attempt / log_path
    protected = {'ulog': log_path, 'result': result_path}
    before = {key: sha256(path) for key, path in protected.items()}
    audit.require(before['ulog'] == archived['sha256'], 'Archived ULog fingerprint mismatch')
    log = ULog(str(log_path))
    # This prevents accidental mutation even within this diagnostic process.
    for topic in log.data_list:
        for values in topic.data.values():
            if isinstance(values, np.ndarray):
                values.flags.writeable = False
    checks = []

    def check(name, function):
        try:
            value = function()
            checks.append(dict(name=name, passed=True, evidence=plain(value)))
            return value
        except Exception as exc:
            checks.append(dict(name=name, passed=False, error=repr(exc)))
            return None

    check('frozen_complete_audit_unchanged', lambda: audit.audit_native_log(
        log_path, original['events'], origin, job, attempt / 'ros/sent.jsonl'))
    windows, special = audit.phase_windows(original['events'], job['task'])
    start = next(window['start'] for window in windows if window['phase'] == 'climb')
    end = special['landed_disarmed']
    diagnostic_contract = audit.diagnostic_contract(job)
    topics = {name: audit.dataset(log, name) for name in (*audit.BASE_TOPICS, *diagnostic_contract)}

    def topic_checks():
        evidence = {}
        for name, data in topics.items():
            audit.require(data is not None, 'Missing required topic ' + name)
            publication = audit.publication_clock(data, name)
            evidence[name] = dict(records=len(publication), publication_first_us=int(publication[0]),
                                  publication_last_us=int(publication[-1]))
        audit.require(not log.dropouts and not log.file_corruption, 'Dropout/corruption')
        return dict(dropouts=len(log.dropouts), file_corruption=bool(log.file_corruption), topics=evidence)

    check('topics_publication_clocks_and_integrity', topic_checks)
    check('expected_native_parameters', lambda: audit.parameter_audit(log, job['expected_parameters'], start, end))
    p = topics['vehicle_local_position']
    t, position_clock = audit.clock(p)
    full = np.unique(np.r_[max(0, np.searchsorted(t, start, side='right') - 1),
                           np.flatnonzero((t >= start) & (t <= end))])
    xyz = np.column_stack([p[key] for key in ('x', 'y', 'z')]).astype(float)
    velocity = np.column_stack([p[key] for key in ('vx', 'vy', 'vz')]).astype(float)
    height = origin['z'] - xyz[:, 2]
    horizontal = np.linalg.norm(xyz[:, :2] - [origin['x'], origin['y']], axis=1)
    reset_evidence = {}
    for key in ('xy_reset_counter', 'z_reset_counter', 'vxy_reset_counter', 'vz_reset_counter', 'heading_reset_counter'):
        values = p[key][full]
        changes = np.flatnonzero(np.diff(values.astype(np.int64))) + 1
        reset_evidence[key] = dict(values=np.unique(values).astype(int).tolist(), changes=len(changes),
                                  first_changed_samples_us=[int(t[full[index]]) for index in changes])
        def reset_check(values=values, key=key):
            audit.require(np.isfinite(values).all() and not np.any(np.diff(values.astype(np.int64))),
                          'Native estimator reset: ' + key)
            return reset_evidence[key]
        check('no_reset/' + key, reset_check)

    def full_safety():
        audit.require(t[0] < start and t[-1] >= end - 100000, 'Incomplete position boundaries')
        audit.require(np.max(np.diff(t[full])) <= audit.MAX_GAP_US, 'Position gap')
        audit.require(np.isfinite(xyz[full]).all() and np.isfinite(velocity[full]).all(), 'Nonfinite flight state')
        for key in ('xy_valid', 'z_valid', 'v_xy_valid', 'v_z_valid'):
            audit.require(np.all(p[key][full] == 1), 'Invalid native estimate ' + key)
        audit.require(height[full].min() >= -.5 and height[full].max() <= 4
                      and np.abs(velocity[full, 2]).max() <= 3.5, 'Vertical envelope')
        audit.require(np.linalg.norm(velocity[full, :2], axis=1).max() <= 1
                      and horizontal[full].max() <= 2, 'Horizontal envelope')
        attitude = topics['vehicle_attitude']
        audit.clock(attitude, strict=False)
        at = audit.publication_clock(attitude, 'vehicle_attitude')
        audit.require(at[0] <= start and at[-1] >= end - 100000, 'Attitude boundaries')
        indices = audit.sample_coverage(at, start, min(end, int(at[-1])), 'full-flight attitude')
        q = np.column_stack([attitude['q[%d]' % i] for i in range(4)]).astype(float)[indices]
        norm = np.linalg.norm(q, axis=1)
        audit.require(np.isfinite(q).all() and np.all(norm > 0), 'Quaternion invalid')
        unit = q / norm[:, None]
        tilt = np.degrees(np.arccos(np.clip(1 - 2 * (unit[:, 1]**2 + unit[:, 2]**2), -1, 1)))
        audit.require(tilt.max() <= 15, 'Tilt envelope')
        audit.hold_check(topics['vehicle_status'], 'failsafe', start, end, 0, 'vehicle_status')
        audit.hold_check(topics['vehicle_land_detected'], 'freefall', start, end, 0, 'vehicle_land_detected')
        return dict(window_us=[start, end], position_records=len(full), position_clock=position_clock,
                    maximum_position_gap_s=float(np.diff(t[full]).max() / 1e6),
                    height_range_m=[float(height[full].min()), float(height[full].max())],
                    maximum_absolute_vz_m_s=float(np.abs(velocity[full, 2]).max()),
                    maximum_xy_speed_m_s=float(np.linalg.norm(velocity[full, :2], axis=1).max()),
                    maximum_xy_displacement_m=float(horizontal[full].max()), maximum_tilt_deg=float(tilt.max()))

    check('full_flight_safety_independent_of_reset_rule', full_safety)
    for window in windows:
        if window['phase'] not in audit.SCORED_PHASES:
            continue
        left, right, phase = window['start'], window['end'], window['phase']
        def state_check():
            indices = audit.sample_coverage(t, left, right, phase)
            for field, expected in (('nav_state', 14), ('arming_state', 2), ('failsafe', 0)):
                audit.hold_check(topics['vehicle_status'], field, left, right, expected, 'vehicle_status')
            for field in ('landed', 'ground_contact', 'maybe_landed'):
                audit.hold_check(topics['vehicle_land_detected'], field, left, right, 0, 'vehicle_land_detected')
            audit.hold_check(topics['takeoff_status'], 'takeoff_state', left, right, 5, 'takeoff_status')
            evidence = dict(window_us=[left, right], position_samples=len(indices))
            if phase == 'hover':
                error = float(np.max(np.abs(height[indices] - 2.5)))
                speed = float(np.max(np.abs(velocity[indices, 2])))
                audit.require(error <= 1 and speed <= .6, 'Hover safety envelope')
                evidence.update(maximum_absolute_height_error_m=error, maximum_absolute_vz_m_s=speed)
            return evidence
        check(phase + '/native_state_and_safety', state_check)
        def controller_check():
            evidence = {}
            for name, fields in diagnostic_contract.items():
                data = topics[name]
                dt = audit.publication_clock(data, name)
                indices = audit.sample_coverage(dt, left, right, name)
                rows = np.unique(np.r_[audit.held_rows(dt, left, right, name), indices])
                for field, expected in fields.items():
                    audit.require(np.all(data[field][rows] == expected), 'Wrong controller ' + name + '.' + field)
                evidence[name] = dict(samples=len(indices), expected_fields=fields)
            return evidence
        check(phase + '/actual_controller_identity', controller_check)
        check(phase + '/descriptive_metrics_not_accepted', lambda: audit.tracking_metrics(
            p, topics['vehicle_local_position_setpoint'], left, right, origin, phase))

    def final_state():
        event = next(event for event in original['events'] if event['name'] == 'landed_disarmed')
        status_time, land_time = event.get('status_timestamp_us', end), event.get('land_timestamp_us', end)
        audit.require(abs(status_time - end) <= audit.MAX_GAP_US and abs(land_time - end) <= audit.MAX_GAP_US,
                      'Stale final state receipt')
        audit.hold_check(topics['vehicle_status'], 'arming_state', status_time, status_time + 1, 1, 'vehicle_status')
        audit.hold_check(topics['vehicle_land_detected'], 'landed', land_time, land_time + 1, 1, 'vehicle_land_detected')
        return dict(status_timestamp_us=status_time, land_timestamp_us=land_time, landed=True, disarmed=True)
    check('final_landed_disarmed_native_receipts', final_state)
    sent_result = check('ROS_publisher_to_actual_wire_receipts', lambda: audit.audit_sent(
        attempt / 'ros/sent.jsonl', windows, origin, original['events'])[1])
    if sent_result is not None:
        check('native_trajectory_against_past_wire_receipts', lambda: audit.audit_trajectory(
            topics['trajectory_setpoint'], audit._json_lines(attempt / 'ros/sent.jsonl'), windows))

    changes = np.flatnonzero(np.diff(p['heading_reset_counter'].astype(np.int64))) + 1
    heading_events = []
    for index in changes:
        timestamp = int(t[index])
        heading_events.append(dict(timestamp_us=timestamp, previous_sample_us=int(t[index - 1]),
            counter_before=int(p['heading_reset_counter'][index - 1]), counter_after=int(p['heading_reset_counter'][index]),
            delta_heading_rad=float(p['delta_heading'][index]), delta_heading_deg=math.degrees(float(p['delta_heading'][index])),
            height_above_origin_m=float(height[index]), during_frozen_flight=bool(start <= timestamp <= end),
            phase=next((w['phase'] for w in windows if w['start'] <= timestamp < w['end']), None)))
    flag_data = log.get_dataset('estimator_status_flags', 0).data
    flag_changes = np.flatnonzero(np.diff(flag_data['cs_mag_aligned_in_flight'].astype(np.int64))) + 1
    flags = []
    flag_fields = ('timestamp', 'timestamp_sample', 'cs_in_air', 'cs_fixed_wing', 'cs_yaw_align',
                   'cs_ev_yaw', 'cs_gps_yaw', 'cs_mag_aligned_in_flight', 'cs_mag_hdg', 'cs_mag_3d',
                   'cs_mag_fault', 'cs_mag_field_disturbed', 'reject_yaw')
    for index in flag_changes:
        if start <= flag_data['timestamp'][index] <= end and flag_data['cs_mag_aligned_in_flight'][index]:
            flags.append(dict(before={key: plain(flag_data[key][index - 1]) for key in flag_fields},
                              after={key: plain(flag_data[key][index]) for key in flag_fields}))
    selector = log.get_dataset('estimator_selector_status', 0).data
    selector_rows = (selector['timestamp'] >= start) & (selector['timestamp'] <= end)
    estimator_events = log.get_dataset('estimator_event_flags', 0).data
    after = {key: sha256(path) for key, path in protected.items()}
    audit.require(before == after, 'Read-only evidence fingerprint changed')
    return plain(dict(schema=1, diagnostic_only=True, not_acceptance=True, original_success=original['success'],
        original_analysis_error=original.get('analysis_error'), original_outcome_unchanged=True,
        source_attempt=str(attempt), source_script_sha256=sha256(__file__),
        protected_sha256_before=before, protected_sha256_after=after, checks=checks,
        heading_events=heading_events, reset_counter_evidence=reset_evidence, estimator0_alignment_flags=flags,
        selected_estimator=dict(primary_instances=np.unique(selector['primary_instance'][selector_rows]),
            instance_changed_counts=np.unique(selector['instance_changed_count'][selector_rows])),
        emergency_yaw_events={key: bool(np.any(estimator_events[key])) for key in
            ('emergency_yaw_reset_mag_stopped', 'bad_yaw_using_gps_course', 'yaw_aligned_to_imu_gps', 'stopping_mag_use')},
        interpretation='Evidence supports the normal first in-air magnetic yaw alignment path. The frozen no-heading-reset requirement remains violated; independent checks do not change acceptance.',
        source_evidence=[dict(path='src/lib/ecl/EKF/mag_control.cpp', line=127,
            meaning='First in-air yaw reset requested above internal 1.5 m HAGL threshold'),
            dict(path='src/lib/ecl/EKF/mag_control.cpp', line=167,
                 meaning='In-air magnetic reset marks mag_aligned_in_flight'),
            dict(path='src/lib/ecl/EKF/ekf_helper.cpp', line=1585,
                 meaning='Yaw reset records quaternion delta and increments reset counter')]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    audit.require(not args.output.exists(), 'Refusing existing diagnosis output')
    audit.require(args.output.resolve() != args.attempt.resolve()
                  and not args.output.resolve().is_relative_to(args.attempt.resolve()),
                  'Diagnosis must be written outside the original attempt')
    evidence = run_diagnosis(args.attempt)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(evidence, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    print(json.dumps(dict(diagnostic_only=True, not_acceptance=True, output=str(args.output.resolve()),
                         checks=len(evidence['checks']),
                         failed_checks=[row['name'] for row in evidence['checks'] if not row['passed']],
                         original_outcome_unchanged=evidence['original_outcome_unchanged'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
