#!/usr/bin/env python3
"""Read-only failed-run diagnosis; partial hover evidence is never full acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from pyulog import ULog
from analyze_v04_core04 import check_diagnostic
from analyze_v04_handoff07 import check_handoff
from analyze_v04_protocol07 import check_first_invocation
from analyze_v03 import exact_output_match
from audit_v00_results import saturation_summary
from v04_heading_stream import replay
from v04_task04 import check_cli_reference


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();run=args.run.resolve();out=args.output.resolve()
    if run==out or run in out.parents:raise ValueError('Use independent diagnosis directory')
    out.mkdir(parents=True,exist_ok=False)
    r=json.loads((run/'result.json').read_text());events={e['name']:e['timestamp_us'] for e in r['events']}
    e=dict(accepted=False,acceptance_changed=False,new_flights=0,source_head=r['source_head'],
           original_error=r['error'],events=r['events'],logs=[],checks=[])
    decoded=[]
    for item in r['logs']:
        path=Path(item['archive'])
        if sha(path)!=item['sha256']:raise ValueError('Original ULog changed')
        u=ULog(str(path));decoded.append((item['bytes'],u))
        e['logs'].append(dict(**item,dropouts=len(u.dropouts),corruption=bool(u.file_corruption)))
    u=max(decoded,key=lambda x:x[0])[1]
    def check(name,value):e['checks'].append(dict(name=name,passed=bool(value)))
    def rows(d,ids,fields):return [{k:d[k][i].item() for k in fields} for i in ids]
    check('failed_run_without_completed_landing',not r['success'] and 'landed_disarmed' not in events)
    check('original_error_is_reference_timestamp',r['error']=="ValueError('CLI reference representation changed: ref_timestamp')")
    check('no_reported_ulog_dropout_or_corruption',all(not v['dropouts'] and not v['corruption'] for v in e['logs']))
    ref=json.loads((run/'height_reference.json').read_text());frozen=json.loads((run/'task_yaw.json').read_text())
    lp=u.get_dataset('vehicle_local_position').data;ss=u.get_dataset('estimator_selector_status').data
    begin,end=events['hover_start'],events['hover_end']
    e['hover_duration_s']=(end-begin)*1e-6
    check('complete_60s_observation',60<=e['hover_duration_s']<=62)
    # Window explicitly ends at hover_end: do NOT fabricate a landed_disarmed event.
    e['heading_through_hover_only']=replay(u,ref,end=end,frozen=frozen)
    handoff_ref={**ref,'yaw':frozen['yaw']}
    e['handoff_through_hover_only']=check_handoff(u,run,handoff_ref,frozen,events)
    check('repaired_event_and_receiver_checks_pass',bool(e['handoff_through_hover_only']))
    try:replay(u,ref,end=int(lp['timestamp'][-1]),frozen=frozen)
    except ValueError as exc:e['full_record_heading_rejection']=str(exc)
    else:raise ValueError('Required rejection of the landing switch was not reproduced')
    check('raw_stream_also_rejects_not_just_CLI',True)
    last=json.loads((run/'samples.jsonl').read_text().splitlines()[-1]);e['last_host_sample']=last
    try:check_cli_reference(last['position'],ref)
    except ValueError as exc:e['reproduced_cli_rejection']=str(exc)
    else:raise ValueError('Original CLI failure not reproduced')
    check('original_CLI_failure_reproduced',True)
    switches=np.flatnonzero((np.r_[False,np.diff(ss['primary_instance'].astype(int))!=0]) & (ss['timestamp']>=events['takeoff_command']))
    e['selector_switches']=[]
    selector_fields=['timestamp','primary_instance','instance_changed_count','healthy[0]','healthy[1]',
                     'combined_test_ratio[0]','combined_test_ratio[1]','relative_test_ratio[1]',
                     'gyro_fault_detected','accel_fault_detected']
    for i in switches:e['selector_switches'].append(rows(ss,[i-1,i],selector_fields))
    check('single_actual_landing_primary_switch',len(switches)==1 and ss['timestamp'][switches[0]]>events['land_command'])
    ix=np.flatnonzero((np.r_[False,np.diff(lp['ref_timestamp'].astype(np.int64))!=0]) & (lp['timestamp']>=events['takeoff_command']))
    fields=['timestamp','ref_timestamp','ref_lat','ref_lon','ref_alt','x','y','z','vx','vy','vz','heading',
            'delta_xy[0]','delta_xy[1]','delta_z','delta_vxy[0]','delta_vxy[1]','delta_vz','delta_heading',
            'xy_reset_counter','z_reset_counter','vxy_reset_counter','vz_reset_counter','heading_reset_counter']
    e['reference_changes']=[rows(lp,[i-1,i],fields) for i in ix]
    check('raw_reference_change_aligned_with_primary_switch',len(ix)==1 and len(switches)==1 and lp['timestamp'][ix[0]]==ss['timestamp'][switches[0]])
    d=u.get_dataset('sta_velocity_ctrl_status').data;m=d['timestamp']>=events['takeoff_command']
    keys=['effective_mode','effective_axes','inner_mode','inner_axes','inner_divisor','inner_valid','first_fail',
          'retry_result','fault','sta_fault','failsafe','timing','pid_calls','valid','excitation_fault']
    e['flight_values_until_abort']={k:np.unique(d[k][m]).tolist() for k in keys}
    check('actual_velocity_and_inner_PID',all(e['flight_values_until_abort'][k]==[v] for k,v in
        dict(effective_mode=0,effective_axes=0,inner_mode=0,inner_axes=0,inner_divisor=1,inner_valid=1).items()))
    check('no_first_failure_retry_or_controller_fault',all(e['flight_values_until_abort'][k]==[0] for k in
        ('first_fail','retry_result','fault','sta_fault','failsafe','timing')))
    e['first_invocation_until_abort']=check_first_invocation(d,m)
    e['hover_diagnostic_descriptive_only']=check_diagnostic(d,begin,end,0)
    e['recorded_flight_diagnostic_until_abort']=check_diagnostic(d,events['takeoff_command'],int(d['timestamp'][-1])+1,0,False)
    pairs=[(f'v_sp[{i}]',v) for i,v in enumerate(('vx','vy','vz'))]
    pairs += [(f'a_req[{i}]',f'acceleration[{i}]') for i in range(3)]
    pairs += [(f'thrust[{i}]',f'thrust[{i}]') for i in range(3)]
    e['hover_local_output']=exact_output_match(d,u.get_dataset('vehicle_local_position_setpoint').data,'output_timestamp',pairs,begin,end)
    e['hover_attitude_output']=exact_output_match(d,u.get_dataset('vehicle_attitude_setpoint').data,'attitude_timestamp',
        [(f'q_sp[{i}]',f'q_d[{i}]') for i in range(4)],begin,end)
    rate=u.get_dataset('sta_rate_ctrl_status').data;rm=(rate['timestamp']>=begin)&(rate['timestamp']<end)
    e['hover_mixer']=saturation_summary(rate['sat_bits'][rm],rate['sat_valid'][rm])
    hm=(lp['timestamp']>=begin)&(lp['timestamp']<end);height=ref['position']['z']-lp['z'][hm]
    yaw=np.angle(np.exp(1j*(lp['heading'][hm]-frozen['yaw'])))
    e['additional_descriptive_only']=dict(height_rmse_m=float(np.sqrt(np.mean((height-2.5)**2))),
        height_max_error_m=float(np.max(np.abs(height-2.5))),yaw_rmse_rad=float(np.sqrt(np.mean(yaw**2))),
        method='Equal-weight local_position samples in completed observation, not a replacement primary metric')
    check('complete_32s_excitation_checks_pass',e['hover_diagnostic_descriptive_only']['samples']>=2500)
    status=u.get_dataset('vehicle_status').data;land=u.get_dataset('vehicle_land_detected').data
    e['last_logged_vehicle_status']=rows(status,[-1],['timestamp','nav_state','arming_state','failsafe'])[0]
    e['last_logged_land_state']=rows(land,[-1],['timestamp','landed','ground_contact'])[0]
    check('no_logged_landed_or_disarmed_after_land_command',not np.any(status['arming_state'][status['timestamp']>=events['land_command']]==1)
          and not np.any(land['landed'][land['timestamp']>=events['land_command']]))
    e['not_evaluated']='No complete landing/whole-flight acceptance, no ESTA or pair; no causal identification of the sensor innovation change. Partial windows never change accepted=false.'
    files=sorted(p for p in run.parent.rglob('*') if p.is_file() and not p.is_symlink())
    (out/'original_artifacts.sha256').write_text(''.join(f'{sha(p)}  {p}\n' for p in files))
    e['original_artifact_count']=len(files);e['diagnostic_passed']=all(c['passed'] for c in e['checks'])
    (out/'diagnosis.json').write_text(json.dumps(e,indent=2)+'\n')
    print(json.dumps(dict(checks=e['checks'],diagnostic_passed=e['diagnostic_passed'],accepted=False),indent=2))
    return 0 if e['diagnostic_passed'] else 1


if __name__=='__main__':raise SystemExit(main())
