#!/usr/bin/env python3
"""AX04 numerical core (AX02 metrics unchanged): eight exact configurations, recorded-state metrics."""
import argparse
import json
from pathlib import Path
import numpy as np
from position_log import ULog
import baseline as analyze_v00
from analyze_v03 import check_inner_evidence, exact_output_match, vector
from audit_v00_results import saturation_summary
from run_v00 import save

CONFIG = Path(__file__).resolve().parent


from cadence import aligned, check as check_cadence

def check_diagnostic(d,selection,start,end,job,require_excitation=True):
    m=(d['timestamp']>=start)&(d['timestamp']<end)
    x={k:v[m] for k,v in d.items()}; q=aligned(x,selection); mode=job['mode']; n=len(x['timestamp'])
    if n<600 or x['timestamp'][0]-start>40000 or end-x['timestamp'][-1]>40000:
        raise ValueError('Missing diagnostic window/boundary')
    for key in ('timestamp','timestamp_sample','input_timestamp'):
        delta=np.diff(x[key].astype(np.int64))
        if np.any(delta<=0) or delta.max()>40000: raise ValueError('Diagnostic time '+key)
    if np.any(np.diff(x['publish_seq'].astype(np.int64))!=1): raise ValueError('Missing publication')
    if np.any(np.diff(x['update_seq'].astype(np.int64))!=x['pid_calls'][1:]): raise ValueError('Call count mismatch')
    enabled=x['enabled'].astype(bool)
    if not np.any(enabled) or np.any(x['pid_calls']!=enabled.astype(int)): raise ValueError('Wrong module invocation count')
    for key,value in dict(requested_mode=mode,effective_mode=mode,requested_axes=job['axes'],effective_axes=job['axes'],
                         pending=0,reject=0,inner_mode=0,inner_axes=0,inner_divisor=1,inner_valid=1,
                         fault=0,failsafe=0,timing=0,sta_fault=0,config_pending=0).items():
        if np.any(x[key]!=value): raise ValueError('Unexpected '+key)
    if np.any(x['valid'][enabled]!=1): raise ValueError('Invalid output')
    inner=check_inner_evidence({k:v[enabled] for k,v in x.items()})
    dt=np.diff(x['timestamp_sample'].astype(np.int64))*1e-6
    if not np.allclose(x['raw_dt'][1:],dt,atol=1e-7,rtol=0): raise ValueError('Wrong raw sample dt')
    if not np.allclose(x['used_dt'],np.clip(x['input_dt'],.002,.04),atol=1e-7,rtol=0): raise ValueError('Legacy dt changed')
    if not np.allclose(vector(x,'s')[enabled],(vector(x,'v')-vector(x,'v_sp'))[enabled],atol=1e-7,rtol=0,equal_nan=True):
        raise ValueError('Not consumed error')
    for field in ('a_req','a_proxy','thrust'):
        if not np.all(np.isfinite(vector(x,field)[enabled])): raise ValueError('Nonfinite '+field)
    proxy=vector(x,'thrust')*(9.80665/x['hover_thrust'][:,None]); proxy[:,2]+=9.80665
    if not np.allclose(proxy[enabled],vector(x,'a_proxy')[enabled],atol=5e-6,rtol=0): raise ValueError('Wrong proxy')
    result=dict(n=n,inner=inner,maximum_gap_s=float(dt.max()),hz=1/float(dt.mean()))
    result['cadence']=check_cadence(x,q,job,require_excitation)
    if not require_excitation: return result
    if not np.all(enabled) or np.any(x['armed']!=1): raise ValueError('Observation not active')
    t=x['excitation_time'].astype(float)
    clock=(t>=0)&(t<64)
    gate=x['timestamp_sample'][clock].astype(float)-(t[clock]+12)*1e6
    if not len(gate) or np.ptp(gate)>10: raise ValueError('Wrong task clock')
    for key in ('excitation','excitation_y','excitation_z'):
        if np.any(x[key]!=0): raise ValueError('Unexpected velocity injection')
    if t[0]>0 or t[-1]<64: raise ValueError('Incomplete task')
    tm=x['timestamp_sample'].astype(np.int64); w=np.diff(np.r_[tm,tm[-1]+int(np.median(np.diff(tm)))])*1e-6
    x['_actual_update']=q['control_updated'].astype(bool)
    result['windows']={}
    for name,lo,hi in [('first_loop',0,32),('second_loop',32,64)]:
        em=(t>=lo)&(t<hi)
        if em.sum()<.8*(hi-lo)*100 or np.ptp(t[em])<hi-lo-.04: raise ValueError('Incomplete '+name)
        result['windows'][name]=window_metrics(x,em,w,job)
    result.update(window_metrics(x,(t>=0)&(t<64),w,job))
    result['xy_rmse']=float(np.sqrt(np.mean(np.square(result['error']['rmse'][:2]))))
    return result

