#!/usr/bin/env python3
"""Read-only protocol04 CLI/raw-reference audit; never reruns or reaccepts flight."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from pyulog import ULog
from analyze_v04_protocol04 import check_first_invocation
from v04_task04 import REFERENCE, check_reference, scalars
from v04_heading_stream import replay, row


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run, out = args.run.resolve(), args.output.resolve()
    if out == run or run in out.parents:
        raise ValueError('Use a separate new evidence directory')
    out.mkdir(parents=True, exist_ok=False)
    result = json.loads((run/'result.json').read_text())
    ref = json.loads((run/'height_reference.json').read_text())
    samples = [json.loads(s) for s in (run/'samples.jsonl').read_text().splitlines()]
    observed = samples[-1]
    start = next(e['timestamp_us'] for e in result['events'] if e['name'] == 'takeoff_command')
    evidence = dict(accepted=False, original_error=result['error'], source_head=result['source_head'],
                    planned=6, attempts=1, accepted_attempts=0, unexecuted=5, esta_attempts=0,
                    original_events=result['events'], failure_sample=observed, logs=[])
    decoded = []
    for item in result['logs']:
        path = Path(item['archive'])
        if sha(path) != item['sha256']:
            raise ValueError('Changed original ULog')
        u = ULog(str(path))
        decoded.append((item, u))
        evidence['logs'].append(dict(**item, dropouts=len(u.dropouts), corruption=u.file_corruption))
    item, u = max(decoded, key=lambda pair: pair[0]['bytes'])
    pos = u.get_dataset('vehicle_local_position').data
    ix = np.flatnonzero(pos['timestamp'] == observed['position']['timestamp'])
    if len(ix) != 1:
        raise ValueError('CLI sample not uniquely present in raw ULog')
    raw = row(pos, int(ix[0]))
    check_reference(raw, ref)
    try:
        check_reference(observed['position'], ref)
    except ValueError as exc:
        evidence['reproduced_exception'] = str(exc)
    else:
        raise AssertionError('Expected original failure was not reproduced')
    checks = [dict(name='raw_sample_reference_accepted', passed=True),
              dict(name='original_cli_reference_rejected', passed=evidence['reproduced_exception'] == 'Coordinate/reset changed: ref_lat')]
    evidence['coordinate_printing'] = {}
    for key in ('ref_lat', 'ref_lon'):
        formatted = float(format(raw[key], '.6f'))
        evidence['coordinate_printing'][key] = dict(raw=raw[key], cli=observed['position'][key],
            formatted_six_decimals=formatted, absolute_difference=abs(raw[key]-formatted), old_limit=1e-7)
        checks.append(dict(name=key+'_six_decimal_output_matches', passed=formatted == observed['position'][key]))
    commands = [json.loads(s) for s in (run/'commands.jsonl').read_text().splitlines()]
    matched = [c for c in commands if 'listener' in Path(c['cmd'][0]).name and 'vehicle_local_position' in c['cmd']
               and scalars(c['stdout']).get('timestamp') == observed['position']['timestamp']]
    checks.append(dict(name='archived_cli_stdout_matches', passed=bool(matched) and all(
        scalars(c['stdout'])['ref_lat'] == observed['position']['ref_lat'] for c in matched)))
    pm = pos['timestamp'] >= start
    evidence['raw_reference_unique'] = {k: np.unique(pos[k][pm]).tolist() for k in (*REFERENCE, 'heading_reset_counter')}
    checks.append(dict(name='raw_reference_all_samples_unchanged', passed=all(
        np.all(pos[k][pm] == ref['position'][k]) for k in (*REFERENCE, 'heading_reset_counter'))))
    evidence['raw_heading_replay'] = replay(u, ref, allow_pending=True)
    evidence['topics'] = {}
    for name in ('vehicle_status', 'vehicle_land_detected', 'sta_velocity_ctrl_status', 'sta_rate_ctrl_status'):
        d = u.get_dataset(name).data
        m = d['timestamp'] >= start
        ts = d['timestamp'][m].astype(np.int64)
        entry = dict(samples=int(m.sum()), max_gap_us=int(np.diff(ts).max()) if len(ts) > 1 else None)
        for key in ('arming_state', 'nav_state', 'takeoff_time', 'landed', 'ground_contact',
                    'requested_mode', 'requested_axes', 'effective_mode', 'effective_axes', 'div_eff',
                    'inner_mode', 'inner_axes', 'inner_divisor', 'inner_valid', 'armed', 'enabled',
                    'first_fail', 'retry_result', 'fault', 'sta_fault', 'timing', 'failsafe', 'valid', 'pid_calls',
                    'excitation_fault', 'excitation', 'excitation_time'):
            if key in d:
                entry[key] = np.unique(d[key][m]).tolist()
        for key in ('publish_seq', 'update_seq'):
            if key in d:
                entry[key+'_nonunit_deltas'] = int(np.count_nonzero(np.diff(d[key][m].astype(np.int64)) != 1))
        if name == 'sta_velocity_ctrl_status':
            entry['first_invocation'] = check_first_invocation(d, m)
        evidence['topics'][name] = entry
    evidence['raw_position'] = dict(samples=int(pm.sum()),
        first_timestamp=int(pos['timestamp'][pm][0]), last_timestamp=int(pos['timestamp'][pm][-1]),
        max_gap_us=int(np.diff(pos['timestamp'][pm].astype(np.int64)).max()),
        height_range_m=[float((ref['position']['z']-pos['z'][pm]).min()), float((ref['position']['z']-pos['z'][pm]).max())])
    checks.append(dict(name='no_flight_detected', passed=all(
        evidence['topics']['vehicle_land_detected'][k] == [1] for k in ('landed', 'ground_contact'))
        and evidence['topics']['vehicle_status']['takeoff_time'] == [0]))
    checks.append(dict(name='no_task_or_excitation', passed=not (run/'reposition_command.json').exists()
        and not (run/'task_yaw.json').exists() and evidence['topics']['sta_velocity_ctrl_status']['excitation'] == [0.0]))
    evidence['diagnostic_checks'] = checks
    evidence['diagnostic_passed'] = all(c['passed'] for c in checks)
    evidence['interpretation'] = ('CLI %.6f rounding is inconsistent with the 1e-7 CLI/raw comparison. '
        'No raw origin/reset change in the recorded interval; no detected liftoff or complete performance window. '
        'This audit does not fix the monitor or reclassify the failed attempt.')
    files = sorted(p for p in run.parent.rglob('*') if p.is_file() and not p.is_symlink())
    (out/'original_artifacts.sha256').write_text(''.join(f'{sha(p)}  {p}\n' for p in files))
    evidence['original_artifact_count'] = len(files)
    evidence['original_artifact_index_sha256'] = sha(out/'original_artifacts.sha256')
    (out/'diagnosis.json').write_text(json.dumps(evidence, indent=2)+'\n')
    print(json.dumps(evidence, indent=2))
    return 0 if evidence['diagnostic_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
