#!/usr/bin/env python3
"""Read-only native ULog acceptance and descriptive Offboard comparison.

No simulator or ROS runtime is started here. The old AUTO_LOITER/nav=4
acceptance routine is deliberately not called. Each required topic and field
must exist in the new log; historical flights never fill missing evidence.
"""

import hashlib
import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import heading_check

from ros_bridge import ENVELOPE_FIELDS, canonical_json, strict_json_loads, wire_fields
from task_contract import (PHASE_DURATION_S, SAFETY_LIMITS, SYSTEM_ORDER, TASK_PHASES, Phase,
                           make_target, validate_origin, validate_target)


_legacy_spec = importlib.util.spec_from_file_location(
    '_offboard_legacy_metrics', Path(__file__).resolve().parents[1] / 'tools' / 'analyze_hover.py')
_legacy = importlib.util.module_from_spec(_legacy_spec)
_legacy_spec.loader.exec_module(_legacy)
require = _legacy.require
dataset = _legacy.dataset
clock = _legacy.clock
clock_statistics = _legacy.clock_statistics
window_weights = _legacy.window_weights
weighted_rms = _legacy.weighted_rms

BASE_TOPICS = ('vehicle_local_position', 'vehicle_attitude', 'vehicle_status',
               'vehicle_land_detected', 'takeoff_status', 'trajectory_setpoint',
               'vehicle_local_position_setpoint')
SCORED_PHASES = {'hover', 'step_up', 'step_down', 'velocity'}
MAX_GAP_US = 500000
BOUNDARY_EXCLUSION_US = 500000
WIRE_ATOL = 1e-4
FLOAT_FIELDS = ('x', 'y', 'z', 'vx', 'vy', 'vz', 'yaw')


def positive_us(value, name):
    require(type(value) is int and value > 0, 'Invalid ' + name)
    return value


def phase_windows(events, task):
    require(task in TASK_PHASES, 'Unknown task')
    require(isinstance(events, list) and events, 'Missing task events')
    pairs, special = {}, {}
    previous = 0
    for event in events:
        require(isinstance(event, dict), 'Invalid task event')
        timestamp = positive_us(event.get('timestamp_us'), 'event timestamp_us')
        require(timestamp >= previous, 'Event time reversed')
        previous = timestamp
        name = event.get('name')
        if name in ('land_command', 'landed_disarmed'):
            require(name not in special, 'Repeated final event ' + name)
            special[name] = timestamp
            continue
        if not isinstance(name, str) or '_' not in name:
            continue
        phase, edge = name.rsplit('_', 1)
        if phase not in set(TASK_PHASES[task]) or edge not in ('start', 'end'):
            continue
        generation = event.get('generation')
        require(type(generation) is int and generation >= 0, 'Missing/invalid phase generation')
        key = (phase, generation)
        pair = pairs.setdefault(key, {})
        require(edge not in pair, 'Repeated phase edge ' + name)
        pair[edge] = timestamp
    windows = []
    for (phase, generation), pair in pairs.items():
        require(set(pair) == {'start', 'end'}, 'Unpaired phase event: ' + phase)
        require(pair['start'] < pair['end'], 'Empty/reversed phase: ' + phase)
        minimum = PHASE_DURATION_S.get(phase)
        if minimum is not None:
            require(pair['end'] - pair['start'] >= round(minimum * 1e6),
                    'Truncated phase duration: ' + phase)
        windows.append(dict(phase=phase, generation=generation, **pair))
    windows.sort(key=lambda value: value['start'])
    require(tuple(value['phase'] for value in windows) == TASK_PHASES[task], 'Missing/reordered task phases')
    for before, after in zip(windows, windows[1:]):
        require(before['end'] <= after['start'], 'Overlapping phase windows')
        require(before['generation'] < after['generation'], 'Phase generation did not advance')
    require(set(special) == {'land_command', 'landed_disarmed'}, 'Missing final flight events')
    require(windows[-1]['end'] <= special['land_command'] < special['landed_disarmed'],
            'Invalid descent/landing/disarm order')
    return windows, special


