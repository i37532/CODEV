"""Qualified RI03 X-only complete analysis. No historical mode relabelling."""
import argparse
import json
import math
from pathlib import Path
import traceback

from bindings import (api, clone, digest, exact, FINAL, HERE, KERNEL, load,
                      read, REPO, save, source_binding)


def require(value, message):
    if not value:
        raise ValueError(message)


def validate_job(job):
    require(job.get('revision') == 'ri03' and job.get('gate') == 'A', 'Only RI03 A/X jobs admitted')
    result = KERNEL.full_chain.spec(job)
    require(job.get('candidate') == {0: 'PID', 3: 'RSTA', 4: 'RISTA'}.get(job.get('mode')),
            'Candidate label and actual mode differ')
    require(type(job.get('seed')) is int and job['seed'] > 0, 'Missing registered seed')
    return result


def protocol_identity(protocol, job):
    validate_job(job)
    canonical = api().load_protocol('A')
    excluded = {'qualification_path', 'startup_overrides'}
    require(exact({k: v for k, v in protocol.items() if k not in excluded},
                  {k: v for k, v in canonical.items() if k not in excluded}), 'Noncanonical RI03 protocol')
    require(any(exact(job, j) for j in canonical['jobs']), 'Job outside nine-run manifest')
    require(exact(protocol['startup_overrides'], {**canonical['startup_overrides'], **job['parameters']}),
            'Wrong exact per-job parameter overlay')
    qpath = Path(protocol['qualification_path']).resolve()
    require(Path(canonical['qualification_path']).resolve().parent.parent in qpath.parents,
            'Qualification outside frozen gate')
    return canonical


def archive_scope(run, protocol, job):
    validate_job(job)
    original = (Path(protocol['artifacts']['new_run_root']) / job['id']).resolve()
    record = read(Path(run) / 'result.json')
    logs = record.get('logs', [])
    require(logs and len({x['archive'] for x in logs}) == len(logs), 'Missing/duplicate owned ULogs')
    for item in logs:
        path = Path(item['archive']).resolve()
        require(path.parent == original and path.suffix == '.ulg' and path.is_file(), 'Wrong RI03 raw archive scope')
        require(path.stat().st_size == item['bytes'] and digest(path) == item['sha256'], 'Raw ULog fingerprint changed')
    return record


def source_context(run, protocol, job, *, original_source=None, authorization_sha256=None):
    """Bind diagnostics to their canonical archive without copying authority.

    Called before any science output is written. The frozen full engine also
    invokes provenance as its first try-body statement, before verify_model,
    baseline decoding, or any save; regression exercises that real ordering.
    """
    run = Path(run).resolve()
    original = (Path(protocol['artifacts']['new_run_root']) / job['id']).resolve()
    if original_source is None:
        require(run == original and authorization_sha256 is None, 'Live analysis must use canonical original run')
    else:
        require(Path(original_source).resolve() == original and run != original,
                'Replay original source differs from canonical job archive')
        require(authorization_sha256 is not None, 'Missing original authorization fingerprint')
        require(not any((run / name).exists() or (run / name).is_symlink()
                        for name in ('authorization.json', 'gate_pass.json')),
                'Replay must not contain reusable authorization/gate authority')
        require(not any(path.is_symlink() for path in run.iterdir()), 'Replay sidecar must not be a symlink')
        FINAL._handoff.copied_input_binding(original, run)
    original_authorization = original / 'authorization.json'
    require(original_authorization.is_file() and not original_authorization.is_symlink(),
            'Missing/non-original authorization receipt')
    actual_sha = digest(original_authorization)
    if authorization_sha256 is not None:
        require(actual_sha == authorization_sha256, 'Original authorization changed during replay')
    return original, actual_sha


