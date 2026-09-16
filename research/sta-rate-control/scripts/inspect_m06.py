#!/usr/bin/env python3
"""Diagnostic only, also decodes failed attempts without changing pass/fail."""
import argparse
import json
from pathlib import Path
import numpy as np
from pyulog import ULog
from run_m00 import digest
from analyze_m00 import plain
from analyze_m03 import vector


def inspect(run):
    result=json.loads((run/'result.json').read_text())
    candidates=[]
    for item in result['logs']:
        if digest(Path(item['archive']))!=item['sha256']:raise ValueError('ULog hash')
        log=ULog(item['archive'])
        if log.initial_parameters.get('SDLOG_PROFILE')==147:candidates.append((item,log))
    if len(candidates)!=1:raise ValueError('Require one experimental ULog')
    item,log=candidates[0];d=log.get_dataset('sta_rate_ctrl_status').data
    armed=d['armed'].astype(bool);event={e['name']:e['timestamp_us'] for e in result['events']}
    first=float(d['timestamp_sample'][armed][0]) if np.any(armed) else float(d['timestamp_sample'][0])
    start=event.get('hover_start',first);t=(d['timestamp_sample'].astype(float)-start)*1e-6
    segments={}
    for name,lo,hi in [('early_hover',0,15),('tracking',15,51),('late_hover',51,60)]:
        mask=armed&(t>=lo)&(t<hi)
        if not np.any(mask):continue
        segments[name]=dict(samples=int(np.sum(mask)),rmse=np.sqrt(np.mean(vector(d,'s')[mask].astype(float)**2,axis=0)),
            mean_error=np.mean(vector(d,'s')[mask].astype(float),axis=0),
            mean_nu=np.mean(vector(d,'nu')[mask].astype(float),axis=0),
            min_nu=np.min(vector(d,'nu')[mask],axis=0),max_nu=np.max(vector(d,'nu')[mask],axis=0),
            limits_fraction={str(a):{str(b):float(np.mean(d[f'limits[{a}]'][mask]&b!=0)) for b in (1,2,4,8)} for a in range(3)})
    indices=np.unique(np.minimum(np.searchsorted(d['timestamp_sample'],np.arange(first,d['timestamp_sample'][-1]+1,250000)),len(t)-1))
    rows=[]
    for i in indices:
        rows.append(dict(time_from_arming=(float(d['timestamp_sample'][i])-first)*1e-6,
            armed=bool(d['armed'][i]),landed=bool(d['landed'][i]),fault=int(d['fault'][i]),
            rate=vector(d,'rate')[i],sp=vector(d,'rate_sp')[i],nu=vector(d,'nu')[i],command=vector(d,'c_applied')[i],
            motor_saturation=int(d['motor_saturation'][i])))
    asp=log.get_dataset('vehicle_attitude_setpoint').data
    att=log.get_dataset('vehicle_attitude').data
    outer=(asp['timestamp']>=start)&(asp['timestamp']<=event.get('hover_end',start))&(np.abs(asp['yaw_sp_move_rate'])>.15)
    outer_events=[]
    for i in np.flatnonzero(outer):
        previous=np.clip(np.searchsorted(att['timestamp'],asp['timestamp'][i],side='right')-1,0,len(att['timestamp'])-1)
        outer_events.append(dict(timestamp_us=int(asp['timestamp'][i]),yaw_body=float(asp['yaw_body'][i]),
            yaw_sp_move_rate=float(asp['yaw_sp_move_rate'][i]),quat_reset_counter=int(att['quat_reset_counter'][previous])))
    return dict(scope='Diagnosis only, not acceptance; original result unchanged',scenario_success=result['success'],
                error=result.get('error'),ulog_sha256=item['sha256'],segments=segments,samples_250ms=rows,
                outer_yaw_feedforward_events=outer_events)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    with args.output.open('x') as f:json.dump(inspect(args.run),f,indent=2,default=plain);f.write('\n')
