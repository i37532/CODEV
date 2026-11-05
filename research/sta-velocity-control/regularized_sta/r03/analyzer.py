"""R03 whole-flight qualification, distinct from R02 offline component validity.

Threshold sources: AX04 core/analyze and V08 protocol02 baseline (90--92s,
paired 1.25*PID+[.02,.02,.01], position+.05, yaw+.02, constraints .05/.5s).
A/B use the qualified V04/Z03 32s waveform, split into predeclared16s halves;
C/D retain64s/32s halves. R02 clock/protection primitives remain immutable.
The observed low-amplitude task must be velocity-unclamped (targets.py); active
velocity-limit behavior is covered offline, not inferred from hidden limits.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import numpy as np

# Import by path so a verifier/library caller outside this directory cannot
# resolve an unrelated historical module named targets (or fail to find it).
_target_spec=importlib.util.spec_from_file_location('r03_targets_module',Path(__file__).with_name('targets.py'))
_targets=importlib.util.module_from_spec(_target_spec);_target_spec.loader.exec_module(_targets)
REPO,HERE,leaf,spec,windows=_targets.REPO,_targets.HERE,_targets.leaf,_targets.spec,_targets.windows
check_targets,check_waveform=_targets.check_targets,_targets.check_waveform


def _protocol():
    return leaf('protocol',str((HERE/'protocol.py').relative_to(REPO)))


def _r02():
    """Load immutable R02 in an isolated namespace; restore generic import keys."""
    root = HERE.parent / 'r02/tools'
    saved = {name: sys.modules.get(name) for name in ('config', 'legacy')}
    try:
        for name in ('config', 'legacy'):
            module = leaf('r02_'+name, str((root/(name+'.py')).relative_to(REPO)))
            sys.modules[name] = module
        return leaf('r02_analyzer', str((root/'analyzer.py').relative_to(REPO)))
    finally:
        for name, value in saved.items():
            if value is None: sys.modules.pop(name, None)
            else: sys.modules[name] = value


r02 = _r02()
r02.initialize()
from position_log import ULog
from v04_attitude_clock09 import AttitudeClockPolicy, exact_output_match
from run_v00 import save, check_parameters
from analyze_v00 import previous_indices
from analyze_v03 import check_inner_evidence
from audit_v00_results import saturation_summary
from height import height_evidence
from landing_health import verify_model
from landing_complete import check_complete
from imu_health import check_health
from cli_clock import audit_commands
from v04_task04 import excitation_class


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_job(job):
    task, axes, task_mode, duration = spec(job)
    r02.validate(job['mode'], job['axes'], job['parameters'], allowed_task_modes=(task_mode,))
    if type(job.get('seed')) is not int or job['seed'] <= 0:
        raise ValueError('Missing positive integral paired seed')
    if job.get('candidate') != {0:'PID', 1:'ESTA', 3:'RSTA'}[job['mode']]:
        raise ValueError('Candidate label differs from actual requested mode')
    return task, axes, task_mode, duration


def check_components(d, selection, job, start, end, steady=False):
    """Explicit R03 task dispatch around unchanged R02 numerical validators."""
    validate_job(job)
    fullq = r02.aligned(d, selection)
    mask = (d['timestamp'] >= start)&(d['timestamp'] < end)
    x = {k:v[mask] for k,v in d.items()}; q = {k:v[mask] for k,v in fullq.items()}
    if len(x['timestamp']) < 600 or x['timestamp'][0]-start > 40000 or end-x['timestamp'][-1] > 40000:
        raise ValueError('Missing diagnostic window/boundary')
    for key in ('timestamp', 'timestamp_sample', 'input_timestamp'):
        if np.max(np.diff(x[key].astype(np.int64))) > 40000:
            raise ValueError('Diagnostic time gap '+key)
    for key, value in dict(requested_mode=job['mode'], effective_mode=job['mode'], requested_axes=job['axes'],
            effective_axes=job['axes'], pending=0, reject=0, inner_mode=0, inner_axes=0, inner_divisor=1,
            inner_valid=1, fault=0, failsafe=0, timing=0, sta_fault=0, config_pending=0).items():
        if np.any(x[key] != value): raise ValueError('Unexpected actual mode/state '+key)
    active = x['enabled'].astype(bool)
    if not np.any(active) or np.any(x['valid'][active] != 1) or np.any(x['pid_calls'] != active.astype(int)):
        raise ValueError('Invalid output/first invocation/failsafe retry')
    if np.any(np.diff(x['update_seq'].astype(np.int64)) != x['pid_calls'][1:]):
        raise ValueError('Missing controller invocation')
    if np.any(~np.isfinite(x['raw_dt'][active])) or np.any(x['raw_dt'][active] < .002) or np.any(x['raw_dt'][active] > .04):
        raise ValueError('Actual raw sample interval out of domain')
    if not np.allclose(x['raw_dt'][1:], np.diff(x['timestamp_sample'].astype(np.int64))*1e-6, atol=1e-7, rtol=0):
        raise ValueError('raw_dt differs from actual sensor time')
    if not np.allclose(x['used_dt'], np.clip(x['input_dt'], .002, .04), atol=1e-7, rtol=0):
        raise ValueError('Legacy PID dt semantics changed')
    if not np.allclose(r02.vector(x,'s')[active], (r02.vector(x,'v')-r02.vector(x,'v_sp'))[active], atol=1e-7, rtol=0, equal_nan=True):
        raise ValueError('Wrong consumed velocity error')
    if steady and (not np.all(active) or not np.all(x['armed']) or np.any(x['reset_bits'])
            or np.any(x['sta_flags'].astype(int)&(1|2|4|64|128))):
        raise ValueError('Observation reset/priming/inactive/fault')
    check_inner_evidence({k:v[active] for k,v in x.items()})
    for key, value in dict(variant_req=job['mode'], variant_eff=job['mode'], sta_pending=0).items():
        if np.any(q[key] != value): raise ValueError('Wrong selected algorithm metadata '+key)
    if job['mode'] and np.any(q['sta_reject']):
        raise ValueError('Rejected active STA configuration')
    if not np.array_equal(q['sta_gen'], x['config_generation']) or (steady and np.any(np.diff(q['sta_gen'].astype(np.int64)))):
        raise ValueError('Wrong/stale armed parameter generation')
    if job['mode'] and np.any(q['sta_gen'] <= 0):
        raise ValueError('Active STA has no accepted configuration generation')
    for axis, suffix in enumerate('XYZ'):
        eps = job['parameters']['MPC_VC_EPS_'+suffix]
        if not np.allclose(q[f'eps_req[{axis}]'], eps, atol=1e-7, rtol=0):
            raise ValueError('Wrong requested epsilon')
        eff = q[f'eps_eff[{axis}]']
        if job['mode'] == 3 and job['axes']&(1<<axis):
            if not np.allclose(eff, eps, atol=1e-7, rtol=0): raise ValueError('Wrong effective epsilon')
        elif not np.all(np.isnan(eff)):
            raise ValueError('Effective epsilon claimed by unselected/legacy axis')
    cadence = (r02.check_regularized(x,q,job,steady) if job['mode'] == 3
               else r02.cadence_checks().check(x,q,job,steady))
    for field in ('a_req','a_proxy','thrust'):
        if not np.all(np.isfinite(r02.vector(x,field)[active])): raise ValueError('Nonfinite output '+field)
    proxy = r02.vector(x,'thrust')*(9.80665/x['hover_thrust'][:,None]); proxy[:,2] += 9.80665
    if not np.allclose(proxy[active],r02.vector(x,'a_proxy')[active],atol=5e-6,rtol=0):
        raise ValueError('Thrust mapping proxy differs')
    return dict(samples=len(x['timestamp']), cadence=cadence,
        sample_hz=(len(x['timestamp'])-1)/((x['timestamp_sample'][-1]-x['timestamp_sample'][0])*1e-6)), x, q


def stats(values, weights):
    a = np.asarray(values,dtype=float); w = np.asarray(weights,dtype=float)
    if not len(a) or not np.all(np.isfinite(a)) or np.any(w <= 0) or not np.all(np.isfinite(w)):
        raise ValueError('Invalid metric samples/weights')
    mean = np.average(a,axis=0,weights=w); variance = np.average((a-mean)**2,axis=0,weights=w)
    return dict(rmse=np.sqrt(np.average(a*a,axis=0,weights=w)).tolist(),mean=mean.tolist(),
        variance=variance.tolist(),std=np.sqrt(variance).tolist(),max_abs=np.max(abs(a),axis=0).tolist())


def window_metrics(x, q, job, lo, hi):
    t = x['excitation_time'].astype(float); m = (t >= lo)&(t < hi)
    if m.sum() < .8*(hi-lo)*100 or np.ptp(t[m]) < hi-lo-.04:
        raise ValueError('Incomplete main/half window')
    tm = x['timestamp_sample'].astype(np.int64)
    h = np.diff(np.r_[tm,tm[-1]+int(np.median(np.diff(tm)))])*1e-6
    constrained = (x['constraint_bits'][m] != 0)|((x['sta_flags'][m].astype(int)&(8|16|32)) != 0)
    longest = current = 0.
    for flag, step in zip(constrained,h[m]):
        current = current+step if flag else 0.; longest = max(longest,current)
    fraction = float(np.mean(constrained))
    if fraction > .05 or longest > .5: raise ValueError('Constraint risk envelope')
    updated = m&q['control_updated'].astype(bool)
    err = stats(r02.vector(x,'s')[m],h[m]); seconds = float(h[m].sum())
    fields = {'acceleration':'a_req','normalized_thrust':'thrust'}
    result = dict(error=err,J=float(np.mean(err['rmse'])),seconds=seconds,samples=int(m.sum()),
        actual_updates=int(updated.sum()),constraint_fraction=fraction,maximum_continuous_constraint_s=longest,
        iae_m=(abs(r02.vector(x,'s')[m])*h[m,None]).sum(axis=0).tolist(),
        nu_peak={axis:float(np.max(abs(x[f'nu_applied[{i}]'][m]))) for i,axis in enumerate('XYZ') if job['axes']&(1<<i)})
    for label, field in fields.items():
        tv=np.abs(np.diff(r02.vector(x,field)[updated],axis=0)).sum(axis=0)
        result[label+'_tv']=tv.tolist();result[label+'_tv_per_second']=(tv/seconds).tolist()
    correction = r02.vector(q,'correction')[updated]
    tv = np.abs(np.diff(correction,axis=0)).sum(axis=0)
    result.update(correction_tv=tv.tolist(),correction_tv_per_second=(tv/seconds).tolist())
    return result


def spectral_metrics(x,q,duration):
    spectra = leaf('spectra_reference','research/sta-velocity-control/v07/protocol03/spectra.py')
    m=(x['excitation_time']>=0)&(x['excitation_time']<duration)
    t=x['timestamp_sample'][m].astype(float)*1e-6; updated=q['control_updated'][m].astype(bool)
    if len(t)<.8*duration*100 or np.any(np.diff(t)<=0) or np.max(np.diff(t))>.040001:
        raise ValueError('Incomplete spectral source')
    c=r02.vector(q,'correction')[m]; st=t[updated]; rate=(len(st)-1)/(st[-1]-st[0])
    ng=np.arange(st[0],st[-1],1/rate); native=c[updated][np.searchsorted(st,ng,side='right')-1]
    cg=np.arange(t[0],t[-1],.01); callbacks=c[np.searchsorted(t,cg,side='right')-1]
    f,p=spectra.psd(native,rate); cf,cp=spectra.psd(spectra.antialias(callbacks),25.)
    band=cf<=7.;df=cf[1]-cf[0]
    return dict(update_hz=rate,native_frequency_hz=f.tolist(),native_psd=p.tolist(),
        common_frequency_hz=cf.tolist(),common_psd=cp.tolist(),common_0_7hz_rms=np.sqrt(np.sum(cp[band],axis=0)*df).tolist(),
        notes='Analysis-only measured-rate ZOH,100Hz callback grid;513tap8Hz Blackman FIR then25Hz;2.56s boundary crop. No interpolation used for log validity; TV is not energy.')


def first_invocation(d,mask):
    active=mask&d['enabled'].astype(bool)
    if not np.any(active) or np.any(d['first_fail'][active]) or np.any(d['retry_result'][active]):
        raise ValueError('First controller invocation failed/retried')
    expected=np.zeros(active.sum(),dtype=np.uint16)
    for group,field in enumerate(('p_sp','v_ff','a_ff','v','v_dot')):
        for axis in range(3): expected|=np.isfinite(d[f'{field}[{axis}]'][active]).astype(np.uint16)<<(3*group+axis)
    if not np.array_equal(expected,d['first_input'][active]): raise ValueError('Wrong first-input validity mask')
    return dict(samples=int(active.sum()),first_failures=0,retries=0)


def check_exit(d,status,events):
    start,end=events['takeoff_command'],events['landed_disarmed']
    hs,he,land=[events[k] for k in ('hover_start','hover_end','land_command')]
    if not start<hs<he<=land<end or not 90e6<=he-hs<=92e6:
        raise ValueError('Wrong observation/landing event intervals')
    m=(d['timestamp']>=start)&(d['timestamp']<=end)
    i,_=previous_indices(status['timestamp'],d['timestamp'][m]);nav=status['nav_state'][i]
    entered=np.flatnonzero((nav==18)&(d['timestamp'][m]>=land))
    if not len(entered) or np.any(nav[entered[0]:]!=18):raise ValueError('Missing/left planned AUTO_LAND')
    counts={'clear':0,'expected_planned_landing_gate':0}
    for j,n in zip(np.flatnonzero(m),nav):
        t=d['timestamp'][j]
        for key in ('excitation','excitation_y','excitation_z'):
            category=excitation_class(int(d['excitation_fault'][j]),bool(d['armed'][j]),int(n),t>=land,t>=he,d[key][j])
        counts[category]+=1
    pre=d['armed'].astype(bool)&(d['timestamp']<start)
    disarmed=(d['timestamp']>=end)&~d['armed'].astype(bool)
    if np.any(d['excitation_fault'][pre]) or not np.any(disarmed) or np.any(d['excitation_fault'][disarmed]):
        raise ValueError('Preflight latch or missing disarm reset')
    if not counts['expected_planned_landing_gate']:raise ValueError('Missing planned gate exit')
    return counts


def provenance(run,protocol,job):
    validate_job(job)
    if job not in protocol['jobs']:raise ValueError('Job outside frozen manifest')
    if json.loads((run/'run_protocol.json').read_text())!=protocol:
        raise ValueError('Saved actual protocol differs from analyzer binding')
    config=Path(protocol['config_dir']); execution=Path(protocol['execution_path']); qp=Path(protocol['qualification_path'])
    reference=json.loads((run/'qualification_reference.json').read_text())
    if Path(reference.get('path','')).resolve()!=qp.resolve() or reference.get('sha256')!=digest(qp):
        raise ValueError('Explicit qualification sidecar differs')
    approval=json.loads((run/'authorization.json').read_text()); qualified=json.loads(qp.read_text())
    record=json.loads((run/'result.json').read_text())
    if (qualified.get('success') is not True or qualified.get('clean') is not True
            or qualified.get('stage')!=protocol['stage'] or qualified.get('gate')!=job['gate']
            or qualified.get('new_flights')!=0):
        raise ValueError('Qualification is not an accepted clean offline gate')
    expected=dict(stage=protocol['stage'],gate=job['gate'],source_head=qualified['source_head'],execution_sha256=digest(execution),
        frozen_sha256=digest(config/'frozen.json'),firmware_sha256=qualified['firmware_sha256'],
        qualification_sha256=digest(qp),maximum_attempts=protocol['maximum_attempts'],
        total_maximum_attempts=protocol['total_maximum_attempts'])
    if protocol['maximum_attempts']!=9 or protocol['total_maximum_attempts']!=36:
        raise ValueError('Changed fixed gate/total attempt budget')
    for key in ('execution_sha256','frozen_sha256'):
        if qualified.get(key)!=expected[key]:raise ValueError('Qualification frozen input changed')
    if approval.get('approved') is not True or any(approval.get(k)!=v for k,v in expected.items()):
        raise ValueError('Wrong frozen qualification/authorization binding')
    if (record.get('source_head')!=expected['source_head'] or record.get('binary_sha256')!=expected['firmware_sha256']
            or record.get('scenario_sha256')!=expected['execution_sha256'] or record.get('scenario_path')!=str(execution)
            or json.loads((run/'job.json').read_text())!=job):raise ValueError('Wrong source/binary/scenario/job provenance')
    restored=json.loads((run/'parameter_restore.json').read_text())
    if (restored.get('parameter_restore_exact') is not True or restored.get('remaining_simulators')
            or restored.get('stopped_before_restore') is not True or restored.get('source_head')!=record['source_head']
            or restored.get('gate')!=job['gate'] or restored.get('job_id')!=job['id']
            or restored.get('original_parameter_sha256')!=digest(run/'original_parameters.bson')
            or restored.get('restored_parameter_sha256')!=restored['original_parameter_sha256']):
        raise ValueError('Missing exact complete parameter restore/shutdown evidence')
    return expected


def replay_protocol(run,job):
    """Only the explicitly qualified path and this job's startup overlay vary."""
    frozen=_protocol().load_protocol(job['gate']);saved=json.loads((Path(run)/'run_protocol.json').read_text())
    reference=json.loads((Path(run)/'qualification_reference.json').read_text())
    if Path(reference.get('path','')).resolve()!=Path(saved['qualification_path']).resolve() or reference.get('sha256')!=digest(Path(reference['path'])):
        raise ValueError('Replay qualification sidecar mismatch')
    excluded={'qualification_path','startup_overrides'}
    if {k:v for k,v in saved.items() if k not in excluded}!={k:v for k,v in frozen.items() if k not in excluded}:
        raise ValueError('Saved replay protocol differs from frozen gate')
    if saved['startup_overrides']!={**frozen['startup_overrides'],**job['parameters']}:
        raise ValueError('Wrong per-job replay parameter overlay')
    path=Path(saved['qualification_path']).resolve()
    if Path(frozen['qualification_path']).resolve().parent.parent not in path.parents:
        raise ValueError('Replay qualification is outside frozen gate')
    return saved


