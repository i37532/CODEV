#!/usr/bin/env python3
"""V03 consumed-state diagnostics. Exact matches only; no missing-sample interpolation."""
import argparse
import json
from pathlib import Path
import numpy as np
from pyulog import ULog
import analyze_v01
from analyze_v00 import stats
from run_v00 import save

CONFIG = Path(__file__).resolve().parents[1]/'v03/protocol01'


def vector(d, field, width=3):
    return np.column_stack([d[f'{field}[{i}]'] for i in range(width)])


def check_inner_evidence(d):
    age = d['inner_check_timestamp'].astype(np.int64)-d['inner_timestamp'].astype(np.int64)
    if np.any(d['inner_timestamp']==0) or np.any(age<0) or np.any(age>=100000):
        raise ValueError('Consumed inner diagnostic really stale/future/missing')
    if np.any(d['inner_reads']<0) or np.any(d['inner_reads']>32):
        raise ValueError('Unbounded inner queue drain')
    if np.any(np.diff(d['inner_seq'].astype(np.int64))<0):
        raise ValueError('Reversed inner diagnostic sequence')
    return dict(max_age_us=int(age.max()),median_age_us=float(np.median(age)),
                maximum_reads=int(d['inner_reads'].max()))


def check_diagnostic(d, start, end, require_excitation=True):
    m = (d['timestamp'] >= start) & (d['timestamp'] < end)
    x = {k:v[m] for k,v in d.items()}
    n = len(x['timestamp'])
    if n < 600: raise ValueError('Missing diagnostic window')
    inner = check_inner_evidence(x)
    if x['timestamp'][0]-start > 40000 or end-x['timestamp'][-1] > 40000:
        raise ValueError('Missing diagnostic window boundary')
    for field in ('timestamp', 'timestamp_sample', 'input_timestamp'):
        delta = np.diff(x[field].astype(np.int64))
        if np.any(delta <= 0) or np.max(delta) > 40000:
            raise ValueError('Nonmonotonic or missing diagnostic time '+field)
    for field in ('publish_seq', 'update_seq'):
        if np.any(np.diff(x[field].astype(np.int64)) != 1):
            raise ValueError('Missing/duplicate update sequence '+field)
    for field, value in dict(requested_mode=0,requested_axes=0,effective_mode=0,effective_axes=0,
        pending=0,reject=0,active_axes=0,inner_mode=0,inner_axes=0,inner_divisor=1,inner_valid=1,
        pid_calls=1,updated=1,valid=1,enabled=1,armed=1,timing=0,failsafe=0,fault=0).items():
        if np.any(x[field] != value): raise ValueError('Wrong diagnostic state '+field)
    measured = np.diff(x['timestamp_sample'].astype(np.int64))*1e-6
    if not np.allclose(x['raw_dt'][1:], measured, rtol=0, atol=1e-7):
        raise ValueError('raw_dt is not sensor time')
    if not np.allclose(x['used_dt'], np.clip(x['input_dt'], .002, .04), rtol=0, atol=1e-7):
        raise ValueError('PID dt semantics changed')
    if not np.allclose(vector(x,'s'), vector(x,'v')-vector(x,'v_sp'), rtol=0, atol=1e-7):
        raise ValueError('Not consumed-state error')
    for field in ('nu_before','nu_ideal','nu_applied','a_sta'):
        if not np.all(np.isnan(vector(x,field))): raise ValueError('Invented STA state in PID')
    for field in ('a_req','a_proxy','thrust'):
        if not np.all(np.isfinite(vector(x,field))): raise ValueError('Nonfinite output '+field)
    proxy = vector(x,'thrust')*(9.80665/x['hover_thrust'][:,None])
    proxy[:,2] += 9.80665
    if not np.allclose(proxy,vector(x,'a_proxy'),rtol=0,atol=5e-6):
        raise ValueError('Incorrectly labelled thrust-map proxy')
    t = x['excitation_time'].astype(float)
    expected = np.where((t > 0)&(t < 32), .2*np.sin(2*np.pi*t/8)*np.sin(np.pi*t/32)**2, 0)
    if not np.allclose(expected, x['excitation'], rtol=0, atol=1e-6):
        raise ValueError('Wrong/inhibited waveform')
    em = (t >= 0)&(t < 32)
    if require_excitation and (em.sum() < 2500 or np.ptp(t[em]) < 31.96 or t[-1] < 32 or t[0] > 0):
        raise ValueError('Incomplete 32 s excitation inside hover window')
    tm = x['timestamp_sample'].astype(np.int64)
    weights = np.diff(np.r_[tm, tm[-1]+int(np.median(np.diff(tm)))])*1e-6
    result = dict(n=n,hz=(n-1)*1e6/(tm[-1]-tm[0]), maximum_gap_s=float(np.diff(tm).max()*1e-6),
                  consumed_velocity_error=stats(vector(x,'s'),weights), sequence_complete=True, inner=inner,
                  clock=int(x['clock'][0]), controller_time_max_us=int(x['controller_time_us'].max()),
                  module_time_max_us=int(x['module_time_us'].max()))
    if require_excitation:
        result['excitation_error'] = stats(vector(x,'s')[em],weights[em])
        result['excitation_samples'] = int(em.sum())
        result['excitation_seconds'] = float(weights[em].sum())
        result['constraint_fraction'] = float(np.mean(x['constraint_bits'][em] != 0))
        constrained = x['constraint_bits'][em] != 0
        longest = current = 0.
        for flag,dt in zip(constrained,weights[em]):
            current = current+dt if flag else 0.
            longest = max(longest,current)
        result['maximum_continuous_constraint_s'] = float(longest)
        if result['constraint_fraction'] > .05 or longest > .5:
            raise ValueError('PID excitation constraint envelope exceeded')
        result['excitation_iae_m'] = (np.abs(vector(x,'s')[em])*weights[em,None]).sum(axis=0).tolist()
        result['acceleration_tv'] = np.abs(np.diff(vector(x,'a_req')[em],axis=0)).sum(axis=0).tolist()
        result['excitation_peak_m_s'] = float(np.abs(x['excitation'][em]).max())
    return result


