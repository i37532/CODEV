#!/usr/bin/env python3
"""Read-only, post-hoc bias/variance decomposition of a fixed historical subset.

No calls to existing analyzers that write into historical run directories.
Not new held-out evidence; preserves the original callback-grid RMSE/window.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from pyulog import ULog

from audit import digest, moments, write_json


def vector(data, name):
    return np.column_stack([data[f'{name}[{i}]'] for i in range(3)]).astype(float)


def analyze(run):
    path = run/'m10_analysis.json'
    before = digest(path)
    old = json.loads(path.read_text())
    if not old['success']:
        raise ValueError('This fixed descriptive subset requires accepted historical runs')
    fingerprints = {row['archive']: row['sha256'] for row in old['logs']}
    for file, expected in fingerprints.items():
        if digest(file) != expected:
            raise ValueError('Historical ULog fingerprint mismatch')
    log = ULog(old['ulog'])
    d = log.get_dataset('sta_rate_ctrl_status').data
    t = d['timestamp_sample'].astype(np.int64)
    idx = np.flatnonzero((t >= old['tracking_start_us']) & (t < old['tracking_start_us']+36000000))
    if len(idx) != 9000 or np.any(np.diff(t[idx]) != 4000):
        raise ValueError('Incomplete original 36s callback window')
    if np.any(np.diff(d['publish_seq'][idx].astype(np.int64)) != 1):
        raise ValueError('Missing diagnostics')
    if not np.all(d['effective_mode'][idx] == old['mode']):
        raise ValueError('Mode mismatch')
    # Preserve the historical callback-grid s field for the primary RMSE;
    # candidate fields/dt are meaningful only on actual updates.
    error = vector(d, 's')[idx]
    stats = moments(error)
    if not np.allclose(stats['rmse'], old['rmse_tracking'], rtol=1e-10, atol=1e-12):
        raise AssertionError('Original RMSE not reproduced')
    updates = idx[d['updated'][idx].astype(bool)]
    h = d['dt'][updates].astype(float)
    nu = vector(d, 'nu')[updates]
    missing_updates = int(np.maximum(np.diff(d['update_seq'][updates].astype(np.int64))-1, 0).sum())
    if missing_updates:
        raise ValueError('Missing actual updates')
    result = dict(run=str(run), mode=old['mode'], candidate=old['candidate'], scene=old['scene'], seed=old['seed'],
                  source_head=old['source_head'], historical_analysis_sha256=before, logs_sha256=fingerprints,
                  window_start_us=old['tracking_start_us'], duration_s=36., callbacks=len(idx), updates=len(updates),
                  diagnostic_missing=0, update_missing=missing_updates, ulog_dropouts=len(log.dropouts),
                  effective_axes=np.unique(d['effective_axes'][idx]).tolist(),
                  dt_min=float(np.min(h)), dt_max=float(np.max(h)), moments=stats,
                  nu_mean_updates=np.mean(nu, axis=0).tolist(),
                  negative_h_nu_mean_updates=np.mean(-h[:, None]*nu, axis=0).tolist(),
                  protected_counts=np.count_nonzero(vector(d, 'limits')[idx], axis=0).tolist(),
                  old_raw_motor_limits_diagnostic=old['motor_original'],
                  original_rmse_reproduced=True)
    if old['mode'] == 2:
        result['virtual_mean_updates'] = np.mean(vector(d, 'virtual_state')[updates], axis=0).tolist()
    if digest(path) != before or any(digest(file) != sha for file, sha in fingerprints.items()):
        raise AssertionError('Historical files changed')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    selected = []
    for stage in ('reference', 'screen', 'training'):
        for path in sorted((a.root/stage).glob('*/m10_job.json')):
            job = json.loads(path.read_text())
            if job['candidate'] in ('ESTA', 'L09') and job['scene'] in ('nominal', 'div2', 'div4') and job['seed'] in (5201, 5202):
                selected.append(path.parent)
    if len(selected) != 12:
        raise AssertionError(('Expected 12 fixed historical runs', selected))
    manifest = Path(__file__).resolve().parents[2]/'ista_opt02/results_evidence/artifacts.sha256'
    pinned = {line.split('  ', 1)[1]: line.split('  ', 1)[0] for line in manifest.read_text().splitlines()}
    data = []
    for run in selected:
        print('DECODE', run, flush=True)
        for name in ('m10_job.json', 'm10_analysis.json'):
            path = run/name
            if digest(path) != pinned[str(path)]:
                raise ValueError('Historical metadata differs from committed index')
        row = analyze(run)
        if any(sha != pinned[path] for path, sha in row['logs_sha256'].items()):
            raise ValueError('ULog differs from committed index')
        write_json(a.output/(run.name+'.json'), row)
        data.append(row)
    write_json(a.output/'summary.json', dict(scope='Exploratory selected historical subset, not independent validation',
               success=True, runs=data, original_primary_metric_unchanged=True,
               historical_manifest_sha256=digest(manifest)))


if __name__ == '__main__':
    main()
