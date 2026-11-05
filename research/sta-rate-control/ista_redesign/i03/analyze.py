#!/usr/bin/env python3
"""Read-only I03 ULog decode. Simulator truth is post-hoc diagnostics only."""
import hashlib
import json
from pathlib import Path
import numpy as np
from pyulog import ULog

from design import load_frozen


def vec(data, name):
    return np.column_stack([data[f'{name}[{i}]'] for i in range(3)]).astype(float)


def missing_fraction(sequence):
    sequence = np.asarray(sequence, dtype=np.int64)
    if len(sequence) < 2:
        return 1.0, 0
    missing = int(np.maximum(np.diff(sequence)-1, 0).sum())
    return missing/max(1, missing+len(sequence)), missing


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inherited_audit_adjudicated(run, m10, result):
    """Accept only the exact, reviewed M09 freeze-model mismatch; never hide another failure."""
    if m10.get('success') or not result.get('success'):
        return False
    if m10.get('error') != "ValueError('Protected nu/freeze is inconsistent')":
        return False
    path = run.parent/(run.name+'.adjudication.json')
    if not path.exists():
        return False
    review = json.loads(path.read_text())
    return bool(review.get('analysis_resolved_without_reflight') and
                review.get('flight_result_success') and
                review.get('new_analysis_sha256') == file_digest(run/'m10_analysis.json'))


