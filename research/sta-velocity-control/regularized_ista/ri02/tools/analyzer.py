"""Version-1 R-ISTA diagnostic contract, strictly non-authorizing.

The final R03 callback whitelist/whole-group association is reused verbatim.
The new compensated implicit equations are NOT relabelled as MODE3. Root/output
limits retain RI01/R03 bounds. Candidate nu is checked bitwise using numeric05
integer/Fraction arithmetic with p (NOT s); no arbitrary nu allclose tolerance.
No publication deduplication/interpolation is permitted.
"""
import math
import numpy as np

from dependencies import callbacks, candidate_arithmetic, final_analysis

RI_VECTORS = ('p', 'nu_candidate', 'nu_applied', 'a_ideal', 'a_applied',
              'acc_published', 'thrust_published')


def vector(data, name):
    return np.column_stack([data[f'{name}[{i}]'] for i in range(3)])


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def join(status, selection):
    cb = callbacks()
    cb.validate(status)
    cb.validate(selection)
    keys = selection['publish_seq']
    indices = np.searchsorted(keys, status['publish_seq'])
    require(np.all(indices < len(keys)), 'Missing selection row')
    require(np.array_equal(keys[indices], status['publish_seq']), 'Missing exact sequence row')
    result = {k: np.asarray(v)[indices] for k, v in selection.items()}
    for key in ('timestamp_sample', 'input_timestamp', 'requested_mode', 'requested_axes',
                'effective_mode', 'effective_axes', 'pending', 'reject', 'armed', 'enabled', 'pid_calls'):
        require(np.array_equal(status[key], result[key]), 'Exact callback join mismatch: ' + key)
    return result


def closed_admission(status, selection):
    """Actual RI02 production evidence: a request for 4 never becomes output."""
    q = join(status, selection)
    require(np.all(q['ri_version'] == 1), 'Missing R-ISTA schema')
    requested = q['requested_mode'] == 4
    require(np.any(requested), 'No actual MODE4 request evidence')
    require(np.all(q['effective_mode'][requested] != 4), 'Forbidden MODE4 takeover')
    require(np.all((q['reject'][requested].astype(int) & 2) != 0), 'No explicit unimplemented rejection')
    require(not np.any(q['ri_valid']) and not np.any(q['ri_commit_axes']), 'Rejected mode produced candidate/commit')
    for key in RI_VECTORS:
        require(np.all(np.isnan(vector(q, 'ri_' + key))), 'Inactive R-ISTA field must be NaN: ' + key)
    return dict(valid=True, production_mode4_effective=False, flight_accepted=False)


def shape(p, epsilon):
    radius = np.maximum(np.abs(p), epsilon)
    rho = p / radius
    return np.sqrt(radius) * rho, rho


def candidate_nu(root, h, l2, epsilon, old, nxt, declared_epsilon):
    """Reuse only exact rho(input)->nu arithmetic, with the implicit root input.

    Numeric05 knows no MODE. New p's implicit equation and candidate-nu output
    are separately checked here; this does not substitute old Psi(s) control.
    """
    arithmetic = candidate_arithmetic()
    return arithmetic.check_candidate(s=root, h=h, lambda2=arithmetic.binary32(l2),
        epsilon=epsilon, nu_before=old, nu_ideal=nxt,
        declared_lambda2=l2, declared_epsilon=declared_epsilon)


