#!/usr/bin/env python3
"""Read-only evidence collection after frozen RI04_REVISION01 analysis; never flies.

This result-layer script does not change acceptance or compute new primary
metrics. It retains the frozen per-run metrics and derives descriptive means.
Existing outputs must match exactly; original runs/qualification are read-only.
"""
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI04_REVISION01')
HERE = Path(__file__).resolve().parent
BATCH = ROOT / 'B/batch01'
REPLAY = ROOT / 'B/replay01'


def read(path):
    return json.loads(path.read_text())


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def save(path, value):
    raw = (json.dumps(json_view(value), indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode()
    if path.exists():
        assert path.read_bytes() == raw, 'Existing result differs: ' + str(path)
    else:
        with path.open('xb') as stream:
            stream.write(raw)


def json_view(value):
    """Lossless tagged display for intentional unlimited diagnostic fields.

    Raw metric files and their hashes remain untouched; tags are never fed
    back into the frozen numerical checks or the aggregates above.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return {'nonfinite_float': 'NaN' if math.isnan(value) else ('Infinity' if value > 0 else '-Infinity')}
    if isinstance(value, dict):
        return {k: json_view(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_view(v) for v in value]
    return value


def exact(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(exact(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(exact(x, y) for x, y in zip(a, b))
    return a == b


def check_nonfinite(value, path=(), *, diagnostic=False):
    allowed = {prefix + (field,) for prefix in (
        ('height_task', 'heading', 'latest_position'),
        ('height_task', 'handoff', 'source', 'reference'),
        ('height_task', 'reference', 'position'))
        for field in ('vxy_max', 'vz_max', 'hagl_min', 'hagl_max')}
    if isinstance(value, dict):
        for key, item in value.items():
            check_nonfinite(item, path + (key,), diagnostic=diagnostic)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            check_nonfinite(item, path + (index,), diagnostic=diagnostic)
    elif isinstance(value, float) and not math.isfinite(value):
        assert diagnostic and path in allowed and value == math.inf, 'Unexpected nonfinite statistic/diagnostic: ' + str(path)


def ref(path):
    return dict(path=str(path), sha256=digest(path), bytes=path.stat().st_size)


def validate_current_ledger(ledger):
    assert ledger['stage'] == 'RI04-REVISION01-B' and ledger['revision'] == 'ri04_revision01'
    assert ledger['source_head'] == 'a1c2046d94a6bbf061720385a5ad36110b1d0dc2'
    assert {k: ledger[k] for k in ('planned','total_budget','new_planned','prior_attempts')} == dict(
        planned=9, total_budget=12, new_planned=9, prior_attempts=3)
    assert len(ledger['attempts']) == 9 and all(r['status'] == 'accepted' for r in ledger['attempts'])
    for index, row in enumerate(ledger['attempts'], 1):
        job = row['job']
        assert job['id'] == f'run{index:03d}' and job['gate'] == 'B' and job['task'] == 'Z'
        assert job['mode'] in (0,3,4) and job['axes'] == (0 if job['mode'] == 0 else 4)


def main():
    qpath = ROOT / 'B/qualification01/evidence.json'
    q, ledger, replay = read(qpath), read(BATCH / 'ledger.json'), read(REPLAY / 'summary.json')
    gate = read(ROOT / 'B/gate_pass.json')
    validate_current_ledger(ledger)
    assert gate['stage'] == 'RI04-REVISION01-B' and gate['revision'] == 'ri04_revision01'
    import sys
    sys.path.insert(0, str(HERE.parent/'tools'))
    import bindings
    bindings.local('replay').verify_complete(REPLAY)
    assert q['success'] and q['approved'] and all(c['exit_code'] == 0 for c in q['commands'])
    assert ledger['success'] and len(ledger['attempts']) == 9 and len(ledger['pairs']) == 6
    assert ledger['parameter_restore_exact'] and ledger['remaining_simulators'] == [] and ledger['unattempted'] == []
    assert replay['success'] and replay['replayed'] == 9 and replay['source_inputs_unchanged']
    assert len(replay['commands']) == 9 and all(c['returncode'] == 0 for c in replay['commands'])
    assert gate['accepted'] and gate['source_head'] == ledger['source_head'] == q['source_head']
    assert gate['firmware_sha256'] == ledger['firmware_sha256'] == q['firmware_sha256']
    assert gate['ledger_sha256'] == digest(BATCH / 'ledger.json')
    assert gate['replay_summary_sha256'] == digest(REPLAY / 'summary.json')
    assert exact(ledger['pairs'], replay['pairs'])
    runs, raw_logs = [], []
    for item in ledger['attempts']:
        run = Path(item['directory'])
        metrics, result = read(run / 'r03_metrics.json'), read(run / 'result.json')
        assert item['status'] == 'accepted' and metrics['accepted'] and result['success']
        assert digest(run / 'r03_metrics.json') == item['metrics_sha256']
        assert exact(metrics, read(REPLAY / run.name / 'r03_metrics.json'))
        check_nonfinite(metrics, diagnostic=True)
        assert digest(run / 'spectra.json') == digest(REPLAY / run.name / 'spectra.json')
        events = {e['name'] for e in result['events']}
        assert {'takeoff_command', 'hover_start', 'hover_end', 'landed_disarmed'} <= events
        restore = read(run / 'parameter_restore.json')
        assert restore['parameter_restore_exact'] and restore['remaining_simulators'] == []
        for log in result['logs']:
            actual = ref(Path(log['archive']))
            assert actual['sha256'] == log['sha256'] and actual['bytes'] == log['bytes']
            raw_logs.append(dict(job_id=run.name, **actual))
        runs.append(dict(id=run.name, seed=item['job']['seed'], candidate=item['job']['candidate'],
            attempted=True, airborne=True, accepted=True, metrics=metrics,
            result=ref(run / 'result.json'), metrics_file=ref(run / 'r03_metrics.json'),
            spectra=ref(run / 'spectra.json'), parameter_restore=ref(run / 'parameter_restore.json')))
    groups = {}
    for candidate in ('PID', 'RSTA', 'RISTA'):
        rows = [row['metrics'] for row in runs if row['candidate'] == candidate]
        assert len(rows) == 3
        vector = lambda fn: [statistics.mean(fn(row)[axis] for row in rows) for axis in range(3)]
        groups[candidate] = dict(n=3,
            rmse_mean=vector(lambda r: r['diagnostic']['error']['rmse']),
            rmse_between_run_sd=[statistics.stdev(r['diagnostic']['error']['rmse'][a] for r in rows) for a in range(3)],
            J_mean=statistics.mean(r['diagnostic']['J'] for r in rows),
            position_rmse_mean=vector(lambda r: r['position_rmse']),
            height_rmse_mean=statistics.mean(r['height']['rmse'] for r in rows),
            yaw_rmse_mean=statistics.mean(r['yaw_rmse'] for r in rows),
            correction_tv_per_second_mean=vector(lambda r: r['diagnostic']['correction_tv_per_second']),
            acceleration_tv_per_second_mean=vector(lambda r: r['diagnostic']['acceleration_tv_per_second']),
            thrust_tv_per_second_mean=vector(lambda r: r['diagnostic']['normalized_thrust_tv_per_second']),
            common_0_7hz_rms_mean=vector(lambda r: r['spectral_summary']['common_0_7hz_rms']),
            cost_mean_of_per_run_quantiles={field: {stat: statistics.mean(r['host_cost'][field][stat] for r in rows)
                for stat in ('median_us', 'p95_us', 'p99_us', 'max_us')} for field in ('path_ns', 'module_ns')})
    paired = []
    for seed in sorted({r['seed'] for r in runs}):
        block = {r['candidate']: r['metrics'] for r in runs if r['seed'] == seed}
        a = block['RSTA']['diagnostic']['error']['rmse'][2]
        b = block['RISTA']['diagnostic']['error']['rmse'][2]
        paired.append(dict(seed=seed, rsta_z_rmse=a, rista_z_rmse=b, rista_minus_rsta=b-a,
                           rista_relative_change_percent=100*(b-a)/a))
    check_nonfinite(groups)
    check_nonfinite(paired)
    summary = dict(stage='RI04-REVISION01-B', status='passed', source_head=ledger['source_head'],
        firmware_sha256=ledger['firmware_sha256'], qualification=ref(qpath), qualification_counts=q['counts'],
        budget=dict(planned=9, attempted=9, airborne=9, accepted=9, failed=0, invalid=0, missing=0, unattempted=0, retries=0),
        history=dict(prior_attempted=3, prior_accepted=2, prior_failed=1, old_unattempted_cancelled=6,
                     total_attempts=12, total_authorized_maximum=12, historical_samples_not_pooled=True),
        rista_hte_records=[dict(id=r['id'], cache=r['metrics']['flight']['closed_cache_policy'],
            mapping=r['metrics']['flight']['closed_cache_hte']) for r in runs if r['candidate']=='RISTA'],
        independent_replays=9, paired_risk_checks=6, paired_individual_checks=78,
        parameter_restore_exact=True, remaining_simulators=[], groups=groups,
        rista_vs_rsta_descriptive_pairs=paired, runs=runs,
        ledger=ref(BATCH / 'ledger.json'), replay=ref(REPLAY / 'summary.json'), gate=ref(ROOT / 'B/gate_pass.json'),
        diagnostic_serialization='Nonfinite source diagnostics use explicit nonfinite_float tags, not zero/null; original metrics are unchanged',
        limits=['n=3 paired development only, no significance claim', 'Only Z velocity R-ISTA; X/Y and rate PID',
                'Common source parameters, no per-algorithm tuning or pure Euler causal claim',
                'TV is not energy; host wall-clock is not board CPU/WCET', 'MATLAB was not rerun'])
    save(HERE / 'summary.json', summary)
    save(HERE / 'ulog_index.json', dict(log_count=len(raw_logs), files=raw_logs))
    save(HERE / 'gate_pass.json', gate)
    # Full historical/preflight/new-flight evidence inventory, no deletion or relabelling.
    index_path = ROOT / 'archive_index.json'
    files, links = [], {}
    for path in sorted(ROOT.rglob('*')):
        if path == index_path:
            continue
        if path.is_symlink():
            links[str(path)] = str(path.readlink())
        elif path.is_file():
            files.append(ref(path))
    save(index_path, dict(scope=str(ROOT), files=files, symlinks=links,
                         excludes=['archive_index.json (self)'], preserved_failures=True))
    save(HERE / 'archive_reference.json', dict(**ref(index_path), file_count=len(files), symlink_count=len(links)))
    print(json.dumps(dict(status='passed', runs=len(runs), logs=len(raw_logs), archive_files=len(files),
                          groups=groups, rista_vs_rsta=paired), indent=2))


if __name__ == '__main__':
    main()
