#!/usr/bin/env python3
"""Exercise the new whole-flight composition on unchanged OLD mode0/1 data.

No synthetic epsilon metadata is added to the ULog. It is explicitly absent;
new_metadata=False is legal only for modes0/1. Results never accept an R03 flight.
"""
import argparse
import json
from pathlib import Path
from config import digest, HERE
from legacy import initialize
from analyzer import whole_flight_components


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('run', type=Path); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(argv); source = a.run.resolve(); output = a.output.resolve()
    audit = json.loads((HERE.parents[1] / 'r00/evidence/baseline_audit02.json').read_text())
    allowed = {Path(e['archive']).parent.resolve() for e in audit['raw_log_samples']}
    if source not in allowed:
        raise ValueError('Only R00 already-inspected four logs; no unseen/holdout inputs')
    if output.exists() or source == output or source in output.parents:
        raise ValueError('Independent unused output file required')
    record = json.loads((source / 'result.json').read_text())
    events = {e['name']: e['timestamp_us'] for e in record['events']}
    job = json.loads((source / 'job.json').read_text())
    if job['mode'] not in (0, 1): raise ValueError('Archived composition permits only real old modes')
    # Unused offline defaults permit configuration validation; no data mutation.
    job['parameters'] = {**job['parameters'], **{f'MPC_VC_EPS_{axis}': value for axis, value in zip('XYZ', (.01, .01, .02))}}
    initial = json.loads((source / 'runtime_parameters_start.json').read_text())
    job['parameters'] = {**initial, **job['parameters']}
    baseline = json.loads((source / 'v00_metrics.json').read_text())
    archive = Path(baseline['ulog']['archive']); before = digest(archive)
    if before != baseline['ulog']['sha256']: raise ValueError('Raw ULog fingerprint mismatch')
    initialize()
    from pyulog import ULog
    result = dict(success=False, new_flights=0, flight_accepted=False, raw_ulog=str(archive), raw_sha256=before,
                  old_mode=job['mode'], old_axes=job['axes'], new_metadata_present=False,
                  source_inputs={str(p): digest(p) for p in sorted(HERE.glob('*.py'))})
    try:
        result['components'] = whole_flight_components(ULog(str(archive)), source, job, events, new_metadata=False)
        result['success'] = True
    except BaseException as exc:
        result['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        result['raw_unchanged'] = digest(archive) == before
        result['source_inputs_unchanged'] = all(digest(p) == value for p, value in result['source_inputs'].items())
        if not result['source_inputs_unchanged'] or not result['raw_unchanged']:
            result['success'] = False
        output.write_text(json.dumps(result, indent=2, default=lambda v: v.item()) + '\n')
    print(json.dumps(dict(success=True, new_flight_accepted=False, output=str(output))))


if __name__ == '__main__':
    main()