def exact_output_match(d, output, dtime, pairs, start, end):
    m = (d['timestamp'] >= start)&(d['timestamp'] < end)
    keys = d[dtime][m].astype(np.int64)
    common, a, b = np.intersect1d(keys,output['timestamp'].astype(np.int64),return_indices=True)
    coverage = len(common)/len(keys) if len(keys) else 0
    gap = np.max(np.diff(common))*1e-6 if len(common)>1 else float('inf')
    if coverage < .8 or gap > .25: raise ValueError('Insufficient downstream exact coverage '+dtime)
    maximum = 0.
    for left,right in pairs:
        l,r = d[left][m][a],output[right][b]
        if not np.array_equal(l,r,equal_nan=True): raise ValueError('Published output differs '+left)
        finite = np.isfinite(l)&np.isfinite(r)
        if finite.any(): maximum = max(maximum,float(np.abs(l[finite]-r[finite]).max()))
    return dict(matched=len(common),denominator=len(keys),coverage=coverage,max_gap_s=float(gap),max_abs_error=maximum)


def analyze(run, protocol):
    analyze_v01.CONFIG = CONFIG
    baseline = analyze_v01.analyze(run,protocol)
    v00 = json.loads((run/'v00_metrics.json').read_text())
    log = ULog(v00['ulog']['archive'])
    events = {e['name']:e['timestamp_us'] for e in json.loads((run/'result.json').read_text())['events']}
    summary = dict(accepted=False,baseline_accepted=baseline['accepted'])
    try:
        d = log.get_dataset('sta_velocity_ctrl_status').data
        start,end = events['hover_start'],events['hover_end']
        summary['diagnostic'] = check_diagnostic(d,start,end)
        # Entire flight has mode/time/sequence evidence; finite velocity errors
        # and all PID axes are required only in the main airborne metric window.
        fm = (d['timestamp']>=events['takeoff_command'])&(d['timestamp']<events['landed_disarmed'])
        ft = d['timestamp'][fm]
        if not len(ft) or ft[0]-events['takeoff_command']>40000 or events['landed_disarmed']-ft[-1]>40000:
            raise ValueError('Flight diagnostic boundary missing')
        if np.any(np.diff(d['publish_seq'][fm].astype(np.int64))!=1): raise ValueError('Flight sequence missing')
        for k,v in dict(effective_mode=0,effective_axes=0,inner_mode=0,inner_axes=0,inner_divisor=1,
                        inner_valid=1,fault=0,failsafe=0,timing=0,pid_calls=1,valid=1).items():
            if np.any(d[k][fm]!=v): raise ValueError('Flight diagnostic '+k)
        pairs = [(f'v_sp[{i}]',v) for i,v in enumerate(('vx','vy','vz'))]
        pairs += [(f'a_req[{i}]',f'acceleration[{i}]') for i in range(3)]
        pairs += [(f'thrust[{i}]',f'thrust[{i}]') for i in range(3)]
        summary['local_output'] = exact_output_match(d,log.get_dataset('vehicle_local_position_setpoint').data,
                                                     'output_timestamp',pairs,start,end)
        summary['attitude_output'] = exact_output_match(d,log.get_dataset('vehicle_attitude_setpoint').data,
            'attitude_timestamp',[(f'q_sp[{i}]',f'q_d[{i}]') for i in range(4)],start,end)
        summary['accepted'] = baseline['accepted']
        summary['limitations'] = ['Thrust-map proxy is not measured acceleration; HRT is simulation clock.',
            'One PID development flight, default unseeded engines, no STA performance claim.',
            'Async output checks use exact available matches, not fabricated full downstream coverage.']
    except (KeyError,ValueError,IndexError) as error:
        summary['error'] = str(error)
    save(run/'v03_metrics.json',summary)
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('run',type=Path); args=p.parse_args()
    result = analyze(args.run,json.loads((CONFIG/'protocol.json').read_text()))
    print(json.dumps(result,indent=2)); raise SystemExit(0 if result['accepted'] else 1)