def window_metrics(x,em,w,job):
    constrained=(x['constraint_bits'][em]!=0)|((x['sta_flags'][em] & (8|16|32))!=0)
    longest=current=0.
    for flag,h in zip(constrained,w[em]):
        current=current+h if flag else 0.; longest=max(longest,current)
    if np.mean(constrained)>.05 or longest>.5: raise ValueError('Constraint envelope')
    return dict(error=analyze_v00.stats(vector(x,'s')[em],w[em]),
        iae_m=(np.abs(vector(x,'s')[em])*w[em,None]).sum(axis=0).tolist(),
        acceleration_tv=np.abs(np.diff(vector(x,'a_req')[em & x['_actual_update']],axis=0)).sum(axis=0).tolist(),
        normalized_thrust_tv=np.abs(np.diff(vector(x,'thrust')[em & x['_actual_update']],axis=0)).sum(axis=0).tolist(),
        samples=int(em.sum()),seconds=float(w[em].sum()),constraint_fraction=float(np.mean(constrained)),
        maximum_continuous_constraint_s=longest,
        nu_peak=[float(np.max(np.abs(x[f'nu_applied[{a}]'][em]))) for a in range(3) if job['axes']&(1<<a)] if job['mode'] else None)


def analyze(run, protocol, job, *, attitude_policy=None):
    analyze_v00.CONFIG=CONFIG/('esta' if job['mode'] else 'pid')
    base=analyze_v00.analyze(run,protocol,attitude_policy=attitude_policy)
    base['limitations']=['Consumed diagnostic is checked separately; inherited 90s position/yaw metrics alone are not proof of consumed velocity state.',
        'IMU engine only is seeded; other sensor/host randomness is not fully paired.',
        '20 planned paired IMU blocks; acceptance-conditioned inference, downstream coverage reported.',
        'Request TV is not motor energy; different algorithms synthesize different final velocity targets through original position P.']
    save(run/'v00_metrics.json',base)
    match_output = exact_output_match
    if attitude_policy is not None:
        from v04_attitude_clock09 import exact_output_match as match_output
    r=json.loads((run/'result.json').read_text()); e={x['name']:x['timestamp_us'] for x in r['events']}
    u=ULog(base['ulog']['archive']); d=u.get_dataset('sta_velocity_ctrl_status').data
    selection=u.get_dataset('velocity_ctrl_selection').data
    out=dict(accepted=False,job=job,baseline_accepted=base['accepted'])
    try:
        out['flight']=check_diagnostic(d,selection,e['takeoff_command'],e['landed_disarmed'],job,False)
        out['diagnostic']=check_diagnostic(d,selection,e['hover_start'],e['hover_end'],job)
        from spectra import analyze as spectra
        sm=(d['timestamp']>=e['hover_start'])&(d['timestamp']<e['hover_end'])
        sd={k:v[sm] for k,v in d.items()}
        from cadence import check_pid_path
        out['pid_reconstruction']=check_pid_path(sd,aligned(sd,selection),job,u.initial_parameters)
        spectrum=spectra(sd,aligned(sd,selection)); save(run/'spectra.json',spectrum)
        out['spectral_summary']={k:v for k,v in spectrum.items() if not k.endswith(('psd','frequency_hz'))}
        for name in ('runtime_parameters_start.json','runtime_parameters_end.json'):
            if json.loads((run/name).read_text()).get('MPC_VC_DIV')!=job['divisor']: raise ValueError('Runtime divisor mismatch')
        from task import check_targets
        out['task_targets']=check_targets(u,d,e,job)
        selection=u.get_dataset('velocity_ctrl_selection').data
        sm=(selection['timestamp']>=e['takeoff_command'])&(selection['timestamp']<e['landed_disarmed'])
        if sm.sum()<600 or np.any(np.diff(selection['publish_seq'][sm].astype(np.int64))!=1):
            raise ValueError('Missing selector')
        for key,value in dict(requested_mode=job['mode'],effective_mode=job['mode'],requested_axes=job['axes'],
                              effective_axes=job['axes'],pending=0,reject=0).items():
            if np.any(selection[key][sm]!=value): raise ValueError('Selector '+key)
        if np.any(selection['pid_calls'][sm]!=selection['enabled'][sm].astype(int)):
            raise ValueError('Selector enabled/disabled invocation count')
        pairs=[(f'v_sp[{i}]',v) for i,v in enumerate(('vx','vy','vz'))]
        pairs +=[(f'a_req[{i}]',f'acceleration[{i}]') for i in range(3)]
        pairs +=[(f'thrust[{i}]',f'thrust[{i}]') for i in range(3)]
        out['local_output']=match_output(d,u.get_dataset('vehicle_local_position_setpoint').data,'output_timestamp',pairs,e['hover_start'],e['hover_end'])
        out['attitude_output']=match_output(d,u.get_dataset('vehicle_attitude_setpoint').data,'attitude_timestamp',
            [(f'q_sp[{i}]',f'q_d[{i}]') for i in range(4)],e['hover_start'],e['hover_end'])
        rate=u.get_dataset('sta_rate_ctrl_status').data; hm=(rate['timestamp']>=e['hover_start'])&(rate['timestamp']<e['hover_end'])
        out['mixer']=saturation_summary(rate['sat_bits'][hm],rate['sat_valid'][hm])
        out['position_rmse']=base['metrics']['position_error_m']['rmse']
        out['yaw_rmse']=base['metrics']['yaw_error_rad']['rmse']
        out['height']=base['metrics']['height_error_from_2p5_m']
        out['accepted']=bool(base['accepted'])
    except (KeyError,ValueError,IndexError) as exc: out['error']=str(exc)
    save(run/'xyz_core_metrics.json',out); return out


