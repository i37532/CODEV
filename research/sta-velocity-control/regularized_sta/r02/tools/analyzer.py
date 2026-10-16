"""Strict R02 offline components, never a real MODE3 flight acceptance claim.

Uses the actual piecewise regularized law, not smooth hypot surrogates. Legacy
functions are called directly without changing source, data, modes or globals.
The whole-flight composition remains non-authorizing until an R03 protocol binds
the exact task, source, safety/performance gates and per-run provenance.
"""
import json
from pathlib import Path
import numpy as np
from config import validate
from legacy import cadence_checks, clock_policy, initialize, leaf, task_checks


def vector(d, name):
    return np.column_stack([d[f'{name}[{axis}]'] for axis in range(3)])


def columns(d):
    n = len(d['timestamp'])
    if not n or any(np.asarray(v).shape != (n,) for v in d.values()):
        raise ValueError('Missing/malformed diagnostic columns')
    return n


def integer_sequence(a, *, contiguous=False):
    a = np.asarray(a)
    if a.ndim != 1 or not len(a) or a.dtype.kind not in 'iu' or np.any(a < 0):
        raise ValueError('Invalid sequence')
    delta = np.diff(a.astype(np.int64))
    bad = np.any(delta != 1) if contiguous else np.any(delta <= 0)
    if bad:
        raise ValueError('Duplicate/backward/missing sequence')
    return a


def aligned(status, selection):
    """Unique sequence AND exact sensor sample; no nearest or dedup fallback."""
    columns(status); columns(selection)
    key = integer_sequence(selection['publish_seq'], contiguous=True)
    seq = integer_sequence(status['publish_seq'], contiguous=True)
    cp = clock_policy()
    for data in (status, selection):
        for name in ('timestamp', 'timestamp_sample', 'input_timestamp'):
            cp.strict_clock(data[name])
        if np.any(data['timestamp_sample'] > data['input_timestamp']) or np.any(data['input_timestamp'] > data['timestamp']):
            raise ValueError('Future consumed clock')
    indices = np.searchsorted(key, seq)
    if np.any(indices >= len(key)) or not np.array_equal(key[indices], seq):
        raise ValueError('Missing exact selection publication')
    q = {k: v[indices] for k, v in selection.items()}
    for name in ('timestamp_sample', 'input_timestamp', 'pid_calls', 'enabled', 'armed',
                 'requested_mode', 'effective_mode', 'requested_axes', 'effective_axes', 'pending', 'reject'):
        if not np.array_equal(q[name], status[name]):
            raise ValueError('Selection exact join mismatch: ' + name)
    return q


def nonlinear(s, epsilon):
    """Independent binary64 product form from the R00 equations."""
    s = np.asarray(s, dtype=np.float64)
    if not .001 <= epsilon <= 1 or not np.isfinite(epsilon) or not np.all(np.isfinite(s)):
        raise ValueError('Invalid regularized nonlinearity input')
    radius = np.maximum(np.abs(s), epsilon)
    rho = s / radius
    psi = np.sqrt(radius) * rho
    return psi, rho


