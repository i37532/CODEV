#!/usr/bin/env python3
"""Verify archived Z03 results and isolated replays; no flight or parameter writes."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--batch', type=Path, required=True)
    p.add_argument('--replay', type=Path, required=True)
    p.add_argument('--verification', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    ledger = read(a.batch / 'ledger.json')
    assert ledger['success'] and ledger['parameter_restore_exact'] and not ledger['remaining_simulators']
    assert len(ledger['attempts']) == 6 and len(ledger['pairs']) == 3
    assert all(x['accepted'] and x['paired_noise'] for x in ledger['pairs'])
    evidence = read(a.verification / 'evidence.json')
    assert evidence['success'] and evidence['head'] == ledger['source_head']
    assert all(c['exit_code'] == 0 for c in evidence['commands'])
    rows = []
    for item in ledger['attempts']:
        assert item['status'] == 'accepted'
        run = Path(item['directory'])
        d = read(run / 'z03_metrics.json')
        replay = a.replay / run.name / 'z03_metrics.json'
        assert d['accepted'] and read(replay) == d
        rows.append(d)
    groups = []
    for mode in (0, 1):
        group = [d for d in rows if d['job']['mode'] == mode]
        assert len(group) == 3
        groups.append(dict(mode=mode, n=3,
            velocity_rmse_mean=[statistics.mean(d['diagnostic']['error']['rmse'][i] for d in group) for i in range(3)],
            z_request_tv_mean=statistics.mean(d['diagnostic']['acceleration_tv'][2] for d in group),
            height_rmse_mean=statistics.mean(d['height']['rmse'] for d in group),
            yaw_rmse_mean=statistics.mean(d['yaw_rmse'] for d in group)))
    paths = [a.batch / 'ledger.json']
    paths += [f for f in a.verification.rglob('*') if f.is_file()]
    paths += [f for f in a.replay.rglob('*') if f.is_file()]
    # Fresh hashes of every raw artifact; missing/changed source fails, never reclassifies a run.
    for line in (a.output.parent / 'raw_artifacts.sha256').read_text().splitlines():
        expected, path = line.split('  ', 1)
        assert sha(Path(path)) == expected, path
    result = dict(accepted=True, source_head=ledger['source_head'],
        verification=evidence, isolated_replays_equal=6, groups=groups,
        evidence_sha256={str(f): sha(f) for f in sorted(set(paths))})
    with a.output.open('x') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    print(json.dumps(dict(accepted=True, groups=groups, replay_count=6, evidence_files=len(paths))))


if __name__ == '__main__':
    main()
