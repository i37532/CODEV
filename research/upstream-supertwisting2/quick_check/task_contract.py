"""Pure targets for the frozen eight-attempt exploratory Offboard batch."""

import math
from collections.abc import Mapping
from enum import Enum
from numbers import Real
from types import MappingProxyType


class Phase(str, Enum):
    PRESTREAM = 'prestream'
    CLIMB = 'climb'
    HOVER = 'hover'
    STEP_UP = 'step_up'
    STEP_DOWN = 'step_down'
    VELOCITY = 'velocity'
    RECOVER = 'recover'
    DESCEND = 'descend'


MAX_ATTEMPTS = 8
SYSTEM_ORDER = ('PID', 'STA2', 'RSTA', 'RISTA')
TASK_ORDER = ('position', 'velocity')
BATCH_ORDER = tuple((task, system) for task in TASK_ORDER for system in SYSTEM_ORDER)
TARGET_HEIGHT_M = 2.5
STEP_HEIGHT_M = 2.8
LAND_HANDOFF_HEIGHT_M = 0.3
STABLE_REQUIRED_S = 3.0
STABLE_TIMEOUT_S = 15.0
SETPOINT_HZ = 20

# The runner owns prestream and bounded stable-wait clocks, and AUTO_LAND.
PHASE_DURATION_S = MappingProxyType({
    'climb': 16.0, 'hover': 10.0, 'step_up': 8.0, 'step_down': 8.0,
    'velocity': 12.0, 'descend': 16.0,
})
TASK_PHASES = MappingProxyType({
    'hover': ('prestream', 'climb', 'recover', 'hover', 'recover', 'descend'),
    'position': ('prestream', 'climb', 'recover', 'hover', 'step_up',
                 'step_down', 'recover', 'descend'),
    'velocity': ('prestream', 'climb', 'recover', 'hover', 'velocity',
                 'recover', 'descend'),
})
SAFETY_LIMITS = MappingProxyType({
    'tilt_deg': 15.0, 'xy_speed_m_s': 1.0, 'xy_displacement_m': 2.0,
    'height_range_m': (-0.5, 4.0), 'vertical_speed_m_s': 3.5,
    'hover_height_deviation_m': 1.0, 'hover_vertical_speed_m_s': 0.6,
})
ENTRY_LIMITS = MappingProxyType({
    'height_tolerance_m': 0.3, 'vertical_speed_m_s': 0.2,
    'stable_s': STABLE_REQUIRED_S, 'timeout_s': STABLE_TIMEOUT_S,
})

# MAVLink ignores: position bits 0..2, velocity 3..5, acceleration 6..8,
# force bit 9, yaw bit 10, yaw rate bit 11. Yaw remains active throughout.
POSITION_MASK = 56 | 448 | 2048  # 2552: XYZ position and yaw.
Z_VELOCITY_MASK = 4 | 24 | 448 | 2048  # 2524: XY position, Z velocity, yaw.
_FLOAT32_MAX = 3.4028234663852886e38
_TARGET_FIELDS = frozenset(('kind', 'x', 'y', 'z', 'vx', 'vy', 'vz', 'yaw', 'type_mask'))


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(name + ' must be a finite number')
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(name + ' must be a finite number') from exc
    if not math.isfinite(result):
        raise ValueError(name + ' must be a finite number')
    return result


def validate_dt(dt_s):
    """Return a positive finite duration; booleans and numeric strings fail."""
    value = _finite(dt_s, 'dt_s')
    if value <= 0:
        raise ValueError('dt_s must be positive')
    return value


def _elapsed(elapsed_s):
    value = _finite(elapsed_s, 'elapsed_s')
    if value < 0:
        raise ValueError('elapsed_s must be nonnegative')
    return value


def _phase(phase):
    try:
        return Phase(phase)
    except (TypeError, ValueError) as exc:
        raise ValueError('Unknown task phase') from exc


def validate_origin(origin):
    """Copy the fixed local NED origin and yaw, without modifying the input."""
    if not isinstance(origin, Mapping):
        raise ValueError('origin must map x, y, z and heading')
    result = {}
    for key in ('x', 'y', 'z', 'heading'):
        if key not in origin:
            raise ValueError('Missing origin ' + key)
        result[key] = _finite(origin[key], 'origin.' + key)
        if abs(result[key]) > _FLOAT32_MAX:
            raise ValueError('origin.' + key + ' exceeds MAVLink float32 range')
    return result


