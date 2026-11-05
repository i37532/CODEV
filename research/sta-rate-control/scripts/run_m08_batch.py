#!/usr/bin/env python3
"""Guarded nine-flight final series. Stops on any runner/ULog/ratio failure.

Requires successful roll and R/P gates, preserves all runs, no retries/picking.
No Git mutation or push. Each flight uses the existing project SITL launcher.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--roll-gate',type=Path,required=True);p.add_argument('--rp-gate',type=Path,required=True)
    args=p.parse_args();repo=Path(__file__).resolve().parents[3]
    for path,axes in [(args.roll_gate,1),(args.rp_gate,3)]:
        gate=json.loads(path.read_text())
        if not gate['success'] or gate['stage_axes']!=axes:raise RuntimeError('Staged precursor not accepted')
        for name,expected in gate['input_hashes'].items():
            if digest(Path(name))!=expected:raise RuntimeError('Stage evidence drift')
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    env=os.environ.copy();env.update(PYTHONPATH=str(repo/'.px4-python')+':/home/yr/Desktop/codev doc/experiments/M00-20260912/python',
                                    PATH=str(repo/'.px4-python/bin')+':'+env['PATH'],PYTHONDONTWRITEBYTECODE='1',M08_SCENE='rpy')
    tracked=subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=repo,text=True).splitlines()
    untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=repo,text=True).splitlines()
    source={name:digest(repo/name) for name in sorted(set(tracked+untracked)) if (repo/name).is_file()}
    for name in source:
        target=out/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(repo/name,target)
    evidence=dict(success=False,source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),
                  source_files=source,firmware_sha256=digest(repo/'build/px4_sitl_default/bin/px4'),
                  gates={str(path.resolve()):digest(path) for path in (args.roll_gate,args.rp_gate)},commands=[],runs=[])
    def run(name,argv,run_env=env):
        print('RUN',name,flush=True)
        with (out/(name+'.log')).open('w') as stream:
            r=subprocess.run(argv,cwd=repo,env=run_env,stdout=stream,stderr=subprocess.STDOUT)
        evidence['commands'].append(dict(name=name,argv=argv,returncode=r.returncode))
        (out/'series.json').write_text(json.dumps(evidence,indent=2)+'\n')
        print('EXIT',name,r.returncode,flush=True)
        if r.returncode:raise RuntimeError(name+' failed; retained data, no automatic retry')
    try:
        groups=[]
        for mode,label,config in [(0,'pid','iris_pid'),(1,'esta','iris_esta_rpy'),(2,'ista','iris_ista_rpy_candidate02')]:
            group=[];flight_env=dict(env,M08_MODE=str(mode),M08_CONFIG=str(repo/'research/sta-rate-control/m08'/(config+'.json')))
            for repeat in range(1,4):
                name=f'{label}{repeat:02d}';folder=out/name
                run(name+'_run',[sys.executable,'research/sta-rate-control/scripts/run_m08.py','--output',str(folder)],flight_env)
                run(name+'_analysis',[sys.executable,'research/sta-rate-control/scripts/analyze_m08.py',str(folder)])
                evidence['runs'].append(str(folder));group.append(str(folder))
                if digest(repo/'build/px4_sitl_default/bin/px4')!=evidence['firmware_sha256']:raise RuntimeError('Binary changed')
                if any(digest(repo/name)!=sha for name,sha in source.items()):raise RuntimeError('Source changed during series')
            groups.append(group)
        run('comparison',[sys.executable,'research/sta-rate-control/scripts/compare_m08.py',
                          '--pid',*groups[0],'--esta',*groups[1],'--ista',*groups[2],'--output',str(out/'comparison.json')])
        evidence['success']=True
    except Exception as exc:
        evidence['error']=repr(exc);raise
    finally:
        (out/'series.json').write_text(json.dumps(evidence,indent=2)+'\n')


if __name__=='__main__':main()
