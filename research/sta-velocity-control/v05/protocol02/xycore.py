#!/usr/bin/env python3
"""Protocol04 numerical core; original V04 metrics, explicit disabled lifecycle."""
import argparse
import json
from pathlib import Path
import numpy as np
from pyulog import ULog
import baseline as analyze_v00
from analyze_v03 import check_inner_evidence, exact_output_match, vector
from audit_v00_results import saturation_summary
from run_v00 import save

CONFIG = Path(__file__).resolve().parent


def check_diagnostic(d, start, end, mode, require_excitation=True):
    m=(d['timestamp']>=start)&(d['timestamp']<end)
    if not require_excitation:
        flight={k:v[m] for k,v in d.items()}
        if len(flight['timestamp'])<600: raise ValueError('Missing complete flight diagnostic')
        if flight['timestamp'][0]-start>40000 or end-flight['timestamp'][-1]>40000:
            raise ValueError('Missing flight boundary')
        for k in ('timestamp','timestamp_sample','input_timestamp'):
            dt=np.diff(flight[k].astype(np.int64))
            if np.any(dt<=0) or np.max(dt)>40000: raise ValueError('Whole flight time '+k)
        if np.any(np.diff(flight['publish_seq'].astype(np.int64))!=1): raise ValueError('Missing publication')
        if np.any(np.diff(flight['update_seq'].astype(np.int64))!=flight['pid_calls'][1:]): raise ValueError('Update/call count mismatch')
        enabled=flight['enabled'].astype(bool)
        if not np.any(enabled) or np.any(flight['pid_calls'][~enabled]!=0): raise ValueError('Disabled invocation')
        selected=dict(requested_mode=mode,effective_mode=mode,requested_axes=3*mode,effective_axes=3*mode,pending=0,reject=0)
        for key,val in selected.items():
            if np.any(flight[key]!=val): raise ValueError('Flight selection '+key)
        active=np.flatnonzero(enabled)
        if not np.all(enabled[active[0]:active[-1]+1]): raise ValueError('Unexpected control exit/reentry')
        m &= d['enabled'].astype(bool)
        start=float(d['timestamp'][m][0]); end=float(d['timestamp'][m][-1])+1
    x={k:v[m] for k,v in d.items()}; n=len(x['timestamp'])
    if n<600 or x['timestamp'][0]-start>40000 or end-x['timestamp'][-1]>40000:
        raise ValueError('Missing diagnostic window/boundary')
    inner=check_inner_evidence(x)
    for key in ('timestamp','timestamp_sample','input_timestamp'):
        delta=np.diff(x[key].astype(np.int64))
        if np.any(delta<=0) or delta.max()>40000: raise ValueError('Diagnostic time '+key)
    for key in ('publish_seq','update_seq'):
        if np.any(np.diff(x[key].astype(np.int64))!=1): raise ValueError('Missing update '+key)
    states=dict(requested_mode=mode,effective_mode=mode,requested_axes=3*mode,effective_axes=3*mode,
                pending=0,reject=0,inner_mode=0,inner_axes=0,inner_divisor=1,inner_valid=1,
                fault=0,failsafe=0,timing=0,pid_calls=1,updated=1,valid=1,sta_fault=0,config_pending=0,z_phase=0,z_hte_shift=0)
    if require_excitation:
        states.update(armed=1,enabled=1,active_axes=3*mode,committed_axes=3*mode,pid_axes=4 if mode else 7)
    for key,value in states.items():
        if np.any(x[key]!=value): raise ValueError('Unexpected '+key)
    dt=np.diff(x['timestamp_sample'].astype(np.int64))*1e-6
    if not np.allclose(x['raw_dt'][1:],dt,atol=1e-7,rtol=0): raise ValueError('Wrong sample dt')
    if not np.allclose(x['used_dt'],np.clip(x['input_dt'],.002,.04),atol=1e-7,rtol=0):
        raise ValueError('Changed PID dt')
    if require_excitation:
        if not np.allclose(vector(x,'s'),vector(x,'v')-vector(x,'v_sp'),atol=1e-7,rtol=0):
            raise ValueError('Not consumed error')
    for field in ('nu_before','nu_ideal','nu_applied','a_sta'):
        expected_nan=vector(x,field)[:,2:] if mode else vector(x,field)
        if not np.all(np.isnan(expected_nan)): raise ValueError('STA state on PID axes')
    if mode and require_excitation:
        for axis in (0,1):
            for field in ('nu_before','nu_ideal','nu_applied','a_sta'):
                if not np.all(np.isfinite(x[field+f'[{axis}]'])): raise ValueError('Invalid ESTA state')
            s=x[f's[{axis}]']; before=x[f'nu_before[{axis}]']; h=x['raw_dt']
            ideal=-np.sqrt(np.abs(s))*np.sign(s)+before
            if not np.allclose(x[f'a_sta[{axis}]'],ideal,atol=2e-6,rtol=0): raise ValueError('Wrong old-nu output')
            if not np.allclose(x[f'nu_ideal[{axis}]'],before-h*.2*np.sign(s),atol=2e-7,rtol=0): raise ValueError('Wrong candidate')
            if not np.allclose(before[1:],x[f'nu_applied[{axis}]'][:-1],atol=0,rtol=0): raise ValueError('Stale/duplicate nu')
            ff=np.where(np.isfinite(x[f'a_ff[{axis}]']),x[f'a_ff[{axis}]'],0)
            if not np.allclose(x[f'a_req[{axis}]'],np.clip(ideal,-.8,.8)+ff,atol=2e-6,rtol=0): raise ValueError('FF/mapping')
            if np.max(np.abs(x[f'nu_applied[{axis}]']))>.400001: raise ValueError('nu limit')
            if np.any(x['sta_flags'] & (1|2|4|64|128)): raise ValueError('Unexpected reset/freeze lifecycle')
            # Protected state is checked separately from the ideal proposal.
            applied=np.clip(x[f'nu_ideal[{axis}]'],-.4,.4)
            constrained=x['constraint_bits']!=0
            outward=((applied-before)*(ideal-np.clip(ideal,-.8,.8))>0)|(
                constrained & ((applied-before)*(x[f'a_req[{axis}]']-x[f'a_proxy[{axis}]'])>0))
            applied=np.where(outward,before,applied)
            if not np.allclose(x[f'nu_applied[{axis}]'],applied,atol=2e-7,rtol=0): raise ValueError('Protected nu mismatch')
    for field in ('a_req','a_proxy','thrust'):
        if not np.all(np.isfinite(vector(x,field))): raise ValueError('Nonfinite '+field)
    proxy=vector(x,'thrust')*(9.80665/x['hover_thrust'][:,None]); proxy[:,2]+=9.80665
    if not np.allclose(proxy,vector(x,'a_proxy'),rtol=0,atol=5e-6): raise ValueError('Proxy mapping')
    result=dict(n=n,inner=inner,maximum_gap_s=float(dt.max()),hz=1/float(dt.mean()))
    if not require_excitation: return result
    t=x['excitation_time'].astype(float)
    active_clock=(t>=0)&(t<64)
    gate=x['timestamp_sample'][active_clock].astype(float)-(t[active_clock]+12)*1e6
    if not len(gate) or np.ptp(gate)>10: raise ValueError('Combined excitation clock/deadline')
    expected_x,expected_y=waveform(t)
    for key,expected in [('excitation',expected_x),('excitation_y',expected_y)]:
        if key not in x or not np.allclose(expected,x[key],rtol=0,atol=1e-6):
            raise ValueError('Waveform '+key)
    if t[0]>0 or t[-1]<64: raise ValueError('Incomplete combined excitation')
    tm=x['timestamp_sample'].astype(np.int64)
    w=np.diff(np.r_[tm,tm[-1]+int(np.median(np.diff(tm)))])*1e-6
    result['windows']={}
    for name,lo,hi in [('X',0,32),('Y',32,48),('XY',48,64)]:
        em=(t>=lo)&(t<hi)
        if em.sum()<.8*(hi-lo)*100 or np.ptp(t[em])<hi-lo-.04:
            raise ValueError('Incomplete excitation '+name)
        result['windows'][name]=window_metrics(x,em,w,mode)
    result.update(window_metrics(x,(t>=0)&(t<64),w,mode))
    return result


