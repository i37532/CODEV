#!/usr/bin/env python3
"""Freeze a qualified eight-attempt manifest without changing gains or firmware."""
import argparse
import copy
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from prepare import HERE, LABELS, RUNTIME, SOURCE, draft, sha256
from heading_check import POLICY, STRICT, REPUBLICATION_EVENTS

HEADING_REVISION = 'heading_alignment_v1'
DIAGNOSTIC_REVISION = 'diagnostic_wiring_v1'
FINAL_CAPTURE_REVISION = 'event_landing_capture_v1'


def revision_lineage(data_root, previous_manifest):
    """Close the one-attempt failed batch; no old successes enter new samples."""
    path = Path(previous_manifest).resolve()
    old = json.loads(path.read_text())
    old_root, new_root = Path(old['data_root']).resolve(), Path(data_root).resolve()
    if old_root == new_root or old_root.is_relative_to(new_root) or new_root.is_relative_to(old_root):
        raise ValueError('New batch must use a separate nonoverlapping data tree')
    attempts = sorted(p for p in (old_root / 'runs').iterdir() if p.is_dir())
    if old.get('max_attempts') != 8 or [p.name for p in attempts] != ['O001']:
        raise ValueError('Revision only covers the frozen one-attempt failed batch')
    result_path = attempts[0] / 'result.json'
    result = json.loads(result_path.read_text())
    if (result.get('id') != 'O001' or result.get('success') is not False
            or result.get('independent_replay_passed') is not False
            or result.get('parameter_restore_exact') is not True
            or not result.get('finished_utc') or result.get('remaining_simulators') != []
            or result.get('manifest_sha256') != sha256(path)):
        raise ValueError('Previous attempt must be closed, failed and exactly restored')
    return dict(previous_manifest=str(path), previous_manifest_sha256=sha256(path),
        previous_result=str(result_path), previous_result_sha256=sha256(result_path),
        previous_attempts=1, new_max_attempts=8, cumulative_max_attempts=9,
        old_unexecuted_jobs_closed=7, old_result_unchanged=True,
        authorization='User: 重新冻结新批次，再开展四系统对比。')


def diagnostic_revision_lineage(data_root, previous_manifest):
    """Close B02's PID pass and STA2 tool failure; eight entirely new samples."""
    path = Path(previous_manifest).resolve()
    old = json.loads(path.read_text())
    old_root, new_root = Path(old['data_root']).resolve(), Path(data_root).resolve()
    if old_root == new_root or old_root.is_relative_to(new_root) or new_root.is_relative_to(old_root):
        raise ValueError('New batch must use a separate nonoverlapping data tree')
    attempts = sorted(p for p in (old_root / 'runs').iterdir() if p.is_dir())
    if old.get('max_attempts') != 8 or [p.name for p in attempts] != ['O001', 'O002']:
        raise ValueError('Diagnostic revision requires exactly two closed B02 attempts')
    history = old['budget_history']
    ancestor = Path(history['previous_manifest']).resolve()
    ancestor_history = revision_lineage(old_root, ancestor)
    if any(history.get(key) != ancestor_history[key] for key in
           ('previous_manifest_sha256', 'previous_result_sha256', 'previous_attempts')):
        raise ValueError('Ancestor evidence/count changed')
    ancestor_root = Path(json.loads(ancestor.read_text())['data_root']).resolve()
    if new_root == ancestor_root or new_root.is_relative_to(ancestor_root) or ancestor_root.is_relative_to(new_root):
        raise ValueError('New batch overlaps ancestor data')
    assets = {str(path): sha256(path), str(ancestor): sha256(ancestor),
              ancestor_history['previous_result']: ancestor_history['previous_result_sha256']}
    receipts = []
    for directory, system, accepted in zip(attempts, ('PID', 'STA2'), (True, False)):
        receipt = directory / 'result.json'
        row = json.loads(receipt.read_text())
        if (row.get('id') != directory.name or row.get('system') != system or row.get('task') != 'position'
                or row.get('success') is not accepted or row.get('independent_replay_passed') is not accepted
                or row.get('parameter_restore_exact') is not True or not row.get('finished_utc')
                or row.get('remaining_simulators') != [] or row.get('manifest_sha256') != sha256(path)):
            raise ValueError('B02 outcome must be closed, correctly identified and restored')
        if accepted and row.get('task_completed') is not True:
            raise ValueError('B02 PID must have completed its task')
        if not accepted and row.get('error') != "ValueError('diagnostic attitude_sta_status must be a mapping')":
            raise ValueError('Unexpected B02 failure; this revision only covers diagnostic wiring')
        assets[str(receipt)] = sha256(receipt)
        receipts.append(dict(path=str(receipt), sha256=sha256(receipt), success=accepted))
    return dict(previous_manifest=str(path), previous_manifest_sha256=sha256(path),
        previous_result=receipts[-1]['path'], previous_result_sha256=receipts[-1]['sha256'],
        previous_results=receipts, previous_attempts=2, ancestor_attempts=1, prior_total_attempts=3,
        new_max_attempts=8, cumulative_max_attempts=11, old_unexecuted_jobs_closed=6,
        old_results_unchanged=True, historical_successes_not_imported=True, lineage_assets=assets,
        authorization='User: 新冻结有限批次，再开展四系统对比。')