def _column(data, name, count=None):
    require(name in data, 'Missing native field: ' + name)
    values = np.asarray(data[name])
    require(values.ndim == 1 and (count is None or len(values) == count), 'Invalid native field shape: ' + name)
    return values


def publication_clock(data, name):
    publication = _column(data, 'timestamp')
    result, unused = clock({'timestamp': publication})
    for field, values in data.items():
        require(np.asarray(values).ndim == 1 and len(values) == len(result), 'Inconsistent topic arrays: ' + name + '.' + field)
    return result


def _vectors(data, names, count):
    return np.column_stack([_column(data, name, count) for name in names]).astype(float)


def trajectory_vectors(data):
    """Original PX4 arrays and CODEV scalar trajectory layouts are both explicit."""
    count = len(data['timestamp'])
    scalar = all(name in data for name in ('x', 'y', 'z', 'vx', 'vy', 'vz'))
    array = all(name in data for name in tuple('position[%d]' % i for i in range(3))
                + tuple('velocity[%d]' % i for i in range(3)))
    require(scalar != array, 'Missing or ambiguous trajectory layout')
    p_names = ('x', 'y', 'z') if scalar else tuple('position[%d]' % i for i in range(3))
    v_names = ('vx', 'vy', 'vz') if scalar else tuple('velocity[%d]' % i for i in range(3))
    return _vectors(data, p_names, count), _vectors(data, v_names, count)


def sample_coverage(t, left, right, name, boundary_tolerance=MAX_GAP_US):
    require(left < right, 'Invalid coverage window')
    mask = (t >= left) & (t < right)
    indices = np.flatnonzero(mask)
    require(len(indices) >= 2, 'Insufficient samples: ' + name)
    require(t[indices[0]] - left <= boundary_tolerance and right - t[indices[-1]] <= boundary_tolerance,
            'Missing window edges: ' + name)
    require(np.max(np.diff(t[indices])) <= MAX_GAP_US, 'Native gap over 0.5 s: ' + name)
    return indices


def held_rows(t, left, right, name):
    before = int(np.searchsorted(t, left, side='right') - 1)
    require(before >= 0, 'Missing state predecessor: ' + name)
    return np.r_[before, np.flatnonzero((t > left) & (t < right))]


def hold_check(data, field, left, right, expected, name):
    t = publication_clock(data, name)
    indices = held_rows(t, left, right, name)
    values = _column(data, field, len(t))[indices]
    require(np.all(np.isfinite(values)) and np.all(values == expected), 'Wrong state ' + name + '.' + field)


def diagnostic_contract(job):
    system = job.get('system')
    require(system in SYSTEM_ORDER, 'Unknown system')
    if system == 'STA2':
        required = {'attitude_sta_status': {}}
    else:
        mode = {'PID': 0, 'RSTA': 3, 'RISTA': 4}[system]
        axes = 0 if system == 'PID' else 7
        required = {
            'sta_velocity_ctrl_status': dict(effective_mode=mode, effective_axes=axes,
                active_axes=axes, inner_mode=0, inner_axes=0, fault=0),
            'sta_rate_ctrl_status': dict(effective_mode=0, effective_axes=0, fault=0)}
    for field in ('diagnostic_expectations', 'hover_diagnostic_expectations'):
        supplied = job.get(field, {})
        require(isinstance(supplied, dict), 'Invalid diagnostic expectations')
        for topic, fields in supplied.items():
            require(isinstance(fields, dict), 'Invalid diagnostic field expectations')
            dest = required.setdefault(topic, {})
            for key, expected in fields.items():
                require(key not in dest or dest[key] == expected, 'Conflicting frozen controller expectation')
                dest[key] = expected
    return required


def parameter_audit(log, expected, start, end):
    require(isinstance(expected, dict) and expected, 'Missing expected parameters')
    parameters = dict(getattr(log, 'initial_parameters', {}))
    changes = getattr(log, 'changed_parameters', [])
    previous = -1
    relevant = []
    for change in changes:
        require(len(change) == 3, 'Malformed native parameter change')
        timestamp, name, value = change
        require(timestamp >= previous, 'Parameter change clock reversed')
        previous = timestamp
        if timestamp <= start:
            parameters[name] = value
        elif timestamp <= end and name in expected:
            relevant.append((timestamp, name, value))
    def equal(actual, value):
        return (isinstance(actual, (int, float, np.number)) and
                math.isfinite(float(actual)) and math.isfinite(float(value)) and
                abs(float(actual) - float(value)) <= 1e-5 * max(1.0, abs(float(value))))
    for name, value in expected.items():
        require(name in parameters and equal(parameters[name], value), 'Native parameter mismatch: ' + name)
    for unused, name, value in relevant:
        require(equal(value, expected[name]), 'Native expected parameter changed during flight: ' + name)
    return {'verified_count': len(expected), 'matching_change_records': len(relevant)}


