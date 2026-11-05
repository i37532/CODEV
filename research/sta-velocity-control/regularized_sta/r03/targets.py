"""R03 task-specific recorded consumption. No interpolation or new setpoint source."""
import importlib.util
from pathlib import Path
import sys
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
for path in (REPO / 'research/sta-velocity-control/scripts', REPO / '.px4-python'):
    if str(path) not in sys.path:
        sys.path.append(str(path))


def leaf(name, relative):
    key = 'r03_' + name
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, REPO / relative)
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
    return sys.modules[key]


old = leaf('task_reference', 'research/sta-velocity-control/axis_ablation/ax02/task.py')
SPECS = {'A': ('X', 1, 1, 32), 'B': ('Z', 4, 2, 32),
         'C': ('H', 3, 6, 64), 'D': ('V', 7, 8, 64)}


def spec(job):
    gate = job.get('gate')
    if gate not in SPECS:
        raise ValueError('Unknown R03 gate')
    task, axes, mode, duration = SPECS[gate]
    algorithm = job.get('mode')
    if type(algorithm) is not int or algorithm not in (0, 1, 3):
        raise ValueError('R03 admits explicit PID/ESTA/RSTA modes only')
    if (job.get('task') != task or job.get('axes') != (0 if algorithm == 0 else axes)
            or job.get('divisor') != 1 or job.get('main_duration_s') != duration
            or job['parameters'].get('MPC_VCT_TEST') != mode):
        raise ValueError('Wrong R03 gate/task/axes/window/divisor')
    return task, axes, mode, duration


def windows(job):
    duration = spec(job)[3]
    return [('first_half', 0, duration / 2), ('second_half', duration / 2, duration)]


def waveform(t, amplitude):
    t = np.asarray(t, dtype=float)
    active = (t > 0) & (t < 32)
    return np.where(active, amplitude * np.sin(2*np.pi*t/8) * np.sin(np.pi*t/32)**2, 0.)


def check_waveform(x, job):
    _, _, mode, duration = spec(job)
    t = x['excitation_time'].astype(float)
    if not np.all(np.isfinite(t)) or t[0] >= 0 or t[-1] < duration:
        raise ValueError('Incomplete task clock boundaries')
    active = (t >= 0) & (t < duration)
    if active.sum() < duration*100-10 or np.ptp(t[active]) < duration-.04:
        raise ValueError('Missing main task samples')
    gate = x['timestamp_sample'][active].astype(float) - (t[active]+12)*1e6
    if np.ptp(gate) > 10:
        raise ValueError('Task time is not the same sensor-clock single shot')
    expected = waveform(t, .2 if mode == 1 else .1) if mode in (1, 2) else np.zeros(len(t))
    if not np.allclose(x['excitation'], expected, atol=1e-6, rtol=0):
        raise ValueError('Wrong task injection waveform or amplitude')
    if np.any(x['excitation_y']) or np.any(x['excitation_z']):
        raise ValueError('Unexpected extra velocity injection axis')
    return dict(main_duration_s=duration, samples=int(active.sum()),
                gate_sample_us=float(np.median(gate)), theoretical_added_velocity_integral_m=0 if mode in (1, 2) else None,
                actual_displacement_not_claimed_zero=True)


def equal_topology(actual, expected, label, tolerance=2e-6):
    a, b = np.asarray(actual), np.asarray(expected)
    if np.any(np.isinf(a)) or np.any(np.isinf(b)) or not np.array_equal(np.isfinite(a), np.isfinite(b)):
        raise ValueError('Wrong finite/NaN topology: '+label)
    valid = np.isfinite(b)
    error = float(np.max(np.abs(a[valid]-b[valid]))) if np.any(valid) else 0.
    if error > tolerance:
        raise ValueError('Wrong consumed target/FF: '+label)
    return error


def attitude_match(x, attitude, start, end, job):
    """Same exact partial coverage criterion; bounds also apply to every R03 half."""
    from v04_attitude_clock09 import strict_clock, exact_output_match
    wanted = strict_clock(x['attitude_timestamp']); source = strict_clock(attitude['timestamp'])
    if any(not np.all(np.isfinite(x[f'q_sp[{i}]'])) or not np.all(np.isfinite(attitude[f'q_d[{i}]'])) for i in range(4)):
        raise ValueError('Nonfinite requested/recorded attitude geometry')
    evidence = exact_output_match(x, attitude, 'attitude_timestamp',
        [(f'q_sp[{i}]', f'q_d[{i}]') for i in range(4)], start, end)
    _, di, ai = np.intersect1d(wanted, source, return_indices=True)
    found = np.zeros(len(wanted), dtype=bool); found[di] = True
    t = x['excitation_time']; duration = spec(job)[3]
    intervals = [('observation', np.ones(len(t), dtype=bool)), ('main', (t >= 0)&(t < duration))]
    intervals += [(name, (t >= lo)&(t < hi)) for name, lo, hi in windows(job)]
    evidence['windows'] = {}
    for name, mask in intervals:
        requested, matched = wanted[mask], wanted[mask & found]
        if len(requested) < 2 or len(matched) < 2:
            raise ValueError('Missing attitude window '+name)
        gaps = np.r_[matched[0]-requested[0], np.diff(matched), requested[-1]-matched[-1]]
        coverage = len(matched)/len(requested)
        if coverage < .8 or np.max(gaps) > 250000:
            raise ValueError('Attitude window coverage/boundary '+name)
        evidence['windows'][name] = dict(requested=len(requested), matched=len(matched),
            coverage=coverage, max_gap_including_edges_s=float(np.max(gaps)*1e-6))
    evidence.update(missing_rows_not_reconstructed=True, association='unique exact publication intersection')
    return di, ai, evidence


