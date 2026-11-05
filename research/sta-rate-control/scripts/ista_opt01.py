#!/usr/bin/env python3
"""Preregistered, bounded ISTA-only search; untouched M10 flight/analysis path."""
import argparse
import copy
import hashlib
import itertools
import json
import subprocess
from pathlib import Path
import numpy as np
from batch_m10 import execute, REPO
from m10_design import SCENES, scenario, equal_gains
from summarize_m10 import paired_interval

BASE = REPO / 'research/sta-rate-control/m10/FROZEN.json'
PROTOCOL = REPO / 'research/sta-rate-control/ista_opt01/PROTOCOL_CN.md'
TRAIN = (4101, 4102)
VALIDATE = (4201, 4202, 4203)
HOLDOUT = tuple(range(4301, 4321))
L1 = (1.2, 1.6, 2., 2.4, 2.8, 3.2)
L2 = (.02, .05, .1, .2, .4, .8, 1.6)


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def immutable(path, data):
    path = Path(path)
    data = json.loads(json.dumps(data, allow_nan=False))
    if path.exists():
        if json.loads(path.read_text()) != data:
            raise RuntimeError('Immutable artifact differs: ' + str(path))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def implicit(s, old, h, l1, l2):
    target = s + h*old
    sign = np.sign(target)
    q = h*h*l2
    mag = np.maximum(abs(target)-q, 0)
    root = 2*mag / (np.sqrt((h*l1)**2 + 4*mag) + h*l1)
    sliding = abs(target) <= q
    nu = np.where(sliding, -s/h, old-h*l2*sign)
    return np.where(sliding, nu, -l1*root*sign+nu), nu


def proxy():
    """Batch axis-grid proxy with shared noise per scene, not production proof."""
    f = json.loads(BASE.read_text());ref = f['selection']['1']['parameters']
    pairs = list(itertools.product(L1, L2));n = len(pairs)
    l1 = np.tile(np.array([x[0] for x in pairs])[:, None], (1, 3))
    l2 = np.tile(np.array([x[1] for x in pairs])[:, None], (1, 3))
    l1 = np.vstack((l1, [ref['MC_STA_L1_'+a] for a in 'RPY']))
    l2 = np.vstack((l2, [ref['MC_STA_L2_'+a] for a in 'RPY']))
    g = np.array([ref['MC_STA_G_'+a] for a in 'RPY'])
    errors = []
    for scene in SCENES:
        setting = scenario(scene, 4001);div = setting['div'];h = .004
        rate = np.zeros((n+1, 3));nu = np.zeros_like(rate);motor = np.zeros_like(rate)
        command = np.zeros_like(rate);sums = np.zeros_like(rate);peak = 0.
        rng = np.random.Generator(np.random.PCG64(4001))
        for k in range(10000):
            t = k*h;sp = np.array([.04,.08,.12])*np.sin(2*np.pi*t/4)
            measured = rate+rng.normal(0, .003*setting['gyro_density_scale'], 3)
            s = measured-sp
            if k % div == 0:
                dt = h*div
                a, proposed = implicit(s, nu, dt, l1, l2)
                a[-1] = -l1[-1]*np.sqrt(abs(s[-1]))*np.sign(s[-1])+nu[-1]
                proposed[-1] = nu[-1]-dt*l2[-1]*np.sign(s[-1])
                command = np.clip(a/g, -.15, .15);nu = np.clip(proposed, -3, 3)
            motor = command+(motor-command)*np.exp(-h/.025)
            torque = np.zeros(3)
            if scene == 'torque' and 2 <= t <= 12:
                torque = np.array([.004,-.004,-.002])*np.sin(np.pi*(t-2)/10)**2*np.sin(2*np.pi*.4*(t-2)+np.array(setting['torque_phases']))
            rate += (g*motor+torque/np.array([.029125,.029125,.055225]))/setting['inertia_scale']*h
            sums += s*s;peak = max(peak,float(np.max(abs(rate))))
        if not np.all(np.isfinite(sums)) or peak > 1:
            raise RuntimeError('Proxy numerical/rate guard failed')
        errors.append(np.sqrt(sums/10000))
    errors = np.array(errors)
    scores = np.exp(np.mean(np.log(errors[:,:n]/errors[:,-1:, :]),axis=0))
    best = [sorted(range(n),key=lambda i:(scores[i,a],i))[:2] for a in range(3)]
    candidates = []
    def add(p, origin):
        p=copy.deepcopy(p);p['MC_RTC_MODE']=2;p['MC_STA_AXES']=7;p['MC_RTC_DIV']=1
        if any(c['parameters']==p for c in candidates):return
        candidates.append(dict(id=f'C{len(candidates):02d}',parameters=p,origin=origin))
    add(f['selection']['2']['parameters'], 'Original M10 B/ISTA anchor')
    base = equal_gains(2);add(base,'M10 A equal-gain ISTA anchor')
    for scale in (4,16):
        p=copy.deepcopy(base)
        for a in 'RPY':p['MC_STA_L2_'+a]*=scale
        add(p,f'Prespecified equal-gain lambda2 x{scale} anchor')
    for indices in itertools.product(*best):
        p=copy.deepcopy(base)
        for a,i in zip('RPY',indices):p['MC_STA_L1_'+a],p['MC_STA_L2_'+a]=pairs[i]
        add(p,'Independent axis proxy top-two combination '+str(indices))
    assert len(candidates)<=12
    return dict(scope='Independent simplified rate proxy, NOT PX4 takeoff/production protection',
                seed=4001,pairs=pairs,scenes=SCENES,rmse=errors.tolist(),scores=scores.tolist(),
                best_axis_indices=best,candidates=candidates)


