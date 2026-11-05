#!/usr/bin/env python3
"""Decode V00 logs. No interpolation; asynchronous matches expose their age."""
import argparse
import json
from pathlib import Path
import re

import numpy as np
from position_log import ULog

from run_v00 import check_parameters, digest, CONFIG, save


def stats(x, weights=None):
    x = np.asarray(x, dtype=float)
    if not len(x) or not np.all(np.isfinite(x)):
        raise ValueError('Empty/nonfinite metric')
    mean = np.average(x, axis=0, weights=weights)
    return {'rmse': np.sqrt(np.average(x*x, axis=0, weights=weights)).tolist(),
            'mean': mean.tolist(), 'std': np.sqrt(np.average((x-mean)**2, axis=0, weights=weights)).tolist(),
            'max_abs': np.max(np.abs(x), axis=0).tolist()}


def previous_indices(source_time, targets, max_age_us=None):
    i = np.searchsorted(source_time, targets, side='right') - 1
    if np.any(i < 0):
        raise ValueError('No preceding sample')
    age = targets.astype(np.int64) - source_time[i].astype(np.int64)
    if max_age_us is not None and np.any(age > max_age_us):
        raise ValueError('Asynchronous pairing too old')
    return i, age


def analyze(run, protocol, *, attitude_policy=None):
    result = json.loads((run / 'result.json').read_text())
    events = {e['name']: e['timestamp_us'] for e in result['events']}
    start, end = events['hover_start'], events['hover_end']
    flight_start, flight_end = events['takeoff_command'], events['landed_disarmed']
    candidates = []
    for entry in result['logs']:
        if digest(Path(entry['archive'])) != entry['sha256']:
            raise ValueError('ULog fingerprint mismatch')
        log = ULog(entry['archive'])
        try:
            d = log.get_dataset('sta_rate_ctrl_status').data
            if d['timestamp'][0] <= flight_start and d['timestamp'][-1] >= flight_end:
                candidates.append((entry, log))
        except (KeyError, IndexError):
            pass
    if len(candidates) != 1:
        raise ValueError(f'Need one complete flight log, found {len(candidates)}')
    entry, log = candidates[0]
    log.get_dataset('vehicle_local_position')
    save(run/'position_log_evidence.json', log.position_log_evidence)
    checks = {'runner_success': bool(result['success']), 'observation_90s': 90 <= (end-start)*1e-6 <= 92,
              'no_ulog_dropout': len(log.dropouts) == 0}
    output = dict(accepted=False, checks=checks, ulog=entry, hover_seconds=(end-start)*1e-6,
                  topic_rates={}, metrics={}, limitations=[])

    def data(name):
        if attitude_policy is not None and name == 'vehicle_attitude':
            return attitude_policy.data(log, name)
        return log.get_dataset(name).data

    def mask(d, a=start, b=end):
        return (d['timestamp'] >= a) & (d['timestamp'] < b)

    def vec(d, fields):
        return np.column_stack([d[k] for k in fields])

    def all_state(name, field, value, a, b):
        d = data(name)
        i, _ = previous_indices(d['timestamp'], np.array([a]))
        v = np.r_[d[field][i], d[field][mask(d, a, b)]]
        return bool(np.all(v == value))

    expected = json.loads((run / 'runtime_parameters_start.json').read_text())
    critical = {**json.loads((CONFIG / 'frozen.json').read_text())['control_parameters'],
                **protocol['startup_overrides']}
    required_names = ['MPC_XY_P','MPC_Z_P','MPC_XY_VEL_P_ACC','MPC_XY_VEL_I_ACC','MPC_XY_VEL_D_ACC',
        'MPC_Z_VEL_P_ACC','MPC_Z_VEL_I_ACC','MPC_Z_VEL_D_ACC','MPC_USE_HTE',
        'MC_ROLLRATE_P','MC_ROLLRATE_I','MC_ROLLRATE_D','MC_PITCHRATE_P','MC_PITCHRATE_I','MC_PITCHRATE_D',
        'MC_YAWRATE_P','MC_YAWRATE_I','MC_YAWRATE_D']
    logged_critical = {k: v for k,v in critical.items() if k in log.initial_parameters or k in required_names}
    check_parameters(log.initial_parameters, {**logged_critical, **protocol['startup_overrides'],
                                             'SDLOG_PROFILE': expected['SDLOG_PROFILE']})
    output['parameters_not_in_used_only_ulog'] = sorted(set(critical)-set(log.initial_parameters))
    check_parameters(json.loads((run / 'runtime_parameters_end.json').read_text()), critical)
    checks['critical_parameters_unchanged'] = not any(name in critical or name in protocol['startup_overrides']
        for _, name, _ in log.changed_parameters)
    checks['hover_loiter'] = all_state('vehicle_status', 'nav_state', 4, start, end)
    checks['hover_armed'] = all_state('vehicle_status', 'arming_state', 2, start, end)
    checks['hover_airborne'] = all_state('vehicle_land_detected', 'landed', 0, start, end)
    checks['no_failsafe'] = all_state('vehicle_status', 'failsafe', 0, flight_start, flight_end)
    checks['no_failure_detector'] = all_state('vehicle_status', 'failure_detector_status', 0, flight_start, flight_end)
    checks['landed_disarmed'] = bool(data('vehicle_status')['arming_state'][-1] == 1 and data('vehicle_land_detected')['landed'][-1])
    for name in ('vehicle_local_position', 'vehicle_local_position_setpoint', 'trajectory_setpoint',
                 'vehicle_attitude', 'vehicle_attitude_setpoint', 'actuator_controls_0',
                 'sta_rate_ctrl_status', 'multirotor_motor_limits'):
        d = data(name)
        if attitude_policy is not None and name == 'vehicle_attitude':
            rates, covered = attitude_policy.topic_rates(d, mask(d))
            output['topic_rates'][name] = rates
            checks[name + '_coverage'] = covered
            continue
        t = d['timestamp'][mask(d)].astype(np.int64)
        if len(t) < 2 or np.any(np.diff(t) <= 0):
            raise ValueError('Missing/nonmonotonic topic: ' + name)
        dt = np.diff(t)*1e-6
        output['topic_rates'][name] = dict(n=len(t), hz=(len(t)-1)/((t[-1]-t[0])*1e-6),
            dt_min_s=float(dt.min()), dt_median_s=float(np.median(dt)), dt_max_s=float(dt.max()),
            dt_p95_s=float(np.percentile(dt,95)))
        checks[name + '_coverage'] = bool(dt.max() <= .25 and len(t) >= 600)

    d = data('sta_rate_ctrl_status')
    fm, hm = mask(d, flight_start, flight_end), mask(d)
    for field, value in {'effective_mode': 0, 'effective_axes': 0, 'requested_mode': 0,
                         'requested_axes': 0, 'div_eff': 1, 'div_req': 1, 'fault': 0,
                         'abort_requested': 0, 'termination': 0, 'experiment_updated': 0}.items():
        checks['rate_' + field] = bool(np.all(d[field][fm] == value))
    checks['rate_sequence_complete'] = bool(np.all(np.diff(d['publish_seq'][fm].astype(np.int64)) == 1))
    active = fm & d['armed'].astype(bool) & d['rate_enabled'].astype(bool)
    checks['rate_active_valid'] = bool(np.any(active) and np.all(d['output_valid'][active])
        and np.all(d['measurement_valid'][active]) and np.all(d['timing_status'][active] == 0))
    checks['hover_pid_updates'] = bool(np.all(d['pid_updated'][hm]) and np.all(d['updated'][hm]))
    for key in ('research_roll_addition', 'research_pitch_addition', 'research_yaw_addition'):
        checks[key + '_zero'] = bool(np.all(d[key][fm] == 0))
    output['metrics']['rate_error_rad_s'] = stats(vec(d, [f's[{i}]' for i in range(3)])[hm])

    pos, sp = data('vehicle_local_position'), data('vehicle_local_position_setpoint')
    pf, ph, sh = mask(pos, flight_start, flight_end), mask(pos), mask(sp)
    for k in ('xy_valid', 'z_valid', 'v_xy_valid', 'v_z_valid'):
        checks[k] = bool(np.all(pos[k][pf]))
    ground = np.asarray(json.loads((run / 'ground.json').read_text()))
    xyz = vec(pos, ['x', 'y', 'z'])
    velocity = vec(pos, ['vx', 'vy', 'vz'])
    height = ground[2] - xyz[:,2]
    checks['height_whole_flight'] = bool(np.all((height[pf] >= -.5) & (height[pf] <= 4)))
    checks['hover_height'] = bool(np.max(np.abs(height[ph]-2.5)) <= 1)
    checks['xy_position'] = bool(np.max(np.linalg.norm(xyz[pf,:2]-ground[:2],axis=1)) <= 2)
    checks['xy_speed'] = bool(np.max(np.linalg.norm(velocity[pf,:2],axis=1)) <= 1)
    checks['z_speed_flight'] = bool(np.max(np.abs(velocity[pf,2])) <= 3.5)
    checks['z_speed_hover'] = bool(np.max(np.abs(velocity[ph,2])) <= .6)
    # Final published setpoint paired with newest preceding measured state.
    # No claim that this uninstrumented module consumed exactly that sample.
    times = sp['timestamp'][sh].astype(np.int64)
    ix, age = previous_indices(pos['timestamp'], times, 20000)
    weights = np.diff(np.r_[times, int(end)]) * 1e-6
    if weights.sum() < 89.75:
        raise ValueError('Metric time coverage below 89.75 seconds')
    output['pairing_age_us'] = dict(max=int(age.max()), median=float(np.median(age)), matched=len(ix))
    output['metrics']['velocity_error_m_s'] = stats(vec(sp,['vx','vy','vz'])[sh] - velocity[ix], weights)
    output['metrics']['position_error_m'] = stats(vec(sp,['x','y','z'])[sh] - xyz[ix], weights)
    output['metrics']['height_error_from_2p5_m'] = stats(height[ph]-2.5)
    output['metrics']['acceleration_request_m_s2'] = stats(vec(sp,[f'acceleration[{i}]' for i in range(3)])[sh])
    output['metrics']['thrust_ned_normalized'] = stats(vec(sp,[f'thrust[{i}]' for i in range(3)])[sh])
    for name in ('timestamp', 'timestamp_sample'):
        delta = np.diff(pos[name][ph].astype(np.int64))*1e-6
        output['metrics']['position_' + name + '_delta_s'] = stats(delta)
    output['metrics']['position_publish_minus_sample_s'] = stats(
        (pos['timestamp'][ph].astype(np.int64)-pos['timestamp_sample'][ph].astype(np.int64))*1e-6)
    qd = data('vehicle_attitude')
    q = vec(qd,[f'q[{i}]' for i in range(4)])
    tilt = np.rad2deg(np.arccos(np.clip(1-2*(q[:,1]**2+q[:,2]**2),-1,1)))
    checks['tilt_15deg'] = bool(np.max(tilt[mask(qd,flight_start,flight_end)]) <= 15)
    output['metrics']['tilt_deg'] = stats(tilt[mask(qd)])
    yaw = np.arctan2(2*(q[:,0]*q[:,3]+q[:,1]*q[:,2]),1-2*(q[:,2]**2+q[:,3]**2))
    ay = data('vehicle_attitude_setpoint')
    j, _ = previous_indices(ay['timestamp'], qd['timestamp'][mask(qd)], 20000)
    ye = np.angle(np.exp(1j*(yaw[mask(qd)]-ay['yaw_body'][j])))
    output['metrics']['yaw_error_rad'] = stats(ye)
    checks['yaw_error'] = bool(np.max(np.abs(ye)) <= math_radians_20())
    if attitude_policy is not None:
        # Both boundaries/all tied records checked; descriptive yaw metric keeps
        # its old one-record-one-weight convention. No change to velocity dt.
        output['attitude_clock_safety'] = dict(
            flight=attitude_policy.safety(qd, ay, flight_start, flight_end, check_yaw=False),
            hover=attitude_policy.safety(qd, ay, start, end))
        revised = attitude_policy.yaw_metrics(qd, ay, start, end)
        output['metrics']['yaw_error_rad'] = revised['stats']
        output['attitude_yaw_semantics'] = {k:v for k,v in revised.items() if k != 'stats'}
    act = data('actuator_controls_0')
    af = vec(act,[f'control[{i}]' for i in range(4)])[mask(act,flight_start,flight_end)]
    checks['finite_bounded_commands'] = bool(np.all(np.isfinite(af)) and np.max(np.abs(af)) <= 1.001)
    # Exact timestamp_sample intersection only; missing downstream records are
    # disclosed, never interpolated into a false equality claim.
    at = act['timestamp_sample'].astype(np.int64)
    dt = d['timestamp_sample'][hm].astype(np.int64)
    if attitude_policy is not None:
        from v04_attitude_clock09 import strict_clock
        strict_clock(at)
        strict_clock(dt)
    common, ia, ib = np.intersect1d(at, dt, return_indices=True)
    if not len(common):
        raise ValueError('No actual actuator matches')
    ca = vec(act,[f'control[{i}]' for i in range(3)])[ia]
    cd = vec(d,[f'c_applied[{i}]' for i in range(3)])[hm][ib]
    output['actuator_matches'] = dict(matched=len(common), diagnostic_count=len(dt), coverage=len(common)/len(dt),
        max_gap_s=float(np.max(np.diff(common))*1e-6) if len(common)>1 else None,
        max_abs_error=float(np.max(np.abs(ca-cd))))
    checks['matched_actuator_equal'] = bool(np.array_equal(ca, cd))
    checks['matched_actuator_coverage'] = bool(len(common)/len(dt) >= .8 and output['actuator_matches']['max_gap_s'] <= .25)
    output['consumed_mixer_saturation_fraction'] = float(np.mean(d['sat_bits'][hm] != 0))
    output['consumed_mixer_valid_fraction'] = float(np.mean(d['sat_valid'][hm]))
    counts = re.findall(r'mc_pos_control: cycle:\s*(\d+) events', (run/'console.log').read_text())
    output['position_module_perf_counts'] = [int(x) for x in counts]
    if len(counts) == 2:
        output['position_module_approx_hz'] = (int(counts[1])-int(counts[0]))/output['hover_seconds']
    output['limitations'] = ['No new velocity controller diagnostic exists in V00; paired measured state is a proxy, not proven consumed state.',
        'Publication timestamp distributions and perf counts do not prove full callback/update sequence coverage.',
        'RMSE uses recorded samples; no full-bandwidth TV/PSD or motor energy claim.',
        'Default random engines; three restarts are not three independent seeded draws.']
    output['accepted'] = bool(all(checks.values()))
    save(run/'v00_metrics.json', output)
    save(run/'ulog_parameters.json', log.initial_parameters)
    save(run/'ulog_topics.json', [dict(name=x.name, instance=x.multi_id, count=len(x.data['timestamp'])) for x in log.data_list])
    return output


def math_radians_20():
    return float(np.deg2rad(20))


if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('run',type=Path); args=p.parse_args()
    result=analyze(args.run,json.loads((CONFIG/'protocol.json').read_text()))
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['accepted'] else 1)