def check_components(status, selection, job, start, end, *, steady=False, new_metadata=True):
    historical_task = {'H': 6, 'V': 8}.get(job.get('task'), 0)
    validate(job['mode'], job['axes'], job['parameters'], allowed_task_modes=(historical_task,))
    fullq = aligned(status, selection)
    mask = (status['timestamp'] >= start) & (status['timestamp'] < end)
    x = {k: v[mask] for k, v in status.items()}
    q = {k: v[mask] for k, v in fullq.items()}
    if len(x['timestamp']) < 600 or x['timestamp'][0] - start > 40000 or end - x['timestamp'][-1] > 40000:
        raise ValueError('Missing complete diagnostic window/boundary')
    for name in ('timestamp', 'timestamp_sample', 'input_timestamp'):
        if np.max(np.diff(x[name].astype(np.int64))) > 40000:
            raise ValueError('Diagnostic gap ' + name)
    mode, axes, p = job['mode'], job['axes'], job['parameters']
    for name, value in dict(requested_mode=mode, effective_mode=mode, requested_axes=axes, effective_axes=axes,
                            pending=0, reject=0, inner_mode=0, inner_axes=0, inner_divisor=1,
                            inner_valid=1, fault=0, failsafe=0, timing=0, sta_fault=0, config_pending=0).items():
        if np.any(x[name] != value):
            raise ValueError('Invalid mode/lifecycle/inner state ' + name)
    active = x['enabled'].astype(bool)
    if not np.any(active) or np.any(x['valid'][active] != 1):
        raise ValueError('No valid actual outputs')
    if np.any(x['pid_calls'][active] != 1):
        raise ValueError('First invocation/failsafe retry is not a valid task sample')
    if np.any(~np.isfinite(x['raw_dt'][active])) or np.any(x['raw_dt'][active] < .002) or np.any(x['raw_dt'][active] > .04):
        raise ValueError('Real sensor h outside frozen [2,40] ms domain')
    if np.any(np.diff(x['update_seq'].astype(np.int64)) != x['pid_calls'][1:]):
        raise ValueError('Controller invocation sequence mismatch')
    if not np.allclose(x['raw_dt'][1:], np.diff(x['timestamp_sample'].astype(np.int64))*1e-6, atol=1e-7, rtol=0):
        raise ValueError('raw_dt not actual sensor delta')
    if not np.allclose(x['used_dt'], np.clip(x['input_dt'], .002, .04), atol=1e-7, rtol=0):
        raise ValueError('Legacy PID dt semantics changed')
    if not np.allclose(vector(x, 's'), vector(x, 'v') - vector(x, 'v_sp'), atol=1e-7, rtol=0, equal_nan=True):
        raise ValueError('Wrong consumed error sign/target')
    if steady and (not np.all(active) or not np.all(x['armed']) or np.any(x['reset_bits']) or np.any(x['sta_flags'].astype(int) & (1 | 2 | 4 | 64 | 128))):
        raise ValueError('Steady window reset/priming/latch/inactive')
    initialize()
    from analyze_v03 import check_inner_evidence
    check_inner_evidence(x)
    if new_metadata:
        expected_metadata = dict(variant_req=mode, variant_eff=mode, sta_pending=0)
        # sta_reject describes STA gain/epsilon validity, not PID admissibility.
        # A default PID with unused zero STA gains may legitimately set it.
        if mode != 0:
            expected_metadata['sta_reject'] = 0
        for name, value in expected_metadata.items():
            if np.any(q[name] != value):
                raise ValueError('STA configuration metadata mismatch ' + name)
        if steady and np.any(np.diff(q['sta_gen'].astype(np.int64)) != 0):
            raise ValueError('Armed configuration generation changed')
        if not np.array_equal(q['sta_gen'], x['config_generation']):
            raise ValueError('STA configuration generation differs across exact join')
        for axis, suffix in enumerate('XYZ'):
            epsilon = p['MPC_VC_EPS_' + suffix]
            if not np.allclose(q[f'eps_req[{axis}]'], epsilon, rtol=0, atol=1e-7):
                raise ValueError('Requested epsilon differs from frozen config')
            effective = q[f'eps_eff[{axis}]']
            if mode == 3 and axes & (1 << axis):
                if not np.allclose(effective, epsilon, rtol=0, atol=1e-7):
                    raise ValueError('Wrong effective epsilon')
            elif not np.all(np.isnan(effective)):
                raise ValueError('Effective epsilon on unselected/nonregularized axis')
    elif mode == 3:
        raise ValueError('MODE3 requires new effective-epsilon evidence')
    if mode != 3:
        cadence = cadence_checks().check(x, q, job, steady)
    else:
        cadence = check_regularized(x, q, job, steady)
    for name in ('a_req', 'a_proxy', 'thrust'):
        if not np.all(np.isfinite(vector(x, name)[active])):
            raise ValueError('Nonfinite actual output/proxy ' + name)
    proxy = vector(x, 'thrust') * (9.80665 / x['hover_thrust'][:, None])
    proxy[:, 2] += 9.80665
    if not np.allclose(vector(x, 'a_proxy')[active], proxy[active], atol=5e-6, rtol=0):
        raise ValueError('Thrust mapping proxy mismatch; not a measured acceleration')
    return dict(component_valid=True, flight_accepted=False, samples=len(x['timestamp']),
                start_us=int(start), end_us=int(end), steady=steady, cadence=cadence,
                scope='Offline components only; complete R03 provenance/task/safety/landing gates still mandatory')


