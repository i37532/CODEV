#!/usr/bin/env python3
"""RI02 offline C++/metadata/build qualification; never launches PX4 or Gazebo."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import time
import traceback
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
BASE = '2f19cefc850ef4b77a8bcdc455aaec193f3da331'
MODULE = 'src/modules/mc_pos_control/'
POSITION = MODULE + 'PositionControl/'
ALLOWED = {MODULE + name for name in (
    'CMakeLists.txt', 'MulticopterPositionControl.cpp', 'MulticopterPositionControl.hpp',
    'mc_pos_control_params.c', 'RegularizedVelocityModuleTest.cpp',
    'RegularizedIstaVelocityModuleTest.cpp')}
ALLOWED |= {POSITION + name for name in (
    'CMakeLists.txt', 'PositionControl.cpp', 'PositionControl.hpp',
    'RegularizedIstaVelocityControl.cpp', 'RegularizedIstaVelocityControl.hpp',
    'RegularizedIstaVelocityControlTest.cpp', 'RegularizedVelocityIntegrationTest.cpp',
    'StaVelocityProtection.cpp', 'StaVelocityProtection.hpp', 'VelocityControlSelector.hpp',
    'RegularizedIstaPositionTest.cpp', 'RegularizedIstaProtectionTest.cpp',
    'RegularizedIstaRegressionTest.cpp', 'RegularizedIstaVelocityParamTest.cpp')}
ALLOWED.add('msg/velocity_ctrl_selection.msg')
PRODUCTION = ('src', 'msg', 'Tools', 'platforms', 'sitl', 'ROMFS', 'boards')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RI01 = load('ri02_original_verifier', HERE.parent / 'ri01/verify.py')
XML = load('ri02_xml_counter', REPO / 'research/sta-velocity-control/regularized_sta/r01/verification/verify.py')
sha, require = RI01.sha, RI01.require


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.resolve()
    require(out != REPO and REPO not in out.parents, 'External evidence only')
    out.mkdir(parents=True, exist_ok=False)
    env = {k: v for k, v in os.environ.items() if not k.startswith('GTEST_')}
    env['PATH'] = str(REPO / '.px4-python/bin') + ':' + env['PATH']
    env['PYTHONPATH'] = ':'.join([str(REPO / '.px4-python'),
        str(REPO / 'research/sta-velocity-control/scripts'),
        '/home/yr/Desktop/codev doc/experiments/M00-20260912/python', env.get('PYTHONPATH', '')])
    param = REPO / 'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
    binary = REPO / 'build/px4_sitl_default/bin/px4'
    result = dict(stage='RI02', baseline=BASE, success=False, commands=[], new_flights=0,
        new_seeds=[], not_executed=['Gazebo/PX4 runtime', 'MODE4 flight ULog', 'MATLAB/Simulink rerun',
        'flight tuning', 'hardware', 'RI03', 'old R04/R05'],
        test_counting='Completed unique XML testcase identities; repeated CTest/direct execution counted once')

    def save():
        (out / 'evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')

    def run(name, argv, cwd=REPO, timeout=1800):
        log = out / (name + '.log')
        start = time.monotonic()
        with log.open('x') as stream:
            try:
                code = subprocess.run(argv, cwd=cwd, env=env, stdout=stream,
                    stderr=subprocess.STDOUT, timeout=timeout).returncode
            except subprocess.TimeoutExpired:
                code = 124
        result['commands'].append(dict(name=name, argv=list(map(str, argv)), cwd=str(cwd),
            exit_code=code, wall_seconds=time.monotonic()-start, log_sha256=sha(log)))
        save()
        print(name, code, flush=True)
        require(code == 0, name + ' failed, retained at ' + str(out))
        return log.read_text()

    def scope(label):
        changed = run(label + '_changed', ['git', 'diff', '--name-only', BASE, '--', *PRODUCTION]).splitlines()
        new = run(label + '_untracked', ['git', 'ls-files', '--others', '--exclude-standard', '--', *PRODUCTION]).splitlines()
        actual = set(changed + new)
        require(actual == ALLOWED, 'Unexpected production scope ' + repr(actual.symmetric_difference(ALLOWED)))
        return sorted(actual)

    try:
        require(run('head', ['git', 'rev-parse', 'HEAD']).strip() == BASE, 'Unexpected qualification baseline')
        require(run('branch', ['git', 'branch', '--show-current']).strip() == 'research/ista-velocity-regularized', 'Wrong branch')
        result['worktree'] = run('status', ['git', 'status', '--short', '--untracked-files=all'])
        sm = run('submodules', ['git', 'submodule', 'status', '--recursive'])
        require(len(sm.splitlines()) == 33 and all(s.startswith(' ') for s in sm.splitlines()), 'Submodule mismatch')
        require(not run('submodule_status', ['git', 'submodule', 'foreach', '--quiet', '--recursive',
            'git status --porcelain']).strip(), 'Submodule dirty')
        result['scope_before'] = scope('before')
        run('old_research_unchanged', ['git', 'diff', '--exit-code', BASE, '--',
            'research/sta-rate-control', 'research/sta-velocity-control/regularized_sta',
            'research/sta-velocity-control/axis_ablation', 'research/sta-velocity-control/v08',
            'research/sta-velocity-control/regularized_ista/ri00',
            'research/sta-velocity-control/regularized_ista/ri01', 'sim_scripts'])
        result['eeprom_before'] = sha(param)
        shutil.copyfile(param, out / 'eeprom_before.bin')
        result['firmware_before'] = sha(binary)
        shutil.copyfile(binary, out / 'firmware_before.bin')
        inputs = {str(REPO / name): sha(REPO / name) for name in ALLOWED}
        for path in list((HERE / 'reference').iterdir()) + [HERE / 'verify.py', HERE / 'CONTRACT_CN.md']:
            if path.is_file():
                inputs[str(path)] = sha(path)
        result['input_sha256'] = inputs
        save()
        run('reference', ['python3', '-B', str(HERE / 'reference/freeze.py')])
        package = Path('/home/yr/Desktop/STA-ISTA-MATLAB-PX4')
        original = json.loads((HERE.parent / 'ri00/results/source_fingerprints.json').read_text())
        require(all(sha(package / name) == value['sha256'] for name, value in original.items()), 'Source package changed')
        run('source_package', ['sha256sum', '--check', 'SHA256SUMS.txt'], package)
        run('configure', ['make', 'tests', 'TESTFILTER=RegularizedIsta', '-j4'])
        targets = ['unit-' + n for n in RI01.UNIT] + ['functional-' + n for n in RI01.FUNCTIONAL]
        extra = ['unit-RegularizedIstaRegression', 'unit-RegularizedIstaProtection',
                 'unit-RegularizedIstaPosition', 'functional-RegularizedIstaVelocityParam',
                 'functional-RegularizedIstaVelocityModule']
        targets += extra
        require(len(set(targets)) == len(targets), 'Duplicate executable')
        run('build_regression', ['cmake', '--build', str(REPO / 'build/px4_sitl_test'),
            '--target', *targets, '--parallel', '4'])
        for target in targets:
            run(target, [str(REPO / 'build/px4_sitl_test' / target),
                '--gtest_output=xml:' + str(out / (target + '.xml'))], timeout=180)
        result['cpp_inventory'] = XML.xml_inventory(out.glob('*.xml'))
        result['new_cpp_inventory'] = XML.xml_inventory(out / (target + '.xml') for target in extra)
        regression = ET.parse(out / 'unit-RegularizedIstaRegression.xml').getroot()
        result['sequence_properties'] = [dict(classname=c.attrib['classname'], name=c.attrib['name'],
            properties={p.attrib['name']: p.attrib['value'] for p in c.findall('properties/property')})
            for c in regression.iter('testcase')]
        run('strict_cxx14', ['g++', '-std=c++14', '-pedantic-errors', '-Wall', '-Wextra', '-Werror',
            '-fno-exceptions', '-fno-rtti', '-c', str(REPO / (POSITION + 'RegularizedIstaVelocityControl.cpp')),
            '-o', str(out / 'strict_kernel.o')])
        run('build_sitl', ['make', 'px4_sitl_default', '-j4'])
        schemas = {}
        for topic in ('velocity_ctrl_selection', 'sta_velocity_ctrl_status'):
            generated = REPO / 'build/px4_sitl_default/msg/topics_sources' / (topic + '.cpp')
            text = generated.read_text()
            fields = re.search(r'__orb_' + topic + r'_fields\[\]\s*=\s*"([^"]+)"', text)
            require(fields is not None, 'Missing actual generated format')
            length = len((topic + ':' + fields[1]).encode()) + 1
            require(length < 1500 and 'ORB_DEFINE(' + topic + ',' in text, 'ULog format/register invalid')
            header = REPO / 'build/px4_sitl_default/uORB/topics' / (topic + '.h')
            require(re.search(r'ORB_QUEUE_LENGTH\s*=\s*8', header.read_text()), 'Queue changed')
            schemas[topic] = dict(ulog_format_bytes_including_nul=length, queue=8,
                generated_sha256=sha(generated), header_sha256=sha(header))
        result['generated_schema'] = schemas
        logger = REPO / 'src/modules/logger/logged_topics.cpp'
        logger_text = logger.read_text()
        high_rate = logger_text.split('void LoggedTopics::add_high_rate_topics()', 1)[1].split('\n}', 1)[0]
        require('add_topic("velocity_ctrl_selection");' in high_rate
            and 'add_topic("sta_velocity_ctrl_status");' in high_rate, 'High-frequency logger registration absent')
        require(subprocess.check_output(['git', 'diff', BASE, '--', str(logger)], cwd=REPO) == b'', 'Logger changed')
        metadata = ET.parse(REPO / 'build/px4_sitl_default/parameters.xml').getroot()
        mode = next(p for p in metadata.iter('parameter') if p.attrib.get('name') == 'MPC_VC_MODE')
        require(float(mode.attrib['default']) == 0, 'Non-PID default')
        require(any(v.attrib.get('code') == '4' for v in mode.iter('value')), 'MODE4 metadata missing')
        result['mode_metadata'] = ET.tostring(mode, encoding='unicode')
        references = run('admission_references', ['rg', '-n', '_regularized_ista_admission', 'src'])
        writers = [line for line in references.splitlines() if re.search(r'_regularized_ista_admission\s*=\s*true', line)]
        require(writers and all('Test.cpp:' in line for line in writers), 'Production admission writer')
        require('bool _regularized_ista_admission{false}' in (REPO / (POSITION + 'PositionControl.hpp')).read_text(), 'Default gate not closed')
        result['no_actuator_path'] = dict(default_private_false=True, true_writers=writers,
            firmware_contains_adapter=True, public_parameter_or_setter=False,
            actual_selector_module_persistence_negative_tests=True,
            limitation='Not an absent-symbol proof: adapter is linked but production gate remains closed')
        run('model_reference', ['python3', '-B', str(HERE.parent / 'ri01/model/check.py'),
            '--output', str(out / 'model_reference')])
        result['model'] = json.loads((out / 'model_reference/summary.json').read_text())
        result['scope_after'] = scope('after')
        require(result['scope_before'] == result['scope_after'], 'Scope changed')
        require(all(sha(path) == expected for path, expected in inputs.items()), 'Verification input changed during run')
        result['eeprom_after'] = sha(param)
        require(result['eeprom_before'] == result['eeprom_after'], 'Runtime EEPROM changed')
        require(all(sha(package / name) == value['sha256'] for name, value in original.items()), 'Package changed')
        run('diff_check', ['git', 'diff', '--check'])
        result['firmware_sha256'] = sha(binary)
        result['counts'] = dict(cpp_unique=result['cpp_inventory']['unique_tests'],
            new_cpp=result['new_cpp_inventory']['unique_tests'], cpp_targets=len(targets),
            model_oracle_tests=result['model']['oracle_tests'])
        result['success'] = True
    except BaseException as error:
        result['failure'] = dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())
        raise
    finally:
        result['eeprom_finally'] = sha(param) if param.exists() else None
        save()
        index = {str(p.relative_to(out)): dict(bytes=p.stat().st_size, sha256=sha(p))
            for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'index.json'}
        (out / 'index.json').write_text(json.dumps(index, indent=2) + '\n')


if __name__ == '__main__':
    main()
