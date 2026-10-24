#!/usr/bin/env python3
"""Independent trace/metric replay and compact research results, no flight API."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import re


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def aggregate(points):
    if not points:
        return None
    duration = math.fsum(p['h'] for p in points)
    true = [p['v']-p['v_sp'] for p in points]
    measured = [p['measurement']-p['v_sp'] for p in points]
    return dict(seconds=duration, samples=len(points),
                rmse=math.sqrt(math.fsum(p['h']*e*e for p, e in zip(points, true))/duration),
                measured_rmse=math.sqrt(math.fsum(p['h']*e*e for p, e in zip(points, measured))/duration),
                mean=math.fsum(p['h']*e for p, e in zip(points, true))/duration,
                measured_mean=math.fsum(p['h']*e for p, e in zip(points, measured))/duration,
                peak_error=max(map(abs, true)), measured_peak_error=max(map(abs, measured)),
                correction_tv_per_s=math.fsum(abs(b['a_applied']-a['a_applied']) for a, b in zip(points, points[1:]))/duration,
                peak_correction=max(abs(p['a_applied']) for p in points),
                peak_nu=max(abs(p['nu_applied']) for p in points),
                constrained_fraction=math.fsum(p['h'] for p in points if p['constrained'])/duration)


def verify(expected, actual):
    if expected is None or actual is None:
        if expected != actual:
            raise AssertionError('empty window mismatch')
        return
    if expected.keys() != actual.keys():
        raise AssertionError('metric keys mismatch')
    for key, value in expected.items():
        # nu_applied is the float committed value; in these runs every
        # unmodified/capped candidate is exactly representable as float.
        if not math.isclose(value, actual[key], rel_tol=1e-11, abs_tol=1e-13):
            raise AssertionError(f'{key} mismatch: {value} / {actual[key]}')


def replay(summary_path):
    summary = json.loads(summary_path.read_text())
    if not summary['success'] or len(summary['rows']) != 144:
        raise ValueError('incomplete diagnostic matrix')
    rows = []
    for row in summary['rows']:
        path = Path(row['trace'])
        if digest(path) != row['trace_sha256']:
            raise AssertionError('trace fingerprint mismatch')
        with gzip.open(path, 'rt') as stream:
            points = [json.loads(line) for line in stream]
        if len(points) != row['updates']:
            raise AssertionError('trace update count mismatch')
        previous_end = 0.
        for p in points:
            if not math.isclose(p['t'], previous_end, abs_tol=1e-12, rel_tol=0):
                raise AssertionError('time discontinuity')
            previous_end = p['t'] + p['h']
        if not math.isclose(previous_end, row['seconds'], abs_tol=1e-12, rel_tol=0):
            raise AssertionError('trace duration mismatch')
        full = aggregate(points)
        tail = aggregate([p for p in points if p['t'] >= 12.])
        verify(row['full'], full)
        verify(row['tail_12_36'], tail)
        if digest(path) != row['trace_sha256']:
            raise AssertionError('trace changed during replay')
        rows.append({**row, 'independent_metric_replay': True})
    result = {key: summary[key] for key in (
        'entry_head', 'branch', 'input_sha256', 'submodules', 'success', 'new_flights',
        'complete_trajectories', 'rejected_trajectories', 'total_updates', 'theory_checks',
        'infeasible_checks_passed', 'existing_cpp_cases', 'matlab_rerun', 'firmware_build')}
    bridge_log = (summary_path.parent/'cpp_bridge_tests.log').read_text()
    python_log = (summary_path.parent/'python_tests.log').read_text()
    bridge_count = re.search(r'Tests run: (\d+), passed: (\d+), failed: 0', bridge_log)
    python_count = re.search(r'Ran (\d+) tests in', python_log)
    if not bridge_count or bridge_count[1] != bridge_count[2] or not python_count or '\nOK\n' not in python_log:
        raise ValueError('missing nonzero passing test receipts')
    if min(int(bridge_count[1]), int(python_count[1])) <= 0:
        raise ValueError('zero tests')
    result.update(rows=rows, summary_path=str(summary_path), summary_sha256=digest(summary_path),
                  independent_metric_replays=len(rows), cpp_bridge_tests=int(bridge_count[1]), python_tests=int(python_count[1]),
                  analysis_sha256=digest(Path(__file__)),
                  interpretation='Research diagnostics complete, not 144 successful controllers or flight qualification',
                  new_cpp_compilation='three unchanged kernels and bridge freshly compiled C++14',
                  existing_cpp_note='Existing test binaries rerun, not full firmware/test tree rebuilt',
                  update_tv_boundary='Within each window; first output has no artificial zero predecessor',
                  sample_metric='Time-weighted sampled errors, not continuous-time error integral')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = replay(args.summary.resolve())
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    paths = sorted(p for p in args.summary.parent.rglob('*') if p.is_file())
    index = [dict(path=str(p.resolve()), bytes=p.stat().st_size, sha256=digest(p)) for p in paths]
    (args.output/'archive_index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2)+'\n')
    for row in result['rows']:
        if row['period'] == 'alternating8_12ms' and row['tail_12_36'] is not None:
            tail = row['tail_12_36']
            print(row['algorithm'], row['scenario'], f"RMSE={tail['rmse']:.9g}",
                  f"TV/s={tail['correction_tv_per_s']:.9g}")
    print(json.dumps(dict(independent_replays=len(result['rows']), archive_files=len(index),
                          archive_bytes=sum(p['bytes'] for p in index))))


if __name__ == '__main__':
    main()
