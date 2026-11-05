#!/usr/bin/env python3
"""Paper metrics plus strict inherited semantics; never turn a failure into pass."""
import argparse
import contextlib
import hashlib
import json
from pathlib import Path
import numpy as np
from pyulog import ULog
from analyze_m09 import main as analyze_semantics
from audit_m09 import audit
from analyze_m03 import vector, sequence_stats
from analyze_m00 import plain
from m10_design import scenario


def recovery(t,error,start,threshold=.02,hold=1.,horizon=10.):
    """First <=threshold interval sustained for hold seconds; right-censor at horizon."""
    # Logged sensor clocks have integer-microsecond resolution. Avoid excluding
    # the exact stop sample because e.g. 70.4 differs by one binary64 ulp.
    t=np.rint(np.asarray(t)*1e6).astype(np.int64);start_us=round(start*1e6)
    hold_us=round(hold*1e6);horizon_us=round(horizon*1e6)
    m=(t>=start_us)&(t<=start_us+horizon_us)
    t=t[m];error=np.max(np.abs(error[m]),axis=1)
    began=None
    for ti,ei in zip(t,error):
        if not np.isfinite(ei) or ei>threshold:began=None
        elif began is None:began=ti
        if began is not None and ti-began>=hold_us:
            return dict(recovered=True,time_s=float(began-start_us)*1e-6,censored=False)
    return dict(recovered=False,time_s=None,censored=True,observed_until_s=float(t[-1]-start_us)*1e-6 if len(t) else 0.)