def lifecycle(x, q, profile):
    """Original phase semantics, but implicit seed inverse is independently checked."""
    axes, parameters = profile['axes'], profile['parameters']
    count = len(x['timestamp'])
    target, valid = np.zeros(count, dtype=np.uint8), np.zeros(count, dtype=np.uint8)
    for axis in range(3):
        finite = np.isfinite(x[f'v_sp[{axis}]'])
        target |= finite.astype(np.uint8) << axis
        valid |= (finite & np.isfinite(x[f'v[{axis}]']) & np.isfinite(x[f'v_dot[{axis}]'])).astype(np.uint8) << axis
    require(np.array_equal(np.isfinite(x['v_sp[0]']), np.isfinite(x['v_sp[1]'])), 'Half-enabled XY target')
    flags, phase = x['sta_flags'].astype(int), x['z_phase']
    priming, inactive = (flags & 1) != 0, (flags & 2) != 0
    expected_pid = valid & (7 ^ axes)
    selected_active = target & axes
    if axes & 4:
        require(np.all(np.isin(phase, (1, 2, 3, 4))), 'Missing Z phase')
        ground, boundary = phase == 1, phase == 2
        pid_boundary = ground | boundary | ((phase == 4) & (axes == 4))
        expected_pid = np.where(pid_boundary, valid, expected_pid)
        require(not np.any(x['active_axes'][ground | boundary]) and not np.any(x['committed_axes'][ground | boundary]), 'Ground/ramp/seed falsely committed')
        require(not np.any(boundary & ~priming) and not np.any(boundary[1:] & boundary[:-1]), 'Seed must be one priming frame')
        require(not np.any((phase == 3) & ((selected_active & 4) == 0)) and not np.any((phase == 4) & ((selected_active & 4) != 0)), 'Z target-enable/phase mismatch')
        normal = (phase == 3) | (phase == 4)
        require(np.all(x['active_axes'][normal] == selected_active[normal]), 'Normal Z active mask differs')
    else:
        ground, boundary = inactive, priming
        require(not np.any(phase) and not np.any(x['z_hte_shift']), 'Unselected Z lifecycle/HTE')
        require(np.all(x['active_axes'][~inactive] == selected_active[~inactive]), 'Horizontal active mask differs')
    require(np.array_equal(x['pid_axes'], expected_pid), 'Actual PID axes/lifecycle mismatch')
    normal_commit = ~priming & ~inactive
    require(np.all(x['committed_axes'][normal_commit] == x['active_axes'][normal_commit]), 'Missing normal atomic commit')
    require(not np.any(x['committed_axes'][priming | inactive]), 'Inactive/priming integrated')
    for axis, suffix in enumerate('XYZ'):
        if not axes & (1 << axis):
            continue
        state, old = q[f'ri_nu_applied[{axis}]'], x[f'nu_before[{axis}]']
        require(np.all(np.isfinite(state)) and np.all(abs(state) <= parameters['MPC_VC_NU_' + suffix] + 1e-6), 'Lifecycle state invalid')
        require(np.all(state[ground] == 0), 'Inactive/ground nu did not reset')
        chosen = boundary & ((selected_active & (1 << axis)) != 0) if axes & 4 else np.zeros(count, bool)
        if np.any(chosen):
            h = q['ri_seed_h'][chosen]
            require(np.all(np.isfinite(h)) and np.all((h >= .002) & (h <= .04)), 'Invalid seed h')
            root = q[f'ri_p[{axis}]'][chosen]
            s = x[f's[{axis}]'][chosen]
            l1, l2, eps = [parameters[f'MPC_VC_{key}_{suffix}'] for key in ('L1', 'L2', 'EPS')]
            psi, rho = shape(root, eps)
            residual = root + h * l1 * psi + h * h * l2 * rho - s
            require(np.all(np.isfinite(residual)) and np.all(abs(residual) <= 3e-6 * (1 + abs(s))), 'Seed implicit p mismatch')
            wanted = q[f'correction[{axis}]'][chosen] + l1 * psi + h * l2 * rho
            require(np.allclose(state[chosen], wanted, atol=2e-6, rtol=0), 'Implicit seed inverse mismatch')
            require(not np.any(q['ri_valid'][chosen]) and not np.any(q['ri_strict_axes'][chosen]), 'Seed falsely labeled candidate/implicit commit')
            require(np.all(np.isnan(q[f'ri_nu_candidate[{axis}]'][chosen])) and np.all(np.isnan(q[f'ri_a_ideal[{axis}]'][chosen])), 'Seed invented current candidate')
        consecutive = normal_commit[1:] & ((flags[1:] & 128) == 0) & ((x['active_axes'][1:].astype(int) & (1 << axis)) != 0)
        previous = state[:-1] + (x['z_hte_shift'][1:] if axis == 2 else 0)
        require(np.array_equal(old[1:][consecutive], previous[consecutive]), 'State continuity/HTE differs')


