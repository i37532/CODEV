#!/usr/bin/env python3
"""Actual non-flight regression and source qualification for the new D-only9."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import traceback
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
p=load('_up08_verify_protocol',HERE/'protocol.py')
freeze=load('_up08_verify_freeze',HERE/'freeze.py')
R02=load('_up08_old_helpers',HERE.parent/'r02/verification/verify.py')
helper=R02.helper;REPO=p.REPO
EXTRA=[('VehicleIMU','functional'),('EKF2SelectorTiming','functional'),('EKF2Selector','functional'),
       ('EstimatorDiagnosticTopics','functional'),('VelocityAxes','unit')]
TARGETS=R02.TESTS+EXTRA
EEPROM=REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--gate',choices=p.GATES,required=True)
    parser.add_argument('--qualify',action='store_true');args=parser.parse_args();out=args.output.resolve()
    if out.exists() or p.DATA_ROOT not in out.parents:raise ValueError('Fresh diagnostic evidence root required')
    if args.qualify and p.git('status','--porcelain'):raise ValueError('Qualification requires clean committed source')
    p.require_execution_authority(args.gate);out.mkdir(parents=True)
    env=os.environ.copy();removed={k:env.pop(k) for k in list(env) if k.startswith('GTEST_')}
    env['PATH']=str(REPO/'.px4-python/bin')+':'+env['PATH'];env['PYTHONDONTWRITEBYTECODE']='1'
    env['PYTHONPATH']=':'.join([str(REPO/'.px4-python'),str(REPO/'research/sta-velocity-control/scripts'),
        '/home/yr/Desktop/codev doc/experiments/M00-20260912/python'])
    e=dict(success=False,clean=False,source_head=p.git('rev-parse','HEAD'),commands=[],new_flights=0,
        removed_gtest_environment=removed,qualification_requested=args.qualify,cpp_test_targets=[],
        eeprom_before=p.fingerprint(EEPROM),not_executed=['MATLAB','flight','hardware','R03 acceptance','R04/R05'],
        excluded_legacy_scope_assertions=[
            'AX01 final git diff against its historical upstream source: now explicitly authorized upstream fix',
            'R02 closed-admission and old-source qualification: remain historical, not new proof',
            'V08 unchanged-production provenance: obsolete for this new source',
            'revision06 RevisionAuditTest.test_actual_scope_old_source_and_retained_counts: asserts zero upstream change at old entry; replaced by current freeze.scope'],
        test_lockstep_limit='Functional tests use test build without ENABLE_LOCKSTEP_SCHEDULER; default SITL build has real lockstep. No claim that functional fixture reproduces original initial 28ms pause')
    def save():
        (out/'evidence.json').write_text(json.dumps(e,indent=2)+'\n')
    def run(name,argv,timeout=1200,cwd=REPO):
        started=time.monotonic()
        with (out/(name+'.log')).open('x') as f:
            proc=subprocess.Popen(argv,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
            try:code=proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # Only this command's newly created process group is ours.
                os.killpg(proc.pid,signal.SIGTERM)
                try:proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
                code=124
        e['commands'].append(dict(name=name,argv=list(map(str,argv)),cwd=str(cwd),exit_code=code,wall_seconds=time.monotonic()-started))
        save();print(name,code,flush=True)
        if code:raise ValueError(name+' failed; preserve '+str(out))
    try:
        if p.git('branch','--show-current')!='research/sta-velocity-regularized':raise ValueError('Wrong branch')
        snap=freeze.check(args.gate) if args.qualify else freeze.capture(args.gate);e['scope']=freeze.scope();e['submodules']=snap['submodules']
        inputs={str(REPO/n):sha for n,sha in snap['assets'].items()};inputs.update(snap['external_assets']);e['input_sha256']=inputs
        e['reference']=R02.check_reference()
        run('build_test_targets',['cmake','--build',str(REPO/'build/px4_sitl_test'),'--target',
            *[kind+'-'+name for name,kind in TARGETS],'--parallel','4'])
        for name,kind in TARGETS:
            target=kind+'-'+name
            run(target,['timeout','60s',str(REPO/'build/px4_sitl_test'/target),'--gtest_output=xml:'+str(out/(name+'.xml'))],timeout=70)
            helper.xml_inventory([out/(name+'.xml')]);e['cpp_test_targets'].append(target)
        # Unchanged V07 functional verifier does not request its old frozen-source
        # qualification. AX01's later upstream-unchanged assertion is not called.
        run('v07_functional',['python3',str(REPO/'research/sta-velocity-control/v07/protocol07/verify.py'),'--output',str(out/'v07')])
        if p.read(out/'v07/evidence.json').get('success') is not True:raise ValueError('V07 regression failed')
        ax01=REPO/'research/sta-velocity-control/axis_ablation/ax01'
        for name in ('test_interface.py','legacy_tuning.py'):
            run('ax01_'+Path(name).stem,['python3',str(ax01/name)])
        v08=REPO/'research/sta-velocity-control/v08'
        for folder,name in [('protocol02','test_cli_clock'),('protocol03b','test_validation'),('protocol03b','test_task_output'),
                ('protocol04','test_pilot'),('protocol04','test_design'),('protocol04','test_formal_design'),
                ('evidence_tools','test_replay_batch'),('protocol05','test_mass'),('formal','test_runtime'),
                ('formal','test_formal_package'),('evidence_tools','test_qualified_gate_summary')]:
            run('v08_'+name,['python3',str(v08/folder/(name+'.py'))])
        run('r02_tools',['python3','-m','unittest','discover','-s',str(HERE.parent/'r02/tools'),'-p','test_*.py','-v'])
        for folder in ('r03_numeric05','r03_handoff06','r03_monitor02','r03_prearm04'):
            for path in sorted((HERE.parent/folder).glob('test_*.py')):
                run(folder+'_'+path.stem,['python3',str(path)])
        for path in sorted((HERE.parent/'r03_revision06').glob('test_*.py')):
            # Scope tests are specific to the immutable old06 zero-production-change
            # policy. Their mocks remain valid; current qualification uses freeze.scope.
            if path.name=='test_revision_audit.py':
                run('old06_'+path.stem,['python3','-c',
                    "import importlib.util,unittest;s=importlib.util.spec_from_file_location('old_audit',"+repr(str(path))+
                    ");m=importlib.util.module_from_spec(s);s.loader.exec_module(m);names=unittest.defaultTestLoader.getTestCaseNames(m.RevisionAuditTest);"+
                    "suite=unittest.TestSuite(m.RevisionAuditTest(n) for n in names if n!='test_actual_scope_old_source_and_retained_counts');"+
                    "r=unittest.TextTestRunner(verbosity=2).run(suite);raise SystemExit(not r.wasSuccessful())"])
            else:run('old06_'+path.stem,['python3',str(path)])
        for path in sorted((HERE.parent/'r03_upstream08').glob('test_*.py')):
            run('up08_'+path.stem,['python3',str(path)])
        for folder in ('r03_revision09','r03_warmup10'):
            for path in sorted((HERE.parent/folder).glob('test_*.py')):
                run(folder+'_'+path.stem,['python3',str(path)])
        tests=sorted(HERE.glob('test_*.py'))
        if not tests:raise ValueError('No current diagnostic tests')
        for path in tests:run(path.stem,['python3',str(path)])
        for number in (28,29,30):
            source=p.EXTERNAL/'R03_revision06/D/batch01'/f'run{number:03d}'
            for order in ('runner-first','analyzer-first'):
                label=f'history_{number}_{order}'
                run(label,['python3',str(HERE.parent/'r03_upstream08/analyzer.py'),str(source),'--output',str(out/label),
                    '--historical-diagnostic','--import-order',order],timeout=600)
                record=p.read(out/label/'evidence.json')
                if (record.get('original_accepted') is not (number!=30) or record.get('accepted') is not False
                        or record.get('source_inputs_unchanged') is not True or record.get('new_flights')!=0):
                    raise ValueError('Historical verdict/input changed')
        run('sitl_build',['make','px4_sitl_default','-j4'])
        run('gazebo_build_only',['env','DONT_RUN=1','make','px4_sitl_default','gazebo_iris','-j4'])
        e['metadata']=R02.check_metadata()
        nodes={x.attrib['name']:x for x in ET.parse(REPO/'build/px4_sitl_default/parameters.xml').iter('parameter')}
        n=nodes['SDLOG_PROFILE']
        if int(n.attrib['default'])!=1 or n.findtext('max')!='4095':raise ValueError('Logger metadata/default mismatch')
        e['logger_metadata']=dict(default=1,max=4095,added_bit=11)
        e['cpp_inventory']=helper.xml_inventory(out.rglob('*.xml'));e['python_inventory']=helper.python_leaf_counts(out)
        e['counts']=dict(cpp_unique_tests=e['cpp_inventory']['unique_tests'],python_tests=e['python_inventory']['tests'],
            fixed_legacy_samples=32768,fixed_same_sample_recalculations=256,new_flights=0)
        fixed=helper.xml_inventory([out/'RegularizedVelocityRegression.xml'])
        if fixed['unique_tests']!=16:raise ValueError('Missing fixed-sequence matrix')
        if e['counts']['cpp_unique_tests']<525 or e['counts']['python_tests']<800:raise ValueError('Missing regression cases')
        for name,sha in inputs.items():
            if p.fingerprint(name)!=sha:raise ValueError('Input changed during verification '+name)
        if freeze.submodules()!=e['submodules'] or p.fingerprint(EEPROM)!=e['eeprom_before']:raise ValueError('Submodule/EEPROM changed')
        if freeze.scope()!=e['scope']:raise ValueError('Production scope changed')
        run('diff_check',['git','diff','--check'])
        e['clean']=not bool(p.git('status','--porcelain'))
        if args.qualify:
            if not e['clean'] or p.git('rev-parse','HEAD')!=e['source_head']:raise ValueError('Dirty/new HEAD during qualification')
            if e['source_head'] not in (REPO/'build/px4_sitl_default/src/lib/version/build_git_version.h').read_text():raise ValueError('Firmware not built at source HEAD')
            freeze.check(args.gate)
        e.update(p.qualification_binding(args.gate,e['source_head'],p.fingerprint(REPO/'build/px4_sitl_default/bin/px4')));e['success']=True
    except BaseException as error:
        e.update(error=repr(error),traceback=traceback.format_exc());raise
    finally:
        e['eeprom_final']=p.fingerprint(EEPROM)
        e['evidence_files']={str(x):p.fingerprint(x) for x in sorted(out.rglob('*')) if x.is_file() and x!=out/'evidence.json'}
        save()
    if args.qualify:
        with (out/'authorization.json').open('x') as f:json.dump(p.authorization_binding(e,out/'evidence.json'),f,indent=2);f.write('\n')
    print(json.dumps(dict(success=e['success'],counts=e['counts'],new_flights=0)))


if __name__=='__main__':main()
