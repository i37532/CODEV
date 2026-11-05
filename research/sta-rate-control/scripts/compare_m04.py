#!/usr/bin/env python3
"""Require three accepted, same-protocol runs per mode; no cherry-picked windows."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics


def compare(pid, esta):
    runs=pid+esta
    if len(pid)!=3 or len(esta)!=3 or len({p.resolve() for p in runs})!=6:
        raise ValueError('Exactly three distinct runs per mode required')
    summaries=[json.loads((p/'m04_analysis.json').read_text()) for p in runs]
    if not all(d['success'] and d['mode']==int(i>=3) for i,d in enumerate(summaries)):
        raise ValueError('Acceptance or mode mismatch')
    protocols=[(p/'m04_protocol.json').read_bytes() for p in runs]
    if len(set(protocols))!=1 or len({d['binary_sha256'] for d in summaries})!=1:
        raise ValueError('Protocol or firmware differs')
    sources=[json.loads((p/'m04_source_hashes.json').read_text()) for p in runs]
    if sources!=[sources[0]]*6:
        raise ValueError('Calibration or scenario source differs')
    configs=[json.loads((p/'m04_config.json').read_text()) for p in runs]
    if configs[3:]!=[configs[3]]*3:
        raise ValueError('ESTA parameters differ')
    for c in configs:
        if any(c.get(k)!=v for k,v in json.loads(protocols[0]).get('scenario_parameters',{}).items()):
            raise ValueError('Scenario parameters differ')
    if len({d['ulog_sha256'] for d in summaries})!=6:
        raise ValueError('Duplicate raw logs')
    limit=json.loads(protocols[0])['limits']['rmse_ratio_max']
    medians={w:statistics.median(d['metrics'][w]['rmse'][0] for d in summaries[:3]) for w in ['hover','tracking']}
    ratios=[{w:d['metrics'][w]['rmse'][0]/medians[w] for w in medians} for d in summaries[3:]]
    return dict(success=all(r<=limit for row in ratios for r in row.values()),
        scope='Development SITL; retained failed/tuning attempts are reported separately, not independent statistical trials.',
        protocol_sha256=hashlib.sha256(protocols[0]).hexdigest(),binary_sha256=summaries[0]['binary_sha256'],
        pid_median_rmse=medians,esta_ratios=ratios,ratio_limit=limit,
        runs=[dict(path=str(p.resolve()),summary=d) for p,d in zip(runs,summaries)])


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--pid',type=Path,nargs=3,required=True)
    parser.add_argument('--esta',type=Path,nargs=3,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); result=compare(args.pid,args.esta)
    with args.output.open('x') as stream:
        json.dump(result,stream,indent=2); stream.write('\n')
    if not result['success']:
        raise SystemExit('M04 RMSE gate failed')
