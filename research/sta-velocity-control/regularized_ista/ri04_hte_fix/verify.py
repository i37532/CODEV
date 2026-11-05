#!/usr/bin/env python3
"""Offline HTE repair regression only. No qualification, authority or flight.

Inherited inventories are read-only; no old freeze.capture/check is invoked.
Historical analyses bind their original Git objects and retain old verdicts.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
ROOT = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI04_HTE_FIX')
RI04 = HERE.parent/'ri04'
sys.path.insert(0, str(RI04))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


old = load('_ri04_hte_inventory', RI04/'verify.py')
receipt = load('_ri04_hte_receipt', RI04/'receipt.py')
TARGETS = old.TARGETS
EEPROM, BINARY = old.EEPROM, old.BINARY
ALLOWED = {'src/modules/mc_pos_control/PositionControl/PositionControl.cpp',
           'src/modules/mc_pos_control/PositionControl/RegularizedIstaPositionTest.cpp',
           'src/modules/mc_pos_control/RegularizedIstaVelocityModuleTest.cpp'}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO).decode().strip()


def read(path):
    return json.loads(Path(path).read_text())


def input_snapshot():
    frozen = read(RI04/'gates/B/frozen.json')
    current, changed = {}, {}
    for name, digest in frozen['assets'].items():
        actual = sha(REPO/name)
        current[str(REPO/name)] = actual
        if actual != digest:
            require(name in ALLOWED, 'Unexpected inherited source change '+name)
            changed[name] = dict(old_sha256=digest, new_sha256=actual)
    for name, digest in frozen['external_assets'].items():
        require(sha(name) == digest, 'External model/plugin changed '+name)
        current[name] = digest
    for path in sorted(HERE.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            current[str(path)] = sha(path)
    return dict(inputs=current, changed_from_ri04_flight_source=changed,
                inherited_frozen_sha256=sha(RI04/'gates/B/frozen.json'),
                submodules=old.freeze.submodules())


def python_commands():
    commands = receipt.python_commands()
    for path in sorted(HERE.glob('test_*.py')):
        commands['hte_'+path.stem] = ['python3', '-B', str(path)]
    return commands


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    require(ROOT in out.parents and not out.exists(), 'Fresh new offline evidence directory required')
    out.mkdir(parents=True)
    env = {k:v for k,v in os.environ.items() if not k.startswith('GTEST_')}
    env.update(PYTHONDONTWRITEBYTECODE='1',
        PATH=str(REPO/'.px4-python/bin')+':'+os.environ['PATH'],
        PYTHONPATH=':'.join([str(REPO/'.px4-python'), str(REPO/'research/sta-velocity-control/scripts'),
                          '/home/yr/Desktop/codev doc/experiments/M00-20260912/python']))
    evidence = dict(stage='RI04_HTE_FIX offline only', success=False, approved=False,
        flight_authorized=False, flight_accepted=False, new_flights=0, new_budget=0,
        original_ri04_status='failed unchanged; 3 attempts, 2 accepted, 1 failed, 6 unattempted',
        source_head=git('rev-parse','HEAD'), working_tree=git('status','--porcelain'),
        commands=[], cpp_test_targets=[], python_tests_executed=[],
        not_executed=['new flight','new qualification','MATLAB rerun','tuning','RI05','hardware','push'])

    def save():
        (out/'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False)+'\n')

    def run(name, argv, timeout=1800, cwd=REPO, unittest=False):
        log = out/(name+'.log'); start = time.monotonic()
        with log.open('x') as stream:
            process = subprocess.Popen(list(map(str, argv)), cwd=cwd, env=env, stdout=stream,
                stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=5)
                code = 124
        evidence['commands'].append(dict(name=name, argv=list(map(str,argv)), cwd=str(cwd),
            exit_code=code, wall_seconds=time.monotonic()-start, log_sha256=sha(log)))
        save(); print(name, code, flush=True)
        require(code == 0, name+' failed; evidence retained')
        if unittest:
            count = receipt.unittest_count(log.read_bytes(), name)
            evidence['python_tests_executed'].append(dict(name=name, tests=count, log_sha256=sha(log)))
        return log

    try:
        require(git('branch','--show-current') == 'research/ista-velocity-regularized', 'Wrong branch')
        require(len(TARGETS) == len(set(TARGETS)) == 48, 'Target inventory changed')
        snapshot = input_snapshot(); evidence['input_snapshot'] = snapshot
        evidence['eeprom_before'] = sha(EEPROM)
        shutil.copyfile(EEPROM, out/'eeprom_before.bin')
        evidence['firmware_before'] = sha(BINARY)
        run('ri02_frozen_reference', ['python3','-B',HERE.parent/'ri02/reference/freeze.py'])
        package = Path('/home/yr/Desktop/STA-ISTA-MATLAB-PX4')
        original = read(HERE.parent/'ri00/results/source_fingerprints.json')
        require(all(sha(package/n) == v['sha256'] for n,v in original.items()), 'Original source package changed')
        run('source_package', ['sha256sum','--check','SHA256SUMS.txt'], cwd=package)
        run('recorded_failure_fixture', ['python3','-B',HERE/'fixture.py','--output',out/'recorded_failure'])
        run('configure_tests', ['make','tests','TESTFILTER=RegularizedIsta','-j4'])
        run('build_test_targets', ['cmake','--build',REPO/'build/px4_sitl_test','--target',*TARGETS,'--parallel','4'])
        for target in TARGETS:
            run(target, [REPO/'build/px4_sitl_test'/target, '--gtest_output=xml:'+str(out/(target+'.xml'))], timeout=180)
            receipt.completed_cases((out/(target+'.xml')).read_bytes(), target)
            evidence['cpp_test_targets'].append(target)
        evidence['cpp_inventory'] = old.helper.xml_inventory(out.glob('*.xml'))
        run('strict_cxx14', ['g++','-std=c++14','-pedantic-errors','-Wall','-Wextra','-Werror',
            '-fno-exceptions','-fno-rtti','-c',REPO/'src/modules/mc_pos_control/PositionControl/RegularizedIstaVelocityControl.cpp',
            '-o',out/'strict_kernel.o'])
        for name, argv in python_commands().items():
            run(name, argv, unittest=True)
        run('model_reference', ['python3','-B',HERE.parent/'ri01/model/check.py','--output',out/'model_reference'])
        evidence['model'] = read(out/'model_reference/summary.json')
        require(evidence['model']['oracle_tests'] == 6, 'Missing independent model oracles')
        replay_records = []
        for task, numbers in (('X',(1,2,3)), ('Z',(10,11,12))):
            for number in numbers:
                gate = 'A' if task == 'X' else 'B'
                source = old.HISTORY/('R03_revision09/'+gate+'/batch01')/f'run{number:03d}'
                label = f'history_{task}_{number:03d}'
                run(label, ['python3','-B',HERE.parent/'ri02/tools/replay.py',source,'--output',out/label], timeout=900)
                replay_records.append(dict(source=str(source), output=str(out/label), original_verdict_preserved=True))
        for number in (1,2,3):
            source = ROOT.parent/'RI03/A/batch01'/f'run{number:03d}'
            label = f'ri03_X_{number:03d}'
            run(label, ['python3','-B',HERE.parent/'ri03/tools/analyzer.py',source,'--output',out/label], timeout=900)
            require(canonical(read(source/'r03_metrics.json')) == canonical(read(out/label/'r03_metrics.json'))
                and sha(source/'spectra.json') == sha(out/label/'spectra.json'), 'Historical RI03 science differs')
            replay_records.append(dict(source=str(source), output=str(out/label), exact_metrics_types_and_spectra=True))
        evidence['historical_accepted_replays'] = replay_records
        run('original_failure_exact_prefix', ['python3','-B',old.OLD/'r03_position11/audit.py',
                                             '--output',out/'historical_failure_audit.json'], timeout=900)
        run('build_sitl', ['make','px4_sitl_default','-j4'])
        run('gazebo_build_only', ['env','DONT_RUN=1','make','px4_sitl_default','gazebo_iris','-j4'])
        schemas = {}
        for topic in ('velocity_ctrl_selection','sta_velocity_ctrl_status'):
            generated = REPO/'build/px4_sitl_default/msg/topics_sources'/(topic+'.cpp')
            text = generated.read_text()
            match = re.search(r'__orb_'+topic+r'_fields\[\]\s*=\s*"([^"]+)"', text)
            require(match and 'ORB_DEFINE('+topic+',' in text, 'Missing actual format/registration')
            size = len((topic+':'+match[1]).encode())+1
            header = REPO/'build/px4_sitl_default/uORB/topics'/(topic+'.h')
            require(size < 1500 and re.search(r'ORB_QUEUE_LENGTH\s*=\s*8',header.read_text()), 'ULog format/queue')
            schemas[topic] = dict(bytes_including_nul=size, queue=8, generated_sha256=sha(generated), header_sha256=sha(header))
        evidence['generated_schema'] = schemas
        nodes = {x.attrib['name']:x for x in ET.parse(REPO/'build/px4_sitl_default/parameters.xml').iter('parameter')}
        require(float(nodes['MPC_VC_MODE'].attrib['default']) == 0
                and any(x.attrib.get('code') == '4' for x in nodes['MPC_VC_MODE'].iter('value')), 'PID default/MODE4')
        require(nodes['SDLOG_PROFILE'].findtext('max') == '4095'
                and nodes['SDLOG_PROFILE'].attrib['default'] == '1', 'Logger defaults')
        counts = dict(cpp_unique_tests=evidence['cpp_inventory']['unique_tests'], cpp_targets=48,
            python_tests=sum(x['tests'] for x in evidence['python_tests_executed']),
            model_oracle_tests=6, historical_accepted_replays=9, original_failure_audits=2, new_flights=0)
        require(counts['cpp_unique_tests'] >= 698 and counts['python_tests'] >= 872, 'Missing actual regression inventory')
        evidence['counts'] = counts
        require(input_snapshot() == snapshot, 'Verification source/assets changed during run')
        require(git('rev-parse','HEAD') == evidence['source_head'] and sha(EEPROM) == evidence['eeprom_before'], 'HEAD/EEPROM changed')
        run('diff_check', ['git','diff','--check','HEAD'])
        evidence['firmware_after'] = sha(BINARY)
        evidence['success'] = True
    except BaseException as error:
        evidence.update(error=repr(error), traceback=traceback.format_exc())
        raise
    finally:
        evidence['eeprom_final'] = sha(EEPROM)
        evidence['evidence_files'] = {str(x):sha(x) for x in sorted(out.rglob('*')) if x.is_file() and x != out/'evidence.json'}
        save()
    try:
        evidence['independent_leaf_receipt'] = receipt.validate(evidence, out/'evidence.json', set(TARGETS), 872,
                                                               expected_python_commands=python_commands())
    except BaseException as error:
        evidence.update(success=False, error=repr(error), traceback=traceback.format_exc())
        raise
    finally:
        save()
    print(json.dumps(dict(success=True, approved=False, flight_authorized=False, counts=evidence['counts'])))


if __name__ == '__main__':
    main()