def analyze(run,protocol,job):
    run=Path(run);out=dict(accepted=False,job=job)
    try:
        out['binding']=provenance(run,protocol,job)
        verify_model(run,Path(protocol['plugins']),replay=True)
        # A separately loaded baseline instance: no mutation of old shared modules.
        bs=importlib.util.spec_from_file_location('r03_baseline_instance',REPO/'research/sta-velocity-control/v08/protocol02/baseline.py')
        base_module=importlib.util.module_from_spec(bs);bs.loader.exec_module(base_module)
        base_module.CONFIG=Path(protocol['config_dir'])
        policy=AttitudeClockPolicy();p={**protocol,'startup_overrides':{**protocol['startup_overrides'],**job['parameters']}}
        base=base_module.analyze(run,p,attitude_policy=policy)
        base['limitations']=['Inherited90s position/yaw and physical safety checks; uninstrumented output/state association is a proxy.',
            'R03 separately checks actual consumed velocity/target/sample and complete diagnostic sequences.',
            'Three paired IMU seeds per gate; non-IMU randomness and host scheduling are not claimed independently seeded.']
        save(run/'v00_metrics.json',base)
        out['baseline_accepted']=bool(base['accepted']);out['baseline_checks']=base['checks']
        record=json.loads((run/'result.json').read_text());events={e['name']:e['timestamp_us'] for e in record['events']}
        u=ULog(base['ulog']['archive'])
        if u.dropouts or getattr(u,'file_corruption',False):raise ValueError('ULog dropout/corruption')
        d=u.get_dataset('sta_velocity_ctrl_status').data;q=u.get_dataset('velocity_ctrl_selection').data
        fs,fe=events['takeoff_command'],events['landed_disarmed'];hs,he=events['hover_start'],events['hover_end']
        out['flight'],whole,wholeq=check_components(d,q,job,fs,fe)
        out['lifecycle']={key:{str(int(k)):int(v) for k,v in zip(*np.unique(whole[key],return_counts=True))}
            for key in ('z_phase','active_axes','committed_axes','pid_axes','takeoff_state','reset_bits')}
        out['lifecycle'].update(hte_shift_count=int(np.count_nonzero(whole['z_hte_shift'])),
            hte_shift_max_abs=float(np.max(abs(whole['z_hte_shift']))),
            true_updates=int(np.count_nonzero(wholeq['control_updated'])),
            actual_algorithms=np.unique(wholeq['variant_eff']).astype(int).tolist())
        out['observation'],x,s=check_components(d,q,job,hs,he,True)
        out['first_invocation']=first_invocation(d,(d['timestamp']>=fs)&(d['timestamp']<fe))
        out['exit']=check_exit(d,u.get_dataset('vehicle_status').data,events)
        out['task_targets']=check_targets(u,d,events,job)
        out['diagnostic']=window_metrics(x,s,job,0,spec(job)[3])
        out['diagnostic']['windows']={name:window_metrics(x,s,job,lo,hi) for name,lo,hi in windows(job)}
        out['pid_reconstruction']=r02.cadence_checks().check_pid_path(x,s,job,u.initial_parameters)
        spectrum=spectral_metrics(x,s,spec(job)[3]);save(run/'spectra.json',spectrum)
        out['spectral_summary']={k:v for k,v in spectrum.items() if not k.endswith(('psd','frequency_hz'))}
        out['host_cost']={name:{k:float(v) for k,v in zip(('median_us','p95_us','p99_us','max_us'),np.percentile(s[name]*1e-3,[50,95,99,100]))} for name in ('path_ns','module_ns')}
        for filename in ('runtime_parameters_start.json','runtime_parameters_end.json'):
            check_parameters(json.loads((run/filename).read_text()),job['parameters'])
        out['actual_output']=exact_output_match(d,u.get_dataset('vehicle_local_position_setpoint').data,'output_timestamp',
            [(f'v_sp[{i}]',('vx','vy','vz')[i]) for i in range(3)]+[(f'a_req[{i}]',f'acceleration[{i}]') for i in range(3)]+
            [(f'thrust[{i}]',f'thrust[{i}]') for i in range(3)],fs,fe)
        out['rate_actuator']=r02.rate_and_actuator_evidence(u,fs,fe)
        out['height_task']=height_evidence(u,run,d,events,attitude_policy=policy)
        out['landing']=check_complete(u,events,json.loads((run/'landing_context.json').read_text()))
        out['landing_health']=check_health(u,events['land_command'],fe)
        tail=json.loads((run/'postland_tail.json').read_text())
        if (tail['landing_start_us']!=events['land_command'] or tail['landed_disarmed_us']!=fe or not tail['snapshots']
                or tail['snapshots'][-1]['pending'] or tail['health']!=out['landing_health']):raise ValueError('Incomplete postlanding tail')
        out['postland_tail']=tail;out['cli_receipts']=audit_commands(run/'commands.jsonl')
        commands=[json.loads(line) for line in (run/'commands.jsonl').read_text().splitlines()]
        lands=[c for c in commands if c['cmd'][-3:]==['commander','mode','auto:land'] or c['cmd'][-2:]==['mode','auto:land']]
        if len(lands)!=1 or lands[0]['returncode']!=0:raise ValueError('Land command not unique/successful')
        rate=u.get_dataset('sta_rate_ctrl_status').data;rm=(rate['timestamp']>=hs)&(rate['timestamp']<he)
        out['mixer']=saturation_summary(rate['sat_bits'][rm],rate['sat_valid'][rm])
        out.update(position_log=u.position_log_evidence,ulog=base['ulog'],position_rmse=base['metrics']['position_error_m']['rmse'],
            yaw_rmse=base['metrics']['yaw_error_rad']['rmse'],height=base['metrics']['height_error_from_2p5_m'],
            accepted=bool(base['accepted']),limitations=['R03 development only; three paired IMU seeds per gate, other randomness not fully controlled.',
                'New source per gate; four gates are not36 same-source repetitions.','Common external target does not imply identical consumed velocity targets.',
                'Observed task is velocity-unclamped; active speed limiting only has offline regression evidence.',
                'Thrust proxy is not actual acceleration; TV is not energy; host wall time is not board CPU.'])
    except (KeyError,ValueError,IndexError,FileNotFoundError,TypeError) as exc:
        out.update(accepted=False,error=str(exc))
    save(run/'r03_metrics.json',out)
    return out