def _json_lines(path):
    require(Path(path).is_file(), 'Missing evidence file: ' + str(path))
    rows = []
    with Path(path).open(encoding='utf-8') as stream:
        for line in stream:
            require(line.strip(), 'Blank JSON evidence row')
            value = strict_json_loads(line)
            require(isinstance(value, dict), 'Invalid JSON evidence row')
            rows.append(value)
    require(rows, 'Empty evidence file: ' + str(path))
    return rows


def control_windows(events):
    controls = [event for event in events if event.get('name') == 'control_change']
    require(len(controls) >= 2 and controls[0].get('enabled') is False and controls[-1].get('enabled') is False,
            'Missing disabled control ownership boundaries')
    previous_generation, previous_time = -1, 0
    for control in controls:
        generation = control.get('generation')
        timestamp = positive_us(control.get('timestamp_us'), 'control timestamp')
        require(type(generation) is int and generation > previous_generation, 'Control generation not strictly increasing')
        require(timestamp >= previous_time and type(control.get('enabled')) is bool,
                'Invalid control ownership time/enabled')
        require(control.get('phase') in {phase.value for phase in Phase}, 'Unknown control phase')
        previous_generation, previous_time = generation, timestamp
    return {control['generation']: dict(control, end=following['timestamp_us'])
            for control, following in zip(controls, controls[1:])}


def audit_sent(sent_path, windows, origin, events):
    """Join real publisher/subscriber receipts by seq and exact JSON payload hash."""
    sent_path = Path(sent_path)
    published = _json_lines(sent_path.with_name('ros_published.jsonl'))
    sent = _json_lines(sent_path)
    by_seq, last_seq, last_sim = {}, 0, -1
    by_generation = {window['generation']: window for window in windows}
    ownership = control_windows(events)
    for row in published:
        require(ENVELOPE_FIELDS.issubset(row), 'Incomplete published ROS envelope')
        require(type(row['seq']) is int and row['seq'] > last_seq, 'Published sequence repeated/reversed')
        require(type(row['sim_us']) is int and row['sim_us'] >= last_sim, 'Published native time reversed')
        payload = {key: row[key] for key in ENVELOPE_FIELDS}
        digest = hashlib.sha256(canonical_json(payload).encode()).hexdigest()
        require(row.get('ros_sha256') == digest, 'Published ROS payload hash mismatch')
        by_seq[row['seq']] = payload, digest
        last_seq, last_sim = row['seq'], row['sim_us']
    last_seq, last_sim, last_generation = 0, -1, -1
    for row in sent:
        require(ENVELOPE_FIELDS.issubset(row), 'Incomplete actual-send envelope')
        seq = row['seq']
        require(type(seq) is int and seq > last_seq and seq in by_seq, 'Invalid actual-send sequence')
        require(type(row['sim_us']) is int and row['sim_us'] >= last_sim, 'Actual-send native time reversed')
        payload = {key: row[key] for key in ENVELOPE_FIELDS}
        require((payload, row.get('ros_sha256')) == by_seq[seq], 'Published/subscribed ROS payload mismatch')
        require(row.get('identity_verified') is True, 'Missing runtime wire identity proof')
        require(row.get('peer') == ['127.0.0.1', 14580] and row.get('source_system') == 245
                and row.get('source_component') == 191, 'Wrong actual-send endpoint/source')
        validate_target(row['target'])
        expected_wire = wire_fields(row['target'], row['sim_us'])
        require(row.get('wire_fields') == expected_wire, 'ROS-to-wire identity mismatch')
        require(type(row.get('generation')) is int and row['generation'] in by_generation,
                'Unknown actual-send phase generation')
        phase = by_generation[row['generation']]
        require(row['phase'] == phase['phase'], 'Wrong actual-send phase')
        require(row['generation'] >= last_generation, 'Actual-send generation regressed')
        require(row['generation'] in ownership, 'Missing actual-send control ownership')
        owner = ownership[row['generation']]
        require(owner['enabled'] is True and owner['phase'] == row['phase'], 'Actual send without enabled phase ownership')
        # Events use native publication time; setpoint generation uses the sampled
        # local-position clock. A small sampled-clock lead is clamped by the bridge.
        delta = row['sim_us'] - owner['timestamp_us']
        require(delta >= -100000 and row['sim_us'] <= owner['end'] + 100000,
                'Actual-send target outside its control ownership')
        require(row['elapsed_s'] == max(0.0, delta / 1000000.0), 'Wrong actual-send phase clock')
        require(row['target'] == make_target(row['phase'], row['elapsed_s'], origin),
                'Actual-send target violates task contract')
        last_seq, last_sim, last_generation = seq, row['sim_us'], row['generation']
    return sent, {'published_count': len(published), 'sent_count': len(sent),
                  'ros_payload_wire_identity': True,
                  'float_conversion': 'Explicit MAVLink float32; target matching absolute tolerance 1e-4'}


