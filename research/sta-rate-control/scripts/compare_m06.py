#!/usr/bin/env python3
"""M06 equal-provenance six-flight comparison; all axes and fixed windows."""
import argparse
import json
import statistics
from pathlib import Path
from compare_m04 import compare as base_compare


def compare(pid, esta):
    result = base_compare(pid, esta)
    summaries = [r['summary'] for r in result['runs']]
    protocol = json.loads((pid[0]/'m04_protocol.json').read_text())
    if (protocol.get('milestone') != 'M06' or protocol['trigger'] != 4 or protocol.get('version') != 2
            or protocol.get('scenario_parameters',{}).get('MPC_YAW_MODE') != 3 or 'heading_contract' not in protocol):
        raise ValueError('Full M06 v2 fixed-heading combined scene required, not v1 or yaw precursor')
    for i, d in enumerate(summaries):
        if d.get('milestone') != 'M06' or d.get('axes') != (0 if i < 3 else 7):
            raise ValueError('M06 mode/axes mismatch')
        if i >= 3 and d.get('pid_updates_armed') != 0:
            raise ValueError('Full-axis ESTA must not calculate PID')
        if i < 3 and d.get('pid_updates_armed',0) <= 0:
            raise ValueError('PID reference must actually calculate PID')
        if not 0 <= d.get('max_outer_yaw_feedforward_rad_s',float('inf')) <= protocol['heading_contract']['max_outer_yaw_feedforward_rad_s']:
            raise ValueError('Unverified fixed-heading scene')
    windows = ['hover', 'tracking', *protocol['windows']]
    medians = {w: [statistics.median(d['metrics'][w]['rmse'][a] for d in summaries[:3]) for a in range(3)] for w in windows}
    if any(v <= 0 for row in medians.values() for v in row):
        raise ValueError('Undefined relative reference')
    ratios = [{w: [d['metrics'][w]['rmse'][a]/medians[w][a] for a in range(3)] for w in windows} for d in summaries[3:]]
    violations = [dict(repeat=i+1,window=w,axis='RPY'[a],ratio=v)
                  for i,row in enumerate(ratios) for w,values in row.items() for a,v in enumerate(values) if v>result['ratio_limit']]
    result.update(success=not violations, all_axis_pid_medians=medians, all_axis_esta_ratios=ratios, violations=violations)
    return result


if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--pid',type=Path,nargs=3,required=True)
    p.add_argument('--esta',type=Path,nargs=3,required=True); p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(); result=compare(args.pid,args.esta)
    with args.output.open('x') as stream: json.dump(result,stream,indent=2); stream.write('\n')
    if not result['success']: raise SystemExit('M06 RMSE gate failed: '+str(result['violations']))
