#!/usr/bin/env python3
"""Read-only ULog tail replay, not a replacement flight or historical acceptance.

The alternative end event exists only in memory. It exercises the actual new
wait helper and the complete analyzer on a log-derived hypothetical listener
schedule. Original events/results/manifests are never rewritten.
"""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

import numpy as np
from pyulog import ULog

import analyze as a
import heading_check as h
import replay_event_fix as history
import run
import runner_contract as rc
from prepare import sha256

HERE = Path(__file__).resolve().parent


def held_snapshot(ulog, publication_us):
    """Latest actually logged publications <= a position publication, no truth."""
    mapping = dict(position='vehicle_local_position', status='vehicle_status',
                   land='vehicle_land_detected', attitude='vehicle_attitude',
                   takeoff='takeoff_status')
    state = dict(phase='landing', diagnostics={})
    for key, name in mapping.items():
        data = h.topic(ulog, name)
        index = int(np.searchsorted(data['timestamp'], publication_us, side='right')) - 1
        if index < 0:
            raise ValueError('Missing causal tail topic: ' + name)
        state[key] = {field: values[index].item() for field, values in data.items()}
    state['attitude']['q'] = [state['attitude']['q[%d]' % index] for index in range(4)]
    return state


class VirtualClock:
    def __init__(self):
        self.seconds = 0.

    def monotonic(self):
        return self.seconds

    def sleep(self, seconds):
        self.seconds += seconds