def compare(pid,candidate):
    for item in (pid,candidate):
        validate_job(item['job'])
        if item.get('accepted') is not True:raise ValueError('Unaccepted paired member')
    a,b=pid['job'],candidate['job']
    if a['mode']!=0 or b['mode'] not in (1,3) or any(a[k]!=b[k] for k in ('seed','gate','task','divisor','main_duration_s')):
        raise ValueError('Wrong mode/seed/gate/task paired comparison')
    if pid.get('binding')!=candidate.get('binding'):raise ValueError('Pair not from the same frozen source/protocol/firmware')
    permitted={'MPC_VC_MODE','MPC_VC_AXES'}
    if {k:v for k,v in a['parameters'].items() if k not in permitted}!={k:v for k,v in b['parameters'].items() if k not in permitted}:
        raise ValueError('Paired fixed gains/protection/epsilon differ')
    checks={}
    for axis,allow in enumerate((.02,.02,.01)):
        checks['velocity_'+str(axis)]=candidate['diagnostic']['error']['rmse'][axis]<=1.25*pid['diagnostic']['error']['rmse'][axis]+allow
        checks['position_'+str(axis)]=candidate['position_rmse'][axis]<=1.25*pid['position_rmse'][axis]+.05
        for name,_,_ in windows(a):
            checks[name+'_velocity_'+str(axis)]=candidate['diagnostic']['windows'][name]['error']['rmse'][axis]<=1.25*pid['diagnostic']['windows'][name]['error']['rmse'][axis]+allow
    checks['yaw']=candidate['yaw_rmse']<=1.25*pid['yaw_rmse']+.02
    return dict(accepted=all(checks.values()),checks=checks,seed=a['seed'],gate=a['gate'],candidate=b['candidate'],
                criterion='Inherited development risk, not a requirement to beat PID or ESTA')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('run',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();source=args.run.resolve();dest=args.output.resolve()
    if source==dest or source in dest.parents:raise ValueError('Independent replay output required')
    dest.mkdir(parents=True,exist_ok=False)
    for path in source.iterdir():
        if path.is_file() and path.suffix in ('.json','.jsonl','.txt','.log','.bson'):shutil.copyfile(path,dest/path.name)
    job=json.loads((dest/'job.json').read_text());protocol=replay_protocol(dest,job)
    result=analyze(dest,protocol,job);print(json.dumps(result,indent=2));raise SystemExit(0 if result['accepted'] else 1)
