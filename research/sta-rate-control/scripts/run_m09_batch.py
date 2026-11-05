#!/usr/bin/env python3
"""Nine M09 development cells, one flight per mode/divisor; NOT M10 repetitions.
Stop on first failure. Preserve every result. No Git writes or push.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    repo=Path(__file__).resolve().parents[3];out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    env=os.environ.copy();env.update(PYTHONPATH=str(repo/'.px4-python')+':/home/yr/Desktop/codev doc/experiments/M00-20260912/python',
                                    PATH=str(repo/'.px4-python/bin')+':'+env['PATH'],PYTHONDONTWRITEBYTECODE='1')
    for key in tuple(env):
        if key.startswith(('M04_','M05_','M06_','M08_','M09_')):env.pop(key)
    tracked=subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=repo,text=True).splitlines()
    untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=repo,text=True).splitlines()
    files={name:sha(repo/name) for name in sorted(set(tracked+untracked)) if (repo/name).is_file()}
    for name in files:
        target=out/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(repo/name,target)
    e=dict(success=False,source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),
           files=files,firmware_sha256=sha(repo/'build/px4_sitl_default/bin/px4'),commands=[],runs=[])
    (out/'submodules.txt').write_text(subprocess.check_output(['git','submodule','status','--recursive'],cwd=repo,text=True))
    def run(name,argv,run_env=env):
        print('RUN',name,flush=True)
        with (out/(name+'.log')).open('w') as stream:
            r=subprocess.run(argv,cwd=repo,env=run_env,stdout=stream,stderr=subprocess.STDOUT)
        e['commands'].append(dict(name=name,argv=argv,returncode=r.returncode));save()
        print('EXIT',name,r.returncode,flush=True)
        if r.returncode:raise RuntimeError(name+' failed; no retry/next cell')
    def save(): (out/'series.json').write_text(json.dumps(e,indent=2)+'\n')
    try:
        for mode,label in enumerate(('pid','esta','ista')):
            for div in (1,2,4):
                name=f'{label}_div{div}';folder=out/name
                run(name+'_run',[sys.executable,'research/sta-rate-control/scripts/run_m09.py','--output',str(folder)],
                    dict(env,M09_MODE=str(mode),M09_DIV=str(div)))
                run(name+'_analysis',[sys.executable,'research/sta-rate-control/scripts/analyze_m09.py',str(folder)])
                e['runs'].append(json.loads((folder/'m09_analysis.json').read_text()))
                if sha(repo/'build/px4_sitl_default/bin/px4')!=e['firmware_sha256']:raise RuntimeError('Binary drift')
                if any(sha(repo/name)!=s for name,s in files.items()):raise RuntimeError('Source drift during series')
        params=[json.loads((out/f'{label}_div{div}'/'ulog_initial_parameters.json').read_text())
                for label in ('pid','esta','ista') for div in (1,2,4)]
        fixed_prefixes=('IMU_','SENS_','INS_','EKF2_','MC_DTERM','MC_DGYRO')
        fixed={k:v for k,v in params[0].items() if k.startswith(fixed_prefixes)}
        if any({k:v for k,v in x.items() if k.startswith(fixed_prefixes)} != fixed for x in params):
            raise RuntimeError('Sensor/filter/estimator parameters differ')
        e['unchanged_sensor_filter_parameters']=fixed
        for r in e['runs']:
            ref=next(x for x in e['runs'] if x['mode']==r['mode'] and x['div']==1)
            pid=next(x for x in e['runs'] if x['mode']==0 and x['div']==r['div'])
            r['tracking_ratio_own_n1']=[a/b for a,b in zip(r['rmse_tracking'],ref['rmse_tracking'])]
            r['tracking_ratio_same_div_pid']=[a/b for a,b in zip(r['rmse_tracking'],pid['rmse_tracking'])]
        e['success']=True
    except Exception as exc:
        e['error']=repr(exc);raise
    finally:save()


if __name__=='__main__':main()
