"""Offline full regression/build, design-only mock, and formal asset audit."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import common

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--frozen',action='store_true')
    args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    env=os.environ.copy();env['PATH']=str(common.REPO/'.px4-python/bin')+':'+env['PATH']
    env['PYTHONPATH']=':'.join([str(common.REPO/'.px4-python'),str(common.REPO/'research/sta-velocity-control/scripts'),'/home/yr/Desktop/codev doc/experiments/M00-20260912/python'])
    e=dict(success=False,new_flights=0,commands=[],head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=common.REPO,text=True).strip())
    def run(name,argv):
        with (out/(name+'.log')).open('x') as stream:r=subprocess.run(argv,cwd=common.REPO,env=env,stdout=stream,stderr=subprocess.STDOUT)
        e['commands'].append(dict(name=name,argv=argv,exit_code=r.returncode));print(name,r.returncode,flush=True)
        if r.returncode:raise RuntimeError(name+' failed')
    try:
        run('formal_runtime_tests',['python3',str(common.CONFIG/'test_runtime.py')])
        run('formal_package_tests',['python3',str(common.CONFIG/'test_formal_package.py')])
        run('qualified_gate_tests',['python3',str(common.REPO/'research/sta-velocity-control/v08/evidence_tools/test_qualified_gate_summary.py')])
        run('previous_regression',['python3',str(common.REPO/'research/sta-velocity-control/v08/protocol05/verify.py'),'--output',str(out/'regression')])
        previous=json.loads((out/'regression/evidence.json').read_text());assert previous['success']
        e['new_python_tests']=sum(int(re.search(r'Ran (\d+) tests?',(out/(name+'.log')).read_text())[1]) for name in ('formal_runtime_tests','formal_package_tests','qualified_gate_tests'))
        e['cpp_tests']=previous['cpp_tests'];e['python_tests']=previous['python_tests']+e['new_python_tests']
        e['waveform_probe_cases']=previous['waveform_probe_cases'];e['invalid_probe_cases']=previous['invalid_probe_cases']
        run('dry_run',['python3',str(common.CONFIG/'run.py'),'--source-head',e['head'],'--output',str(out/'NOT_CREATED')])
        assert not (out/'NOT_CREATED').exists()
        run('zero_holdout_statistics',['python3',str(common.CONFIG/'formal_package.py'),'analyze','--manifest',str(common.CONFIG/'manifest.json'),'--outcomes',str(common.CONFIG/'outcomes_unattempted.json'),'--output',str(out/'zero_holdout_statistics.json')])
        zero=json.loads((out/'zero_holdout_statistics.json').read_text());assert zero['accepted']==0 and not zero['majority_condition_met']
        if args.frozen:
            frozen=json.loads((common.CONFIG/'frozen.json').read_text())
            for name,expected in frozen['assets'].items():assert common.fingerprint(common.REPO/name)==expected,name
            e['assets_checked']=len(frozen['assets'])
        e['firmware_sha256']=common.fingerprint(common.REPO/'build/px4_sitl_default/bin/px4');e['success']=True
    finally:
        (out/'evidence.json').write_text(json.dumps(e,indent=2)+'\n')
        (out/'artifacts.sha256').write_text(''.join(f'{common.fingerprint(f)}  {f}\n' for f in sorted(out.rglob('*')) if f.is_file() and f.name!='artifacts.sha256'))
    print(json.dumps(e,indent=2))

if __name__=='__main__':main()
