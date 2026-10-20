"""Read-only full-rate gyro evidence; never changes timestamps or grants flight acceptance.

Reuse the frozen IMU 12 ms dual-clock/boundary policy for the newly observed
gyro topics. This is a log-coverage criterion, not a new sensor/control limit.
No sorting, deduplication, interpolation, or reconstructed missing samples.
"""
import importlib.util
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
V08 = HERE.parents[1] / 'v08/protocol02'
for path in (V08,HERE.parents[1]/'v06/soft_landing'):
    if str(path) not in sys.path:
        sys.path.append(str(path))
_spec = importlib.util.spec_from_file_location('_upstream08_imu_clock', V08/'imu_health.py')
_health = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_health)


def gyro_evidence(data, start, end):
    """Complete boundary publication groups, including the sealing successor."""
    mask = _health.bounds(data, start, end)
    pub, sample = _health.clock(data)
    for key in ('device_id', 'samples', 'error_count'):
        v = np.asarray(data[key])[mask]
        if v.dtype.kind not in 'ui' or not len(v):
            raise ValueError('Invalid gyro integer field '+key)
        if key in ('device_id', 'samples') and np.any(v == 0):
            raise ValueError('Missing gyro device/sample count')
        if key in ('device_id', 'error_count') and np.any(v != v[0]):
            raise ValueError('Gyro device/error count changed')
    values = np.column_stack([data[key][mask] for key in ('x', 'y', 'z')])
    if not np.all(np.isfinite(values)):
        raise ValueError('Nonfinite gyro values')
    dt = np.diff(sample[mask])
    return dict(rows=int(mask.sum()), device_id=int(data['device_id'][mask][0]),
        publication_ties=int(np.count_nonzero(np.diff(pub[mask]) == 0)),
        max_publication_gap_us=int(np.diff(pub[mask]).max()),
        max_sample_gap_us=int(dt.max()), max_age_us=int((pub[mask]-sample[mask]).max()),
        median_sample_interval_us=float(np.median(dt)),
        observed_median_rate_hz=float(1e6/np.median(dt)),
        boundary_groups_complete=True, error_count=int(data['error_count'][mask][0]),
        sample_counts=np.unique(data['samples'][mask]).astype(int).tolist(),
        coverage='bounded recorded evidence, not lossless callback-consumption proof')


def trace_summary(data, start, end):
    """Describe upstream ages without turning an observed problem into a pass."""
    pub, sample = _health.clock(data)
    m = (pub >= start) & (pub <= end)
    if np.count_nonzero(m) < 2:
        raise ValueError('Missing upstream trace window')
    age = pub[m]-sample[m]
    return dict(rows=int(m.sum()), max_age_us=int(age.max()),
        max_publication_gap_us=int(np.diff(pub[m]).max()),
        max_sample_gap_us=int(np.diff(sample[m]).max()),
        publication_ties=int(np.count_nonzero(np.diff(pub[m]) == 0)),
        age_over_existing_12ms=int(np.count_nonzero(age > _health.GAP_US)))


def inspect_log(log, start, end):
    """Require the additional gyro coverage; report the unchanged downstream chain."""
    if log.dropouts or getattr(log, 'file_corruption', False):
        raise ValueError('Timing evidence ULog dropout/corruption')
    if log.initial_parameters.get('SDLOG_PROFILE') != 3089:
        raise ValueError('Full-rate gyro log profile not actually applied')
    output = dict(gyro={}, imu={}, estimator={}, accepted_for_R03=0,
        diagnostic_only=True, logger_added_mask=2048, logging_profile=3089)
    for instance in range(3):
        output['gyro'][str(instance)] = gyro_evidence(
            log.get_dataset('sensor_gyro', instance).data, start, end)
        output['imu'][str(instance)] = trace_summary(
            log.get_dataset('vehicle_imu', instance).data, start, end)
    for instance in range(6):
        output['estimator'][str(instance)] = trace_summary(
            log.get_dataset('estimator_status', instance).data, start, end)
    output['upstream_age_event_observed'] = any(
        row['age_over_existing_12ms'] for rows in (output['imu'], output['estimator']) for row in rows.values())
    output['limitations'] = [
        'Additional logging changes host I/O load; not a sensor-frequency change.',
        'No event in two diagnostic flights does not prove the original fault eliminated.',
        'Publication clocks do not measure host CPU residence or callback ordering.',
        'One paired IMU seed, not two statistically independent replicates.']
    return output
