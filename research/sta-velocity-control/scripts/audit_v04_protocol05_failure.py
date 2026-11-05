#!/usr/bin/env python3
"""Read-only series04 diagnosis. Does not repair, fly, or reaccept a run."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from pyulog import ULog
from v04_heading_stream import replay
from v04_task04 import REFERENCE, current_triplet


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run, out = args.run.resolve(), args.output.resolve()
    if out == run or run in out.parents:
        raise ValueError('Use a new separate evidence directory')
    out.mkdir(parents=True, exist_ok=False)
    result = json.loads((run/'result.json').read_text())
    ref = json.loads((run/'height_reference.json').read_text())
    frozen = json.loads((run/'task_yaw.json').read_text())
    start = next(e['timestamp_us'] for e in result['events'] if e['name'] == 'takeoff_command')
    logs, decoded = [], []
    for item in result['logs']:
        path = Path(item['archive'])
        if sha(path) != item['sha256']:
            raise ValueError('Original ULog fingerprint mismatch')
        u = ULog(str(path))
        logs.append(dict(**item, dropouts=len(u.dropouts), corruption=bool(u.file_corruption)))
        decoded.append((item['bytes'], u))
    u = max(decoded, key=lambda x: x[0])[1]
    evidence = dict(accepted=False, source_head=result['source_head'], original_error=result['error'],
                    events=result['events'], logs=logs, diagnostic_checks=[])

    def check(name, passed):
        evidence['diagnostic_checks'].append(dict(name=name, passed=bool(passed)))

    try:
        current_triplet((run/'triplet_before.txt').read_text())
    except ValueError as exc:
        evidence['reproduced_exception'] = str(exc)
    else:
        evidence['reproduced_exception'] = None
    check('archived_cli_reproduces_original_rejection', evidence['reproduced_exception'] == 'Invalid navigator target')
    triplet = u.get_dataset('position_setpoint_triplet').data
    status = u.get_dataset('vehicle_status').data
    ti = len(triplet['timestamp'])-1
    tt = int(triplet['timestamp'][ti])
    si = np.searchsorted(status['timestamp'], tt, side='right')-1
    target = {key: float(triplet['current.'+key][ti]) for key in ('valid', 'type', 'lat', 'lon', 'alt', 'yaw_valid')}
    evidence['final_navigator_target'] = dict(timestamp=tt, nav_state=int(status['nav_state'][si]), current=target)
    check('raw_ulog_confirms_invalid_posctl_triplet', status['nav_state'][si] == 2
          and target['valid'] == 0 and target['type'] == 5 and np.isnan(target['lat']) and np.isnan(target['lon']))
    trajectory = u.get_dataset('trajectory_setpoint').data
    tm = trajectory['timestamp'] >= tt
    evidence['posctl_trajectory'] = dict(samples=int(tm.sum()),
        finite_fields={k: bool(np.all(np.isfinite(trajectory[k][tm]))) for k in ('x', 'y', 'z', 'yaw')},
        final={k: float(trajectory[k][-1]) for k in ('timestamp', 'x', 'y', 'z', 'vz', 'yaw')},
        z_velocity_fallback_samples=int(np.count_nonzero(~np.isfinite(trajectory['z'][tm]) & np.isfinite(trajectory['vz'][tm]))),
        z_or_vz_valid=bool(np.all(np.isfinite(trajectory['z'][tm]) | np.isfinite(trajectory['vz'][tm]))))
    # Manual-position braking may use a finite vertical velocity and NaN Z position.
    # This is a diagnostic of existing target semantics, not a relaxed flight gate.
    check('posctl_has_separate_legal_local_target', tm.sum() > 0
          and all(evidence['posctl_trajectory']['finite_fields'][k] for k in ('x', 'y', 'yaw'))
          and evidence['posctl_trajectory']['z_or_vz_valid'])
    sm = status['timestamp'] >= start
    changed = np.flatnonzero(np.r_[True, np.diff(status['nav_state'].astype(int)) != 0])
    evidence['nav_transitions'] = [dict(timestamp=int(status['timestamp'][i]), nav_state=int(status['nav_state'][i]))
                                   for i in changed if status['timestamp'][i] >= start]
    land = u.get_dataset('vehicle_land_detected').data
    lm = land['timestamp'] >= start
    check('actual_liftoff_detected', np.any(status['takeoff_time'][sm] > 0) and np.any(land['landed'][lm] == 0))
    evidence['first_takeoff_time'] = int(np.min(status['takeoff_time'][sm & (status['takeoff_time'] > 0)]))
    evidence['heading_replay'] = replay(u, ref, frozen=frozen, allow_pending=True)
    check('heading_alignment_and_quiet_gate_completed', evidence['heading_replay']['confirmed'] and evidence['heading_replay']['ready'])
    pos = u.get_dataset('vehicle_local_position').data
    pm = pos['timestamp'] >= start
    evidence['reference_unique'] = {k: np.unique(pos[k][pm]).tolist() for k in REFERENCE}
    check('raw_origin_and_pv_counters_unchanged', all(np.all(pos[k][pm] == ref['position'][k]) for k in REFERENCE))
    evidence['height_range_m'] = [float(np.min(ref['position']['z']-pos['z'][pm])),
                                  float(np.max(ref['position']['z']-pos['z'][pm]))]
    evidence['last_position_timestamp'] = int(pos['timestamp'][-1])
    cmd = u.get_dataset('vehicle_command').data
    evidence['reposition_commands_after_takeoff'] = int(np.count_nonzero((cmd['timestamp'] >= start) & (cmd['command'] == 192)))
    check('no_reposition_sent', evidence['reposition_commands_after_takeoff'] == 0 and not (run/'reposition_command.json').exists())
    check('no_complete_performance_or_landing_window', not any(e['name'] in ('hover_start', 'land_command', 'landed_disarmed') for e in result['events']))
    evidence['topics'] = {}
    for name in ('sta_velocity_ctrl_status', 'sta_rate_ctrl_status'):
        d = u.get_dataset(name).data
        m = d['timestamp'] >= start
        ts = d['timestamp'][m].astype(np.int64)
        item = dict(samples=int(m.sum()), max_gap_us=int(np.max(np.diff(ts))))
        for key in ('requested_mode', 'effective_mode', 'effective_axes', 'inner_mode', 'inner_axes', 'inner_divisor',
                    'inner_valid', 'div_eff', 'first_fail', 'retry_result', 'fault', 'sta_fault', 'timing',
                    'failsafe', 'pid_calls', 'valid', 'excitation_fault', 'excitation', 'excitation_time'):
            if key in d:
                item[key] = np.unique(d[key][m]).tolist()
        for key in ('publish_seq', 'update_seq'):
            if key in d:
                item[key+'_nonunit_deltas'] = int(np.count_nonzero(np.diff(d[key][m].astype(np.int64)) != 1))
        evidence['topics'][name] = item
    velocity = evidence['topics']['sta_velocity_ctrl_status']
    check('recorded_pid_controls_no_first_update_or_latched_fault', all(velocity[k] == [0] for k in
          ('effective_mode', 'effective_axes', 'inner_mode', 'inner_axes', 'first_fail', 'retry_result', 'fault', 'sta_fault', 'timing', 'failsafe', 'excitation_fault'))
          and velocity['inner_divisor'] == [1] and velocity['pid_calls'] == [1])
    check('raw_logs_have_no_reported_dropout_or_corruption', all(not p['dropouts'] and not p['corruption'] for p in logs))
    live = [json.loads(line) for line in (run/'heading_live.jsonl').read_text().splitlines()]
    evidence['live_transport'] = dict(observations=len(live), min_age_us=min(x['age_us'] for x in live),
                                    max_age_us=max(x['age_us'] for x in live))
    evidence['interpretation'] = ('POSCTL intentionally clears the navigator triplet while its local trajectory has finite XY/yaw and legal mixed Z/vz targets. '
        'The runner requires POSCTL, then wrongly requires a valid navigator triplet before the height command. '
        'The altitude-only NaN XY command copies curr->current.lat/lon in the pinned navigator; skipping this gate would not fix the target contract. '
        'No runner/controller repair, protocol revision or new flight is performed; original acceptance remains false.')
    evidence['diagnostic_passed'] = all(c['passed'] for c in evidence['diagnostic_checks'])
    files = sorted(p for p in run.parent.rglob('*') if p.is_file() and not p.is_symlink())
    (out/'original_artifacts.sha256').write_text(''.join(f'{sha(p)}  {p}\n' for p in files))
    evidence['original_artifact_count'] = len(files)
    (out/'diagnosis.json').write_text(json.dumps(evidence, indent=2)+'\n')
    print(json.dumps(evidence, indent=2))
    return 0 if evidence['diagnostic_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
