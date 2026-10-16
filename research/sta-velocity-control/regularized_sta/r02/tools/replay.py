#!/usr/bin/env python3
"""Read-only four-log AX05 full-chain replay, isolated from all old outcomes.

Only R00's already-inspected PID/XYZ H/V logs are eligible; no unseen dataset or
future holdout is opened. This command starts Python analyzers, never simulators.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from config import REPO, HERE, digest

AUDIT = HERE.parents[1] / 'r00/evidence/baseline_audit02.json'
HISTORICAL = REPO / 'research/sta-velocity-control/axis_ablation/ax04/analyze.py'


def snapshot(directory):
    return {p.name: digest(p) for p in sorted(directory.iterdir()) if p.is_file()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output == REPO or REPO in output.parents:
        raise ValueError('Large replay outputs must be external')
    entries = json.loads(AUDIT.read_text())['raw_log_samples']
    if [(x['id'], x['task'], x['candidate']) for x in entries] != [
            ('run007', 'H', 'PID'), ('run008', 'H', 'XYZ'), ('run163', 'V', 'PID'), ('run165', 'V', 'XYZ')]:
        raise ValueError('R00 four-log sampling identity changed')
    for e in entries:
        source = Path(e['archive']).parent.resolve()
        if output == source or source in output.parents:
            raise ValueError('Never write inside original data')
    output.mkdir(parents=True, exist_ok=False)
    evidence = dict(stage='R02-offline-historical-replay', success=False, new_flights=0,
        new_mode3_flight_acceptances=0, historical_decisions_changed=False,
        input_audit=dict(path=str(AUDIT), sha256=digest(AUDIT)),
        analyzer=dict(path=str(HISTORICAL), sha256=digest(HISTORICAL)),
        wrapper_sha256=digest(Path(__file__)), runs=[])
    summary = output / 'evidence.json'
    try:
        for e in entries:
            archive = Path(e['archive']); source = archive.parent
            if digest(archive) != e['sha256']:
                raise ValueError('Old raw ULog fingerprint changed ' + e['id'])
            before = snapshot(source)
            original = json.loads((source / 'xyz_metrics.json').read_text())
            cmd = [sys.executable, str(HISTORICAL), str(source), '--output', str(output / e['id'])]
            env = dict(os.environ)
            env['PYTHONPATH'] = ':'.join([str(REPO / '.px4-python'),
                str(REPO / 'research/sta-velocity-control/scripts'),
                '/home/yr/Desktop/codev doc/experiments/M00-20260912/python', env.get('PYTHONPATH', '')])
            proc = subprocess.run(cmd, cwd=REPO, env=env, text=True, capture_output=True)
            (output / (e['id'] + '.stdout.log')).write_text(proc.stdout)
            (output / (e['id'] + '.stderr.log')).write_text(proc.stderr)
            path = output / e['id'] / 'xyz_metrics.json'
            result = json.loads(path.read_text()) if path.exists() else {}
            after = snapshot(source)
            row = dict(id=e['id'], task=e['task'], candidate=e['candidate'], command=cmd, exit_code=proc.returncode,
                raw_ulog_sha256=e['sha256'], original_accepted=original.get('accepted'),
                replay_accepted=result.get('accepted'), original_files_unchanged=before == after,
                original_file_sha256=before, result_sha256=digest(path) if path.exists() else None,
                whole_chain_keys=sorted(result), error=result.get('error'))
            evidence['runs'].append(row)
            summary.write_text(json.dumps(evidence, indent=2) + '\n')
            if proc.returncode or result.get('accepted') is not True or before != after:
                raise RuntimeError('Historical full-chain replay failed: ' + e['id'])
        evidence['success'] = True
    except BaseException as exc:
        evidence['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        summary.write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(dict(success=True, complete_log_replays=len(evidence['runs']), evidence=str(summary)), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
