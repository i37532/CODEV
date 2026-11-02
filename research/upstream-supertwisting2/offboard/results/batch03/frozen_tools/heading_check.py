"""Opt-in, read-only classification of one pre-task magnetic yaw alignment.

Publication clocks locate *observation intervals*, not the unlogged instant of
an EKF reset. No rows are sorted/deduplicated and no setpoint is compensated.
Historical manifests keep the strict policy in analyze.py.
"""
import math

import numpy as np

POLICY = 'offboard_first_takeoff_alignment_v1'
STRICT = 'strict_no_reset_v1'
CODEV_SCHEMA = 'codev_ecl_v1'
STA2_SCHEMA = 'upstream_sta2_fc3720'
STA2_HEAD = 'fc3720f67767c78cfab668777de13f68562fe2fd'
TOPICS = ('estimator_selector_status', 'estimator_status',
          'estimator_status_flags', 'estimator_event_flags')
PV_COUNTERS = ('xy_reset_counter', 'z_reset_counter', 'vxy_reset_counter', 'vz_reset_counter')
REFERENCES = ('ref_timestamp', 'ref_lat', 'ref_lon', 'ref_alt')
FORBIDDEN_EVENTS = ('reset_vel_to_gps', 'reset_vel_to_flow', 'reset_vel_to_vision',
    'reset_vel_to_zero', 'reset_pos_to_last_known', 'reset_pos_to_gps', 'reset_pos_to_vision',
    'starting_vision_yaw_fusion', 'yaw_aligned_to_imu_gps', 'bad_yaw_using_gps_course',
    'emergency_yaw_reset_mag_stopped', 'stopping_mag_use', 'stopping_navigation')
FORBIDDEN_FLAGS = ('cs_mag_fault', 'cs_mag_field_disturbed', 'cs_ev_yaw', 'cs_gps_yaw')
OLD_WARNING_FIELDS = ('bad_yaw_using_gps_course', 'emergency_yaw_reset_mag_stopped',
                      'stopping_mag_use', 'stopping_navigation')
NEW_STATE_FIELDS = ('cs_gnss_yaw_fault', 'cs_ev_yaw_fault', 'cs_inertial_dead_reckoning',
                    'cs_wind_dead_reckoning', 'cs_fake_pos', 'cs_fake_hgt')
# Existing V04 engineering limits, not fitted to O001. The 500 ms native
# coverage rule is the existing Offboard logger contract, NOT V04's 40 ms
# controller-rate logging. The 40 ms event pairing tolerance stays unchanged.
MAX_NATIVE_GAP_US = 500000
PAIR_US = 40000
CONFIRM_US = 500000
QUIET_US = 1000000
DELTA_MAX_RAD = math.radians(5)
DELTA_TOL_RAD = 1e-4


def require(ok, message):
    if not ok:
        raise ValueError('Heading evidence: ' + message)


def column(data, key):
    require(key in data, 'missing field ' + key)
    v = np.asarray(data[key])
    require(v.ndim == 1 and len(v) == len(data['timestamp']), 'field shape ' + key)
    return v


def integer(data, key, maximum):
    v = column(data, key)
    require(np.isfinite(v).all() and np.all((v >= 0) & (v <= maximum))
            and np.all(v == np.floor(v)), 'invalid integer ' + key)
    return v.astype(np.int64)


def topic(log, name, instance=0):
    matches = [d.data for d in log.data_list if d.name == name and d.multi_id == instance]
    require(len(matches) == 1, 'missing/ambiguous topic %s instance %s' % (name, instance))
    d = matches[0]
    require('timestamp' in d, 'missing publication clock ' + name)
    t = integer(d, 'timestamp', np.iinfo(np.int64).max)
    require(len(t) > 0 and np.all(t > 0) and np.all(np.diff(t) > 0), 'non-increasing publication ' + name)
    for key, v in d.items():
        require(np.asarray(v).ndim == 1 and len(v) == len(t), 'array shape ' + name + '.' + key)
    return d


