#!/usr/bin/env python3
"""Post-run descriptive errata only. Does not alter frozen metrics or acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import re

import numpy as np
from pyulog import ULog


def saturation_summary(bits, feedback_valid):
    bits = np.asarray(bits, dtype=np.uint16)
    valid = np.asarray(feedback_valid, dtype=bool)
    if not len(bits) or bits.shape != valid.shape:
        raise ValueError('Empty/mismatched feedback')
    valid = valid & ((bits & 1) != 0)
    values, counts = np.unique(bits, return_counts=True)
    return dict(count=len(bits), bit_histogram={str(int(v)): int(n) for v, n in zip(values, counts)},
                feedback_valid_fraction=float(np.mean(valid)),
                raw_nonzero_fraction=float(np.mean(bits != 0)),
                saturation_fraction_among_valid=float(np.mean((bits[valid] & 0x7fe) != 0)) if valid.any() else None,
                rate_direction_saturation_fraction_among_valid=float(np.mean((bits[valid] & 0x1f8) != 0)) if valid.any() else None)


def perf_counts(console, duration):
    counts = [int(x) for x in re.findall(r'mc_pos_control: cycle time:\s*(\d+) events', console)]
    if len(counts) != 2 or counts[1] <= counts[0] or duration <= 0:
        raise ValueError('Missing/nonmonotonic position perf snapshots')
    return dict(counts=counts, approximate_hz=(counts[1]-counts[0])/duration,
                limitation='CLI snapshot boundaries approximate hover boundaries; simulated elapsed=0 is not zero CPU cost.')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('series', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    summary = dict(purpose='Descriptive errata; original frozen acceptance unchanged',
                   analyzer_sha256=sha(Path(__file__)), runs=[])
    ledger = json.loads((args.series/'ledger.json').read_text())
    for attempt in ledger['attempts']:
        run = Path(attempt['directory'])
        m = json.loads((run/'v00_metrics.json').read_text())
        result = json.loads((run/'result.json').read_text())
        events = {v['name']: v['timestamp_us'] for v in result['events']}
        archive = Path(m['ulog']['archive'])
        if sha(archive) != m['ulog']['sha256']:
            raise ValueError('ULog fingerprint mismatch')
        log = ULog(str(archive))
        d = log.get_dataset('sta_rate_ctrl_status').data
        hm = (d['timestamp'] >= events['hover_start']) & (d['timestamp'] < events['hover_end'])
        p = log.get_dataset('vehicle_local_position').data
        ph = (p['timestamp'] >= events['hover_start']) & (p['timestamp'] < events['hover_end'])
        ground = json.loads((run/'ground.json').read_text())
        height = ground[2] - p['z'][ph]
        summary['runs'].append(dict(attempt=attempt['attempt'], original_accepted=m['accepted'],
            original_metrics_sha256=sha(run/'v00_metrics.json'), ulog_sha256=sha(archive),
            saturation=saturation_summary(d['sat_bits'][hm], d['sat_valid'][hm]),
            position_module_perf=perf_counts((run/'console.log').read_text(), m['hover_seconds']),
            estimated_hover_height_m=dict(mean=float(np.mean(height)), min=float(np.min(height)), max=float(np.max(height))),
            evidence_note='Height relative to estimated preflight ground; not Gazebo true altitude.'))
    (out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
