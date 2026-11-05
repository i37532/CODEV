#!/usr/bin/env python3
"""Default: verify a 17-job plan. --assess-first is offline; --execute flies."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from prepare_rc_continuation import prepare, ROOT
from design_rc import REPO, HERE, load
from summary_rc import summarize

ANALYZER=HERE.parent/'i05/analyze.py'
RUNNER=HERE.parent/'i05/run.py'
FIRST=ROOT/'0000_I05RC_d1_esta_m1_s7001'
BASE='0ca14b4b86a60c4f32f9426a9e1026fe831636b0'


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2);f.write('\n')


def plan(head):
    ledger=json.loads((HERE/'RC_CONTINUATION_LEDGER.json').read_text())
    if ledger!=prepare():raise ValueError('Continuation ledger drift')
    original=json.loads((ROOT/'jobs.json').read_text());pending=[]
    for entry in ledger['pending']:
        index=entry['original_index'];job=copy.deepcopy(original[index])
        job.update(frozen_head=head,analysis_protocol='amended-v1',original_index=index)
        pending.append(job)
    return ledger,pending


def gate(rows,div):
    result=summarize(rows)
    errors=[v for v in result['violations'] if v.startswith((str(div)+':','pair:'+str(div)+':','invalid:'+str(div)+':')) or v=='median:'+str(div)]
    if len([r for r in rows if r.get('divisor')==div])!=6:errors.append('divisor_count')
    return dict(divisor=div,success=not errors,violations=errors,metrics=result['by_divisor'][str(div)])


def execute_pending(pending,first,run_job,record,check_gate=gate):
    if not first.get('success'):raise ValueError('First amended assessment failed')
    if [j['original_index'] for j in pending]!=list(range(1,18)):raise ValueError('Pending indices must be exactly 1..17')
    rows=[first]
    for job in pending:
        row=run_job(job);rows.append(row);record('attempt',rows)
        if not row.get('success'):raise RuntimeError('Single attempt failed; stopped')
        if len(rows)%6==0:
            result=check_gate(rows,job['divisor']);record('gate',result)
            if not result['success']:raise RuntimeError('Divisor gate failed; stopped')
    return rows


def preflight():
    if subprocess.check_output(['git','status','--porcelain'],cwd=REPO,text=True).strip():
        raise ValueError('Clean committed source required')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    changed=subprocess.check_output(['git','diff','--name-only',BASE,head],cwd=REPO,text=True).splitlines()
    if any(not p.startswith('research/sta-rate-control/') for p in changed):
        raise ValueError('Production/build/model drift from original first flight')
    submodules=subprocess.check_output(['git','submodule','status','--recursive'],cwd=REPO,text=True)
    if any(line.startswith(('+','-','U')) for line in submodules.splitlines()):raise ValueError('Submodule drift')
    load() # frozen plugin manifest, model baseline and prior gate hashes
    return head,submodules


def main():
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group()
    g.add_argument('--assess-first',type=Path,metavar='NEW_DIRECTORY')
    g.add_argument('--execute',action='store_true')
    p.add_argument('--first-assessment',type=Path)
    a=p.parse_args();head,submodules=preflight();ledger,pending=plan(head)
    env=os.environ.copy();env.update(PYTHONPATH=str(REPO/'.px4-python')+':/home/yr/Desktop/codev doc/experiments/M00-20260912/python',
        PATH=str(REPO/'.px4-python/bin')+':'+env['PATH'],PYTHONDONTWRITEBYTECODE='1',M10_SPEED='5',M10_PLUGINS=str(load()[2]))
    if a.assess_first:
        return subprocess.call([sys.executable,str(ANALYZER),str(FIRST),'--protocol','amended-v1','--output',str(a.assess_first)],cwd=REPO,env=env)
    if not a.execute:
        print(json.dumps(dict(head=head,pending_count=len(pending),pending=[{k:j[k] for k in ('original_index','divisor','algorithm','seed')} for j in pending]),indent=2));return 0
    if a.first_assessment is None:raise ValueError('--first-assessment is required for execution')
    first=json.loads((a.first_assessment/'i05_analysis.json').read_text())
    if not first.get('success') or first.get('analysis_protocol')!='amended-v1':raise ValueError('Require successful amended first assessment')
    provenance=first['provenance']
    if provenance['analyzer_worktree']:raise ValueError('First assessment must use clean analyzer commit')
    subprocess.run(['git','merge-base','--is-ancestor',provenance['analyzer_head'],head],cwd=REPO,check=True)
    since_assessment=subprocess.check_output(['git','diff','--name-only',provenance['analyzer_head'],head],cwd=REPO,text=True).splitlines()
    if any(not p.startswith('research/sta-rate-control/reports/') for p in since_assessment):
        raise ValueError('Analyzer/protocol changed since first assessment; reassess offline at this commit')
    if provenance['original_run']!=str(FIRST) or provenance['original_acceptance'] is not False:raise ValueError('Wrong original first attempt')
    for name,value in provenance['input_sha256'].items():
        if digest(FIRST/name)!=value:raise ValueError('Original input changed')
    if digest(FIRST/'i05_analysis.json')!=provenance['original_analysis_sha256']:raise ValueError('Original analysis changed')
    if (first['algorithm'],first['seed'],first['divisor'],first['source_head'])!=('esta',7001,1,BASE):raise ValueError('Wrong first identity')
    if digest(first['ulog'])!=first['ulog_sha256']:raise ValueError('Original ULog changed')
    root=Path(ledger['continuation_directory']);root.mkdir(parents=True,exist_ok=False)
    write(root/'jobs.json',pending)
    # Build at the bound commit, then freeze binary before any launcher call.
    with (root/'build.log').open('x') as log:
        subprocess.run(['make','px4_sitl_default'],cwd=REPO,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    binary=digest(REPO/'build/px4_sitl_default/bin/px4')
    write(root/'binding.json',dict(execution_source_head=head,binary_sha256=binary,submodules=submodules,
        first_assessment_sha256=digest(a.first_assessment/'i05_analysis.json'),first_source_head=first['source_head'],
        first_binary_sha256=first['binary_sha256'],ledger_sha256=digest(HERE/'RC_CONTINUATION_LEDGER.json'),
        compiler=subprocess.check_output(['c++','--version'],text=True),source_changes='research-only; original and new binaries have separately recorded version metadata'))
    write(root/'first_assessment.json',first)
    def run_job(job):
        n=job['original_index'];run=root/f'{n:04d}_d{job["divisor"]}_{job["algorithm"]}_s{job["seed"]}'
        jf=root/f'{n:04d}.job.json';write(jf,job);local=dict(env,M10_JOB=str(jf))
        write(root/f'{n:04d}.started.json',job);print('START',n,'/ 17',flush=True)
        with (root/f'{n:04d}.flight.log').open('x') as log:
            rc=subprocess.call([sys.executable,str(RUNNER),'--output',str(run)],cwd=REPO,env=local,stdout=log,stderr=subprocess.STDOUT)
        result=json.loads((run/'result.json').read_text()) if (run/'result.json').exists() else {}
        if rc or not result.get('success') or result.get('source_head')!=head or result.get('binary_sha256')!=binary:
            return dict(success=False,original_index=n,algorithm=job['algorithm'],divisor=job['divisor'],seed=job['seed'],error='Flight/process/source/binary check failed',returncode=rc)
        output=root/f'{n:04d}.analysis'
        with (root/f'{n:04d}.analysis.log').open('x') as log:
            rc=subprocess.call([sys.executable,str(ANALYZER),str(run),'--protocol','amended-v1','--output',str(output)],cwd=REPO,env=local,stdout=log,stderr=subprocess.STDOUT)
        row=json.loads((output/'i05_analysis.json').read_text()) if (output/'i05_analysis.json').exists() else dict(success=False,error='No analysis result')
        if rc:row['success']=False
        row.update(original_index=n,original_acceptance=None,original_acceptance_note='Strict criterion not retrospectively redefined; amended analysis used')
        print('END',n,row['success'],flush=True);return row
    def record(kind,value):
        name=f'after_{len(value)-1:04d}.json' if kind=='attempt' else f'gate_div{value["divisor"]}.json'
        write(root/name,value)
    try:
        rows=execute_pending(pending,first,run_job,record)
        summary=summarize(rows);summary.update(analysis_protocol='amended-v1',original_first_acceptance=False,
            execution_source_head=head,continuation_attempts=17)
        write(root/'summary.json',summary);return 0 if summary['success'] else 1
    except BaseException as exc:
        write(root/'stopped.json',dict(error=repr(exc),no_retry=True));raise


if __name__=='__main__':raise SystemExit(main())