def quintic_state(elapsed_s, duration_s, start=0.0, end=1.0):
    """Return value, first and second time derivatives; hold after duration."""
    elapsed = _elapsed(elapsed_s)
    duration = validate_dt(duration_s)
    start, end = _finite(start, 'start'), _finite(end, 'end')
    if elapsed == 0:
        return start, 0.0, 0.0
    if elapsed >= duration:
        return end, 0.0, 0.0
    u = elapsed / duration
    # Evaluate the nearer endpoint to avoid cancellation and overshoot near u=1.
    v = u if u <= 0.5 else 1.0 - u
    endpoint_blend = v**3 * (10.0 + v * (-15.0 + 6.0 * v))
    blend = endpoint_blend if u <= 0.5 else 1.0 - endpoint_blend
    slope = 30.0 * u**2 * (1.0 - u)**2 / duration
    curvature = 60.0 * u * (1.0 - u) * (1.0 - 2.0 * u) / duration / duration
    delta = end - start
    result = (start + delta * blend, delta * slope, delta * curvature)
    if not all(math.isfinite(value) for value in result):
        raise ValueError('Nonfinite quintic result')
    return result


def quintic_max_speed(start, end, duration_s):
    """Exact maximum absolute first derivative, attained at half duration."""
    value = abs(_finite(end, 'end') - _finite(start, 'start')) * 1.875 / validate_dt(duration_s)
    return _finite(value, 'maximum speed')


def height_profile(phase, elapsed_s):
    """Position-phase height and within-phase derivatives, positive upwards."""
    phase, elapsed = _phase(phase), _elapsed(elapsed_s)
    if phase == Phase.CLIMB:
        return quintic_state(elapsed, PHASE_DURATION_S['climb'], 0.0, TARGET_HEIGHT_M)
    if phase == Phase.DESCEND:
        return quintic_state(elapsed, PHASE_DURATION_S['descend'],
                             TARGET_HEIGHT_M, LAND_HANDOFF_HEIGHT_M)
    if phase == Phase.VELOCITY:
        raise ValueError('Velocity phase has no Z position target')
    height = 0.0 if phase == Phase.PRESTREAM else (
        STEP_HEIGHT_M if phase == Phase.STEP_UP else TARGET_HEIGHT_M)
    return height, 0.0, 0.0


def upward_velocity(elapsed_s):
    """Frozen half-open pulses: +0.2 [0,2), zero [2,6), -0.2 [6,8)."""
    elapsed = _elapsed(elapsed_s)
    if elapsed < 2.0:
        return 0.2
    if 6.0 <= elapsed < 8.0:
        return -0.2
    return 0.0


def velocity_height_offset(elapsed_s):
    """Analytic target integral only; zero net integral does not bound drift."""
    elapsed = _elapsed(elapsed_s)
    return 0.2 * min(elapsed, 2.0) - 0.2 * min(max(elapsed - 6.0, 0.0), 2.0)


def validate_target(target):
    """Reject altered masks, nonfinite wire data and active feedforward fields."""
    if not isinstance(target, Mapping) or set(target) != _TARGET_FIELDS:
        raise ValueError('Unexpected target fields')
    kind = target['kind']
    if kind not in ('position', 'z_velocity'):
        raise ValueError('Unsupported target kind')
    expected_mask = POSITION_MASK if kind == 'position' else Z_VELOCITY_MASK
    if type(target['type_mask']) is not int or target['type_mask'] != expected_mask:
        raise ValueError('Unexpected target type_mask')
    for key in ('x', 'y', 'z', 'vx', 'vy', 'vz', 'yaw'):
        value = _finite(target[key], key)
        if abs(value) > _FLOAT32_MAX:
            raise ValueError(key + ' exceeds MAVLink float32 range')
    ignored_fields = ('vx', 'vy', 'vz') if kind == 'position' else ('z', 'vx', 'vy')
    if any(target[key] != 0.0 for key in ignored_fields):
        raise ValueError('Ignored wire fields must be zero')
    if kind == 'z_velocity' and target['vz'] not in (-0.2, 0.0, 0.2):
        raise ValueError('Z velocity must remain the frozen pulse value')
    return dict(target)


def make_target(phase, elapsed_s, origin):
    """Return finite MAVLink payload fields; acceleration and yaw rate are ignored."""
    phase, elapsed, origin = _phase(phase), _elapsed(elapsed_s), validate_origin(origin)
    is_velocity = phase == Phase.VELOCITY
    target = dict(kind='z_velocity' if is_velocity else 'position',
                  x=origin['x'], y=origin['y'], z=0.0, vx=0.0, vy=0.0, vz=0.0,
                  yaw=origin['heading'], type_mask=Z_VELOCITY_MASK if is_velocity else POSITION_MASK)
    if is_velocity:
        target['vz'] = -upward_velocity(elapsed)
    else:
        target['z'] = origin['z'] - height_profile(phase, elapsed)[0]
    return validate_target(target)


def validate_batch_order(order, max_attempts=MAX_ATTEMPTS):
    """Only the eight planned attempts are allowed; stop conditions are external."""
    if type(max_attempts) is not int or max_attempts != MAX_ATTEMPTS:
        raise ValueError('Batch budget must remain eight attempts')
    try:
        actual = tuple(tuple(item) for item in order)
    except TypeError as exc:
        raise ValueError('Invalid batch order') from exc
    if actual != BATCH_ORDER:
        raise ValueError('Batch order or task scope changed')
    return actual
