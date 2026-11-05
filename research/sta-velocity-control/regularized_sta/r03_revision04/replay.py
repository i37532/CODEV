#!/usr/bin/env python3
"""Independent R03 revision04 nine-run reanalysis; old failures remain invalid. Never flies or rewrites original inputs.

Each analyzer runs in a separate process and reads the original archived ULogs.
The output directory must be fresh. A successful gate_pass.json is written only
with --finalize, after rechecking all nine actual outputs and all six paired
decisions; it cannot be issued from an arbitrary caller-supplied success flag.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('r03_revision04_replay_protocol', HERE/'protocol.py')
protocol = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(protocol)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            result.update(block)
    return result.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
        stream.flush(); os.fsync(stream.fileno())


def exact(a, b):
    """Ignore dictionary key order only, not numeric type, precision or sign."""
    return json.dumps(a, sort_keys=True, separators=(',', ':'), ensure_ascii=False) == \
           json.dumps(b, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def compare_metrics(original, replayed):
    a, b = json.loads(original), json.loads(replayed)
    require(a.get('accepted') is True and b.get('accepted') is True, 'Unaccepted metric payload')
    require(exact(a, b), 'Replay metric content changed; no numerical normalization permitted')
    return dict(numeric_equal=True, bytes_identical=original == replayed,
                representation_only=original != replayed,
                comparison='All JSON values/types/list order exact; dictionary key order/whitespace ignored')


def tree_snapshot(root):
    root = Path(root).resolve()
    require(root.is_dir(), 'Missing input directory '+str(root))
    # rglob does not traverse directory symlinks. Record symlink targets too so
    # a model-link replacement is not hidden by unchanged neighboring files.
    files, links = {}, {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            links[str(path)] = os.readlink(path)
            require(path.exists(), 'Broken input link '+str(path))
        if path.is_file():
            files[str(path)] = digest(path)
    return dict(files=files, links=links)


def raw_snapshot(run):
    """Bind every source file and every explicitly archived startup/flight log."""
    run = Path(run).resolve()
    result = read(run/'result.json')
    logs = result.get('logs', [])
    require(isinstance(logs, list) and len(logs) > 0, 'Missing archived ULog inputs')
    seen = set()
    for entry in logs:
        path = Path(entry['archive']).resolve()
        require(path.parent == run and path.suffix == '.ulg' and path not in seen,
                'Wrong/duplicate archived ULog path')
        require(type(entry.get('bytes')) is int and entry['bytes'] > 0,
                'Invalid archived ULog byte count')
        require(path.stat().st_size == entry['bytes'] and digest(path) == entry.get('sha256'),
                'Archived ULog bytes or SHA changed')
        seen.add(path)
    require({path.resolve() for path in run.glob('*.ulg')} == seen, 'Unregistered/missing archived ULog')
    return tree_snapshot(run)


def validate_ledger(ledger, jobs, batch):
    """Validate actual identities and decisions, never only aggregate counts."""
    batch = Path(batch).resolve()
    require(len(jobs) == 9 and len({j['gate'] for j in jobs}) == 1
            and all(job.get('revision') == protocol.REVISION for job in jobs), 'Wrong revision/gate jobs')
    gate = jobs[0]['gate']
    require(gate in protocol.GATES, 'Unknown gate')
    historical = protocol.retained_failure()
    require(ledger.get('success') is True and ledger.get('stage') == 'R03-revision04-'+gate
            and ledger.get('revision') == protocol.REVISION
            and ledger.get('gate') == gate and type(ledger.get('planned')) is int and ledger['planned'] == 9
            and type(ledger.get('total_budget')) is int and ledger['total_budget'] == protocol.TOTAL_MAXIMUM_ATTEMPTS
            and type(ledger.get('retained_invalid_attempts')) is int
            and ledger['retained_invalid_attempts'] == historical['failed']
            and type(ledger.get('retained_accepted_attempts')) is int
            and ledger['retained_accepted_attempts'] == historical['accepted']
            and type(ledger.get('retained_attempts')) is int
            and ledger['retained_attempts'] == protocol.HISTORICAL_ATTEMPTS
            and type(ledger.get('new_planned')) is int and ledger['new_planned'] == protocol.NEW_MATRIX_ATTEMPTS
            and type(ledger.get('prior_attempts')) is int
            and ledger['prior_attempts'] == protocol.HISTORICAL_ATTEMPTS+9*list(protocol.GATES).index(gate)
            and exact(ledger.get('historical_budget'), historical)
            and exact(ledger.get('seed_migration'),protocol.seed_migration()),
            'Not a completed nine-run gate')
    require(ledger.get('parameter_restore_exact') is True and ledger.get('remaining_simulators') == []
            and ledger.get('unattempted') == [], 'Incomplete cleanup or remaining attempts')
    require(re.fullmatch('[0-9a-f]{40}', ledger.get('source_head', '')) is not None
            and re.fullmatch('[0-9a-f]{64}', ledger.get('firmware_sha256', '')) is not None,
            'Missing gate source/firmware identity')
    attempts = ledger.get('attempts', [])
    require(len(attempts) == 9, 'Incomplete attempts')
    for index, (item, job) in enumerate(zip(attempts, jobs), 1):
        require(type(item.get('attempt')) is int and item['attempt'] == index and exact(item.get('job'), job)
                and item.get('status') == 'accepted', 'Changed/reordered/failed attempt')
        require(Path(item['directory']).resolve() == batch/job['id'], 'Attempt directory escapes exact job')
        require(re.fullmatch('[0-9a-f]{64}', item.get('metrics_sha256', '')) is not None, 'Missing source metrics SHA')
    expected = sorted((j['seed'], gate, j['candidate']) for j in jobs if j['mode'])
    pairs = ledger.get('pairs', [])
    required_checks = {'yaw'} | {prefix+str(i) for prefix in
        ('velocity_', 'position_', 'first_half_velocity_', 'second_half_velocity_') for i in range(3)}
    require(len(pairs) == 6, 'Missing paired decisions')
    identities = []
    for pair in pairs:
        require(type(pair.get('seed')) is int and pair.get('accepted') is True
                and set(pair.get('checks', {})) == required_checks
                and all(value is True for value in pair['checks'].values()), 'Failed/incomplete paired decision')
        identities.append((pair['seed'], pair.get('gate'), pair.get('candidate')))
    require(sorted(identities) == expected, 'Duplicated/wrong seed/gate/algorithm pair')
    return True


def source_metrics(item, ledger):
    run = Path(item['directory']).resolve()
    require(digest(run/'r03_metrics.json') == item['metrics_sha256'], 'Original metrics SHA changed')
    metrics, result = read(run/'r03_metrics.json'), read(run/'result.json')
    require(metrics.get('accepted') is True and exact(metrics.get('job'), item['job']), 'Original metrics/job not accepted')
    preparation = metrics.get('prearm_preparation', {})
    require(preparation.get('valid') is True and preparation.get('receipt_sha256') ==
            digest(run/'r03_prearm04_timing.jsonl'), 'Original prearm preparation receipt changed or missing')
    require(exact(read(run/'job.json'), item['job']), 'Original job file changed')
    require(result.get('success') is True and result.get('source_head') == ledger['source_head']
            and result.get('binary_sha256') == ledger['firmware_sha256'], 'Original result/source/firmware differs')
    binding = metrics.get('binding', {})
    require(binding.get('source_head') == ledger['source_head']
            and binding.get('firmware_sha256') == ledger['firmware_sha256']
            and binding.get('gate') == ledger['gate'] and binding.get('stage') == ledger['stage']
            and binding.get('revision') == protocol.REVISION
            and exact(binding.get('historical_budget'),ledger['historical_budget'])
            and exact(binding.get('seed_migration'),ledger['seed_migration']),
            'Original metric qualification binding differs')
    for key, expected in (('maximum_attempts',9), ('total_maximum_attempts',protocol.TOTAL_MAXIMUM_ATTEMPTS),
                          ('new_matrix_attempts',protocol.NEW_MATRIX_ATTEMPTS),
                          ('historical_attempts',protocol.HISTORICAL_ATTEMPTS)):
        require(type(binding.get(key)) is int and binding[key] == expected,
                'Original metric budget binding differs: '+key)
    return metrics


def paired_decision(pid, candidate):
    """Independently evaluate the frozen risk inequalities from numeric metrics.

    This does not import analyzer.compare or trust its stored acceptance flags.
    Both complete-window and predeclared half-window RMSEs must pass. These are
    development-risk ceilings, not a requirement that either STA beats PID.
    """
    require(pid.get('accepted') is True and candidate.get('accepted') is True,
            'Unaccepted paired metrics')
    a, b = pid['job'], candidate['job']
    require(a.get('revision') == protocol.REVISION and b.get('revision') == protocol.REVISION
            and type(a.get('mode')) is int and a['mode'] == 0
            and type(b.get('mode')) is int and b['mode'] in (1, 3)
            and type(a.get('seed')) is int and a['seed'] > 0
            and all(exact(a.get(k), b.get(k)) for k in
                    ('seed', 'gate', 'task', 'divisor', 'main_duration_s')),
            'Wrong paired algorithm/seed/task')
    require(pid.get('binding',{}).get('revision') == protocol.REVISION
            and exact(pid.get('binding'), candidate.get('binding')), 'Different paired evidence binding')
    omitted = {'MPC_VC_MODE', 'MPC_VC_AXES'}
    require(exact({k:v for k,v in a['parameters'].items() if k not in omitted},
                  {k:v for k,v in b['parameters'].items() if k not in omitted}),
            'Different paired fixed parameters')

    def scalar(value):
        require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
                'Invalid paired nonnegative finite metric')
        return value

    def vector(values):
        require(isinstance(values, list) and len(values) == 3, 'Missing three-axis paired metric')
        return [scalar(value) for value in values]

    checks = {}
    pv = vector(pid['diagnostic']['error']['rmse'])
    cv = vector(candidate['diagnostic']['error']['rmse'])
    pp, cp = vector(pid['position_rmse']), vector(candidate['position_rmse'])
    for axis, allowance in enumerate((.02, .02, .01)):
        checks['velocity_'+str(axis)] = cv[axis] <= 1.25*pv[axis]+allowance
        checks['position_'+str(axis)] = cp[axis] <= 1.25*pp[axis]+.05
    for window in ('first_half', 'second_half'):
        pv = vector(pid['diagnostic']['windows'][window]['error']['rmse'])
        cv = vector(candidate['diagnostic']['windows'][window]['error']['rmse'])
        for axis, allowance in enumerate((.02, .02, .01)):
            checks[window+'_velocity_'+str(axis)] = cv[axis] <= 1.25*pv[axis]+allowance
    checks['yaw'] = scalar(candidate['yaw_rmse']) <= 1.25*scalar(pid['yaw_rmse'])+.02
    return dict(accepted=all(checks.values()), checks=checks, seed=a['seed'], gate=a['gate'],
                candidate=b['candidate'],
                criterion='Inherited development risk, not a requirement to beat PID or ESTA')


def recompute_pairs(ledger, metrics_by_id):
    """Recompute six ordered decisions from the independently repeated metrics."""
    jobs = [item['job'] for item in ledger['attempts']]
    require(set(metrics_by_id) == {job['id'] for job in jobs}, 'Missing replayed pair member')
    blocks = {}
    for job in jobs:
        value = metrics_by_id[job['id']]
        require(exact(value.get('job'), job), 'Replayed paired job differs')
        block = blocks.setdefault(job['seed'], {})
        require(job['mode'] not in block, 'Duplicate paired mode')
        block[job['mode']] = value
    decisions = []
    for job in jobs:
        if job['mode']:
            decision = paired_decision(blocks[job['seed']][0], blocks[job['seed']][job['mode']])
            require(decision['accepted'] is True, 'Recomputed paired risk threshold failed '+job['id'])
            decisions.append(decision)
    require(len(decisions) == 6 and exact(decisions, ledger['pairs']),
            'Stored paired decisions differ from numeric recomputation')
    return decisions


def verify_complete(gate, root=None):
    """Read and independently recheck completed evidence without issuing receipt."""
    protocol.require_execution_authority(gate)
    p = protocol.load_protocol(gate)
    expected_root = (protocol.EXTERNAL/protocol.DATA_STAGE/gate).resolve()
    root = expected_root if root is None else Path(root).resolve()
    require(root == expected_root, 'Wrong frozen gate evidence root')
    batch, replay = root/'batch01', root/'replay01'
    ledger, summary = read(batch/'ledger.json'), read(replay/'summary.json')
    validate_ledger(ledger, p['jobs'], batch)
    require(summary.get('success') is True and summary.get('source_inputs_unchanged') is True
            and summary.get('revision') == protocol.REVISION and summary.get('stage') == ledger['stage']
            and summary.get('gate') == gate and summary.get('source_head') == ledger['source_head']
            and type(summary.get('replayed')) is int and summary['replayed'] == 9
            and summary.get('new_flights') == 0 and type(summary.get('new_flights')) is int,
            'Independent replay incomplete')
    for key in ('total_budget','retained_invalid_attempts','retained_accepted_attempts','retained_attempts','new_planned','prior_attempts','historical_budget','seed_migration'):
        require(exact(summary.get(key),ledger[key]), 'Replay budget/retained history binding changed: '+key)
    require(summary.get('ledger_sha256') == digest(batch/'ledger.json'), 'Replay ledger binding changed')
    require(summary.get('source_batch_snapshot') == tree_snapshot(batch), 'Source batch changed after replay')
    rows = summary.get('rows', [])
    require(len(rows) == 9, 'Missing independent replay rows')
    files = {str(batch/'ledger.json'): digest(batch/'ledger.json'), str(replay/'summary.json'): digest(replay/'summary.json')}
    repeated_metrics = {}
    for item, row in zip(ledger['attempts'], rows):
        run, dest = Path(item['directory']).resolve(), replay/item['job']['id']
        require(row.get('id') == item['job']['id'] and row.get('source_directory') == str(run)
                and row.get('replay_directory') == str(dest) and row.get('accepted') is True
                and row.get('numeric_equal') is True and type(row.get('exit_code')) is int and row['exit_code'] == 0,
                'Wrong/incomplete replay identity or process result')
        source_metrics(item, ledger)
        snapshot = raw_snapshot(run)
        require(row.get('input_files') == snapshot['files'] and row.get('input_links') == snapshot['links'],
                'Replay source input inventory changed/incomplete')
        original, repeated = run/'r03_metrics.json', dest/'r03_metrics.json'
        require(row.get('source_metrics_sha256') == digest(original)
                and row.get('replay_metrics_sha256') == digest(repeated), 'Replay metrics SHA changed')
        compare_metrics(original.read_bytes(), repeated.read_bytes())
        repeated_metrics[item['job']['id']] = read(repeated)
        require(digest(run/'spectra.json') == digest(dest/'spectra.json') == row.get('spectra_sha256'),
                'Replay spectrum changed')
        command = [sys.executable, str(HERE/'analyzer.py'), str(run), '--output', str(dest)]
        require(row.get('argv') == command, 'Wrong independent analyzer command')
        command_log = replay/(item['job']['id']+'.log')
        require(row.get('command_log_sha256') == digest(command_log), 'Independent analyzer log changed')
        for path in (original, repeated, run/'spectra.json', dest/'spectra.json', command_log):
            files[str(path)] = digest(path)
    recompute_pairs(ledger, repeated_metrics)
    historical = protocol.retained_failure()
    for previous in historical['batches']:
        files[previous['ledger_path']] = previous['ledger_sha256']
        files[previous['journal_path']] = previous['journal_sha256']
        files.update(previous.get('evidence_files', {}))
    return dict(success=True, revision=protocol.REVISION, stage=ledger['stage'], gate=gate,
                source_head=ledger['source_head'], planned=9, attempts=9, accepted=9,
                independent_replays=9, paired_checks=6, files=files,
                total_budget=protocol.TOTAL_MAXIMUM_ATTEMPTS,
                retained_invalid_attempts=historical['failed'],retained_accepted_attempts=historical['accepted'],
                retained_attempts=protocol.HISTORICAL_ATTEMPTS,
                new_planned=protocol.NEW_MATRIX_ATTEMPTS,prior_attempts=ledger['prior_attempts'],
                historical_budget=historical,seed_migration=protocol.seed_migration())


def finalize(gate):
    protocol.require_execution_authority(gate)
    root = (protocol.EXTERNAL/protocol.DATA_STAGE/gate).resolve()
    require(not (root/'gate_pass.json').exists(), 'Refuse to replace gate-pass receipt')
    receipt = verify_complete(gate, root)
    save_new(root/'gate_pass.json', receipt)
    return receipt


def replay_gate(gate, output, finalize_after=False):
    protocol.require_execution_authority(gate)
    p = protocol.load_protocol(gate)
    root = (protocol.EXTERNAL/protocol.DATA_STAGE/gate).resolve()
    batch, output = root/'batch01', Path(output).resolve()
    require(output == root/'replay01' and not output.exists(), 'Fresh exact replay01 output required')
    ledger = read(batch/'ledger.json')
    validate_ledger(ledger, p['jobs'], batch)
    snapshot = tree_snapshot(batch)
    output.mkdir(parents=True, exist_ok=False)
    evidence = dict(stage='R03-revision04-'+gate, revision=protocol.REVISION, gate=gate,
                    source_head=ledger['source_head'], success=False,
                    new_flights=0, replayed=0, rows=[], ledger_sha256=digest(batch/'ledger.json'),
                    source_batch_snapshot=snapshot, source_inputs_unchanged=False,
                    analyzer_sha256=digest(HERE/'analyzer.py'), replay_tool_sha256=digest(__file__),
                    **{key:ledger[key] for key in
                       ('total_budget','retained_invalid_attempts','retained_accepted_attempts','retained_attempts','new_planned','prior_attempts','historical_budget','seed_migration')})
    env = os.environ.copy()
    env['PYTHONPATH'] = ':'.join([str(protocol.REPO/'.px4-python'),
        str(protocol.REPO/'research/sta-velocity-control/scripts'),
        '/home/yr/Desktop/codev doc/experiments/M00-20260912/python', env.get('PYTHONPATH','')])
    repeated_metrics = {}
    try:
        for item in ledger['attempts']:
            run = Path(item['directory']).resolve(); dest = output/item['job']['id']
            source_metrics(item, ledger); before = raw_snapshot(run)
            argv = [sys.executable, str(HERE/'analyzer.py'), str(run), '--output', str(dest)]
            row = dict(id=item['job']['id'], source_directory=str(run), replay_directory=str(dest),
                       accepted=False, numeric_equal=False, argv=argv, input_files=before['files'],
                       input_links=before['links'], source_metrics_sha256=digest(run/'r03_metrics.json'))
            evidence['rows'].append(row)
            started = time.monotonic(); log = output/(item['job']['id']+'.log')
            try:
                with log.open('x') as stream:
                    try:
                        completed = subprocess.run(argv, cwd=protocol.REPO, env=env, stdout=stream,
                                                   stderr=subprocess.STDOUT, timeout=300)
                        row['exit_code'] = completed.returncode
                    except subprocess.TimeoutExpired:
                        row['exit_code'] = 124
                row['command_log_sha256'] = digest(log)
                require(row['exit_code'] == 0, 'Independent analyzer rejected '+item['job']['id'])
                row.update(compare_metrics((run/'r03_metrics.json').read_bytes(), (dest/'r03_metrics.json').read_bytes()))
                row['replay_metrics_sha256'] = digest(dest/'r03_metrics.json')
                row['spectra_sha256'] = digest(run/'spectra.json')
                require(digest(dest/'spectra.json') == row['spectra_sha256'], 'Independent spectrum differs')
            finally:
                row['wall_seconds'] = time.monotonic()-started
                row['source_inputs_unchanged'] = raw_snapshot(run) == before
                require(row['source_inputs_unchanged'], 'Original input changed during independent replay')
            row['accepted'] = True; evidence['replayed'] += 1
            repeated_metrics[item['job']['id']] = read(dest/'r03_metrics.json')
            print(json.dumps(dict(id=row['id'], exit_code=row['exit_code'], numeric_equal=row['numeric_equal'])), flush=True)
        require(evidence['replayed'] == 9, 'Incomplete independent replays')
        recompute_pairs(ledger, repeated_metrics)
        require(digest(HERE/'analyzer.py') == evidence['analyzer_sha256'] and digest(__file__) == evidence['replay_tool_sha256'],
                'Replay/analyzer source changed during execution')
        evidence['success'] = True
    except BaseException as exc:
        evidence.update(success=False, error=repr(exc), traceback=traceback.format_exc())
        raise
    finally:
        try:
            evidence['source_inputs_unchanged'] = tree_snapshot(batch) == snapshot
        except Exception as exc:
            evidence['source_inputs_unchanged'] = False
            evidence['source_snapshot_error'] = repr(exc)
        if not evidence['source_inputs_unchanged']:
            evidence['success'] = False
        save_new(output/'summary.json', evidence)
    require(evidence['success'], 'Replay source inputs changed; retain failed evidence')
    verify_complete(gate, root)
    if finalize_after:
        finalize(gate)
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gate', choices=protocol.GATES, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--finalize', action='store_true')
    args = parser.parse_args()
    replay_gate(args.gate, args.output, args.finalize)