def audit_trajectory(data, sent, windows):
    t = publication_clock(data, 'trajectory_setpoint')
    position, velocity = trajectory_vectors(data)
    yaw = _column(data, 'yaw', len(t)).astype(float)
    sent_t = np.asarray([row['sim_us'] for row in sent], dtype=np.int64)
    result = []
    for window in windows:
        if window['phase'] == 'prestream':
            # PX4's MAVLink path only publishes trajectory_setpoint in Offboard.
            continue
        left, right = window['start'], window['end']
        sample_coverage(t, left, right, 'trajectory/' + window['phase'])
        interior = np.flatnonzero((t >= left + BOUNDARY_EXCLUSION_US)
                                  & (t < right - BOUNDARY_EXCLUSION_US))
        require(len(interior) >= 2, 'Missing trajectory interior: ' + window['phase'])
        matches = 0
        for index in interior:
            p, v = position[index], velocity[index]
            require(np.isfinite(yaw[index]), 'Nonfinite trajectory yaw')
            is_velocity = window['phase'] == 'velocity'
            if is_velocity:
                require(np.isfinite(p[:2]).all() and np.isnan(p[2]) and
                        np.isnan(v[:2]).all() and np.isfinite(v[2]), 'Wrong mixed Z-velocity trajectory shape')
            else:
                require(np.isfinite(p).all() and np.isnan(v).all(), 'Wrong position trajectory shape')
            first = int(np.searchsorted(sent_t, t[index] - MAX_GAP_US, side='left'))
            last = int(np.searchsorted(sent_t, t[index], side='right'))
            matched = False
            for row in sent[first:last]:
                if row['generation'] != window['generation']:
                    continue
                fields = row['wire_fields']
                actual = [p[0], p[1], v[2] if is_velocity else p[2], yaw[index]]
                expected = [fields['x'], fields['y'], fields['vz'] if is_velocity else fields['z'], fields['yaw']]
                if np.allclose(actual, expected, atol=WIRE_ATOL, rtol=0):
                    matched = True
                    break
            require(matched, 'Native trajectory has no matching past actual-send target at ' + str(int(t[index])))
            matches += 1
        result.append(dict(phase=window['phase'], generation=window['generation'],
                           matched_native_samples=matches, interior_us=[left + BOUNDARY_EXCLUSION_US,
                                                                       right - BOUNDARY_EXCLUSION_US]))
    return result


