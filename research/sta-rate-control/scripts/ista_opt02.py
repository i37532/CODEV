#!/usr/bin/env python3
"""Frozen ablation followed by bounded low-lambda2 local parameter search."""
import argparse
import copy
import json
import subprocess
from pathlib import Path
import numpy as np
from batch_m10 import execute, REPO
from m10_design import equal_gains, SCENES, scenario
from ista_opt01 import BASE, immutable, digest, implicit, rows, metrics, compare_final
from diagnose_ista_takeoff import diagnose

PROTOCOL=REPO/'research/sta-rate-control/ista_opt02/PROTOCOL_CN.md'
TRAIN=(5201,5202)
VALIDATE=(5301,5302,5303)
DIAG=(5101,5102)
PROFILES=((2.2,2.4,1.5),(2.2,2.8,1.5),(2.2,3.2,1.5),(2.6,2.8,1.5),(2.2,2.8,1.8),(2.6,3.2,1.8))


def candidates():
    out=[]
    for gains in PROFILES:
        for scale in (.5,1.):
            p=equal_gains(2)
            for axis,l1 in zip('RPY',gains):
                p['MC_STA_L1_'+axis]=l1;p['MC_STA_L2_'+axis]*=scale
            out.append(dict(id=f'L{len(out):02d}',parameters=p))
    return out


def ablations():
    out=[]
    for axes in ('','P','RY','RPY'):
        p=equal_gains(2)
        for axis in axes:p['MC_STA_L2_'+axis]*=4
        out.append(dict(id=f'D{len(out)}',parameters=p,scaled_axes=axes))
    return out


def scalar_checks():
    configs=candidates();n=len(configs)
    gains=lambda key:np.array([[c['parameters'][f'MC_STA_{key}_{a}'] for a in 'RPY'] for c in configs])
    l1,l2,g=gains('L1'),gains('L2'),gains('G');out=[]
    for scene in SCENES:
        setting=scenario(scene,5001);div=setting['div'];h=.004
        rate=np.zeros((n,3));nu=np.zeros_like(rate);motor=np.zeros_like(rate);command=np.zeros_like(rate)
        peak=np.zeros(n);rng=np.random.Generator(np.random.PCG64(5001))
        for k in range(10000):
            t=k*h;sp=np.array([.04,.08,.12])*np.sin(2*np.pi*t/4)
            s=rate+rng.normal(0,.003*setting['gyro_density_scale'],3)-sp
            if k%div==0:
                a,nu=implicit(s,nu,h*div,l1,l2);command=np.clip(a/g,-.15,.15);nu=np.clip(nu,-3,3)
            motor=command+(motor-command)*np.exp(-h/.025)
            torque=np.zeros(3)
            if scene=='torque' and 2<=t<=12:
                torque=np.array([.004,-.004,-.002])*np.sin(np.pi*(t-2)/10)**2*np.sin(2*np.pi*.4*(t-2)+np.array(setting['torque_phases']))
            rate+=(g*motor+torque/np.array([.029125,.029125,.055225]))/setting['inertia_scale']*h
            peak=np.maximum(peak,np.max(abs(rate),axis=1))
        if not np.all(np.isfinite(rate)) or np.any(peak>=1):raise RuntimeError('Scalar numeric/boundedness failed')
        out.append(dict(scene=scene,peak_rate_by_candidate=peak.tolist()))
    return dict(scope='Numerical finite/boundedness only; no contact/liftoff proof or parameter ranking',seed=5001,cases=out)


def diagnostic_gate(data):
    expected={(f'D{i}',k) for i in range(4) for k in DIAG}
    if {(r['candidate'],r['seed']) for r in data}!=expected or len(data)!=8:return False
    baseline=[r for r in data if r['candidate']=='D0']
    return (all(r['flight_success'] for r in baseline)
            and all(r['fault_samples']==0 and r['diagnostic_missing']==0 and r['frozen_state_equal'] for r in data)
            and all(r['released_but_stationary_ground_samples']>250 and r['release_to_20mm_s']>2 for r in data)
            and all(next(r for r in data if r['candidate']=='D1' and r['seed']==k)['ground_nu_peak'][1]
                    >next(r for r in data if r['candidate']=='D0' and r['seed']==k)['ground_nu_peak'][1]*2 for k in DIAG))


