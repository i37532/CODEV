#!/usr/bin/env python3
"""Diagnose a completed or rejected PID run without changing its acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from pyulog import ULog
from analyze_m03 import vector, pid_output, sequence_stats, require
from analyze_m04 import check_gyro_events


def inspect(run):
    result=json.loads((run/'result.json').read_text())
    protocol=json.loads((run/'m04_protocol.json').read_text())
    logs=[(item,ULog(item['archive'])) for item in result['logs']]
    item,log=next((item,log) for item,log in logs if log.initial_parameters.get('SDLOG_PROFILE')==147)
    require(hashlib.sha256(Path(item['archive']).read_bytes()).hexdigest()==item['sha256'],'ULog hash')
    d=log.get_dataset('sta_rate_ctrl_status').data
    require(np.all(d['effective_mode']==0),'PID-only diagnosis')
    gyro=log.get_dataset('gyro_sample_status').data
    check_gyro_events(gyro,d['timestamp_sample'])
    armed=d['armed'].astype(bool); updated=d['updated'].astype(bool)
    events={e['name']:e['timestamp_us'] for e in result['events']}
    hover=(d['timestamp_sample']>=events['hover_start'])&(d['timestamp_sample']<=events['hover_end'])
    tracking=hover&(d['research_elapsed']>=0)&(d['research_elapsed']<=24)
    mismatches=int(np.count_nonzero(pid_output(d)[updated].copy().view(np.uint32)!=vector(d,'c_raw')[updated].copy().view(np.uint32)))
    act=log.get_dataset('actuator_controls_0').data
    common,di,ai=np.intersect1d(d['timestamp_sample'][updated],act['timestamp_sample'],return_indices=True)
    command=np.column_stack([act[f'control[{i}]'] for i in range(3)])
    actuator_mismatches=int(np.count_nonzero(vector(d,'c_applied')[updated][di].view(np.uint32)!=command[ai].view(np.uint32)))
    violations=np.flatnonzero(armed&(np.abs(d['c_applied[0]'])>protocol['limits']['roll_command_abs']+1e-6))
    fields=['timestamp_sample','raw_dt','c_applied[0]','rate[0]','rate_sp[0]','angular_accel[0]','landed','maybe_landed']
    rows=[]
    for i in violations:
        row={k:d[k][i].item() for k in fields}
        for topic in ['vehicle_local_position','vehicle_local_position_groundtruth']:
            pos=log.get_dataset(topic).data
            j=int(np.argmin(abs(pos['timestamp'].astype(float)-d['timestamp_sample'][i])))
            row[topic]={k:pos[k][j].item() for k in ['timestamp','z','vz']}
        rows.append(row)
    return dict(note='Diagnostic only, not M04 acceptance. No samples excluded from gate.',
        source_head=result['source_head'],binary_sha256=result['binary_sha256'],ulog_sha256=item['sha256'],
        flight_completed=result['success'],events=events,pid_bit_mismatches=mismatches,
        pid_compared_samples=int(np.count_nonzero(updated)),actuator_matched_samples=len(common),actuator_mismatches=actuator_mismatches,
        published_dt_us=np.unique(np.diff(d['timestamp_sample'])).tolist(),
        armed_timing_bad=int(np.count_nonzero(d['timing_status'][armed])),
        fault_count=int(np.count_nonzero(d['fault'])),abort_count=int(np.count_nonzero(d['abort_requested'])),
        sequences={name:sequence_stats(d[field][hover],d['timestamp_sample'][hover]) for name,field in [('status','publish_seq'),('updates','update_seq')]},
        gyro_events=[{k:v[i].item() for k,v in gyro.items()} for i in range(len(gyro['timestamp']))],
        roll_bound_violations=rows,roll_peak_armed=float(np.max(abs(d['c_applied[0]'][armed]))),
        roll_peak_hover=float(np.max(abs(d['c_applied[0]'][hover]))),
        rmse={name:np.sqrt(np.mean(vector(d,'s')[mask].astype(float)**2,axis=0)).tolist() for name,mask in [('hover',hover),('tracking',tracking)]})


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('run',type=Path); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    with args.output.open('x') as stream:
        json.dump(inspect(args.run),stream,indent=2); stream.write('\n')