def final_capture_lineage(data_root, previous_manifest):
    """Close B03 after its event-analysis failure; five old attempts plus eight new."""
    path = Path(previous_manifest).resolve()
    old = json.loads(path.read_text())
    old_root, new_root = Path(old['data_root']).resolve(), Path(data_root).resolve()
    if old_root == new_root or old_root.is_relative_to(new_root) or new_root.is_relative_to(old_root):
        raise ValueError('New batch overlaps B03')
    if old.get('revision') != DIAGNOSTIC_REVISION or old.get('max_attempts') != 8:
        raise ValueError('Require frozen B03 diagnostic revision')
    attempts = sorted(p for p in (old_root / 'runs').iterdir() if p.is_dir())
    if [p.name for p in attempts] != ['O001', 'O002']:
        raise ValueError('Exactly two closed B03 attempts are required')
    ancestor = Path(old['budget_history']['previous_manifest']).resolve()
    verified = diagnostic_revision_lineage(new_root, ancestor)
    # Reconstruct B03's complete budget history, not just its claimed count.
    recorded = old['budget_history']
    if recorded != diagnostic_revision_lineage(old_root, ancestor):
        raise ValueError('B03 ancestor history changed')
    assets = dict(verified['lineage_assets'])
    assets[str(path)] = sha256(path)
    receipts = []
    for directory, system, accepted in zip(attempts, ('PID', 'STA2'), (True, False)):
        receipt = directory / 'result.json'
        row = json.loads(receipt.read_text())
        if (row.get('id') != directory.name or row.get('system') != system or row.get('task') != 'position'
                or row.get('success') is not accepted or row.get('independent_replay_passed') is not accepted
                or row.get('task_completed') is not True or row.get('parameter_restore_exact') is not True
                or not row.get('finished_utc') or row.get('remaining_simulators') != []
                or row.get('manifest_sha256') != sha256(path)):
            raise ValueError('B03 must be completed, correctly identified and exactly restored')
        if not accepted and row.get('analysis_error') != "ValueError('Heading evidence: unexpected reset_vel_to_gps')":
            raise ValueError('Unexpected B03 failure; no general retry authorization')
        if not row.get('logs'):
            raise ValueError('B03 native ULog evidence is required')
        assets[str(receipt)] = sha256(receipt)
        for log in row.get('logs', []):
            if sha256(log['archive']) != log['sha256']:
                raise ValueError('B03 ULog fingerprint changed')
            assets[log['archive']] = log['sha256']
        receipts.append(dict(path=str(receipt), sha256=sha256(receipt), success=accepted))
    return dict(previous_manifest=str(path), previous_manifest_sha256=sha256(path),
        previous_result=receipts[-1]['path'], previous_result_sha256=receipts[-1]['sha256'],
        previous_results=receipts, previous_attempts=2, ancestor_attempts=3, prior_total_attempts=5,
        new_max_attempts=8, cumulative_max_attempts=13, old_unexecuted_jobs_closed=6,
        old_results_unchanged=True, historical_successes_not_imported=True, lineage_assets=assets,
        authorization='User: 更新冻结资格和工具指纹，再冻结新的有限批次开展 SITL 对比')


