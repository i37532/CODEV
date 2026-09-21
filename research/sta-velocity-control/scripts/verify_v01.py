#!/usr/bin/env python3
"""Offline V01 build, original-reference provenance, and actual test counts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[3]
BASE = 'b11068e2ddb0c6734ae566045dc096eaf7a7c834'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    out = p.parse_args().output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env['PYTHONPATH'] = str(REPO/'.px4-python') + ':' + env.get('PYTHONPATH', '')
    env['PATH'] = str(REPO/'.px4-python/bin') + ':' + env['PATH']
    evidence = dict(base=BASE, commands=[], references={}, tests={}, success=False)

    def save():
        (out/'evidence.json').write_text(json.dumps(evidence, indent=2)+'\n')

    def run(name, cmd):
        with (out/(name+'.log')).open('w') as stream:
            r = subprocess.run(cmd, cwd=REPO, env=env, stdout=stream, stderr=subprocess.STDOUT)
        evidence['commands'].append(dict(name=name, command=cmd, exit_code=r.returncode))
        save()
        print(name, r.returncode, flush=True)
        if r.returncode:
            raise RuntimeError(name+' failed; see preserved log')

    try:
        for name, cmd in [('head',['git','rev-parse','HEAD']), ('status',['git','status','--short','--branch']),
                          ('submodules',['git','submodule','status','--recursive']),
                          ('submodule_workspaces',['git','submodule','foreach','--recursive','--quiet','git status --porcelain']),
                          ('compiler',['g++','--version']), ('gazebo',['pkg-config','--modversion','gazebo'])]:
            run(name,cmd)
        for rel in ['PositionControl/PositionControl.hpp','PositionControl/PositionControl.cpp',
                    'PositionControl/ControlMath.hpp','PositionControl/ControlMath.cpp','Takeoff/Takeoff.hpp','Takeoff/Takeoff.cpp']:
            path='src/modules/mc_pos_control/'+rel
            original=subprocess.check_output(['git','show',BASE+':'+path],cwd=REPO)
            # V00 external reference must corroborate the Git source, not today's modified controller.
            v00=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260921/V00/verification04/references')/path
            if v00.read_bytes()!=original:
                raise ValueError('V00 reference mismatch: '+path)
            transformed=original.decode()
            for symbol in ('PositionControlStates','PositionControl','ControlMath','TakeoffState','Takeoff'):
                transformed=re.sub(r'\b'+symbol+r'\b','V00'+symbol,transformed)
            if rel=='PositionControl/PositionControl.hpp':
                transformed=transformed.replace('private:\n','private:\n\tfriend class VelocityControlTestAccess;\n')
            reference=REPO/'src/modules/mc_pos_control/PositionControl/test/v00'/('V00'+Path(rel).name)
            if reference.read_text()!=transformed.rstrip()+'\n':
                raise ValueError('Transformed reference changed: '+str(reference))
            evidence['references'][path]=dict(original_sha256=hashlib.sha256(original).hexdigest(),
                reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
                transformations='Identifier/include renaming; PositionControl friend test access only')
        module='src/modules/mc_pos_control/MulticopterPositionControl.cpp'
        old=subprocess.check_output(['git','show',BASE+':'+module],cwd=REPO,text=True)
        new=(REPO/module).read_text()
        for signature in ('int MulticopterPositionControl::parameters_update',
                          'PositionControlStates MulticopterPositionControl::set_vehicle_states',
                          'void MulticopterPositionControl::failsafe'):
            def body(text):
                start=text.index(signature)
                end=text.index('\n}',start)+2
                return text[start:end]
            if body(old)!=body(new):
                raise ValueError('Original module semantics changed: '+signature)
        evidence['original_parameter_state_failsafe_functions_unchanged']=True
        save()
        run('build_sitl',['make','px4_sitl_default','-j4'])
        run('build_tests',['make','tests','TESTFILTER=VelocityControl','-j4'])
        for name in ('PositionControl','ControlMath','Takeoff','RateControl','RateControlDispatcher','VelocityControl','VelocitySelectionParam'):
            binary=('functional-' if name=='VelocitySelectionParam' else 'unit-')+name
            xml=out/(name+'.xml')
            run(name,[str(REPO/'build/px4_sitl_test'/binary),'--gtest_output=xml:'+str(xml)])
            attrs=ET.parse(xml).getroot().attrib
            evidence['tests'][name]={k:int(attrs[k]) for k in ('tests','failures','errors','disabled')}
            if not evidence['tests'][name]['tests'] or any(evidence['tests'][name][k] for k in ('failures','errors','disabled')):
                raise ValueError('No valid nonzero test run: '+name)
            save()
        run('python_tools',['python3','-m','unittest','discover','-s','research/sta-velocity-control/scripts','-p','test_*.py','-v'])
        params=json.loads((REPO/'build/px4_sitl_default/parameters.json').read_text())['parameters']
        for name in ('MPC_VC_MODE','MPC_VC_AXES'):
            matches=[v for v in params if v['name']==name]
            assert len(matches)==1 and matches[0]['type']=='Int32' and matches[0]['default']==0
        evidence['unique_cpp_tests']=sum(t['tests'] for t in evidence['tests'].values())
        evidence['success']=True
    finally:
        save()


if __name__=='__main__':
    main()