def waveform(t):
    t=np.asarray(t,dtype=float)
    x=np.zeros_like(t); y=np.zeros_like(t)
    a=(t>0)&(t<32); b=(t>=32)&(t<48); c=(t>=48)&(t<64)
    x[a]=.2*np.sin(2*np.pi*t[a]/8)*np.sin(np.pi*t[a]/32)**2
    u=t[b]-32; y[b]=.2*np.sin(2*np.pi*u/8)*np.sin(np.pi*u/16)**2
    u=t[c]-48; x[c]=(.2/np.sqrt(2))*np.sin(2*np.pi*u/8)*np.sin(np.pi*u/16)**2
    y[c]=-x[c]
    return x,y


def window_metrics(x,em,w,mode):
    constrained=(x['constraint_bits'][em]!=0)|((x['sta_flags'][em] & (8|16|32))!=0)
    longest=current=0.
    for flag,h in zip(constrained,w[em]):
        current=current+h if flag else 0.; longest=max(longest,current)
    if np.mean(constrained)>.05 or longest>.5: raise ValueError('Constraint envelope')
    return dict(error=analyze_v00.stats(vector(x,'s')[em],w[em]),
        iae_m=(np.abs(vector(x,'s')[em])*w[em,None]).sum(axis=0).tolist(),
        acceleration_tv=np.abs(np.diff(vector(x,'a_req')[em],axis=0)).sum(axis=0).tolist(),
        samples=int(em.sum()),seconds=float(w[em].sum()),constraint_fraction=float(np.mean(constrained)),
        maximum_continuous_constraint_s=longest,
        nu_peak=[float(np.max(np.abs(x[f'nu_applied[{a}]'][em]))) for a in (0,1)] if mode else None)


