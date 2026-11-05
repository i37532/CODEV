#!/usr/bin/env python3
"""Read-only final R03 index: retained A04/B05/C05 and new D06 evidence.

No flights, simulator processes, analyzer subprocesses, regrading, receipt creation,
or writes to inputs. All raw ULogs are hashed, not decoded. An existing gate_pass
must equal its original version's read-only verify_complete result. Do not run on
an active batch: any observed mutation invalidates the snapshot. Output is stdout
unless --output names a fresh directory under EXTERNAL/R03_revision06_summaries.
Exit 0 means all four original-version gate proofs were verified; otherwise exit 2.
Only observed attempts appear: no future manifest rows/seeds are serialized.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import statistics
import sys

# Importing the frozen readers must not create/update repository __pycache__.
sys.dont_write_bytecode = True

REPO = Path('/home/yr/Desktop/Codev-autopilot')
REGULARIZED = Path('research/sta-velocity-control/regularized_sta')
ALGORITHMS = ('PID', 'ESTA', 'RSTA')
ERRORS = (ValueError, KeyError, TypeError, OSError)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def exact(a, b):
    return json.dumps(a, sort_keys=True, separators=(',', ':'), allow_nan=False) == \
        json.dumps(b, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(path):
    path = Path(path)
    before = path.stat()
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            h.update(chunk)
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            'File changed while hashing: '+str(path))
    return h.hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inventory(root):
    return {str(p): ('link', str(p.readlink())) if p.is_symlink() else
            ('file',) if p.is_file() else ('directory',)
            for p in sorted(Path(root).rglob('*'))}


class Evidence:
    def __init__(self):
        self.files = {}
        self.trees = {}

    def track(self, path):
        path = Path(path).resolve()
        sha = digest(path)
        require(str(path) not in self.files or self.files[str(path)] == sha,
                'Input changed between reads: '+str(path))
        self.files[str(path)] = sha
        return dict(path=str(path), sha256=sha)

    def read(self, path):
        entry = self.track(path)
        value = json.loads(Path(path).read_text())
        require(digest(path) == entry['sha256'], 'JSON changed during read')
        return value

    def optional(self, path):
        return self.track(path) if Path(path).is_file() else None

    def tree(self, root):
        self.trees[str(root)] = inventory(root)

    def finish(self):
        require(all(inventory(root) == before for root, before in self.trees.items()),
                'Input tree changed during summary')
        require(all(digest(path) == sha for path, sha in self.files.items()),
                'Input bytes changed during summary')
        return dict(files=self.files, trees=self.trees, unchanged=True)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
            'Expected finite nonnegative metric')
    return value


def vector(value):
    require(type(value) is list and len(value) == 3, 'Expected three-axis metric')
    return [number(v) for v in value]


def measures(metrics, job):
    d = metrics['diagnostic']
    rmse, j, seconds = vector(d['error']['rmse']), number(d['J']), number(d['seconds'])
    require(seconds > 0 and seconds == job['main_duration_s'], 'Wrong main window')
    require(math.isclose(j, sum(rmse)/3, rel_tol=1e-12, abs_tol=1e-12), 'J is not mean of axis RMSE')
    out = dict(velocity_rmse_m_s=rmse, J_m_s=j, seconds=seconds,
               position_rmse_m=vector(metrics['position_rmse']), yaw_rmse_rad=number(metrics['yaw_rmse']))
    for stem in ('correction', 'acceleration', 'normalized_thrust'):
        tv, rate = vector(d[stem+'_tv']), vector(d[stem+'_tv_per_second'])
        require(all(math.isclose(a/seconds, b, rel_tol=2e-6, abs_tol=1e-9)
                    for a, b in zip(tv, rate)), 'TV/T mismatch')
        out[stem+'_tv'], out[stem+'_tv_per_second'] = tv, rate
    return out


def averages(rows):
    out = {}
    for candidate in ALGORITHMS:
        selected = [row for row in rows if row['candidate'] == candidate and row['metrics_verified']]
        result = dict(n=len(selected), ids=[row['id'] for row in selected],
                      aggregation='Descriptive arithmetic mean of accepted, individually verified run metrics only')
        if selected:
            result['mean'], result['range'] = {}, {}
            for key, value in selected[0]['measures'].items():
                if isinstance(value, list):
                    groups = [[row['measures'][key][i] for row in selected] for i in range(3)]
                    result['mean'][key] = [statistics.mean(g) for g in groups]
                    result['range'][key] = [[min(g), max(g)] for g in groups]
                else:
                    values = [row['measures'][key] for row in selected]
                    result['mean'][key] = statistics.mean(values)
                    result['range'][key] = [min(values), max(values)]
        out[candidate] = result
    return out


def raw_logs(evidence, run, data):
    entries = data.get('logs')
    require(type(entries) is list and entries, 'No archived ULogs')
    seen, rows = set(), []
    for item in entries:
        path = Path(item['archive']).resolve()
        require(path.parent == run and path.suffix == '.ulg' and path not in seen,
                'Duplicate or escaped ULog archive')
        require(type(item.get('bytes')) is int and item['bytes'] > 0, 'Bad ULog byte count')
        verified = evidence.track(path)
        require(path.stat().st_size == item['bytes'] and verified['sha256'] == item['sha256'],
                'ULog bytes/SHA do not match recorded fingerprint')
        rows.append(dict(archive=str(path), source=item.get('source'), bytes=item['bytes'],
                         recorded_sha256=item['sha256'], verified_sha256=verified['sha256']))
        seen.add(path)
    require({p.resolve() for p in run.glob('*.ulg')} == seen, 'Unregistered/missing ULog archive')
    return rows


def restore(evidence, run, ledger, job):
    record = evidence.read(run/'parameter_restore.json')
    backup = Path(record['backup_path']).resolve()
    require(backup == run.parent/'original_parameters.bson', 'Foreign parameter backup')
    original = evidence.track(backup)['sha256']
    require(record.get('source_head') == ledger['source_head'] and record.get('gate') == job['gate']
            and record.get('job_id') == job['id'] and record.get('parameter_restore_exact') is True
            and record.get('stopped_before_restore') is True and record.get('remaining_simulators') == []
            and record.get('original_parameter_sha256') == original
            and record.get('restored_parameter_sha256') == original
            and ledger.get('original_parameter_sha256') == original, 'Inexact/unbound parameter restoration')
    return dict(receipt=evidence.track(run/'parameter_restore.json'), backup=evidence.track(backup),
                exact=True, scope='Recorded per-run restoration; current EEPROM is not substituted for historical evidence')


def retained_bindings(api):
    if api.REVISION == 'r03_revision05':return {'retained_a':api.retained_a()}
    if api.REVISION == 'r03_revision06':return {'retained_abc':api.retained_abc()}
    require(api.REVISION == 'r03_revision04','Unknown evidence revision')
    return {}


def qualification(evidence, root, ledger, api):
    batch = root/'batch01'
    ref = evidence.read(batch/'qualification_reference.json')
    path = Path(ref['path']).resolve()
    require(root in path.parents and path.name == 'evidence.json', 'Foreign qualification path')
    require(evidence.track(path)['sha256'] == ref['sha256'], 'Qualification reference SHA differs')
    q, receipt = evidence.read(path), evidence.read(path.parent/'authorization.json')
    expected = dict(success=True, clean=True, source_head=ledger['source_head'], gate=ledger['gate'],
                    revision=api.REVISION, stage=ledger['stage'], firmware_sha256=ledger['firmware_sha256'],
                    execution_authorized=True, flight_authorized=True, execution_ready=True,
                    maximum_attempts=9, total_maximum_attempts=api.TOTAL_MAXIMUM_ATTEMPTS,
                    new_matrix_attempts=api.NEW_MATRIX_ATTEMPTS, historical_attempts=api.HISTORICAL_ATTEMPTS,
                    new_flights=0)
    require(all(exact(q.get(k), v) for k, v in expected.items()), 'Qualification source/budget/flags mismatch')
    require(exact(evidence.read(batch/'qualification.json'), q), 'Batch qualification copy changed')
    require(receipt.get('approved') is True and receipt.get('qualification_sha256') == ref['sha256'],
            'Qualification authorization mismatch')
    for key in ('source_head', 'firmware_sha256', 'stage', 'gate', 'revision', 'execution_authorized',
                'flight_authorized', 'execution_ready', 'maximum_attempts', 'total_maximum_attempts',
                'new_matrix_attempts', 'historical_attempts', 'execution_sha256', 'frozen_sha256',
                'historical_budget', 'seed_migration'):
        require(key in q and exact(receipt.get(key), q[key]), 'Qualification receipt field changed: '+key)
    for key,expected_retained in retained_bindings(api).items():
        require(exact(q.get(key), expected_retained) and
                exact(receipt.get(key), q[key]), 'Qualification retained gate mismatch: '+key)
    files = q.get('evidence_files', {})
    require(type(files) is dict and files, 'No qualification command evidence')
    for name, sha in files.items():
        require(path.parent in Path(name).resolve().parents and evidence.track(name)['sha256'] == sha,
                'Qualification command evidence changed')
    counts = q.get('counts', {})
    require(all(type(counts.get(k)) is int and counts[k] > 0 for k in ('cpp_unique_tests', 'python_tests')),
            'Missing actual qualification test counts')
    return dict(evidence=evidence.track(path), authorization=evidence.track(path.parent/'authorization.json'),
                counts=counts, source_head=q['source_head'], firmware_sha256=q['firmware_sha256'],
                scope='Historical source-bound offline evidence; no comparison to current HEAD or current binary')


def gate_summary(api, proof, gate):
    root = (api.EXTERNAL/api.DATA_STAGE/gate).resolve()
    batch, ledger_path = root/'batch01', root/'batch01/ledger.json'
    result = dict(revision=api.REVISION, gate=gate, planned=9, status='pending', gate_passed=False,
                  attempted=None, accepted_recorded=None, failed=None, unattempted=None,
                  rows=[], algorithms=None, issues=[], inputs_unchanged=False)
    if not ledger_path.is_file():
        result['issues'].append('No ledger: actual counts unknown, not zero; future manifest rows omitted')
        return result
    evidence = Evidence()
    evidence.tree(root)
    try:
        p, ledger = api.load_protocol(gate), evidence.read(ledger_path)
        jobs = p['jobs']
        require(len(jobs) == 9, 'Wrong frozen gate size')
        expected = dict(revision=api.REVISION, gate=gate, stage=p['stage'], planned=9,
                        total_budget=api.TOTAL_MAXIMUM_ATTEMPTS, new_planned=api.NEW_MATRIX_ATTEMPTS,
                        retained_attempts=api.HISTORICAL_ATTEMPTS,
                        retained_invalid_attempts=api.retained_failure()['failed'],
                        retained_accepted_attempts=api.retained_failure()['accepted'],
                        prior_attempts=api.HISTORICAL_ATTEMPTS+9*list(api.GATES).index(gate),
                        historical_budget=api.retained_failure(), seed_migration=api.seed_migration())
        expected.update(retained_bindings(api))
        require(all(exact(ledger.get(k), v) for k, v in expected.items()), 'Ledger identity/budget changed')
        require(re.fullmatch('[0-9a-f]{40}', ledger.get('source_head', '')) and
                re.fullmatch('[0-9a-f]{64}', ledger.get('firmware_sha256', '')), 'Invalid source/binary identity')
        attempts = ledger['attempts']
        require(type(attempts) is list and len(attempts) <= 9, 'Invalid attempt count')
        require(set(batch.glob('run[0-9][0-9][0-9]')) == {batch/j['id'] for j in jobs[:len(attempts)]},
                'Orphan/missing attempt directories')
        result.update(ledger=evidence.track(ledger_path), journal=evidence.optional(batch/'journal.jsonl'),
                      attempted=len(attempts), accepted_recorded=sum(r.get('status') == 'accepted' for r in attempts),
                      failed=sum(r.get('status') == 'failed' for r in attempts), unattempted=9-len(attempts),
                      source_head=ledger['source_head'], firmware_sha256=ledger['firmware_sha256'],
                      parameter_restore_exact=ledger.get('parameter_restore_exact'),
                      remaining_simulators=ledger.get('remaining_simulators'))
        result['qualification'] = qualification(evidence, root, ledger, api)
        for i, item in enumerate(attempts):
            job, run = jobs[i], (batch/jobs[i]['id']).resolve()
            require(exact(item.get('attempt'), i+1) and exact(item.get('job'), job)
                    and Path(item['directory']).resolve() == run, 'Foreign/reordered attempt')
            row = dict(id=job['id'], candidate=job['candidate'], mode=job['mode'], axes=job['axes'],
                       seed=job['seed'], status=item.get('status'), metrics_verified=False, issues=[],
                       result=evidence.optional(run/'result.json'), metrics=evidence.optional(run/'r03_metrics.json'),
                       takeoff_command=None, airborne_task_reached=None, landed_disarmed=None, logs=[])
            result['rows'].append(row)
            try:
                require(row['result'], 'Missing result; physical outcome unknown')
                data = evidence.read(run/'result.json')
                require(data.get('source_head') == ledger['source_head'] and
                        data.get('binary_sha256') == ledger['firmware_sha256'], 'Result source/binary mismatch')
                names = {v['name'] for v in data.get('events', [])}
                row.update(takeoff_command='takeoff_command' in names,
                           airborne_task_reached=bool(names & {'handoff_ready', 'hover_start'}),
                           landed_disarmed='landed_disarmed' in names, runner_success=data.get('success'),
                           error=data.get('error'), logs=raw_logs(evidence, run, data))
                row['parameter_restore'] = restore(evidence, run, ledger, job)
                require(exact(evidence.read(run/'qualification_reference.json'),
                              evidence.read(batch/'qualification_reference.json')), 'Per-run qualification differs')
                if item.get('status') == 'accepted':
                    require(row['metrics'] and row['metrics']['sha256'] == item.get('metrics_sha256'),
                            'Accepted metrics missing/changed')
                    metrics = proof.source_metrics(item, ledger)
                    require(metrics.get('accepted') is True and exact(metrics.get('job'), job), 'Wrong accepted metrics')
                    row['measures'], row['metrics_verified'] = measures(metrics, job), True
                elif row['metrics']:
                    failed_metrics=evidence.read(run/'r03_metrics.json')
                    row['analysis_error']=failed_metrics.get('error')
                    row['original_metric_accepted']=failed_metrics.get('accepted')
                    row['issues'].append('Nonaccepted metrics excluded; original verdict retained')
            except ERRORS as exc:
                row['issues'].append(str(exc))
        rows = result['rows']
        result.update(accepted_metrics_verified=sum(r['metrics_verified'] for r in rows),
                      missing_results=sum(r['result'] is None for r in rows),
                      missing_metrics=sum(r['metrics'] is None for r in rows),
                      ulog_files_verified=sum(len(r['logs']) for r in rows), algorithms=averages(rows))
        for key in ('takeoff_command', 'airborne_task_reached', 'landed_disarmed'):
            result[key+'_count'] = None if any(r[key] is None for r in rows) else sum(r[key] for r in rows)
        pairs = ledger.get('pairs')
        result['paired_recorded'] = None if not isinstance(pairs, list) else dict(total=len(pairs),
            accepted=sum(v.get('accepted') is True for v in pairs), scope='Stored decisions only until complete proof')
        result['replay'] = evidence.optional(root/'replay01/summary.json')
        result['gate_pass'] = evidence.optional(root/'gate_pass.json')
        result['status'] = 'stopped_failed' if result['failed'] else 'pending'
        if result['gate_pass']:
            require(result['replay'], 'Gate receipt without independent replay')
            if api.REVISION in ('r03_revision05','r03_revision06'):
                previous = api.require_previous_gates(gate)  # Read-only, including original A verifier.
                q = evidence.read(Path(result['qualification']['evidence']['path']))
                require(exact(q.get('previous_gates'), previous), 'Qualification predecessor proof differs')
                result['previous_gates_verified'] = previous
            verified = proof.verify_complete(gate, root)  # Never call replay_gate/finalize/analyze.
            require(exact(evidence.read(root/'gate_pass.json'), verified), 'Gate receipt differs from original verifier')
            require(all(exact(verified.get(k), v) for k, v in dict(success=True, revision=api.REVISION,
                    gate=gate, source_head=ledger['source_head'], attempts=9, accepted=9,
                    independent_replays=9, paired_checks=6).items()), 'Incomplete gate proof')
            require(result['accepted_metrics_verified'] == 9 and not any(r['issues'] for r in rows),
                    'Incomplete per-run evidence')
            summary = evidence.read(root/'replay01/summary.json')
            for name, sha in summary['source_batch_snapshot']['files'].items():
                require(batch in Path(name).resolve().parents and evidence.track(name)['sha256'] == sha,
                        'Verified batch input changed after complete proof')
            result['independent_replay'] = dict(replayed=summary['replayed'],
                source_inputs_unchanged=summary['source_inputs_unchanged'], rows=summary['rows'],
                six_paired_decisions=ledger['pairs'], numeric_pairs_independently_recomputed=True)
            result.update(gate_passed=True, status='passed')
    except ERRORS as exc:
        result.update(status='evidence_error', gate_passed=False)
        result['issues'].append(str(exc))
    try:
        result['input_fingerprints'] = evidence.finish()
        result['inputs_unchanged'] = True
    except ERRORS as exc:
        result.update(status='changed_during_read', gate_passed=False)
        result['issues'].append(str(exc))
    return result


def summarize(api, proof, api04, proof04, api05, proof05):
    """Verify four separate complete gates, never pool partial historical batches."""
    require(api.REVISION == 'r03_revision06' and tuple(api.GATES) == ('D',)
            and api.TOTAL_MAXIMUM_ATTEMPTS == 58 and api.HISTORICAL_ATTEMPTS == 49
            and api.NEW_MATRIX_ATTEMPTS == 9, 'Wrong revision06 D-only budget')
    require(api04.REVISION == 'r03_revision04' and api05.REVISION == 'r03_revision05',
            'Wrong retained original-version verifier')
    historical=api.retained_failure()
    require(all(exact(historical.get(k),v) for k,v in
                dict(attempts=49,takeoffs=48,accepted=44,failed=5).items()),'Wrong retained history counts')
    retained=api.retained_abc()
    require(exact(retained.get('accepted_design_runs'),27) and exact(retained.get('new_attempts'),0)
            and [(p.get('gate'),p.get('revision')) for p in retained.get('gates',[])] ==
            [('A','r03_revision04'),('B','r03_revision05'),('C','r03_revision05')],
            'Wrong retained ABC identity/order or new-attempt count')
    old=[gate_summary(api04,proof04,'A'),gate_summary(api05,proof05,'B'),gate_summary(api05,proof05,'C')]
    for result,binding in zip(old,retained['gates']):
        if result['gate_passed']:
            require(result['gate_pass']['sha256']==binding['receipt_sha256']
                    and result['source_head']==binding['source_head'], 'Retained ABC fixed binding differs')
    current=gate_summary(api,proof,'D')
    require(exact(api.retained_abc(),retained) and exact(api.retained_failure(),historical),
            'Retained evidence changed while reading')
    complete=all(item['gate_passed'] for item in [*old,current])
    used=current['attempted']
    cumulative=dict(attempts=None if used is None else 49+used,
        takeoff_commands=None if current.get('takeoff_command_count') is None else 48+current['takeoff_command_count'],
        accepted=None if current['accepted_recorded'] is None else 44+current['accepted_recorded'],
        failed=None if current['failed'] is None else 5+current['failed'],
        unused_budget=None if used is None else 9-used,
        interpretation='Historical accounting only; not the scientific four-gate sample size')
    return dict(revision=api.REVISION,stage='Read-only four-gate R03 result index',
        generated_utc=datetime.now(timezone.utc).isoformat(),
        tool=dict(path=str(Path(__file__).resolve()),sha256=digest(__file__)),
        total_budget=58,new_matrix_planned=9,
        historical=dict(attempts=49,takeoffs=48,accepted=44,failed=5,pooled_into_new_results=False),
        retained_abc=old,gates=[current],cumulative=cumulative,
        accepted_design=dict(planned=36,retained_complete_gate_runs=27,new_d_planned=9,
            verified_runs=sum(item.get('accepted_metrics_verified',0) for item in [*old,current]),
            interpretation='A04/B05/C05/D06 stay separate; per algorithm per gate planned n=3'),
        requested_scope_verified=complete,all_r03_gates_verified=complete,
        definitions=dict(rmse='Time-weighted consumed velocity error per axis, m/s; frozen main window',
            J='Arithmetic mean of three per-axis RMSEs; run metrics averaged descriptively',
            tv='Actual-update correction / total acceleration / normalized thrust kept separate; not energy',
            tv_units='Acceleration TV m/s^2; TV/T m/s^3. Normalized thrust TV dimensionless; TV/T 1/s',
            missing='Unknown stays null; failed/missing not filled with zero; no old runs fill new D',
            takeoffs='Command, airborne-task and landed-disarmed events separate; command is not proof of lift-off'),
        limitations=['Per-algorithm planned n=3 development samples, not significance or universal superiority',
            'Only observed attempts serialized; only accepted independently bound metrics enter means',
            'Partial accepted means may have selection bias; different gates and source revisions not pooled',
            'Retained A/B/C use their original source and checkers; historical D failure is not regraded',
            'Raw hashes and existing complete replay proofs checked; no decoding, flight, or new gate receipt',
            'Summary has no execution authority; host cost is not board CPU and TV is not energy'])


def write_fresh(directory, value, api):
    path = Path(directory).resolve()
    allowed = api.EXTERNAL.resolve()/'R03_revision06_summaries'
    require(not allowed.is_symlink() and allowed.resolve() == allowed,
            'Dedicated summary root must not be a symbolic-link alias')
    require(allowed in path.parents and path != allowed, 'Output must be a fresh child of R03_revision06_summaries')
    require(api.REPO.resolve() not in path.parents, 'Output cannot be in repository')
    path.mkdir(parents=True, exist_ok=False)
    with (path/'summary.json').open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=REPO)
    parser.add_argument('--output',type=Path,help='Fresh dedicated external output; omit for stdout only')
    args=parser.parse_args();base=args.repo.resolve()/REGULARIZED
    paths=[(revision,leaf,base/revision/(leaf+'.py')) for revision in
           ('r03_revision06','r03_revision04','r03_revision05') for leaf in ('protocol','replay')]
    before={str(path):digest(path) for _,_,path in paths}
    readers=[load('_summary_'+revision+'_'+leaf,path) for revision,leaf,path in paths]
    value=summarize(*readers)
    require(all(digest(path)==sha for path,sha in before.items()),'Reader source changed during summary')
    value['reader_sources']=before
    if args.output:write_fresh(args.output,value,readers[0])
    print(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False))
    return 0 if value['all_r03_gates_verified'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
