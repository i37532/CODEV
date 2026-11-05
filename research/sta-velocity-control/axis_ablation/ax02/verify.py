#!/usr/bin/env python3
"""AX02 offline audit/build/tests/replay; never call --execute or launch SITL."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import common
from freeze import capture

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--require-clean',action='store_true');args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    repo=common.REPO;env=os.environ.copy()
    env['PATH']=str(repo/'.px4-python/bin')+':'+env['PATH']
    env['PYTHONPATH']=':'.join([str(repo/'.px4-python'),'/home/yr/Desktop/codev doc/experiments/M00-20260912/python',str(repo/'research/sta-velocity-control/scripts'),env.get('PYTHONPATH','')])
    param=repo/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
    e=dict(success=False,new_flights=0,new_seeds_used=[],commands=[],eeprom_before=common.fingerprint(param))
    def save(): (out/'evidence.json').write_text(json.dumps(e,indent=2)+'\n')
    def run(name,argv):
        with (out/(name+'.log')).open('x') as log:
            r=subprocess.run(argv,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=3600)
        e['commands'].append(dict(name=name,argv=argv,exit_code=r.returncode));save();print(name,r.returncode,flush=True)
        if r.returncode:raise RuntimeError(name+' failed; all evidence retained')
    try:
        e['head']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
        e['worktree']=subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True)
        if args.require_clean and e['worktree']:raise RuntimeError('Clean committed source required')
        if subprocess.check_output(['git','branch','--show-current'],cwd=repo,text=True).strip()!='research/sta-velocity-control':raise RuntimeError('Wrong branch')
        run('submodules',['git','submodule','status','--recursive'])
        if any(s[:1] in ('+','-','U') for s in (out/'submodules.log').read_text().splitlines()):raise RuntimeError('Submodule mismatch')
        run('submodule_worktrees',['git','submodule','foreach','--recursive','--quiet','git status --porcelain'])
        if (out/'submodule_worktrees.log').read_text():raise RuntimeError('Dirty submodule')
        common.validate_manifest()
        audit=common.fresh_seeds()
        if not audit['accepted']:raise RuntimeError('Seed history collision/invalid JSON: '+str(audit))
        # Do not create a second apparent registration with seed-valued keys.
        e['seed_audit']={k:audit[k] for k in ('files_parsed','scan_manifest_sha256','roots','excluded','accepted')}
        e['seed_audit']['design_registration_count']=len(audit['design_registrations'])
        current=capture();frozen=json.loads((common.CONFIG/'frozen.json').read_text())
        if current!=frozen:raise RuntimeError('Frozen asset/parameter/model/submodule snapshot changed')
        e['frozen_assets']=len(frozen['assets']);e['external_assets']=len(frozen['external_assets'])
        run('dry_run',['bash',str(common.CONFIG.parent/'run.sh')])
        run('historical',['python3',str(common.CONFIG.parent/'ax01/verify.py'),'--output',str(out/'historical')])
        old=json.loads((out/'historical/evidence.json').read_text());assert old['success']
        extra=0
        for name in ('test_protocol','test_targets'):
            run(name,['python3',str(common.CONFIG/(name+'.py'))])
            extra+=int(re.search(r'Ran (\d+) tests?',(out/(name+'.log')).read_text())[1])
        xml=out/'VelocityAblationTask.xml'
        run('VelocityAblationTask',[str(repo/'build/px4_sitl_test/unit-VelocityAblationTask'),'--gtest_output=xml:'+str(xml)])
        counts={k:int(v) for k,v in ET.parse(xml).getroot().attrib.items() if k in ('tests','failures','errors','disabled')}
        assert counts['tests']>0 and not any(counts[k] for k in ('failures','errors','disabled'))
        e['cpp_tests']=old['cpp_tests']+counts['tests'];e['python_tests']=old['python_tests']+extra
        e['excluded_historical_assertion']=old['v08_provenance_not_applicable']
        run('historical_ulog_replay',['python3',str(common.CONFIG/'replay.py'),'--output',str(out/'replay.json')])
        replay=json.loads((out/'replay.json').read_text());assert replay['success'];e['historical_logs']=len(replay['runs'])
        run('diff_check',['git','diff','--check'])
        unchanged=['src/modules/mc_pos_control/PositionControl/PositionControl.cpp','src/modules/mc_pos_control/PositionControl/StaVelocityProtection.cpp',
                   'src/modules/mc_pos_control/PositionControl/StaVelocityControl.cpp','src/modules/mc_rate_control','src/modules/ekf2','src/modules/sensors',
                   'src/modules/land_detector','msg','Tools/sitl_gazebo','sitl','sim_scripts','research/sta-velocity-control/v08']
        assert not subprocess.check_output(['git','diff',frozen['baseline_head'],'--',*unchanged],cwd=repo)
        e['protected_paths_unchanged']=unchanged
        metadata={p.attrib['name']:p for p in ET.parse(repo/'build/px4_sitl_default/parameters.xml').iter('parameter')}
        assert metadata['MPC_VCT_TEST'].attrib['default']=='0' and metadata['MPC_VCT_TEST'].findtext('max')=='8'
        e['model_sha256']=common.fingerprint(common.CONFIG/'models/iris.sdf')
        e['eeprom_after']=common.fingerprint(param);assert e['eeprom_after']==e['eeprom_before']
        e['firmware_sha256']=common.fingerprint(repo/'build/px4_sitl_default/bin/px4')
        e['ulog_format_bytes']=old['ulog_format_bytes'];e['success']=True
    finally:
        save()
        (out/'artifacts.sha256').write_text(''.join(f'{common.fingerprint(p)}  {p}\n' for p in sorted(out.rglob('*')) if p.is_file() and p.name!='artifacts.sha256'))
    print(json.dumps(e,indent=2))

if __name__=='__main__':main()
