#!/usr/bin/env python3
"""RI05 gate-specific offline verification/clean qualification; no flight launch."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time
import traceback
import xml.etree.ElementTree as ET

import protocol as p

HERE, REPO = p.HERE, p.REPO
RI01 = p.load_file('_ri05_original_tests', HERE.parent/'ri01/verify.py')
helper = p.load_file('_ri05_xml', REPO/'research/sta-velocity-control/regularized_sta/r01/verification/verify.py')
freeze = p.load_file('_ri05_freeze', HERE/'freeze.py')
OLD = REPO/'research/sta-velocity-control/regularized_sta'
EXTRA = ['unit-RegularizedIstaRegression', 'unit-RegularizedIstaProtection',
         'unit-RegularizedIstaPosition', 'unit-RegularizedIstaNonSitl',
         'functional-RegularizedIstaVelocityParam', 'functional-RegularizedIstaVelocityModule',
         'functional-VehicleIMU', 'functional-EKF2SelectorTiming', 'functional-EKF2Selector',
         'functional-EstimatorDiagnosticTopics']
TARGETS = ['unit-'+n for n in RI01.UNIT]+['functional-'+n for n in RI01.FUNCTIONAL]+EXTRA
EEPROM = REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
BINARY = REPO/'build/px4_sitl_default/bin/px4'
HISTORY = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016')


def python_tests():
    """Use the same frozen direct-suite inventory as archive validation."""
    return p.load_file("_ri05_verify_receipt", HERE/"receipt.py").python_scripts()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--gate', choices=p.GATES, default='C')
    parser.add_argument('--qualify', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    if p.DATA_ROOT not in out.parents or out.exists():
        raise ValueError('Fresh external evidence directory required')
    if args.qualify and p.DATA_ROOT/args.gate not in out.parents:
        raise ValueError('Qualification must be inside its exact gate directory')
    if args.qualify and p.git('status', '--porcelain'):
        raise ValueError('Clean committed source required')
    p.require_execution_authority(args.gate)
    # A missing manifest must fail before the costly regression, not when
    # constructing the final binding. Freeze explicitly before either phase.
    freeze.check(args.gate)
    out.mkdir(parents=True)
    env = {k:v for k,v in os.environ.items() if not k.startswith('GTEST_')}
    env['PATH'] = str(REPO/'.px4-python/bin')+':'+env['PATH']
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONPATH'] = ':'.join([str(REPO/'.px4-python'), str(REPO/'research/sta-velocity-control/scripts'),
                                '/home/yr/Desktop/codev doc/experiments/M00-20260912/python'])
    e = dict(stage='RI05-'+args.gate, success=False, clean=False, approved=False,
        source_head=p.git('rev-parse','HEAD'), commands=[], new_flights=0,
        qualification_requested=args.qualify, cpp_test_targets=[], python_tests_executed=[],
        eeprom_before=p.fingerprint(EEPROM), not_executed=['MATLAB/Simulink rerun','flight',
        'hardware','RI06','old R04/R05','tuning','push','Proper-ISTA integration'],
        counting='Unique completed C++ XML testcase identities; direct passing unittest leaf logs only',
        historical_scope_exclusions=['RI01 absent-kernel proof', 'RI02 closed production admission proof',
        'RI04 current-head zero-production-diff/protocol checks replaced by RI05 scoped admission/freeze tests; old receipt/tools tests retained',
        'old R03/V08 historical source-head qualifications; current freeze and mask/non-SITL tests replace them'],
        model_limit='Ideal, variable sample, noise, constrained and lagged models reported separately; '
        '18 expected tiny-float rejection trajectories and six infeasible-limit cases are not convergence passes')

    def save():
        (out/'evidence.json').write_text(json.dumps(e,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

    def run(name, argv, timeout=1800, cwd=REPO, unittest=False):
        log = out/(name+'.log')
        started = time.monotonic()
        with log.open('x') as stream:
            proc = subprocess.Popen(list(map(str,argv)),cwd=cwd,env=env,stdout=stream,
                                    stderr=subprocess.STDOUT,start_new_session=True)
            try:
                code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid,signal.SIGKILL); proc.wait(timeout=5)
                code = 124
        e['commands'].append(dict(name=name,argv=list(map(str,argv)),cwd=str(cwd),exit_code=code,
            wall_seconds=time.monotonic()-started,log_sha256=p.fingerprint(log)))
        save(); print(name,code,flush=True)
        if code:
            raise ValueError(name+' failed; raw evidence retained at '+str(out))
        if unittest:
            text = log.read_text()
            counts = re.findall(r'^Ran (\d+) tests? in [^\n]+$',text,re.MULTILINE)
            if len(counts)!=1 or int(counts[0])<1 or not re.search(r'^OK\s*$',text,re.MULTILINE):
                raise ValueError('Missing actual nonzero passing unittest count '+name)
            e['python_tests_executed'].append(dict(name=name,tests=int(counts[0]),log_sha256=p.fingerprint(log)))
        return log.read_text()

    try:
        if p.git('branch','--show-current') != 'research/ista-velocity-regularized':
            raise ValueError('Wrong branch')
        if len(TARGETS)!=48 or len(set(TARGETS))!=48 or p.REQUIRED_TARGETS!=set(TARGETS):
            raise ValueError('Required executable inventory changed')
        snap = freeze.check(args.gate)
        e['scope'] = freeze.scope(); e['submodules'] = snap['submodules']
        inputs = {str(REPO/n):sha for n,sha in snap['assets'].items()}
        inputs.update(snap['external_assets']); e['input_sha256'] = inputs
        shutil.copyfile(EEPROM,out/'eeprom_before.bin')
        shutil.copyfile(BINARY,out/'firmware_before.bin')
        e['firmware_before'] = p.fingerprint(BINARY)
        run('ri02_frozen_reference',['python3','-B',HERE.parent/'ri02/reference/freeze.py'])
        package = Path('/home/yr/Desktop/STA-ISTA-MATLAB-PX4')
        original = p.read(HERE.parent/'ri00/results/source_fingerprints.json')
        if not all(p.fingerprint(package/n)==v['sha256'] for n,v in original.items()):
            raise ValueError('Original MATLAB package changed')
        run('source_package',['sha256sum','--check','SHA256SUMS.txt'],cwd=package)
        run('recorded_failure_fixture', ['python3','-B',HERE/'replay_failed_fixture.py',
            '--output',out/'recorded_failure'])
        run('configure_tests',['make','tests','TESTFILTER=RegularizedIsta','-j4'])
        run('build_test_targets',['cmake','--build',REPO/'build/px4_sitl_test','--target',*TARGETS,'--parallel','4'])
        for target in TARGETS:
            run(target,[REPO/'build/px4_sitl_test'/target,'--gtest_output=xml:'+str(out/(target+'.xml'))],timeout=180)
            helper.xml_inventory([out/(target+'.xml')]); e['cpp_test_targets'].append(target)
        e['cpp_inventory'] = helper.xml_inventory(out.glob('*.xml'))
        regression = ET.parse(out/'unit-RegularizedIstaRegression.xml').getroot()
        e['sequence_properties'] = [dict(classname=c.attrib['classname'],name=c.attrib['name'],
            properties={x.attrib['name']:x.attrib['value'] for x in c.findall('properties/property')})
            for c in regression.iter('testcase')]
        run('strict_cxx14',['g++','-std=c++14','-pedantic-errors','-Wall','-Wextra','-Werror',
            '-fno-exceptions','-fno-rtti','-c',REPO/'src/modules/mc_pos_control/PositionControl/RegularizedIstaVelocityControl.cpp',
            '-o',out/'strict_kernel.o'])
        for index,path in enumerate(python_tests()):
            run(f'py{index:02d}_{path.parent.name}_{path.stem}',['python3','-B',path],unittest=True)
        run('r02_tools',['python3','-B','-m','unittest','discover','-s',OLD/'r02/tools','-p','test_*.py','-v'],unittest=True)
        run('model_reference',['python3','-B',HERE.parent/'ri01/model/check.py','--output',out/'model_reference'])
        e['model'] = p.read(out/'model_reference/summary.json')
        objects = p.read(out/'model_reference/objects.json')['trajectories']
        z = [row for row in objects if row['family'] == 'Z']
        if len(z) != 51 or {row['timing'] for row in z} != {'fixed_8ms','fixed_12ms','measured_sequence'}:
            raise ValueError('Missing real Z-gain independent object regressions')
        e['z_objects'] = dict(trajectories=len(z), gains=[2.,1.,.02,4.],
            kernel_updates=sum(row['steps'] for row in z),
            numerical_domain_stops=sum(row['numeric_domain_exhaustion'] is not None for row in z),
            infeasible_limit_counterexamples=sum(row['conclusion']=='infeasible_actuation_not_convergent' for row in z),
            max_double_reference_velocity_difference=max(row['max_double_reference_velocity_difference'] for row in z),
            production_z_mapping_tested_separately=True, theory_and_engineering_cases_not_pooled=True)
        # Historical acceptance is never recomputed into a new flight receipt.
        # Old X and Z logs retain their own canonical source/authority identities.
        for number in (1,2,3):
            source = HISTORY/'R03_revision09/A/batch01'/f'run{number:03d}'
            label = f'history_X_{number:03d}'
            run(label,['python3','-B',HERE.parent/'ri02/tools/replay.py',source,'--output',out/label],timeout=900)
        for number in (10,11,12):
            source = HISTORY/'R03_revision09/B/batch01'/f'run{number:03d}'
            label = f'history_Z_{number:03d}'
            run(label,['python3','-B',HERE.parent/'ri02/tools/replay.py',source,'--output',out/label],timeout=900)
        for gate, revision, numbers in [('C', 'R03_revision09', (19,20,21)),
                                       ('D', 'R03_revision11', (28,29,30))]:
            for number in numbers:
                source = HISTORY/revision/gate/'batch01'/f'run{number:03d}'
                label = f'history_{gate}_{number:03d}'
                run(label,['python3','-B',HERE.parent/'ri02/tools/replay.py',source,'--output',out/label],timeout=900)
        for number in (1,2,3):
            source = p.DATA_ROOT.parent/'RI03/A/batch01'/f'run{number:03d}'
            label = f'ri03_X_{number:03d}'
            run(label,['python3','-B',HERE.parent/'ri03/tools/analyzer.py',source,'--output',out/label],timeout=900)
            old = p.read(source/'r03_metrics.json')
            replayed = p.read(out/label/'r03_metrics.json')
            def canonical(value):
                return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=True)
            if canonical(old) != canonical(replayed) or p.fingerprint(source/'spectra.json') != p.fingerprint(out/label/'spectra.json'):
                raise ValueError('Accepted RI03 X science changed during read-only replay')
        for number in (1,2,3):
            source = p.DATA_ROOT.parent/'RI04_REVISION01/B/batch01'/f'run{number:03d}'
            label = f'ri04_Z_{number:03d}'
            run(label,['python3','-B',HERE.parent/'ri04_revision01/tools/analyzer.py',source,'--output',out/label],timeout=900)
            old = p.read(source/'r03_metrics.json')
            replayed = p.read(out/label/'r03_metrics.json')
            if canonical(old) != canonical(replayed) or p.fingerprint(source/'spectra.json') != p.fingerprint(out/label/'spectra.json'):
                raise ValueError('Accepted RI04 Z science changed during read-only replay')
        run('original_failure_exact_prefix',['python3','-B',OLD/'r03_position11/audit.py',
            '--output',out/'historical_failure_audit.json'],timeout=900)
        run('build_sitl',['make','px4_sitl_default','-j4'])
        run('gazebo_build_only',['env','DONT_RUN=1','make','px4_sitl_default','gazebo_iris','-j4'])
        schemas = {}
        for topic in ('velocity_ctrl_selection','sta_velocity_ctrl_status'):
            generated = REPO/'build/px4_sitl_default/msg/topics_sources'/(topic+'.cpp')
            text = generated.read_text()
            fields = re.search(r'__orb_'+topic+r'_fields\[\]\s*=\s*"([^"]+)"',text)
            if fields is None or 'ORB_DEFINE('+topic+',' not in text:
                raise ValueError('Missing actual generated format/registration '+topic)
            length = len((topic+':'+fields[1]).encode())+1
            header = REPO/'build/px4_sitl_default/uORB/topics'/(topic+'.h')
            if length>=1500 or not re.search(r'ORB_QUEUE_LENGTH\s*=\s*8',header.read_text()):
                raise ValueError('ULog format/queue invalid '+topic)
            schemas[topic] = dict(ulog_format_bytes_including_nul=length,queue=8,
                generated_sha256=p.fingerprint(generated),header_sha256=p.fingerprint(header))
        e['generated_schema'] = schemas
        nodes = {n.attrib['name']:n for n in ET.parse(REPO/'build/px4_sitl_default/parameters.xml').iter('parameter')}
        if float(nodes['MPC_VC_MODE'].attrib['default'])!=0 or not any(n.attrib.get('code')=='4' for n in nodes['MPC_VC_MODE'].iter('value')):
            raise ValueError('MODE4/PID-default metadata invalid')
        if nodes['SDLOG_PROFILE'].findtext('max')!='4095' or int(nodes['SDLOG_PROFILE'].attrib['default'])!=1:
            raise ValueError('Logger metadata changed')
        e['mode_metadata'] = ET.tostring(nodes['MPC_VC_MODE'],encoding='unicode')
        e['counts'] = dict(cpp_unique_tests=e['cpp_inventory']['unique_tests'],cpp_targets=len(TARGETS),
            python_tests=sum(x['tests'] for x in e['python_tests_executed']),model_oracle_tests=e['model']['oracle_tests'],
            historical_accepted_replays=18,historical_failure_audits=2,new_flights=0)
        if e['counts']['cpp_unique_tests']<p.MIN_CPP or e['counts']['python_tests']<p.MIN_PYTHON:
            raise ValueError('Missing minimum actual regression inventory '+str(e['counts']))
        if any(p.fingerprint(name)!=sha for name,sha in inputs.items()):
            raise ValueError('Frozen verification input changed during execution')
        if freeze.submodules()!=e['submodules'] or freeze.scope()!=e['scope'] or p.fingerprint(EEPROM)!=e['eeprom_before']:
            raise ValueError('Submodule/source/EEPROM changed during verification')
        run('diff_check',['git','diff','--check','HEAD'])
        e['clean'] = not bool(p.git('status','--porcelain'))
        if args.qualify:
            if not e['clean'] or p.git('rev-parse','HEAD')!=e['source_head']:
                raise ValueError('Source changed during qualification')
            if e['source_head'] not in (REPO/'build/px4_sitl_default/src/lib/version/build_git_version.h').read_text():
                raise ValueError('Firmware version is not clean source HEAD')
            freeze.check(args.gate)
        e.update(p.qualification_binding(args.gate,e['source_head'],p.fingerprint(BINARY)))
        e['success'] = True; e['approved'] = bool(args.qualify)
    except BaseException as error:
        e.update(error=repr(error),traceback=traceback.format_exc()); raise
    finally:
        e['eeprom_final'] = p.fingerprint(EEPROM)
        e['evidence_files'] = {str(x):p.fingerprint(x) for x in sorted(out.rglob('*')) if x.is_file() and x!=out/'evidence.json'}
        save()
    if args.qualify:
        try:
            with (out/'authorization.json').open('x') as stream:
                json.dump(p.authorization_binding(e,out/'evidence.json'),stream,indent=2); stream.write('\n')
            p.require_qualification(args.gate,e['source_head'],out/'evidence.json')
        except BaseException as error:
            e.update(success=False,approved=False,error=repr(error),traceback=traceback.format_exc())
            save()
            raise
    print(json.dumps(dict(success=e['success'],approved=e['approved'],counts=e['counts'],new_flights=0)))


if __name__ == '__main__':
    main()