def check_regularized(x, q, job, steady):
    axes, p = job['axes'], job['parameters']
    for name, value in dict(div_req=1, div_eff=1, div_pending=0, div_reject=0, control_fault=0, clock=1).items():
        if np.any(q[name] != value):
            raise ValueError('RSTA cadence ' + name)
    enabled = x['enabled'].astype(bool)
    for name in ('control_updated', 'control_held'):
        if np.any(~np.isin(q[name], (0, 1))):
            raise ValueError('Nonboolean cadence flag')
    updated = q['control_updated'].astype(bool)
    if np.any(q['control_held']) or not np.array_equal(updated, enabled):
        raise ValueError('DIV1 update/hold ownership')
    if np.any(np.diff(q['control_seq'].astype(np.int64)) != updated[1:]):
        raise ValueError('Real update sequence gap')
    if not np.allclose(q['h'][updated], x['used_dt'][updated], atol=1e-7, rtol=0):
        raise ValueError('Selection PID h changed; RSTA uses separate raw_dt')
    for name in ('path_ns', 'module_ns'):
        if np.any(q[name][enabled] <= 0):
            raise ValueError('Missing host cost ' + name)
    correction, ff = vector(q, 'correction'), vector(x, 'a_ff')
    expected = np.where(np.isfinite(correction), np.where(np.isfinite(ff), ff, 0) + correction, ff)
    if not np.allclose(vector(x, 'a_req')[enabled], expected[enabled], atol=2e-6, rtol=0):
        raise ValueError('Acceleration FF missing/double counted')
    if np.any(x['active_axes'].astype(int) & ~axes) or np.any(x['committed_axes'].astype(int) & ~axes):
        raise ValueError('Unselected axis active/committed')
    commits = x['committed_axes'] != 0
    if np.any(commits & ~updated) or np.any(x['committed_axes'][commits] != x['active_axes'][commits]):
        raise ValueError('Partial or held atomic commit')
    if steady and (np.any(x['active_axes'] != axes) or np.any(x['committed_axes'] != axes) or np.any(x['pid_axes'] != (7 ^ axes))):
        raise ValueError('Not engaged or wrong unselected PID axes')
    if axes & 4:
        if np.any(~np.isin(x['z_phase'], (0, 1, 2, 3, 4))) or (steady and np.any(x['z_phase'] != 3)):
            raise ValueError('Invalid/unengaged Z phase')
    elif np.any(x['z_phase']) or np.any(x['z_hte_shift']):
        raise ValueError('Unselected Z state')
    check_lifecycle(x, q, job)
    for axis, suffix in enumerate('XYZ'):
        if not axes & (1 << axis):
            for field in ('nu_before', 'nu_ideal', 'nu_applied', 'a_sta'):
                if not np.all(np.isnan(x[f'{field}[{axis}]'])):
                    raise ValueError('RSTA state leaked onto PID axis')
            continue
        commit = (x['committed_axes'].astype(int) & (1 << axis)) != 0
        l1, l2, bound, limit, epsilon = [p[k + suffix] for k in ('MPC_VC_L1_', 'MPC_VC_L2_', 'MPC_VC_NU_', 'MPC_VC_A_', 'MPC_VC_EPS_')]
        before, ideal, applied, raw = [x[f'{k}[{axis}]'] for k in ('nu_before', 'nu_ideal', 'nu_applied', 'a_sta')]
        if np.any(~np.isfinite(applied[enabled])) or np.any(abs(applied[enabled]) > bound + 1e-6):
            raise ValueError('Invalid/beyond-limit applied nu')
        if np.any(commit):
            psi, rho = nonlinear(x[f's[{axis}]'][commit], epsilon)
            expected_raw = before[commit] - l1 * psi
            expected_ideal = before[commit] - x['raw_dt'][commit] * l2 * rho
            if not np.allclose(raw[commit], expected_raw, atol=2e-6, rtol=0):
                raise ValueError('RSTA old-nu/Psi output mismatch')
            if not np.allclose(ideal[commit], expected_ideal, atol=2e-7, rtol=0):
                raise ValueError('RSTA rho/raw-dt candidate mismatch')
            if not np.allclose(correction[commit, axis], np.clip(raw[commit], -limit, limit), atol=2e-6, rtol=0):
                raise ValueError('RSTA applied correction limit mismatch')
            next_nu = np.clip(ideal, -bound, bound)
            delta = next_nu - before
            constrained = x['constraint_bits'] != 0 if axis < 2 else (x['constraint_bits'].astype(int) & 6) != 0
            outward = ((raw - np.clip(raw, -limit, limit)) * delta > 0) | (constrained & ((x[f'a_req[{axis}]'] - x[f'a_proxy[{axis}]']) * delta > 0))
            next_nu = np.where(outward, before, next_nu)
            if not np.allclose(applied[commit], next_nu[commit], atol=2e-7, rtol=0):
                raise ValueError('RSTA protected applied state mismatch')
        if steady:
            previous = applied[:-1] + (x['z_hte_shift'][1:] if axis == 2 else 0)
            if not np.array_equal(before[1:], previous):
                raise ValueError('Stale/foreign nu or missing HTE rebase')
    return dict(updates=int(updated.sum()), holds=0, true_h_min_s=float(x['raw_dt'][updated].min()),
                true_h_max_s=float(x['raw_dt'][updated].max()), formula='piecewise rho/Psi with OLD nu',
                applied_state='bounded/frozen candidate; not the unconstrained ideal recursion')


