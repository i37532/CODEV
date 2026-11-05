#!/usr/bin/env python3
"""Offline replay of seven existing PID records, including both failed V04 runs.

No simulator commands, writes to original logs, or acceptance reclassification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
from pyulog import ULog

REPO=Path(__file__).resolve().parents[3]
RESEARCH=REPO/'research/sta-velocity-control'
RECORDS=[('V00-1','v00/resume02/results/run01_result.json'),
         ('V00-2','v00/resume02/results/run02_result.json'),
         ('V00-3','v00/resume02/results/run03_result.json'),
         ('V01','v01/results/run01.json'),('V03','v03/results02/run01_result.json'),
         ('V04-series01','v04/results01/run01_result.json'),('V04-series02','v04/results03/run01.json')]
SOURCES=['src/lib/ecl/EKF/mag_control.cpp','src/lib/ecl/EKF/ekf_helper.cpp','src/lib/ecl/EKF/ekf.h',
         'src/modules/ekf2/EKF2.cpp','src/modules/ekf2/EKF2Selector.cpp',
         'src/modules/flight_mode_manager/tasks/FlightTask/FlightTask.cpp',
         'src/modules/flight_mode_manager/tasks/Auto/FlightTaskAuto.cpp',
         'src/modules/flight_mode_manager/tasks/AutoLineSmoothVel/FlightTaskAutoLineSmoothVel.cpp',
         'src/modules/flight_mode_manager/tasks/ManualAltitude/FlightTaskManualAltitude.cpp',
         'src/modules/mc_pos_control/MulticopterPositionControl.cpp',
         'src/modules/mc_att_control/mc_att_control_main.cpp','src/modules/mc_att_control/AttitudeControl/AttitudeControl.hpp']


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def wrap(x): return np.angle(np.exp(1j*x))


def preceding(d,t):
    i=int(np.searchsorted(d['timestamp'],t,side='right'))-1
    if i<0: raise ValueError('No preceding evidence')
    return i


def yaw(d,field='q'):
    w,x,y,z=[d[f'{field}[{i}]'].astype(float) for i in range(4)]
    return np.arctan2(2*(w*z+x*y),1-2*(y*y+z*z))


def audit(label,record):
    r=json.loads(record.read_text()); start=next(e['timestamp_us'] for e in r['events'] if e['name']=='takeoff_command')
    selected=None; fingerprints=[]
    for entry in r['logs']:
        path=Path(entry['archive']); assert sha(path)==entry['sha256'], str(path)
        fingerprints.append(entry)
        u=ULog(str(path))
        try: d=u.get_dataset('vehicle_local_position').data
        except (KeyError,IndexError): continue
        if len(d['timestamp']) and d['timestamp'][-1]>start: selected=(u,d)
    if selected is None: raise ValueError('No takeoff record')
    u,d=selected; ground=json.loads((Path(fingerprints[-1]['archive']).parent/'ground.json').read_text())
    row=dict(label=label,record=str(record),source_head=r['source_head'],historical_success=r['success'],
             historical_error=r.get('error'),ulog_fingerprints=fingerprints,dropouts=len(u.dropouts),
             flight_start_us=start,flight_last_us=int(d['timestamp'][-1]),resets=[],other_reference_changes={})
    m=d['timestamp']>=start
    for key in ('ref_timestamp','ref_lat','ref_lon','ref_alt','xy_reset_counter','z_reset_counter','vxy_reset_counter','vz_reset_counter'):
        row['other_reference_changes'][key]=int(np.count_nonzero(np.diff(d[key][m].astype(float))))
    selector=u.get_dataset('estimator_selector_status').data
    si=preceding(selector,start)
    row['primary_instances']=np.unique(selector['primary_instance'][si:]).tolist()
    att=u.get_dataset('vehicle_attitude').data; ay=yaw(att); dq=yaw(att,'delta_q_reset')
    traj=u.get_dataset('trajectory_setpoint').data
    out=u.get_dataset('vehicle_local_position_setpoint').data
    status=u.get_dataset('vehicle_status').data; land=u.get_dataset('vehicle_land_detected').data
    try: diag=u.get_dataset('sta_velocity_ctrl_status').data
    except (KeyError,IndexError): diag=None
    ix=np.flatnonzero(np.r_[False,np.diff(d['heading_reset_counter'].astype(int))!=0]&m)
    for i in ix:
        t=int(d['timestamp'][i]); delta=float(d['delta_heading'][i]); primary=int(selector['primary_instance'][preceding(selector,t)])
        es=u.get_dataset('estimator_status',primary).data; flags=es['control_mode_flags'].astype(np.uint32)
        aligned=(flags>>23)&1
        changes=np.flatnonzero(np.r_[False,np.diff(aligned.astype(int))==1] & (np.abs(es['timestamp'].astype(float)-t)<=500000))
        before=preceding(es,t-200000)
        near=np.flatnonzero((att['timestamp']>=t-40000)&(att['timestamp']<=t+40000)
                            & np.r_[False,np.diff(att['quat_reset_counter'].astype(int))!=0])
        event=dict(timestamp=t,count_before=int(d['heading_reset_counter'][i-1]),count_after=int(d['heading_reset_counter'][i]),
            delta_heading_rad=delta,delta_heading_deg=float(np.rad2deg(delta)),
            height_from_ground_m=float(ground[2]-d['z'][i]),dist_bottom_m=float(d['dist_bottom'][i]),dist_bottom_valid=bool(d['dist_bottom_valid'][i]),
            primary=primary,nav_state=int(status['nav_state'][preceding(status,t)]),armed=int(status['arming_state'][preceding(status,t)]),
            landed=bool(land['landed'][preceding(land,t)]),
            primary_aligned_before=int(aligned[before]),
            alignment_transition_lag_us=[int(es['timestamp'][j])-t for j in changes],
            attitude_reset_lag_us=[int(att['timestamp'][j])-t for j in near],
            quaternion_delta_yaw_rad=[float(dq[j]) for j in near])
        # Inspect sampled outputs, not hidden internal attitude-controller state.
        trace=[]
        for j in np.flatnonzero((out['timestamp']>=t-40000)&(out['timestamp']<=t+200000)):
            ts=int(out['timestamp'][j]); ai=preceding(att,ts); ti=preceding(traj,ts)
            item=dict(timestamp=ts,published_yaw=float(out['yaw'][j]),trajectory_timestamp=int(traj['timestamp'][ti]),
                trajectory_yaw=float(traj['yaw'][ti]),attitude_timestamp=int(att['timestamp'][ai]),measured_yaw=float(ay[ai]),
                yaw_error_rad=float(wrap(out['yaw'][j]-ay[ai])))
            if diag is not None:
                di=np.flatnonzero(diag['output_timestamp']==ts)
                if len(di)==1:
                    k=di[0]; item.update(consumed_setpoint_timestamp=int(diag['setpoint_timestamp'][k]),reset_bits=int(diag['reset_bits'][k]),
                        pid_calls=int(diag['pid_calls'][k]),valid=bool(diag['valid'][k]))
            trace.append(item)
        event['output_trace']=trace
        pre=preceding(out,t-1); post=preceding(out,t)
        event['published_yaw_step_at_local_reset_rad']=float(wrap(out['yaw'][post]-out['yaw'][pre]))
        event['nearby_peak_abs_yaw_error_rad']=max(abs(v['yaw_error_rad']) for v in trace)
        metadata={}
        for name,instance,keys in [
            ('estimator_selector_status',0,['primary_instance','instance_changed_count',f'healthy[{primary}]','gyro_fault_detected','accel_fault_detected']),
            ('estimator_status',primary,['control_mode_flags','filter_fault_flags']),
            ('estimator_status_flags',primary,['cs_mag_aligned_in_flight','cs_yaw_align','cs_mag_fault','cs_mag_field_disturbed','cs_ev_yaw','cs_gps_yaw']),
            ('estimator_event_flags',primary,['information_event_changes','warning_event_changes','emergency_yaw_reset_mag_stopped','yaw_aligned_to_imu_gps','bad_yaw_using_gps_course'])]:
            stream=u.get_dataset(name,instance).data; j=preceding(stream,t)
            metadata[name]=dict(instance=instance,preceding_timestamp=int(stream['timestamp'][j]),age_s=(t-int(stream['timestamp'][j]))*1e-6,
                values={key:stream[key][j].item() for key in keys},
                nearby_publication_times=stream['timestamp'][(stream['timestamp']>=t-1000000)&(stream['timestamp']<=t+500000)].astype(int).tolist())
        event['metadata_observations']=metadata
        row['resets'].append(event)
    row['parameters']={k:u.initial_parameters.get(k) for k in ('EKF2_MAG_TYPE','MPC_YAW_MODE','MPC_POS_MODE','MPC_VC_MODE','MC_RTC_MODE')}
    return row


def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',type=Path,required=True); args=p.parse_args()
    out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    evidence=dict(kind='offline_descriptive_development_audit_not_acceptance',new_flights=0,
        source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        source_hashes={name:sha(REPO/name) for name in SOURCES},
        submodules=subprocess.check_output(['git','submodule','status','--recursive'],cwd=REPO,text=True).splitlines(),
        records=[])
    for label,path in RECORDS:
        row=audit(label,RESEARCH/path); evidence['records'].append(row)
        print(label, 'historical_success='+str(row['historical_success']),
              'resets='+str([(x['timestamp'],round(x['delta_heading_deg'],6)) for x in row['resets']]),flush=True)
    evidence['limitations']=['Historical developmental PID data, not new paired samples or performance evidence.',
        'ULog published yaw is not the internal adapted attitude-controller quaternion.',
        'Alignment flags are asynchronous; no interpolation or exact private-function call claim.',
        'dist_bottom_valid can be false; exported range is not an exact reconstruction of private delayed terrain predicate.']
    (out/'audit.json').write_text(json.dumps(evidence,indent=2)+'\n')


if __name__=='__main__': main()