def analyze(run):
    job=json.loads((run/'m10_job.json').read_text())
    out={k:job[k] for k in ('mode','scene','seed')}
    out.update({k:job[k] for k in ('group','candidate','formal','frozen_head') if k in job})
    out.update(success=False,flight_success=False,analysis_success=False)
    result=json.loads((run/'result.json').read_text())
    out['source_head']=result['source_head'];out['binary_sha256']=result['binary_sha256']
    out['logs']=result.get('logs',[]);out['flight_success']=result['success']
    try:
        if not result['success']:raise RuntimeError('flight_failure: '+str(result.get('error',result.get('cleanup_error'))))
        with (run/'analysis_details.log').open('w') as stream, contextlib.redirect_stdout(stream):
            base=analyze_semantics(run,fixed_window=True)
            safety=audit(run)
        log=ULog(base['ulog']);d=log.get_dataset('sta_rate_ctrl_status').data
        out['ulog_firmware_commit']=log.msg_info_dict.get('ver_sw')
        if log.msg_info_dict.get('ver_hw')!='PX4_SITL':raise RuntimeError('Not a SITL firmware log')
        if job.get('formal') and log.msg_info_dict.get('ver_sw')!=job['frozen_head']:
            raise RuntimeError('Embedded firmware commit differs from frozen source')
        t=d['timestamp_sample'].astype(np.int64);e=vector(d,'s').astype(float);c=vector(d,'c_applied').astype(float)
        if np.any(d['config_pending']):raise RuntimeError('Unexpected pending gain configuration')
        armed_times=t[d['armed'].astype(bool)]
        allowed={'MC_RATT_TEST','COM_FLIGHT_UUID','LND_FLIGHT_T_HI','LND_FLIGHT_T_LO'}
        for stamp,name,value in log.changed_parameters:
            if armed_times[0]<=stamp<=armed_times[-1]:
                if name not in allowed or (name=='MC_RATT_TEST' and value!=4):
                    raise RuntimeError('Unexpected armed parameter write: '+name)
        tracking=(t>=base['tracking_start_us'])&(t<base['tracking_start_us']+36000000)
        idx=np.flatnonzero(tracking)
        if len(idx)<8900:raise RuntimeError('Missing tracking window')
        config=json.loads((run/'m04_config.json').read_text())
        for name,value in config.items():
            if name not in log.initial_parameters or not np.isclose(log.initial_parameters[name],value,atol=2e-6,rtol=2e-6):
                raise RuntimeError('Logged parameter mismatch: '+name)
        for name,value in job.get('fixed_parameters',{}).items():
            if name not in log.initial_parameters or log.initial_parameters[name]!=value:
                raise RuntimeError('Frozen non-experimental parameter mismatch: '+name)
        gyro=np.genfromtxt(run/'imu_innovations.csv',delimiter=',',names=True)
        torque=np.genfromtxt(run/'torque.csv',delimiter=',',names=True)
        if len(gyro)<1000 or not np.all(np.diff(gyro['seq'])==1):raise RuntimeError('IMU innovation capture gap')
        if not np.allclose(gyro['dt'][1:],.004,rtol=0,atol=1e-9):raise RuntimeError('Changed physics/IMU step')
        if not np.any(torque['elapsed_s']>=36):raise RuntimeError('Torque plugin or trigger missing')
        active=np.flatnonzero(torque['elapsed_s']>=0)
        world_start=torque['sim_s'][active[0]]-torque['elapsed_s'][active[0]]
        trigger_latency=float(torque['elapsed_s'][active[0]])
        if trigger_latency>=2:raise RuntimeError('Disturbance trigger missed zero-prefix delivery deadline')
        excitation_start=float(t[idx[0]])*1e-6
        # Both clocks originate in the Gazebo HIL_SENSOR sample epoch.
        sync=world_start-excitation_start
        if abs(sync)>.5:raise RuntimeError('Torque/controller clock mismatch exceeds .5 s: '+str(sync))
        body_torque=np.column_stack([torque[k] for k in ('tx_Nm','ty_Nm','tz_Nm')])
        expected_torque=job['scene']=='torque'
        if bool(np.any(body_torque!=0))!=expected_torque:raise RuntimeError('Physical torque scenario absent/unexpected')
        setting=scenario(job['scene'],job['seed'])
        elapsed=torque['elapsed_s'];nonzero=(elapsed>=2)&(elapsed<=12)
        reference_torque=np.zeros_like(body_torque)
        if expected_torque:
            x=elapsed[nonzero,None]-2
            reference_torque[nonzero]=np.array([.004,.004,.002])*np.sin(np.pi*x/10)**2*np.sin(2*np.pi*.4*x+setting['torque_phases'])
        waveform_error=float(np.max(np.abs(body_torque-reference_torque)))
        if waveform_error>2e-12:raise RuntimeError('Applied torque differs from seeded phase/envelope')
        if np.max(np.abs(body_torque))>.004000001:raise RuntimeError('Torque bound')
        derivative=np.diff(body_torque,axis=0)/np.diff(torque['sim_s'])[:,None]
        if np.max(np.abs(derivative))>.0115:raise RuntimeError('Torque derivative bound')
        m=json.loads((run/'metrics.json').read_text());hover=(t>=m['hover_start_us'])&(t<m['hover_start_us']+10e6)
        dt=1/base['callback_hz']
        out.update(base);out.update(safety)
        out['rmse_tracking']=np.sqrt(np.mean(e[tracking]**2,axis=0)).tolist()
        out['iae_tracking_rad']=np.sum(np.abs(e[tracking]),axis=0).tolist();out['iae_tracking_rad']=(np.array(out['iae_tracking_rad'])*dt).tolist()
        out['rmse_steady']=np.sqrt(np.mean(e[hover]**2,axis=0)).tolist()
        out['control_rms']=np.sqrt(np.mean(c[tracking]**2,axis=0)).tolist()
        out['control_peak']=np.max(np.abs(c[tracking]),axis=0).tolist()
        out['protected_fraction']=np.mean(vector(d,'limits')[tracking]!=0,axis=0).tolist()
        out['mixer_saturation_fraction']=np.mean((d['sat_bits'][tracking].astype(int)&~1)!=0).item()
        out['recovery']=recovery(t*1e-6,e,world_start+12) if expected_torque else dict(applicable=False)
        out['torque_clock_offset_s']=sync
        out['trigger_delivery_latency_s']=trigger_latency
        out['torque_derivative_max_Nm_s']=float(np.max(np.abs(derivative)))
        out['torque_waveform_max_abs_error_Nm']=waveform_error
        out['imu_samples']=len(gyro)
        out['imu_initial_realization']=[[float(gyro[k][j]) for k in ('gx','gy','gz','ax','ay','az')] for j in range(16)]
        out['imu_noise_std']=np.std(np.column_stack([gyro[k] for k in ('gx','gy','gz')]),axis=0).tolist()
        expected_sigma=.00018665*(2 if job['scene']=='noise' else 1)/np.sqrt(.004)
        out['gyro_white_noise_sigma_expected']=expected_sigma
        sigma_ratio=np.asarray(out['imu_noise_std'])/expected_sigma
        if np.any((sigma_ratio<.8)|(sigma_ratio>1.2)):
            raise RuntimeError('Recorded gyro noise disagrees with configured density/physics dt')
        out['sequence']=sequence_stats(d['publish_seq'][tracking],t[tracking])
        out['analysis_success']=True;out['success']=True
    except Exception as exc:
        out['success']=False;out['error']=repr(exc)
        out['failure_class']='flight' if not result['success'] else 'analysis_or_data_quality'
        if any(word in str(exc) for word in ('Tilt boundary','tilt boundary','Height boundary','height tracking',
                'Rate boundary','R/P command boundary','Yaw boundary','Nu boundary')):
            out['failure_class']='control_boundary'
        if any(word in str(result.get('error','')) for word in ('Stale/absent','Startup','CLI failed','Seeded IMU','model override',
                'Frozen background','Divisor not accepted','Controller/config not accepted','Require default inactive',
                'Global estimator readiness','Research trigger delivery','Invalid research trigger origin')) or result.get('cleanup_error'):
            out['failure_class']='infrastructure'
        # Decode basic failure counters when possible, without asserting validity.
        summaries=[]
        for item in result.get('logs',[]):
            try:
                log=ULog(item['archive']);d=log.get_dataset('sta_rate_ctrl_status').data
                command=vector(d,'c_applied')
                peak_indices=np.nanargmax(np.abs(command),axis=0)
                peak_times=d['timestamp_sample'][peak_indices]
                events=result.get('events',[])
                peak_events=[next((v['name'] for v in reversed(events) if v['timestamp_us']<=stamp),'startup')
                             for stamp in peak_times]
                summaries.append(dict(ulog=item['archive'],fault_samples=int(np.count_nonzero(d['fault'])),
                                      abort_samples=int(np.count_nonzero(d['abort_requested'])),
                                      effective_modes=np.unique(d['effective_mode']).tolist(),dropouts=len(log.dropouts),
                                      max_rate_abs=np.nanmax(np.abs(vector(d,'rate')),axis=0).tolist(),
                                      max_command_abs=np.nanmax(np.abs(command),axis=0).tolist(),
                                      command_peak_sample_us=peak_times.tolist(),command_peak_last_event=peak_events))
            except Exception as e2:summaries.append(dict(ulog=item['archive'],decode_error=repr(e2)))
        out['failure_diagnostics']=summaries
    (run/'m10_analysis.json').write_text(json.dumps(out,indent=2,default=plain)+'\n')
    print(json.dumps(out,indent=2,default=plain))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args()
    raise SystemExit(0 if analyze(a.run.resolve())['success'] else 1)
