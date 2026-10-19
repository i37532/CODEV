#!/usr/bin/env python3
"""Read-only, point-in-time R03 revision04 accounting; never launches or grades flights.

Missing ledgers/metrics are unknown, not zero acceptance. Means use only individually
accepted, hash/job-bound metrics from this revision and gate. No historical pooling,
significance claim, or automatic gate_pass creation. A stored gate_pass is called
passed only after the original replay.verify_complete recomputes the same receipt.
No ULog redecoding occurs here; raw log hashes are recorded claims until that proof.
The optional output directory must be fresh and outside all source/input roots.
"""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
VERSION = HERE/'r03_revision04'
ALGORITHMS = ('PID', 'ESTA', 'RSTA')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def entry(path):
    return dict(path=str(path), sha256=digest(path)) if path.is_file() else None


def exact(a, b):
    return json.dumps(a, sort_keys=True, separators=(',', ':'), allow_nan=False) == \
        json.dumps(b, sort_keys=True, separators=(',', ':'), allow_nan=False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
            'Metric is not finite/nonnegative')
    return value


def vector(value):
    require(isinstance(value, list) and len(value) == 3, 'Expected three-axis metric')
    return [number(x) for x in value]


def measures(metrics, job):
    d = metrics['diagnostic']
    rmse, j, seconds = vector(d['error']['rmse']), number(d['J']), number(d['seconds'])
    require(seconds > 0 and seconds == job['main_duration_s'], 'Wrong metric window')
    require(math.isclose(j, sum(rmse)/3, rel_tol=1e-12, abs_tol=1e-12), 'J is not axis-RMSE mean')
    result = dict(velocity_rmse_m_s=rmse, J_m_s=j, seconds=seconds)
    for stem in ('correction', 'acceleration', 'normalized_thrust'):
        tv, rate = vector(d[stem+'_tv']), vector(d[stem+'_tv_per_second'])
        require(all(math.isclose(a/seconds, b, rel_tol=2e-6, abs_tol=1e-9)
                    for a,b in zip(tv,rate)), 'TV/T mismatch')
        result[stem+'_tv'] = tv
        result[stem+'_tv_per_second'] = rate
    return result


def averages(rows):
    out = {}
    for name in ALGORITHMS:
        selected = [row['measures'] for row in rows if row.get('candidate') == name
                    and row.get('metrics_verified') is True]
        stats = dict(n=len(selected), aggregation='Arithmetic mean of accepted run metrics only')
        if selected:
            for key,value in selected[0].items():
                stats[key] = ([statistics.mean(row[key][i] for row in selected) for i in range(3)]
                              if isinstance(value,list) else statistics.mean(row[key] for row in selected))
        out[name] = stats
    return out


