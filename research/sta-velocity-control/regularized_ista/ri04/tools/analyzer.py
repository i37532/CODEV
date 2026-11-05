"""Qualified RI04 Z-only complete analysis. No historical mode relabelling."""
import argparse
import json
import math
from pathlib import Path
import traceback

import numpy as np

from bindings import (api, clone, digest, exact, FINAL, HERE, KERNEL, load,
                      read, REPO, save, source_binding)


def require(value, message):
    if not value:
        raise ValueError(message)


def validate_job(job):
    require(job.get('revision') == 'ri04' and job.get('gate') == 'B', 'Only RI04 B/Z jobs admitted')
    result = KERNEL.full_chain.spec(job)
    require(job.get('candidate') == {0: 'PID', 3: 'RSTA', 4: 'RISTA'}.get(job.get('mode')),
            'Candidate label and actual mode differ')
    require(type(job.get('seed')) is int and job['seed'] > 0, 'Missing registered seed')
    return result


def protocol_identity(protocol, job):
    validate_job(job)
    canonical = api().load_protocol('B')
    excluded = {'qualification_path', 'startup_overrides'}
    require(exact({k: v for k, v in protocol.items() if k not in excluded},
                  {k: v for k, v in canonical.items() if k not in excluded}), 'Noncanonical RI04 protocol')
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
        require(path.parent == original and path.suffix == '.ulg' and path.is_file(), 'Wrong RI04 raw archive scope')
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
    api().require_execution_authority('B')
    record = archive_scope(run, protocol, job)
    require(exact(read(run / 'run_protocol.json'), protocol), 'Saved actual protocol differs')
    qpath = Path(protocol['qualification_path']).resolve()
    reference = read(run / 'qualification_reference.json')
    require(Path(reference.get('path', '')).resolve() == qpath and reference.get('sha256') == digest(qpath),
            'Qualification reference changed')
    qualified = api().archive_qualification('B', record['source_head'], qpath)
    require(exact(read(run / 'qualification.json'), qualified), 'Copied qualification changed')
    approval = read(original / 'authorization.json')
    require(exact(approval, read(qpath.parent / 'authorization.json')), 'Original authorization changed')
    expected = dict(revision='ri04', stage=protocol['stage'], gate='B', source_head=qualified['source_head'],
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
            and restored.get('gate') == 'B' and restored.get('job_id') == job['id']
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
    if job['mode'] != 4:
        return KERNEL.full_chain.components(d, selection, job, start, end, steady)
    result, x, q = KERNEL.full_chain.components(d, selection, job, start, end, steady)
    result['closed_cache_hte'] = closed_cache_hte(x, q, job)
    return result, x, q


def closed_cache_hte(x, q, job):
    """Check observable normal-Z HTE mapping; retain full lifecycle elsewhere.

    Module Run consumes at most one valid HTE update before setState/update.
    On the declared subset its input is the previous closed sample cache.
    We do not infer hidden HTE publications, nor expand this formula to reset,
    seed, inactive, same-sample retry or incomplete-cache boundaries.
    The 2e-6 m/s² equality tolerance is the inherited applied-output tolerance.
    """
    require(job['mode'] == 4 and job['axes'] == 4 and job['parameters']['MPC_USE_HTE'] == 1,
            'Closed-cache HTE needs frozen R-ISTA Z/HTE configuration')
    count = len(x['timestamp'])
    eligible = np.zeros(count, dtype=bool)
    eligible[1:] = ((x['z_phase'][:-1] == 3) & (x['z_phase'][1:] == 3)
        & q['ri_cache_valid'][:-1].astype(bool)
        & (q['ri_cache_sample'][:-1] == x['timestamp_sample'][:-1])
        & (q['sta_gen'][:-1] == q['sta_gen'][1:])
        & (np.diff(q['control_seq'].astype(np.int64)) == 1)
        & q['control_updated'][:-1].astype(bool) & q['control_updated'][1:].astype(bool)
        & (x['pid_calls'][:-1] == 1) & (x['pid_calls'][1:] == 1)
        & (x['reset_bits'][:-1] == 0) & (x['reset_bits'][1:] == 0)
        & ((x['sta_flags'][:-1].astype(int) & (1 | 2 | 4 | 64 | 128 | 256)) == 0)
        & ((x['sta_flags'][1:].astype(int) & (1 | 2 | 4 | 64 | 128 | 256)) == 0))
    indices = np.flatnonzero(eligible)
    previous = indices - 1
    hover_old = np.asarray(x['hover_thrust'][previous], dtype=np.float32)
    hover_new = np.asarray(x['hover_thrust'][indices], dtype=np.float32)
    correction = np.asarray(q['correction[2]'][previous], dtype=np.float32)
    ff_raw = np.asarray(x['a_ff[2]'][previous], dtype=np.float32)
    ff = np.where(np.isfinite(ff_raw), ff_raw, np.float32(0))
    require(np.all(np.isfinite(hover_old)) and np.all(np.isfinite(hover_new))
            and np.all((hover_old >= .1) & (hover_old <= .9))
            and np.all((hover_new >= .1) & (hover_new <= .9))
            and np.all(np.isfinite(correction)), 'Invalid closed-cache HTE map')
    expected = (hover_old / hover_new - np.float32(1)) * (correction + ff - np.float32(9.80665))
    actual = np.asarray(x['z_hte_shift'][indices], dtype=np.float32)
    require(np.all(np.isfinite(actual)) and np.allclose(actual, expected, atol=2e-6, rtol=0),
            'Closed-cache HTE shift differs from hover/correction/FF map')
    error = abs(actual.astype(float) - expected.astype(float))
    return dict(eligible_pairs=len(indices), nonzero_shifts_checked=int(np.count_nonzero(actual)),
        nonzero_shifts_outside_subset=int(np.count_nonzero(x['z_hte_shift'][~eligible])),
        max_abs_error_m_s2=float(error.max()) if len(error) else None,
        tolerance_m_s2=2e-6, model='closed previous correction/FF cache, one HTE consumption per callback',
        limitation='Subset mapping evidence only; full lifecycle validates excluded boundaries, not hidden HTE publications')


def full_analysis(checked_provenance):
    # The frozen RI02 composition supplies NEW p/nu/applied mathematics and
    # explicit private target mode4 domain, without changing any old module.
    function = KERNEL.full_chain.build(checked_provenance, save)
    return clone(function, check_components=components, validate_job=validate_job)


def z_metric_labels(result):
    """Expose existing metrics, not a new threshold or a fabricated trajectory.

    TEST2 adds a bounded velocity sinusoid after position P. Its integral is
    zero but the actual consumed v_sp also contains position correction.
    Nominal height deviation includes that intentional motion; it is not the
    vertical velocity-target tracking error and does not use its 32s window.
    """
    diagnostic = result['diagnostic']
    return dict(
        consumed_vertical_velocity_target_tracking=dict(
            axis='NED Z (down positive)', units='m/s', error='v[2]-v_sp[2]',
            window='32s injected-velocity main window', seconds=diagnostic['seconds'],
            statistics={key: value[2] for key, value in diagnostic['error'].items()},
            half_windows={name: {key: value[2] for key, value in window['error'].items()}
                          for name, window in diagnostic['windows'].items()}),
        nominal_height_deviation=dict(
            reference_height_m=2.5, units='m', window='full recorded observation (90-92s)',
            statistics=result['height'], is_velocity_tracking_error=False,
            includes_intentional_vertical_motion=True),
        consumed_position_target_error=dict(units='m', axis='NED Z',
            window='inherited position-metric observation window', rmse=result['position_rmse'][2]),
        waveform='TEST2: 0.1*sin(2*pi*t/8)*sin(pi*t/32)^2 m/s, 0<=t<32; otherwise zero',
        target_note='Position P remains active; common injected velocity does not imply equal consumed v_sp.')


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
        'RI04 fixed-parameter Z development only: PID/R-STA/R-ISTA, three paired IMU seeds each.',
        'No claim of XY/XYZ admission, formal tuning, hardware validity, or old ESTA comparison.',
        'Common external target does not imply identical consumed velocity targets.',
        'Only IMU noise is explicitly seeded; other sensor/scheduler randomness is not independently controlled.',
        'Ideal p/a/nu candidates and protected applied/published outputs are checked separately; protected outputs are not strict implicit solutions.',
        'Thrust proxy is not measured acceleration; TV is not energy; host wall time is not board CPU.',
    ]
    if result.get('accepted') is True:
        try:
            result.update(FINAL.upstream_evidence(run, result))
            result['z_task_metrics'] = z_metric_labels(result)
        except Exception as error:
            result.update(accepted=False, error='Full-rate upstream coverage/Z metric evidence: ' + str(error))
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
    return dict(accepted=all(checks.values()), checks=checks, seed=pid['job']['seed'], gate='B',
                candidate=candidate['job']['candidate'],
                criterion='Inherited development risk, not a requirement to beat PID or another STA')


def replay_new(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    job = read(source / 'job.json')
    p = replay_protocol(source, job)
    require(source == (Path(p['artifacts']['new_run_root']) / job['id']).resolve(), 'Not original RI04 run')
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