def check_position_sum(u, x, job):
    """Prove no velocity clamp in this low-amplitude window, not infer its limit.

    Effective velocity constraints have no consumed-key field. Therefore no
    claim about a hidden active clamp is made: every recorded v_sp MUST equal
    position P + available velocity FF + the exact test addition. An active
    clamp, reset or missing consumed local-position record fails this task.
    """
    from v04_attitude_clock09 import strict_clock
    pos = u.get_dataset('vehicle_local_position').data
    source = strict_clock(pos['timestamp']); wanted = x['input_timestamp']
    j = np.searchsorted(source, wanted)
    if np.any(j >= len(source)) or not np.array_equal(source[j], wanted):
        raise ValueError('Missing exact consumed local-position publication')
    if not np.array_equal(pos['timestamp_sample'][j], x['timestamp_sample']):
        raise ValueError('Position consumption sample differs')
    if np.any(x['reset_bits']):
        raise ValueError('Task observation reset is not an unchanged P target')
    mode = spec(job)[2]; error = []
    for axis, name in enumerate(('x', 'y', 'z')):
        p = x[f'p_sp[{axis}]']; ff = x[f'v_ff[{axis}]']
        gain = job['parameters']['MPC_Z_P' if axis == 2 else 'MPC_XY_P']
        position = (p-pos[name][j])*gain
        if not np.all(np.isfinite(position)):
            raise ValueError('Missing finite position P target/state')
        expected = position + np.where(np.isfinite(ff), ff, 0.)
        if (mode == 1 and axis == 0) or (mode == 2 and axis == 2):
            expected += x['excitation']
        error.append(equal_topology(x[f'v_sp[{axis}]'], expected, 'positionP/FF/injection '+name, 3e-6))
    return dict(samples=len(j), max_abs_error=error, exact_input_timestamp=True,
                scope='No active velocity clamp in the observation window; actual downstream thrust constraints checked separately')


def check_targets(u, d, events, job):
    _, _, mode, duration = spec(job)
    start, end = events['hover_start'], events['hover_end']
    m = (d['timestamp'] >= start)&(d['timestamp'] < end); x = {k:v[m] for k,v in d.items()}
    if len(x['timestamp']) < 8900:
        raise ValueError('Missing 90s task target interval')
    timing = check_waveform(x, job)
    source = u.get_dataset('trajectory_setpoint').data
    j, age = old.consumed_targets(source, x)
    offsets = old.offsets(mode, x['excitation_time'])
    errors = {}
    for field, keys, addition in [('p_sp', ('x','y','z'), offsets['p']),
            ('v_ff', ('vx','vy','vz'), offsets['v']),
            ('a_ff', ('acceleration[0]','acceleration[1]','acceleration[2]'), offsets['a'])]:
        errors[field] = []
        for axis, key in enumerate(keys):
            original = source[key][j].astype(float)
            # Only TEST6/8 call the trajectory adapter, which converts NaN FF
            # to zero. TEST1/2 preserve raw topology and add velocity after P.
            if mode in (6, 8) and field != 'p_sp':
                original = np.where(np.isfinite(original), original, 0.)
            errors[field].append(equal_topology(x[f'{field}[{axis}]'], original+addition[:,axis], field))
    position = check_position_sum(u, x, job)
    attitude = u.get_dataset('vehicle_attitude_setpoint').data
    di, ai, evidence = attitude_match(x, attitude, start, end, job)
    yaw = source['yaw'][j]
    if not np.all(np.isfinite(yaw)):
        raise ValueError('Missing requested fixed heading')
    yaw_error = np.angle(np.exp(1j*(attitude['yaw_body'][ai]-yaw[di])))
    if not np.all(np.isfinite(yaw_error)) or np.max(abs(yaw_error)) > 2e-6:
        raise ValueError('Applied heading target differs')
    yaw_rate = np.where(np.isfinite(source['yawspeed'][j]), source['yawspeed'][j], 0.)
    equal_topology(attitude['yaw_sp_move_rate'][ai], yaw_rate[di], 'yaw rate FF')
    return dict(task=job['task'], timing=timing, maximum_target_error=errors,
        source_association='exact diagnostic.setpoint_timestamp, unique raw source; no nearest/dedup fallback',
        max_source_age_us=int(age.max()), position_p=position, attitude=evidence,
        theoretical_reference_displacement_max=float(np.max(np.linalg.norm(offsets['p'], axis=1))),
        fixed_external_trajectory_not_identical_internal_velocity_targets=True)
