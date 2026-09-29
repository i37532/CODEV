"""Validation-only tests plus unchanged production and training regressions."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from common import REPO, CONFIG, TRAIN, fingerprint

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--frozen',action='store_true')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    env=os.environ.copy()
    env['PATH']=str(REPO/'.px4-python/bin')+':'+env['PATH']
    env['PYTHONPATH']=':'.join([str(REPO/'.px4-python'),str(REPO/'research/sta-velocity-control/scripts'),'/home/yr/Desktop/codev doc/experiments/M00-20260912/python'])
    evidence=dict(success=False,new_flights=0,commands=[],head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip())
    def run(name,argv):
        with (out/(name+'.log')).open('x') as stream:
            result=subprocess.run(argv,cwd=REPO,env=env,stdout=stream,stderr=subprocess.STDOUT)
        evidence['commands'].append(dict(name=name,argv=argv,exit_code=result.returncode))
        print(name,result.returncode,flush=True)
        if result.returncode:raise RuntimeError(name+' failed')
    try:
        run('validation_tests',['python3',str(CONFIG/'test_validation.py')])
        run('task_output_tests',['python3',str(CONFIG/'test_task_output.py')])
        run('previous_regression',['python3',str(TRAIN/'verify.py'),'--output',str(out/'regression')])
        previous=json.loads((out/'regression/evidence.json').read_text())
        assert previous['success']
        evidence['cpp_tests']=previous['cpp_tests']
        evidence['new_python_tests']=int(re.search(r'Ran (\d+) tests?',(out/'validation_tests.log').read_text())[1])
        evidence['new_python_tests']+=int(re.search(r'Ran (\d+) tests?',(out/'task_output_tests.log').read_text())[1])
        evidence['python_tests']=previous['python_tests']+evidence['new_python_tests']
        run('dry_run',['python3',str(CONFIG/'run.py'),'--source-head',evidence['head'],'--output',str(out/'NOT_CREATED')])
        assert not (out/'NOT_CREATED').exists()
        if args.frozen:
            frozen=json.loads((CONFIG/'frozen.json').read_text())
            for name,expected in frozen['assets'].items():assert fingerprint(REPO/name)==expected,name
            evidence['assets_checked']=len(frozen['assets'])
        evidence['firmware_sha256']=fingerprint(REPO/'build/px4_sitl_default/bin/px4')
        evidence['success']=True
    finally:
        (out/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
        (out/'artifacts.sha256').write_text(''.join(f'{fingerprint(f)}  {f}\n' for f in sorted(out.rglob('*')) if f.is_file() and f.name!='artifacts.sha256'))
    print(json.dumps(evidence,indent=2))

if __name__=='__main__':main()
