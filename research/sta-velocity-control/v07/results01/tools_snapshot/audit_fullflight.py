"""Exploratory full flight components only; original failed acceptance is immutable."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from pyulog import ULog
ROOT=Path(__file__).resolve().parent
REPO=Path('/home/yr/Desktop/Codev-autopilot')
sys.path.insert(0,str(REPO/'research/sta-velocity-control/v07/protocol01'))
import common
import core
run=ROOT/'series01/run11'; r=json.loads((run/'result.json').read_text())
assert r['success'] is False
entry=max(r['logs'],key=lambda x:x['bytes'])
assert hashlib.sha256(Path(entry['archive']).read_bytes()).hexdigest()==entry['sha256']
u=ULog(entry['archive']); e={x['name']:x['timestamp_us'] for x in r['events']}
d=u.get_dataset('sta_velocity_ctrl_status').data; q=u.get_dataset('velocity_ctrl_selection').data
job=json.loads((run/'job.json').read_text())
out=dict(original_accepted=False,full_chain_acceptance=False,new_flights=0,source_head=r['source_head'],ulog_sha256=entry['sha256'])
out['velocity_control_fullflight']=core.check_diagnostic(d,q,e['takeoff_command'],e['landed_disarmed'],job,False)
out['imu']=[]
for i in range(3):
    t=u.get_dataset('vehicle_imu',i).data; s=t['timestamp_sample'].astype(np.int64)
    out['imu'].append(dict(instance=i,sample_strictly_increasing=bool(np.all(np.diff(s)>0)),
        maximum_sample_gap_us=int(np.diff(s).max()),clipping_or=int(np.bitwise_or.reduce(t['delta_velocity_clipping'])),
        calibration_counts=np.unique(t['calibration_count']).tolist()))
out['ekf']=[dict(instance=i,filter_fault_flags_or=int(np.bitwise_or.reduce(u.get_dataset('estimator_status',i).data['filter_fault_flags']))) for i in range(6)]
selector=u.get_dataset('estimator_selector_status').data
out['primary_instances']=np.unique(selector['primary_instance']).tolist()
out['instance_change_count']=np.unique(selector['instance_changed_count']).tolist()
out['source_evidence']=dict(file='src/modules/sensors/vehicle_imu/VehicleIMU.cpp',sha256=hashlib.sha256((REPO/'src/modules/sensors/vehicle_imu/VehicleIMU.cpp').read_bytes()).hexdigest(),
    lines='154: queued sample loop;467: timestamp_sample from gyro sample;474: timestamp from hrt_absolute_time',
    inference='Distinct sample integration can share lockstep publication time. No scheduling trace proves why this specific pair shared it; no upstream fix or relaxed clock rule is implemented.')
target=ROOT/'failure_audit01/fullflight_components.json'
assert not target.exists(); target.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