def tracking_metrics(position, setpoint, left, right, origin, phase):
    """Integrate actual velocity-reference error on the union of native clocks."""
    pt, source_clock = clock(position)
    st = publication_clock(setpoint, 'vehicle_local_position_setpoint')
    actual = _vectors(position, ('vx', 'vy', 'vz'), len(pt))
    target = _vectors(setpoint, ('vx', 'vy', 'vz'), len(st))
    sample_coverage(pt, left, right, 'metric position/' + phase)
    sample_coverage(st, left, right, 'metric setpoint/' + phase)
    require(pt[0] <= left and st[0] <= left and pt[-1] >= right and st[-1] >= right,
            'Missing full tracking metric boundaries')
    knots = np.unique(np.r_[left, pt[(pt > left) & (pt < right)], st[(st > left) & (st < right)], right])
    weights = np.diff(knots) * 1e-6
    require(abs(float(weights.sum()) - (right - left) / 1e6) < 1e-9, 'Tracking metric coverage mismatch')
    pi = np.searchsorted(pt, knots[:-1], side='right') - 1
    si = np.searchsorted(st, knots[:-1], side='right') - 1
    require(np.all(knots[:-1] - pt[pi] <= MAX_GAP_US) and np.all(knots[:-1] - st[si] <= MAX_GAP_US),
            'Stale native state/reference in metric')
    require(np.isfinite(actual[pi]).all() and np.isfinite(target[si]).all(), 'Nonfinite actual velocity/reference')
    error = actual[pi] - target[si]
    xyz = _vectors(position, ('x', 'y', 'z'), len(pt))
    idx, p_weights = window_weights(pt, left, right)
    displacement = xyz[idx] - np.asarray([origin[key] for key in ('x', 'y', 'z')])
    height = -displacement[:, 2]
    return dict(window_us=[left, right], seconds=(right - left) / 1e6,
                velocity_tracking_rmse_xyz_m_s=weighted_rms(error, weights),
                actual_velocity_rms_xyz_m_s=weighted_rms(actual[pi], weights),
                displacement_rms_xyz_m=weighted_rms(displacement, p_weights),
                horizontal_displacement_max_m=float(np.max(np.linalg.norm(displacement[:, :2], axis=1))),
                height_mean_m=float(np.sum(height * p_weights) / p_weights.sum()),
                height_min_m=float(np.min(height)), height_max_m=float(np.max(height)),
                source_clock=source_clock, position_samples=len(idx), reference_samples=int(np.sum((st >= left) & (st < right))),
                integration_intervals=len(weights),
                definition='Full phase; exact ZOH time integral against actual published controller velocity setpoints, not ROS positions')


