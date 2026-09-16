#!/usr/bin/env python3
"""Same six-run provenance gates as M04; every axis in every fixed phase."""
import argparse
import json
from pathlib import Path
import statistics
from compare_m04 import compare as base_compare


def compare(pid, esta):
    result = base_compare(pid, esta)
    summaries = [r['summary'] for r in result['runs']]
    protocol = json.loads((pid[0]/'m04_protocol.json').read_text())
    if protocol.get('milestone') != 'M05' or any(d.get('milestone') != 'M05' or d.get('axes') != (0 if i<3 else 3) for i,d in enumerate(summaries)):
        raise ValueError('M05 mode/axes/protocol required')
    windows = ['hover', 'tracking'] + list(protocol['windows'])
    medians = {w:[statistics.median(d['metrics'][w]['rmse'][a] for d in summaries[:3]) for a in range(3)] for w in windows}
    if any(v <= 0 for values in medians.values() for v in values):
        raise ValueError('Zero PID reference; relative gate undefined')
    ratios = [{w:[d['metrics'][w]['rmse'][a]/medians[w][a] for a in range(3)] for w in windows} for d in summaries[3:]]
    violations = [dict(repeat=i+1, window=w, axis='RPY'[a], ratio=v)
                  for i,row in enumerate(ratios) for w,values in row.items() for a,v in enumerate(values) if v>result['ratio_limit']]
    result.update(success=not violations, all_axis_pid_medians=medians, all_axis_esta_ratios=ratios, violations=violations)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pid', type=Path, nargs=3, required=True)
    parser.add_argument('--esta', type=Path, nargs=3, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); result = compare(args.pid, args.esta)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    if not result['success']:
        raise SystemExit('M05 all-axis phase RMSE gate failed: '+str(result['violations']))
