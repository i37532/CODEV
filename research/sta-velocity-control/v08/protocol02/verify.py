"""Execute actual previous production regressions plus new V08 research tests."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from common import REPO,CONFIG,fingerprint

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--frozen',action='store_true')
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    env=os.environ.copy();env['PATH']=str(REPO/'.px4-python/bin')+':'+env['PATH']
    env['PYTHONPATH']=':'.join([str(REPO/'.px4-python'),str(REPO/'research/sta-velocity-control/scripts'),'/home/yr/Desktop/codev doc/experiments/M00-20260912/python'])
    e=dict(success=False,commands=[],new_flights=0,head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip())
    def run(name,argv):
        with (out/(name+'.log')).open('w') as f:r=subprocess.run(argv,cwd=REPO,env=env,stdout=f,stderr=subprocess.STDOUT)
        e['commands'].append(dict(name=name,argv=argv,exit_code=r.returncode));print(name,r.returncode,flush=True)
        if r.returncode:raise RuntimeError(name+' failed')
    try:
        run('v08_tests',['python3',str(CONFIG/'test_tuning.py')])
        run('cli_clock_tests',['python3',str(CONFIG/'test_cli_clock.py')])
        # V07's flight snapshot predates its result README commit. Keep it intact;
        # run its tests, then check the NEW V08 snapshot of current assets below.
        run('previous_regression',['python3',str(REPO/'research/sta-velocity-control/v07/protocol07/verify.py'),'--output',str(out/'regression')])
        previous=json.loads((out/'regression/evidence.json').read_text());assert previous['success']
        e['cpp_tests']=previous['cpp_tests']
        e['new_python_tests']=int(re.search(r'Ran (\d+) tests?',(out/'v08_tests.log').read_text())[1])
        e['clock_python_tests']=int(re.search(r'Ran (\d+) tests?',(out/'cli_clock_tests.log').read_text())[1])
        e['new_python_tests']+=e['clock_python_tests']
        e['python_tests']=previous['python_tests']+e['new_python_tests']
        run('dry_run',['python3',str(CONFIG/'run.py'),'--source-head',e['head'],'--output',str(out/'NOT_CREATED')])
        assert not (out/'NOT_CREATED').exists()
        if a.frozen:
            frozen=json.loads((CONFIG/'frozen.json').read_text())
            for name,expected in frozen['assets'].items():assert fingerprint(REPO/name)==expected,name
            e['assets_checked']=len(frozen['assets'])
        e['firmware_sha256']=fingerprint(REPO/'build/px4_sitl_default/bin/px4');e['success']=True
    finally:
        (out/'evidence.json').write_text(json.dumps(e,indent=2)+'\n')
        (out/'artifacts.sha256').write_text(''.join(f'{fingerprint(f)}  {f}\n' for f in sorted(out.rglob('*')) if f.is_file() and f.name!='artifacts.sha256'))
    print(json.dumps(e,indent=2))

if __name__=='__main__':main()
