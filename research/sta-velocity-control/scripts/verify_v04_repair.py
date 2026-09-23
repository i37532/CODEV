#!/usr/bin/env python3
"""Offline-only authorized upstream repair audit. Never starts SITL or changes EEPROM.

Old verify_v01/verify_v04 remain frozen: their unchanged-failsafe assertion no
longer applies to this explicitly authorized repair. Keep reference math checks.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[3]
BASE = '640a5857a28b8045ea91690a33748446ba4ce275'


def body(text, signature):
    start = text.index(signature)
    return text[start:text.index('\n}', start) + 2]


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True)
    out = p.parse_args().output.resolve(); out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy(); env['PATH'] = str(REPO/'.px4-python/bin') + ':' + env['PATH']
    env['PYTHONPATH'] = str(REPO/'.px4-python') + ':' + env.get('PYTHONPATH', '')
    e = dict(success=False, scope='offline_only_no_flight', base=BASE, commands=[], tests={}, unchanged={})

    def save(): (out/'evidence.json').write_text(json.dumps(e, indent=2)+'\n')
    def run(name, cmd):
        with (out/(name+'.log')).open('w') as f:
            r = subprocess.run(cmd, cwd=REPO, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=600)
        e['commands'].append(dict(name=name, argv=cmd, exit_code=r.returncode)); save()
        print(name, r.returncode, flush=True)
        if r.returncode: raise RuntimeError(name+' failed; preserve this output directory')

    try:
        for name,cmd in [('head',['git','rev-parse','HEAD']),('status',['git','status','--short']),
                         ('submodules',['git','submodule','status','--recursive'])]: run(name,cmd)
        prefix = 'src/modules/mc_pos_control/'
        for rel, signatures in {
            'MulticopterPositionControl.cpp': ['int MulticopterPositionControl::parameters_update',
                'PositionControlStates MulticopterPositionControl::set_vehicle_states'],
            'PositionControl/PositionControl.cpp': ['void PositionControl::_positionControl()',
                'void PositionControl::_velocityControlPid(', 'void PositionControl::_velocityControlEstaX(',
                'void PositionControl::_accelerationControl()', 'bool PositionControl::_updateSuccessful()']
        }.items():
            old = subprocess.check_output(['git','show',BASE+':'+prefix+rel],cwd=REPO,text=True)
            new = (REPO/prefix/rel).read_text()
            for sig in signatures:
                assert body(old,sig)==body(new,sig), 'Unexpected math change '+sig
                e['unchanged'][sig]=True
        for rel in ['Takeoff/Takeoff.cpp','Takeoff/Takeoff.hpp','mc_pos_control_params.c']:
            old=subprocess.check_output(['git','show',BASE+':'+prefix+rel],cwd=REPO)
            assert old==(REPO/prefix/rel).read_bytes(), 'Unexpected Takeoff/default change'
            e['unchanged'][rel]=hashlib.sha256(old).hexdigest()
        # References must stay exactly as frozen before the repair.
        for path in sorted((REPO/prefix/'PositionControl/test/v00').iterdir()):
            if path.is_file():
                rel=str(path.relative_to(REPO))
                assert subprocess.check_output(['git','show',BASE+':'+rel],cwd=REPO)==path.read_bytes()
        e['failsafe_semantics_intentionally_changed']=True
        run('build_sitl',['make','px4_sitl_default','-j4'])
        run('build_tests',['make','tests','TESTFILTER=VelocityModule','-j4'])
        for name in ['PositionControl','ControlMath','Takeoff','RateControl','RateControlDispatcher',
                     'VelocityControl','VelocitySelectionParam','StaVelocityControl','StaVelocityProtection',
                     'StaRateControl','VelocityDiagnosticInput','VelocityEsta','VelocityModule']:
            functional=name in ['VelocitySelectionParam','VelocityDiagnosticInput','VelocityModule']
            binary=('functional-' if functional else 'unit-')+name
            xml=out/(name+'.xml')
            run(name,['timeout','60s',str(REPO/'build/px4_sitl_test'/binary),'--gtest_output=xml:'+str(xml)])
            a=ET.parse(xml).getroot().attrib
            e['tests'][name]={k:int(a[k]) for k in ['tests','failures','errors','disabled']}
            assert e['tests'][name]['tests']>0 and not any(e['tests'][name][k] for k in ['failures','errors','disabled'])
        # Preserve the three original candidate provenance regressions as well.
        frozen=json.loads((REPO/'research/sta-velocity-control/v04/results01/verification.json').read_text())
        previous='/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/verification_committed01'
        for c in frozen['commands']:
            if c['name'] in ['candidate_compile','candidate_audit']:
                run(c['name'],[x.replace(previous,str(out)) for x in c['command']])
        a=ET.parse(out/'candidate_audit.xml').getroot().attrib
        e['tests']['candidate_audit']={k:int(a[k]) for k in ['tests','failures','errors','disabled']}
        assert e['tests']['candidate_audit']['tests']==3
        run('python_tools',['python3','-m','unittest','discover','-s','research/sta-velocity-control/scripts','-p','test_*.py','-v'])
        run('gazebo_build_only',['env','DONT_RUN=1','make','px4_sitl_default','gazebo_iris','-j4'])
        generated=REPO/'build/px4_sitl_default/msg/topics_sources/sta_velocity_ctrl_status.cpp'
        fields=re.search(r'__orb_sta_velocity_ctrl_status_fields\[\] = "([^"]+)"',generated.read_text())[1]
        e['ulog_format_bytes']=len('sta_velocity_ctrl_status:')+len(fields)+1
        assert e['ulog_format_bytes']<1500
        for field in ['first_fail','first_input','retry_result','excitation_fault']: assert field in fields
        e['unique_cpp_tests']=sum(v['tests'] for v in e['tests'].values())
        e['firmware_sha256']=hashlib.sha256((REPO/'build/px4_sitl_default/bin/px4').read_bytes()).hexdigest()
        e['changed_files']={}
        names=subprocess.check_output(['git','diff','--name-only',BASE],cwd=REPO,text=True).splitlines()
        names+=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=REPO,text=True).splitlines()
        for rel in sorted(set(names)):
            if (REPO/rel).is_file(): e['changed_files'][rel]=hashlib.sha256((REPO/rel).read_bytes()).hexdigest()
        run('diff_check',['git','diff','--check'])
        e['success']=True
    finally: save()


if __name__=='__main__': main()