def tail_replay():
    attempt = history.BATCHES[-1] / 'runs/O002'
    result = json.loads((attempt / 'result.json').read_text())
    job = json.loads((attempt / 'job.json').read_text())
    origin = json.loads((attempt / 'origin.json').read_text())
    native = max(result['logs'], key=lambda row: row['bytes'])
    assert sha256(native['archive']) == native['sha256']
    ulog = ULog(native['archive'])
    original_events = copy.deepcopy(result['events'])
    old_final = next(event for event in original_events if event['name'] == 'landed_disarmed')
    observed = [json.loads(line) for line in (attempt / 'samples.jsonl').read_text().splitlines()]
    original_last = next(state for state in reversed(observed) if state['phase'] == 'landing')
    assert original_last['position']['timestamp'] == old_final['timestamp_us']
    assert original_last['land']['timestamp'] == old_final['land_timestamp_us']
    assert original_last['status']['timestamp'] == old_final['status_timestamp_us']
    assert not rc.landing_confirmation_ready(original_last)
    old_job = dict(job, heading_reset_policy=h.POLICY, event_semantics_policy=h.REPUBLICATION_EVENTS)
    args = (native['archive'], original_events, origin, old_job, attempt / 'ros/sent.jsonl')
    old = history.capture(lambda: a.audit_native_log(*args))
    assert old == dict(passed=False, error="ValueError('Stale final state receipts')")

    # The real wait loop sleeps 100 ms. Model zero CLI latency here; do not claim
    # this predicts future process timing. Each selected value is real ULog data.
    clock = VirtualClock()
    used, recorded = [], []
    position_times = h.topic(ulog, 'vehicle_local_position')['timestamp']

    def sample(phase):
        assert phase == 'landing'
        if not used:
            state = copy.deepcopy(original_last)
        else:
            wanted = old_final['timestamp_us'] + round(clock.seconds * 1e6)
            index = int(np.searchsorted(position_times, wanted))
            if index >= len(position_times):
                raise ValueError('Existing ULog tail exhausted; not a fresh observation')
            state = held_snapshot(ulog, int(position_times[index]))
            for name in rc.diagnostic_expectations(job):
                data = h.topic(ulog, name)
                row = int(np.searchsorted(data['timestamp'], state['position']['timestamp'], side='right')) - 1
                assert row >= 0
                state['diagnostics'][name] = {key: values[row].item() for key, values in data.items()}
        rc.check_active_state(state, job, phase, origin)
        used.append(copy.deepcopy(state))
        return state

    def record(name, state):
        recorded.append(dict(name=name, timestamp_us=int(state['position']['timestamp']),
                             status_timestamp_us=int(state['status']['timestamp']),
                             land_timestamp_us=int(state['land']['timestamp']),
                             generation=old_final['generation']))

    with patch.object(run.time, 'monotonic', clock.monotonic), patch.object(run.time, 'sleep', clock.sleep):
        final = run.wait_for_landing_confirmation(sample, record)
    assert len(recorded) == 1 and len(used) == 2
    alternative = recorded[0]
    assert alternative['timestamp_us'] > old_final['timestamp_us']
    assert rc.landing_confirmation_ready(final)
    assert all(state['status']['arming_state'] == 1 and state['land']['landed'] == 1 for state in used)
    alternative_events = [alternative if event['name'] == 'landed_disarmed' else copy.deepcopy(event)
                          for event in original_events]
    probe_args = (native['archive'], alternative_events, origin, old_job, attempt / 'ros/sent.jsonl')
    metrics = a.audit_native_log(*probe_args)
    replay_metrics = a.audit_native_log(*probe_args)
    assert metrics == replay_metrics and metrics['accepted'] is True

    # Negative probes must still fail even with correct versioned event semantics.
    negatives = []
    for label, mutate in (
            ('original_stale_receipt', lambda event: event.update(land_timestamp_us=old_final['land_timestamp_us'])),
            ('stale_status', lambda event: event.update(status_timestamp_us=alternative['timestamp_us'] - 500001)),
            ('too_far_future_land', lambda event: event.update(land_timestamp_us=alternative['timestamp_us'] + 500001))):
        bad_events = copy.deepcopy(alternative_events)
        mutate(next(event for event in bad_events if event['name'] == 'landed_disarmed'))
        outcome = history.capture(lambda: a.audit_native_log(native['archive'], bad_events, origin, old_job,
                                                              attempt / 'ros/sent.jsonl'))
        assert outcome == dict(passed=False, error="ValueError('Stale final state receipts')")
        negatives.append(dict(case=label, **outcome))
    assert result['events'] == original_events
    assert json.loads((attempt / 'result.json').read_text()) == result
    assert result['success'] is False
    return dict(diagnostic_only=True, actual_new_flights=0, flight_accepted=False,
                historical_acceptance_changed=False, source_ulog_sha256=native['sha256'],
                original_result_sha256=sha256(attempt / 'result.json'),
                original_analysis_still_rejects=old, original_final_event=old_final,
                hypothetical_listener='100 ms polling; zero CLI latency; causal native topics; offline only',
                simulated_final_event=alternative, simulated_polls=len(used),
                simulated_additional_native_time_us=alternative['timestamp_us'] - old_final['timestamp_us'],
                status_age_us=alternative['timestamp_us'] - alternative['status_timestamp_us'],
                land_age_us=alternative['timestamp_us'] - alternative['land_timestamp_us'],
                unchanged_max_gap_us=a.MAX_GAP_US, full_diagnostic_chain_passed=True,
                deterministic_analysis_replay=True, phase_metrics=metrics['phase_metrics'],
                heading_evidence=metrics['heading_evidence'], send_evidence=metrics['send_evidence'],
                trajectory_evidence=metrics['trajectory_evidence'], negative_probes=negatives,
                future_live_listener_timing_not_validated=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--tests', action='store_true', help='Also run the three offline unit suites, no ROS/SITL')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or any(output.is_relative_to(batch) for batch in history.BATCHES):
        raise ValueError('Require a new output outside historical batches')
    commands = []
    if args.tests:
        for label, folder, pattern in (
                ('offboard', HERE, 'test_*.py'),
                ('upstream_tools', HERE.parent / 'tools', 'test_*.py'),
                ('legacy_heading', HERE.parents[1] / 'sta-velocity-control/scripts', 'test_v04_heading_policy.py')):
            argv = [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(folder), '-p', pattern, '-v']
            log = output.parent / (output.stem + '_' + label + '.log')
            start = time.monotonic()
            with log.open('x') as stream:
                cp = subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT, timeout=600)
            commands.append(dict(argv=argv, exit_code=cp.returncode, log=str(log), log_sha256=sha256(log),
                                 seconds=time.monotonic() - start))
            print(label, 'exit', cp.returncode, flush=True)
            if cp.returncode:
                raise RuntimeError('Offline test failed; preserved ' + str(log))
    historical = history.replay()
    tail = tail_replay()
    # Check all prior evidence again AFTER the alternative-tail probe as well.
    assert all(sha256(path) == digest for path, digest in historical['protected_sha256'].items())
    report = dict(status='offline_landing_capture_fix_passed_not_flight_qualified', new_flights=0,
                  new_manifest_created=False, history=historical, tail_probe=tail, test_commands=commands,
                  source_sha256={str(path): sha256(path) for path in sorted(HERE.glob('*.py'))})
    with output.open('x') as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(status=report['status'], historical_logs=historical['ulog_count'],
                         tail_probe=tail['full_diagnostic_chain_passed'], new_flights=0), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
