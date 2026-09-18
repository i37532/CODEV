#!/usr/bin/env python3
import argparse, hashlib, json, math
from pathlib import Path
import sys
import numpy as np
from pyulog import ULog

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'scripts'))
from analyze_m00 import analyze as analyze_base, plain
from analyze_m03 import pid_output, require, sequence_stats, vector

def proper_reference(s,nu,h,l1,l2,g,iterations=100):
    q=h*h*l2
    if abs(s)<=q: z,xi=0.,s/q
    else:
        sign=math.copysign(1.,s);delta=abs(s)-q;lo,hi=0.,delta
        for _ in range(iterations):
            mid=(lo+hi)*.5
            if mid+h*l1*math.sqrt(mid)>delta: hi=mid
            else: lo=mid
        z,xi=sign*(lo+hi)*.5,sign
    next_nu=nu-h*l2*xi;a=next_nu+(z-s)/h
    return dict(z=z,xi=xi,nu=next_nu,a=a,c=a/g,branch=2 if z==0 else (1 if z>0 else 3))

def research_log(run,result):
    settings=json.loads((run/'m03_logging.json').read_text());candidates=[]
    for index,item in enumerate(result.get('logs',[])):
        path=Path(item['archive']);require(hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256'],'ULog hash')
        log=ULog(str(path))
        if log.initial_parameters.get('SDLOG_PROFILE')==settings['research_profile']: candidates.append((index,path,log))
    require(len(candidates)==1,'Require one research ULog');return candidates[0]

def windows(protocol,d,hover):
    result={'hover':hover,'tracking':hover&(d['research_elapsed']>=0)&(d['research_elapsed']<=protocol['tracking_seconds'])}
    for name,(lo,hi) in protocol['windows'].items(): result[name]=hover&(d['research_elapsed']>=lo)&(d['research_elapsed']<hi)
    return result

def analyze(run):
    result=json.loads((run/'result.json').read_text()); job=json.loads((run/'m10_job.json').read_text())
    out=dict(success=False,algorithm=job['algorithm'],mode=job['mode'],seed=job['seed'],subgate=job['subgate'],
             source_head=result.get('source_head'),binary_sha256=result.get('binary_sha256'))
    try:
        require(result['success'],'Flight failed: '+str(result.get('error',result.get('cleanup_error'))))
        index,path,log=research_log(run,result); analyze_base(run,log_index=index)
        metrics=json.loads((run/'metrics.json').read_text()); config=json.loads((run/'m04_config.json').read_text())
        protocol=json.loads((run/'m04_protocol.json').read_text()); limits=protocol['limits']; mode=int(job['mode'])
        remediation=job.get('remediation_subgate'); expected_axes=7 if remediation in ('R-B','R-C') else 3
        require(job['subgate']=='A' and mode in (1,3) and config['MC_STA_AXES']==expected_axes,'Wrong I05 mode/mask')
        expected_div=int(config['MC_RTC_DIV'])
        require(expected_div==int(job['parameters']['MC_RTC_DIV']),'Requested/actual divisor mismatch')
        require(config['MC_STA_TKO_MGT']==0 and expected_div in (1,2,4),'Protection/divisor drift')
        require(log.msg_info_dict.get('ver_hw')=='PX4_SITL' and log.msg_info_dict.get('ver_sw')==job['frozen_head'],'Wrong SITL/source')
        for name,value in config.items():
            require(name in log.initial_parameters and np.isclose(log.initial_parameters[name],value,rtol=2e-6,atol=2e-6),'Parameter mismatch '+name)
        d=log.get_dataset('sta_rate_ctrl_status').data; t=d['timestamp_sample'].astype(np.int64); armed=d['armed'].astype(bool)
        hover=(t>=metrics['hover_start_us'])&(t<=metrics['hover_end_us']); masks=windows(protocol,d,hover)
        require(all(np.count_nonzero(v)>2000 for v in masks.values()),'Incomplete metric window')
        for field,expected in [('requested_mode',mode),('effective_mode',mode),('requested_axes',expected_axes),('effective_axes',expected_axes),
                               ('request_status',0),('pending',0),('fault',0),('abort_requested',0),('config_pending',0)]:
            require(np.all(d[field]==expected),'Unexpected '+field)
        for field in ('measurement_valid','output_valid'): require(np.all(d[field][armed]),'Invalid '+field)
        require(np.all(d['timing_status'][armed]==0) and np.all(np.diff(t)>0),'Timing/sample order')
        updated=d['updated'].astype(bool); held=d['held'].astype(bool)
        require(np.all(updated[armed]^held[armed]),'Update/hold partition')
        require(np.all(d['div_eff']==expected_div)&np.all(d['div_ok']),'DIV mismatch')
        status_seq=sequence_stats(d['publish_seq'][hover],t[hover]); update_seq=sequence_stats(d['update_seq'][hover],t[hover])
        require(status_seq['missing']==0 and len(log.dropouts)==0,'Diagnostic/ULog loss')
        require(np.all(np.diff(d['update_seq'].astype(np.int64))==updated[1:]),'Update counter')
        rate=vector(d,'rate'); error=vector(d,'s'); command=vector(d,'c_applied')
        require(np.max(np.abs(rate[armed]))<=limits['rate_rad_s'],'Rate boundary')
        selected=range(3) if expected_axes==7 else range(2)
        require(np.max(np.abs(command[armed][:,selected]))<=limits['selected_command_abs']+1e-6,'Command boundary')
        require(np.max(np.abs(vector(d,'nu')[armed][:,selected]))<=limits['nu_abs_rad_s2']+1e-6,'Nu boundary')
        require(metrics['tilt_deg']['max_abs']<=limits['tilt_deg'] and metrics['position_error_m']['max_abs'][2]<=limits['height_error_m'],'Pose boundary')
        if expected_axes==3:
            expected_pid=pid_output(d)
            require(np.array_equal(vector(d,'c_raw')[updated,2].copy().view(np.uint32),expected_pid[updated,2].copy().view(np.uint32)),'Yaw PID bit mismatch')
            require(np.all(d['pid_updated'][armed]),'Mixed path must update PID'); require(np.all(vector(d,'nu')[:,2]==0),'Yaw nu changed')
        else:
            require(not np.any(d['pid_updated'][armed]),'Full-axis path computed idle PID')
        if expected_div>1:
            require(np.all(np.isnan(d['dt'][held])) and np.all(d['kern_ns'][held]==0),'Held cycle evaluated kernel')
            require(np.array_equal(vector(d,'nu')[held],vector(d,'nu_before')[held]),'Nu advanced on hold')
            hidx=np.flatnonzero(held);hidx=hidx[hidx>0];cached=vector(d,'c_held')
            require(np.array_equal(cached[hidx],cached[hidx-1]),'Held torque changed')
            require(np.array_equal(command[armed],(cached*d['battery_scale'][:,None])[armed]),'Battery scale accumulated')
        for axis in selected:
            active=hover&d['experiment_updated'].astype(bool); old=vector(d,'nu_before')[:,axis]; candidate=vector(d,'nu_candidate')[:,axis]
            ideal_a=vector(d,'a_raw')[:,axis]; g=vector(d,'g')[:,axis]; s=error[:,axis]
            if mode==3:
                idx=np.flatnonzero(active); refs=[proper_reference(float(s[i]),float(old[i]),float(d['dt'][i]),
                    float(vector(d,'lambda1')[i,axis]),float(vector(d,'lambda2')[i,axis]),float(g[i])) for i in idx]
                for key,logged in [('a',ideal_a),('nu',candidate),('z',vector(d,'virtual_state')[:,axis]),('xi',vector(d,'xi')[:,axis])]:
                    np.testing.assert_allclose(logged[idx],np.array([r[key] for r in refs]),rtol=2e-6,atol=2e-7)
                np.testing.assert_array_equal(d[f'ista_branch[{axis}]'][idx],np.array([r['branch'] for r in refs])); factor=2.
            else:
                sigma=np.sign(s); expected_a=-vector(d,'lambda1')[:,axis]*np.sqrt(np.abs(s))*sigma+old
                expected_nu=old-d['dt']*vector(d,'lambda2')[:,axis]*sigma
                np.testing.assert_allclose(ideal_a[active],expected_a[active],rtol=2e-6,atol=2e-7)
                np.testing.assert_allclose(candidate[active],expected_nu[active],rtol=2e-6,atol=2e-7); factor=0.
            protected=ideal_a+factor*(vector(d,'nu')[:,axis]-candidate)
            np.testing.assert_allclose(vector(d,'a_protected')[active,axis],protected[active],rtol=2e-6,atol=2e-7)
            np.testing.assert_allclose(command[active,axis],np.clip(protected/g,-.15,.15)[active]*d['battery_scale'][active],rtol=2e-6,atol=2e-7)
            idx=np.flatnonzero(active); continuous=idx[1:][d['reset_reason'][idx[1:]]==0]
            previous=np.searchsorted(idx,continuous)-1
            np.testing.assert_array_equal(old[continuous],vector(d,'nu')[idx[previous],axis])
        act=log.get_dataset('actuator_controls_0').data; common,di,ai=np.intersect1d(t[updated],act['timestamp_sample'],return_indices=True)
        actual=np.column_stack([act[f'control[{i}]'] for i in range(3)])
        require(len(common)>10000/expected_div and np.array_equal(command[updated][di].copy().view(np.uint32),actual[ai].copy().view(np.uint32)),'Actuator mismatch')
        require(np.all(np.isin(t[hover&updated],common)),'Missing hover actuator update')
        elapsed=d['research_elapsed']; additions=np.column_stack([d['research_roll_addition'],d['research_pitch_addition'],d['research_yaw_addition']])
        commanded=({'yaw_only':(2,), 'synchronous_low':(0,1,2), 'synchronous_repeat':(0,1,2)}
                   if expected_axes==7 else {'roll_only':(0,), 'pitch_only':(1,), 'synchronous':(0,1)})
        stats={}
        for name,mask in masks.items():
            stats[name]=dict(rmse=np.sqrt(np.mean(error[mask].astype(float)**2,axis=0)).tolist(),samples=int(np.count_nonzero(mask)))
            if name in commanded:
                for axis in range(3):
                    v=additions[mask,axis]
                    if axis in commanded[name]:
                        require(np.max(v)>.119 and np.min(v)<-.119 and abs(float(np.trapz(v,elapsed[mask])))<.002,'Excitation '+name)
                    else: require(np.all(v==0),'Unexpected excitation '+name)
        rates_topics=[x for x in log.data_list if x.name=='vehicle_rates_setpoint']; require({x.multi_id for x in rates_topics}=={0},'Setpoint publisher multiplicity')
        ui=np.flatnonzero(hover&updated);require(len(ui)>1000 and np.all(np.diff(ui)==expected_div),'Measured update spacing')
        actual_update_hz=1/float(np.median(np.diff(t[ui]))*1e-6)
        out.update(success=True,analysis_success=True,ulog=str(path),ulog_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                   metrics=stats,dropouts=len(log.dropouts),sequences=dict(status=status_seq,updates=update_seq),
                   max_tilt_deg=metrics['tilt_deg']['max_abs'],max_height_error_m=metrics['position_error_m']['max_abs'][2],
                   max_abs_command=np.max(np.abs(command[armed]),axis=0).tolist(),max_abs_nu=np.max(np.abs(vector(d,'nu')[armed]),axis=0).tolist(),
                   saturation_fraction=float(np.mean((d['motor_saturation'][hover].astype(np.uint16)&0x1f8)!=0)),actuator_samples=len(common),
                   divisor=expected_div,actual_update_hz=actual_update_hz,held_samples=int(np.count_nonzero(hover&held)))
    except Exception as exc:
        out.update(success=False,analysis_success=False,error=repr(exc),failure_class='flight' if not result.get('success') else 'analysis_or_data_quality')
        if any(x in str(exc).lower() for x in ('boundary','fault','abort')): out['failure_class']='control_boundary'
    (run/'i05_analysis.json').write_text(json.dumps(out,indent=2,default=plain)+'\n'); print(json.dumps(out,indent=2,default=plain)); return out

def summarize(rows,name='A'):
    frozen=json.loads((HERE/f'FROZEN_{name}.json').read_text()); violations=[]
    if len(rows)!=len(frozen['ordered_jobs']): violations.append('attempt_count')
    for row in rows:
        if not row.get('success'): violations.append(row.get('algorithm','unknown')+':'+str(row.get('seed')))
    esta=[r for r in rows if r.get('algorithm')=='esta' and r.get('success')]; proper=[r for r in rows if r.get('algorithm')=='proper_ista' and r.get('success')]
    checks=[]; limits=frozen['flight_protocol']['limits']; command={'hover':(0,1),'tracking':(0,1),'roll_only':(0,), 'pitch_only':(1,), 'synchronous':(0,1)}
    if len(esta)!=3: violations.append('esta_count')
    if len(proper)!=3: violations.append('proper_count')
    if len(esta)==len(proper)==3:
        for window,axes in command.items():
            baseline=np.median([r['metrics'][window]['rmse'] for r in esta],axis=0)
            for row in proper:
                for axis,value in enumerate(row['metrics'][window]['rmse']):
                    threshold=limits['rmse_ratio_max']*baseline[axis] if axis in axes else max(limits['rmse_ratio_max']*baseline[axis],baseline[axis]+limits['uncommanded_absolute_margin_rad_s'])
                    checks.append(dict(seed=row['seed'],window=window,axis=axis,value=value,baseline=float(baseline[axis]),threshold=float(threshold)))
                    if value>threshold: violations.append(f"{row['seed']}:{window}:{axis}")
    return dict(success=not violations,subgate=name,planned=len(frozen['ordered_jobs']),attempted=len(rows),accepted=sum(bool(r.get('success')) for r in rows),violations=violations,checks=checks,rows=rows)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();raise SystemExit(0 if analyze(a.run.resolve())['success'] else 1)
