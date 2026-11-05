#!/usr/bin/env python3
"""Read-only audit of archived logs; never overwrite flight acceptance results."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from pyulog import ULog


def coverage(status, actuator, start, end):
    t = status['timestamp_sample'].astype(np.int64)
    at = actuator['timestamp_sample'].astype(np.int64)
    eligible = (t >= start) & (t <= end) & status['output_valid'].astype(bool)
    updated = eligible & status['updated'].astype(bool)
    held = eligible & status['held'].astype(bool)
    common, si, ai = np.intersect1d(t, at, return_indices=True)
    use = eligible[si]
    si, ai = si[use], ai[use]
    expected = np.column_stack([status[f'c_applied[{i}]'] for i in range(3)] + [status['thrust']])
    actual = np.column_stack([actuator[f'control[{i}]'] for i in range(4)])
    matched = np.isin(t, common)
    gaps = np.diff(at[(at >= start) & (at <= end)])
    values, counts = np.unique(gaps, return_counts=True)
    return dict(callbacks=int(eligible.sum()), updates=int(updated.sum()), held=int(held.sum()),
                missing_callbacks=int((eligible & ~matched).sum()),
                missing_updates=int((updated & ~matched).sum()),
                missing_held=int((held & ~matched).sum()), matched_samples=len(si),
                matched_torque_thrust_bitwise_equal=bool(len(si) and np.array_equal(
                    expected[si].astype(np.float32).view(np.uint32),
                    actual[ai].astype(np.float32).view(np.uint32))),
                actuator_gap_us={str(int(v)):int(n) for v,n in zip(values,counts)},
                unique_status_timestamps=bool(len(np.unique(t)) == len(t)),
                unique_actuator_timestamps=bool(len(np.unique(at)) == len(at)))


def audit(run):
    result = json.loads((run/'result.json').read_text())
    candidates = []
    for item in result['logs']:
        path = Path(item['archive'])
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('ULog fingerprint mismatch: '+str(path))
        log = ULog(str(path))
        try:
            d = log.get_dataset('sta_rate_ctrl_status').data
            a = log.get_dataset('actuator_controls_0').data
        except KeyError:
            continue
        events = {e['name']: e['timestamp_us'] for e in result['events']}
        if len(d['timestamp_sample']) and d['timestamp_sample'][-1] >= events['hover_end']:
            row = coverage(d,a,events['hover_start'],events['hover_end'])
            row.update(run=str(run), ulog=str(path), sha256=item['sha256'],
                       source_head=result['source_head'], ulog_dropouts=len(log.dropouts),
                       divisor=int(json.loads((run/'m04_config.json').read_text())['MC_RTC_DIV']))
            logger = [x for x in log.data_list if x.name == 'logger_status']
            row['logger_message_gaps_max'] = max((int(np.max(x.data['message_gaps'])) for x in logger), default=None)
            candidates.append(row)
    if len(candidates) != 1:
        raise ValueError('Expected one complete research log: '+str(run))
    return candidates[0]


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('runs',type=Path,nargs='+')
    p.add_argument('--output',type=Path,required=True)
    args = p.parse_args()
    rows = [audit(run.resolve()) for run in args.runs]
    with args.output.open('x') as stream:
        json.dump(dict(scope='Exploratory offline audit; not flight admission',rows=rows),stream,indent=2)
        stream.write('\n')
    for r in rows:
        print(Path(r['run']).name, 'DIV',r['divisor'], 'missing',r['missing_callbacks'], '/',r['callbacks'],
              'matched_equal',r['matched_torque_thrust_bitwise_equal'],'dropouts',r['ulog_dropouts'])
