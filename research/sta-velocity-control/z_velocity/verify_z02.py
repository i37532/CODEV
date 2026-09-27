#!/usr/bin/env python3
"""Z02 offline verifier. New opt-in scope; old frozen verifiers stay untouched."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[3]
BASE = '9f0dff53a25e01fbd9acfb97d7ce8da67e96930f'

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def body(text, sig):
    start = text.index(sig)
    return text[start:text.index('\n}', start) + 2]

def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True)
    out = p.parse_args().output.resolve(); out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy(); env['PATH'] = str(REPO / '.px4-python/bin') + ':' + env['PATH']
    env['PYTHONPATH'] = ':'.join([str(REPO / '.px4-python'), '/home/yr/Desktop/codev doc/experiments/M00-20260912/python', env.get('PYTHONPATH', '')])
    eeprom = REPO / 'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
    e = dict(success=False, commands=[], tests={}, new_flights=0, base=BASE,
             head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(), eeprom_before=digest(eeprom))
    def save(): (out / 'evidence.json').write_text(json.dumps(e,indent=2)+'\n')
    def run(name, argv):
        with (out / (name+'.log')).open('w') as stream:
            r = subprocess.run(argv,cwd=REPO,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=900)
        e['commands'].append(dict(name=name,argv=argv,exit_code=r.returncode)); save(); print(name,r.returncode,flush=True)
        if r.returncode: raise RuntimeError(name+' failed; preserve evidence')
    save()
    try:
        for name,args in [('status',['git','status','--short']),('submodules',['git','submodule','status','--recursive'])]: run(name,args)
        prefix = 'src/modules/mc_pos_control/'
        for rel,sigs in {
            'PositionControl/PositionControl.cpp':['void PositionControl::_positionControl()', 'void PositionControl::_velocityControlPid(',
                'void PositionControl::_velocityControlEstaX(', 'void PositionControl::_accelerationControl()', 'bool PositionControl::_updateSuccessful()'],
            'MulticopterPositionControl.cpp':['int MulticopterPositionControl::parameters_update',
                'PositionControlStates MulticopterPositionControl::set_vehicle_states', 'void MulticopterPositionControl::failsafe(']
        }.items():
            old=subprocess.check_output(['git','show',BASE+':'+prefix+rel],cwd=REPO,text=True)
            new=(REPO/prefix/rel).read_text()
            for sig in sigs: assert body(old,sig)==body(new,sig), sig
        for rel in ['Takeoff/Takeoff.cpp','Takeoff/Takeoff.hpp']:
            assert subprocess.check_output(['git','show',BASE+':'+prefix+rel],cwd=REPO)==(REPO/prefix/rel).read_bytes()
        for f in (REPO/prefix/'PositionControl/test/v00').iterdir():
            if f.is_file(): assert subprocess.check_output(['git','show',BASE+':'+str(f.relative_to(REPO))],cwd=REPO)==f.read_bytes()
        old=subprocess.check_output(['git','show',BASE+':'+prefix+'mc_pos_control_params.c'],cwd=REPO,text=True)
        new=(REPO/prefix/'mc_pos_control_params.c').read_text()
        defaults=lambda text:dict(re.findall(r'PARAM_DEFINE_\w+\((\w+),\s*([^;]+)\);',text))
        assert all(defaults(new)[k]==v for k,v in defaults(old).items())
        run('build_tests',['make','tests','TESTFILTER=VelocityZIntegration','-j4'])
        run('build_sitl',['make','px4_sitl_default','-j4'])
        names=['PositionControl','ControlMath','Takeoff','RateControl','RateControlDispatcher','VelocityControl',
            'VelocitySelectionParam','StaVelocityControl','StaVelocityProtection','StaRateControl','VelocityDiagnosticInput',
            'VelocityEsta','VelocityModule','VelocityEstaZ','VelocityZIntegration','EKF2Selector',
            'LandingDescentContract','EstimatorDiagnosticTopics']
        functional={'VelocitySelectionParam','VelocityDiagnosticInput','VelocityModule','EKF2Selector','LandingDescentContract','EstimatorDiagnosticTopics'}
        for name in names:
            binary=REPO/'build/px4_sitl_test'/('functional-' if name in functional else 'unit-')
            binary=Path(str(binary)+name)
            xml=out/(name+'.xml')
            run(name,['timeout','60s',str(binary),'--gtest_output=xml:'+str(xml)])
            a=ET.parse(xml).getroot().attrib; e['tests'][name]={k:int(a[k]) for k in ['tests','failures','errors','disabled']}
            assert e['tests'][name]['tests']>0 and not any(e['tests'][name][k] for k in ['failures','errors','disabled'])
        frozen=json.loads((REPO/'research/sta-velocity-control/v04/results01/verification.json').read_text())
        previous='/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/verification_committed01'
        for c in frozen['commands']:
            if c['name'] in ['candidate_compile','candidate_audit']:
                run(c['name'],[v.replace(previous,str(out)) for v in c['command']])
        attrs=ET.parse(out/'candidate_audit.xml').getroot().attrib
        e['tests']['candidate_audit']={k:int(attrs[k]) for k in ['tests','failures','errors','disabled']}
        assert e['tests']['candidate_audit']==dict(tests=3,failures=0,errors=0,disabled=0)
        run('python_tools',['python3','-m','unittest','discover','-s','research/sta-velocity-control/scripts','-p','test_*.py','-v'])
        run('gazebo_build_only',['env','DONT_RUN=1','make','px4_sitl_default','gazebo_iris','-j4'])
        text=(REPO/'build/px4_sitl_default/msg/topics_sources/sta_velocity_ctrl_status.cpp').read_text()
        fields=re.search(r'__orb_sta_velocity_ctrl_status_fields\[\] = "([^"]+)"',text)[1]
        e['ulog_format_bytes']=len('sta_velocity_ctrl_status:')+len(fields)+1
        assert e['ulog_format_bytes']<1500 and 'z_phase' in fields and 'z_hte_shift' in fields
        e['unique_cpp_tests']=sum(v['tests'] for v in e['tests'].values())
        e['python_tests']=int(re.search(r'Ran (\d+) tests',(out/'python_tools.log').read_text())[1])
        e['firmware_sha256']=digest(REPO/'build/px4_sitl_default/bin/px4')
        e['eeprom_after']=digest(eeprom); assert e['eeprom_after']==e['eeprom_before']
        run('diff_check',['git','diff','--check']); e['success']=True
    finally:
        save()
        files=sorted(f for f in out.rglob('*') if f.is_file() and f.name!='artifacts.sha256')
        (out/'artifacts.sha256').write_text(''.join(f'{digest(f)}  {f}\n' for f in files))
    print(json.dumps(e))

if __name__=='__main__': main()