def labels(jobs):
    return [f"{i:04d}_{j['group']}_m{j['mode']}_{j['scene']}_s{j['seed']}" for i,j in enumerate(jobs)]


def rows(root):
    jobs=json.loads((root/'jobs.json').read_text());out=[]
    for name in labels(jobs):
        p=root/name/'m10_analysis.json';r=json.loads(p.read_text());r['path']=str(p);out.append(r)
    return out


def metrics(data, reference, scenes=SCENES, seeds=TRAIN):
    expected={(s,k) for s in scenes for k in seeds}
    def keyed(v):
        d={(x['scene'],x['seed']):x for x in v}
        if len(d)!=len(v) or set(d)!=expected:raise ValueError('Incomplete or duplicate comparison')
        return d
    a=keyed(data);b=keyed(reference)
    if not all(x['success'] for x in list(a.values())+list(b.values())):
        return dict(eligible=False,reason='At least one nonaccepted attempt; no imputation')
    for x in list(a.values())+list(b.values()):
        v=np.asarray(x['rmse_tracking'])
        if v.shape != (3,) or not np.all(np.isfinite(v)) or np.any(v<=0):
            raise ValueError('Invalid/nonpositive three-axis sample metric')
    axis=[];ratios=[]
    for s in scenes:
        ar=np.mean([a[s,k]['rmse_tracking'] for k in seeds],axis=0)
        br=np.mean([b[s,k]['rmse_tracking'] for k in seeds],axis=0)
        if ar.shape != (3,) or br.shape != (3,) or not np.all(np.isfinite([ar,br])) or np.any(ar<=0) or np.any(br<=0):
            raise ValueError('Invalid/nonpositive three-axis metric')
        axis.append((ar/br).tolist());ratios.append(float(ar.mean()/br.mean()))
    worst=max(ratios);max_axis=float(np.max(axis));eligible=worst<=1.10 and max_axis<=1.25
    return dict(eligible=eligible,scenes=list(scenes),ratios=ratios,axis_ratios=axis,
                wins=sum(x<=.99 for x in ratios),geometric_ratio=float(np.exp(np.mean(np.log(ratios)))),
                worst_ratio=worst,max_axis_ratio=max_axis,goal_met=eligible and sum(x<=.99 for x in ratios)>=4)


def compare_final(data, ref, seeds):
    result=metrics(data,ref,seeds=seeds);result['contrasts']=[]
    for scene in SCENES:
        a={x['seed']:x for x in data if x['scene']==scene and x['success']}
        b={x['seed']:x for x in ref if x['scene']==scene and x['success']}
        paired=sorted(set(a)&set(b))
        c=dict(scene=scene,paired_seeds=paired,interpretation='ISTA minus fixed ESTA; conditional on both accepted')
        if len(paired)>=2:
            c.update(paired_interval([np.mean(a[k]['rmse_tracking'])-np.mean(b[k]['rmse_tracking']) for k in paired],family=6))
        result['contrasts'].append(c)
    result['ista_accepted']=sum(x['success'] for x in data);result['esta_accepted']=sum(x['success'] for x in ref)
    result['attempts_per_controller']=len(data)
    return result


