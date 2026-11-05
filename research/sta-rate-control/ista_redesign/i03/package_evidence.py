#!/usr/bin/env python3
"""Verify the frozen I03 package, audit paired noise, and write small Git evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np

from design import HERE, REPO, build_jobs, digest, load_frozen


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args(); root = args.root.resolve()
    summary = json.loads((root/'i03_summary.json').read_text())
    source_head = summary['source_head']; frozen, expected_jobs = build_jobs(source_head)
    actual_jobs = json.loads((root/'jobs.json').read_text())
    if actual_jobs != expected_jobs or len(actual_jobs) != 12:
        raise ValueError('Frozen job manifest mismatch')
    run_dirs = sorted(p for p in root.glob('[0-9][0-9][0-9][0-9]_I03_*') if p.is_dir())
    if len(run_dirs) != 12 or len(list(root.glob('*.execution.json'))) != 12:
        raise ValueError('Expected exactly 12 attempts/execution records')
    rows = []; innovations = {}; ulogs = []; binaries = set(); sources = set(); adjudications = 0
    for run in run_dirs:
        result = json.loads((run/'result.json').read_text())
        job = json.loads((run/'m10_job.json').read_text())
        analysis = json.loads((run/'i03_analysis.json').read_text())
        execution = json.loads((root/(run.name+'.execution.json')).read_text())
        if not result['success'] or not execution['commands'][0]['returncode'] == 0:
            raise ValueError('I03 flight/runner failure: '+run.name)
        if (run/'worktree_status.txt').read_text().strip() or (run/'tracked_diff.patch').stat().st_size:
            raise ValueError('Formal run was not clean: '+run.name)
        sources.add(result['source_head']); binaries.add(result['binary_sha256'])
        for item in result['logs']:
            if digest(item['archive']) != item['sha256']:
                raise ValueError('ULog fingerprint changed: '+item['archive'])
            ulogs.append(dict(run=run.name, archive=item['archive'], sha256=item['sha256'], bytes=item['bytes']))
        data = np.genfromtxt(run/'imu_innovations.csv', delimiter=',', names=True)
        if len(data) < 5000 or not np.all(np.diff(data['seq'][:5000]) == 1):
            raise ValueError('Insufficient/gapped IMU realization: '+run.name)
        fields = ('gx', 'gy', 'gz', 'ax', 'ay', 'az')
        realization = np.column_stack([data[name][:5000] for name in fields])
        innovations.setdefault(job['seed'], []).append((run.name, realization))
        review = root/(run.name+'.adjudication.json')
        if review.exists():
            reviewed = json.loads(review.read_text()); adjudications += 1
            m10_path = run/'m10_analysis.json'
            if not reviewed.get('analysis_resolved_without_reflight') or reviewed['new_analysis_sha256'] != digest(m10_path):
                raise ValueError('Invalid adjudication: '+run.name)
        rows.append(dict(run=run.name, algorithm=job['algorithm'], protection=job['protection'], seed=job['seed'],
                         accepted=analysis['accepted'], release_delta_s=analysis['manager_release_after_truth_liftoff_s'],
                         liftoff_nu_l2=analysis['liftoff_nu_l2'], early_rate_rmse=analysis['early_rate_rmse'],
                         peak_tilt_deg=analysis['peak_tilt_deg'], ulog_dropouts=analysis['ulog_dropouts'],
                         sequence=analysis['sequence']))
    if sources != {source_head} or len(binaries) != 1 or len(ulogs) != 24:
        raise ValueError('Source/binary/ULog multiplicity mismatch')
    same_seed = {}; first = {}
    for seed, items in innovations.items():
        reference = items[0][1]
        differences = [float(np.max(np.abs(values-reference))) for _, values in items[1:]]
        same_seed[str(seed)] = dict(runs=[name for name, _ in items], max_abs_difference=max(differences, default=0.0), exact=all(v == 0 for v in differences))
        first[seed] = reference
    cross_seed_distinct = all(not np.array_equal(first[a], first[b]) for i, a in enumerate(sorted(first)) for b in sorted(first)[i+1:])
    if not all(row['exact'] for row in same_seed.values()) or not cross_seed_distinct:
        raise ValueError('Seed pairing/variation audit failed')
    evidence = dict(success=True, source_head=source_head, binary_sha256=next(iter(binaries)), planned=12,
                    attempts=12, completed_flights=12, accepted=summary['accepted'], adjudications=adjudications,
                    ulogs=len(ulogs), ulog_bytes=sum(x['bytes'] for x in ulogs), ulog_fingerprints=ulogs,
                    seed_audit=dict(same_seed_first_5000=same_seed, cross_seed_distinct=cross_seed_distinct,
                                    limitation='Only IMU engine and torque phase explicitly seeded; GPS/mag/baro/host scheduling not claimed independent.'),
                    frozen_sha256=digest(HERE/'FROZEN.json'), protocol_sha256=digest(HERE/'PROTOCOL_CN.md'),
                    design_sha256=digest(HERE/'design.py'), analysis_sha256=digest(HERE/'analyze.py'),
                    package_tool_sha256=digest(Path(__file__)),
                    plugin_manifest_sha256=digest(Path(frozen['plugins_manifest']['path'])), rows=rows,
                    selected_common_protection=summary['selected_common_protection'], stop_future_flight=summary['stop_future_flight'])
    write_json(root/'evidence.json', evidence)
    manifest = root/'artifacts.sha256'
    files = sorted(p for p in root.rglob('*') if p.is_file() and p != manifest)
    with manifest.open('w') as stream:
        for path in files:
            stream.write(digest(path)+'  '+str(path.relative_to(root))+'\n')
    results = HERE/'results'; results.mkdir(exist_ok=True)
    shutil.copyfile(root/'i03_summary.json', results/'summary.json')
    shutil.copyfile(root/'evidence.json', results/'evidence.json')
    shutil.copyfile(manifest, results/'artifacts.sha256')
    snapshot = dict(external_root=str(root), external_files=len(files), external_bytes=sum(p.stat().st_size for p in files),
                    external_manifest_sha256=digest(manifest), evidence_sha256=digest(root/'evidence.json'),
                    summary_sha256=digest(root/'i03_summary.json'))
    write_json(results/'package.json', snapshot)
    print(json.dumps(snapshot, indent=2))


if __name__ == '__main__':
    main()
