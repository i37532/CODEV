#!/usr/bin/env python3
"""Freeze one repair contact gate, then (only if accepted) four comparison runs."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys

from qualify import MAIN, REPAIR, ROOT, HERE, sha
from runner_contract import validate_manifest
from run import active_simulators

ORIGINAL=Path('/home/yr/Desktop/Codev-SuperTwisting2-original')
OLD=HERE.parent/'offboard/results/batch04/manifest.json'


def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['contact_gate','comparison'],required=True)
    p.add_argument('--qualification',type=Path,required=True);a=p.parse_args()
    assert not active_simulators()
    assert shutil.disk_usage(ROOT).free>8*1024**3
    q=json.loads(a.qualification.read_text()); assert q['passed'] and q['new_flights']==0
    for f,h in q['source_sha256'].items(): assert sha(f)==h, f
    for c in q['commands']: assert c['exit_code']==0 and sha(c['log'])==c['log_sha256']
    old=json.loads(OLD.read_text()); assets=dict(old['assets'])
    for f,h in assets.items(): assert sha(f)==h, f
    manifest=copy.deepcopy(old)
    for key in ('budget_history','combined_offline_qualification','offline_tests'):manifest.pop(key,None)
    out=ROOT/a.stage
    assert not out.exists()
    systems=['STA2'] if a.stage=='contact_gate' else ['PID','STA2','RSTA','RISTA']
    by_system={j['system']:j for j in old['jobs']}
    manifest.update(revision='imu_fix_quick_v1',quick_stage=a.stage,total_new_attempts_ceiling=5,
                    max_attempts=len(systems),data_root=str(out),flight_qualified=False,jobs=[],
                    status='frozen_quick_hover',qualification=str(a.qualification.resolve()),
                    prior_flights_not_imported=True,comparison='descriptive system-level hover; n=1; smooth ramp not intrinsic step response')
    if a.stage=='comparison':
        gate=ROOT/'contact_gate/runs/O001/result.json'
        receipt=json.loads(gate.read_text())
        assert receipt.get('success') and receipt.get('independent_replay_passed') and receipt.get('contact_audit_passed')
        manifest.update(contact_gate_receipt=str(gate),contact_gate_sha256=sha(gate));assets[str(gate)]=sha(gate)
        ca=gate.parent/'contact_audit.json';assert sha(ca)==receipt['contact_audit_sha256'];assets[str(ca)]=sha(ca)
    for i,system in enumerate(systems,1):
        j=copy.deepcopy(by_system[system]);j.update(id='O%03d'%i,task='hover',status='unattempted')
        if system=='STA2':
            for k in ('repo','bin','rootfs'):
                j[k]=j[k].replace(str(ORIGINAL),str(REPAIR))
            j['launch_command']=[v.replace(str(ORIGINAL),str(REPAIR)) for v in j['launch_command']]
            # Use the exact old compiled plugins/assets, without rebuilding or altering them.
            plugins=str(ORIGINAL/'build/px4_sitl_default/build_gazebo-classic')
            models=str(ORIGINAL/'Tools/simulation/gazebo-classic/sitl_gazebo-classic/models')
            j['launch_env'].update(GAZEBO_PLUGIN_PATH=plugins,LD_LIBRARY_PATH=plugins,GAZEBO_MODEL_PATH=models)
            j['variant']='original_control_with_sim_imu_fix'
            j['display_label']='STA2 + IMU fix'
            j['firmware_sha256']=sha(REPAIR/'build/px4_sitl_default/bin/px4')
            assert j['firmware_sha256']==q['firmware_sha256']
            assert all(sha(REPAIR/f)==h for f,h in j['source_assets'].items())
            names=subprocess.check_output(['git','ls-files'],cwd=REPAIR,text=True).splitlines()
            names+=['src/modules/simulation/simulator_mavlink/ImuConversionTest.cpp']
            j['source_assets']={n:sha(REPAIR/n) for n in names if (REPAIR/n).is_file()}
        if 'M10_IMU_LOG' in j['launch_env']:
            j['launch_env']['M10_IMU_LOG']=str(out/(j['id']+'_imu.csv'))
        assert sha(Path(j['bin'])/'px4')==j['firmware_sha256']
        for f,h in j['source_assets'].items():assert sha(Path(j['repo'])/f)==h, f
        manifest['jobs'].append(j)
    manifest['order']=[j['id'] for j in manifest['jobs']]
    runtime=json.loads((a.qualification.parent/'runtime.log').read_text())
    assert runtime['ready'] and runtime['roundtrip_passed']
    manifest['runtime'].update(qualification=runtime,launcher=runtime['launcher_argv'],environment=runtime['environment'])
    for f in [*HERE.glob('*.py'),HERE/'PROTOCOL_CN.md',OLD,a.qualification,*a.qualification.parent.glob('*.xml'),
              *a.qualification.parent.glob('*.log')]:assets[str(f.resolve())]=sha(f)
    manifest['assets']=assets;manifest['flight_qualified']=True
    for j in manifest['jobs']:validate_manifest(manifest,j['id'])
    out.mkdir()
    patch=subprocess.check_output(['git','diff','--binary'],cwd=REPAIR,text=True)
    extra=subprocess.run(['git','diff','--no-index','--','/dev/null','src/modules/simulation/simulator_mavlink/ImuConversionTest.cpp'],
                         cwd=REPAIR,text=True,capture_output=True)
    assert extra.returncode==1
    (out/'repair_source.patch').write_text(patch+extra.stdout)
    manifest['assets'][str(out/'repair_source.patch')]=sha(out/'repair_source.patch')
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    (out/'outcomes.json').write_text(json.dumps({j['id']:'unattempted' for j in manifest['jobs']},indent=2)+'\n')
    for name,repo in [('main',MAIN),('original',ORIGINAL),('repair',REPAIR)]:
        for label,cmd in [('status',['status','--short']),('head',['rev-parse','HEAD']),('submodules',['submodule','status','--recursive'])]:
            (out/(name+'_'+label+'.txt')).write_text(subprocess.check_output(['git',*cmd],cwd=repo,text=True))
    print(out/'manifest.json')


if __name__=='__main__':main()
