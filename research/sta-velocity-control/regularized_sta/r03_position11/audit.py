#!/usr/bin/env python3
"""Read-only source/full-ULog/exact-prefix diagnosis of revision10 run033.

No historical acceptance can be changed by this tool. Output must be a fresh
separate file. A successful diagnostic is not a complete flight or R03 gate.
"""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import subprocess
import traceback

import numpy as np
from pyulog import ULog

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
RUN=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision10/D/batch01/run033')
PREFIX=67333572


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()


def load(name,path):
    s=importlib.util.spec_from_file_location('_position11_audit_'+name,path)
    m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def json_value(value):
    if isinstance(value,dict): return {k:json_value(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [json_value(v) for v in value]
    if isinstance(value,np.generic): return json_value(value.item())
    if isinstance(value,float) and not math.isfinite(value): return {'recorded_nonfinite':repr(value)}
    return value


def audit():
    a=load('adapter',HERE/'adapter.py'); policy=a.policy
    incremental=load('decoder',HERE.parent/'r03_monitor02/incremental.py')
    paths=[RUN/'log001.ulg', RUN/'result.json', RUN/'r03_prearm04_timing.jsonl', RUN/'height_reference.json',RUN/'task_yaw.json']
    before={str(p):sha(p) for p in paths}
    log=ULog(str(paths[0])); decoder=incremental.Decoder()
    with paths[0].open('rb') as f: decoder.feed(f.read(PREFIX))
    prefix=decoder.snapshot()
    result=dict(diagnostic_only=True,flight_accepted=False,new_flights=0,historical_acceptance_unchanged=False,
        input_sha256_before=before,source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),dropouts=len(log.dropouts),corruption=log.file_corruption,
        prefix_bytes=PREFIX,clocks=[],original_rejections={},new_checks={},selectors=[],imu=[],consumed=[])
    result['source_sha256']={str(REPO/name):sha(REPO/name) for name in (
        'src/modules/ekf2/EKF2Selector.cpp','platforms/posix/src/px4/common/drv_hrt.cpp',
        'src/modules/simulator/simulator_mavlink.cpp','src/modules/mc_pos_control/MulticopterPositionControl.cpp')}
    for topic in ('vehicle_local_position','vehicle_local_position_log','vehicle_attitude',
                  'sta_velocity_ctrl_status','velocity_ctrl_selection','vehicle_local_position_setpoint',
                  'vehicle_attitude_setpoint','vehicle_rates_setpoint','sensors_status_imu'):
        d=log.get_dataset(topic).data
        for key in ('timestamp','timestamp_sample'):
            if key not in d:continue
            t=d[key].astype(np.int64); tied=np.flatnonzero(np.diff(t)==0)+1; back=np.flatnonzero(np.diff(t)<0)+1
            result['clocks'].append(dict(topic=topic,key=key,rows=len(t),equal_count=len(tied),backward_count=len(back),
                pairs=[dict(index=int(i),before={k:d[k][i-1].item() for k in ('timestamp','timestamp_sample') if k in d},
                            after={k:d[k][i].item() for k in ('timestamp','timestamp_sample') if k in d}) for i in tied]))
    for label,raw in (('complete',log),('exact_online_prefix',prefix)):
        try: policy.legacy.checked(raw)
        except ValueError as exc: result['original_rejections'][label]=str(exc)
        else: raise ValueError('Historical rejection did not reproduce')
        view=policy.PositionLogView(raw); position=view.get_dataset('vehicle_local_position').data
        result['new_checks'][label]=dict(position_evidence=view.position_log_evidence)
        if label=='exact_online_prefix':
            h=a.build_heading()
            result['new_checks'][label]['heading']=h.live_replay(view,json.loads((RUN/'height_reference.json').read_text()),
                frozen=json.loads((RUN/'task_yaw.json').read_text()),allow_pending=True)
        original=raw.get_dataset('vehicle_local_position').data
        full=log.get_dataset('vehicle_local_position').data
        result['new_checks'][label]['all_original_columns_identical']=all(
            np.asarray(value).tobytes()==np.asarray(full[key][:len(value)]).tobytes() for key,value in original.items())
    d=log.get_dataset('sta_velocity_ctrl_status').data
    selected=np.flatnonzero((d['input_timestamp']>=128780000)&(d['input_timestamp']<=128830000))
    for i in selected:
        result['consumed'].append({k:d[k][i].item() for k in ('timestamp','input_timestamp','timestamp_sample',
            'publish_seq','update_seq','raw_dt','fault','timing','first_fail','retry_result','active_axes','pid_axes','valid')})
    selector=log.get_dataset('estimator_selector_status').data
    ix=np.flatnonzero((selector['timestamp']>128000000)&(selector['timestamp']<130000000))
    for i in ix:
        result['selectors'].append({k:selector[k][i].item() for k in ('timestamp','primary_instance','instance_changed_count',
            'last_instance_change','healthy[0]','gyro_fault_detected','accel_fault_detected')})
    for instance in range(6):
        d=log.get_dataset('estimator_status',instance).data
        ix=np.flatnonzero((d['timestamp']>128000000)&(d['timestamp']<130000000))
        result['imu'].append(dict(instance=instance,rows=[{k:d[k][i].item() for k in
            ('timestamp','timestamp_sample','time_slip','filter_fault_flags') if k in d} for i in ix]))
    result['input_sha256_after']={str(p):sha(p) for p in paths}
    result['historical_acceptance_unchanged']=before==result['input_sha256_after']
    result['success']=result['historical_acceptance_unchanged'] and all(
        item['all_original_columns_identical'] for item in result['new_checks'].values())
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() or RUN==args.output.parent or RUN in args.output.parents: raise ValueError('Fresh separate diagnostic output required')
    try: result=audit()
    except BaseException as exc:
        result=dict(success=False,diagnostic_only=True,flight_accepted=False,new_flights=0,error=repr(exc),traceback=traceback.format_exc())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(json_value(result),indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('clocks','new_checks','imu','selectors','consumed')},indent=2))
    raise SystemExit(0 if result['success'] else 1)
