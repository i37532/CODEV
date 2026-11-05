#!/usr/bin/env python3
"""Read-only flight diagnosis, separate output; never reclassifies acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import numpy as np
from pyulog import ULog


def main():
    p=argparse.ArgumentParser(); p.add_argument('run',type=Path); p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(); run=args.run.resolve(); out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    result=json.loads((run/'result.json').read_text()); ground=json.loads((run/'ground.json').read_text())
    events={x['name']:x['timestamp_us'] for x in result['events']}
    queries=[]
    for line in (run/'commands.jsonl').read_text().splitlines():
        c=json.loads(line)
        if 'vehicle_local_position' not in c['cmd'] or c.get('returncode')!=0: continue
        fields={k:float(v) for k,v in re.findall(r'^\s*(timestamp|z|vz):\s*([-+\d.eE]+)',c['stdout'],re.M)}
        if 'z' in fields:
            fields['height_from_ground_m']=ground[2]-fields['z']; queries.append(fields)
    logs=[]
    for entry in result['logs']:
        path=Path(entry['archive']); assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']
        u=ULog(str(path)); row=dict(archive=str(path),sha256=entry['sha256'],bytes=path.stat().st_size,dropouts=len(u.dropouts))
        for topic in ('sta_velocity_ctrl_status','sta_rate_ctrl_status','vehicle_local_position','vehicle_status'):
            try: d=u.get_dataset(topic).data
            except (KeyError,IndexError): row[topic]=dict(missing=True); continue
            t=d['timestamp']; fm=t>=events['takeoff_command']; info=dict(n=len(t),first=int(t[0]),last=int(t[-1]),flight_samples=int(fm.sum()))
            if fm.any():
                for key in ('effective_mode','effective_axes','div_eff','fault','failsafe','inner_valid','inner_mode','sta_fault','timing','pid_calls','valid','committed_axes','active_axes','nav_state','arming_state'):
                    if key in d: info[key]=np.unique(d[key][fm]).tolist()
                for key in ('publish_seq','update_seq'):
                    if key in d: info[key+'_non_unit_deltas']=int(np.sum(np.diff(d[key][fm].astype(np.int64))!=1))
                if topic=='sta_velocity_ctrl_status':
                    age=d['inner_check_timestamp'][fm].astype(np.int64)-d['inner_timestamp'][fm].astype(np.int64)
                    info.update(inner_age_max_us=int(age.max()),excitation_peak=float(np.max(np.abs(d['excitation'][fm]))),
                        excitation_time_range=[float(d['excitation_time'][fm].min()),float(d['excitation_time'][fm].max())],
                        all_pid_nu_nan=bool(np.all(np.isnan(d['nu_applied[0]'][fm]))),
                        pid_retry_timestamps=d['timestamp'][fm & (d['pid_calls']>1)].astype(int).tolist(),
                        update_counter_note='A delta of 2 at pid_calls=2 is two actual calls, not a lost publication.')
                if topic=='vehicle_local_position':
                    info['last_height_m']=float(ground[2]-d['z'][fm][-1]); info['last_vz_m_s']=float(d['vz'][fm][-1])
            row[topic]=info
        logs.append(row)
    diagnostic=dict(accepted=False,original_error=result.get('error'),events=events,ground=ground,
        last_position_queries=queries[-4:],hover_entry_required_height_m=[2.,3.],logs=logs,
        no_complete_metric_window=True,sta_flights=0,paired_comparisons=0,
        conclusion='First PID seed9101 failed frozen hover-entry height gate; recorded one same-sample PID retry also violates normal-call gate. No ESTA performance/safety inference; preserve failure, stop remaining five attempts.')
    (out/'diagnosis.json').write_text(json.dumps(diagnostic,indent=2)+'\n')
    print(json.dumps(diagnostic,indent=2))


if __name__=='__main__': main()
