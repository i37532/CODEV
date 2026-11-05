#!/usr/bin/env python3
"""Verify one completed I04 batch and write small Git-tracked evidence."""
import argparse
import json
from pathlib import Path
import shutil

from design import HERE, build_jobs, digest


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args(); root = args.root.resolve()
    summary = json.loads((root/'i04_summary.json').read_text())
    head = summary['source_head']; frozen, expected = build_jobs(head)
    jobs = json.loads((root/'jobs.json').read_text())
    if jobs != expected or len(jobs) != 8:
        raise ValueError('Frozen I04 job manifest mismatch')
    runs = sorted(p for p in root.glob('[0-9][0-9][0-9][0-9]_I04_*') if p.is_dir())
    if len(runs) != 8 or len(list(root.glob('*.execution.json'))) != 8:
        raise ValueError('Expected exactly eight immutable attempts')
    sources, binaries, ulogs, rows = set(), set(), [], []
    for run in runs:
        result = json.loads((run/'result.json').read_text())
        analysis = json.loads((run/'i04_analysis.json').read_text())
        execution = json.loads((root/(run.name+'.execution.json')).read_text())
        if (run/'worktree_status.txt').read_text().strip() or (run/'tracked_diff.patch').stat().st_size:
            raise ValueError('Formal run was not clean: '+run.name)
        sources.add(result['source_head']); binaries.add(result['binary_sha256'])
        for item in result['logs']:
            if digest(item['archive']) != item['sha256']:
                raise ValueError('ULog fingerprint changed: '+item['archive'])
            ulogs.append(dict(run=run.name, archive=item['archive'], sha256=item['sha256'], bytes=item['bytes']))
        rows.append(dict(run=run.name, algorithm=analysis['algorithm'], seed=analysis['seed'],
                         accepted=analysis['success'], flight_returncode=execution['commands'][0]['returncode'],
                         analysis_returncode=execution['commands'][-1]['returncode'],
                         hover_rmse=analysis.get('hover_rmse'), tracking_rmse=analysis.get('tracking_rmse'),
                         error=analysis.get('error')))
    if sources != {head} or len(binaries) != 1 or summary.get('binary_sha256') not in binaries:
        raise ValueError('Source/binary multiplicity mismatch')
    evidence = dict(success=summary['success'], source_head=head, binary_sha256=next(iter(binaries)),
                    planned=8, attempts=8, accepted=summary['accepted'], ulogs=len(ulogs),
                    ulog_bytes=sum(x['bytes'] for x in ulogs), ulog_fingerprints=ulogs,
                    frozen_sha256=digest(HERE/'FROZEN.json'), protocol_sha256=digest(HERE/'PROTOCOL_CN.md'),
                    seed_audit_sha256=digest(HERE/'SEED_HISTORY_AUDIT.json'),
                    design_sha256=digest(HERE/'design.py'), analysis_sha256=digest(HERE/'analyze.py'),
                    package_tool_sha256=digest(Path(__file__)), plugin_manifest_sha256=digest(Path(frozen['plugins_manifest']['path'])),
                    rows=rows, violations=summary['violations'])
    write_json(root/'evidence.json', evidence)
    manifest = root/'artifacts.sha256'
    files = sorted(p for p in root.rglob('*') if p.is_file() and p != manifest)
    with manifest.open('w') as stream:
        for path in files:
            stream.write(digest(path)+'  '+str(path.relative_to(root))+'\n')
    results = HERE/'results'; results.mkdir(exist_ok=True)
    shutil.copyfile(root/'i04_summary.json', results/'summary.json')
    shutil.copyfile(root/'evidence.json', results/'evidence.json')
    shutil.copyfile(manifest, results/'artifacts.sha256')
    package = dict(external_root=str(root), external_files=len(files),
                   external_bytes=sum(p.stat().st_size for p in files),
                   external_manifest_sha256=digest(manifest), evidence_sha256=digest(root/'evidence.json'),
                   summary_sha256=digest(root/'i04_summary.json'))
    write_json(results/'package.json', package)
    print(json.dumps(package, indent=2))


if __name__ == '__main__':
    main()
