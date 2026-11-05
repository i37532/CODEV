"""Pilot regressions/build and its own asset freeze, zero flight authorization."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from common import REPO,CONFIG,TRAIN,fingerprint

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--frozen',action='store_true')
    args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    env=os.environ.copy();env['PATH']=str(REPO/'.px4-python/bin')+':'+env['PATH']
    env['PYTHONPATH']=':'.join([str(REPO/'.px4-python'),str(REPO/'research/sta-velocity-control/scripts'),'/home/yr/Desktop/codev doc/experiments/M00-20260912/python'])
    e=dict(success=False,new_flights=0,commands=[],head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip())
    def run(name,argv):
        with (out/(name+'.log')).open('x') as stream:r=subprocess.run(argv,cwd=REPO,env=env,stdout=stream,stderr=subprocess.STDOUT)
        e['commands'].append(dict(name=name,argv=argv,exit_code=r.returncode));print(name,r.returncode,flush=True)
        if r.returncode:raise RuntimeError(name+' failed')
    try:
        run('pilot_tests',['python3',str(CONFIG/'test_pilot.py')])
        run('design_tests',['python3',str(CONFIG/'test_design.py')])
        run('formal_design_tests',['python3',str(CONFIG/'test_formal_design.py')])
        run('evidence_tests',['python3',str(REPO/'research/sta-velocity-control/v08/evidence_tools/test_replay_batch.py')])
        run('previous_regression',['python3',str(REPO/'research/sta-velocity-control/v08/protocol03b/verify.py'),'--output',str(out/'regression')])
        previous=json.loads((out/'regression/evidence.json').read_text());assert previous['success']
        e['new_python_tests']=sum(int(re.search(r'Ran (\d+) tests?',(out/(name+'.log')).read_text())[1]) for name in ('pilot_tests','design_tests','formal_design_tests','evidence_tests'))
        e['cpp_tests']=previous['cpp_tests'];e['python_tests']=previous['python_tests']+e['new_python_tests']
        run('plugin_and_probe_build',['python3',str(CONFIG/'build_offline.py'),'--output',str(out/'plugin_build')])
        plugin=json.loads((out/'plugin_build/evidence.json').read_text());assert plugin['success']
        # The independently compiled C++14 waveform probe is counted separately
        # from the 231 firmware gtests; Gazebo's pkg-config uses C++17.
        e['waveform_probe_cases']=len(plugin['probe_cases']);e['invalid_probe_cases']=3
        run('dry_run',['python3',str(CONFIG/'run.py'),'--source-head',e['head'],'--output',str(out/'NOT_CREATED')])
        assert not (out/'NOT_CREATED').exists()
        if args.frozen:
            frozen=json.loads((CONFIG/'frozen.json').read_text())
            for name,expected in frozen['assets'].items():assert fingerprint(REPO/name)==expected,name
            e['assets_checked']=len(frozen['assets'])
        e['firmware_sha256']=fingerprint(REPO/'build/px4_sitl_default/bin/px4');e['success']=True
    finally:
        (out/'evidence.json').write_text(json.dumps(e,indent=2)+'\n')
        (out/'artifacts.sha256').write_text(''.join(f'{fingerprint(f)}  {f}\n' for f in sorted(out.rglob('*')) if f.is_file() and f.name!='artifacts.sha256'))
    print(json.dumps(e,indent=2))

if __name__=='__main__':main()
