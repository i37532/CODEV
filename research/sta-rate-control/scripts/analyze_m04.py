#!/usr/bin/env python3
"""Decode real M04 ULog; no success claim without explicit data checks."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from pyulog import ULog
from analyze_m00 import analyze, plain
from analyze_m03 import vector, pid_output, require, sequence_stats


def check_gyro_events(gyro, published_samples):
    """A switched FIFO may replay older samples; prove suppression, not acceptance."""
    reason=gyro['reason']
    duplicate=reason==1
    backward=reason==2
    require(np.all(gyro['timestamp_sample'][duplicate]==gyro['previous_sample'][duplicate]) and
            np.all(gyro['published'][duplicate]==0),'Duplicate suppression diagnostic inconsistent')
    require(np.all(gyro['timestamp_sample'][backward]<gyro['previous_sample'][backward]) and
            np.all(gyro['published'][backward]==0),'Backward suppression diagnostic inconsistent')
    require(np.all(np.isin(gyro['timestamp_sample'][backward],published_samples)),
            'Backward sample is not previously observed FIFO history: inspect')
    require(np.all(reason!=3),'Zero upstream sample: inspect')
    require(np.all(np.diff(gyro['event_seq'].astype(np.int64))==1),'Gyro diagnostic events missing')


def main(run):
    result=json.loads((run/'result.json').read_text())
    settings=json.loads((run/'m03_logging.json').read_text())
    require(settings['research_profile']==settings['original_profile']|16,'Profile bits not preserved')
    config=json.loads((run/'m04_config.json').read_text())
    protocol=json.loads((run/'m04_protocol.json').read_text())
    limits=protocol['limits']
    mode=int(config['MC_RTC_MODE'])
    mask_axes=int(config['MC_STA_AXES'])
    experiment_axes=[i for i in range(3) if mask_axes & (1<<i)]
    rp=protocol.get('milestone')=='M05'
    require(result['success'],'Scenario failure')
    candidates=[]
    for index,item in enumerate(result['logs']):
        path=Path(item['archive'])
        require(hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256'],'ULog hash')
        log=ULog(str(path))
        if log.initial_parameters.get('SDLOG_PROFILE')==settings['research_profile']:
            candidates.append((index,log))
    require(len(candidates)==1,'Require one research log')
    index,log=candidates[0]
    analyze(run,log_index=index)
    metrics=json.loads((run/'metrics.json').read_text())
    d=log.get_dataset('sta_rate_ctrl_status').data
    start,end=metrics['hover_start_us'],metrics['hover_end_us']
    hover=(d['timestamp_sample']>=start)&(d['timestamp_sample']<=end)
    tracking=hover&(d['research_elapsed']>=0)&(d['research_elapsed']<=protocol.get('tracking_seconds',24))
    require(np.count_nonzero(hover)>1000 and np.count_nonzero(tracking)>1000,'Insufficient samples')
    armed=d['armed'].astype(bool)
    for key,value in [('requested_mode',mode),('requested_axes',mask_axes),('effective_mode',mode),('effective_axes',mask_axes),
                      ('request_status',0),('pending',0),('fault',0),('abort_requested',0)]:
        require(np.all(d[key]==value),'Unexpected '+key)
    for key in ['measurement_valid','output_valid','updated']:
        require(np.all(d[key][armed]),'Invalid '+key)
    require(np.all(d['timing_status'][armed]==0),'Invalid dt')
    require(np.all(np.diff(d['timestamp_sample'].astype(np.int64))>0),'Nonmonotonic published gyro sample')
    gyro=log.get_dataset('gyro_sample_status').data
    check_gyro_events(gyro,d['timestamp_sample'])
    require(np.all(d['config_seq'][armed]==d['config_seq'][armed][0]),'Armed config drift')
    require(np.all(np.isfinite(vector(d,'c_applied')[armed])),'Nonfinite command')
    require(np.all(np.abs(vector(d,'rate')[armed])<=limits['rate_rad_s']),'Rate bound')
    require(np.all(np.abs(vector(d,'c_applied')[armed,0])<=limits['roll_command_abs']+1e-6),'Roll command bound')
    require(np.all(np.abs(vector(d,'nu')[armed,0])<=limits['nu_abs_rad_s2']+1e-6),'Nu bound')
    if rp:
        require(np.all(np.abs(vector(d,'c_applied')[armed,1])<=limits['pitch_command_abs']+1e-6),'Pitch command bound')
        require(np.all(np.abs(vector(d,'nu')[armed,1])<=limits['nu_abs_rad_s2']+1e-6),'Pitch nu bound')
    require(metrics['tilt_deg']['max_abs']<=limits['tilt_deg'],'Tilt bound')
    attitude=log.get_dataset('vehicle_attitude').data
    preceding=np.clip(np.searchsorted(d['timestamp_sample'],attitude['timestamp'],side='right')-1,0,len(armed)-1)
    am=armed[preceding]
    tilt=np.degrees(np.arccos(np.clip(1-2*(attitude['q[1]']**2+attitude['q[2]']**2),-1,1)))
    require(np.count_nonzero(am)>100 and np.all(np.isfinite(tilt[am])) and np.max(tilt[am])<=limits['tilt_deg'],'Armed tilt bound')
    require(metrics['position_error_m']['max_abs'][2]<=limits['height_error_m'],'Height bound')
    # PID pure path and both non-experimental axes keep float operation order.
    expected,raw=pid_output(d),vector(d,'c_raw')
    axes=[i for i in range(3) if i not in experiment_axes]
    updated=d['updated'].astype(bool)
    a=expected[updated][:,axes].copy(); b=raw[updated][:,axes].copy()
    pid_mismatch=int(np.count_nonzero(a.view(np.uint32)!=b.view(np.uint32)))
    require(pid_mismatch==0,'PID bit mismatch')
    for axis in experiment_axes:
        s=vector(d,'s')[:,axis]; old=vector(d,'nu_before')[:,axis]
        l1,l2,g=(vector(d,n)[:,axis] for n in ('lambda1','lambda2','g'))
        for field,param in [('lambda1','L1'),('lambda2','L2'),('g','G')]:
            require(np.all(vector(d,field)[armed,axis]==np.float32(config['MC_STA_'+param+'_'+'RPY'[axis]])), 'Logged gain mismatch')
        sigma=np.sign(s).astype(np.float32)
        alpha=-(l1*np.sqrt(np.abs(s)))*sigma+old
        np.testing.assert_allclose(vector(d,'a_raw')[armed,axis],alpha[armed],rtol=1e-6,atol=1e-7)
        np.testing.assert_allclose(raw[armed,axis],(alpha/g)[armed],rtol=1e-6,atol=1e-7)
        nu_next=old-(d['raw_dt']*l2)*sigma
        freeze=(d[f'limits[{axis}]']&3)!=0
        # Output-limit winding direction is a freeze, just as invalid feedback.
        delta=nu_next-old
        freeze |= ((raw[:,axis]>.15)&(delta>0))|((raw[:,axis]<-.15)&(delta<0))
        freeze |= ~d['experiment_updated'].astype(bool)
        nu_next=np.where(freeze,old,np.clip(nu_next,-3,3))
        np.testing.assert_allclose(vector(d,'nu')[armed,axis],nu_next[armed],rtol=1e-6,atol=1e-7)
        # Full-rate state continuity detects shared/swapped states, not just a local formula.
        contiguous=(np.diff(d['update_seq'].astype(np.int64))==1)&armed[1:]&armed[:-1]&(d['reset_reason'][1:]==0)
        np.testing.assert_array_equal(old[1:][contiguous],vector(d,'nu')[:-1,axis][contiguous])
    if mode==1:
        require(np.all(d['experiment_updated'][hover]),'Frozen experiment in hover')
        require(np.all(vector(d,'nu')[:,axes]==0),'Non-selected experimental state changed')
    else:
        require(np.all(d['experiment_updated']==0),'PID experiment updated')
    command=raw.copy()
    for axis in experiment_axes:
        command[:,axis]=np.clip(command[:,axis],-.15,.15)
    np.testing.assert_allclose(vector(d,'c_applied')[updated],(command*d['battery_scale'][:,None])[updated],rtol=1e-6,atol=1e-7)
    act=log.get_dataset('actuator_controls_0').data
    common,di,ai=np.intersect1d(d['timestamp_sample'][updated],act['timestamp_sample'],return_indices=True)
    require(len(common)>1000,'No actuator overlap')
    published=np.column_stack([act[f'control[{i}]'] for i in range(3)])
    require(np.array_equal(vector(d,'c_applied')[updated][di].view(np.uint32),published[ai].view(np.uint32)),'Actuator publication mismatch')
    error=vector(d,'s')
    stats={name:dict(rmse=np.sqrt(np.mean(error[mask].astype(float)**2,axis=0)),samples=int(np.count_nonzero(mask)))
           for name,mask in [('hover',hover),('tracking',tracking)]}
    for name,(lo,hi) in protocol.get('windows',{}).items():
        mask=hover&(d['research_elapsed']>=lo)&(d['research_elapsed']<hi)
        require(np.count_nonzero(mask)>2000,'Missing phase '+name)
        stats[name]=dict(rmse=np.sqrt(np.mean(error[mask].astype(float)**2,axis=0)),samples=int(np.count_nonzero(mask)),
                         rate_rms=np.sqrt(np.mean(vector(d,'rate')[mask].astype(float)**2,axis=0)),
                         command_rms=np.sqrt(np.mean(vector(d,'c_applied')[mask].astype(float)**2,axis=0)))
        for axis,field in enumerate(['research_roll_addition','research_pitch_addition']):
            values=d[field][mask]
            commanded=name=='synchronous' or name==['roll_only','pitch_only'][axis]
            if commanded:
                require(np.max(values)>.119 and np.min(values)<-.119,'Incomplete phase signs '+name)
                require(abs(float(np.trapz(values,d['research_elapsed'][mask])))<.002,'Phase nonzero integral')
            else:
                require(np.all(values==0),'Uncommanded axis received excitation')
    pulse=d['research_roll_addition']
    require(np.max(pulse[tracking])>.119 and np.min(pulse[tracking])<-.119,'Pulse sequence incomplete')
    elapsed=d['research_elapsed'][tracking].astype(float)
    integral=float(np.trapz(pulse[tracking],elapsed))
    require(abs(integral)<.002,'Pulse not zero integral')
    if rp:
        pitch_pulse=d['research_pitch_addition'][tracking]
        require(abs(float(np.trapz(pitch_pulse,elapsed)))<.002,'Pitch pulse not zero integral')
        t=d['research_elapsed'].astype(float)
        local=t % 12; cycle=np.floor(local/4)
        expected_pulse=.04*(cycle+1)*np.sin(np.pi*.5*(local-4*cycle))
        for axis,field in enumerate(['research_roll_addition','research_pitch_addition']):
            active=(t>=0)&(t<36)&((np.floor(t/12)==axis)|(t>=24))
            np.testing.assert_allclose(d[field],np.where(active,expected_pulse,0),atol=2e-6,rtol=1e-5)
    motor=log.get_dataset('multirotor_motor_limits').data
    mm=(motor['timestamp']>=start)&(motor['timestamp']<=end)
    seq=dict(status=sequence_stats(d['publish_seq'][hover],d['timestamp_sample'][hover]),
             updates=sequence_stats(d['update_seq'][hover],d['timestamp_sample'][hover]),
             raw_motor=sequence_stats(motor['update_seq'][mm],motor['timestamp'][mm]))
    consumed=d['motor_update_seq'][hover]; unique=np.r_[True,consumed[1:]!=consumed[:-1]]
    seq['consumed_motor']=sequence_stats(consumed[unique],d['motor_timestamp'][hover][unique])
    require(seq['updates']['missing']==0 and seq['status']['missing']==0,'Controller diagnostics missing; reacquire')
    baseline=json.loads((Path(__file__).resolve().parents[1]/'baseline/pid_initial_parameters.json').read_text())
    late=json.loads((Path(__file__).resolve().parents[1]/'m03/late_logged_baseline.json').read_text())['values']
    # Verified in M00 run03/params_all.txt; boot ULog only records used parameters.
    late.update(json.loads((Path(__file__).resolve().parents[1]/'m04/late_logged_baseline.json').read_text())['values'])
    allowed={'MC_RTC_MODE','MC_RATT_TEST','SDLOG_PROFILE','COM_FLIGHT_UUID','LND_FLIGHT_T_LO','LND_FLIGHT_T_HI'}
    for key,value in protocol.get('scenario_parameters',{}).items():
        require(log.initial_parameters.get(key)==float(np.float32(value)),'Scenario parameter mismatch: '+key)
        allowed.add(key)
    changes={k:[baseline.get(k),log.initial_parameters.get(k)] for k in baseline.keys()|log.initial_parameters.keys()
             if baseline.get(k)!=log.initial_parameters.get(k)}
    require(all(k in allowed or k.startswith('MC_STA_') or (k not in baseline and log.initial_parameters[k]==late.get(k))
                for k in changes),'Nonresearch parameter drift: '+str(changes))
    require(all(k in allowed or k.startswith('MC_STA_') for _,k,_ in log.changed_parameters),'Unexpected parameter changes')
    # No experimental tuning or scene drift while armed. The sole planned
    # change is the existing publisher's pulse trigger; counters are PX4-owned.
    first_armed=int(d['timestamp_sample'][armed][0]); last_armed=int(d['timestamp_sample'][armed][-1])
    require(all(k in {'MC_RATT_TEST','COM_FLIGHT_UUID','LND_FLIGHT_T_LO','LND_FLIGHT_T_HI'}
                for t,k,v in log.changed_parameters if first_armed<=t<=last_armed),'Armed parameter change')
    summary=dict(success=True,mode=mode,source_head=result['source_head'],binary_sha256=result['binary_sha256'],
                 ulog_sha256=result['logs'][index]['sha256'],hover_duration_s=metrics['hover_duration_s'],
                 metrics=stats,pid_bit_mismatches=pid_mismatch,pid_compared_samples=int(np.count_nonzero(updated)),
                 actuator_matched_samples=len(common),pulse_integral_rad=integral,sequences=seq,
                 motor_valid_ratio=float(np.mean(d['motor_valid'][hover])),
                 gyro_event_count=len(gyro['timestamp']),gyro_switch_count=int(gyro['switch_count'][-1]),
                 gyro_duplicate_count=int(gyro['duplicate_count'][-1]),
                 gyro_backward_count=int(gyro['backward_count'][-1]),
                 limits_fraction={str(i):float(np.mean(d['limits[0]'][hover]&i!=0)) for i in (1,2,4,8)},
                 max_abs_nu=float(np.max(np.abs(vector(d,'nu')[hover,0]))),
                 max_abs_roll_command=float(np.max(np.abs(vector(d,'c_applied')[hover,0]))),
                 max_tilt_deg=metrics['tilt_deg']['max_abs'],max_height_error_m=metrics['position_error_m']['max_abs'][2],
                 max_armed_tilt_deg=float(np.max(tilt[am])),max_armed_roll_command=float(np.max(np.abs(vector(d,'c_applied')[armed,0]))),
                 dropout_count=len(log.dropouts),full_raw_topic_tv_ready=all(s['missing']==0 for s in seq.values()) and not log.dropouts,
                 parameter_differences=changes,parameter_changes=log.changed_parameters)
    if rp:
        asp=log.get_dataset('vehicle_attitude_setpoint').data
        q=np.column_stack([attitude[f'q[{i}]'] for i in range(4)]).astype(float)
        yaw=np.arctan2(2*(q[:,0]*q[:,3]+q[:,1]*q[:,2]),1-2*(q[:,2]**2+q[:,3]**2))
        previous=np.clip(np.searchsorted(asp['timestamp'],attitude['timestamp'],side='right')-1,0,len(asp['timestamp'])-1)
        yaw_error=np.arctan2(np.sin(yaw-asp['yaw_body'][previous]),np.cos(yaw-asp['yaw_body'][previous]))
        ah=(attitude['timestamp']>=start)&(attitude['timestamp']<=end)
        require(np.count_nonzero(ah)>100 and np.all(np.isfinite(yaw_error[ah])),'Invalid yaw attitude data')
        summary.update(axes=mask_axes, milestone='M05',
                       yaw_attitude_error_rad=dict(rmse=float(np.sqrt(np.mean(yaw_error[ah]**2))),max_abs=float(np.max(np.abs(yaw_error[ah])))),
                       all_axes_max_nu=np.max(np.abs(vector(d,'nu')[armed]),axis=0),
                       all_axes_max_command=np.max(np.abs(vector(d,'c_applied')[armed]),axis=0),
                       all_axes_hover_max_command=np.max(np.abs(vector(d,'c_applied')[hover]),axis=0),
                       all_axes_armed_limits_fraction={str(axis):{str(bit):float(np.mean(d[f'limits[{axis}]'][armed]&bit!=0)) for bit in (1,2,4,8)} for axis in range(3)},
                       all_axes_armed_mixer_saturation_fraction={str(axis):{direction:float(np.mean((d['motor_saturation'][armed]&(1<<(3+2*axis+j)))!=0)) for j,direction in enumerate(['positive','negative'])} for axis in range(3)},
                       all_axes_limits_fraction={str(axis):{str(bit):float(np.mean(d[f'limits[{axis}]'][hover]&bit!=0)) for bit in (1,2,4,8)} for axis in range(3)},
                       all_axes_mixer_saturation_fraction={str(axis):{direction:float(np.mean((d['motor_saturation'][hover]&(1<<(3+2*axis+j)))!=0)) for j,direction in enumerate(['positive','negative'])} for axis in range(3)})
    (run/'m04_analysis.json').write_text(json.dumps(summary,indent=2,default=plain)+'\n')
    print(json.dumps(summary,indent=2,default=plain))


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('run',type=Path)
    main(parser.parse_args().run)