def offline_test_count(path):
    text = Path(path).read_text()
    matches = re.findall(r'^Ran (\d+) tests? in ', text, re.M)
    if (len(matches) != 1 or int(matches[0]) == 0 or not re.search(r'^OK\s*$', text, re.M)
            or re.search(r'^(FAILED|ERROR|FAIL:|OK \(skipped)', text, re.M)):
        raise ValueError('Require complete nonzero offline test evidence with no skips/failures')
    return int(matches[0])


def final_capture_qualification(path):
    """Bind current sources to complete tests, immutable history and tail replay."""
    path = Path(path).resolve()
    evidence = json.loads(path.read_text())
    if (evidence.get('status') != 'offline_landing_capture_fix_passed_not_flight_qualified'
            or evidence.get('new_flights') != 0 or evidence.get('new_manifest_created') is not False):
        raise ValueError('Missing complete offline landing qualification')
    expected_paths = {str(p.resolve()) for p in HERE.glob('*.py')}
    sources = evidence.get('source_sha256', {})
    if set(sources) != expected_paths:
        raise ValueError('Qualification does not cover the current complete tool set')
    assets = {str(path): sha256(path)}
    for source, expected in sources.items():
        if sha256(source) != expected:
            raise ValueError('Qualified source changed: ' + source)
        assets[source] = expected
    commands = evidence.get('test_commands', [])
    expected_suites = {
        (str(HERE.resolve()), 'test_*.py'),
        (str((HERE.parent / 'tools').resolve()), 'test_*.py'),
        (str((HERE.parents[1] / 'sta-velocity-control/scripts').resolve()), 'test_v04_heading_policy.py')}
    suites = set()
    counts = []
    for command in commands:
        argv = command['argv']
        if command.get('exit_code') != 0 or sha256(command['log']) != command['log_sha256']:
            raise ValueError('Failed or changed qualification tests')
        if len(argv) != 10 or argv[1:5] != ['-B', '-m', 'unittest', 'discover'] or argv[5] != '-s' or argv[7] != '-p' or argv[-1] != '-v':
            raise ValueError('Unknown qualification test command')
        suites.add((argv[6], argv[8]))
        counts.append(offline_test_count(command['log']))
        assets[command['log']] = command['log_sha256']
    if len(commands) != 3 or suites != expected_suites:
        raise ValueError('Incomplete qualification test suites')
    history = evidence['history']
    tail = evidence['tail_probe']
    if (history.get('ulog_count') != 9 or history.get('original_outcomes_and_evidence_unchanged') is not True
            or len(history.get('protected_sha256', {})) < 209
            or tail.get('full_diagnostic_chain_passed') is not True
            or tail.get('deterministic_analysis_replay') is not True
            or tail.get('historical_acceptance_changed') is not False
            or tail.get('flight_accepted') is not False or tail.get('actual_new_flights') != 0
            or tail.get('original_analysis_still_rejects', {}).get('passed') is not False
            or tail.get('unchanged_max_gap_us') != 500000
            or len(tail.get('negative_probes', [])) != 3
            or any(row.get('passed') is not False for row in tail.get('negative_probes', []))):
        raise ValueError('Incomplete strict historical/tail regression')
    for source, expected in history['protected_sha256'].items():
        if sha256(source) != expected:
            raise ValueError('Historical evidence changed: ' + source)
        assets[source] = expected
    return dict(assets=assets, test_counts=counts, total_tests=sum(counts),
                validation=str(path), validation_sha256=sha256(path))


