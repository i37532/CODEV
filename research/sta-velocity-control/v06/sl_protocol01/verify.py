"""Verify V06 offline, including source and actual nonzero test counts."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
from common import REPO,CONFIG,fingerprint

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve(); out.mkdir(parents=True,exist_ok=False)
    env=os.environ.copy(); env['PATH']=str(REPO/'.px4-python/bin')+':'+env['PATH']
    env['PYTHONPATH']=':'.join([str(REPO/'.px4-python'),str(REPO/'research/sta-velocity-control/scripts'),'/home/yr/Desktop/codev doc/experiments/M00-20260912/python',env.get('PYTHONPATH','')])
    e=dict(success=False,commands=[],new_flights=0,head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip())
    def save(): (out/'evidence.json').write_text(json.dumps(e,indent=2)+'\n')
    def run(name,argv):
        with (out/(name+'.log')).open('w') as stream:
            r=subprocess.run(argv,cwd=REPO,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=900)
        e['commands'].append(dict(name=name,argv=argv,exit_code=r.returncode)); save(); print(name,r.returncode,flush=True)
        if r.returncode: raise RuntimeError(name+' failed; retain evidence')
    try:
        run('contact_tests',['python3',str(CONFIG.parent/'soft_landing/test_contact.py')])
        run('contact_object',['python3',str(CONFIG.parent/'soft_landing/test_contact_object.py')])
        run('health_tests',['python3',str(CONFIG.parent/'soft_landing/test_health.py')])
        run('binding',['python3',str(CONFIG/'test_protocol.py')])
        run('landing_tests',['python3',str(CONFIG/'test_landing.py')])
        run('dry_run',['python3',str(CONFIG/'run.py'),'--source-head',e['head'],'--output',str(out/'NOT_CREATED')])
        run('controls',['python3',str(REPO/'research/sta-velocity-control/z_velocity/verify_z02.py'),'--output',str(out/'controls')])
        run('xy_unit',['timeout','60s',str(REPO/'build/px4_sitl_test/unit-VelocityXYIntegration'),'--gtest_output=xml:'+str(out/'xy_unit.xml')])
        run('xyz_unit',['timeout','60s',str(REPO/'build/px4_sitl_test/unit-VelocityXYZIntegration'),'--gtest_output=xml:'+str(out/'xyz_unit.xml')])
        xyz=ET.parse(out/'xyz_unit.xml').getroot().attrib
        assert int(xyz['tests'])>0 and not any(int(xyz[k]) for k in ('failures','errors','disabled'))
        e['xyz_tests']=int(xyz['tests'])
        a=ET.parse(out/'xy_unit.xml').getroot().attrib
        assert int(a['tests'])>0 and not any(int(a[k]) for k in ('failures','errors','disabled'))
        e['xy_tests']=int(a['tests'])
        c=json.loads((out/'controls/evidence.json').read_text()); run('task_unit',['timeout','60s',str(REPO/'build/px4_sitl_test/unit-VelocityResearchTask'),'--gtest_output=xml:'+str(out/'task_unit.xml')])
        a=ET.parse(out/'task_unit.xml').getroot().attrib
        assert int(a['tests'])>0 and not any(int(a[k]) for k in ('failures','errors','disabled'))
        e['task_tests']=int(a['tests'])
        e['cpp_tests']=c['unique_cpp_tests']+e['xy_tests']+e['xyz_tests']+e['task_tests']
        e['python_tests']=c['python_tests']+sum(int(re.search(r'Ran (\d+) tests?',(out/(name+'.log')).read_text())[1]) for name in ('binding','landing_tests','contact_tests','health_tests','contact_object'))
        frozen=json.loads((CONFIG/'frozen.json').read_text())
        for name,expected in frozen['assets'].items(): assert fingerprint(REPO/name)==expected,name
        e['assets_checked']=len(frozen['assets']); e['success']=True
    finally:
        save()
        files=sorted(f for f in out.rglob('*') if f.is_file() and f.name!='artifacts.sha256')
        (out/'artifacts.sha256').write_text(''.join(f'{fingerprint(f)}  {f}\n' for f in files))
    print(json.dumps(e))

if __name__=='__main__': main()
