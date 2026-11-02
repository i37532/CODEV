#!/usr/bin/env python3
"""Offline complete-log replay with separate results, never a flight acceptance edit."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types
from unittest.mock import patch

import numpy as np
from pyulog import ULog

import analyze as a
import heading_check as h
import plot_results
from prepare import sha256
from runner_contract import check_order

HERE=Path(__file__).resolve().parent
EXPERIMENTS=Path('/home/yr/Desktop/codev doc/experiments')
BATCHES=[EXPERIMENTS/name for name in (
    'UPSTREAM-STA2-ROS-OFFBOARD-20261102',
    'UPSTREAM-STA2-ROS-OFFBOARD-20261102-B02',
    'UPSTREAM-STA2-ROS-OFFBOARD-20261102-B03')]


def capture(function):
    try:return dict(passed=True,value=function())
    except ValueError as exc:return dict(passed=False,error=repr(exc))


def load_frozen():
    frozen_dir=HERE/'results/batch03/frozen_tools'
    manifest=json.loads((BATCHES[-1]/'manifest.json').read_text())
    modules=[]
    for name in ('heading_check','analyze'):
        source=frozen_dir/(name+'.py')
        assert sha256(source)==manifest['assets'][str(HERE/(name+'.py'))]
        module=types.ModuleType('event_fix_frozen_'+name)
        module.__file__=str(HERE/(name+'.py'))
        with patch.dict(sys.modules,{'heading_check':modules[0]} if modules else {}):
            exec(compile(source.read_text(),str(source),'exec'),module.__dict__)
        modules.append(module)
    return modules[-1]


def source_contract():
    original=Path('/home/yr/Desktop/Codev-SuperTwisting2-original')
    paths=['src/modules/ekf2/EKF2.cpp','msg/EstimatorEventFlags.msg']
    result={}
    for relative in paths:
        raw=subprocess.check_output(['git','show',h.STA2_HEAD+':'+relative],cwd=original)
        expected=hashlib.sha256(raw).hexdigest()
        assert sha256(original/relative)==expected
        result[str(original/relative)]=expected
    return dict(pinned_upstream_commit=h.STA2_HEAD,upstream_sources=result,
        old_codev_source_sha256=sha256(HERE.parents[2]/'src/modules/ekf2/EKF2.cpp'))


def tail_diagnosis(attempt,result,job,origin,ulog):
    """Check remaining components separately; never bypass final-state freshness."""
    windows,special=a.phase_windows(result['events'],job['task'])
    final=next(e for e in result['events'] if e['name']=='landed_disarmed')
    end=special['landed_disarmed']
    status=h.topic(ulog,'vehicle_status');land=h.topic(ulog,'vehicle_land_detected')
    st,lt=final['status_timestamp_us'],final['land_timestamp_us']
    def native_final():
        a.hold_check(status,'arming_state',st,st+1,1,'vehicle_status')
        a.hold_check(land,'landed',lt,lt+1,1,'vehicle_land_detected')
        return dict(landed=True,disarmed=True)
    def freshness():
        a.require(abs(st-end)<=a.MAX_GAP_US and abs(lt-end)<=a.MAX_GAP_US,'Stale final state receipts')
        return True
    sent_check=capture(lambda:a.audit_sent(attempt/'ros/sent.jsonl',windows,origin,result['events'])[1])
    wire=a._json_lines(attempt/'ros/sent.jsonl')
    trajectory_check=capture(lambda:a.audit_trajectory(h.topic(ulog,'trajectory_setpoint'),wire,windows))
    clock_check=capture(lambda:{name:a.clock_statistics(h.topic(ulog,name))
                               for name in (*a.BASE_TOPICS,*a.diagnostic_contract(job))})
    # Observe whether a later native land publication existed. It does not
    # replace the runner's recorded final event or create a new accepted run.
    later=np.flatnonzero(land['timestamp']>end)
    row=int(later[0]) if len(later) else None
    return dict(diagnostic_only=True,recorded_final_position_us=end,status_us=st,land_us=lt,
        absolute_status_age_us=abs(st-end),absolute_land_age_us=abs(lt-end),limit_us=a.MAX_GAP_US,
        freshness=capture(freshness),native_final_values=capture(native_final),
        ros_publisher_wire=sent_check,native_trajectory=trajectory_check,clock_statistics=clock_check,
        next_land_publication=None if row is None else dict(timestamp_us=int(land['timestamp'][row]),
            landed=int(land['landed'][row]),ground_contact=int(land['ground_contact'][row])),
        no_event_or_log_rewritten=True)


def replay():
    frozen=load_frozen();sources=source_contract()
    # Every file in the original Offboard batches is protected, not just results.
    protected={str(p):sha256(p) for root in BATCHES for p in root.rglob('*') if p.is_file()}
    offboard=[];negative=[]
    for batch in BATCHES:
        for attempt in sorted((batch/'runs').iterdir()):
            if not attempt.is_dir():continue
            result=json.loads((attempt/'result.json').read_text())
            job=json.loads((attempt/'job.json').read_text())
            origin=json.loads((attempt/'origin.json').read_text())
            native=max(result['logs'],key=lambda x:x['bytes'])
            assert sha256(native['archive'])==native['sha256']
            args=(native['archive'],result['events'],origin,job,attempt/'ros/sent.jsonl')
            old=capture(lambda:frozen.audit_native_log(*args))
            unchanged=capture(lambda:a.audit_native_log(*args))
            assert old==unchanged
            revised=dict(job,event_semantics_policy=h.REPUBLICATION_EVENTS,
                         heading_reset_policy=h.POLICY)
            revised_args=(native['archive'],result['events'],origin,revised,attempt/'ros/sent.jsonl')
            new=capture(lambda:a.audit_native_log(*revised_args))
            again=capture(lambda:a.audit_native_log(*revised_args))
            assert new==again
            row=dict(batch=batch.name,id=result['id'],system=job['system'],task=job['task'],
                original_success=result['success'],original_task_completed=result.get('task_completed',False),
                original_result_sha256=sha256(attempt/'result.json'),ulog_sha256=native['sha256'],
                frozen_and_default_exactly_equal=True,deterministic_revised_replay=True,
                revised_offline_passed=new['passed'],flight_accepted=False,new_flights=0)
            if old['passed']:
                assert result['success'] is True
                assert old['value']==json.loads((attempt/'metrics.json').read_text())
                assert old['value']==json.loads((attempt/'independent_replay.json').read_text())
                assert new==old
                row['complete_metrics_exact']=True
            else:
                row['old_error']=old['error']
            if new['passed']:
                row['heading_evidence']=new['value']['heading_evidence']
                row['phase_metrics']=new['value']['phase_metrics']
                row['parameters']=new['value']['parameters']
                row['send_evidence']=new['value']['send_evidence']
                row['trajectory_evidence']=new['value']['trajectory_evidence']
            else:row['revised_error']=new['error']
            if batch==BATCHES[-1] and job['system']=='STA2':
                assert new['error']=="ValueError('Stale final state receipts')"
                ulog=ULog(native['archive'])
                fixture_path=HERE/'results/event_fix01/sta2_event_fixture.json'
                fixture=json.loads(fixture_path.read_text())
                assert fixture['source_sha256']==sha256(native['archive'])
                assert fixture['recorded_result_sha256']==sha256(attempt/'result.json')
                recorded_events=h.topic(ulog,'estimator_event_flags')
                assert fixture['event_data']=={key:values.tolist() for key,values in recorded_events.items()}
                row['actual_event_fixture_verified_sha256']=sha256(fixture_path)
                windows,special=a.phase_windows(result['events'],job['task'])
                climb=next(w for w in windows if w['phase']=='climb')
                scored=min(w['start'] for w in windows if w['phase'] in a.SCORED_PHASES)
                row['revised_heading_evidence']=h.audit(ulog,climb['start'],special['landed_disarmed'],
                    climb['end'],scored,origin,schema=h.STA2_SCHEMA,event_policy=h.REPUBLICATION_EVENTS)
                row['remaining_chain']=tail_diagnosis(attempt,result,job,origin,ulog)
                assert not row['remaining_chain']['freshness']['passed']
                for key in ('native_final_values','ros_publisher_wire','native_trajectory','clock_statistics'):
                    assert row['remaining_chain'][key]['passed'],(key,row['remaining_chain'][key])
                # Real ULog clones in memory only: tests must fail at event
                # validation, not merely hit the known final-state failure.
                for label,mutator,expected in (
                    ('payload_without_counter',lambda d,i:d['gps_checks_passed'].__setitem__(i,1-int(d['gps_checks_passed'][i])),'cached event'),
                    ('sample_without_counter',lambda d,i:d['timestamp_sample'].__setitem__(slice(i,None),int(d['timestamp_sample'][i])+1),'changed sample'),
                    ('counter_gap',lambda d,i:d['information_event_changes'].__setitem__(slice(i,None),int(d['information_event_changes'][i])+2),'counter jump'),
                    ('new_forbidden_event',None,'unexpected reset_vel_to_gps')):
                    changed=copy.deepcopy(ulog);ev=h.topic(changed,'estimator_event_flags')
                    i=int(np.searchsorted(ev['timestamp'],60000000))
                    if mutator:mutator(ev,i)
                    else:
                        ev['information_event_changes'][i:]+=1;ev['timestamp_sample'][i:]=int(ev['timestamp'][i])-152000
                    bad=capture(lambda:a.audit_native_log(*revised_args,ulog_class=lambda *args,**kw:changed))
                    assert not bad['passed'] and expected in bad['error'],bad
                    negative.append(dict(case=label,error=bad['error'],memory_only=True,rejected_at_expected_guard=True))
            offboard.append(row)
    assert len(offboard)==5
    assert [r['revised_offline_passed'] for r in offboard]==[True,True,False,True,False]

    legacy_path=HERE.parent/'results/four_systems/manifest04_pid.json'
    manifest=json.loads(legacy_path.read_text())
    recorded=json.loads((legacy_path.parent/'metrics.json').read_text())
    rows={r['job']['id']:r for r in recorded['runs']};legacy=[]
    for job in manifest['jobs']:
        row,_=a._legacy.analyze_job(manifest,job,legacy_path)
        for key in ('metrics','runner_success','analysis_valid','result_sha256','ulog'):
            assert row[key]==rows[job['id']][key]
        legacy.append(dict(id=job['id'],system=job['label'],ulog=row['ulog'],
            result_sha256=row['result_sha256'],unchanged_own_navigator_contract=True,metrics_exact=True))
    stopped=capture(lambda:check_order(json.loads((BATCHES[-1]/'manifest.json').read_text()),'O003'))
    assert not stopped['passed'] and 'Previous attempt failed' in stopped['error']
    plot_admission=capture(lambda:plot_results.audit_inputs(BATCHES[-1]/'manifest.json'))
    assert not plot_admission['passed'] and 'O002' in plot_admission['error']
    assert protected=={path:sha256(path) for path in protected}
    return dict(status='event_fix_passed_complete_chain_blocked_by_final_receipt_freshness',
        diagnostic_only=True,flight_qualification=False,new_flights=0,new_manifest_created=False,
        original_outcomes_and_evidence_unchanged=True,protected_sha256=protected,
        ulog_count=9,complete_task_logs=8,partial_task_logs=1,offboard_replays=offboard,
        legacy_navigator_replays=legacy,in_memory_real_log_negatives=negative,
        next_job_remains_blocked=stopped['error'],comparison_plot_still_rejected=plot_admission['error'],
        source_contract=sources,
        source_sha256={str(p):sha256(p) for p in (HERE/'heading_check.py',HERE/'analyze.py',
            HERE/'runner_contract.py',HERE/'test_event_semantics.py',Path(__file__))})


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() or any(args.output.resolve().is_relative_to(p) for p in BATCHES):
        raise ValueError('Require a new output outside original batches')
    result=replay()
    with args.output.open('x') as stream:json.dump(result,stream,indent=2,ensure_ascii=False,allow_nan=False);stream.write('\n')
    print(json.dumps({k:result[k] for k in ('status','ulog_count','complete_task_logs','partial_task_logs',
        'new_flights','original_outcomes_and_evidence_unchanged')},ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