def interval(d, start, end, maximum_gap=None):
    """Include predecessor and successor, so boundary-straddling resets fail."""
    t = d['timestamp'].astype(np.int64)
    lo = int(np.searchsorted(t, start, side='left') - 1)
    hi = int(np.searchsorted(t, end, side='left'))
    require(lo >= 0 and hi < len(t), 'missing complete interval boundaries')
    ix = np.arange(lo, hi + 1)
    if maximum_gap is not None:
        require(end - int(t[max(lo, hi-1)]) <= maximum_gap and
                start - int(t[lo]) <= maximum_gap and
                (len(ix) < 2 or np.max(np.diff(t[ix])) <= maximum_gap), 'stale/gapped periodic evidence')
    return ix


def held(d, start, end):
    t = d['timestamp'].astype(np.int64)
    lo = int(np.searchsorted(t, start, side='right') - 1)
    require(lo >= 0, 'missing preceding state/event')
    return np.arange(lo, int(np.searchsorted(t, end, side='right')))


def constant(d, key, ix):
    values = column(d, key)[ix]
    require(len(values) and np.isfinite(values).all() and np.all(values == values[0]), 'changed/nonfinite ' + key)
    return values[0]


def equals(d, key, ix, expected):
    require(np.all(column(d, key)[ix] == expected), 'unexpected ' + key)


def changes(d, key, ix, maximum=255):
    values = integer(d, key, maximum)
    dx = np.diff(values[ix])
    require(np.all((dx == 0) | ((dx % (maximum + 1)) == 1)), 'counter jump ' + key)
    return ix[1:][dx != 0]


def bracket(d, i):
    require(i > 0, 'reset lacks predecessor')
    return [int(d['timestamp'][i-1]), int(d['timestamp'][i])]


def sample_clock(d, name, repeated=False):
    t = integer(d, 'timestamp_sample', np.iinfo(np.int64).max)
    require(np.all(t > 0) and np.all(t <= d['timestamp']), 'invalid sample/publication relationship ' + name)
    require(np.all(np.diff(t) >= 0 if repeated else np.diff(t) > 0), 'sample clock reversed/repeated ' + name)
    if repeated:
        same = np.flatnonzero(np.diff(t) == 0) + 1
        # Retain every publication; equal samples with conflicting reset evidence
        # are ambiguous, not an excuse to keep only a convenient row.
        for key in ('quat_reset_counter', *('delta_q_reset[%d]' % i for i in range(4))):
            v = column(d, key)
            require(np.all(v[same] == v[same-1]), 'ambiguous same-sample reset evidence ' + key)


def estimator_profile(log, flags, ev, schema):
    """Explicit versioned contracts, never 'missing field means no fault'.

    New upstream has no warning counter. Its resetYawToEKFGSF always sets
    yaw_aligned_to_imu_gps, and emergency recovery sets mag/EV/GNSS fault bits.
    Require those and continuous mag/navigation state instead; do not claim a
    reconstructed warning history. Reject mixed or unpinned schemas.
    """
    if schema == CODEV_SCHEMA:
        require('cs_gnss_yaw' not in flags, 'mixed estimator schema')
        return FORBIDDEN_FLAGS, FORBIDDEN_EVENTS, ('information_event_changes', 'warning_event_changes')
    require(schema == STA2_SCHEMA, 'unknown estimator schema')
    require(getattr(log, 'msg_info_dict', {}).get('ver_sw') == STA2_HEAD, 'unverified upstream firmware version')
    require('cs_gps_yaw' not in flags and 'warning_event_changes' not in ev
            and not any(key in ev for key in OLD_WARNING_FIELDS), 'mixed upstream estimator schema')
    flag_keys = tuple('cs_gnss_yaw' if key == 'cs_gps_yaw' else key for key in FORBIDDEN_FLAGS) + NEW_STATE_FIELDS
    event_keys = tuple(key for key in FORBIDDEN_EVENTS if key not in OLD_WARNING_FIELDS)
    event_keys += ('reset_hgt_to_baro', 'reset_hgt_to_gps', 'reset_hgt_to_rng', 'reset_hgt_to_ev')
    # Check even if there are no changed event rows in the interval.
    for key in (*event_keys, 'information_event_changes'):
        column(ev, key)
    column(flags, 'cs_mag')
    return flag_keys, event_keys, ('information_event_changes',)