def check_lifecycle(x, q, job):
    """All rows, including ground/ramp/priming/acceleration-only, not just hover."""
    axes, p = job['axes'], job['parameters']
    n = len(x['timestamp']); valid_mask = np.zeros(n, dtype=np.uint8)
    target_mask = np.zeros(n, dtype=np.uint8)
    for axis in range(3):
        target_mask |= np.isfinite(x[f'v_sp[{axis}]']).astype(np.uint8) << axis
        valid_mask |= (np.isfinite(x[f'v_sp[{axis}]']) & np.isfinite(x[f'v[{axis}]']) &
                       np.isfinite(x[f'v_dot[{axis}]'])).astype(np.uint8) << axis
    phase = x['z_phase']; flags = x['sta_flags'].astype(int)
    priming = (flags & 1) != 0; inactive = (flags & 2) != 0
    selected_active = target_mask & axes
    expected_pid = valid_mask & (7 ^ axes)
    if axes & 4:
        if np.any(~np.isin(phase, (1, 2, 3, 4))):
            raise ValueError('Selected Z has no valid lifecycle phase')
        ground, boundary = phase == 1, phase == 2
        pid_boundary = ground | boundary | ((phase == 4) & (axes == 4))
        expected_pid = np.where(pid_boundary, valid_mask, expected_pid)
        if np.any(x['active_axes'][ground | boundary]) or np.any(x['committed_axes'][ground | boundary]):
            raise ValueError('Ground/handover claims STA takeover/integration')
        if np.any(boundary & ~priming) or np.any(boundary[1:] & boundary[:-1]):
            raise ValueError('PID handover must be one priming boundary frame')
        if np.any((phase == 3) & ((selected_active & 4) == 0)) or np.any((phase == 4) & ((selected_active & 4) != 0)):
            raise ValueError('Z phase inconsistent with velocity target enable')
        normal = (phase == 3) | (phase == 4)
        if np.any(x['active_axes'][normal] != selected_active[normal]):
            raise ValueError('Actual active axes inconsistent with Z handoff')
    else:
        ground = inactive; boundary = priming
        if np.any(phase):
            raise ValueError('Horizontal-only configuration has Z lifecycle')
        if np.any(x['active_axes'][~inactive] != selected_active[~inactive]):
            raise ValueError('Horizontal active axes inconsistent with target')
    if np.any(x['pid_axes'] != expected_pid):
        raise ValueError('Actual PID calculation axes disagree with lifecycle')
    normal_commit = ~priming & ~inactive
    if np.any(x['committed_axes'][normal_commit] != x['active_axes'][normal_commit]):
        raise ValueError('Normal active update missing atomic commit')
    if np.any(x['committed_axes'][priming | inactive]):
        raise ValueError('Priming/inactive frame integrated')
    for axis, suffix in enumerate('XYZ'):
        if not axes & (1 << axis): continue
        applied, before = x[f'nu_applied[{axis}]'], x[f'nu_before[{axis}]']
        if np.any(~np.isfinite(applied)) or np.any(abs(applied) > p['MPC_VC_NU_' + suffix] + 1e-6):
            raise ValueError('Lifecycle nu must remain finite and bounded')
        if np.any(applied[ground] != 0):
            raise ValueError('Ground/inactive state did not reset')
        if axes & 4 and np.any(boundary):
            chosen = boundary & ((selected_active & (1 << axis)) != 0)
            if np.any(chosen):
                psi, _ = nonlinear(x[f's[{axis}]'][chosen], p['MPC_VC_EPS_' + suffix])
                seed = q[f'correction[{axis}]'][chosen] + p['MPC_VC_L1_' + suffix] * psi
                if not np.allclose(applied[chosen], seed, atol=2e-6, rtol=0):
                    raise ValueError('Bounded PID-to-RSTA seed mapping mismatch')
        consecutive = normal_commit[1:] & ((flags[1:] & 128) == 0) & ((x['active_axes'][1:].astype(int) & (1 << axis)) != 0)
        previous = applied[:-1] + (x['z_hte_shift'][1:] if axis == 2 else 0)
        if not np.array_equal(before[1:][consecutive], previous[consecutive]):
            raise ValueError('Nonsteady state continuity/HTE mismatch')