def check(status, selection, profile, start, end, *, steady=False):
    """Offline instrumented MODE4 fixture/new-log component, not flight gate.

    Complete task/model/provenance/landing validation remains the pinned R03
    full-chain composition. This function supplies only new-mode mathematics
    and lifecycle to that composition; it cannot issue an accepted receipt.
    """
    qfull = join(status, selection)
    times = np.asarray(status['timestamp'])
    # Inspect the entire strict predecessor group and end group for chronology
    # above; numerical task window remains [start,end), never last-row-only.
    first = np.searchsorted(times, start, side='left')
    require(first > 0 and end <= times[-1], 'Missing complete boundary/predecessor')
    left = np.searchsorted(times, times[first - 1], side='left')
    stop = np.searchsorted(times, end, side='right')
    boundary = np.arange(left, stop)
    require(len(boundary) >= 2, 'Empty boundary')
    for key in ('timestamp', 'timestamp_sample', 'input_timestamp'):
        require(np.max(np.diff(np.asarray(status[key])[boundary].astype(np.int64))) <= 40000,
                'Diagnostic gap: ' + key)
    for key in ('reset_bits', 'fault', 'failsafe', 'sta_fault'):
        if steady:
            require(not np.any(status[key][boundary]), 'Steady boundary/reset/fault: ' + key)
    mask = (times >= start) & (times < end)
    x = {k: np.asarray(v)[mask] for k, v in status.items()}
    q = {k: np.asarray(v)[mask] for k, v in qfull.items()}
    require(len(x['timestamp']) >= 600 and x['timestamp'][0] - start <= 40000
            and end - x['timestamp'][-1] <= 40000, 'Missing complete diagnostic window')
    axes, p = profile['axes'], profile['parameters']
    require(profile['mode'] == 4 and axes in (1, 4, 3, 7), 'Wrong R-ISTA profile')
    for key, value in dict(requested_mode=4, effective_mode=4, requested_axes=axes, effective_axes=axes,
                           pending=0, reject=0, inner_mode=0, inner_axes=0, inner_divisor=1,
                           inner_valid=1, fault=0, failsafe=0, timing=0, sta_fault=0, config_pending=0).items():
        require(np.all(x[key] == value), 'Wrong mode/lifecycle/inner: ' + key)
    for key, value in dict(ri_version=1, variant_req=4, variant_eff=4, sta_pending=0, sta_reject=0,
                           div_req=1, div_eff=1, div_pending=0, div_reject=0, control_fault=0, clock=1).items():
        require(np.all(q[key] == value), 'Wrong variant/schema/cadence: ' + key)
    active = x['enabled'].astype(bool)
    require(np.any(active) and np.all(x['valid'][active]), 'No valid actual output')
    require(np.array_equal(x['pid_calls'], active.astype(int)), 'Retry/inactive invocation cannot be valid task sample')
    require(np.array_equal(q['control_updated'].astype(bool), active) and not np.any(q['control_held']), 'DIV1 updates/holds')
    require(np.all(np.diff(q['control_seq'].astype(np.int64)) == active[1:]), 'True update sequence gap')
    require(np.all(np.diff(x['update_seq'].astype(np.int64)) == x['pid_calls'][1:]), 'Invocation sequence gap')
    require(np.all(np.isfinite(x['raw_dt'])) and np.all((x['raw_dt'] >= .002) & (x['raw_dt'] <= .04)), 'Invalid raw sample h')
    require(np.allclose(x['raw_dt'][1:], np.diff(x['timestamp_sample'].astype(np.int64)) * 1e-6, atol=1e-7, rtol=0), 'Sample h mismatch')
    require(np.allclose(x['used_dt'], np.clip(x['input_dt'], .002, .04), atol=1e-7, rtol=0), 'Legacy PID h changed')
    require(np.allclose(q['h'][active], x['used_dt'][active], atol=1e-7, rtol=0), 'DIV1 legacy published h changed')
    for key in ('path_ns', 'module_ns'):
        require(np.all(q[key][active] > 0), 'Unavailable host clock ' + key)
    # DIV1 has no held interval. Invented interval bits must not explain a
    # state freeze which this production path could never request.
    require(not np.any(q['interval_pos']) and not np.any(q['interval_neg']), 'DIV1 invented interval constraints')
    require(np.allclose(vector(x, 's'), vector(x, 'v') - vector(x, 'v_sp'), atol=1e-7, rtol=0, equal_nan=True), 'Error sign/target differs')
    require(np.array_equal(q['sta_gen'], x['config_generation']) and np.all(q['sta_gen'] > 0), 'Generation join mismatch/invalid')
    if steady:
        require(np.all(active) and np.all(x['armed']) and not np.any(np.diff(q['sta_gen'])), 'Armed generation changed/inactive')
        require(not np.any(x['sta_flags'].astype(int) & (1 | 2 | 4 | 64 | 128 | 256)), 'Steady priming/inactive/reset/fault/held flag')
        require(np.all(x['active_axes'] == axes) and np.all(x['committed_axes'] == axes)
                and np.all(x['pid_axes'] == (7 ^ axes)), 'Not engaged/wrong PID axes')
    committed = x['committed_axes'].astype(int)
    require(np.array_equal(q['ri_commit_axes'], committed), 'Commit diagnostic differs')
    require(not np.any(committed & ~axes) and np.all(committed[committed != 0] == x['active_axes'][committed != 0]), 'Partial/foreign atomic commit')
    candidate = q['ri_valid'].astype(bool)
    for flag in ('ri_valid', 'ri_cache_valid', 'control_updated', 'control_held'):
        require(np.all(np.isin(q[flag], (0, 1))), 'Malformed boolean diagnostic ' + flag)
    cached = q['ri_cache_valid'].astype(bool)
    require(not np.any(cached) if not axes & 4 else True, 'Unselected Z claims HTE cache')
    require(np.array_equal(q['ri_cache_sample'][cached], x['timestamp_sample'][cached])
            and not np.any(q['ri_cache_sample'][~cached]), 'HTE cache sample identity')
    require(np.array_equal(candidate, committed != 0), 'Candidate validity differs from complete successful commit')
    require(not np.any(q['ri_strict_axes'].astype(int) & ~committed), 'Strict claim outside committed axes')
    lifecycle(x, q, profile)
    correction, ff = vector(q, 'correction'), vector(x, 'a_ff')
    expected_acc = np.where(np.isfinite(correction), correction + np.where(np.isfinite(ff), ff, 0), ff)
    require(np.allclose(vector(x, 'a_req')[active], expected_acc[active], atol=2e-6, rtol=0), 'Acceleration FF missing/doubled')
    require(np.array_equal(vector(q, 'ri_acc_published')[active], vector(x, 'a_req')[active], equal_nan=True), 'Published acceleration mismatch')
    require(np.array_equal(vector(q, 'ri_thrust_published')[active], vector(x, 'thrust')[active], equal_nan=True), 'Published thrust mismatch')
    residual_max = 0.
    for axis, suffix in enumerate('XYZ'):
        eps = p['MPC_VC_EPS_' + suffix]
        require(np.allclose(q[f'eps_req[{axis}]'], eps, atol=1e-7, rtol=0), 'Requested epsilon differs')
        if not axes & (1 << axis):
            require(np.all(np.isnan(q[f'eps_eff[{axis}]'])), 'Effective epsilon on unselected axis')
            for key in ('p', 'nu_candidate', 'nu_applied', 'a_ideal'):
                require(np.all(np.isnan(q[f'ri_{key}[{axis}]'])), 'R-ISTA leaked onto PID axis')
            for key in ('nu_before', 'nu_ideal', 'nu_applied', 'a_sta'):
                require(np.all(np.isnan(x[f'{key}[{axis}]'])), 'Legacy STA field leaked onto PID axis')
            require(np.array_equal(q[f'ri_a_applied[{axis}]'][active], correction[active, axis], equal_nan=True), 'Mixed PID correction differs')
            continue
        require(np.allclose(q[f'eps_eff[{axis}]'], eps, atol=1e-7, rtol=0), 'Effective epsilon differs')
        m = (committed & (1 << axis)) != 0
        l1, l2, cap, limit = [p[f'MPC_VC_{k}_{suffix}'] for k in ('L1', 'L2', 'NU', 'A')]
        root, old, nxt, applied, ideal, output = [q[f'ri_{key}[{axis}]'] if key not in ('nu_before',) else x[f'{key}[{axis}]']
            for key in ('p', 'nu_before', 'nu_candidate', 'nu_applied', 'a_ideal', 'a_applied')]
        seed = (x['z_phase'] == 2) & (q['ri_seed_h'] > 0) & ((x['sta_flags'].astype(int) & 1) != 0)
        require(np.all(np.isnan(nxt[~m])) and np.all(np.isnan(ideal[~m])), 'Absent candidate carries ideal payload')
        require(np.all(np.isnan(root[~m & ~seed])), 'Absent candidate/seed carries root')
        require(np.all(np.isfinite(applied)) and np.all(abs(applied) <= cap + 1e-6), 'Applied state nonfinite/unbounded')
        if not np.any(m):
            continue
        h = q['ri_h'][m]
        require(np.array_equal(h, x['raw_dt'][m]), 'Kernel h must be actual sample h')
        psi, rho = shape(root[m], eps)
        s = x[f's[{axis}]'][m]
        residual = root[m] + h * l1 * psi + h * h * l2 * rho - s
        scaled = abs(residual) / (1 + abs(s))
        require(np.all(np.isfinite(scaled)) and np.all(scaled <= 3e-6), 'Ideal implicit root residual')
        residual_max = max(residual_max, float(scaled.max()))
        for index in np.flatnonzero(m):
            candidate_nu(root[index], q['ri_h'][index], l2, q[f'eps_eff[{axis}]'][index],
                         old[index], nxt[index], eps)
        require(np.allclose(ideal[m], -l1 * psi + nxt[m], atol=2e-6, rtol=0), 'Ideal output must use candidate nu')
        require(np.allclose(output[m], np.clip(ideal[m], -limit, limit), atol=2e-6, rtol=0), 'Applied correction clip differs')
        require(np.array_equal(output[m], correction[m, axis]), 'Actual selected correction differs')
        require(np.array_equal(nxt[m], x[f'nu_ideal[{axis}]'][m]) and np.array_equal(applied[m], x[f'nu_applied[{axis}]'][m]), 'Legacy/new candidate-state fields disagree')
        require(np.array_equal(ideal[m], x[f'a_sta[{axis}]'][m]), 'Legacy/new ideal output differs')
        bounded = np.clip(nxt, -cap, cap)
        delta = bounded - old
        constrained = x['constraint_bits'] != 0 if axis < 2 else (x['constraint_bits'].astype(int) & 6) != 0
        outward = ((ideal - np.clip(ideal, -limit, limit)) * delta > 0) | (constrained & ((x[f'a_req[{axis}]'] - x[f'a_proxy[{axis}]']) * delta > 0))
        expected = np.where(outward, old, bounded)
        require(np.allclose(applied[m], expected[m], atol=2e-7, rtol=0), 'Protected state freeze/bound differs')
        strict = (q['ri_strict_axes'].astype(int) & (1 << axis)) != 0
        exact_ideal = (output == ideal) & (applied == nxt) & ~constrained
        require(np.array_equal(strict[m], exact_ideal[m]), 'Protected output mislabeled strict implicit')
    return dict(component_valid=True, flight_accepted=False, schema=1, samples=len(x['timestamp']),
                max_scaled_implicit_residual=residual_max, actual_mode=4,
                raw_records_preserved=True, deduplicated=False,
                warning='Only ideal candidate satisfies implicit equations; constrained pair is explicitly separate')


def inherited_chain():
    """Unchanged complete final chain; all historical modes retain identity."""
    return final_analysis()