def gate_summary(api, proof, gate):
    root = api.EXTERNAL/api.DATA_STAGE/gate
    batch = root/'batch01'
    jobs = [j for j in api.design()['jobs'] if j['gate'] == gate]
    ledger_path = batch/'ledger.json'
    result = dict(gate=gate, planned=len(jobs), status='pending', gate_passed=False,
        ledger=entry(ledger_path), journal=entry(batch/'journal.jsonl'),
        attempted=None, accepted_recorded=None, accepted_metrics_verified=None, failed=None,
        missing_results=None, missing_metrics=None, unattempted=None, takeoff_commands=None,
        airborne_task_reached=None, paired_recorded=None, independent_replays_recorded=None,
        gate_pass=entry(root/'gate_pass.json'), replay=entry(root/'replay01/summary.json'),
        rows=[], algorithms=None, issues=[])
    if not ledger_path.is_file():
        result['issues'].append('No ledger; actual counts unknown. Planned jobs are not observed attempts.')
        return result
    before = digest(ledger_path)
    try:
        ledger = read(ledger_path)
        require(ledger.get('revision') == api.REVISION and ledger.get('gate') == gate
                and ledger.get('stage') == 'R03-revision04-'+gate, 'Wrong ledger revision/gate')
        attempts = ledger['attempts']
        require(isinstance(attempts,list) and len(attempts) <= len(jobs), 'Invalid attempt count')
        require(type(ledger.get('planned')) is int and ledger['planned'] == len(jobs), 'Wrong ledger plan')
        require(type(ledger.get('total_budget')) is int and ledger['total_budget'] == 51, 'Wrong total budget')
        result.update(attempted=len(attempts), accepted_recorded=sum(r.get('status')=='accepted' for r in attempts),
            failed=sum(r.get('status')=='failed' for r in attempts), unattempted=len(jobs)-len(attempts),
            source_head=ledger.get('source_head'), firmware_sha256=ledger.get('firmware_sha256'),
            parameter_restore_exact=ledger.get('parameter_restore_exact'),
            remaining_simulators=ledger.get('remaining_simulators'))
        expected_dirs = {batch/job['id'] for job in jobs[:len(attempts)]}
        require(set(batch.glob('run[0-9][0-9][0-9]')) == expected_dirs, 'Orphan/missing run directory')
        for index,item in enumerate(attempts):
            job = jobs[index]
            run = batch/job['id']
            require(type(item.get('attempt')) is int and item['attempt'] == index+1
                    and exact(item.get('job'),job) and Path(item['directory']).resolve() == run.resolve(),
                    'Changed/reordered/foreign attempt')
            row = dict(id=job['id'], candidate=job['candidate'], mode=job['mode'], axes=job['axes'],
                seed=job['seed'], status=item.get('status'), result=entry(run/'result.json'),
                metrics=entry(run/'r03_metrics.json'), parameter_restore=entry(run/'parameter_restore.json'),
                takeoff_command=None, airborne_task_reached=None, landed_disarmed=None,
                metrics_verified=False, issues=[])
            result['rows'].append(row)
            if row['result']:
                data = read(run/'result.json')
                require(data.get('source_head') == ledger.get('source_head')
                        and data.get('binary_sha256') == ledger.get('firmware_sha256'), 'Wrong result source/firmware')
                names = [e['name'] for e in data.get('events',[])]
                row.update(takeoff_command='takeoff_command' in names,
                    airborne_task_reached=bool({'handoff_ready','hover_start'} & set(names)),
                    landed_disarmed='landed_disarmed' in names, runner_success=data.get('success'),
                    error=data.get('error'), logs=data.get('logs',[]),
                    log_hash_scope='Recorded result.json fingerprints; complete gate proof verifies raw files')
            else:
                row['issues'].append('Result not present; do not infer takeoff or success')
            if item.get('status') == 'accepted':
                try:
                    require(row['metrics'] is not None, 'Accepted row missing metrics')
                    require(row['metrics']['sha256'] == item.get('metrics_sha256'), 'Accepted metrics SHA changed')
                    metrics = read(run/'r03_metrics.json')
                    require(metrics.get('accepted') is True and exact(metrics.get('job'),job), 'Metrics not accepted/matching job')
                    require(row.get('runner_success') is True, 'Accepted row has no successful result')
                    binding = metrics['binding']
                    require(binding.get('source_head') == ledger.get('source_head')
                            and binding.get('firmware_sha256') == ledger.get('firmware_sha256')
                            and binding.get('revision') == api.REVISION and binding.get('gate') == gate,
                            'Metric source/gate binding changed')
                    row['measures'] = measures(metrics,job)
                    row['metrics_verified'] = True
                except (ValueError,KeyError,TypeError,OSError) as exc:
                    row['issues'].append(repr(exc))
            elif row['metrics']:
                row['issues'].append('Nonaccepted attempt retained; metric excluded from means')
        rows = result['rows']
        result['missing_results'] = sum(row['result'] is None for row in rows)
        result['missing_metrics'] = sum(row['metrics'] is None for row in rows)
        result['takeoff_commands'] = (sum(row['takeoff_command'] for row in rows)
                                       if not result['missing_results'] else None)
        result['airborne_task_reached'] = (sum(row['airborne_task_reached'] for row in rows)
                                         if not result['missing_results'] else None)
        result['accepted_metrics_verified'] = sum(row['metrics_verified'] for row in rows)
        result['algorithms'] = averages(rows)
        pairs = ledger.get('pairs')
        if isinstance(pairs,list):
            result['paired_recorded'] = dict(total=len(pairs), accepted=sum(p.get('accepted') is True for p in pairs),
                failed=sum(p.get('accepted') is False for p in pairs), scope='Recorded decisions, not independent recomputation')
        if result['replay']:
            replay = read(root/'replay01/summary.json')
            require(replay.get('revision') == api.REVISION and replay.get('gate') == gate, 'Foreign replay evidence')
            count=replay.get('replayed')
            require(type(count) is int and 0 <= count <= len(attempts), 'Invalid replay count')
            result['independent_replays_recorded'] = count
        result['status'] = 'stopped_failed' if result['failed'] else 'pending'
        if result['gate_pass']:
            # This existing verifier only reads/recomputes proof; never call finalize/replay_gate.
            verified = proof.verify_complete(gate,root)
            require(exact(read(root/'gate_pass.json'),verified), 'gate_pass does not match complete proof')
            require(verified.get('success') is True and verified.get('accepted') == 9
                    and verified.get('independent_replays') == 9 and verified.get('paired_checks') == 6,
                    'Incomplete gate proof')
            require(not any(row['issues'] for row in rows), 'Summary row validation incomplete')
            result.update(status='passed',gate_passed=True,independent_replays_recorded=9,
                          complete_proof=dict(accepted=9,independent_replays=9,paired_checks=6))
    except (ValueError,KeyError,TypeError,OSError) as exc:
        result.update(status='evidence_error',gate_passed=False)
        result['issues'].append(repr(exc))
    if digest(ledger_path) != before:
        result.update(status='changed_during_read',gate_passed=False)
        result['issues'].append('Ledger changed during read; rerun a fresh summary after activity stops')
    return result