def rate_and_actuator_evidence(log, start, end):
    """Actual whole-rate stream plus exact sample-key actuator partial coverage."""
    cp = clock_policy()
    d = log.get_dataset('sta_rate_ctrl_status').data
    cp.strict_clock(d['timestamp']); cp.strict_clock(d['timestamp_sample'])
    m = (d['timestamp'] >= start) & (d['timestamp'] < end)
    if np.count_nonzero(m) < 600 or d['timestamp'][m][0] - start > 40000 or end - d['timestamp'][m][-1] > 40000:
        raise ValueError('Missing whole-flight actual rate evidence')
    integer_sequence(d['publish_seq'][m], contiguous=True)
    for key, value in dict(requested_mode=0, effective_mode=0, requested_axes=0, effective_axes=0,
                            div_req=1, div_eff=1, fault=0, abort_requested=0, termination=0, experiment_updated=0).items():
        if np.any(d[key][m] != value):
            raise ValueError('Actual rate is not fixed PID: ' + key)
    active = m & d['armed'].astype(bool) & d['rate_enabled'].astype(bool)
    if not np.any(active) or np.any(~d['measurement_valid'][active].astype(bool)) or np.any(~d['output_valid'][active].astype(bool)) or np.any(d['timing_status'][active]):
        raise ValueError('Invalid active rate PID evidence')
    for key in ('research_roll_addition', 'research_pitch_addition', 'research_yaw_addition'):
        if np.any(d[key][m] != 0):
            raise ValueError('Unexpected rate research excitation')
    output = log.get_dataset('actuator_controls_0').data
    cp.strict_clock(output['timestamp_sample'])
    keys = d['timestamp_sample'][m]
    common, a, b = np.intersect1d(keys, output['timestamp_sample'], return_indices=True)
    if len(common) < 2:
        raise ValueError('No exact actuator samples')
    gaps = np.r_[common[0] - keys[0], np.diff(common), keys[-1] - common[-1]]
    if len(common) / len(keys) < .8 or np.max(gaps) > 250000:
        raise ValueError('Insufficient actual actuator partial coverage/boundary')
    for axis in range(3):
        if not np.array_equal(d[f'c_applied[{axis}]'][m][a], output[f'control[{axis}]'][b]):
            raise ValueError('Actual emitted rate command differs')
    return dict(rate_samples=int(m.sum()), matched=len(common), coverage=len(common)/len(keys),
                max_gap_including_edges_s=float(np.max(gaps)*1e-6),
                partial_coverage=True, missing_rows_not_reconstructed=True)


