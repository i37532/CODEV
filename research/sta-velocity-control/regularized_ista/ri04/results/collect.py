#!/usr/bin/env python3
"""Collect the stopped RI04 batch without granting acceptance or filling data.

Only result-layer artifacts are written. Frozen inputs, original metrics and
failed logs remain byte-identical. A successful collection is NOT a passed gate.
"""
import argparse
import importlib.util
import json
from pathlib import Path

import replay_stopped

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI04')
BATCH = ROOT / 'B/batch01'
REPLAY = ROOT / 'B/replay_stopped01'
SOURCE = replay_stopped.SOURCE_HEAD
spec = importlib.util.spec_from_file_location('ri03_result_serialization',
    HERE.parents[1] / 'ri03/results/collect.py')
view = importlib.util.module_from_spec(spec)
spec.loader.exec_module(view)


def require(value, message):
    if not value:
        raise ValueError(message)


def validate_replay(ledger, repeated):
    require(repeated.get('success') is True and repeated.get('stage_accepted') is False
            and repeated.get('gate_pass_generated') is False and repeated.get('gate_pass_absent') is True,
            'Replay cannot grant RI04 acceptance')
    require(repeated.get('source_head') == SOURCE and repeated.get('replayed') == 2
            and repeated.get('pair_count') == 1 and repeated.get('new_flights') == 0,
            'Replay scope differs')
    require(repeated.get('source_inputs_unchanged') is True
            and repeated['original_input_sha256_before'] == repeated['original_input_sha256_after'],
            'Replay changed original input')
    require(len(repeated.get('commands', [])) == 2
            and all(c['exit_code'] == 0 for c in repeated['commands']), 'Replay subprocess failed/missing')
    require(view.exact([repeated['single_pair']], ledger['pairs']), 'Pair changed')


def validate_replay_files(repeated):
    require(repeated['result_script_sha256'] == view.digest(HERE / 'replay_stopped.py'), 'Replay script changed')
    for command, run_id in zip(repeated['commands'], ('run001', 'run002')):
        expected_tail = ['-B', str(HERE.parent / 'tools/analyzer.py'), str(BATCH / run_id),
                         '--output', str(REPLAY / run_id)]
        require(len(command['argv']) == 6 and Path(command['argv'][0]).name in ('python3', 'python3.10')
                and command['argv'][1:] == expected_tail
                and Path(command['cwd']) == replay_stopped.bindings.REPO, 'Replay command/output differs')
        log = REPLAY / (run_id + '.log')
        require(command['log'] == str(log) and command['log_sha256'] == view.digest(log), 'Replay log changed')


def validate_failure_audit(audit, result, raw):
    for key in ('success', 'audit_completed', 'source_inputs_unchanged', 'airborne_confirmed',
                'original_failure_preserved'):
        require(audit.get(key) is True, 'Missing failure-audit confirmation ' + key)
    for key in ('stage_accepted', 'flight_accepted'):
        require(audit.get(key) is False, 'Failure audit cannot grant acceptance')
    for key in ('new_flights', 'retries', 'budget_added'):
        require(type(audit.get(key)) is int and audit[key] == 0, 'Audit scope changed')
    require(audit.get('source_head') == SOURCE and view.exact(audit.get('original_result'), result),
            'Failure audit source/result differs')
    require(result.get('success') is False and audit['main_task']['started'] is False,
            'Failed/missing task was relabelled')
    preservation = audit['preservation']
    require(preservation['identical'] is True and preservation['before'] == preservation['after']
            and preservation['decoded_ulog_count'] == preservation['original_ulog_count'] == 2,
            'Failure audit missing full two-log preservation')
    require(len(raw) == 2 and set(audit['raw_ulog_fingerprints']) == set(raw), 'Wrong failed raw logs')
    for path, value in raw.items():
        expected = dict(type='regular', bytes=value['bytes'], sha256=value['sha256'])
        require(view.exact(audit['raw_ulog_fingerprints'][path], dict(before=expected, after=expected))
                and view.exact(preservation['after'][Path(path).name], expected), 'Failure raw fingerprint differs')


