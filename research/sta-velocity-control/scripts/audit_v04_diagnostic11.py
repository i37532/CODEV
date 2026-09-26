#!/usr/bin/env python3
"""Read-only diagnosis; never accepts/relabels a flight or modifies its inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from pyulog import ULog


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(run):
    result = json.loads((run / 'result.json').read_text())
    entry = max(result['logs'], key=lambda x: x['bytes']); path = Path(entry['archive'])
    if sha(path) != entry['sha256']: raise ValueError('Raw ULog changed')
    names = ['sensor_accel', 'vehicle_imu', 'vehicle_imu_status', 'estimator_status_flags',
        'estimator_status', 'estimator_selector_status', 'estimator_local_position', 'estimator_attitude',
        'vehicle_local_position', 'vehicle_local_position_groundtruth', 'vehicle_land_detected',
        'sta_velocity_ctrl_status', 'sta_rate_ctrl_status']
    u = ULog(str(path), message_name_filter_list=names)
    events = {x['name']: x['timestamp_us'] for x in result['events']}
    land = events.get('land_command')
    if land is None: raise ValueError('No landing window; cannot diagnose contact')
    e = dict(kind='diagnosis_not_acceptance', formal_accepted=False, runtime_success=result['success'],
        runtime_error=result.get('error'), ulog=entry, events=events,
        dropout_count=len(u.dropouts), corruption=bool(u.file_corruption), topics={}, faults=[], clipping=[],
        selector=[], reset_changes=[], timing_faults=[], initial_parameters={k: u.initial_parameters.get(k) for k in
            ['MPC_LAND_SPEED', 'MPC_VC_MODE', 'MPC_VC_AXES', 'MC_RTC_MODE', 'MC_STA_AXES', 'MC_RTC_DIV', 'SDLOG_PROFILE']})
    for topic in u.data_list:
        d = topic.data; t = d['timestamp'].astype(np.int64); mask = t >= land; indices = np.flatnonzero(mask)
        delta = np.diff(t)
        stats = dict(samples=len(t), median_interval_us=float(np.median(delta)) if len(delta) else None,
            max_interval_us=int(max(delta)) if len(delta) else None, duplicate_publish_times=int(np.sum(delta == 0)))
        if 'timestamp_sample' in d:
            sample_delta = np.diff(d['timestamp_sample'].astype(np.int64))
            stats['sample_reversals'] = int(np.sum(sample_delta < 0))
            stats['sample_equal'] = int(np.sum(sample_delta == 0))
        e['topics'][f'{topic.name}:{topic.multi_id}'] = stats
        if topic.name == 'estimator_status_flags':
            for i in indices:
                flags = [k for k in d if k.startswith('fs_') and d[k][i]]
                if flags: e['faults'].append(dict(instance=topic.multi_id, t=int(t[i]), sample=int(d['timestamp_sample'][i]), flags=flags))
        if topic.name == 'sensor_accel':
            for i in indices:
                clips = [int(d[f'clip_counter[{a}]'][i]) for a in range(3)]
                if any(clips): e['clipping'].append(dict(instance=topic.multi_id, t=int(t[i]),
                    sample=int(d['timestamp_sample'][i]), clips=clips, xyz=[float(d[a][i]) for a in ('x', 'y', 'z')]))
        if topic.name == 'estimator_selector_status':
            for i in indices:
                if i == 0 or d['primary_instance'][i] != d['primary_instance'][i-1]:
                    e['selector'].append(dict(t=int(t[i]), primary=int(d['primary_instance'][i]),
                        healthy=[int(d[f'healthy[{k}]'][i]) for k in range(6)]))
        if topic.name == 'vehicle_local_position':
            fields = ['xy_reset_counter', 'z_reset_counter', 'vxy_reset_counter', 'vz_reset_counter',
                      'heading_reset_counter', 'ref_alt']
            for i in indices:
                changes = [k for k in fields if i and d[k][i] != d[k][i-1]]
                if changes: e['reset_changes'].append(dict(t=int(t[i]), sample=int(d['timestamp_sample'][i]), fields=changes))
        if topic.name == 'sta_velocity_ctrl_status':
            for field in ['effective_mode', 'effective_axes', 'inner_mode', 'inner_axes', 'inner_divisor', 'timing', 'excitation_fault']:
                e[field] = [int(x) for x in np.unique(d[field][mask])]
            for i in indices:
                if d['timing'][i]: e['timing_faults'].append(dict(t=int(t[i]), raw_dt=float(d['raw_dt'][i])))
    # Keep a compact timestamped contact window; truth is offline evidence only.
    e['contact_window'] = []
    if e['clipping']:
        hit = min(x['sample'] for x in e['clipping'])
        for name in ['vehicle_imu', 'vehicle_local_position_groundtruth', 'vehicle_local_position', 'vehicle_land_detected']:
            for topic in [x for x in u.data_list if x.name == name]:
                d = topic.data
                for i, t in enumerate(d['timestamp']):
                    if hit - 20000 <= int(t) <= hit + 160000:
                        fields = ['timestamp', 'timestamp_sample', 'z', 'vz', 'az', 'delta_velocity_clipping',
                                  'delta_velocity[2]', 'delta_velocity_dt', 'landed', 'ground_contact']
                        e['contact_window'].append(dict(topic=name, instance=topic.multi_id,
                            **{k: float(d[k][i]) for k in fields if k in d}))
    if sha(path) != entry['sha256']: raise ValueError('Raw ULog changed during analysis')
    return e


def main():
    p = argparse.ArgumentParser(); p.add_argument('run', type=Path); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); run = a.run.resolve(); out = a.output.resolve()
    if out == run or run in out.parents: raise ValueError('Analysis must not overwrite flight evidence')
    out.mkdir(parents=True, exist_ok=False)
    e = audit(run)
    (out / 'evidence.json').write_text(json.dumps(e, indent=2, allow_nan=False) + '\n')
    (out / 'artifacts.sha256').write_text(f"{sha(out / 'evidence.json')}  {out / 'evidence.json'}\n")
    print(json.dumps({k: v for k, v in e.items() if k not in ('contact_window', 'topics')}, indent=2))


if __name__ == '__main__': main()
