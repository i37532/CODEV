"""Versioned vehicle_imu-only dual-clock policy; no historical policy mutation.

No sort, dedup, interpolation, resampling or timestamp rewriting. Health windows
include complete boundary publication groups and both clock domains. The actual
strictly later publication seals the final group (important for live ULog tails).
"""
import time
import numpy as np
from landing_health import window as strict_window
from postland import read, TOPICS

GAP_US = 12000  # Existing IMU publication evidence bound, now also sample/age.


def clock(d):
    arrays = []
    for key in ('timestamp', 'timestamp_sample'):
        a = np.asarray(d[key])
        if (a.ndim != 1 or not len(a) or a.dtype.kind not in 'ui'
                or np.any(a <= 0) or np.any(a > np.iinfo(np.int64).max)):
            raise ValueError('Invalid IMU clock representation')
        arrays.append(a.astype(np.int64))
    p, s = arrays
    if (len(p) != len(s) or np.any(np.diff(p) < 0)
            or np.any(np.diff(s) <= 0) or np.any(s > p)):
        raise ValueError('IMU publication/sample order or future sample')
    if any(np.asarray(a).ndim != 1 or len(a) != len(p) for a in d.values()):
        raise ValueError('Inconsistent IMU row lengths')
    return p, s


def bounds(d, start, end, pending=False):
    if not 0 < start < end:
        raise ValueError('Invalid IMU health interval')
    p, s = clock(d)
    left = min(int(np.searchsorted(t, start, side='right') - 1) for t in (p, s))
    if left < 0:
        raise ValueError('Missing IMU start boundary')
    left = int(np.searchsorted(p, p[left], side='left'))
    right = max(int(np.searchsorted(t, end, side='left')) for t in (p, s))
    if right >= len(p):
        if pending: return None
        raise ValueError('Missing IMU end boundary')
    stop = int(np.searchsorted(p, p[right], side='right'))
    if stop == len(p):
        if pending: return None
        raise ValueError('Unsealed IMU end publication group')
    # Successor seals the group, and is itself checked (not silently discarded).
    mask = np.zeros(len(p), dtype=bool); mask[left:stop+1] = True
    if (np.max(np.diff(p[mask])) > GAP_US or np.max(np.diff(s[mask])) > GAP_US
            or np.max(p[mask] - s[mask]) > GAP_US):
        raise ValueError('IMU publication/sample gap or age')
    return mask


def check_imu(d, start, end):
    m = bounds(d, start, end); p, s = clock(d)
    for key in ('delta_angle_dt', 'delta_velocity_dt'):
        v = d[key][m]
        if not np.all(np.isfinite(v)) or np.any(v <= 0) or np.any(v > GAP_US):
            raise ValueError('Invalid IMU integration interval')
    for stem in ('delta_angle', 'delta_velocity'):
        if not np.all(np.isfinite(np.column_stack([d[f'{stem}[{i}]'][m] for i in range(3)]))):
            raise ValueError('Nonfinite IMU integral')
    if np.any(d['delta_velocity_clipping'][m]): raise ValueError('IMU clipping')
    for key in ('accel_device_id', 'gyro_device_id', 'calibration_count'):
        v = d[key][m]
        if not np.all(np.isfinite(v)) or np.any(v != v[0]):
            raise ValueError('IMU device/calibration changed')
        if key.endswith('device_id') and not v[0]: raise ValueError('Missing IMU device')
    return dict(samples=int(m.sum()), clipping=0, publication_ties=int((np.diff(p[m]) == 0).sum()),
                max_publication_gap_us=int(np.diff(p[m]).max()), max_sample_gap_us=int(np.diff(s[m]).max()),
                max_age_us=int((p[m]-s[m]).max()), boundary_groups_complete=True,
                recorded_gap_not_equal_integration=int(np.count_nonzero(np.diff(s[m]) != d['delta_angle_dt'][m][1:])),
                coverage='bounded recorded evidence; not lossless IMU consumption proof')


def check_health(log, start, end):
    if not 0 < start < end: raise ValueError('Invalid landing interval')
    output = dict(accel={}, imu={}, estimator={}, selector={})
    for instance in range(3):
        d=log.get_dataset('sensor_accel',instance).data; m=strict_window(d,start,end,12000)
        if np.any(np.diff(d['timestamp_sample'][m].astype(np.int64))<=0): raise ValueError('Accel sample clock')
        values=np.column_stack([d[k][m] for k in ('x','y','z')])
        if not np.all(np.isfinite(values)): raise ValueError('Nonfinite acceleration')
        clip=np.column_stack([d[f'clip_counter[{a}]'][m] for a in range(3)])
        if np.any(clip!=clip[0]): raise ValueError('Acceleration clipping')
        output['accel'][str(instance)]=dict(samples=int(m.sum()),peak_abs=np.max(np.abs(values),axis=0).tolist())
        output['imu'][str(instance)]=check_imu(log.get_dataset('vehicle_imu',instance).data,start,end)
    for instance in range(6):
        d=log.get_dataset('estimator_status',instance).data; m=strict_window(d,start,end,40000)
        if np.any(d['filter_fault_flags'][m]): raise ValueError('Estimator fault')
        output['estimator'][str(instance)]=dict(samples=int(m.sum()),faults=0)
    d=log.get_dataset('estimator_selector_status').data; m=strict_window(d,start,end,2000000)
    if np.any(d['primary_instance'][m]!=d['primary_instance'][m][0]): raise ValueError('Estimator switched')
    output['selector']=dict(samples=int(m.sum()),primary=int(d['primary_instance'][m][0]))
    return output


def complete_tail(log,start,end):
    pending=[]
    for name,count in TOPICS.items():
        for i in range(count):
            d=log.get_dataset(name,i).data
            if name == 'vehicle_imu':
                if bounds(d,start,end,pending=True) is None: pending.append(f'{name}:{i}')
            else:
                t=d['timestamp'].astype(np.int64)
                if not len(t) or np.any(t<=0) or np.any(np.diff(t)<=0) or t[0]>start:
                    raise ValueError('Invalid pre-existing health timeline')
                if t[-1]<end: pending.append(f'{name}:{i}')
    return pending


def collect(reader,ground_state,start,end,*,now=time.monotonic,sleep=time.sleep):
    deadline=now()+15.; snapshots=[]
    while now()<deadline:
        state=ground_state()
        if state.get('arming_state')!=1 or not state.get('landed') or state.get('failsafe'):
            raise ValueError('No longer safely disarmed during log tail')
        log=reader(); pending=complete_tail(log,start,end)
        snapshots.append(dict(pending=pending))
        if not pending:
            return dict(landing_start_us=int(start),landed_disarmed_us=int(end),snapshots=snapshots,health=check_health(log,start,end))
        sleep(.2)
    raise TimeoutError('Post-disarm health boundary not collected in15s')
