"""Replay new causal entry gate without changing any historical flight verdict."""
import argparse
import json
from pathlib import Path
import numpy as np
from pyulog import ULog
from audit_v04_diagnostic11 import audit, sha
from v04_entry14 import entry_ready
from analyze_v00 import previous_indices


def main():
    p = argparse.ArgumentParser(); p.add_argument('batch', type=Path); p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(); out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    results = []
    for run in sorted(args.batch.glob('run[0-9][0-9]')):
        r = json.loads((run / 'result.json').read_text()); events = {x['name']:x['timestamp_us'] for x in r['events']}
        original = json.loads((run / 'v04_protocol13_metrics.json').read_text())
        item = dict(run=run.name, original_accepted=original['accepted'], original_error=original.get('error'),
                    results_are_diagnostic_only=True, landing=audit(run))
        entry = max(r['logs'], key=lambda x:x['bytes']); assert sha(entry['archive']) == entry['sha256']
        u = ULog(entry['archive'], message_name_filter_list=['vehicle_local_position', 'trajectory_setpoint',
            'vehicle_status', 'vehicle_land_detected', 'sta_velocity_ctrl_status'])
        ref = json.loads((run / 'height_reference.json').read_text()); ref['yaw'] = json.loads((run / 'task_yaw.json').read_text())['yaw']
        end = events['hover_start']; item['recorded_entry'] = entry_ready(u, ref, end)
        candidates = json.loads((run / 'entry_candidates.json').read_text())
        first_good = next(x for x in candidates if x['valid'])
        item['first_cli_valid'] = dict(position_time=first_good['position']['timestamp'],
            target_time=first_good['target']['timestamp'], future_target_us=first_good['target']['timestamp']-first_good['position']['timestamp'])
        pos = u.get_dataset('vehicle_local_position').data; trajectory = u.get_dataset('trajectory_setpoint').data
        ix = np.flatnonzero((pos['timestamp'] >= end - 3e6) & (pos['timestamp'] <= end))
        j, _ = previous_indices(trajectory['timestamp'], pos['timestamp'][ix], 40000)
        delta = np.abs(trajectory['z'][j] - ref['target_z']); bad = delta > .05
        item['z_entry'] = dict(maximum_error=float(delta.max()), rejected_samples=int(bad.sum()),
            first_bad_time=int(pos['timestamp'][ix][bad][0]) if np.any(bad) else None,
            last_bad_time=int(pos['timestamp'][ix][bad][-1]) if np.any(bad) else None)
        item['earliest_later_ready_diagnostic'] = None
        for candidate in pos['timestamp'][(pos['timestamp'] >= end) & (pos['timestamp'] <= end+1e6)]:
            value = entry_ready(u, ref, int(candidate))
            if value['ready']:
                item['earliest_later_ready_diagnostic'] = value; break
        # A later counterfactual start never retroactively accepts this flight.
        assert json.loads((run / 'v04_protocol13_metrics.json').read_text())['accepted'] == item['original_accepted']
        assert sha(entry['archive']) == entry['sha256']
        results.append(item)
    (out / 'replay.json').write_text(json.dumps(results, indent=2, allow_nan=False) + '\n')
    (out / 'artifacts.sha256').write_text(f"{sha(out/'replay.json')}  {out/'replay.json'}\n")
    print(json.dumps([{k:v for k,v in r.items() if k != 'landing'} for r in results], indent=2))


if __name__ == '__main__': main()