def audit_native_log(path, events, origin, job, sent_path, *, ulog_class=None):
    if ulog_class is None:
        from pyulog import ULog
        ulog_class = ULog
    origin = validate_origin(origin)
    windows, special = phase_windows(events, job.get('task'))
    diagnostics = diagnostic_contract(job)
    reset_policy = job.get('heading_reset_policy', heading_check.STRICT)
    require(reset_policy in (heading_check.STRICT, heading_check.POLICY), 'Unknown heading reset policy')
    log = ulog_class(str(path), message_name_filter_list=list(BASE_TOPICS) + list(diagnostics)
                     + (list(heading_check.TOPICS) if reset_policy == heading_check.POLICY else []))
    require(not log.dropouts and not getattr(log, 'file_corruption', False), 'ULog dropout/corruption')
    topics = {}
    for name in (*BASE_TOPICS, *diagnostics):
        data = dataset(log, name)
        require(data is not None, 'Missing required native topic: ' + name)
        publication_clock(data, name)
        topics[name] = data
    start = next(window['start'] for window in windows if window['phase'] == 'climb')
    end = special['landed_disarmed']
    parameters = parameter_audit(log, job.get('expected_parameters'), start, end)
    p = topics['vehicle_local_position']
    t, unused = clock(p)
    require(t[0] < start and t[-1] >= end - 100000, 'Incomplete native position flight boundaries')
    full = np.r_[max(0, np.searchsorted(t, start, side='right') - 1),
                 np.flatnonzero((t >= start) & (t <= end))]
    full = np.unique(full)
    require(len(full) >= 2 and np.max(np.diff(t[full])) <= MAX_GAP_US, 'Full-flight native position gap')
    xyz = _vectors(p, ('x', 'y', 'z'), len(t))
    velocity = _vectors(p, ('vx', 'vy', 'vz'), len(t))
    require(np.isfinite(xyz[full]).all() and np.isfinite(velocity[full]).all(), 'Nonfinite native flight state')
    for key in ('xy_valid', 'z_valid', 'v_xy_valid', 'v_z_valid'):
        require(np.all(_column(p, key, len(t))[full] == 1), 'Invalid native estimate ' + key)
    reset_keys = ('xy_reset_counter', 'z_reset_counter', 'vxy_reset_counter', 'vz_reset_counter')
    for key in reset_keys + (('heading_reset_counter',) if reset_policy == heading_check.STRICT else ()):
        values = _column(p, key, len(t))[full]
        require(np.isfinite(values).all() and not np.any(np.diff(values.astype(np.int64))), 'Native estimator reset: ' + key)
    heading_evidence = None
    if reset_policy == heading_check.POLICY:
        heading_evidence = heading_check.audit(log, start, end,
            next(w['end'] for w in windows if w['phase'] == 'climb'),
            min(w['start'] for w in windows if w['phase'] in SCORED_PHASES), origin,
            schema=heading_check.STA2_SCHEMA if job['system'] == 'STA2' else heading_check.CODEV_SCHEMA)
    displacement = xyz - np.asarray([origin[key] for key in ('x', 'y', 'z')])
    height = -displacement[:, 2]
    require(np.min(height[full]) >= SAFETY_LIMITS['height_range_m'][0]
            and np.max(height[full]) <= SAFETY_LIMITS['height_range_m'][1]
            and np.max(np.abs(velocity[full, 2])) <= SAFETY_LIMITS['vertical_speed_m_s'], 'Full-flight vertical safety envelope')
    require(np.max(np.linalg.norm(velocity[full, :2], axis=1)) <= SAFETY_LIMITS['xy_speed_m_s']
            and np.max(np.linalg.norm(displacement[full, :2], axis=1)) <= SAFETY_LIMITS['xy_displacement_m'],
            'Full-flight horizontal safety envelope')
    attitude = topics['vehicle_attitude']
    clock(attitude, strict=False)  # Resampled attitude clock may repeat; values still must be valid.
    at = publication_clock(attitude, 'vehicle_attitude')
    require(at[0] <= start and at[-1] >= end - 100000, 'Incomplete attitude flight boundaries')
    ai = sample_coverage(at, start, min(end, int(at[-1])), 'full-flight attitude')
    q = _vectors(attitude, tuple('q[%d]' % i for i in range(4)), len(at))[ai]
    norm = np.linalg.norm(q, axis=1)
    require(np.isfinite(q).all() and np.all(norm > 0), 'Invalid native quaternion')
    unit = q / norm[:, None]
    tilt = np.degrees(np.arccos(np.clip(1 - 2 * (unit[:, 1]**2 + unit[:, 2]**2), -1, 1)))
    require(float(np.max(tilt)) <= SAFETY_LIMITS['tilt_deg'], 'Full-flight tilt safety envelope')
    status, land = topics['vehicle_status'], topics['vehicle_land_detected']
    hold_check(status, 'failsafe', start, end, 0, 'vehicle_status')
    hold_check(land, 'freefall', start, end, 0, 'vehicle_land_detected')
    phase_metrics, diag_evidence = [], []
    for window in windows:
        if window['phase'] not in SCORED_PHASES:
            continue
        left, right = window['start'], window['end']
        pi = sample_coverage(t, left, right, 'scored position/' + window['phase'])
        for key, expected in (('nav_state', 14), ('arming_state', 2), ('failsafe', 0)):
            hold_check(status, key, left, right, expected, 'vehicle_status')
        for key in ('landed', 'ground_contact', 'maybe_landed'):
            hold_check(land, key, left, right, 0, 'vehicle_land_detected')
        hold_check(topics['takeoff_status'], 'takeoff_state', left, right, 5, 'takeoff_status')
        if window['phase'] == 'hover':
            require(np.max(abs(height[pi] - 2.5)) <= SAFETY_LIMITS['hover_height_deviation_m']
                    and np.max(abs(velocity[pi, 2])) <= SAFETY_LIMITS['hover_vertical_speed_m_s'], 'Hover safety envelope')
        for name, fields in diagnostics.items():
            data = topics[name]
            dt = publication_clock(data, name)
            indices = sample_coverage(dt, left, right, name + '/' + window['phase'])
            rows = np.unique(np.r_[held_rows(dt, left, right, name), indices])
            for key, expected in fields.items():
                require(np.all(_column(data, key, len(dt))[rows] == expected), 'Wrong active controller ' + name + '.' + key)
            diag_evidence.append(dict(topic=name, phase=window['phase'], generation=window['generation'], samples=len(indices)))
        phase_metrics.append(dict(phase=window['phase'], generation=window['generation'],
                                  **tracking_metrics(p, topics['vehicle_local_position_setpoint'], left, right, origin, window['phase'])))
    final_event = next(event for event in events if event['name'] == 'landed_disarmed')
    status_end = positive_us(final_event.get('status_timestamp_us', end), 'final status timestamp')
    land_end = positive_us(final_event.get('land_timestamp_us', end), 'final land timestamp')
    require(abs(status_end - end) <= MAX_GAP_US and abs(land_end - end) <= MAX_GAP_US,
            'Stale final state receipts')
    hold_check(status, 'arming_state', status_end, status_end + 1, 1, 'vehicle_status')
    hold_check(land, 'landed', land_end, land_end + 1, 1, 'vehicle_land_detected')
    sent, send_evidence = audit_sent(sent_path, windows, origin, events)
    trajectory_evidence = audit_trajectory(topics['trajectory_setpoint'], sent, windows)
    output = dict(accepted=True, task=job['task'], system=job['system'], phase_metrics=phase_metrics,
                  parameters=parameters, send_evidence=send_evidence, trajectory_evidence=trajectory_evidence,
                  diagnostic_evidence=diag_evidence,
                  maximum_tilt_deg=float(np.max(tilt)), maximum_height_m=float(np.max(height[full])),
                  maximum_native_position_gap_s=float(np.max(np.diff(t[full])) * 1e-6),
                  native_resolutions={name: clock_statistics(data) for name, data in topics.items()},
                  trace=dict(time_s=((t[full] - start) * 1e-6).tolist(),
                             velocity=velocity[full].tolist(), displacement=displacement[full].tolist()),
                  caveat='One native-topic system run; EKF estimates, not truth or formal/full-rate acceptance; no ROS transport validation inferred')
    # Returned acceptance evidence must remain ordinary finite JSON.
    if heading_evidence is not None:
        output['heading_evidence'] = heading_evidence
    json.dumps(output, allow_nan=False)
    return output


