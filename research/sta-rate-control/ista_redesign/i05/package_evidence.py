#!/usr/bin/env python3
"""Verify one completed I05 subgate and retain small Git evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from design import HERE, jobs, load


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--subgate', choices=('A',), required=True)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    summary = json.loads((root / 'summary.json').read_text())
    head = summary['source_head']
    frozen, expected = jobs(head, args.subgate)
    manifest = json.loads((root / 'jobs.json').read_text())
    if manifest != expected:
        raise ValueError('Frozen job manifest mismatch')
    runs = sorted(p for p in root.glob(f'[0-9][0-9][0-9][0-9]_I05{args.subgate}_*') if p.is_dir())
    if len(runs) != len(expected) or len(list(root.glob('*.execution.json'))) != len(expected):
        raise ValueError('Immutable attempt count mismatch')
    sources, binaries, ulogs, rows = set(), set(), [], []
    for run in runs:
        result = json.loads((run / 'result.json').read_text())
        analysis = json.loads((run / 'i05_analysis.json').read_text())
        execution = json.loads((root / (run.name + '.execution.json')).read_text())
        if (run / 'worktree_status.txt').read_text().strip() or (run / 'tracked_diff.patch').stat().st_size:
            raise ValueError('Formal run was not clean: ' + run.name)
        sources.add(result['source_head'])
        binaries.add(result['binary_sha256'])
        for item in result['logs']:
            if digest(item['archive']) != item['sha256']:
                raise ValueError('ULog fingerprint changed: ' + item['archive'])
            ulogs.append(dict(run=run.name, archive=item['archive'], sha256=item['sha256'], bytes=item['bytes']))
        rows.append(dict(run=run.name, algorithm=analysis['algorithm'], seed=analysis['seed'],
                         run_valid=analysis['success'], flight_returncode=execution['commands'][0]['returncode'],
                         analysis_returncode=execution['commands'][-1]['returncode'],
                         metrics=analysis.get('metrics'), error=analysis.get('error')))
    if sources != {head} or len(binaries) != 1 or summary.get('binary_sha256') not in binaries:
        raise ValueError('Source/binary multiplicity mismatch')
    _, _, plugins = load(args.subgate)
    evidence = dict(gate_success=summary['success'], source_head=head,
                    binary_sha256=next(iter(binaries)), planned=len(expected), attempts=len(runs),
                    individually_valid=summary['accepted'], ulogs=len(ulogs),
                    ulog_bytes=sum(x['bytes'] for x in ulogs), ulog_fingerprints=ulogs,
                    frozen_sha256=digest(HERE / f'FROZEN_{args.subgate}.json'),
                    protocol_sha256=digest(HERE / f'PROTOCOL_{args.subgate}_CN.md'),
                    seed_audit_sha256=digest(HERE / f'SEED_HISTORY_AUDIT_{args.subgate}.json'),
                    design_sha256=digest(HERE / 'design.py'), analysis_sha256=digest(HERE / 'analyze.py'),
                    package_tool_sha256=digest(Path(__file__)),
                    plugin_manifest_sha256=digest(plugins / 'manifest.json'),
                    rows=rows, violations=summary['violations'])
    write_json(root / 'evidence.json', evidence)
    checksum_file = root / 'artifacts.sha256'
    files = sorted(p for p in root.rglob('*') if p.is_file() and p != checksum_file)
    with checksum_file.open('w') as stream:
        for path in files:
            stream.write(digest(path) + '  ' + str(path.relative_to(root)) + '\n')
    results = HERE / 'results' / args.subgate
    results.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / 'summary.json', results / 'summary.json')
    shutil.copyfile(root / 'evidence.json', results / 'evidence.json')
    shutil.copyfile(checksum_file, results / 'artifacts.sha256')
    package = dict(external_root=str(root), external_files=len(files),
                   external_bytes=sum(p.stat().st_size for p in files),
                   external_manifest_sha256=digest(checksum_file),
                   evidence_sha256=digest(root / 'evidence.json'),
                   summary_sha256=digest(root / 'summary.json'))
    write_json(results / 'package.json', package)
    print(json.dumps(package, indent=2))


if __name__ == '__main__':
    main()
