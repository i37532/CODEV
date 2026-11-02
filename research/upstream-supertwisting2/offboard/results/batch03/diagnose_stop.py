#!/usr/bin/env python3
"""Read-only B03 evidence; no acceptance override, flight or array mutation."""
import json
import hashlib
from pathlib import Path
import subprocess
import sys

import numpy as np
from pyulog import ULog

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import analyze
import heading_check as heading
from prepare import sha256
from runner_contract import check_order

ROOT = Path('/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-ROS-OFFBOARD-20261102-B03')
ORIGINAL = Path('/home/yr/Desktop/Codev-SuperTwisting2-original')


def diagnose():
    manifest_path = ROOT/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    attempt = ROOT/'runs/O002'
    result_path = attempt/'result.json'
    result = json.loads(result_path.read_text())
    job = json.loads((attempt/'job.json').read_text())
    origin = json.loads((attempt/'origin.json').read_text())
    native = max(result['logs'], key=lambda row: row['bytes'])
    source = ORIGINAL/'src/modules/ekf2/EKF2.cpp'
    protected = [manifest_path, result_path, Path(native['archive']), source,
                 HERE/'heading_check.py', HERE/'analyze.py', HERE/'run.py']
    before = {str(path): sha256(path) for path in protected}
    assert before[native['archive']] == native['sha256']
    for path in (HERE/'heading_check.py', HERE/'analyze.py', HERE/'run.py'):
        assert before[str(path)] == manifest['assets'][str(path)]
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ORIGINAL,text=True).strip() == heading.STA2_HEAD
    original_source = subprocess.check_output(['git','show',heading.STA2_HEAD+':src/modules/ekf2/EKF2.cpp'],cwd=ORIGINAL)
    assert hashlib.sha256(original_source).hexdigest() == before[str(source)]
    assert result['success'] is False and result['task_completed'] is True
    assert result['parameter_restore_exact'] is True and result['remaining_simulators'] == []
    try:
        analyze.audit_native_log(native['archive'], result['events'], origin, job, attempt/'ros/sent.jsonl')
    except ValueError as exc:
        error = repr(exc)
    else:
        raise AssertionError('Frozen full audit must still reject this flight')
    assert error == result['analysis_error'] == "ValueError('Heading evidence: unexpected reset_vel_to_gps')"

    log = ULog(native['archive'])
    for item in log.data_list:
        for data in item.data.values():
            data.flags.writeable = False
    windows, special = analyze.phase_windows(result['events'], job['task'])
    start = next(w['start'] for w in windows if w['phase'] == 'climb')
    end = special['landed_disarmed']
    selector = heading.topic(log, 'estimator_selector_status')
    si = heading.interval(selector, start, end, 1200000)
    primary = int(heading.constant(selector, 'primary_instance', si))
    heading.constant(selector, 'instance_changed_count', si)
    ev = heading.topic(log, 'estimator_event_flags', primary)
    times = ev['timestamp'].astype(np.int64)
    before_start = np.flatnonzero(times < start)
    assert len(before_start)
    predecessor = int(before_start[-1])
    new = np.flatnonzero((times > start) & (times <= end))
    assert len(new)
    counter = ev['information_event_changes']
    all_same_generation = np.r_[predecessor, new]
    assert np.all(counter[all_same_generation] == counter[predecessor])
    last_event = np.flatnonzero(np.diff(counter.astype(np.int64))) + 1
    assert len(last_event) and times[last_event[-1]] < start
    last_event = int(last_event[-1])
    for field in ev:
        if field != 'timestamp':
            assert np.all(ev[field][last_event:] == ev[field][last_event])
    assert ev['reset_vel_to_gps'][last_event] == 1
    assert np.all(ev['reset_vel_to_gps'][new] == 1)
    assert np.all(np.diff(times[last_event:]) == 1000000)
    assert int(ev['timestamp_sample'][last_event]) < start
    p = heading.topic(log, 'vehicle_local_position')
    pi = heading.interval(p, start, end, 500000)
    counters = {}
    for field in heading.PV_COUNTERS:
        value = int(heading.constant(p, field, pi))
        counters[field] = dict(value=value, changed=False, boundary_rows_included=True)
    assert not log.dropouts and not log.file_corruption
    text = source.read_text()
    assert '_filter_information_event_changes++;' in text
    assert '// continue publishing periodically' in text
    assert '_estimator_event_flags_pub.get().timestamp = _replay_mode ? timestamp : hrt_absolute_time();' in text
    assert '_estimator_event_flags_pub.update();' in text
    try:
        check_order(manifest, 'O003')
    except ValueError as exc:
        assert 'Previous attempt failed' in str(exc)
        blocked = repr(exc)
    else:
        raise AssertionError('No continuation after failure')
    after = {str(path): sha256(path) for path in protected}
    assert before == after
    return dict(scope='Read-only failure diagnosis, not acceptance or a revised validator',
        original_outcome_unchanged=True, frozen_rejection_reproduced=error,
        source_sha256=sha256(__file__), protected_sha256=before,
        flight_window_us=[start,end], selected_estimator=primary,
        last_new_information_event=dict(timestamp_us=int(times[last_event]),
            timestamp_sample_us=int(ev['timestamp_sample'][last_event]),
            counter=int(counter[last_event]),
            true_flags=[key for key in ev if key not in ('timestamp','timestamp_sample','information_event_changes')
                        and ev[key][last_event] == 1]),
        periodic_republication=dict(rows_during_flight=len(new),counter_changes_during_flight=0,
            first_after_start_us=int(times[new[0]]),last_before_end_us=int(times[new[-1]]),
            all_payload_fields_identical=True,period_us=1000000),
        position_velocity_reset_counters=counters,
        ulog=dict(samples_event_flags=len(times),dropout_count=0,file_corruption=False),
        source_contract=dict(path=str(source),function='EKF2::PublishEventFlags',
            verified_against_git_commit=heading.STA2_HEAD,
            line_start=1119,new_event_counter_line=1127,periodic_republication_line=1160,
            meaning='New events increment counter; otherwise the cached payload is republished every second with only publication timestamp refreshed.'),
        checker_contract=dict(path=str(HERE/'heading_check.py'),lines=[187,193],
            meaning='Every publication after start is checked as a new event, despite unchanged information-event counter/sample.'),
        next_job_blocked=blocked,
        interpretation='This rejection is caused by treating repeated preflight event payload as a new in-flight GPS reset. '
                       'No in-flight position/velocity reset is observed in the full boundary counters. '
                       'Other full-log checks after the rejection were NOT certified; acceptance remains false.')


if __name__ == '__main__':
    print(json.dumps(diagnose(), ensure_ascii=False, indent=2, allow_nan=False))