def plot_four_systems(audits, output):
    """Plot only four accepted measured systems, separately for each task."""
    require(len(audits) == 4 and all(row.get('accepted') is True for row in audits), 'Need four accepted new runs')
    require({row['system'] for row in audits} == set(SYSTEM_ORDER), 'Missing/duplicate comparison system')
    require(len({row['task'] for row in audits}) == 1, 'Cannot mix position/velocity tasks')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    by_system = {row['system']: row for row in audits}
    paths = []
    for kind, filename, labels in (
            ('velocity', 'actual_velocity_xyz.png', ('X velocity / m/s', 'Y velocity / m/s', 'Upward velocity / m/s')),
            ('displacement', 'actual_displacement_xyz.png', ('X displacement / m', 'Y displacement / m', 'Height above origin / m'))):
        path = output / filename
        require(not path.exists(), 'Refusing existing comparison figure')
        figure, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True, constrained_layout=True)
        for system, color in zip(SYSTEM_ORDER, _legacy.COLORS):
            trace = by_system[system]['trace']
            values = np.asarray(trace[kind], dtype=float)
            for axis, plot in enumerate(axes):
                plot.plot(trace['time_s'], values[:, axis] * (-1 if axis == 2 else 1), color=color, label=system)
                plot.set_ylabel(labels[axis])
                plot.grid(alpha=.2)
        for plot in axes:
            require(len(plot.lines) == 4, 'Unexpected extra comparison curve')
        axes[0].legend(ncol=4)
        axes[0].set_title(audits[0]['task'] + ' task | one new run per system')
        axes[-1].set_xlabel('Time since climb phase start / s')
        figure.savefig(path, dpi=170)
        plt.close(figure)
        paths.append(str(path.resolve()))
    return paths
