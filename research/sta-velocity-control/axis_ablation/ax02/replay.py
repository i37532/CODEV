#!/usr/bin/env python3
"""Read-only component replay. Never regrade old logs as AX03 attempts."""
import argparse
import copy
import json
from pathlib import Path
import numpy as np
import common
import core
import cadence
import task
from position_log import ULog
from v04_attitude_clock09 import AttitudeClockPolicy
from v04_heading_stream import replay as heading

SOURCE=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260929/V08/validation02')

def replay():
    rows=[]
    for number in range(7,13):
        run=SOURCE/f'run{number:02d}'
        protected={str(p):common.fingerprint(p) for p in run.iterdir() if p.is_file() and p.suffix in ('.json','.ulg','.jsonl')}
        record=json.loads((run/'result.json').read_text()); job=json.loads((run/'job.json').read_text())
        saved=json.loads((run/'xyz_metrics.json').read_text())
        entry=max(record['logs'],key=lambda x:x['bytes'])
        if common.fingerprint(entry['archive'])!=entry['sha256']:raise ValueError('Changed historical ULog')
        u=ULog(entry['archive']);d=u.get_dataset('sta_velocity_ctrl_status').data;q=u.get_dataset('velocity_ctrl_selection').data
        events={v['name']:v['timestamp_us'] for v in record['events']}
        numerical=core.check_diagnostic(d,q,events['hover_start'],events['hover_end'],job)
        flight=core.check_diagnostic(d,q,events['takeoff_command'],events['landed_disarmed'],job,False)
        sm=(d['timestamp']>=events['hover_start'])&(d['timestamp']<events['hover_end']);sd={k:v[sm] for k,v in d.items()}
        pid=cadence.check_pid_path(sd,cadence.aligned(sd,q),job,u.initial_parameters)
        # Task label alias only, not gains/mode/seeds/measurements. H is exactly
        # the old mode6 trajectory; this does not meet AX03 source/authority.
        historical_task={**job,'task':'H'}
        target=task.check_targets(u,d,events,historical_task)
        policy=AttitudeClockPolicy()
        ref=json.loads((run/'height_reference.json').read_text());yaw=json.loads((run/'task_yaw.json').read_text())
        reset=heading(u,ref,end=events['landed_disarmed'],frozen=yaw,attitude_policy=policy)
        if numerical['error']!=saved['diagnostic']['error']:raise ValueError('Changed historical RMSE')
        for p,h in protected.items():
            if common.fingerprint(p)!=h:raise ValueError('Historical artifact modified')
        rows.append(dict(run=str(run),mode=job['mode'],axes=job['axes'],ulog_sha256=entry['sha256'],
            original_verdict=saved['accepted'],component_checks_passed=True,ax03_eligible=False,
            diagnostic=numerical,flight=flight,pid=pid,target=target,reset=reset,
            original_artifacts_unchanged=len(protected)))
    return dict(success=len(rows)==6,meaning='Existing H-compatible evidence only; no new acceptance, no V/Z flight claim',runs=rows,new_flights=0)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    r=replay();args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as f:json.dump(r,f,indent=2)
    print(json.dumps(dict(success=r['success'],old_logs=len(r['runs']),new_flights=0)))
