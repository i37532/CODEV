"""Offline parameter/evidence archive verification; cannot launch a vehicle."""
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent
KEYS = ('rise90_s', 'true_height_rmse_m', 'true_height_std_m')
PROFILES = {'PID_REF': 'PID.json', 'STA_REF': 'STA_XYZ.json', 'E06': 'ISTA_E06_XYZ.json'}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(root=ROOT):
    hashes = read(root / 'SHA256.json')
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()
              and p.name != 'SHA256.json' and '__pycache__' not in p.parts}
    require(actual == set(hashes), 'Archive file set changed')
    for name, expected in hashes.items():
        path = (root / name).resolve()
        require(path.is_relative_to(root.resolve()), 'Foreign archive path')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'Changed file: ' + name)
    manifest = read(root / 'evidence/flight_manifest.json')
    results = read(root / 'results.json')
    provenance = read(root / 'provenance.json')
    index = read(root / 'ulog_index.json')
    jobs = manifest['jobs']
    require(len(jobs) == manifest['maximum_attempts'] == manifest['total_maximum_attempts'] == 9, 'Budget')
    require([j['id'] for j in jobs] == [f'Q{i:03d}' for i in range(1, 10)], 'Order/IDs')
    require([j['seed'] for j in jobs] == [99601]*3+[99602]*3+[99603]*3, 'Seeds')
    expected = ['PID_REF', 'STA_REF', 'E06', 'STA_REF', 'E06', 'PID_REF', 'E06', 'PID_REF', 'STA_REF']
    require([j['tuning_candidate'] for j in jobs] == expected, 'Candidate order')
    for job in jobs:
        p = read(root / 'parameters' / PROFILES[job['tuning_candidate']])
        require(p == job['parameters'], 'Full profile mismatch')
        require(p['MPC_VC_MODE'] == {'PID_REF': 0, 'STA_REF': 3, 'E06': 4}[job['tuning_candidate']], 'Mode')
        require(p['MPC_VC_AXES'] == (0 if job['tuning_candidate'] == 'PID_REF' else 7), 'Axes')
        for k, v in {'MPC_VC_DIV': 1, 'MC_RTC_DIV': 1, 'MC_RTC_MODE': 0, 'MC_STA_AXES': 0,
                     'MC_RATT_TEST': 0, 'MC_STA_TKO_MGT': 0, 'MPC_VCT_TEST': 5,
                     'EKF2_BARO_NOISE': .3, 'EKF2_ACC_B_NOISE': .003, 'NAV_MC_ALT_RAD': .1}.items():
            require(p[k] == v, 'Shared parameter mismatch: ' + k)
        if job['tuning_candidate'] == 'E06':
            for axis in 'XYZ':
                values = [p[f'MPC_VC_{name}_{axis}'] for name in ('L1','L2','EPS','NU','A')]
                require(values == ([.55,.11,.01,.4,.8] if axis in 'XY' else [3.3,1.56,.06,4,6]), 'E06 drift')
    require(results['complete'] and results['accepted'] == 9 and results['independent_replays'] == 9, 'Incomplete')
    rows = results['measured']
    require(len(rows) == 9 and [r['id'] for r in rows] == [j['id'] for j in jobs], 'Result order')
    for row, job in zip(rows, jobs):
        require(row['seed'] == job['seed'] and row['tuning_candidate'] == job['tuning_candidate'], 'Row identity')
        require(all(isinstance(row[k], (int, float)) and not isinstance(row[k], bool)
                    and math.isfinite(row[k]) and row[k] >= 0 for k in KEYS), 'Invalid primary metric')
    assessment = results['assessment']
    means = {key: {metric: statistics.fmean(r[metric] for r in rows if r['tuning_candidate'] == key)
                   for metric in KEYS} for key in PROFILES}
    require(means == assessment['means'], 'Mean mismatch')
    thresholds = {k: min(means[r][k] for r in ('PID_REF','STA_REF')) * (.99 if k != 'rise90_s' else 1)
                  - (.02 if k == 'rise90_s' else 0) for k in KEYS}
    passed = {k: means['E06'][k] <= thresholds[k] for k in KEYS}
    require(thresholds == assessment['thresholds'] and passed == assessment['endpoint_passed'], 'Threshold mismatch')
    require(all(passed.values()) == assessment['scientific_success'], 'Scientific conclusion mismatch')
    for pair in assessment['pairs']:
        selected = next(r for r in rows if r['seed'] == pair['seed'] and r['tuning_candidate'] == 'E06')
        ref = next(r for r in rows if r['seed'] == pair['seed'] and r['tuning_candidate'] == pair['reference'])
        require(pair['differences'] == {k: selected[k]-ref[k] for k in KEYS}, 'Paired difference mismatch')
        require(pair['wins'] == {k: selected[k]<ref[k] for k in KEYS}, 'Paired wins mismatch')
    require(provenance['parameters_restored'] and provenance['source_unchanged_during_experiment'], 'Restore/source')
    require(provenance['firmware_sha256'] == '96f20a849bbd1ad0f1c9222c26ba2ebb79ed74bfda5ca10cbf67436b791cab00', 'Firmware')
    require([r['id'] for r in index] == [j['id'] for j in jobs], 'ULog index IDs')
    require(all(r['accepted'] and r['independent_replay_verified'] and r['parameter_restore_exact']
                and r['logs'] and all(len(log['sha256']) == 64 and log['bytes'] > 0 for log in r['logs'])
                for r in index), 'ULog metadata')
    return dict(files=len(hashes), runs=len(jobs), scientific_success=all(passed.values()),
                scope='Archive hashes and summary arithmetic only; not ULog replay or flight')


if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
