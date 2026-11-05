"""Read-only RI04 run003 ULog failure audit; never qualifies or retries a flight.

Only a fresh external report directory is written. The implicit equation is
solved independently by monotone bisection, not by the production kernel.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
DATA = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI04')
RUN = DATA/'B/batch01/run003'
SOURCE = '74327418e18eafd421e18b48fe3964fdad63cfb5'
SOURCE_PATHS = (
    'src/modules/mc_pos_control/PositionControl/PositionControl.cpp',
    'src/modules/mc_pos_control/PositionControl/StaVelocityProtection.cpp',
    'src/modules/mc_pos_control/PositionControl/StaVelocityProtection.hpp',
    'src/modules/mc_pos_control/PositionControl/RegularizedIstaVelocityControl.cpp',
    'src/modules/mc_pos_control/MulticopterPositionControl.cpp',
    'research/sta-velocity-control/v08/protocol02/monitor.py',
)


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            target = os.readlink(path)
            result[str(path.relative_to(root))] = dict(type='symlink', target=target,
                bytes=len(os.fsencode(target)), sha256=hashlib.sha256(os.fsencode(target)).hexdigest())
        elif path.is_file():
            result[str(path.relative_to(root))] = dict(type='regular', bytes=path.stat().st_size, sha256=sha(path))
    return result


def native(value):
    if hasattr(value, 'item'):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return 'NaN' if math.isnan(value) else ('Infinity' if value > 0 else '-Infinity')
    if isinstance(value, dict):
        return {str(k): native(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [native(v) for v in value]
    return value


def row(data, index):
    return {key: native(values[index]) for key, values in data.items()}


def shape(p, epsilon):
    if abs(p) <= epsilon:
        return p / math.sqrt(epsilon), p / epsilon
    return math.copysign(math.sqrt(abs(p)), p), math.copysign(1., p)


def solve(s, h, nu, lambda1, lambda2, epsilon):
    """Unique monotone implicit root, using doubles and bisection only."""
    require(all(math.isfinite(x) for x in (s, h, nu, lambda1, lambda2, epsilon))
            and h > 0 and lambda1 > 0 and lambda2 > 0 and epsilon > 0, 'Invalid numeric audit input')
    left, right = min(s, 0.), max(s, 0.)
    for _ in range(100):
        p = (left + right) / 2
        psi, rho = shape(p, epsilon)
        if p + h*lambda1*psi + h*h*lambda2*rho < s:
            left = p
        else:
            right = p
    p = (left + right) / 2
    psi, rho = shape(p, epsilon)
    candidate = nu - h*lambda2*rho
    return dict(s=s, h=h, nu_before=nu, p=p, psi=psi, rho=rho,
                nu_candidate=candidate, correction=-lambda1*psi+candidate,
                root_residual=p+h*lambda1*psi+h*h*lambda2*rho-s,
                branch='inner' if abs(p) <= epsilon else 'outer')


def hypothetical_hte(old_hover, new_hover, correction, ff, nu, nu_limit, acceleration_limit):
    """Numeric feasibility only; deliberately NOT a cache-policy admission."""
    shift = (old_hover/new_hover-1)*(correction+ff-9.80665)
    return dict(shift=shift, nu_after=nu+shift, correction_after=correction+shift,
                nu_bound_ok=abs(nu+shift) <= nu_limit,
                old_correction_bound_ok=abs(correction) <= acceleration_limit,
                new_correction_bound_ok=abs(correction+shift) <= acceleration_limit,
                actually_executed=False, cache_policy_admitted=False)


def exact_join(status, selection):
    keys = [(int(t), int(s)) for t, s in zip(status['timestamp_sample'], status['publish_seq'])]
    other = [(int(t), int(s)) for t, s in zip(selection['timestamp_sample'], selection['publish_seq'])]
    require(len(keys) == len(set(keys)) and len(other) == len(set(other)), 'Duplicate diagnostic identity')
    mapping = {key: i for i, key in enumerate(other)}
    require(set(keys) == set(other), 'Missing exact diagnostic pair')
    return [mapping[key] for key in keys]


def transitions(data, key, clock='timestamp_sample'):
    return [dict(timestamp_us=int(data[clock][i]), value=native(data[key][i]))
            for i in range(len(data[key])) if i == 0 or data[key][i] != data[key][i-1]]


def first_index(data, key):
    return next((i for i, value in enumerate(data[key]) if value), None)


def at_or_before(data, timestamp):
    indices = [i for i, value in enumerate(data['timestamp']) if value <= timestamp]
    require(indices, 'No preceding topic record')
    return indices[-1]


def audit(run):
    from pyulog import ULog
    run = Path(run).resolve()
    before = snapshot(run)
    result = json.loads((run/'result.json').read_text())
    require(result['source_head'] == SOURCE and result['success'] is False, 'Not the frozen failed RI04 attempt')
    require(result['error'] == "RuntimeError('First update/retry failure')", 'Unexpected original failure')
    require(len(result['logs']) == 2 and len(list(run.glob('*.ulg'))) == 2, 'Expected both owned ULogs')
    decoded, summaries = {}, []
    for item in result['logs']:
        path = Path(item['archive'])
        require(path.parent == run and before[path.name]['sha256'] == item['sha256']
                and before[path.name]['bytes'] == item['bytes'], 'Raw ULog differs from original receipt')
        ulog = ULog(str(path))
        status = ulog.get_dataset('sta_velocity_ctrl_status').data
        selection = ulog.get_dataset('velocity_ctrl_selection').data
        joined = exact_join(status, selection)
        decoded[path.name] = (ulog, status, selection, joined)
        firsts = {}
        for key in ('first_fail', 'sta_fault', 'fault', 'retry_result', 'z_hte_shift'):
            index = first_index(status, key)
            firsts[key] = None if index is None else dict(index=index,
                timestamp_sample=int(status['timestamp_sample'][index]), value=native(status[key][index]))
        summaries.append(dict(name=path.name, sha256=item['sha256'], bytes=item['bytes'],
            header_start_us=ulog.start_timestamp, last_us=ulog.last_timestamp,
            dropout_records=[dict(timestamp=d.timestamp, duration_ms=d.duration) for d in ulog.dropouts],
            topics=[dict(name=d.name, multi_id=d.multi_id, rows=len(d.data['timestamp'])) for d in ulog.data_list],
            status_rows=len(joined), exact_joined_rows=len(joined),
            diagnostic_first_sample=int(status['timestamp_sample'][0]),
            diagnostic_last_sample=int(status['timestamp_sample'][-1]), first_nonzero=firsts,
            fault_rows=int(sum(bool(x) for x in status['fault'])),
            retry_rows=int(sum(bool(x) for x in status['retry_result'])),
            nonzero_hte_shift_rows=int(sum(bool(x) for x in status['z_hte_shift'])),
            transition={k: transitions(status, k) for k in ('armed', 'landed', 'contact', 'takeoff_state', 'z_phase')},
            logged_messages=[dict(timestamp=m.timestamp, message=m.message) for m in ulog.logged_messages]))
    ulog, d, q, joined = decoded['log001.ulg']
    first = first_index(d, 'first_fail')
    require(first is not None and first > 0, 'Missing first fault boundary')
    previous, stamp = first-1, int(d['timestamp_sample'][first])
    require(stamp == 43076000 and int(d['sta_fault'][first]) == 10, 'Unexpected fault signature')
    require(int(d['first_fail'][first]) == 56 and int(d['first_input'][first]) == 32767
            and int(d['pid_calls'][first]) == 2 and int(d['retry_result'][first]) == 2, 'Unexpected first/retry result')
    hte = ulog.get_dataset('hover_thrust_estimate').data
    hte_first = first_index(hte, 'valid')
    require(hte_first is not None and int(hte['timestamp'][hte_first]) == stamp, 'HTE boundary differs')
    require(not q['ri_cache_valid'][joined[previous]] and d['sta_flags'][previous] == 8,
            'Prior cache/StateLimit boundary differs')
    pars = ulog.initial_parameters
    numeric = (pars['MPC_VC_L1_Z'], pars['MPC_VC_L2_Z'], pars['MPC_VC_EPS_Z'])
    candidate_rows, errors = [], []
    for i in range(first):
        j = joined[i]
        if not q['ri_valid'][j]:
            continue
        recomputed = solve(float(d['s[2]'][i]), float(q['ri_h'][j]), float(d['nu_before[2]'][i]), *numeric)
        delta = dict(p=abs(recomputed['p']-float(q['ri_p[2]'][j])),
                     nu_candidate=abs(recomputed['nu_candidate']-float(q['ri_nu_candidate[2]'][j])),
                     correction=abs(recomputed['correction']-float(q['ri_a_ideal[2]'][j])))
        errors.append(delta)
        recomputed.update(timestamp_sample=int(d['timestamp_sample'][i]),
            nu_applied=float(d['nu_applied[2]'][i]), state_limit_flag=bool(d['sta_flags'][i] & 8),
            independently_clipped_nu=max(-pars['MPC_VC_NU_Z'], min(pars['MPC_VC_NU_Z'], recomputed['nu_candidate'])),
            actual_cache_valid=bool(q['ri_cache_valid'][j]), logged_error=delta)
        candidate_rows.append(recomputed)
    require(len(candidate_rows) == 414, 'Unexpected number of real committed implicit candidates')
    max_error = {key: max(e[key] for e in errors) for key in errors[0]}
    # This inherited equality tolerance audits reported floats; not a new flight gate.
    require(all(value <= 2e-6 for value in max_error.values()), 'Independent solve disagrees with real candidates')
    seed_indices = [i for i in range(first) if q['ri_seed_h'][joined[i]] > 0]
    require(len(seed_indices) == 1, 'Unexpected real seed count')
    si = seed_indices[0]; sj = joined[si]
    seed = solve(float(d['s[2]'][si]), float(q['ri_seed_h'][sj]), 0., *numeric)
    seed['inverted_nu'] = float(q['correction[2]'][sj])-seed['correction']
    seed['logged_nu'] = float(d['nu_applied[2]'][si])
    seed['abs_error'] = abs(seed['inverted_nu']-seed['logged_nu'])
    require(seed['abs_error'] <= 2e-6, 'Seed inversion disagrees')
    local = ulog.get_dataset('vehicle_local_position').data
    groundtruth = ulog.get_dataset('vehicle_local_position_groundtruth').data
    trajectory = ulog.get_dataset('trajectory_setpoint').data
    li = at_or_before(local, stamp); ti = at_or_before(trajectory, int(d['setpoint_timestamp'][first]))
    require(int(local['timestamp_sample'][li]) == stamp
            and int(trajectory['timestamp'][ti]) == int(d['setpoint_timestamp'][first]), 'Missing exact boundary inputs')
    original_vsp = (float(trajectory['z'][ti])-float(local['z'][li]))*pars['MPC_Z_P']+float(trajectory['vz'][ti])
    unopened = solve(float(d['v[2]'][first])-original_vsp, float(d['used_dt'][first]),
                     float(d['nu_applied[2]'][previous]), *numeric)
    unopened.update(original_vsp_reconstructed=original_vsp, actually_evaluated=False,
        limitation='Counterfactual only: source HTE rejection occurs before implicit evaluation; final diagnostic v_sp is retry input.')
    numeric_hte = hypothetical_hte(float(d['hover_thrust'][previous]), float(hte['hover_thrust'][hte_first]),
        float(q['correction[2]'][joined[previous]]), float(d['a_ff[2]'][previous]),
        float(d['nu_applied[2]'][previous]), pars['MPC_VC_NU_Z'], pars['MPC_VC_A_Z'])
    ready = next(event['timestamp_us'] for event in result['events'] if event['name'] == 'ready')
    ground = json.loads((run/'ground.json').read_text())
    gt0 = at_or_before(groundtruth, ready); gtf = at_or_before(groundtruth, stamp)
    airborne = dict(fault_local_position=row(local, li), ready_local_z=ground[2],
        local_rise_from_ready_m=ground[2]-float(local['z'][li]),
        ready_groundtruth=row(groundtruth, gt0), fault_groundtruth=row(groundtruth, gtf),
        groundtruth_rise_from_ready_m=float(groundtruth['z'][gt0])-float(groundtruth['z'][gtf]),
        note='Simulator ground truth proves actual model rise; land-detected false alone is not proof of lift-off time. No hardware claim.')
    source_records = {}
    for path in SOURCE_PATHS:
        raw = subprocess.check_output(['git', 'show', SOURCE+':'+path], cwd=REPO)
        digest = hashlib.sha256(raw).hexdigest()
        require(sha(REPO/path) == digest, 'Working production/source reference differs from frozen source')
        source_records[path] = dict(source_head=SOURCE, sha256=digest)
    after = snapshot(run)
    require(before == after, 'Original archive changed during audit')
    return dict(stage='RI04 failure audit only', success=True, stage_accepted=False,
        source_inputs_unchanged=True,
        airborne_confirmed=airborne['groundtruth_rise_from_ready_m'] > 1. and not bool(d['landed'][first]),
        raw_ulog_fingerprints={item['archive']: dict(before=before[Path(item['archive']).name],
                                                    after=after[Path(item['archive']).name]) for item in result['logs']},
        audit_completed=True, flight_accepted=False,
        original_failure_preserved=True, new_flights=0, retries=0, budget_added=0,
        source_head=SOURCE, original_result=result,
        preservation=dict(before=before, after=after, identical=True,
                          original_file_count=sum(item['type'] == 'regular' for item in before.values()),
                          original_symlink_count=sum(item['type'] == 'symlink' for item in before.values()),
                          original_ulog_count=2, decoded_ulog_count=len(decoded)),
        source_files=source_records, logs=summaries,
        source_line_references={
            'fault_and_flag_bits': 'StaVelocityProtection.hpp:38-40',
            'state_limit_protection': 'StaVelocityProtection.cpp:284-287',
            'cache_rejection_after_protected_commit': 'PositionControl.cpp:398-407',
            'hte_consumed_before_current_state': 'MulticopterPositionControl.cpp:326-338',
            'hte_cache_short_circuit': 'PositionControl.cpp:180-196',
            'already_latched_update_and_sample_not_advanced': 'PositionControl.cpp:282-300',
            'first_failure_preserved_and_retry': 'MulticopterPositionControl.cpp:526-554',
            'shift_numerical_bounds_not_reached_this_time': 'StaVelocityProtection.cpp:32-43',
            'seed_inversion': 'StaVelocityProtection.cpp:323-336'},
        total_status_rows=sum(s['status_rows'] for s in summaries),
        timeline=dict(ready_us=ready, first_valid_hte_us=stamp, first_failure_us=stamp,
            seconds_after_ready=(stamp-ready)/1e6, real_seed_sample_us=int(d['timestamp_sample'][si]),
            real_seed_h=float(q['ri_seed_h'][sj]), first_committed_sample_us=candidate_rows[0]['timestamp_sample'],
            first_state_limit_sample_us=next(x['timestamp_sample'] for x in candidate_rows if x['state_limit_flag']),
            cache_transitions=transitions(q, 'ri_cache_valid'),
            final_good_sample_us=int(d['timestamp_sample'][previous]),
            first_fail_bits={'8':'acceleration invalid', '16':'thrust invalid', '32':'STA latch'},
            final_sta_fault_bits={'2':'Measurement added by pre-latched update', '8':'Numerical from HTE cache rejection'},
            source_order='HTE consume -> updateHoverThrust cache refusal/abort8 -> first update abort2 -> preserve first_fail56 -> same-sample retry abort2 -> publish final fault10',
            snapshot_limitation='sta_fault=10 is final retry state, not a directly logged first-abort snapshot; z_phase=3 is retained, not proof of failed-frame kernel execution.'),
        boundary_rows=[dict(status=row(d, i), selection=row(q, joined[i]))
                       for i in sorted(set([si, si+1, previous-1, previous, first, first+1]))],
        hte=dict(rows=[row(hte, i) for i in range(len(hte['timestamp']))],
                 first_valid_index=hte_first, applied_hover_values=sorted({float(v) for v in d['hover_thrust']}),
                 applied_nonzero_shift_count=int(sum(bool(v) for v in d['z_hte_shift'])),
                 refusal='Prior cache_valid=false: outer valid=false, shift=NaN, short-circuit skips shiftZ. This is NOT proof that shiftZ numerical bounds were exceeded.',
                 counterfactual_from_last_published_applied_correction=numeric_hte),
        independent_recomputation=dict(method='100-step monotone double-precision bisection of RI-1; no production kernel import',
            inherited_float_comparison_tolerance=2e-6, max_abs_error=max_error,
            real_candidate_count=len(candidate_rows), real_candidates=candidate_rows,
            seed=seed, unopened_first_fault_candidate=unopened),
        original_first_input=dict(trajectory=row(trajectory, ti), local_position=row(local, li),
                                  all_first_input_finite_mask=int(d['first_input'][first])),
        actual_airborne=airborne,
        main_task=dict(started=False, recorded_result_event_names=[e['name'] for e in result['events']],
                       max_excitation_time=float(max(d['excitation_time'])),
                       nonzero_excitation_count=sum(bool(v) for v in d['excitation'])),
        proven=['Both original ULogs decoded and SHA/byte checked; all original archive files unchanged.',
                'Real 8 ms seed, then 414 successful implicit Z commits precede the first failure.',
                'StateLimit invalidates the HTE continuity cache; last good sample has StateLimit and invalid cache.',
                'First recorded valid HTE and first fault share sample 43076000; frozen source deterministically refuses this cache state.',
                'Failure was after model lift-off but before injected main task; failed attempt remains failed.'],
        limitations=['No direct internal call-stack/first abort snapshot or HTE-consumed message ID is logged; causal branch is inferred from exact observed state and frozen source order.',
                     'The observed candidate/state history explains when nu reached -4, but does not establish why the upstream/plant tracking error accumulated; no plant, HTE-estimator, gain or upstream fault diagnosis is asserted.',
                     'ULog no-dropout records do not prove every publication of every topic was logged; no interpolation fills unseen messages.',
                     'Fault-frame v_sp/a_ff/ri_* are final retry diagnostics, not the first invocation candidate.',
                     'Counterfactual HTE shift and unopened candidate are numeric diagnostics, not valid cached transactions, fixes, or acceptance evidence.',
                     'Actual one-run seed is 8 ms; 12 ms appears on subsequent real updates, not as an additional seed.',
                     'No main-task performance, successful HTE rebase, hardware behavior, or later-seed outcome can be claimed.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=RUN)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run, output = args.run.resolve(), args.output.resolve()
    require(run == RUN and DATA in output.parents and run not in output.parents
            and not output.exists(), 'Only original run003 and a fresh separate RI04 audit output are permitted')
    report = audit(run)
    test_command = [sys.executable, '-B', str(HERE/'test_failure_audit.py')]
    tests = subprocess.run(test_command, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    require(tests.returncode == 0 and b'Ran 8 tests in ' in tests.stdout and b'\nOK\n' in tests.stdout,
            'Independent audit helper tests failed')
    report['tests'] = dict(command=test_command, cwd=str(REPO), exit_code=tests.returncode, tests_executed=8,
        script_sha256=sha(HERE/'test_failure_audit.py'), log_sha256=hashlib.sha256(tests.stdout).hexdigest(),
        log_path=str(output/'tests.log'))
    report['execution'] = dict(command=[sys.executable, '-B', str(Path(__file__).resolve()), *sys.argv[1:]],
        cwd=str(Path.cwd()), pythonpath=os.environ.get('PYTHONPATH'),
        script_sha256=sha(__file__), finished_utc=datetime.now(timezone.utc).isoformat(), exit_code=0,
        prior_exploratory_decode_attempt=dict(exit_code=1, error='ModuleNotFoundError: pyulog',
            cause='Incomplete PYTHONPATH; later two-log decode with existing M00 dependency path succeeded.',
            output='Tool output only, not separately fileized'),
        prior_audit_attempt=dict(exit_code=1, error='ValueError: Original archive contains symlink',
            cause='Snapshot initially refused existing models/iris/meshes symlink; corrected to fingerprint the link itself without following it.',
            wrote_output=False, output='Tool output only, not separately fileized'))
    output.mkdir(parents=True)
    (output/'tests.log').write_bytes(tests.stdout)
    path = output/'summary.json'
    path.write_text(json.dumps(native(report), ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(report=str(path), report_sha256=sha(path), audit_completed=True,
        original_failure_preserved=True, first_fault_us=report['timeline']['first_failure_us'],
        first_fail=56, final_sta_fault=10, independent_candidates=report['independent_recomputation']['real_candidate_count'],
        original_files_unchanged=report['preservation']['original_file_count']), ensure_ascii=False))


if __name__ == '__main__':
    main()
