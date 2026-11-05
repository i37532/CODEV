#!/usr/bin/env python3
"""Immutable job manifest, sequential instances, one attempt/job, explicit resume.

Flight failures remain in the denominator; never retry or overwrite. Unexpected
infrastructure/data quality failures halt the batch for investigation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from m10_design import candidate, equal_gains, formal_jobs, select, TRAIN_SEEDS, PILOT_SEEDS, SCENES

REPO=Path(__file__).resolve().parents[3]
SCRIPTS=Path(__file__).resolve().parent


def execute(root, jobs, plugins, speed):
    root.mkdir(parents=True,exist_ok=True)
    manifest=root/'jobs.json'
    if manifest.exists():
        if json.loads(manifest.read_text())!=jobs:raise RuntimeError('Cannot mutate job manifest on resume')
    else:manifest.write_text(json.dumps(jobs,indent=2)+'\n')
    env=os.environ.copy()
    for key in tuple(env):
        if key.startswith(tuple(f'M{i:02d}_' for i in range(11))):env.pop(key)
    env['PYTHONPATH']=str(REPO/'.px4-python')+':/home/yr/Desktop/codev doc/experiments/M00-20260912/python'
    env['PATH']=str(REPO/'.px4-python/bin')+':'+env['PATH']
    env.update(M10_PLUGINS=str(plugins),M10_SPEED=str(speed),PYTHONDONTWRITEBYTECODE='1')
    rows=[]
    for number,job in enumerate(jobs):
        label=f"{number:04d}_{job.get('group','train')}_m{job['mode']}_{job['scene']}_s{job['seed']}"
        run=root/label;record=root/(label+'.execution.json')
        if record.exists():
            previous=json.loads(record.read_text())
            adjudication=root/(label+'.adjudication.json')
            reviewed=json.loads(adjudication.read_text()) if adjudication.exists() else {}
            retained_gap=reviewed.get('disposition')=='retain_failed_attempt_and_continue' and reviewed.get('retained_prearm_gap')
            if previous.get('halt') and not (reviewed.get('analysis_resolved_without_reflight') or retained_gap):
                raise RuntimeError('Previously halted job; inspect, do not silently skip: '+label)
            if reviewed and hashlib.sha256((run/'m10_analysis.json').read_bytes()).hexdigest()!=reviewed['new_analysis_sha256']:
                raise RuntimeError('Adjudicated analysis fingerprint changed: '+label)
            rows.append(json.loads((run/'m10_analysis.json').read_text()));continue
        if run.exists():raise RuntimeError('Interrupted job needs explicit adjudication, not automatic repeat: '+label)
        jobfile=root/(label+'.job.json');jobfile.write_text(json.dumps(job,indent=2)+'\n')
        env['M10_JOB']=str(jobfile)
        started=time.time()
        print('START',number+1,'/',len(jobs),label,flush=True)
        commands=[]
        for name,argv in [('flight',[sys.executable,str(SCRIPTS/'run_m10.py'),'--output',str(run)]),
                          ('analysis',[sys.executable,str(SCRIPTS/'analyze_m10.py'),str(run)])]:
            with (root/(label+'.'+name+'.log')).open('w') as stream:
                r=subprocess.run(argv,cwd=REPO,env=env,stdout=stream,stderr=subprocess.STDOUT)
            commands.append(dict(name=name,command=argv,returncode=r.returncode))
        analysis=run/'m10_analysis.json'
        row=json.loads(analysis.read_text()) if analysis.exists() else dict(success=False,error='No analysis generated')
        halt=not analysis.exists() or row.get('failure_class') in ('analysis_or_data_quality','infrastructure')
        if job.get('formal') and 'binary_sha256' in row:
            anchor=dict(frozen_head=job['frozen_head'],source_head=row['source_head'],binary_sha256=row['binary_sha256'],
                        plugins_manifest_sha256=hashlib.sha256((plugins/'manifest.json').read_bytes()).hexdigest())
            anchor_file=root/'runtime_anchor.json'
            if anchor_file.exists() and json.loads(anchor_file.read_text())!=anchor:
                halt=True
                (root/(label+'.runtime_drift.json')).write_text(json.dumps(anchor,indent=2)+'\n')
            elif not anchor_file.exists():anchor_file.write_text(json.dumps(anchor,indent=2)+'\n')
        entry=dict(job=job,commands=commands,wall_seconds=time.time()-started,halt=halt,success=row['success'])
        record.write_text(json.dumps(entry,indent=2)+'\n')
        rows.append(row)
        (root/'summary.json').write_text(json.dumps(dict(planned=len(jobs),attempted=len(rows),runs=rows),indent=2)+'\n')
        print('END',label,'success=',row['success'],'wall=',round(entry['wall_seconds'],1),flush=True)
        if halt:raise RuntimeError('Infrastructure/analysis halt, retained '+label)
    return rows


def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=('smoke','train','pilot','formal'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--plugins',type=Path,required=True)
    p.add_argument('--frozen',type=Path);p.add_argument('--speed',type=float,default=5)
    a=p.parse_args();jobs=[]
    frozen=json.loads(a.frozen.read_text()) if a.frozen else None
    if a.stage=='smoke':
        jobs=[dict(mode=0,scene='nominal',seed=1101,parameters=candidate(0,1),candidate=1)]
    elif a.stage=='train':
        for scene in ('nominal','torque'):
            for seed in TRAIN_SEEDS:
                for index in range(3):
                    for mode in (0,1,2):jobs.append(dict(mode=mode,candidate=index,scene=scene,seed=seed,parameters=candidate(mode,index)))
    elif a.stage=='pilot':
        if frozen is None:raise ValueError('--frozen selected training parameters required')
        for scene in SCENES:
            for seed in PILOT_SEEDS:
                for group,modes in [('A',(1,2)),('B',(0,1,2))]:
                    for mode in modes:
                        params=equal_gains(mode) if group=='A' else frozen['selection'][str(mode)]['parameters']
                        jobs.append(dict(mode=mode,group=group,scene=scene,seed=seed,parameters=params))
    else:
        if frozen is None:raise ValueError('--frozen required')
        if a.speed!=frozen['simulation_speed_requested']:raise RuntimeError('Changed frozen lockstep speed request')
        if subprocess.check_output(['git','status','--porcelain'],cwd=REPO,text=True).strip():raise RuntimeError('Dirty formal source')
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
        freeze_path=str(a.frozen.resolve().relative_to(REPO))
        subprocess.run(['git','ls-files','--error-unmatch','--',freeze_path],cwd=REPO,check=True,stdout=subprocess.DEVNULL)
        freeze_commit=subprocess.check_output(['git','log','-1','--format=%H','--',freeze_path],cwd=REPO,text=True).strip()
        if head!=freeze_commit:raise RuntimeError('Run formal batch on the commit that froze this tracked parameter artifact')
        jobs=formal_jobs(frozen)
        for job in jobs:job.update(formal=True,frozen_head=head)
    rows=execute(a.output.resolve(),jobs,a.plugins.resolve(),a.speed)
    if a.stage=='train':(a.output/'selected.json').write_text(json.dumps(select(rows),indent=2)+'\n')


if __name__=='__main__':main()