def whole_flight_components(log, run, job, events, *, target_validator=None, new_metadata=True):
    """Run whole inherited safety/timing/landing components, without acceptance.

    R03 must bind its specific target validator and frozen run provenance before
    enabling flight acceptance. None of these stages can be replaced by a
    caller-supplied boolean. Archived H/V use the existing exact task validator.
    """
    initialize()
    from position_log import PositionLogView
    from height import height_evidence
    from landing_complete import check_complete
    from imu_health import check_health
    from cli_clock import audit_commands
    run = Path(run)
    names = ('takeoff_command', 'hover_start', 'hover_end', 'land_command', 'landed_disarmed')
    times = [events[k] for k in names]
    # The host records hover_end and the planned land command at the same
    # simulation instant; existing AX04 permits equality at this one boundary.
    if not times[0] < times[1] < times[2] <= times[3] < times[4] or not 90e6 <= times[2] - times[1] <= 92e6:
        raise ValueError('Incomplete/out-of-order whole-flight event intervals')
    if log.dropouts or getattr(log, 'file_corruption', False):
        raise ValueError('ULog dropout/corruption')
    view = log if isinstance(log, PositionLogView) else PositionLogView(log)
    view.get_dataset('vehicle_local_position')
    d = view.get_dataset('sta_velocity_ctrl_status').data
    selection = view.get_dataset('velocity_ctrl_selection').data
    cp = clock_policy(); policy = cp.AttitudeClockPolicy()
    attitude = policy.data(view)
    target = view.get_dataset('vehicle_attitude_setpoint').data
    results = dict(position=view.position_log_evidence,
        attitude_whole=policy.safety(attitude, target, times[0], times[4], check_yaw=False),
        attitude_observation=policy.safety(attitude, target, times[1], times[2]),
        state_whole=check_components(d, selection, job, times[0], times[4], new_metadata=new_metadata),
        state_observation=check_components(d, selection, job, times[1], times[2], steady=True, new_metadata=new_metadata),
        height=height_evidence(view, run, d, events, attitude_policy=policy),
        landing=check_complete(view, events, json.loads((run / 'landing_context.json').read_text())),
        imu=check_health(view, times[3], times[4]),
        rate_actuator=rate_and_actuator_evidence(view, times[0], times[4]),
        cli=audit_commands(run / 'commands.jsonl'))
    if target_validator is None:
        if job.get('task') not in ('H', 'V'):
            raise ValueError('No frozen R03 task-specific consumed-target validator')
        target_validator = task_checks().check_targets
    results['consumed_targets'] = target_validator(view, d, events, job)
    results['actual_output'] = cp.exact_output_match(d, view.get_dataset('vehicle_local_position_setpoint').data,
        'output_timestamp', [(f'v_sp[{i}]', ('vx', 'vy', 'vz')[i]) for i in range(3)] +
        [(f'a_req[{i}]', f'acceleration[{i}]') for i in range(3)] +
        [(f'thrust[{i}]', f'thrust[{i}]') for i in range(3)], times[0], times[4])
    results['flight_accepted'] = False
    results['remaining'] = ['R03 exact source/firmware/model/parameter/seed/budget binding',
        'R03 task-specific target/trajectory windows and quantitative performance gates',
        'Actual MODE3 complete flight evidence (none exists in R02)',
        'R03 runner-owned full parameter archive plus shutdown restoration receipt']
    return results