def provenance(run, protocol, job, *, original_source=None, authorization_sha256=None):
    run = Path(run).resolve()
    protocol_identity(protocol, job)
    original, receipt_sha = source_context(run, protocol, job, original_source=original_source,
                                         authorization_sha256=authorization_sha256)
    api().require_execution_authority('A')
    record = archive_scope(run, protocol, job)
    require(exact(read(run / 'run_protocol.json'), protocol), 'Saved actual protocol differs')
    qpath = Path(protocol['qualification_path']).resolve()
    reference = read(run / 'qualification_reference.json')
    require(Path(reference.get('path', '')).resolve() == qpath and reference.get('sha256') == digest(qpath),
            'Qualification reference changed')
    qualified = api().archive_qualification('A', record['source_head'], qpath)
    require(exact(read(run / 'qualification.json'), qualified), 'Copied qualification changed')
    approval = read(original / 'authorization.json')
    require(exact(approval, read(qpath.parent / 'authorization.json')), 'Original authorization changed')
    expected = dict(revision='ri03', stage=protocol['stage'], gate='A', source_head=qualified['source_head'],
        firmware_sha256=qualified['firmware_sha256'], execution_sha256=digest(Path(protocol['execution_path'])),
        frozen_sha256=digest(Path(protocol['config_dir']) / 'frozen.json'), qualification_sha256=digest(qpath),
        maximum_attempts=9, new_matrix_attempts=9, historical_attempts=0, total_maximum_attempts=9,
        execution_authorized=True, flight_authorized=True, execution_ready=True)
    require(approval.get('approved') is True, 'No explicit clean qualification approval')
    for key, value in expected.items():
        require(exact(approval.get(key), value), 'Authorization binding differs: ' + key)
        if key != 'qualification_sha256':
            require(exact(qualified.get(key), value), 'Qualification binding differs: ' + key)
    require(record.get('binary_sha256') == expected['firmware_sha256']
            and record.get('runner_sha256') == digest(HERE / 'runner.py')
            and record.get('scenario_sha256') == expected['execution_sha256']
            and record.get('scenario_path') == str(Path(protocol['execution_path']).resolve())
            and record.get('branch') == 'research/ista-velocity-regularized'
            and exact(read(run / 'job.json'), job), 'Source/binary/scenario/branch/job mismatch')
    restored = read(run / 'parameter_restore.json')
    require(restored.get('parameter_restore_exact') is True and restored.get('remaining_simulators') == []
            and restored.get('stopped_before_restore') is True and restored.get('source_head') == record['source_head']
            and restored.get('gate') == 'A' and restored.get('job_id') == job['id']
            and restored.get('original_parameter_sha256') == digest(run / 'original_parameters.bson')
            and restored.get('restored_parameter_sha256') == restored['original_parameter_sha256'],
            'Incomplete exact parameter restoration/owned shutdown')
    # Identical qualification receipt across all jobs: no per-run source path
    # is added to this shared binding, so genuine paired comparisons stay exact.
    return {**expected, 'authorization_receipt_sha256': receipt_sha}


def replay_protocol(run, job):
    protocol = read(Path(run) / 'run_protocol.json')
    protocol_identity(protocol, job)
    return protocol


def components(d, selection, job, start, end, steady=False):
    validate_job(job)
    return KERNEL.full_chain.components(d, selection, job, start, end, steady)


def full_analysis(checked_provenance):
    # The frozen RI02 composition supplies NEW p/nu/applied mathematics and
    # explicit private target mode4 domain, without changing any old module.
    function = KERNEL.full_chain.build(checked_provenance, save)
    return clone(function, check_components=components, validate_job=validate_job)


def analyze(run, protocol, job, *, original_source=None, authorization_sha256=None):
    protocol_identity(protocol, job)
    archive_scope(run, protocol, job)
    source_context(run, protocol, job, original_source=original_source,
                   authorization_sha256=authorization_sha256)
    preparation, warmup = {}, {}
    def checked(run, p, j):
        result = provenance(run, p, j, original_source=original_source,
                            authorization_sha256=authorization_sha256)
        preparation.update(FINAL.prearm_evidence(run))
        warmup.update(FINAL.warmup_evidence(run))
        return result
    result = full_analysis(checked)(Path(run), protocol, job)
    result.update(prearm_preparation=preparation or dict(valid=False),
        post_logger_warmup=warmup or dict(valid=False), candidate_numeric_binding=source_binding(),
        handoff_dependency_binding=FINAL.HANDOFF_BINDING, position_clock_binding=FINAL.CLOCK_BINDING)
    result['limitations'] = [
        'RI03 fixed-parameter X development only: PID/R-STA/R-ISTA, three paired IMU seeds each.',
        'No claim of Z/XY/XYZ admission, formal tuning, hardware validity, or old ESTA comparison.',
        'Common external target does not imply identical consumed velocity targets.',
        'Only IMU noise is explicitly seeded; other sensor/scheduler randomness is not independently controlled.',
        'Ideal p/a/nu candidates and protected applied/published outputs are checked separately; protected outputs are not strict implicit solutions.',
        'Thrust proxy is not measured acceleration; TV is not energy; host wall time is not board CPU.',
    ]
    if result.get('accepted') is True:
        try:
            result.update(FINAL.upstream_evidence(run, result))
        except Exception as error:
            result.update(accepted=False, error='Full-rate upstream coverage: ' + str(error))
    save(Path(run) / 'r03_metrics.json', result)
    return result