def analyze(run):
    run = Path(run).resolve()
    frozen, _, _ = load_frozen()
    job = json.loads((run/'m10_job.json').read_text())
    result = json.loads((run/'result.json').read_text())
    m10 = json.loads((run/'m10_analysis.json').read_text())
    audit_adjudicated = inherited_audit_adjudicated(run, m10, result)
    out = {k: job[k] for k in ('algorithm', 'protection', 'mode', 'seed', 'frozen_head')}
    out.update(accepted=False, flight_success=bool(result.get('success')), m10_success=bool(m10.get('success')),
               inherited_m09_audit_adjudicated=audit_adjudicated,
               ulog_truth_usage='post-hoc only')
    try:
        logs = []
        for item in result['logs']:
            archive = Path(item['archive'])
            if file_digest(archive) != item['sha256']:
                raise ValueError('ULog fingerprint changed')
            log = ULog(str(archive))
            d = log.get_dataset('sta_rate_ctrl_status').data
            logs.append((int(np.count_nonzero(d['armed'])), log, d, item))
        _, log, d, item = max(logs, key=lambda row: row[0])
        takeoff = log.get_dataset('sta_takeoff_status').data
        truth = log.get_dataset('vehicle_local_position_groundtruth').data
        attitude = log.get_dataset('vehicle_attitude').data
        if log.msg_info_dict.get('ver_hw') != 'PX4_SITL':
            raise ValueError('Not a SITL log')
        if log.msg_info_dict.get('ver_sw') != job['frozen_head']:
            raise ValueError('Embedded firmware commit mismatch')
        for name, value in job['parameters'].items():
            if name not in log.initial_parameters or not np.isclose(log.initial_parameters[name], value, rtol=2e-6, atol=2e-6):
                raise ValueError('Logged parameter mismatch: '+name)
        t = d['timestamp_sample'].astype(np.int64)*1e-6
        armed = d['armed'].astype(bool)
        ai = np.flatnonzero(armed)
        if len(ai) < 2:
            raise ValueError('No armed controller interval')
        arm_time = float(t[ai[0]])
        gt = truth['timestamp'].astype(np.int64)*1e-6
        ref = (gt >= arm_time-1.0) & (gt < arm_time)
        if np.count_nonzero(ref) < 2:
            raise ValueError('No pre-arm truth reference')
        z0 = float(np.median(truth['z'][ref]))
        height = np.interp(t, gt, z0-truth['z'].astype(float))
        vz = np.interp(t, gt, truth['vz'].astype(float))
        lift_candidates = np.flatnonzero(armed & (height > frozen['analysis_windows']['truth_liftoff_height_m']))
        if not len(lift_candidates):
            raise ValueError('No truth +2 cm liftoff event')
        lift = int(lift_candidates[0]); lift_time = float(t[lift])
        q = np.column_stack([attitude[f'q[{i}]'] for i in range(4)]).astype(float)
        tilt_raw = np.degrees(np.arccos(np.clip(1-2*(q[:, 1]**2+q[:, 2]**2), -1, 1)))
        tilt = np.interp(t, attitude['timestamp'].astype(np.int64)*1e-6, tilt_raw)
        nu = vec(d, 'nu'); error = vec(d, 's'); limits = vec(d, 'limits')
        stationary = armed & (t < lift_time) & (np.abs(height) < frozen['analysis_windows']['stationary_height_m']) \
                     & (np.abs(vz) < frozen['analysis_windows']['stationary_vertical_speed_m_s'])
        early = armed & (t >= lift_time) & (t < lift_time+frozen['analysis_windows']['early_after_liftoff_s'])
        if np.count_nonzero(stationary) < 10 or np.count_nonzero(early) < 100:
            raise ValueError('Insufficient pre-liftoff or early-response samples')
        tt = takeoff['timestamp_sample'].astype(np.int64)*1e-6
        ta = takeoff['armed'].astype(bool)
        manager = job['protection'] == 'takeoff_nu_manager'
        active_tko = ta & (tt >= arm_time)
        release_idx = np.flatnonzero(active_tko & (takeoff['event'] == 4))
        release_time = float(tt[release_idx[0]]) if len(release_idx) else None
        pre_release = armed & (t < release_time) if release_time is not None else armed & (t <= lift_time)
        main_missing_fraction, main_missing = missing_fraction(d['publish_seq'][ai])
        ti = np.flatnonzero(active_tko)
        tko_missing_fraction, tko_missing = missing_fraction(takeoff['publish_seq'][ti])
        effective = takeoff['effective_enable'][ti].astype(bool)
        states = takeoff['state'][ti].astype(int)
        events = takeoff['event'][ti].astype(int)
        checks = dict(
            flight_complete=bool(result.get('success') and (m10.get('success') or audit_adjudicated)),
            mode_axes=bool(np.all(d['effective_mode'][ai] == job['mode']) and np.all(d['effective_axes'][ai] == 7)),
            no_fault_abort=bool(not np.any(d['fault'][ai]) and not np.any(d['abort_requested'][ai]) and not np.any(takeoff['abort'][ti])),
            tilt=bool(np.max(tilt[armed]) <= frozen['per_run_limits']['tilt_deg']),
            ulog_dropouts=bool(len(log.dropouts) <= frozen['per_run_limits']['ulog_dropouts']),
            main_sequence=bool(main_missing_fraction <= frozen['per_run_limits']['diagnostic_missing_fraction']),
            takeoff_sequence=bool(tko_missing_fraction <= frozen['per_run_limits']['diagnostic_missing_fraction']))
        if manager:
            checks.update(manager_effective=bool(np.all(effective)), manager_waiting=bool(np.any(states == 2)),
                          manager_one_release=bool(len(release_idx) == 1), manager_no_fault=bool(not np.any(states == 7)),
                          manager_release_window=bool(release_time is not None and
                            lift_time-frozen['per_run_limits']['manager_release_early_tolerance_s'] <= release_time <=
                            lift_time+frozen['per_run_limits']['manager_release_late_s']),
                          manager_pre_release_nu=bool(np.max(np.abs(nu[pre_release])) <=
                            frozen['per_run_limits']['pre_release_nu_abs_rad_s2']),
                          manager_no_airborne_refreeze=bool(release_time is not None and
                            not np.any(takeoff['freeze'][active_tko & (tt > release_time+.05) & (tt < lift_time+20)])))
        else:
            checks.update(manager_disabled=bool(not np.any(effective) and np.all(states == 0) and not np.any(events)))
        out.update(ulog=str(item['archive']), ulog_sha256=item['sha256'], checks=checks,
                   truth_liftoff_s=lift_time, manager_release_s=release_time,
                   manager_release_after_truth_liftoff_s=None if release_time is None else release_time-lift_time,
                   stationary_samples=int(np.count_nonzero(stationary)),
                   stationary_nu_max_abs=np.max(np.abs(nu[stationary]), axis=0).tolist(),
                   liftoff_nu=nu[lift].tolist(), liftoff_nu_l2=float(np.linalg.norm(nu[lift])),
                   prerelease_nu_max_abs=np.max(np.abs(nu[pre_release]), axis=0).tolist(),
                   early_rate_rmse=np.sqrt(np.mean(error[early]**2, axis=0)).tolist(),
                   peak_tilt_deg=float(np.max(tilt[armed])), early_peak_tilt_deg=float(np.max(tilt[early])),
                   height_min_max_m=[float(np.min(height[armed])), float(np.max(height[armed]))],
                   protected_fraction=np.mean(limits[armed] != 0, axis=0).tolist(),
                   mixer_saturation_fraction=float(np.mean((d['sat_bits'][ai].astype(int) & ~1) != 0)),
                   sequence=dict(main_missing=main_missing, main_missing_fraction=main_missing_fraction,
                                 takeoff_missing=tko_missing, takeoff_missing_fraction=tko_missing_fraction),
                   ulog_dropouts=len(log.dropouts), ulog_dropout_ms=sum(row.duration for row in log.dropouts),
                   manager_states=sorted(set(states.tolist())), manager_events=sorted(set(events.tolist())))
        out['accepted'] = bool(all(checks.values()))
    except Exception as exc:
        out['error'] = repr(exc)
    (run/'i03_analysis.json').write_text(json.dumps(out, indent=2)+'\n')
    return out


