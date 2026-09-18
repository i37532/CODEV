#!/usr/bin/env python3
"""Decode one I04 ULog and summarize the frozen eight-run comparison."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
from pyulog import ULog

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]/'scripts'))

from analyze_m00 import analyze as analyze_base, plain
from analyze_m03 import pid_output, require, sequence_stats, vector
from m08_ista_reference import ideal as original_ista_reference

from design import HERE


def proper_reference(s, nu, h, l1, l2, g, iterations=100):
    """Independent binary64 bisection of the monotone implicit inclusion."""
    q = h*h*l2
    if abs(s) <= q:
        z, xi = 0.0, s/q
    else:
        sign = math.copysign(1.0, s); delta = abs(s)-q; lo, hi = 0.0, delta
        for _ in range(iterations):
            mid = (lo+hi)*.5
            if mid+h*l1*math.sqrt(mid) > delta: hi = mid
            else: lo = mid
        z, xi = sign*(lo+hi)*.5, sign
    next_nu = nu-h*l2*xi
    a = next_nu+(z-s)/h
    return dict(z=z, xi=xi, nu=next_nu, a=a, c=a/g,
                branch=2 if z == 0.0 else (1 if z > 0.0 else 3))


def research_log(run, result):
    settings = json.loads((run/'m03_logging.json').read_text())
    candidates = []
    for index, item in enumerate(result.get('logs', [])):
        path = Path(item['archive'])
        require(hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256'], 'ULog hash mismatch')
        log = ULog(str(path))
        if log.initial_parameters.get('SDLOG_PROFILE') == settings['research_profile']:
            candidates.append((index, path, log))
    require(len(candidates) == 1, 'Require exactly one high-rate research ULog')
    return candidates[0]


def analyze(run):
    result = json.loads((run/'result.json').read_text())
    job = json.loads((run/'m10_job.json').read_text())
    out = dict(success=False, flight_success=bool(result.get('success')), mode=job['mode'],
               algorithm=job['algorithm'], seed=job['seed'], source_head=result.get('source_head'),
               binary_sha256=result.get('binary_sha256'))
    try:
        require(result['success'], 'Flight scenario failed: '+str(result.get('error', result.get('cleanup_error'))))
        index, path, log = research_log(run, result)
        analyze_base(run, log_index=index)
        metrics = json.loads((run/'metrics.json').read_text())
        config = json.loads((run/'m04_config.json').read_text())
        protocol = json.loads((run/'m04_protocol.json').read_text())
        limits = protocol['limits']
        mode = int(job['mode']); axes = int(config['MC_STA_AXES'])
        require(mode in (0, 1, 2, 3), 'Unexpected mode')
        require(axes == (0 if mode == 0 else 1), 'I04 is PID or roll-only')
        require(config['MC_STA_TKO_MGT'] == 0 and config['MC_RTC_DIV'] == 1,
                'Protection baseline or divisor changed')
        require(log.msg_info_dict.get('ver_hw') == 'PX4_SITL', 'Not SITL')
        require(log.msg_info_dict.get('ver_sw') == job['frozen_head'], 'Embedded source differs from frozen commit')
        for name, value in config.items():
            require(name in log.initial_parameters and np.isclose(log.initial_parameters[name], value, rtol=2e-6, atol=2e-6),
                    'Logged parameter mismatch: '+name)

        d = log.get_dataset('sta_rate_ctrl_status').data
        t = d['timestamp_sample'].astype(np.int64)
        armed = d['armed'].astype(bool)
        start, end = metrics['hover_start_us'], metrics['hover_end_us']
        hover = (t >= start) & (t <= end)
        tracking = hover & (d['research_elapsed'] >= 0) & (d['research_elapsed'] <= 24)
        require(np.count_nonzero(hover) > 10000 and np.count_nonzero(tracking) > 5000, 'Insufficient windows')
        for field, expected in [('requested_mode', mode), ('effective_mode', mode),
                                ('requested_axes', axes), ('effective_axes', axes),
                                ('request_status', 0), ('pending', 0), ('fault', 0),
                                ('abort_requested', 0), ('config_pending', 0)]:
            require(np.all(d[field] == expected), 'Unexpected '+field)
        for field in ('measurement_valid', 'output_valid', 'updated'):
            require(np.all(d[field][armed]), 'Invalid armed '+field)
        require(np.all(d['timing_status'][armed] == 0), 'Timing fault')
        require(np.all(d['div_eff'] == 1) and np.all(d['div_ok']), 'Divisor mismatch')
        require(np.all(np.diff(t) > 0), 'Nonmonotonic diagnostic sample time')
        seq_status = sequence_stats(d['publish_seq'][hover], t[hover])
        seq_update = sequence_stats(d['update_seq'][hover], t[hover])
        require(seq_status['missing'] == 0 and seq_update['missing'] == 0, 'Diagnostic sequence missing')
        require(len(log.dropouts) == limits['ulog_dropouts'], 'ULog dropout')

        rate = vector(d, 'rate'); error = vector(d, 's'); command = vector(d, 'c_applied')
        require(np.all(np.isfinite(rate[armed])) and np.all(np.isfinite(command[armed])), 'Nonfinite flight data')
        require(np.max(np.abs(rate[armed])) <= limits['rate_rad_s'], 'Rate boundary')
        require(np.max(np.abs(command[armed, 0])) <= limits['roll_command_abs'] + 1e-6, 'Roll command boundary')
        require(np.max(np.abs(vector(d, 'nu')[armed, 0])) <= limits['nu_abs_rad_s2'] + 1e-6, 'Nu boundary')
        require(metrics['tilt_deg']['max_abs'] <= limits['tilt_deg'], 'Tilt boundary')
        require(metrics['position_error_m']['max_abs'][2] <= limits['height_error_m'], 'Height boundary')

        expected_pid = pid_output(d)
        updated = d['updated'].astype(bool)
        pid_axes = (0, 1, 2) if mode == 0 else (1, 2)
        for axis in pid_axes:
            require(np.array_equal(vector(d, 'c_raw')[updated, axis].copy().view(np.uint32),
                                   expected_pid[updated, axis].copy().view(np.uint32)),
                    'PID bit mismatch axis '+str(axis))
        require(np.all(d['pid_updated'][armed]), 'Mixed-axis I04 must keep PID pitch/yaw state current')
        require(np.all(np.diff(d['pid_update_seq'].astype(np.int64)) == d['pid_updated'][1:]), 'PID sequence mismatch')

        active = hover & d['experiment_updated'].astype(bool)
        if mode:
            require(np.all(d['experiment_updated'][hover]), 'Experiment frozen in hover')
            require(np.all(vector(d, 'nu')[:, 1:] == 0), 'Unselected state changed')
            require(np.all(np.isnan(vector(d, 'a_raw')[:, 1:])), 'Unselected ideal output populated')
            old = vector(d, 'nu_before')[:, 0]
            candidate = vector(d, 'nu_candidate')[:, 0]
            ideal_a = vector(d, 'a_raw')[:, 0]
            g = vector(d, 'g')[:, 0]
            require(np.allclose(vector(d, 'c_raw')[active, 0], (ideal_a/g)[active], rtol=1e-6, atol=1e-7),
                    'Ideal command mapping')
            if mode == 3:
                indices = np.flatnonzero(active)
                refs = [proper_reference(float(error[i, 0]), float(old[i]), float(d['dt'][i]),
                                         float(vector(d, 'lambda1')[i, 0]), float(vector(d, 'lambda2')[i, 0]),
                                         float(g[i])) for i in indices]
                for field, logged in [('a', ideal_a), ('nu', candidate),
                                      ('z', vector(d, 'virtual_state')[:, 0]), ('xi', vector(d, 'xi')[:, 0])]:
                    expected = np.array([r[field] for r in refs])
                    np.testing.assert_allclose(logged[indices], expected, rtol=2e-6, atol=2e-7)
                np.testing.assert_array_equal(d['ista_branch[0]'][indices], np.array([r['branch'] for r in refs]))
                factor = 2.0
            elif mode == 2:
                ref = original_ista_reference(error[active, 0], old[active], d['dt'][active],
                                              vector(d, 'lambda1')[active, 0], vector(d, 'lambda2')[active, 0], g[active])
                np.testing.assert_allclose(ideal_a[active], ref['a'], rtol=1e-6, atol=1e-7)
                np.testing.assert_allclose(candidate[active], ref['nu'], rtol=1e-6, atol=1e-7)
                factor = 1.0
            else:
                require(np.all(d['ista_branch[0]'][active] == 255), 'ESTA mislabeled implicit')
                factor = 0.0
            protected = ideal_a + factor * (vector(d, 'nu')[:, 0] - candidate)
            np.testing.assert_allclose(vector(d, 'a_protected')[active, 0], protected[active], rtol=1e-6, atol=1e-7)
            expected_roll = np.clip(protected/g, -.15, .15) * d['battery_scale']
            np.testing.assert_allclose(command[active, 0], expected_roll[active], rtol=1e-6, atol=1e-7)
            contiguous = (np.diff(d['update_seq'].astype(np.int64)) == 1) & armed[1:] & armed[:-1:] & (d['reset_reason'][1:] == 0)
            np.testing.assert_array_equal(old[1:][contiguous], vector(d, 'nu')[:-1, 0][contiguous])
        else:
            require(np.all(~d['experiment_updated'].astype(bool)), 'PID updated experiment')

        act = log.get_dataset('actuator_controls_0').data
        common, di, ai = np.intersect1d(t[updated], act['timestamp_sample'], return_indices=True)
        require(len(common) > 10000, 'Insufficient actuator overlap')
        actual = np.column_stack([act[f'control[{i}]'] for i in range(3)])
        require(np.array_equal(command[updated][di].copy().view(np.uint32), actual[ai].copy().view(np.uint32)),
                'Actuator output mismatch')
        pulse = d['research_roll_addition'][tracking]
        require(np.max(pulse) > .119 and np.min(pulse) < -.119, 'Incomplete signed roll excitation')
        require(abs(float(np.trapz(pulse, d['research_elapsed'][tracking]))) < .002, 'Excitation net angle')
        require(np.all(d['research_pitch_addition'][tracking] == 0) and np.all(d['research_yaw_addition'][tracking] == 0),
                'Non-roll excitation')

        rates_topics = [x for x in log.data_list if x.name == 'vehicle_rates_setpoint']
        require({x.multi_id for x in rates_topics} == {0}, 'Multiple logged rates-setpoint instances')
        out.update(success=True, analysis_success=True, ulog=str(path),
                   ulog_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), dropouts=len(log.dropouts),
                   hover_rmse=np.sqrt(np.mean(error[hover].astype(float)**2, axis=0)).tolist(),
                   tracking_rmse=np.sqrt(np.mean(error[tracking].astype(float)**2, axis=0)).tolist(),
                   max_abs_command=np.max(np.abs(command[armed]), axis=0).tolist(),
                   max_abs_nu=np.max(np.abs(vector(d, 'nu')[armed]), axis=0).tolist(),
                   max_tilt_deg=metrics['tilt_deg']['max_abs'],
                   max_height_error_m=metrics['position_error_m']['max_abs'][2],
                   limit_fraction={str(bit): float(np.mean((d['limits[0]'][hover] & bit) != 0)) for bit in (1, 2, 4, 8)},
                   saturation_fraction=float(np.mean((d['motor_saturation'][hover].astype(np.uint16) & 0x1f8) != 0)),
                   sequences=dict(status=seq_status, updates=seq_update), actuator_matched_samples=len(common),
                   setpoint_instances=[x.multi_id for x in rates_topics])
    except Exception as exc:
        out.update(success=False, analysis_success=False, error=repr(exc),
                   failure_class='flight' if not result.get('success') else 'analysis_or_data_quality')
        if any(word in str(exc) for word in ('boundary', 'Boundary', 'fault', 'abort')):
            out['failure_class'] = 'control_boundary'
    (run/'i04_analysis.json').write_text(json.dumps(out, indent=2, default=plain)+'\n')
    print(json.dumps(out, indent=2, default=plain))
    return out


def summarize(rows):
    frozen = json.loads((HERE/'FROZEN.json').read_text())
    limits = frozen['flight_protocol']['limits']
    violations = []
    if len(rows) != len(frozen['ordered_jobs']): violations.append('attempt_count')
    for row in rows:
        if not row.get('success'): violations.append(row.get('algorithm', 'unknown')+':'+str(row.get('seed')))
    esta = [r for r in rows if r.get('algorithm') == 'esta' and r.get('success')]
    proper = [r for r in rows if r.get('algorithm') == 'proper_ista' and r.get('success')]
    if len(esta) != 3: violations.append('esta_count')
    if len(proper) != 3: violations.append('proper_count')
    ratios = []
    noncommand = []
    if len(esta) == len(proper) == 3:
        e_hover = np.median([r['hover_rmse'] for r in esta], axis=0)
        e_track = np.median([r['tracking_rmse'] for r in esta], axis=0)
        for row in proper:
            ratio = dict(seed=row['seed'], hover_roll=row['hover_rmse'][0]/e_hover[0],
                         tracking_roll=row['tracking_rmse'][0]/e_track[0])
            ratios.append(ratio)
            if ratio['hover_roll'] > limits['rmse_ratio_max']: violations.append('proper_hover_roll:'+str(row['seed']))
            if ratio['tracking_roll'] > limits['rmse_ratio_max']: violations.append('proper_tracking_roll:'+str(row['seed']))
            for window, baseline in [('hover_rmse', e_hover), ('tracking_rmse', e_track)]:
                for axis in (1, 2):
                    threshold = max(limits['rmse_ratio_max']*baseline[axis],
                                    baseline[axis]+limits['noncommand_rmse_absolute_margin_rad_s'])
                    value = row[window][axis]
                    noncommand.append(dict(seed=row['seed'], window=window, axis=axis,
                                           value=value, threshold=threshold))
                    if value > threshold: violations.append('proper_noncommand:'+str(row['seed'])+':'+window+':'+str(axis))
    return dict(success=not violations, planned=len(frozen['ordered_jobs']), attempted=len(rows),
                accepted=sum(bool(r.get('success')) for r in rows), violations=violations,
                proper_to_esta_ratios=ratios, noncommand_checks=noncommand, rows=rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('run', type=Path)
    args = parser.parse_args()
    raise SystemExit(0 if analyze(args.run.resolve())['success'] else 1)