def compare(pid, esta):
    if not pid['accepted'] or not esta['accepted'] or pid['job']['seed']!=esta['job']['seed'] or pid['job']['task']!=esta['job']['task']:
        raise ValueError('Incomplete/wrong seed pair')
    if pid['job']['divisor']!=esta['job']['divisor']: raise ValueError('Wrong divisor pair')
    if pid['job']['mode']!=0 or esta['job']['mode']!=1: raise ValueError('Wrong paired modes')
    checks={}
    for i,allow in enumerate((.02,.02,.01)):
        checks['velocity_'+str(i)]=esta['diagnostic']['error']['rmse'][i]<=1.25*pid['diagnostic']['error']['rmse'][i]+allow
        checks['position_'+str(i)]=esta['position_rmse'][i]<=1.25*pid['position_rmse'][i]+.05
    for name in ('first_loop','second_loop'):
        for i,allow in enumerate((.02,.02,.01)):
            checks[name+'_velocity_'+str(i)]=(esta['diagnostic']['windows'][name]['error']['rmse'][i]
                <=1.25*pid['diagnostic']['windows'][name]['error']['rmse'][i]+allow)
    checks['yaw']=esta['yaw_rmse']<=1.25*pid['yaw_rmse']+.02
    return dict(accepted=all(checks.values()),checks=checks,seed=pid['job']['seed'],task=pid['job']['task'],divisor=pid['job']['divisor'])


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('run',type=Path); args=p.parse_args()
    job=json.loads((args.run/'job.json').read_text()); protocol=json.loads((CONFIG/'protocol.json').read_text())
    protocol['startup_overrides'].update(job['parameters'])
    result=analyze(args.run,protocol,job); print(json.dumps(result,indent=2)); raise SystemExit(0 if result['accepted'] else 1)
