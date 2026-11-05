"""V07 nonzero regression, no launch and no mutable historical freeze files."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from common import REPO,CONFIG,fingerprint

def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',type=Path,required=True); p.add_argument('--frozen',action='store_true')
    args=p.parse_args(); out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    env=os.environ.copy(); env['PATH']=str(REPO/'.px4-python/bin')+':'+env['PATH']
    env['PYTHONPATH']=':'.join([str(REPO/'.px4-python'),str(REPO/'research/sta-velocity-control/scripts'),'/home/yr/Desktop/codev doc/experiments/M00-20260912/python',env.get('PYTHONPATH','')])
    e=dict(success=False,commands=[],tests={},new_flights=0,head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip())
    param=REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'; e['eeprom_before']=fingerprint(param)
    def save(): (out/'evidence.json').write_text(json.dumps(e,indent=2)+'\n')
    def run(name,argv):
        with (out/(name+'.log')).open('w') as stream:
            r=subprocess.run(argv,cwd=REPO,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=1200)
        e['commands'].append(dict(name=name,argv=argv,exit_code=r.returncode)); save(); print(name,r.returncode,flush=True)
        if r.returncode: raise RuntimeError(name+' failed; evidence retained')
    try:
        run('workspace',['git','status','--short']); run('submodules',['git','submodule','status','--recursive'])
        run('build_tests',['make','tests','TESTFILTER=VelocityDecimation','-j4'])
        run('build_sitl',['make','px4_sitl_default','-j4'])
        names=['PositionControl','ControlMath','Takeoff','RateControl','RateControlDispatcher','VelocityControl',
            'VelocitySelectionParam','StaVelocityControl','StaVelocityProtection','StaRateControl','VelocityDiagnosticInput',
            'VelocityEsta','VelocityModule','VelocityEstaZ','VelocityZIntegration','EKF2Selector','LandingDescentContract',
            'EstimatorDiagnosticTopics','VelocityXYIntegration','VelocityXYZIntegration','VelocityResearchTask','VelocityDecimation']
        functional={'VelocitySelectionParam','VelocityDiagnosticInput','VelocityModule','EKF2Selector','LandingDescentContract','EstimatorDiagnosticTopics'}
        for name in names:
            binary=REPO/'build/px4_sitl_test'/('functional-'+name if name in functional else 'unit-'+name); xml=out/(name+'.xml')
            run(name,['timeout','60s',str(binary),'--gtest_output=xml:'+str(xml)])
            a=ET.parse(xml).getroot().attrib; e['tests'][name]={k:int(a[k]) for k in ('tests','failures','errors','disabled')}
            assert int(a['tests'])>0 and not any(int(a[k]) for k in ('failures','errors','disabled'))
        previous='/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/verification_committed01'
        historical=json.loads((REPO/'research/sta-velocity-control/v04/results01/verification.json').read_text())
        for c in historical['commands']:
            if c['name'] in ('candidate_compile','candidate_audit'):
                run(c['name'],[v.replace(previous,str(out)) for v in c['command']])
        a=ET.parse(out/'candidate_audit.xml').getroot().attrib
        e['tests']['candidate_audit']={k:int(a[k]) for k in ('tests','failures','errors','disabled')}
        assert e['tests']['candidate_audit']==dict(tests=3,failures=0,errors=0,disabled=0)
        run('historical_python',['python3','-m','unittest','discover','-s',str(REPO/'research/sta-velocity-control/scripts'),'-p','test_*.py','-v'])
        for name,file in [('cadence','test_cadence.py'),('landing','test_landing.py'),('protocol','test_protocol.py')]:
            run(name,['python3',str(CONFIG/file)])
        run('dry_run',['python3',str(CONFIG/'run.py'),'--source-head',e['head'],'--output',str(out/'NOT_CREATED')])
        assert not (out/'NOT_CREATED').exists()
        run('gazebo_build_only',['env','DONT_RUN=1','make','px4_sitl_default','gazebo_iris','-j4'])
        e['formats']={}
        for name in ('sta_velocity_ctrl_status','velocity_ctrl_selection'):
            text=(REPO/f'build/px4_sitl_default/msg/topics_sources/{name}.cpp').read_text()
            fields=re.search('__orb_'+name+'_fields\\[\\] = "([^"]+)"',text)[1]
            e['formats'][name]=len(name+':')+len(fields)+1; assert e['formats'][name]<1500
        e['cpp_tests']=sum(t['tests'] for t in e['tests'].values())
        e['python_tests']=sum(int(re.search(r'Ran (\d+) tests?',(out/(name+'.log')).read_text())[1]) for name in ('historical_python','cadence','landing','protocol'))
        e['firmware_sha256']=fingerprint(REPO/'build/px4_sitl_default/bin/px4')
        if args.frozen:
            frozen=json.loads((CONFIG/'frozen.json').read_text())
            for name,expected in frozen['assets'].items(): assert fingerprint(REPO/name)==expected,name
            e['assets_checked']=len(frozen['assets'])
        run('diff_check',['git','diff','--check'])
        e['eeprom_after']=fingerprint(param); assert e['eeprom_after']==e['eeprom_before']; e['success']=True
    finally:
        save(); files=sorted(f for f in out.rglob('*') if f.is_file() and f.name!='artifacts.sha256')
        (out/'artifacts.sha256').write_text(''.join(f'{fingerprint(f)}  {f}\n' for f in files))
    print(json.dumps(e))

if __name__=='__main__': main()
