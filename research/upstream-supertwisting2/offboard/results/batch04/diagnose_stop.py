#!/usr/bin/env python3
"""Read-only B04 first-failure diagnosis; no edits, retries or acceptance override."""
import json
from pathlib import Path
import sys

import numpy as np
from pyulog import ULog

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import analyze
import plot_results
import runner_contract
from prepare import sha256
from run import parse_topic
from replay_event_fix import capture

ROOT = Path('/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-ROS-OFFBOARD-20261102-B04')


def main():
    directory = ROOT / 'runs/O002'
    result_path = directory / 'result.json'
    before = {str(p): sha256(p) for p in ROOT.rglob('*') if p.is_file()}
    result = json.loads(result_path.read_text())
    job = json.loads((directory / 'job.json').read_text())
    origin = json.loads((directory / 'origin.json').read_text())
    native = max(result['logs'], key=lambda row: row['bytes'])
    assert sha256(native['archive']) == native['sha256']
    commands = [json.loads(line) for line in (directory / 'commands.jsonl').read_text().splitlines()]
    latest = {}
    for command in commands:
        if command['argv'][0].endswith('px4-listener'):
            assert command['exit_code'] == 0
            latest[command['argv'][1]] = parse_topic(command['stdout'])
    state = dict(phase='landing', diagnostics={'attitude_sta_status': latest['attitude_sta_status']})
    for key, topic in (('position', 'vehicle_local_position'), ('status', 'vehicle_status'),
                       ('land', 'vehicle_land_detected'), ('attitude', 'vehicle_attitude'),
                       ('takeoff', 'takeoff_status')):
        state[key] = latest[topic]
    reproduced = capture(lambda: runner_contract.check_active_state(state, job, 'landing', origin))
    assert reproduced == dict(passed=False, error=result['error'])
    p = state['position']
    height = origin['z'] - p['z']
    assert height < -.5 and abs(p['vz']) < 3.5
    assert state['status']['nav_state'] == 18 and state['status']['arming_state'] == 2
    assert not state['land']['landed']
    log = ULog(native['archive'])
    def topic(name):
        found = [d.data for d in log.data_list if d.name == name and d.multi_id == 0]
        assert len(found) == 1
        return found[0]
    local = topic('vehicle_local_position')
    matched = np.flatnonzero(local['timestamp'] == p['timestamp'])
    assert len(matched) == 1
    i = int(matched[0])
    values = {key: local[key][i].item() for key in ('timestamp', 'timestamp_sample', 'x', 'y', 'z', 'vx', 'vy', 'vz')}
    assert all(abs(values[key] - p[key]) <= .0000051 for key in ('x', 'y', 'z', 'vx', 'vy', 'vz'))
    climb = next(e['timestamp_us'] for e in result['events'] if e['name'] == 'climb_start')
    flight = local['timestamp'] >= climb
    heights = origin['z'] - local['z'].astype(float)
    crossing = int(np.flatnonzero(flight & (heights < -.5))[0])
    first = dict(timestamp_us=int(local['timestamp'][crossing]), height_m=float(heights[crossing]),
                 z_m=float(local['z'][crossing]), vz_m_s=float(local['vz'][crossing]))
    resets = {key: np.unique(local[key][flight]).tolist() for key in
              ('xy_reset_counter', 'z_reset_counter', 'vxy_reset_counter', 'vz_reset_counter')}
    assert all(len(values) == 1 for values in resets.values())
    selector = topic('estimator_selector_status')
    selected = selector['primary_instance'][selector['timestamp'] >= climb]
    assert np.array_equal(np.unique(selected), [0])
    # Exploratory comparison only. Ground-truth values have their OWN zero;
    # subtract the prestream ground-truth reference, never estimator origin.
    truth = topic('vehicle_local_position_groundtruth')
    reference_us = result['events'][0]['timestamp_us']
    def held(data, stamp):
        index = int(np.searchsorted(data['timestamp'], stamp, side='right')) - 1
        assert index >= 0
        return {key: data[key][index].item() for key in ('timestamp', 'z', 'vz')}
    truth_reference = held(truth, reference_us)
    truth_tail = held(truth, int(p['timestamp']))
    comparison = dict(exploratory_only=True, truth_reference=truth_reference, truth_tail=truth_tail,
                      truth_relative_height_m=truth_reference['z'] - truth_tail['z'],
                      estimated_relative_height_m=height,
                      note='Native ground-truth receipt is earlier; source/impact dynamics not fully audited. Not an acceptance replacement or proof of physical penetration.')
    full_analysis = capture(lambda: analyze.audit_native_log(native['archive'], result['events'], origin,
                                                              job, directory / 'ros/sent.jsonl'))
    assert not full_analysis['passed'] and 'Missing final flight events' in full_analysis['error']
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    next_job = capture(lambda: runner_contract.check_order(manifest, 'O003'))
    assert not next_job['passed'] and 'Previous attempt failed' in next_job['error']
    plot = capture(lambda: plot_results.audit_inputs(ROOT / 'manifest.json'))
    assert not plot['passed'] and 'O002' in plot['error']
    assert all(sha256(path) == digest for path, digest in before.items())
    report = dict(status='read_only_reproduced_real_estimated_height_limit', new_flights=0,
                  unchanged_original_evidence=True, original_evidence_sha256=before,
                  error_reproduced=reproduced, first_native_height_violation=first,
                  triggering_listener=dict(timestamp_us=int(p['timestamp']), height_m=height,
                      lower_limit_m=-.5, excess_below_limit_m=-.5-height, vz_m_s=p['vz'], vz_limit_m_s=3.5),
                  native_match=values, listener_matches_raw_ulog_to_print_precision=True,
                  arming_state=state['status']['arming_state'], nav_state=state['status']['nav_state'],
                  landed=state['land']['landed'], ground_contact=state['land']['ground_contact'],
                  reset_counters=resets, primary_instance=np.unique(selected).tolist(),
                  corruption=log.file_corruption, dropout_count=len(log.dropouts),
                  truth_diagnostic=comparison, full_analysis=full_analysis,
                  next_job_stopped=next_job, comparison_plot_rejected=plot,
                  control_or_thresholds_changed=False, parameter_restore_exact=result['parameter_restore_exact'],
                  source_sha256={str(path): sha256(path) for path in
                                 (HERE / 'run.py', HERE / 'runner_contract.py', Path(__file__))})
    with Path(__file__).with_name('stop_diagnosis01.json').open('x') as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps({key: report[key] for key in ('status', 'triggering_listener', 'corruption', 'dropout_count', 'next_job_stopped')}))


if __name__ == '__main__': main()
