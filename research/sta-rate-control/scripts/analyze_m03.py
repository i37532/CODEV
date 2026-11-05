#!/usr/bin/env python3
"""Validate real M03 ULog, float32 PID output and publisher sequence losses."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from pyulog import ULog
from analyze_m00 import analyze, plain


def sequence_stats(seq, times):
    seq = np.asarray(seq, dtype=np.uint64)
    times = np.asarray(times, dtype=np.float64)
    if len(seq) < 2:
        raise ValueError('Insufficient sequence samples')
    delta = (seq[1:] - seq[:-1]) & np.uint64(0xffffffff)
    if np.any(delta == 0) or np.any(delta > 1000000) or np.any(np.diff(times) <= 0):
        raise ValueError('Duplicate/backward sequence or time')
    span = (times[-1] - times[0]) * 1e-6
    return dict(count=len(seq), missing=int(np.sum(delta - 1)), logged_hz=(len(seq)-1)/span,
                producer_hz=int(np.sum(delta))/span, max_interval_s=float(np.max(np.diff(times))*1e-6))


def vector(data, name):
    return np.column_stack([data[f'{name}[{i}]'] for i in range(3)]).astype(np.float32)


def pid_output(d):
    # Independent reconstruction, original float operation order, no reassociation.
    return ((vector(d, 'pid_p') * (vector(d, 'rate_sp') - vector(d, 'rate'))
             + vector(d, 'pid_integral_before')) - vector(d, 'pid_d') * vector(d, 'angular_accel')) \
           + vector(d, 'pid_ff') * vector(d, 'rate_sp')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main(run):
    result = json.loads((run/'result.json').read_text())
    settings = json.loads((run/'m03_logging.json').read_text())
    require(settings['research_profile'] == settings['original_profile'] | 16, 'Profile bits not preserved')
    candidates = []
    for index, item in enumerate(result['logs']):
        path = Path(item['archive'])
        require(hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256'], 'ULog fingerprint mismatch')
        log = ULog(str(path))
        if int(log.initial_parameters.get('SDLOG_PROFILE', -1)) == settings['research_profile']:
            candidates.append((index, log))
    require(len(candidates) == 1, 'Require exactly one restarted high-rate research log')
    index, log = candidates[0]
    analyze(run, log_index=index)
    d = log.get_dataset('sta_rate_ctrl_status').data
    events = {r['name']: r['timestamp_us'] for r in result['events']}
    start, end = events['hover_start'], events['hover_end']
    m = (d['timestamp_sample'] >= start) & (d['timestamp_sample'] <= end)
    require(np.any(m), 'Missing hover data')
    for key in ('effective_mode', 'effective_axes', 'fault', 'abort_requested', 'experiment_updated'):
        require(np.all(d[key] == 0), 'Unexpected ' + key)
    for key in ('measurement_valid', 'output_valid', 'updated'):
        require(np.all(d[key][m]), 'Invalid hover ' + key)
    require(np.all(d['timing_status'][m] == 0), 'Bad hover raw timing')
    for name in ('a_raw', 'xi', 'virtual_state'):
        require(np.all(np.isnan(vector(d, name))), name + ' must be NaN/not applicable for PID')
    require(np.all(vector(d, 'nu') == 0), 'Unexpected experiment state')
    for i in range(3):
        require(np.all(d[f'ista_branch[{i}]'] == 255), 'Wrong ISTA branch')
    updates = d['updated'].astype(bool)
    expected, actual = pid_output(d), vector(d, 'c_raw')
    require(np.all(np.isfinite(actual[updates])), 'Nonfinite PID raw output')
    mismatches = int(np.count_nonzero(expected[updates].view(np.uint32) != actual[updates].view(np.uint32)))
    require(mismatches == 0, f'PID float-bit mismatch: {mismatches}')
    applied = vector(d, 'c_applied')
    scaled = actual * d['battery_scale'][:, None]
    require(np.array_equal(scaled[updates].view(np.uint32), applied[updates].view(np.uint32)), 'Battery scaling mismatch')
    act = log.get_dataset('actuator_controls_0').data
    common, di, ai = np.intersect1d(d['timestamp_sample'][updates], act['timestamp_sample'], return_indices=True)
    controls = np.column_stack([act[f'control[{i}]'] for i in range(3)])
    require(len(common) > 0 and np.array_equal(applied[updates][di].view(np.uint32), controls[ai].view(np.uint32)),
            'Published actuator output mismatch')
    motor = log.get_dataset('multirotor_motor_limits').data
    mm = (motor['timestamp'] >= start) & (motor['timestamp'] <= end)
    summaries = dict(status_publications=sequence_stats(d['publish_seq'][m], d['timestamp_sample'][m]),
                     controller_updates=sequence_stats(d['update_seq'][m], d['timestamp_sample'][m]),
                     motor_publications=sequence_stats(motor['update_seq'][mm], motor['timestamp'][mm]))
    # Status embeds the feedback actually read by PID. Count producer updates
    # after removing legitimate holds; keep raw-topic losses separate.
    consumed = d['motor_update_seq'][m]
    unique = np.r_[True, consumed[1:] != consumed[:-1]]
    summaries['motor_consumed_by_pid'] = sequence_stats(consumed[unique], d['motor_timestamp'][m][unique])
    common_motor, si, mi = np.intersect1d(d['motor_update_seq'][m], motor['update_seq'], return_indices=True)
    require(len(common_motor) > 0 and np.array_equal(d['motor_saturation'][m][si], motor['saturation_status'][mi]),
            'Consumed mixer status does not match producer')
    pair = json.loads((run/'armed_config_check.json').read_text())
    disarmed = json.loads((run/'disarmed_config_check.json').read_text())
    old = pair['before']['config_seq']
    require(np.any(d['config_pending'][m]) and np.all(d['config_seq'][m] == old), 'Armed config changed/not pending')
    require(disarmed['config_seq'] > old and not disarmed['config_pending'], 'No disarm apply')
    baseline = json.loads((Path(__file__).resolve().parents[1]/'baseline/pid_initial_parameters.json').read_text())
    differences = {k: [baseline.get(k), log.initial_parameters.get(k)]
                   for k in baseline.keys() | log.initial_parameters.keys() if baseline.get(k) != log.initial_parameters.get(k)}
    allowed = {'MC_RTC_MODE', 'MC_STA_AXES', 'SDLOG_PROFILE', 'COM_FLIGHT_UUID', 'LND_FLIGHT_T_LO', 'LND_FLIGHT_T_HI'}
    late = json.loads((Path(__file__).resolve().parents[1]/'m03/late_logged_baseline.json').read_text())['values']
    require(all(k in allowed or k.startswith('MC_STA_') or
                (k not in baseline and k in late and log.initial_parameters[k] == late[k])
                for k in differences), f'Baseline drift: {differences}')
    allowed_changes = {'MC_STA_L1_R', 'COM_FLIGHT_UUID', 'LND_FLIGHT_T_LO', 'LND_FLIGHT_T_HI'}
    # Parameter-update notification of the preflight logger profile can arrive
    # after the restarted logger wrote its initial snapshot. Require exact value
    # and pre-takeoff time; do not permit an arbitrary runtime profile change.
    require(all(c[1] in allowed_changes or (c[1] == 'SDLOG_PROFILE' and
                c[2] == settings['research_profile'] and c[0] < events['takeoff_command'])
                for c in log.changed_parameters), f'Unexpected runtime parameters: {log.changed_parameters}')
    tv_ready = all(s['missing'] == 0 for s in summaries.values()) and not log.dropouts
    summary = dict(success=True, ulog_index=index, ulog_sha256=result['logs'][index]['sha256'],
                   profile_original=settings['original_profile'], profile_research=settings['research_profile'],
                   pid_compared_samples=int(np.count_nonzero(updates)), pid_bit_mismatches=mismatches,
                   actuator_matched_samples=len(common), mixer_matched_sequences=len(common_motor), sequences=summaries,
                   motor_valid_ratio=float(np.mean(d['motor_valid'][m])),
                   raw_dt_min=float(np.min(d['raw_dt'][m])), raw_dt_max=float(np.max(d['raw_dt'][m])),
                   logger_dropout_count=len(log.dropouts), suitable_for_full_rate_tv=tv_ready,
                   qualification='No observed loss in hover window only' if tv_ready else 'NOT suitable for full-rate TV/spectrum',
                   parameter_differences_vs_M00=differences, runtime_parameter_changes=log.changed_parameters)
    (run/'m03_analysis.json').write_text(json.dumps(summary, indent=2, default=plain)+'\n')
    print(json.dumps(summary, indent=2, default=plain))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('run', type=Path)
    main(parser.parse_args().run)