def run(root, plugins):
    root=root.resolve();root.mkdir(parents=True,exist_ok=True)
    if subprocess.check_output(['git','status','--porcelain'],cwd=REPO,text=True).strip():raise RuntimeError('Require clean committed search source')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    f=json.loads(BASE.read_text());ref=f['selection']['1']['parameters']
    provenance=dict(source_head=head,protocol_sha256=digest(PROTOCOL),tool_sha256=digest(__file__),
                    binary_sha256=digest(REPO/'build/px4_sitl_default/bin/px4'),plugins_sha256=digest(plugins/'manifest.json'),
                    baseline_sha256=digest(BASE),scope='ISTA-only search; fixed ESTA; not equal tuning budget')
    immutable(root/'provenance.json',provenance)
    pp=root/'proxy.json'
    if not pp.exists():immutable(pp,proxy())
    candidates=json.loads(pp.read_text())['candidates'];immutable(root/'candidates.json',candidates)
    def job(cid,params,scene,seed):
        return dict(group=cid,candidate=cid,mode=params['MC_RTC_MODE'],parameters=params,scene=scene,seed=seed,
                    formal=True,frozen_head=head,simulation_speed_requested=5.,fixed_parameters=f['fixed_parameters'])
    def fly(stage,jobs):
        # Original execute checks immutable manifests and preserves/halt failures.
        execute(root/stage,jobs,plugins,5.)
        return rows(root/stage)
    def conclusion(status,**values):
        immutable(root/'conclusion.json',dict(status=status,**values))
        print('ISTA_OPT01_RESULT',status,flush=True)
    refrows=fly('reference',[job('ESTA',ref,s,k) for s in SCENES for k in TRAIN])
    if not all(x['success'] for x in refrows):return conclusion('reference_not_accepted')
    critical=('inertia','div4')
    screenjobs=[job(c['id'],c['parameters'],s,4101) for c in candidates for s in critical]
    screen=fly('screen',screenjobs)
    screenref=[x for x in refrows if x['scene'] in critical and x['seed']==4101]
    ranking=[]
    for c in candidates:
        v=[x for x in screen if x['candidate']==c['id']]
        m=metrics(v,screenref,critical,(4101,))
        # Screening only demands flight/analysis success; training tests full degradation gates.
        if all(x['success'] for x in v):ranking.append((m['geometric_ratio'],c['id']))
    ids=[cid for _,cid in sorted(ranking)[:3]];immutable(root/'screen_selection.json',dict(ids=ids,ranking=ranking))
    if not ids:return conclusion('no_screen_survivor')
    selected=[c for cid in ids for c in candidates if c['id']==cid]
    trainjobs=[job(c['id'],c['parameters'],s,k) for c in selected for s in SCENES for k in TRAIN if not(s in critical and k==4101)]
    extra=fly('training',trainjobs)
    scores=[]
    for c in selected:
        v=[x for x in screen+extra if x['candidate']==c['id']]
        scores.append(dict(id=c['id'],**metrics(v,refrows)))
    immutable(root/'training_scores.json',scores)
    eligible=[x for x in scores if x['eligible']]
    if not eligible:return conclusion('no_training_eligible_candidate',scores=scores)
    best=min(eligible,key=lambda x:(-x['wins'],x['geometric_ratio'],x['id']))
    if not best['goal_met']:return conclusion('training_goal_not_met',best=best,scores=scores)
    chosen=next(c for c in candidates if c['id']==best['id']);immutable(root/'selected.json',chosen)
    def paired_jobs(seeds):
        out=[]
        for s in SCENES:
            for k in seeds:
                block=[job('ESTA',ref,s,k),job(chosen['id'],chosen['parameters'],s,k)]
                np.random.Generator(np.random.PCG64(k+SCENES.index(s)*10000)).shuffle(block);out+=block
        return out
    val=fly('validation',paired_jobs(VALIDATE));a=[x for x in val if x['mode']==2];b=[x for x in val if x['mode']==1]
    validation=compare_final(a,b,VALIDATE);immutable(root/'validation_comparison.json',validation)
    if not validation.get('goal_met',False):return conclusion('validation_goal_not_met',selected=chosen,validation=validation)
    immutable(root/'FINAL_FREEZE.json',dict(**provenance,selected=chosen,reference=ref,seeds=HOLDOUT,
        training_sha256=digest(root/'training_scores.json'),validation_sha256=digest(root/'validation_comparison.json')))
    final=fly('holdout',paired_jobs(HOLDOUT));a=[x for x in final if x['mode']==2];b=[x for x in final if x['mode']==1]
    comparison=compare_final(a,b,HOLDOUT);immutable(root/'holdout_comparison.json',comparison)
    conclusion('holdout_goal_met' if comparison.get('goal_met',False) else 'holdout_goal_not_met',selected=chosen,comparison=comparison)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);p.add_argument('--plugins',required=True,type=Path)
    a=p.parse_args();run(a.output,a.plugins.resolve())
