"""Raw, causal 3 s entry window; same numerical rules as the final analyzer.

Coarse asynchronous CLI observations remain diagnostic, not evidence of a
continuous window. This module never alters historical acceptance or deadlines.
"""
import numpy as np
from analyze_v00 import previous_indices


def check_entry_window(u, ref, end):
    if not np.isfinite(end) or end <= 3e6:
        raise ValueError('Invalid entry window end')
    for name in ('vehicle_local_position', 'trajectory_setpoint', 'vehicle_status',
                 'vehicle_land_detected', 'sta_velocity_ctrl_status'):
        times = u.get_dataset(name).data['timestamp']
        if not len(times) or not np.all(np.isfinite(times)) or np.any(np.diff(times.astype(np.int64)) <= 0):
            raise ValueError('Nonmonotonic entry topic ' + name)
    start = end - 3e6
    pos = u.get_dataset('vehicle_local_position').data
    ix = np.flatnonzero((pos['timestamp'] >= start) & (pos['timestamp'] <= end))
    if len(ix) < 250 or pos['timestamp'][ix[0]] - start > 40000 or end - pos['timestamp'][ix[-1]] > 40000:
        raise ValueError('Missing 3s entry window')
    stamps = pos['timestamp'][ix].astype(np.int64)
    if np.any(np.diff(stamps) <= 0) or np.max(np.diff(stamps)) > 40000:
        raise ValueError('Entry log gap')
    # Strictly validate samples as well; do not merge/reset/borrow future rows.
    samples = pos['timestamp_sample'][ix].astype(np.int64)
    if np.any(samples <= 0) or np.any(samples > stamps) or np.any(np.diff(samples) <= 0):
        raise ValueError('Invalid entry sample clock')
    height = ref['position']['z'] - pos['z'][ix]
    if not np.all(np.isfinite(height)) or not np.all(np.isfinite(pos['vz'][ix])):
        raise ValueError('Nonfinite entry measurement')
    if np.any((height < 2) | (height > 3)) or np.any(np.abs(pos['vz'][ix]) >= .2):
        raise ValueError('Unstable 3s height entry')
    for key in ('xy_valid', 'z_valid', 'v_xy_valid', 'v_z_valid'):
        if not np.all(pos[key][ix]): raise ValueError('Invalid entry estimate')
    for name, fields in [('vehicle_status', dict(arming_state=2, nav_state=4, failsafe=0)),
                         ('vehicle_land_detected', dict(landed=0, ground_contact=0))]:
        src = u.get_dataset(name).data
        j, _ = previous_indices(src['timestamp'], pos['timestamp'][ix])
        for key, val in fields.items():
            if np.any(src[key][j] != val): raise ValueError('Invalid entry ' + key)
    trajectory = u.get_dataset('trajectory_setpoint').data
    j, _ = previous_indices(trajectory['timestamp'], pos['timestamp'][ix], 40000)
    if not all(np.all(np.isfinite(trajectory[key][j])) for key in ('z', 'vz', 'yaw')):
        raise ValueError('Nonfinite entry trajectory')
    if (np.any(np.abs(trajectory['z'][j] - ref['target_z']) > .05)
            or np.any(np.abs(trajectory['vz'][j]) > .05)
            or np.any(np.abs(np.angle(np.exp(1j * (trajectory['yaw'][j] - ref['yaw'])))) > .001)):
        raise ValueError('Wrong entry trajectory')
    d = u.get_dataset('sta_velocity_ctrl_status').data
    dm = (d['timestamp'] >= start) & (d['timestamp'] <= end)
    selected = d['timestamp'][dm].astype(np.int64)
    if (len(selected) < 250 or selected[0] - start > 40000 or end - selected[-1] > 40000
            or np.max(np.diff(selected)) > 40000):
        raise ValueError('Missing consumed entry samples')
    if not np.all(np.isfinite(d['p_sp[2]'][dm])) or np.any(np.abs(d['p_sp[2]'][dm] - ref['target_z']) > .05):
        raise ValueError('Wrong consumed height target')
    return dict(ready=True, start=start, end=end, samples=len(ix),
                minimum_height=float(height.min()), maximum_height=float(height.max()))


def entry_ready(u, ref, end):
    try:
        return check_entry_window(u, ref, end)
    except ValueError as exc:
        # Normal convergence may wait only within the EXISTING runner deadline.
        # Missing data, invalid estimates/status, clocks or nonfinite inputs fail.
        if str(exc) not in ('Unstable 3s height entry', 'Wrong entry trajectory', 'Wrong consumed height target'):
            raise
        return dict(ready=False, start=end - 3e6, end=end, reason=str(exc))


def advance_entry(gate, sample, valid, diagnostic, read_log, ref, end):
    """Runner integration: retain the original coarse gate and its 10 s deadline.

    Raw convergence cannot reset/extend that deadline. The caller records this
    return value and only emits hover_start when ready is true.
    """
    if not gate.update(sample, valid, diagnostic):
        return dict(ready=False, reason='coarse_gate_pending', end=end)
    return entry_ready(read_log(), ref, end)