def make_manifest(data_root, offline_log, *, heading_policy=STRICT, previous_manifest=None,
                  revision=HEADING_REVISION):
    if revision not in (HEADING_REVISION, DIAGNOSTIC_REVISION, FINAL_CAPTURE_REVISION):
        raise ValueError('Unknown revision')
    if revision in (DIAGNOSTIC_REVISION, FINAL_CAPTURE_REVISION) and (heading_policy != POLICY or previous_manifest is None):
        raise ValueError('Revision requires its closed predecessor and revised heading policy')
    if heading_policy not in (STRICT, POLICY):
        raise ValueError('Unknown heading policy')
    if (heading_policy == POLICY) != (previous_manifest is not None):
        raise ValueError('Revised policy requires an explicit closed previous batch')
    source = json.loads(SOURCE.read_text())
    result = draft(source)
    result['data_root'] = str(Path(data_root).resolve())
    result['heading_reset_policy'] = heading_policy
    result['revision'] = revision
    if revision == FINAL_CAPTURE_REVISION:
        result['event_semantics_policy'] = REPUBLICATION_EVENTS
    if previous_manifest is not None:
        lineage = {HEADING_REVISION: revision_lineage, DIAGNOSTIC_REVISION: diagnostic_revision_lineage,
                   FINAL_CAPTURE_REVISION: final_capture_lineage}[revision]
        result['budget_history'] = lineage(data_root, previous_manifest)
    if (Path(data_root) / 'runs').exists():
        raise ValueError('New batch requires an unused runs directory')
    if shutil.disk_usage(data_root).free < 10 * 1024 ** 3:
        raise ValueError('Less than 10 GiB available for eight native-log attempts')
    count = offline_test_count(offline_log)
    qualification = final_capture_qualification(Path(data_root) / 'qualification01.json') if revision == FINAL_CAPTURE_REVISION else None
    runtime_cp = subprocess.run([sys.executable, str(RUNTIME)], capture_output=True,
                                text=True, timeout=45)
    if runtime_cp.returncode != 0:
        raise ValueError('Real ROS preflight failed: ' + runtime_cp.stdout)
    runtime = json.loads(runtime_cp.stdout)
    if runtime.get('ready') is not True or runtime.get('roundtrip_passed') is not True:
        raise ValueError('Missing actual two-process DDS qualification')
    result['runtime'] = dict(preflight=str(RUNTIME), launcher=runtime['launcher_argv'],
                             environment=runtime['environment'], qualification=runtime)
    live_path = Path(data_root) / 'live_bridge02/verification.json'
    live = json.loads(live_path.read_text())
    if (live.get('passed') is not True or live.get('packet_counts', {}).get('position', 0) < 25
            or live.get('packet_counts', {}).get('velocity', 0) < 20
            or live.get('actual_ros_receipt', {}).get('forwarded_runner_heartbeat_count', 0) < 1):
        raise ValueError('Actual ROS/wire loopback including forwarded GCS is not qualified')
    result['runtime']['live_bridge_evidence'] = str(live_path)
    result['assets'] = copy.deepcopy(source['assets'])
    if qualification:
        result['assets'].update(qualification['assets'])
        result['combined_offline_qualification'] = {key: value for key, value in qualification.items() if key != 'assets'}
    for path, expected in result['assets'].items():
        if sha256(path) != expected:
            raise ValueError('Inherited tool/model/plugin changed: ' + path)
    runtime_root = RUNTIME.parent
    for path in [*sorted(HERE.glob('*.py')), SOURCE, Path(offline_log), RUNTIME, live_path,
                 runtime_root / 'pypi-requirements.lock', Path(runtime['roundtrip_log']),
                 Path(runtime['package_lock']), Path(runtime['launcher_argv'][-1])]:
        result['assets'][str(path.resolve())] = sha256(path)
    old_jobs = {job['label']: job for job in source['jobs']}
    jobs = []
    for planned in result['jobs']:
        old = copy.deepcopy(old_jobs[LABELS[planned['system']]])
        old.pop('result_path', None)
        old.update(id=planned['id'], system=planned['system'], task=planned['task'], status='unattempted')
        old['heading_reset_policy'] = heading_policy
        if revision == FINAL_CAPTURE_REVISION:
            old['event_semantics_policy'] = REPUBLICATION_EVENTS
        old['embedded_build_source_head'] = old['source_head']
        old['source_head'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                                                    cwd=old['repo'], text=True).strip()
        for path, expected in old.get('source_assets', {}).items():
            if sha256(Path(old['repo']) / path) != expected:
                raise ValueError('Inherited source differs: ' + path)
        if sha256(Path(old['bin']) / 'px4') != old['firmware_sha256']:
            raise ValueError('Inherited firmware differs')
        if 'M10_IMU_LOG' in old['launch_env']:
            old['launch_env']['M10_IMU_LOG'] = str(Path(data_root) / (old['id'] + '_imu.csv'))
        jobs.append(old)
    result['jobs'] = jobs
    result['offline_tests'] = dict(count=count, exit_code=0, log=str(Path(offline_log).resolve()),
                                   sha256=sha256(offline_log))
    result['source_manifest_sha256'] = sha256(SOURCE)
    if heading_policy == POLICY:
        schema_path = HERE / 'results/heading_fix01/historical_schema02.json'
        evidence = json.loads(schema_path.read_text())
        for path, expected in evidence['sources'].items():
            if sha256(path) != expected:
                raise ValueError('Audited upstream EKF schema source changed: ' + path)
            result['assets'][path] = expected
        protocol = {HEADING_REVISION: 'BATCH02_PROTOCOL_CN.md', DIAGNOSTIC_REVISION: 'BATCH03_PROTOCOL_CN.md',
                    FINAL_CAPTURE_REVISION: 'BATCH04_PROTOCOL_CN.md'}[revision]
        for path in (schema_path, HERE / 'HEADING_CHECK_FIX_CN.md', HERE / protocol,
                     Path(previous_manifest), Path(result['budget_history']['previous_result'])):
            result['assets'][str(path.resolve())] = sha256(path)
    if revision == FINAL_CAPTURE_REVISION:
        result['assets'].update(result['budget_history']['lineage_assets'])
        for path in (HERE / 'EVENT_SEMANTICS_FIX_CN.md', HERE / 'LANDING_CONFIRMATION_FIX_CN.md',
                     Path(data_root) / 'submodules_main.txt', Path(data_root) / 'submodules_original.txt',
                     Path(data_root) / 'workspace_before.txt', Path(data_root) / 'preflight_sha256.txt'):
            result['assets'][str(path.resolve())] = sha256(path)
    if revision == DIAGNOSTIC_REVISION:
        validation_path = HERE / 'results/diagnostic_fix01/validation.json'
        validation = json.loads(validation_path.read_text())
        if validation.get('status') != 'offline_passed_not_flight_qualified':
            raise ValueError('Diagnostic wiring regression not accepted offline')
        for name in ('run.py', 'runner_contract.py', 'test_diagnostic_wiring.py', 'replay_diagnostic_fix.py'):
            if sha256(HERE / name) != validation['tool_and_doc_sha256'][name]:
                raise ValueError('Qualified diagnostic wiring source changed: ' + name)
        result['assets'].update(result['budget_history']['lineage_assets'])
        for path in (validation_path, HERE / 'DIAGNOSTIC_WIRING_FIX_CN.md',
                     *sorted((HERE / 'results/diagnostic_fix01').glob('*.json')),
                     *sorted((HERE / 'results/batch02/frozen_tools').glob('*.py')),
                     Path(data_root) / 'submodules_main.txt', Path(data_root) / 'submodules_original.txt',
                     Path(data_root) / 'workspace_before.txt', Path(data_root) / 'preflight_sha256.txt'):
            result['assets'][str(path.resolve())] = sha256(path)
    result['randomness'] = 'Existing development IMU seed 93001; not new independent seeds; original stack not exactly paired'
    result['native_log_contract'] = dict(maximum_gap_s=.5, target_matching_lookback_s=.5,
        target_matching_tolerance=1e-4, shape_handoff_margin_s=.5,
        performance_windows='complete scored phases, no handoff exclusion',
        safety_envelope='same as inherited hover; no numerical widening')
    result['outstanding'] = []
    result['status'] = 'qualified_unattempted'
    result['flight_qualified'] = True
    from runner_contract import validate_manifest
    for job in jobs:
        validate_manifest(result, job['id'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', required=True, type=Path)
    parser.add_argument('--offline-log', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--freeze', action='store_true')
    parser.add_argument('--heading-reset-policy', choices=(STRICT, POLICY), default=STRICT)
    parser.add_argument('--previous-manifest', type=Path)
    parser.add_argument('--revision', choices=(HEADING_REVISION, DIAGNOSTIC_REVISION, FINAL_CAPTURE_REVISION), default=HEADING_REVISION)
    args = parser.parse_args()
    result = make_manifest(args.data_root, args.offline_log,
        heading_policy=args.heading_reset_policy, previous_manifest=args.previous_manifest, revision=args.revision)
    if args.freeze:
        with args.output.open('x') as stream:
            json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write('\n')
        print('Frozen eight unattempted jobs:', args.output)
    else:
        print(json.dumps(dict(status=result['status'], order=result['order'], write=False)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