def audit(log, start, end, preparation_end, scored_start, origin, *, schema=CODEV_SCHEMA):
    require(not log.dropouts and not getattr(log, 'file_corruption', False), 'ULog dropout/corruption')
    require(0 < start < preparation_end <= scored_start < end, 'invalid phase boundaries')
    p, att = topic(log, 'vehicle_local_position'), topic(log, 'vehicle_attitude')
    sample_clock(p, 'position')
    sample_clock(att, 'attitude', repeated=True)
    pi = interval(p, start, end, MAX_NATIVE_GAP_US)
    ai = interval(att, start, end, MAX_NATIVE_GAP_US)
    for key in PV_COUNTERS:
        require(not len(changes(p, key, pi)), 'position/velocity reset ' + key)
    for key in REFERENCES:
        constant(p, key, pi)
    for key in ('xy_valid', 'z_valid', 'v_xy_valid', 'v_z_valid'):
        equals(p, key, pi, 1)

    selector = topic(log, 'estimator_selector_status')
    si = interval(selector, start, end, 1200000)
    primary = int(constant(selector, 'primary_instance', si))
    require(0 <= primary <= 8 and primary == constant(selector, 'primary_instance', si), 'invalid primary instance')
    constant(selector, 'instance_changed_count', si)
    for key, expected in (('healthy[%d]' % primary, 1), ('gyro_fault_detected', 0), ('accel_fault_detected', 0)):
        equals(selector, key, si, expected)
    est = topic(log, 'estimator_status', primary)
    flags = topic(log, 'estimator_status_flags', primary)
    ev = topic(log, 'estimator_event_flags', primary)
    flag_keys, event_keys, event_counters = estimator_profile(log, flags, ev, schema)
    ei = interval(est, start, end, 500000)
    fi = interval(flags, start, end, 1200000)
    equals(est, 'filter_fault_flags', ei, 0)
    equals(flags, 'cs_yaw_align', fi, 1)
    for key in (*flag_keys, *(k for k in flags if k.startswith('fs_'))):
        equals(flags, key, fi, 0)
    if schema == STA2_SCHEMA:
        equals(flags, 'cs_mag', fi, 1)
    # Event-only streams have no heartbeat. Require a pre-interval snapshot and
    # intact counter history, never treat an old snapshot as a new event.
    vi = held(ev, start, end)
    for key in event_counters:
        changes(ev, key, vi, 2**32-1)
    new = vi[ev['timestamp'][vi] > start]
    for key in event_keys:
        equals(ev, key, new, 0)

    status, land, takeoff = (topic(log, name) for name in
        ('vehicle_status', 'vehicle_land_detected', 'takeoff_status'))
    for key in ('failsafe', 'failure_detector_status'):
        equals(status, key, held(status, start, end), 0)
    pr = changes(p, 'heading_reset_counter', pi)
    qr = changes(att, 'quat_reset_counter', ai)
    er = changes(est, 'reset_count_quat', ei)
    aligned = integer(flags, 'cs_mag_aligned_in_flight', 1)
    fd = np.diff(aligned[fi])
    # ECL controlMagFusion clears only this boolean on ground; that is NOT a
    # yaw/quaternion reset. Counter checks still cover the entire landing tail.
    falling = fi[1:][fd == -1]
    require(len(falling) <= 1, 'repeated alignment flag clearing')
    for index in falling:
        when = int(flags['timestamp'][index])
        require(when > scored_start, 'alignment flag cleared before task')
        equals(flags, 'cs_in_air', np.asarray([index]), 0)
        equals(land, 'landed', held(land, when, when), 1)
        equals(land, 'ground_contact', held(land, when, when), 1)
    fr = fi[1:][fd == 1]
    require(len(pr) <= 1 and len(pr) == len(qr) == len(er) == len(fr),
            'repeated/unpaired heading, quaternion, estimator or alignment transition')
    evidence = dict(policy=POLICY, estimator_schema=schema, primary_instance=primary, interval_us=[start, end],
                    classification='no_reset', event_count=len(pr), target_yaw_changed=False,
                    warning_event_counter_available=schema == CODEV_SCHEMA,
                    ground_flag_clear_us=[int(flags['timestamp'][i]) for i in falling])
    if not len(pr):
        return evidence

    i, q, e, f = (int(rows[0]) for rows in (pr, qr, er, fr))
    pb, qb, eb = bracket(p, i), bracket(att, q), bracket(est, e)
    # Intersect observed old/new-counter intervals instead of pretending the
    # first decimated record is the physical event instant. A <=40 ms offset
    # between pose streams is allowed, as in the original V04 contract.
    lower, upper = max(pb[0], qb[0]-PAIR_US, eb[0]), min(pb[1], qb[1]+PAIR_US, eb[1])
    require(lower < upper, 'disjoint reset observation intervals')
    require(all(start <= b[0] < b[1] < preparation_end for b in (pb, qb, eb)),
            'reset outside climb preparation or straddling boundary')
    ft = int(flags['timestamp'][f])
    require(lower < ft <= upper + CONFIRM_US,
            'missing/late/disjoint alignment confirmation')
    confirmed = max(pb[1], qb[1], eb[1], ft)
    require(confirmed < preparation_end and confirmed + QUIET_US <= scored_start,
            'no complete pre-task confirmation/quiet interval')
    for key, expected in (('arming_state', 2), ('nav_state', 14)):
        equals(status, key, held(status, lower, confirmed), expected)
    for key in ('landed', 'ground_contact', 'maybe_landed'):
        equals(land, key, held(land, lower, confirmed), 0)
    equals(takeoff, 'takeoff_state', held(takeoff, lower, confirmed), 5)
    equals(flags, 'cs_in_air', np.asarray([f]), 1)
    h = float(origin['z']) - float(column(p, 'z')[i])
    require(math.isfinite(h) and 1 <= h <= 3, 'alignment outside preparation height')
    delta = float(column(p, 'delta_heading')[i])
    require(abs(delta) <= DELTA_MAX_RAD, 'heading delta exceeds 5 degrees')
    w, x, y, z = (float(column(att, 'delta_q_reset[%d]' % axis)[q]) for axis in range(4))
    require(abs(w*w+x*x+y*y+z*z-1) <= .001, 'invalid reset quaternion norm')
    qdelta = math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))
    require(abs(math.remainder(qdelta-delta, 2*math.pi)) <= DELTA_TOL_RAD, 'quaternion/heading delta mismatch')
    # ROS yaw remains the original immutable command: no once-only recapture or
    # extra delta is sent here. Require settling against THAT command instead.
    quiet = interval(p, scored_start-QUIET_US, scored_start, MAX_NATIVE_GAP_US)
    errors = np.arctan2(np.sin(column(p, 'heading')[quiet]-origin['heading']),
                        np.cos(column(p, 'heading')[quiet]-origin['heading']))
    require(np.max(np.abs(errors)) <= math.radians(1), 'not quiet against fixed task yaw')
    evidence.update(classification='expected_first_takeoff_alignment',
        position_observation_us=pb, attitude_observation_us=qb, estimator_observation_us=eb,
        possible_event_us=[lower, upper], alignment_flag_us=ft, confirmed_us=confirmed,
        heading_delta_rad=delta, quaternion_delta_rad=qdelta, height_m=h,
        quiet_window_us=[scored_start-QUIET_US, scored_start],
        maximum_quiet_yaw_error_rad=float(np.max(np.abs(errors))))
    return evidence