def outcomes(jobs, attempts, runs):
    require(len(jobs) == 9 and len(attempts) == 3 and len(runs) == 3, 'Stopped matrix shape changed')
    rows = []
    for index, job in enumerate(jobs):
        row = dict(id=job['id'], seed=job['seed'], candidate=job['candidate'], mode=job['mode'], axes=job['axes'])
        if index < 3:
            require(view.exact(attempts[index]['job'], job) and runs[index]['id'] == job['id'], 'Order changed')
            row.update(status=attempts[index]['status'], attempted=True,
                       airborne=runs[index]['airborne'], accepted=runs[index]['accepted'],
                       metrics_available=runs[index]['accepted'])
        else:
            row.update(status='unattempted', attempted=False, airborne=False, accepted=False,
                       metrics_available=False, missing_reason='Stopped at first mandatory failure, run003')
        rows.append(row)
    return rows


def collect():
    protocol = replay_stopped.bindings.api().load_protocol('B')
    ledger = view.read(BATCH / 'ledger.json')
    repeated = view.read(REPLAY / 'summary.json')
    replay_stopped.validate_stopped(ledger, protocol)
    validate_replay(ledger, repeated)
    validate_replay_files(repeated)
    require(repeated['ledger_sha256'] == view.digest(BATCH / 'ledger.json'), 'Ledger changed after replay')
    require(replay_stopped.replay.snapshot(BATCH) == repeated['original_input_sha256_after'],
            'Original batch changed since replay')
    require(not (ROOT / 'B/gate_pass.json').exists(), 'Stopped batch cannot have gate_pass')
    qpath = ROOT / 'B/qualification01/evidence.json'
    qualified = replay_stopped.bindings.api().archive_qualification('B', SOURCE, qpath)
    require(qualified['firmware_sha256'] == ledger['firmware_sha256'], 'Wrong original firmware')
    runs, logs, metrics_by_id = [], [], {}
    for index, item in enumerate(ledger['attempts']):
        run = Path(item['directory'])
        result = view.read(run / 'result.json')
        restore = view.read(run / 'parameter_restore.json')
        accepted = index < 2
        require(result['source_head'] == SOURCE and result['binary_sha256'] == ledger['firmware_sha256'],
                'Wrong run source/binary')
        require(result['success'] is accepted, 'Original run status changed')
        require(restore['parameter_restore_exact'] is True and restore['remaining_simulators'] == []
                and restore['stopped_before_restore'] is True
                and restore['restored_parameter_sha256'] == ledger['original_parameter_sha256'],
                'Missing exact restoration/cleanup')
        events = {e['name'] for e in result['events']}
        require('takeoff_command' in events, 'Missing takeoff command')
        row = dict(id=run.name, candidate=item['job']['candidate'], seed=item['job']['seed'],
            attempted=True, airborne=True, accepted=accepted,
            result=view.ref(run / 'result.json'), parameter_restore=view.ref(run / 'parameter_restore.json'))
        if accepted:
            require({'hover_start', 'hover_end', 'landed_disarmed'} <= events, 'Accepted run incomplete')
            metrics = view.read(run / 'r03_metrics.json')
            require(metrics['accepted'] and view.digest(run / 'r03_metrics.json') == item['metrics_sha256']
                    and view.exact(metrics, view.read(REPLAY / run.name / 'r03_metrics.json')),
                    'Metrics mismatch')
            require(view.digest(run / 'spectra.json') == view.digest(REPLAY / run.name / 'spectra.json'),
                    'Spectra mismatch')
            view.check_nonfinite(metrics, diagnostic=True)
            row.update(metrics=metrics, metrics_file=view.ref(run / 'r03_metrics.json'),
                       spectra=view.ref(run / 'spectra.json'))
            metrics_by_id[run.name] = metrics
        else:
            require(result['error'] == "RuntimeError('First update/retry failure')"
                    and not ({'hover_start', 'hover_end', 'landed_disarmed'} & events),
                    'Failure identity/stage differs')
            require(not (run / 'r03_metrics.json').exists(), 'Failed run must not get accepted metrics')
            # A takeoff command alone is insufficient: the ULog audit below
            # independently proves landed=false, contact=false and Z takeover.
            row.update(missing_metrics_reason='Mandatory fault during takeoff; no main task window',
                       error=result['error'], airborne_evidence='failure_audit01/summary.json')
        for log in result['logs']:
            actual = view.ref(Path(log['archive']))
            require(actual['sha256'] == log['sha256'] and actual['bytes'] == log['bytes']
                    and log['durable_copy_verified'] is True, 'Raw ULog fingerprint mismatch')
            logs.append(dict(job_id=run.name, **actual))
        runs.append(row)
    pair = replay_stopped.single_pair(ledger, metrics_by_id)
    audit_path = ROOT / 'failure_audit01/summary.json'
    require(audit_path.is_file(), 'Failure audit evidence is required, not guessed')
    audit = view.read(audit_path)
    validate_failure_audit(audit, view.read(BATCH / 'run003/result.json'),
                          {item['path']: item for item in logs if item['job_id'] == 'run003'})
    require(audit['execution']['exit_code'] == 0
            and audit['execution']['script_sha256'] == view.digest(HERE / 'audit_failure.py')
            and audit['tests']['exit_code'] == 0 and audit['tests']['tests_executed'] == 8
            and audit['tests']['script_sha256'] == view.digest(HERE / 'test_failure_audit.py')
            and audit['tests']['log_sha256'] == view.digest(Path(audit['tests']['log_path'])),
            'Failure audit/test receipt changed')
    summary = dict(stage='RI04', status='failed/needs_revision', accepted=False,
        source_head=SOURCE, firmware_sha256=ledger['firmware_sha256'],
        budget=dict(planned=9, attempted=3, airborne=3, accepted=2, failed=1, unattempted=6,
                    missing_main_metrics=7, completed_landing=2, retries=0, replacements=0),
        independent_accepted_replays=2, required_independent_accepted_replays=9,
        paired_risk_checks=1, required_paired_risk_checks=6, paired_individual_checks=13,
        parameter_restore_exact=True, remaining_simulators=[],
        qualification=view.ref(qpath), qualification_counts=qualified['counts'],
        ledger=view.ref(BATCH / 'ledger.json'), replay=view.ref(REPLAY / 'summary.json'),
        failure_audit=view.ref(audit_path), existing_pair=pair,
        outcomes=outcomes(protocol['jobs'], ledger['attempts'], runs), runs=runs,
        interpretation=['Only one PID/R-STA pair has complete task metrics; no R-ISTA performance estimate',
            'No zero filling, significance claim, gate_pass or permission to resume the six stopped jobs',
            'Accepted-run replay success and offline tests do not mean RI04 flight acceptance',
            'Z velocity tracking and deviation from nominal 2.5m height use distinct metrics/windows',
            'TV is not energy; host wall-clock is not board CPU/WCET; MATLAB was not rerun'])
    view.save(HERE / 'summary.json', summary)
    view.save(HERE / 'ulog_index.json', dict(log_count=len(logs), files=logs))
    require(replay_stopped.replay.snapshot(BATCH) == repeated['original_input_sha256_after'],
            'Collection changed original batch')
    print(json.dumps(dict(stage_status=summary['status'], budget=summary['budget'], logs=len(logs))))


def archive():
    # Run after all offline evidence has settled. Refuse an altered rerun;
    # this index intentionally excludes only itself, never any failed log.
    destination = ROOT / 'archive_index.json'
    files, links = [], {}
    for path in sorted(ROOT.rglob('*')):
        if path == destination:
            continue
        if path.is_symlink():
            links[str(path)] = str(path.readlink())
        elif path.is_file():
            files.append(view.ref(path))
    view.save(destination, dict(scope=str(ROOT), files=files, symlinks=links,
        excludes=['archive_index.json (self)'], preserved_failures=True))
    view.save(HERE / 'archive_reference.json', dict(**view.ref(destination),
        file_count=len(files), symlink_count=len(links)))
    print(json.dumps(dict(archive_files=len(files), symlinks=len(links))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', action='store_true', help='Freeze evidence index after collection and tests')
    args = parser.parse_args()
    archive() if args.archive else collect()
