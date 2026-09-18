#!/usr/bin/env python3
import argparse, hashlib, json, os, subprocess, sys, time
from pathlib import Path
from analyze import summarize
from design import HERE,REPO,jobs,load

def main():
    p=argparse.ArgumentParser();p.add_argument('--subgate',choices=('A',),required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if subprocess.check_output(['git','status','--porcelain'],cwd=REPO,text=True).strip(): raise RuntimeError('Clean worktree required')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(); frozen_path=HERE/f'FROZEN_{a.subgate}.json'
    if subprocess.check_output(['git','log','-1','--format=%H','--',str(frozen_path.relative_to(REPO))],cwd=REPO,text=True).strip()!=head: raise RuntimeError('Run only frozen subgate HEAD')
    frozen,manifest=jobs(head,a.subgate);_,_,plugins=load(a.subgate);root=a.output.resolve();root.mkdir(parents=True,exist_ok=False)
    (root/'jobs.json').write_text(json.dumps(manifest,indent=2)+'\n');env=os.environ.copy()
    env.update(PYTHONPATH=str(REPO/'.px4-python')+':/home/yr/Desktop/codev doc/experiments/M00-20260912/python',PATH=str(REPO/'.px4-python/bin')+':'+env['PATH'],M10_PLUGINS=str(plugins),M10_SPEED=str(frozen['simulation_speed_requested']),PYTHONDONTWRITEBYTECODE='1')
    rows=[];anchor=None
    for n,job in enumerate(manifest):
        label=f"{n:04d}_I05{a.subgate}_{job['algorithm']}_m{job['mode']}_s{job['seed']}";run=root/label;jf=root/(label+'.job.json');jf.write_text(json.dumps(job,indent=2)+'\n');env['M10_JOB']=str(jf)
        commands=[];started=time.time();print('START',n+1,'/',len(manifest),label,flush=True)
        for name,argv in [('flight',[sys.executable,str(HERE/'run.py'),'--output',str(run)]),('analysis',[sys.executable,str(HERE/'analyze.py'),str(run)])]:
            with (root/(label+'.'+name+'.log')).open('x') as stream: c=subprocess.run(argv,cwd=REPO,env=env,stdout=stream,stderr=subprocess.STDOUT)
            commands.append(dict(name=name,returncode=c.returncode,command=argv))
            if name=='flight' and not (run/'result.json').exists(): break
        ap=run/'i05_analysis.json';row=json.loads(ap.read_text()) if ap.exists() else dict(success=False,algorithm=job['algorithm'],seed=job['seed'],failure_class='infrastructure',error='No analysis')
        now=(row.get('source_head'),row.get('binary_sha256'))
        if anchor is None and all(now): anchor=now
        elif anchor and now!=anchor: row.update(success=False,failure_class='infrastructure',error='Runtime source/binary changed')
        halt=row.get('failure_class') in ('infrastructure','analysis_or_data_quality');record=dict(job=job,commands=commands,wall_seconds=time.time()-started,success=row.get('success',False),halt=halt)
        (root/(label+'.execution.json')).write_text(json.dumps(record,indent=2)+'\n');rows.append(row);(root/'progress.json').write_text(json.dumps(dict(rows=rows),indent=2)+'\n')
        print('END',label,'success=',row.get('success'),'wall=',round(record['wall_seconds'],1),flush=True)
        if halt: raise RuntimeError('Infrastructure/data halt retained: '+label)
    summary=summarize(rows,a.subgate);summary.update(source_head=head,binary_sha256=anchor[1] if anchor else None,frozen_sha256=hashlib.sha256(frozen_path.read_bytes()).hexdigest())
    (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:summary[k] for k in ('planned','attempted','accepted','success','violations')},indent=2));raise SystemExit(0 if summary['success'] else 1)
if __name__=='__main__':main()
