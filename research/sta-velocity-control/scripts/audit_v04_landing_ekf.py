#!/usr/bin/env python3
"""Offline evidence extraction, NOT a flight acceptance/reclassification tool.

No simulator, parameter writes, compensation changes or new protocol. Exact
timestamp joins only. Ground truth is offline diagnosis, never controller input.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess

import numpy as np
from pyulog import ULog

REPO = Path(__file__).resolve().parents[3]
SOURCES = [
    'src/modules/ekf2/EKF2Selector.cpp', 'src/modules/ekf2/EKF2Selector.hpp',
    'src/modules/flight_mode_manager/FlightModeManager.cpp',
    'src/modules/flight_mode_manager/tasks/FlightTask/FlightTask.cpp',
    'src/modules/flight_mode_manager/tasks/Auto/FlightTaskAuto.cpp',
    'src/modules/flight_mode_manager/tasks/AutoMapper/FlightTaskAutoMapper.cpp',
    'src/modules/flight_mode_manager/tasks/AutoLineSmoothVel/FlightTaskAutoLineSmoothVel.cpp',
    'src/modules/mc_pos_control/MulticopterPositionControl.cpp',
    'src/modules/mc_pos_control/PositionControl/PositionControl.cpp',
    'src/modules/mc_pos_control/PositionControl/StaVelocityProtection.cpp',
    'src/modules/mc_att_control/mc_att_control_main.cpp',
    'src/modules/mc_att_control/AttitudeControl/AttitudeControl.hpp',
    'src/modules/simulator/simulator_mavlink.cpp',
    'src/modules/simulator/simulator.h',
    'src/lib/drivers/accelerometer/PX4Accelerometer.cpp',
    'msg/sensor_accel_fifo.msg', 'src/modules/logger/logged_topics.cpp',
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.generic):
        return clean(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)  # Explicit non-finite marker, never substitute zero.
    return value


def exact_index(data, timestamp):
    ids = np.flatnonzero(data['timestamp'] == timestamp)
    if len(ids) != 1:
        raise ValueError(f'Expected exactly one sample at {timestamp}, got {len(ids)}')
    return int(ids[0])


def row(data, index):
    return {k: v[index].item() for k, v in data.items()}


def combined(vel, pos, hgt):
    # Selector metric only; not an independent estimator implementation.
    values = [v if math.isfinite(v) and v > 0 else 1.0 for v in (vel, pos, hgt)]
    return max(.5 * (values[0] + values[1]), values[2])


def source_target_comparison(diag, target, local, translated):
    pairs = [('p_sp[0]', 'x', 'delta_xy[0]'), ('p_sp[1]', 'y', 'delta_xy[1]'),
             ('p_sp[2]', 'z', 'delta_z'), ('v_ff[0]', 'vx', 'delta_vxy[0]'),
             ('v_ff[1]', 'vy', 'delta_vxy[1]'), ('v_ff[2]', 'vz', 'delta_vz')]
    result = {}
    for dest, src, delta in pairs:
        expected = np.float32(target[src])
        if translated:
            expected = np.float32(expected + np.float32(local[delta]))
        actual = diag[dest]
        same = (math.isnan(actual) and math.isnan(expected)) or actual == expected
        result[dest] = dict(actual=actual, expected=float(expected), exactly_equal=bool(same))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    run, out = args.run.resolve(), args.output.resolve()
    if out == run or run in out.parents or REPO in out.parents:
        raise ValueError('Use a new external audit directory, not the raw run or repository')
    out.mkdir(parents=True, exist_ok=False)
    record = json.loads((run / 'result.json').read_text())
    evidence = dict(kind='offline_audit_not_acceptance', new_flights=0, accepted=False,
                    historical_acceptance_changed=False, original_error=record['error'],
                    audit_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
                    flight_head=record['source_head'], checks=[], logs=[])

    def check(name, value):
        evidence['checks'].append(dict(name=name, passed=bool(value)))

    decoded = []
    for item in record['logs']:
        if sha(item['archive']) != item['sha256']:
            raise ValueError('Original ULog fingerprint changed')
        ulog = ULog(item['archive'])
        decoded.append((item['bytes'], ulog))
        evidence['logs'].append(dict(**item, dropouts=len(ulog.dropouts), corruption=bool(ulog.file_corruption)))
    u = max(decoded, key=lambda v: v[0])[1]
    events = {e['name']: e['timestamp_us'] for e in record['events']}
    check('incomplete_failed_run_preserved', not record['success'] and 'landed_disarmed' not in events)
    check('both_ULogs_no_reported_dropout_or_corruption', all(not x['dropouts'] and not x['corruption'] for x in evidence['logs']))
    lp = u.get_dataset('vehicle_local_position').data
    ss = u.get_dataset('estimator_selector_status').data
    d = u.get_dataset('sta_velocity_ctrl_status').data
    target = u.get_dataset('trajectory_setpoint').data
    output = u.get_dataset('vehicle_local_position_setpoint').data
    switches = np.flatnonzero(np.r_[False, np.diff(ss['primary_instance'].astype(int)) != 0]
                             & (ss['timestamp'] >= events['land_command']))
    if len(switches) != 1:
        raise ValueError('This audit expects exactly one recorded landing switch')
    si = int(switches[0]); time = int(ss['timestamp'][si])
    li = exact_index(lp, time); di = exact_index(d, time)
    local = row(lp, li); before = row(lp, li - 1); diag = row(d, di)
    ti = exact_index(target, diag['setpoint_timestamp'])
    oi = exact_index(output, diag['output_timestamp'])
    next_di = di + 1
    fresh = row(d, next_di); fresh_lp = row(lp, exact_index(lp, fresh['input_timestamp']))
    fresh_target = row(target, exact_index(target, fresh['setpoint_timestamp']))
    fresh_output = row(output, exact_index(output, fresh['output_timestamp']))
    old_match = source_target_comparison(diag, row(target, ti), local, True)
    new_match = source_target_comparison(fresh, fresh_target, fresh_lp, False)
    evidence['switch'] = dict(timestamp_us=time, previous_local=before, local=local,
                             selector_before=row(ss, si - 1), selector_after=row(ss, si))
    evidence['compensation'] = dict(old_diag=diag, old_target=row(target, ti), old_comparison=old_match,
                                   fresh_diag=fresh, fresh_local=fresh_lp, fresh_target=fresh_target,
                                   fresh_comparison=new_match,
                                   yaw_old_raw=float(target['yaw'][ti]), yaw_old_output=float(output['yaw'][oi]),
                                   yaw_fresh_raw=fresh_target['yaw'], yaw_fresh_output=fresh_output['yaw'])
    check('old_cache_timestamp_and_single_all_axis_compensation', diag['setpoint_timestamp'] < time
          and diag['reset_bits'] == 31 and all(x['exactly_equal'] for x in old_match.values()))
    check('old_yaw_compensated', output['yaw'][oi] == np.float32(target['yaw'][ti] + lp['delta_heading'][li]))
    check('fresh_target_same_timestamp_not_translated_again', fresh['setpoint_timestamp'] == fresh['input_timestamp']
          and fresh['reset_bits'] == 0 and fresh_output['yaw'] == fresh_target['yaw']
          and all(x['exactly_equal'] for x in new_match.values()))
    check('fresh_vertical_velocity_matches_new_estimate_not_old_plus_delta',
          fresh_target['vz'] == fresh_lp['vz'] and fresh_target['vz'] != diag['v_ff[2]'])
    for f, delta in [('x', 'delta_xy[0]'), ('y', 'delta_xy[1]'), ('z', 'delta_z'),
                     ('vx', 'delta_vxy[0]'), ('vy', 'delta_vxy[1]'), ('vz', 'delta_vz')]:
        check('public_reset_delta_' + f, local[delta] == float(np.float32(local[f]) - np.float32(before[f])))
    primary, alternative = int(ss['primary_instance'][si - 1]), int(ss['primary_instance'][si])
    delta = np.float32(ss[f'combined_test_ratio[{alternative}]'][si - 1]
                       - ss[f'combined_test_ratio[{primary}]'][si - 1])
    predicted = np.float32(ss[f'relative_test_ratio[{alternative}]'][si - 1] + delta)
    evidence['selector'] = dict(error_delta=float(delta), predicted_next_relative=float(predicted),
        configured_error_reduction=u.initial_parameters['EKF2_SEL_ERR_RED'], source_relative_switch_threshold=-.5,
        interpretation='Logged scores and healthy flags support lower-relative-error selection; no branch-reason telemetry')
    check('lower_error_branch_conditions_supported', predicted <= -.5
          and delta < -max(.05, u.initial_parameters['EKF2_SEL_ERR_RED'])
          and bool(ss[f'healthy[{primary}]'][si]) and bool(ss[f'healthy[{alternative}]'][si])
          and not ss['gyro_fault_detected'][si] and not ss['accel_fault_detected'][si]
          and time - ss['last_instance_change'][si - 1] > 10000000)
    land_mask = d['timestamp'] >= events['land_command']
    evidence['landing_diag_values'] = {k: np.unique(d[k][land_mask]).tolist() for k in
        ['effective_mode', 'effective_axes', 'inner_mode', 'inner_axes', 'inner_divisor', 'inner_valid',
         'first_fail', 'retry_result', 'fault', 'sta_fault', 'failsafe', 'constraint_bits', 'reset_bits', 'timing']}
    check('PID_and_no_controller_failure_in_recorded_landing', all(evidence['landing_diag_values'][k] == [v] for k, v in
          dict(effective_mode=0, effective_axes=0, inner_mode=0, inner_axes=0, inner_divisor=1, inner_valid=1,
               first_fail=0, retry_result=0, fault=0, sta_fault=0, failsafe=0, timing=0).items()))
    evidence['z_transition'] = [{k: d[k][j].item() for k in
        ['timestamp', 'p_sp[2]', 'v_ff[2]', 'v_sp[2]', 'v[2]', 'v_dot[2]', 'a_req[2]', 'thrust[2]']}
        for j in [di - 1, di, di + 1]]
    check('Z_error_continuity_at_old_cache_switch', abs((d['v_sp[2]'][di] - d['v[2]'][di])
          - (d['v_sp[2]'][di - 1] - d['v[2]'][di - 1])) < 1e-6)
    evidence['parameters'] = {k: v for k, v in u.initial_parameters.items() if k.startswith(
        ('EKF2_SEL', 'MPC_LAND', 'MPC_Z_VEL', 'MPC_XY_VEL', 'MC_RTC', 'MC_STA_TKO', 'MPC_VC_'))}
    timeline = {}
    topics = {'estimator_selector_status', 'estimator_status', 'estimator_status_flags', 'estimator_innovations',
        'estimator_local_position', 'vehicle_local_position', 'vehicle_local_position_groundtruth', 'sensor_selection',
        'sensor_combined', 'sensor_accel', 'vehicle_imu', 'vehicle_imu_status', 'sensors_status_imu',
        'trajectory_setpoint', 'vehicle_local_position_setpoint', 'vehicle_attitude', 'vehicle_attitude_setpoint',
        'vehicle_rates_setpoint', 'position_setpoint_triplet', 'vehicle_land_detected', 'sta_velocity_ctrl_status'}
    evidence['topic_coverage'] = {}
    for stream in u.data_list:
        if stream.name not in topics:
            continue
        data = stream.data; ts = data['timestamp']; key = f'{stream.name}:{stream.multi_id}'
        ix = np.flatnonzero((ts >= time - 2000000) & (ts <= time + 500000))
        timeline[key] = [row(data, int(j)) for j in ix]
        gaps = np.diff(ts.astype(np.int64))
        evidence['topic_coverage'][key] = dict(full_log_samples=len(ts), window_samples=len(ix),
            full_log_max_gap_us=int(max(gaps)) if len(gaps) else None)
    truth = u.get_dataset('vehicle_local_position_groundtruth').data
    ix = np.flatnonzero((truth['timestamp'] >= time - 500000) & (truth['timestamp'] < time))
    evidence['truth_before_switch'] = [{k: truth[k][j].item() for k in ['timestamp', 'z', 'vz']} for j in ix]
    check('truth_vertical_reversal_precedes_switch', np.any(truth['vz'][ix] > .5) and np.any(truth['vz'][ix] < -.4))
    check('finite_Z_target_so_no_z_deriv_blending_in_switch_frames', all(math.isfinite(d['p_sp[2]'][j]) for j in [di-1, di, di+1]))
    frozen = json.loads((REPO/'research/sta-velocity-control/v04/protocol07/frozen.json').read_text())
    unchanged = all(sha(REPO / p) == expected for p, expected in frozen['assets'].items())
    evidence['frozen_assets'] = dict(count=len(frozen['assets']), unchanged=unchanged)
    check('all_protocol07_frozen_assets_unchanged', unchanged)
    evidence['source_sha256'] = {p: sha(REPO/p) for p in SOURCES}
    evidence['recursive_submodules'] = subprocess.check_output(['git', 'submodule', 'status', '--recursive'], cwd=REPO, text=True)
    evidence['eeprom_sha256'] = sha(REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016')
    evidence['limits'] = ['Not a new protocol, no automatic reset exemption or reclassification.',
        'No full-rate alternative IMU/raw HIL peak; integer narrowing cause remains a hypothesis.',
        'Ground truth 10 Hz and no contact impulse: reversal is observed, exact contact cause unproved.',
        'Attitude internal adapted setpoint and FlightTask internal state not logged: no full-chain bumpless proof.',
        'Only PID flown; no ESTA landing/reset safety or future completion inferred.']
    (out/'timeline.json').write_text(json.dumps(clean(timeline), indent=2, allow_nan=False)+'\n')
    evidence['timeline_sha256'] = sha(out/'timeline.json')
    originals = sorted(p for p in run.parent.rglob('*') if p.is_file() and not p.is_symlink())
    (out/'original_artifacts.sha256').write_text(''.join(f'{sha(p)}  {p}\n' for p in originals))
    evidence['original_artifact_count'] = len(originals)
    evidence['diagnostic_passed'] = all(c['passed'] for c in evidence['checks'])
    (out/'audit.json').write_text(json.dumps(clean(evidence), indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(checks=evidence['checks'], diagnostic_passed=evidence['diagnostic_passed'], accepted=False), indent=2))
    return 0 if evidence['diagnostic_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
