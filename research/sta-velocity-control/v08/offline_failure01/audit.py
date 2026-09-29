"""Read-only V08 CLI/ULog failure audit, NOT an acceptance override or runner."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import numpy as np
from pyulog import ULog

PROTOCOL = Path(__file__).resolve().parents[1] / 'protocol01'
sys.path.insert(0, str(PROTOCOL))
from position_log import checked


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def listener_clock(command, topic):
    """PX4 generated printer's own time; do not substitute a second topic clock.

    This describes publication age at printing, NOT host delivery latency.
    The generated uint64 `now - timestamp` wraps for future timestamps;
    a huge age therefore remains a rejection, never a negative-age repair.
    """
    argv = command['cmd']
    if (command['returncode'] != 0 or len(argv) != 4
            or Path(argv[0]).name != 'px4-listener' or argv[1:] != [topic, '-n', '1']):
        raise ValueError('Wrong/failed listener invocation')
    text = command['stdout']
    if text.count('TOPIC: ') != 1 or 'TOPIC: ' + topic + '\n' not in text:
        raise ValueError('Missing/ambiguous topic')
    matches = re.findall(r'^\s*timestamp: ([0-9]+)\s+\(([0-9]+)\.([0-9]{6}) seconds ago\)\s*$', text, re.M)
    if len(matches) != 1 or len(re.findall(r'^\s*timestamp:', text, re.M)) != 1:
        raise ValueError('Missing/ambiguous publication age')
    timestamp, seconds, fractional = map(int, matches[0])
    age = seconds * 1000000 + fractional
    if timestamp <= 0 or not 0 <= age <= 1000000:
        raise ValueError('Stale/future/invalid printed timestamp')
    return dict(timestamp_us=timestamp, printed_age_us=age,
                printer_now_us=timestamp + age, host_delivery_latency_known=False)


def sequence(data, key):
    t = np.asarray(data['timestamp'], dtype=np.int64)
    seq = np.asarray(data[key], dtype=np.int64)
    if len(t) < 2 or np.any(np.diff(t) <= 0):
        raise ValueError('Invalid publication sequence')
    delta = np.diff(seq) % (2**32)
    if np.any(delta != 1):
        raise ValueError('Missing/repeated sequence')
    sample = np.asarray(data['timestamp_sample'], dtype=np.int64)
    if np.any(np.diff(sample) <= 0) or np.any(sample > t):
        raise ValueError('Invalid sample clock')
    return dict(records=len(t), start_us=int(t[0]), end_us=int(t[-1]),
                max_publication_gap_us=int(np.diff(t).max()), sequence_gaps=0)


def audit(run):
    result = json.loads((run / 'result.json').read_text())
    if result.get('success') or result.get('error') != "RuntimeError('Stale diagnostic')":
        raise ValueError('Not the frozen failed flight')
    for item in result['logs']:
        if digest(item['archive']) != item['sha256']:
            raise ValueError('Changed ULog archive')
    commands = [json.loads(s) for s in (run / 'commands.jsonl').read_text().splitlines()]
    indices = [i for i, c in enumerate(commands)
               if c['cmd'][1:] == ['sta_velocity_ctrl_status', '-n', '1']]
    vi = indices[-1]
    pi = max(i for i in range(vi) if commands[i]['cmd'][1:] == ['vehicle_local_position', '-n', '1'])
    ai = next(i for i in range(vi + 1, len(commands))
              if commands[i]['cmd'][1:] == ['vehicle_local_position', '-n', '1'])
    p = listener_clock(commands[pi], 'vehicle_local_position')
    v = listener_clock(commands[vi], 'sta_velocity_ctrl_status')
    after = listener_clock(commands[ai], 'vehicle_local_position')
    old_reject = abs(p['timestamp_us'] - v['timestamp_us']) > 1000000
    if not old_reject:
        raise ValueError('Original guard failure not reproduced')
    samples = [json.loads(s) for s in (run / 'samples.jsonl').read_text().splitlines()]
    if samples[-1]['position']['timestamp'] != p['timestamp_us']:
        raise ValueError('Not the actual failing monitor snapshot')
    main = next(x for x in result['logs'] if Path(x['archive']).name == 'log001.ulg')
    u = ULog(main['archive'])
    if u.dropouts or u.file_corruption:
        raise ValueError('Raw log loss/corruption')
    _, position = checked(u)
    topics = {}
    for name, key in [('sta_velocity_ctrl_status', 'publish_seq'),
                      ('sta_rate_ctrl_status', 'publish_seq'),
                      ('velocity_ctrl_selection', 'publish_seq'),
                      ('vehicle_local_position_log', 'log_seq')]:
        topics[name] = sequence(u.get_dataset(name).data, key)
    d = u.get_dataset('sta_velocity_ctrl_status').data
    m = (d['timestamp'] >= p['timestamp_us']) & (d['timestamp'] <= after['timestamp_us'])
    if not np.any(m) or not np.any(d['timestamp'][m] == v['timestamp_us']):
        raise ValueError('Missing exact failed CLI publication in raw log')
    expected = dict(effective_mode=1, effective_axes=3, inner_mode=0, inner_axes=0,
                    inner_divisor=1, inner_valid=1, fault=0, first_fail=0,
                    retry_result=0, timing=0, sta_fault=0, failsafe=0,
                    armed=1, enabled=1, valid=1, pid_axes=4, committed_axes=3)
    for name, value in expected.items():
        if np.any(d[name][m] != value):
            raise ValueError('Unexpected diagnostic around failure: ' + name)
    events = [x['name'] for x in result['events']]
    missing = [x for x in ('hover_end', 'land_command', 'landed_disarmed') if x not in events]
    if not missing:
        raise ValueError('Audit must not imply complete flight')
    return dict(audit_completed=True, flight_accepted=False, historical_regrade=False,
                source_head=result['source_head'], error=result['error'],
                cli=dict(position_before=p, velocity=v, position_after=after,
                         cross_read_difference_us=v['timestamp_us'] - p['timestamp_us'],
                         old_guard_rejects=old_reject, numeric_age_limit_us=1000000,
                         command_indices=[pi, vi, ai]),
                raw_topics=topics, position_log=position, dropout_count=0,
                interval_us=[p['timestamp_us'], after['timestamp_us']],
                interval_samples=int(m.sum()), interval_required_state=expected,
                missing_required_events=missing,
                limitation='Print-time freshness does not prove timely host delivery or continuous online protection. '
                           'Commands lack monotonic start/end timing. No OS scheduling cause or whole-flight success inferred.',
                raw_logs=result['logs'],
                source_fingerprints={name: digest(run / name) for name in
                                     ('commands.jsonl', 'samples.jsonl', 'result.json', 'job.json')})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    evidence = audit(args.run)
    with args.output.open('x') as stream:
        json.dump(evidence, stream, indent=2)
        stream.write('\n')
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
