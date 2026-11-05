"""AX05 post-flight integrity audit; never starts flights or changes acceptance.

Reuse only AX03's per-file ULog decoder. Its 48-run acceptance/aggregation
functions are deliberately NOT used. Formal metrics/statistics remain AX04's.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ax03'))
from collect import digest, raw_evidence


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def validate_complete(ledger, manifest, qualified):
    """Certificate for this complete matrix only; fail closed on partial batches."""
    if len(manifest) != 320 or ledger.get('planned') != 320 or ledger.get('success') is not True:
        raise ValueError('Not a completed formal320 matrix')
    for key in ('source_head', 'firmware_sha256'):
        if ledger.get(key) != qualified[key]:
            raise ValueError('Wrong formal qualification: ' + key)
    if (ledger.get('parameter_restore_exact') is not True or ledger.get('remaining_simulators') != []
            or any(ledger.get(k) != 'accepted160_140pairs' for k in ('H_gate', 'V_gate'))):
        raise ValueError('Missing cleanup or task gate')
    attempts = ledger['attempts']
    if len(attempts) != 320 or any(a['attempt'] != i or a['status'] != 'accepted' or a['job'] != j
            for i, (a, j) in enumerate(zip(attempts, manifest), 1)):
        raise ValueError('Incomplete, failed, replaced or reordered attempts')
    keys = ('task', 'seed', 'candidate', 'axes', 'divisor')
    expected = sorted(tuple(j[k] for k in keys) for j in manifest if j['axes'])
    pairs = ledger['pairs']
    actual = sorted(tuple(p[k] for k in keys) for p in pairs)
    required = {'yaw'} | {f'{prefix}{i}' for prefix in
        ('velocity_', 'position_', 'first_loop_velocity_', 'second_loop_velocity_') for i in range(3)}
    if (len(pairs) != 280 or actual != expected or any(p.get('accepted') is not True
            or set(p['checks']) != required or any(v is not True for v in p['checks'].values()) for p in pairs)):
        raise ValueError('Incomplete, duplicated or failed paired gates')
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--batch', type=Path, required=True)
    p.add_argument('--qualification', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    config = ROOT / 'ax04'
    ledger = read(a.batch / 'ledger.json')
    manifest = read(config / 'manifest.json')
    qualified = read(a.qualification)
    validate_complete(ledger, manifest, qualified)
    a.output.mkdir(parents=True, exist_ok=False)
    evidence = dict(success=False, flights_run=0, ledger_sha256=digest(a.batch / 'ledger.json'),
        source_head=ledger['source_head'], firmware_sha256=ledger['firmware_sha256'],
        qualification_sha256=digest(a.qualification), runs=[], ulogs=[])
    try:
        for item in ledger['attempts']:
            run = Path(item['directory']); record = read(run / 'result.json')
            if (record['success'] is not True or record['source_head'] != ledger['source_head']
                    or record['binary_sha256'] != ledger['firmware_sha256']
                    or record['scenario_sha256'] != digest(config / 'execution.json')
                    or digest(run / 'xyz_metrics.json') != item['metrics_sha256']):
                raise ValueError('Changed raw result/source/metrics: ' + run.name)
            logs, actual = raw_evidence(run, record, item['job'])
            evidence['ulogs'].extend(logs)
            evidence['runs'].append(dict(attempt=item['attempt'], id=run.name,
                task=item['job']['task'], candidate=item['job']['candidate'], seed=item['job']['seed'],
                finished_utc=record['finished_utc'], actual=actual))
            print(f'{run.name}: {len(logs)} ULogs fully decoded and unchanged', flush=True)
        files = sorted(f for f in a.batch.rglob('*') if f.is_file())
        save(a.output / 'artifacts.json', {str(f): dict(sha256=digest(f), bytes=f.stat().st_size) for f in files})
        evidence.update(decoded_ulogs=len(evidence['ulogs']), batch_artifacts=len(files),
            artifacts_sha256=digest(a.output / 'artifacts.json'))
        if digest(a.batch / 'ledger.json') != evidence['ledger_sha256']:
            raise ValueError('Ledger changed during read-only audit')
        evidence['success'] = True
    finally:
        save(a.output / 'evidence.json', evidence)


if __name__ == '__main__':
    main()