def validate_pair(pid, candidate):
    for item in (pid, candidate):
        validate_job(item['job'])
        require(item.get('accepted') is True and item.get('prearm_preparation', {}).get('valid') is True
                and item.get('post_logger_warmup', {}).get('valid') is True, 'Invalid paired whole-flight member')
        require(exact(item.get('candidate_numeric_binding'), source_binding())
                and exact(item.get('handoff_dependency_binding'), FINAL.HANDOFF_BINDING)
                and exact(item.get('position_clock_binding'), FINAL.CLOCK_BINDING), 'Paired scientific binding differs')
    a, b = pid['job'], candidate['job']
    require(a['mode'] == 0 and b['mode'] in (3, 4)
            and all(exact(a[k], b[k]) for k in ('seed', 'gate', 'task', 'divisor', 'main_duration_s')),
            'Wrong pair algorithm/seed/task')
    require(exact(pid.get('binding'), candidate.get('binding')), 'Pair source/protocol/firmware differs')
    omitted = {'MPC_VC_MODE', 'MPC_VC_AXES'}
    require(exact({k: v for k, v in a['parameters'].items() if k not in omitted},
                  {k: v for k, v in b['parameters'].items() if k not in omitted}), 'Different paired fixed parameters')


def compare(pid, candidate):
    validate_pair(pid, candidate)
    for item in (pid, candidate):
        vectors = [item['diagnostic']['error']['rmse'], item['position_rmse']]
        vectors.extend(item['diagnostic']['windows'][w]['error']['rmse'] for w in ('first_half', 'second_half'))
        require(all(isinstance(v, list) and len(v) == 3 for v in vectors), 'Missing three-axis paired metric')
        values = [item['yaw_rmse']] + [x for v in vectors for x in v]
        require(all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in values),
                'Invalid finite nonnegative paired metric')
    checks = {}
    for axis, allowance in enumerate((.02, .02, .01)):
        checks['velocity_' + str(axis)] = candidate['diagnostic']['error']['rmse'][axis] <= 1.25 * pid['diagnostic']['error']['rmse'][axis] + allowance
        checks['position_' + str(axis)] = candidate['position_rmse'][axis] <= 1.25 * pid['position_rmse'][axis] + .05
        for window in ('first_half', 'second_half'):
            checks[window + '_velocity_' + str(axis)] = candidate['diagnostic']['windows'][window]['error']['rmse'][axis] <= 1.25 * pid['diagnostic']['windows'][window]['error']['rmse'][axis] + allowance
    checks['yaw'] = candidate['yaw_rmse'] <= 1.25 * pid['yaw_rmse'] + .02
    return dict(accepted=all(checks.values()), checks=checks, seed=pid['job']['seed'], gate='A',
                candidate=candidate['job']['candidate'],
                criterion='Inherited development risk, not a requirement to beat PID or another STA')


def replay_new(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    job = read(source / 'job.json')
    p = replay_protocol(source, job)
    require(source == (Path(p['artifacts']['new_run_root']) / job['id']).resolve(), 'Not original RI03 run')
    archive_scope(source, p, job)
    _, original_authorization_sha = source_context(source, p, job)
    before = local_snapshot(source)
    FINAL._handoff.copy_sidecars(source, destination)
    FINAL._handoff.copied_input_binding(source, destination)
    try:
        return analyze(destination, p, job, original_source=source,
                       authorization_sha256=original_authorization_sha)
    finally:
        require(digest(source / 'authorization.json') == original_authorization_sha
                and exact(local_snapshot(source), before), 'Original replay inputs changed')


def local_snapshot(source):
    # Reuse the standalone replay snapshot without generic module imports.
    from bindings import local
    return local('replay').snapshot(source)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = replay_new(args.source, args.output)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result.get('accepted') is True else 1)
