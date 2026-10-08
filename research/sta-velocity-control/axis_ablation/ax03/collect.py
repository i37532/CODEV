#!/usr/bin/env python3
"""AX03 result-only audit. No simulator, parameter writes or acceptance changes."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from pyulog import ULog

CONFIG = Path(__file__).resolve().parents[1] / 'ax02'
sys.path.insert(0, str(CONFIG))
import common

GROUPS = ('PID', 'X', 'Y', 'Z', 'XY', 'XZ', 'YZ', 'XYZ')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def validate_ledger(ledger, jobs):
    if len(jobs) != 48 or ledger['planned'] != 48 or not ledger['success']:
        raise ValueError('Not a completed 48-item matrix')
    attempts = ledger['attempts']
    if len(attempts) != 48 or [a['job'] for a in attempts] != jobs:
        raise ValueError('Missing, replaced or reordered attempts')
    if any(a['attempt'] != i or a['status'] != 'accepted' for i, a in enumerate(attempts, 1)):
        raise ValueError('Failed, duplicated or nonaccepted attempt')
    if (not ledger['parameter_restore_exact'] or ledger['remaining_simulators']
            or ledger.get('H_gate') != 'accepted24'
            or ledger.get('V_PID_safety_gate') != 'accepted_budgeted_run25'):
        raise ValueError('Missing gate or cleanup evidence')
    pairs = ledger['pairs']
    expected = [(j['task'], j['seed'], j['candidate'], j['axes']) for j in jobs if j['axes']]
    actual = [(p['task'], p['seed'], p['candidate'], p['axes']) for p in pairs]
    if actual != expected or any(not p['accepted'] or not all(p['checks'].values()) for p in pairs):
        raise ValueError('Incomplete, changed or failed paired gates')
    return True


def aggregate(records):
    result = {}
    fields = ('rmse_m_s', 'position_rmse_m', 'yaw_rmse_rad', 'correction_tv_per_s',
              'acceleration_tv_per_s', 'normalized_thrust_tv_per_s', 'common_0_7hz_rms',
              'constraint_fraction', 'update_hz')
    for task in ('H', 'V'):
        result[task] = {}
        for group in GROUPS:
            rows = [r for r in records if r['task'] == task and r['candidate'] == group]
            if len(rows) != 3 or len({r['seed'] for r in rows}) != 3:
                raise ValueError('Each task/configuration requires three distinct seeds')
            out = dict(n=3, seeds=[r['seed'] for r in rows])
            for field in fields:
                x = np.asarray([r[field] for r in rows], dtype=float)
                if not np.all(np.isfinite(x)):
                    raise ValueError('Nonfinite metric ' + field)
                out[field] = dict(mean=np.mean(x, axis=0).tolist(),
                                  minimum=np.min(x, axis=0).tolist(), maximum=np.max(x, axis=0).tolist())
            result[task][group] = out
    return result


def raw_evidence(run, record, job):
    evidence = []
    main_state = None
    for entry in record['logs']:
        path = Path(entry['archive'])
        before = digest(path)
        if before != entry['sha256'] or path.stat().st_size != entry['bytes']:
            raise ValueError('Raw ULog fingerprint mismatch: ' + str(path))
        u = ULog(str(path))  # Decode every topic, including each startup ULog.
        if u.dropouts or getattr(u, 'file_corruption', False):
            raise ValueError('Raw ULog transport error: ' + str(path))
        topics = {f'{d.name}:{d.multi_id}': len(d.data['timestamp']) for d in u.data_list}
        evidence.append(dict(archive=str(path), sha256=before, bytes=entry['bytes'],
                             dropouts=0, corruption=False, decoded_topics=topics))
        if path.name == 'log001.ulg':
            d = u.get_dataset('sta_velocity_ctrl_status').data
            events = {e['name']: e['timestamp_us'] for e in record['events']}
            flight = (d['timestamp'] >= events['takeoff_command']) & (d['timestamp'] < events['landed_disarmed'])
            window = (d['timestamp'] >= events['hover_start']) & (d['timestamp'] < events['hover_end'])
            window &= (d['excitation_time'] >= 0) & (d['excitation_time'] < 64)
            if not np.any(d['armed'][flight].astype(bool) & ~d['landed'][flight].astype(bool)):
                raise ValueError('No actual airborne evidence')
            fields = ('requested_mode', 'effective_mode', 'requested_axes', 'effective_axes',
                      'active_axes', 'committed_axes', 'pid_axes', 'z_phase',
                      'inner_mode', 'inner_axes', 'inner_divisor', 'constraint_bits')
            unique = {k: np.unique(d[k][window]).astype(int).tolist() for k in fields}
            expected = dict(requested_mode=job['mode'], effective_mode=job['mode'],
                            requested_axes=job['axes'], effective_axes=job['axes'],
                            active_axes=job['axes'], committed_axes=job['axes'], pid_axes=7 ^ job['axes'],
                            inner_mode=0, inner_axes=0, inner_divisor=1)
            if not np.any(window) or any(unique[k] != [v] for k, v in expected.items()):
                raise ValueError('Actual task mode/axis does not match manifest')
            main_state = dict(takeoff_confirmed=True, task_samples=int(window.sum()), task_values=unique,
                flight_z_phases=np.unique(d['z_phase'][flight]).astype(int).tolist(),
                flight_pid_axes=np.unique(d['pid_axes'][flight]).astype(int).tolist(),
                hover_thrust_range=[float(d['hover_thrust'][window].min()), float(d['hover_thrust'][window].max())],
                hte_shift_peak_m_s2=float(np.abs(d['z_hte_shift'][window]).max()),
                parameter_sha256=digest(run/'runtime_parameters_start.json'))
        if digest(path) != before:
            raise ValueError('ULog changed during audit')
        del u
    if main_state is None:
        raise ValueError('No complete flight ULog')
    return evidence, main_state


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--batch', type=Path, required=True)
    p.add_argument('--replay', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    ledger = read(a.batch/'ledger.json')
    validate_ledger(ledger, common.jobs())
    replay = read(a.replay/'evidence.json')
    if (not replay['success'] or replay['ledger_sha256'] != digest(a.batch/'ledger.json')
            or len(replay['commands']) != 48
            or any(c['exit_code'] or not c['metrics_values_identical'] for c in replay['commands'])):
        raise ValueError('Independent replay incomplete or different')
    rows, raw = [], []
    for item in ledger['attempts']:
        job = item['job']; run = Path(item['directory'])
        m = read(run/'xyz_metrics.json'); r = read(run/'result.json')
        if (not r['success'] or not m['accepted'] or r['source_head'] != ledger['source_head']
                or r['binary_sha256'] != ledger['firmware_sha256']
                or r['scenario_sha256'] != digest(CONFIG/'execution.json')
                or digest(run/'xyz_metrics.json') != item['metrics_sha256']):
            raise ValueError('Original result/source changed')
        if m != read(a.replay/run.name/'xyz_metrics.json'):
            raise ValueError('Replay changed numerical content')
        logs, actual = raw_evidence(run, r, job)
        raw.extend(logs)
        diag = m['diagnostic']; spectrum = m['spectral_summary']; seconds = diag['seconds']
        rows.append(dict(id=job['id'], task=job['task'], seed=job['seed'], candidate=job['candidate'],
            mode=job['mode'], axes=job['axes'], source_head=r['source_head'], accepted=True,
            finished_utc=r['finished_utc'], events=r['events'],
            metrics_sha256=item['metrics_sha256'], directory=str(run), actual=actual,
            rmse_m_s=diag['error']['rmse'], mean_error_m_s=diag['error']['mean'], std_error_m_s=diag['error']['std'],
            iae_m=diag['iae_m'], position_rmse_m=m['position_rmse'], yaw_rmse_rad=m['yaw_rmse'],
            height_from_2p5_m=m['height'], windows=diag['windows'],
            correction_tv_per_s=spectrum['correction_tv_per_second'],
            acceleration_tv_per_s=(np.asarray(diag['acceleration_tv'])/seconds).tolist(),
            normalized_thrust_tv_per_s=(np.asarray(diag['normalized_thrust_tv'])/seconds).tolist(),
            common_0_7hz_rms=spectrum['common_0_7hz_rms'], update_hz=spectrum['update_hz'],
            nu_peak=diag['nu_peak'], constraint_fraction=diag['constraint_fraction'],
            maximum_continuous_constraint_s=diag['maximum_continuous_constraint_s'],
            host_cost=diag['cadence']['host_cost'], host_us_per_sim_second=diag['cadence']['host_us_per_sim_second'],
            local_output=m['local_output'], attitude_output=m['attitude_output'],
            position_log=m['position_log'], landing_health=m['landing_health']))
        print(f'{job["id"]}: all {len(logs)} ULogs decoded, actual axes verified, fingerprints unchanged', flush=True)
    result = dict(success=True, new_flights=0, source_head=ledger['source_head'],
        firmware_sha256=ledger['firmware_sha256'], ledger_sha256=digest(a.batch/'ledger.json'),
        execution_sha256=digest(CONFIG/'execution.json'), frozen_sha256=digest(CONFIG/'frozen.json'),
        counts={task:dict(planned=24, attempted=24, takeoffs=24, accepted=24, failed=0, missing=0,
                         pairs=21) for task in ('H','V')},
        parameter_restore_exact=ledger['parameter_restore_exact'], remaining_simulators=ledger['remaining_simulators'],
        replay_evidence_sha256=digest(a.replay/'evidence.json'), decoded_ulog_count=len(raw),
        summaries=aggregate(rows), runs=rows,
        limitations=['Development n=3/task; no formal significance or universal superiority claim.',
          'Consumed velocity target changes through original position P; not identical open-loop input.',
          'IMU seeds only; other sensors and host scheduling not fully paired/independent.',
          'PID first ordering and historical unequal development exposure are disclosed.',
          'TV is not motor energy; host timing is not board CPU/WCET.'])
    save(a.output/'summary.json', result)
    save(a.output/'ulog_index.json', raw)
    files = sorted(f for f in a.batch.rglob('*') if f.is_file())
    # This is a new external integrity index, not an alteration to the batch.
    save(a.output/'artifacts.json', {str(f):dict(sha256=digest(f),bytes=f.stat().st_size) for f in files})
    print(json.dumps(dict(success=True,runs=len(rows),decoded_ulogs=len(raw),batch_artifacts=len(files))))


if __name__ == '__main__':
    main()
