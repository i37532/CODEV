#!/usr/bin/env python3
"""Read-only series08 failure diagnosis. No regrading, launch or checker repair."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from pyulog import ULog
from analyze_v04_core04 import check_diagnostic
from analyze_v04_protocol09 import check_first_invocation
from audit_v04_protocol08_failure import attitude_records
from v04_attitude_clock09 import AttitudeClockPolicy
from v04_heading_stream import LiveLog, TOPICS
from v04_task04 import scalars, excitation_class


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();run=args.run.resolve();out=args.output.resolve()
    if out==run or run in out.parents or out in run.parents:raise ValueError('Independent output required')
    original={str(path):sha(path) for path in run.parent.rglob('*') if path.is_file()}
    out.mkdir(parents=True,exist_ok=False)
    result=json.loads((run/'result.json').read_text());ledger=json.loads((run.parent/'ledger.json').read_text())
    events={x['name']:int(x['timestamp_us']) for x in result['events']}
    e=dict(kind='read_only_diagnosis_not_flight_acceptance',accepted=False,acceptance_changed=False,
        new_flights=0,source_head=result['source_head'],original_error=result.get('error'),events=events,checks=[],logs=[])
    def check(name,value):e['checks'].append(dict(name=name,passed=bool(value)))
    decoded=[]
    for entry in result['logs']:
        if sha(entry['archive'])!=entry['sha256']:raise ValueError('Original ULog changed')
        log=ULog(entry['archive']);decoded.append((entry['bytes'],log,entry))
        e['logs'].append(dict(**entry,dropouts=len(log.dropouts),corruption=bool(log.file_corruption)))
    _,u,entry=max(decoded,key=lambda x:x[0])
    check('no_reported_ulog_dropout_corruption',all(not x['dropouts'] and not x['corruption'] for x in e['logs']))
    check('one_failed_attempt_remaining_five_not_run',len(ledger['attempts'])==1 and ledger['attempts'][0]['status']=='failed'
          and len(list(run.parent.glob('run[0-9][0-9]')))==1 and not ledger['success'])
    check('parameters_restored_and_owned_processes_stopped',ledger['parameter_restore_exact'] and not ledger['remaining_simulators'])
    check('no_completed_landing_or_acceptance',not result['success'] and 'landed_disarmed' not in events)
    e['observation_seconds']=(events['hover_end']-events['hover_start'])*1e-6
    check('recorded_complete_observation',60<=e['observation_seconds']<=62)
    commands=[json.loads(x) for x in (run/'commands.jsonl').read_text().splitlines()]
    land_commands=[i for i,c in enumerate(commands) if c['cmd'][-2:]==['mode','auto:land']]
    check('one_successful_planned_land_command',len(land_commands)==1 and commands[land_commands[0]]['returncode']==0)
    after=commands[land_commands[0]+1:]
    def cli_topic(name):
        return scalars(next(c['stdout'] for c in after if c['cmd'][-3:]==[name,'-n','1']))
    status_cli=cli_topic('vehicle_status');diagnostic_cli=cli_topic('sta_velocity_ctrl_status')
    selected=lambda d,fields:{k:d[k] for k in fields}
    e['mixed_host_snapshot']=dict(status=selected(status_cli,['timestamp','nav_state','arming_state','failsafe']),
        diagnostic=selected(diagnostic_cli,['timestamp','excitation_fault','excitation','armed','fault','failsafe']),
        age_difference_us=diagnostic_cli['timestamp']-status_cli['timestamp'])
    try:
        excitation_class(int(diagnostic_cli['excitation_fault']),bool(diagnostic_cli['armed']),
                         int(status_cli['nav_state']),True,True,diagnostic_cli['excitation'])
    except ValueError as exc:e['mixed_snapshot_rejection']=str(exc)
    check('archived_cli_reproduces_exact_online_error',e.get('mixed_snapshot_rejection')=='Unexpected excitation fault 2')
    d=u.get_dataset('sta_velocity_ctrl_status').data;status=u.get_dataset('vehicle_status').data
    active=(d['timestamp']>=events['takeoff_command']) & d['enabled'].astype(bool)
    fault_rows=np.flatnonzero(d['excitation_fault']!=0)
    k=int(fault_rows[0]);t=int(d['timestamp'][k]);srows=np.flatnonzero(status['timestamp']==t)
    check('fault_first_occurs_after_plan_land_with_same_timestamp_status',t>=events['land_command'] and len(srows)==1)
    si=int(srows[0])
    e['raw_transition']=dict(diagnostic_timestamp_us=t,status_timestamp_us=int(status['timestamp'][si]),
        nav_state=int(status['nav_state'][si]),nav_state_timestamp_us=int(status['nav_state_timestamp'][si]),
        fault=int(d['excitation_fault'][k]),excitation=float(d['excitation'][k]),
        excitation_time_s=float(d['excitation_time'][k]),
        classification=excitation_class(int(d['excitation_fault'][k]),bool(d['armed'][k]),
                                     int(status['nav_state'][si]),True,True,float(d['excitation'][k])))
    check('raw_transition_has_existing_expected_landing_class',e['raw_transition']['classification']=='expected_planned_landing_gate')
    check('only_gate_bit_after_land',np.all(d['excitation_fault'][fault_rows]==2) and np.all(d['timestamp'][fault_rows]>=events['land_command']))
    check('archived_host_used_old_loiter_snapshot',status_cli['nav_state']==4 and status_cli['timestamp']<t==diagnostic_cli['timestamp'])
    expected=dict(effective_mode=0,effective_axes=0,inner_mode=0,inner_axes=0,inner_divisor=1,inner_valid=1,
                  first_fail=0,retry_result=0,fault=0,sta_fault=0,failsafe=0,timing=0,pid_calls=1,valid=1)
    e['active_controller_fields']={key:np.unique(d[key][active]).tolist() for key in expected}
    check('actual_PID_and_no_recorded_controller_failure',all(e['active_controller_fields'][key]==[value] for key,value in expected.items()))
    e['first_invocation']=check_first_invocation(d,active)
    check('velocity_publication_continuous',np.all(np.diff(d['publish_seq'][active].astype(np.int64))==1))
    rate=u.get_dataset('sta_rate_ctrl_status').data;rm=rate['timestamp']>=events['takeoff_command']
    check('rate_publication_continuous',np.all(np.diff(rate['publish_seq'][rm].astype(np.int64))==1))
    e['hover_diagnostic_component_only']=check_diagnostic(d,events['hover_start'],events['hover_end'],0)
    check('complete_32s_excitation_component',e['hover_diagnostic_component_only']['samples']>=2500)
    policy=AttitudeClockPolicy();att=policy.data(u);target=u.get_dataset('vehicle_attitude_setpoint').data
    e['attitude_clock']=dict(records=len(att['timestamp']),equal_publications=int(np.count_nonzero(np.diff(att['timestamp'].astype(np.int64))==0)),
        sample_periods_us=np.unique(np.diff(att['timestamp_sample'].astype(np.int64))).tolist())
    e['hover_attitude_safety_component_only']=policy.safety(att,target,events['hover_start'],events['hover_end'])
    e['hover_yaw_descriptive_component_only']=policy.yaw_metrics(att,target,events['hover_start'],events['hover_end'])
    raw=attitude_records(Path(entry['archive']))
    check('independent_binary_attitude_clocks_match',np.array_equal([x['timestamp'] for x in raw],att['timestamp'])
          and np.array_equal([x['timestamp_sample'] for x in raw],att['timestamp_sample']))
    live=LiveLog(entry['archive']).read();arrays=0
    for ds in u.data_list:
        if ds.name not in TOPICS:continue
        got=live.get_dataset(ds.name,ds.multi_id).data
        for name,values in ds.data.items():np.testing.assert_array_equal(got[name],values);arrays+=1
    e['live_independent_field_arrays_equal']=arrays
    check('live_parser_no_row_loss',arrays>0)
    pos=u.get_dataset('vehicle_local_position').data;pm=pos['timestamp']>=events['takeoff_command']
    keys=['ref_timestamp','ref_lat','ref_lon','ref_alt','xy_reset_counter','z_reset_counter','vxy_reset_counter','vz_reset_counter']
    e['reference_and_counters']={key:np.unique(pos[key][pm]).tolist() for key in keys}
    selector=u.get_dataset('estimator_selector_status').data
    e['primary_instances']=np.unique(selector['primary_instance']).tolist()
    check('no_recorded_reference_or_primary_switch',all(len(v)==1 for v in e['reference_and_counters'].values())
          and len(e['primary_instances'])==1 and not np.any(np.diff(selector['instance_changed_count'].astype(np.int64))))
    heading=[json.loads(x) for x in (run/'heading_live.jsonl').read_text().splitlines()]
    e['live_transport']=dict(polls=len(heading),min_age_us=min(x['age_us'] for x in heading),max_age_us=max(x['age_us'] for x in heading))
    params=json.loads((run/'runtime_parameters_start.json').read_text())
    e['runtime_parameters']={key:params[key] for key in ['MC_RTC_MODE','MC_STA_AXES','MC_RTC_DIV','MC_RATT_TEST','MC_STA_TKO_MGT','MPC_VC_MODE','MPC_VC_AXES','MPC_VCT_TEST','SDLOG_PROFILE']}
    e['limitations']=['No completed landing, no accepted attempt, no ESTA flight or paired comparison.',
        'Raw timestamps do not prove cross-topic consumer causality; CLI command order proves this host mixed old status with newer diagnostic.',
        'Hover component metrics are exploratory failed-attempt evidence, not complete-flight acceptance.',
        'No production, runner, checker, parameter, threshold or frozen protocol repair performed.']
    for path,expected_sha in original.items():
        if sha(path)!=expected_sha:raise ValueError('Original input modified')
    index=''.join(f'{value}  {key}\n' for key,value in sorted(original.items()))
    (out/'original_artifacts.sha256').write_text(index)
    e['original_artifact_count']=len(original);e['original_index_sha256']=sha(out/'original_artifacts.sha256')
    e['diagnostic_checks_passed']=all(x['passed'] for x in e['checks'])
    (out/'diagnosis.json').write_text(json.dumps(e,indent=2)+'\n')
    print(json.dumps(dict(check_count=len(e['checks']),checks=e['checks'],accepted=False),indent=2))
    return 0 if e['diagnostic_checks_passed'] else 1


if __name__=='__main__':raise SystemExit(main())