def run(root,plugins,stage):
    root=root.resolve();root.mkdir(parents=True,exist_ok=True)
    if subprocess.check_output(['git','status','--porcelain'],cwd=REPO,text=True).strip():raise RuntimeError('Require clean committed source')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    f=json.loads(BASE.read_text());ref=f['selection']['1']['parameters']
    provenance=dict(source_head=head,protocol_sha256=digest(PROTOCOL),tool_sha256=digest(__file__),
        diagnosis_tool_sha256=digest(Path(__file__).with_name('diagnose_ista_takeoff.py')),
        binary_sha256=digest(REPO/'build/px4_sitl_default/bin/px4'),plugins_sha256=digest(plugins/'manifest.json'),
        baseline_sha256=digest(BASE),scope='ISTA-only extra budget, fixed ESTA; no production changes')
    immutable(root/'provenance.json',provenance)
    def job(cid,p,s,k):
        return dict(group=cid,candidate=cid,mode=p['MC_RTC_MODE'],parameters=p,scene=s,seed=k,
            formal=True,frozen_head=head,simulation_speed_requested=5.,fixed_parameters=f['fixed_parameters'])
    def fly(name,jobs):
        execute(root/name,jobs,plugins,5.);return rows(root/name)
    def finish(status,**more):
        immutable(root/'conclusion.json',dict(status=status,**more));print('ISTA_OPT02_RESULT',status,flush=True)
    if stage=='diagnosis':
        jobs=[]
        for k in DIAG:
            block=[job(c['id'],c['parameters'],'inertia',k) for c in ablations()]
            np.random.Generator(np.random.PCG64(k)).shuffle(block);jobs+=block
        data=fly('diagnosis',jobs)
        audit=[diagnose(Path(r['path']).parent) for r in data]
        immutable(root/'diagnosis_audit.json',audit)
        passed=diagnostic_gate(audit) and all(r['success'] for r in data if r['candidate']=='D0')
        immutable(root/'diagnosis_gate.json',dict(passed=passed,scope='Ground accumulation observed and baseline accepts; not proof of all causal paths'))
        print('DIAGNOSTIC_GATE',passed,flush=True);return
    if not json.loads((root/'diagnosis_gate.json').read_text())['passed']:raise RuntimeError('Diagnose before search; evidence gate failed')
    configs=candidates();immutable(root/'candidates.json',configs)
    immutable(root/'scalar.json',scalar_checks())
    refrows=fly('reference',[job('ESTA',ref,s,k) for s in SCENES for k in TRAIN])
    if not all(r['success'] for r in refrows):return finish('reference_not_accepted')
    critical=('inertia','div4')
    screen=fly('screen',[job(c['id'],c['parameters'],s,TRAIN[0]) for c in configs for s in critical])
    screenref=[r for r in refrows if r['scene'] in critical and r['seed']==TRAIN[0]]
    ranking=[]
    for c in configs:
        data=[r for r in screen if r['candidate']==c['id']]
        m=metrics(data,screenref,critical,(TRAIN[0],))
        if all(r['success'] for r in data):ranking.append((m['geometric_ratio'],c['id']))
    ids=[cid for _,cid in sorted(ranking)[:2]];immutable(root/'screen_selection.json',dict(ids=ids,ranking=ranking))
    if not ids:return finish('no_screen_survivor')
    extra=fly('training',[job(c['id'],c['parameters'],s,k) for cid in ids for c in configs if c['id']==cid
                         for s in SCENES for k in TRAIN if not(s in critical and k==TRAIN[0])])
    scores=[dict(id=cid,**metrics([r for r in screen+extra if r['candidate']==cid],refrows,seeds=TRAIN)) for cid in ids]
    immutable(root/'training_scores.json',scores)
    eligible=[r for r in scores if r['eligible']]
    if not eligible:return finish('no_training_eligible_candidate',scores=scores)
    best=min(eligible,key=lambda r:(-r['wins'],r['geometric_ratio'],r['id']))
    if not best['goal_met']:return finish('training_goal_not_met',best=best,scores=scores)
    chosen=next(c for c in configs if c['id']==best['id'])
    immutable(root/'selected.json',chosen)
    immutable(root/'VALIDATION_FREEZE.json',dict(**provenance,selected=chosen,reference=ref,seeds=VALIDATE,
        training_sha256=digest(root/'training_scores.json')))
    jobs=[]
    for s in SCENES:
        for k in VALIDATE:
            block=[job('ESTA',ref,s,k),job(chosen['id'],chosen['parameters'],s,k)]
            np.random.Generator(np.random.PCG64(k+SCENES.index(s)*10000)).shuffle(block);jobs+=block
    val=fly('validation',jobs)
    comparison=compare_final([r for r in val if r['mode']==2],[r for r in val if r['mode']==1],VALIDATE)
    immutable(root/'validation_comparison.json',comparison)
    finish('validation_goal_met' if comparison.get('goal_met') else 'validation_goal_not_met',selected=chosen,comparison=comparison)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=('diagnosis','search'));p.add_argument('--output',required=True,type=Path);p.add_argument('--plugins',required=True,type=Path)
    a=p.parse_args();run(a.output,a.plugins.resolve(),a.stage)