def summarize(api=None, proof=None):
    api = api or load('_r03_revision04_summary_protocol',VERSION/'protocol.py')
    proof = proof or load('_r03_revision04_summary_replay',VERSION/'replay.py')
    api.validate_manifest()
    gates = [gate_summary(api,proof,g) for g in api.GATES]
    return dict(revision=api.REVISION, stage='R03 revision04 result summary', gates=gates,
        all_four_gates_verified=len(gates) == 4 and all(g['gate_passed'] for g in gates),
        new_matrix_planned=36, total_budget=51,
        historical=dict(attempts=15,takeoffs=14,accepted=12,failed=3,pooled_into_new_results=False),
        definitions=dict(rmse='Per-axis time-weighted consumed velocity error, m/s, frozen main window',
            J='Arithmetic mean of three axis RMSEs, then arithmetic mean across accepted runs',
            tv='Per-axis total variation on actual controller updates; TV/T divides by main seconds',
            tv_units='correction/acceleration TV m/s^2, TV/T m/s^3; normalized thrust dimensionless and 1/s',
            takeoffs='Separate takeoff-command and airborne-task event counts; commands alone do not prove lift-off',
            missing='Missing evidence stays null/explicit; failed rows excluded from accepted means, never filled with zero',
            pid_calls='Module update invocations, not PID-axis calculations; not used in this summary'),
        limitations=['Descriptive development means only; no significance or universal superiority claim',
            'Different gates have different tasks and source commits; do not pool their means',
            'No gate_pass is created; passed requires an existing receipt and full read-only proof',
            'TV is not energy; host cost is not board CPU; no flight or log redecoding is performed'])


def write_fresh(directory, value, api):
    directory = Path(directory).resolve()
    for protected in (api.REPO.resolve(),api.EXTERNAL.resolve()):
        if directory == protected or protected in directory.parents:
            # Only a dedicated sibling summary tree, never any experiment inputs.
            allowed = api.EXTERNAL/'R03_revision04_summaries'
            require(protected == api.EXTERNAL.resolve() and allowed.resolve() in directory.parents,
                    'Output is inside a protected source/input tree')
    directory.mkdir(parents=True,exist_ok=False)
    with (directory/'summary.json').open('x') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,help='Optional fresh directory; defaults to stdout only')
    args = parser.parse_args()
    api=load('_r03_revision04_summary_main_protocol',VERSION/'protocol.py')
    value=summarize(api=api)
    if args.output:
        write_fresh(args.output,value,api)
    print(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False))


if __name__ == '__main__':
    main()