def analyze(run, protocol, job, *, attitude_policy=None):
    analyze_v00.CONFIG=CONFIG/('esta' if job['mode'] else 'pid')
    base=analyze_v00.analyze(run,protocol,attitude_policy=attitude_policy)
    match_output = exact_output_match
    if attitude_policy is not None:
        from v04_attitude_clock09 import exact_output_match as match_output
    r=json.loads((run/'result.json').read_text()); e={x['name']:x['timestamp_us'] for x in r['events']}
    u=ULog(base['ulog']['archive']); d=u.get_dataset('sta_velocity_ctrl_status').data
    out=dict(accepted=False,job=job,baseline_accepted=base['accepted'])
    try:
        out['flight']=check_diagnostic(d,e['takeoff_command'],e['landed_disarmed'],job['mode'],False)
        out['diagnostic']=check_diagnostic(d,e['hover_start'],e['hover_end'],job['mode'])
        selection=u.get_dataset('velocity_ctrl_selection').data
        sm=(selection['timestamp']>=e['takeoff_command'])&(selection['timestamp']<e['landed_disarmed'])
        if sm.sum()<600 or np.any(np.diff(selection['publish_seq'][sm].astype(np.int64))!=1):
            raise ValueError('Missing selector')
        for key,value in dict(requested_mode=job['mode'],effective_mode=job['mode'],requested_axes=3*job['mode'],
                              effective_axes=3*job['mode'],pending=0,reject=0).items():
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
    save(run/'v05_core_metrics.json',out); return out


def compare(pid, esta):
    if not pid['accepted'] or not esta['accepted'] or pid['job']['seed']!=esta['job']['seed']:
        raise ValueError('Incomplete/wrong seed pair')
    if pid['job']['mode']!=0 or esta['job']['mode']!=1: raise ValueError('Wrong paired modes')
    checks={}
    for i,allow in enumerate((.02,.02,.01)):
        checks['velocity_'+str(i)]=esta['diagnostic']['error']['rmse'][i]<=1.25*pid['diagnostic']['error']['rmse'][i]+allow
        checks['position_'+str(i)]=esta['position_rmse'][i]<=1.25*pid['position_rmse'][i]+.05
    for name in ('X','Y','XY'):
        for i,allow in enumerate((.02,.02,.01)):
            checks[name+'_velocity_'+str(i)]=(esta['diagnostic']['windows'][name]['error']['rmse'][i]
                <=1.25*pid['diagnostic']['windows'][name]['error']['rmse'][i]+allow)
    checks['yaw']=esta['yaw_rmse']<=1.25*pid['yaw_rmse']+.02
    return dict(accepted=all(checks.values()),checks=checks,seed=pid['job']['seed'])


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('run',type=Path); args=p.parse_args()
    job=json.loads((args.run/'job.json').read_text()); protocol=json.loads((CONFIG/'protocol.json').read_text())
    protocol['startup_overrides'].update(job['parameters'])
    result=analyze(args.run,protocol,job); print(json.dumps(result,indent=2)); raise SystemExit(0 if result['accepted'] else 1)
