#!/usr/bin/env python3
"""Save read-only diagnosis of M04 PID timing rejection; never changes acceptance."""
import argparse
import json
from pathlib import Path
import numpy as np
from pyulog import ULog


def inspect(run):
    result=json.loads((run/'result.json').read_text())
    logs=[(item,ULog(item['archive'])) for item in result['logs']]
    item,log=next((item,log) for item,log in logs if log.initial_parameters.get('SDLOG_PROFILE')==147)
    d=log.get_dataset('sta_rate_ctrl_status').data
    selection=log.get_dataset('sensor_selection').data
    bad=np.flatnonzero(d['armed']&(d['timing_status']!=0))
    fields=['timestamp','timestamp_sample','raw_dt','dt','timing_status','publish_seq','update_seq',
            'rate[0]','angular_accel[0]','rate_sp[0]','armed','landed','maybe_landed']
    rows=[]
    for i in bad:
        timestamp=int(d['timestamp_sample'][i])
        matched=np.flatnonzero(selection['timestamp']==timestamp)
        rows.append(dict(samples=[{k:d[k][j].item() for k in fields} for j in range(max(0,i-1),min(len(d['timestamp']),i+2))],
                         matching_sensor_switch=[{k:v[j].item() for k,v in selection.items()} for j in matched]))
    events={e['name']:e['timestamp_us'] for e in result['events']}
    hover=(d['timestamp_sample']>=events['hover_start'])&(d['timestamp_sample']<=events['hover_end'])
    return dict(status='blocked',flight_completed=result['success'],acceptance_passed=False,ulog_sha256=item['sha256'],
                armed_bad_sample_count=len(bad),events=events,diagnosis=rows,
                hover_rmse=np.sqrt(np.mean(np.column_stack([d[f's[{i}]'][hover] for i in range(3)]).astype(float)**2,axis=0)).tolist(),
                note='Changed gyro measurement at identical sample time coincides with sensor_selection switch. Not merely duplicate logging. No ESTA flight performed.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('run',type=Path); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    with args.output.open('x') as stream:
        json.dump(inspect(args.run),stream,indent=2); stream.write('\n')
