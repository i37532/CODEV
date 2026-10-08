"""Offline AX04 verification; no simulator launch. Qualify only clean final HEAD."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import common
from design import BASE_HEAD, OLD
from freeze import capture, PRODUCTION


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--historical-evidence',type=Path,required=True)
    p.add_argument('--qualify',action='store_true')
    args=p.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    repo=common.REPO;env=os.environ.copy()
    env['PYTHONPATH']=str(repo/'.px4-python')+':/home/yr/Desktop/codev doc/experiments/M00-20260912/python:'+env.get('PYTHONPATH','')
    env['PATH']=str(repo/'.px4-python/bin')+':'+env['PATH']
    param=repo/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
    e=dict(success=False,new_flights=0,commands=[],eeprom_before=common.fingerprint(param))
    def save():
        (out/'evidence.json').write_text(json.dumps(e,indent=2)+'\n')
    def run(name,argv):
        with (out/(name+'.log')).open('x') as stream:
            r=subprocess.run(argv,cwd=repo,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=3600)
        e['commands'].append(dict(name=name,argv=argv,exit_code=r.returncode));save()
        print(name,r.returncode,flush=True)
        if r.returncode:raise RuntimeError(name+' failed; evidence preserved')
    try:
        e['source_head']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
        e['workspace']=subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True)
        if args.qualify and e['workspace']:raise RuntimeError('Only final clean commit can qualify')
        if subprocess.check_output(['git','branch','--show-current'],cwd=repo,text=True).strip()!='research/sta-velocity-control':raise RuntimeError('Wrong branch')
        run('submodules',['git','submodule','status','--recursive'])
        if any(x[:1] in ('+','-','U') for x in (out/'submodules.log').read_text().splitlines()):raise RuntimeError('Submodule mismatch')
        run('submodule_clean',['git','submodule','foreach','--recursive','--quiet','git status --porcelain'])
        if (out/'submodule_clean.log').read_text():raise RuntimeError('Dirty submodule')
        common.validate_manifest()
        audit=common.fresh_seeds()
        if not audit['accepted']:raise RuntimeError('Formal seed collision/invalid JSON '+str(audit))
        e['seed_audit']={k:audit[k] for k in ('accepted','files_parsed','scan_manifest_sha256','roots','excluded')}
        e['seed_audit']['registered_matches']=len(audit['design_registrations'])
        prior=json.loads(args.historical_evidence.read_text())
        if not prior['success'] or prior['new_flights']!=0:raise RuntimeError('Missing actual AX04 historical regression')
        # Only evidence collected in THIS AX04 invocation, never historic pass counts.
        if 'AX04' not in str(args.historical_evidence.resolve()):raise RuntimeError('Historical stage counts not current evidence')
        e['historical_evidence']=dict(path=str(args.historical_evidence),sha256=common.fingerprint(args.historical_evidence))
        if args.qualify:
            run('build_sitl',['make','px4_sitl_default','-j4'])
            env['DONT_RUN']='1'
            run('build_gazebo_only',['make','px4_sitl_default','gazebo_iris','-j4'])
            env.pop('DONT_RUN')
        run('snapshot',['python3',str(common.CONFIG/'freeze.py'),'--check'])
        run('dry_run',['python3',str(common.CONFIG/'run.py')])
        extra=0
        for folder,file in ((OLD,'test_protocol.py'),(OLD,'test_targets.py'),(OLD.parent/'ax03','test_collect.py'),(common.CONFIG,'test_formal.py')):
            name=folder.name+'_'+file.removesuffix('.py')
            run(name,['python3',str(folder/file)])
            extra+=int(re.search(r'Ran (\d+) tests?',(out/(name+'.log')).read_text())[1])
        xml=out/'VelocityAblationTask.xml'
        run('VelocityAblationTask',[str(repo/'build/px4_sitl_test/unit-VelocityAblationTask'),'--gtest_output=xml:'+str(xml)])
        counts={k:int(v) for k,v in ET.parse(xml).getroot().attrib.items() if k in ('tests','errors','failures','disabled')}
        if counts['tests']<=0 or any(counts[k] for k in ('errors','failures','disabled')):raise RuntimeError('No passing C++ tests')
        e['cpp_tests']=prior['cpp_tests']+counts['tests'];e['python_tests']=prior['python_tests']+extra
        # Full frozen Monte Carlo count on synthetic accepted data, then the
        # actual empty outcomes. Only compact counts written (no fake flights).
        run('statistics_full_counts',['python3',str(common.CONFIG/'verify_statistics.py')])
        e['synthetic_statistics']=json.loads((out/'statistics_full_counts.log').read_text())
        frozen=json.loads((common.CONFIG/'frozen.json').read_text())
        for rel in PRODUCTION+['research/sta-velocity-control/v08','research/sta-velocity-control/axis_ablation/ax02','research/sta-velocity-control/axis_ablation/ax03','sim_scripts']:
            if subprocess.check_output(['git','diff',BASE_HEAD,'--',rel],cwd=repo):raise RuntimeError('Protected path changed '+rel)
        e['frozen_sha256']=common.fingerprint(common.CONFIG/'frozen.json')
        e['execution_sha256']=common.fingerprint(common.CONFIG/'execution.json')
        e['asset_count']=len(frozen['assets']);e['external_asset_count']=len(frozen['external_assets'])
        e['firmware_sha256']=common.fingerprint(repo/'build/px4_sitl_default/bin/px4')
        if args.qualify:
            version=(repo/'build/px4_sitl_default/src/lib/version/build_git_version.h').read_text()
            if e['source_head'] not in version:raise RuntimeError('Final firmware not built at exact source commit')
        e['eeprom_after']=common.fingerprint(param)
        if e['eeprom_before']!=e['eeprom_after']:raise RuntimeError('Parameters mutated')
        import run_v00
        if run_v00.active_simulators():raise RuntimeError('Unexpected simulator; no process killed')
        run('diff_check',['git','diff','--check'])
        e['success']=True
        save()
        if args.qualify:
            if subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True):raise RuntimeError('Source changed during qualification')
            archive=out/'px4';shutil.copy2(repo/'build/px4_sitl_default/bin/px4',archive)
            if common.fingerprint(archive)!=e['firmware_sha256']:raise RuntimeError('Archive mismatch')
            receipt={k:e[k] for k in ('source_head','success','new_flights','frozen_sha256','execution_sha256','firmware_sha256','cpp_tests','python_tests')}
            receipt.update(evidence_path=str(out/'evidence.json'),evidence_sha256=common.fingerprint(out/'evidence.json'),firmware_archive=str(archive),scope='AX04 offline qualification only, NOT AX05 flight authorization')
            with common.QUALIFICATION.open('x') as stream:json.dump(receipt,stream,indent=2);stream.write('\n')
    finally:
        save()
        (out/'artifacts.sha256').write_text(''.join(f'{common.fingerprint(f)}  {f}\n' for f in sorted(out.rglob('*')) if f.is_file() and f.name!='artifacts.sha256'))
    print(json.dumps({k:e[k] for k in ('success','cpp_tests','python_tests','new_flights')}))


if __name__=='__main__':main()
