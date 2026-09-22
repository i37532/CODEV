#!/usr/bin/env python3
"""Read-only failed-attempt diagnosis, NEVER supplies missing flight metrics."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from pyulog import ULog


def main():
    p=argparse.ArgumentParser(); p.add_argument('run',type=Path); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); a.output.mkdir(parents=True,exist_ok=False)
    result=json.loads((a.run/'result.json').read_text())
    start=next(e['timestamp_us'] for e in result['events'] if e['name']=='takeoff_command')
    report=dict(accepted=False,flight_completed=False,error=result.get('error'),source=result['source_head'],logs=[])
    for entry in result['logs']:
        path=Path(entry['archive'])
        assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']
        log=ULog(str(path)); info=dict(sha256=entry['sha256'],bytes=entry['bytes'],dropouts=len(log.dropouts),topics={})
        for name in ('sta_velocity_ctrl_status','sta_rate_ctrl_status','vehicle_local_position','vehicle_land_detected','vehicle_status'):
            try: d=log.get_dataset(name).data
            except (KeyError,IndexError):
                info['topics'][name]={'missing':True}; continue
            t=d['timestamp'].astype(np.int64); m=t>=start
            v=dict(n=len(t),after_takeoff_command=int(m.sum()),first_us=int(t[0]),last_us=int(t[-1]))
            if len(t)>1: v['hz']=(len(t)-1)*1e6/(t[-1]-t[0])
            if name=='sta_velocity_ctrl_status':
                for k in ('inner_valid','inner_mode','timing','valid','pid_calls','takeoff_state','landed','contact','fault','failsafe','excitation'):
                    values,counts=np.unique(d[k][m],return_counts=True)
                    v[k]=dict(zip(map(str,values.tolist()),map(int,counts)))
                v['sequence_missing']=int(np.sum(np.diff(d['publish_seq'].astype(np.int64))!=1))
                v['format_fields']=list(d)
                v['consumed_inner_timestamp_available']='inner_timestamp' in d
            if name=='sta_rate_ctrl_status':
                for k in ('effective_mode','effective_axes','div_eff','fault','abort_requested','termination','measurement_valid','output_valid'):
                    values,counts=np.unique(d[k][m],return_counts=True)
                    v[k]=dict(zip(map(str,values.tolist()),map(int,counts)))
                v['sequence_missing']=int(np.sum(np.diff(d['publish_seq'].astype(np.int64))!=1))
            if name=='vehicle_land_detected':
                v['airborne_samples_after_command']=int(np.sum(d['landed'][m]==0))
            if name=='vehicle_status':
                v['takeoff_time_max']=int(np.max(d['takeoff_time']))
            info['topics'][name]=v
        report['logs'].append(info)
    report['limitation']='Old V03 diagnostic lacks consumed inner timestamp/seq: exact per-frame age cannot be reconstructed from ULog alone. Queue mechanism separately reproduced with actual uORB functional test. No hover, excitation RMSE or landing acceptance.'
    (a.output/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