def summarize(rows):
    frozen, _, _ = load_frozen(); paired = []
    table = {(r['algorithm'], r['seed'], r['protection']): r for r in rows}
    for algorithm in frozen['source_algorithms']:
        for seed in (6101, 6102, 6103):
            old = table[(algorithm, seed, 'established')]
            new = table[(algorithm, seed, 'takeoff_nu_manager')]
            old_nu = old.get('liftoff_nu_l2', float('nan')); new_nu = new.get('liftoff_nu_l2', float('nan'))
            paired.append(dict(algorithm=algorithm, seed=seed, old_nu=old_nu, new_nu=new_nu,
                               reduction=1-new_nu/max(old_nu, 1e-12),
                               rmse_ratio=(np.asarray(new.get('early_rate_rmse', [np.nan]*3))/
                                           np.maximum(np.asarray(old.get('early_rate_rmse', [np.nan]*3)), 1e-12)).tolist(),
                               tilt_increase_deg=new.get('early_peak_tilt_deg', np.nan)-old.get('early_peak_tilt_deg', np.nan)))
    limits = frozen['paired_selection_limits']
    combined = float(np.nanmedian([p['reduction'] for p in paired]))
    algorithm_summary = {}
    for algorithm in frozen['source_algorithms']:
        subset = [p for p in paired if p['algorithm'] == algorithm]
        algorithm_summary[algorithm] = dict(
            liftoff_nu_reduction_median=float(np.nanmedian([p['reduction'] for p in subset])),
            early_rmse_ratio_median_axis=np.nanmedian(np.asarray([p['rmse_ratio'] for p in subset]), axis=0).tolist(),
            peak_tilt_increase_median_deg=float(np.nanmedian([p['tilt_increase_deg'] for p in subset])))
    all_accepted = all(r.get('accepted', False) for r in rows)
    manager_correct = all(all(v for k, v in r.get('checks', {}).items() if k.startswith('manager_'))
                          for r in rows if r['protection'] == 'takeoff_nu_manager')
    mechanism = combined >= limits['combined_median_liftoff_nu_reduction'] and all(
        v['liftoff_nu_reduction_median'] >= limits['per_algorithm_median_liftoff_nu_reduction']
        for v in algorithm_summary.values())
    no_degradation = all(max(v['early_rmse_ratio_median_axis']) <= limits['early_rate_rmse_ratio'] and
                         v['peak_tilt_increase_median_deg'] <= limits['peak_tilt_increase_deg']
                         for v in algorithm_summary.values())
    choose_new = all_accepted and manager_correct and mechanism and no_degradation
    configurations = {}
    for algorithm in frozen['source_algorithms']:
        for protection in frozen['protection_variants']:
            subset = [r for r in rows if r['algorithm'] == algorithm and r['protection'] == protection]
            configurations[algorithm+'_'+protection] = dict(planned=3, attempted=len(subset), accepted=sum(bool(r.get('accepted')) for r in subset))
    both_unsafe = any(configurations[a+'_established']['accepted'] == 0 and
                      configurations[a+'_takeoff_nu_manager']['accepted'] == 0 for a in frozen['source_algorithms'])
    return dict(planned=12, attempted=len(rows), accepted=sum(bool(r.get('accepted')) for r in rows),
                configurations=configurations, paired=paired, combined_liftoff_nu_reduction_median=combined,
                algorithms=algorithm_summary, all_accepted=all_accepted, manager_correct=manager_correct,
                mechanism=mechanism, no_degradation=no_degradation,
                selected_common_protection='takeoff_nu_manager' if choose_new else 'established',
                stop_future_flight=both_unsafe,
                conclusion_scope='Iris SITL three paired development seeds; not hardware or statistical significance')
