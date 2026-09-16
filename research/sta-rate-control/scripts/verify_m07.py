#!/usr/bin/env python3
"""Offline M07 acceptance: builds, real GTest counts, oracle/plant, PID/ESTA regressions.

Output must not exist. No simulator, Git mutations, vehicle connection or push.
All failed attempts retain source snapshots, commands and logs. Host/SITL only.
"""
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


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env.update(PYTHONDONTWRITEBYTECODE='1',
               PYTHONPATH=str(repo / '.px4-python') + os.pathsep +
               '/home/yr/Desktop/codev doc/experiments/M00-20260912/python' + os.pathsep + env.get('PYTHONPATH', ''),
               PATH=str(repo / '.px4-python/bin') + os.pathsep + env['PATH'],
               M00_PASSING_RUN='/home/yr/Desktop/codev doc/experiments/M00-20260912/run03')
    commands = []

    def run(name, argv):
        print('RUN', name, flush=True)
        with (output / (name + '.log')).open('wb') as log:
            completed = subprocess.run(argv, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT)
        commands.append(dict(name=name, argv=list(map(str, argv)), returncode=completed.returncode))
        (output / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        print('EXIT', name, completed.returncode, flush=True)
        if completed.returncode:
            raise RuntimeError(f'{name} failed: {output / (name + ".log")}')

    def git(*args):
        return subprocess.check_output(['git', *args], cwd=repo).decode().strip()

    source = Path('src/modules/mc_rate_control/StaRateControl')
    paths = sorted({p.relative_to(repo) for folder in
                    ('src/modules/mc_rate_control', 'src/modules/mc_att_control')
                    for p in (repo / folder).rglob('*') if p.is_file()})
    paths += [Path('research/sta-rate-control/scripts') / name for name in
              ('m07_kernel_probe.cpp', 'reference_m07.py', 'verify_m07.py', 'summarize_m07.py')]
    evidence = dict(source_head=git('rev-parse', 'HEAD'), branch=git('branch', '--show-current'),
                    worktree=git('status', '--short'), sources={str(p): digest(repo / p) for p in paths},
                    python=sys.version, matlab=shutil.which('matlab'), octave=shutil.which('octave'),
                    matlab_executed=False, simulator_started=False, tests={}, passed=False)
    for p in paths:
        target = output / 'source' / p
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / p, target)
    (output / 'submodules.txt').write_text(git('submodule', 'status', '--recursive') + '\n')
    (output / 'tracked_diff.patch').write_text(git('diff', '--binary', 'HEAD') + '\n')
    references = [Path('/home/yr/Desktop/codev doc/algorithms') / name for name in
                  ('SUPER_TWISTING_FAMILY_CN.md', 'cpp/sta_algorithms.hpp', 'matlab/ista_step.m')]
    references += [Path('/home/yr/Desktop/codev doc/plan') / name for name in
                   ('STA_MILESTONES_CN.md', 'STA_MILESTONE_STATUS_CN.md')]
    evidence['reference_files'] = {str(p): digest(p) for p in references}
    for i, p in enumerate(references):
        target = output / 'references' / (str(i) + '_' + p.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
    try:
        assert evidence['branch'] == 'research/sta-rate-control'
        run('predecessor_hashes', ['sha256sum', '--check', '--quiet', 'research/sta-rate-control/m06/artifacts.sha256'])
        run('compiler', ['g++', '--version'])
        run('cmake', ['cmake', '--version'])
        run('diff_check', ['git', 'diff', '--check'])
        run('build_tests', ['make', 'tests', 'TESTFILTER=IstaRateControl'])
        targets = {'IstaRateControl': 13, 'StaRateControl': 11, 'StaProtection': 18,
                   'StaAxesApplication': 12, 'RateControl': 1, 'RateControlDispatcher': 4,
                   'ControllerSelection': 5, 'GyroPublicationGuard': 6, 'AttitudeControl': 3}
        for name, count in targets.items():
            xml_path = output / (name + '.xml')
            run(name, [str(repo / 'build/px4_sitl_test' / ('unit-' + name)), '--gtest_output=xml:' + str(xml_path)])
            attrs = ET.parse(xml_path).getroot().attrib
            actual = {key: int(attrs.get(key, 0)) for key in ('tests', 'failures', 'disabled', 'errors')}
            assert actual == dict(tests=count, failures=0, disabled=0, errors=0), (name, actual)
            evidence['tests'][name] = actual
        run('cxx14_probe', ['g++', '-std=c++14', '-pedantic-errors', '-Wall', '-Wextra', '-Werror',
                           '-Wdouble-promotion', '-O2', '-fno-exceptions', '-fno-rtti',
                           '-I' + str(source), str(source / 'IstaRateControl.cpp'),
                           'research/sta-rate-control/scripts/m07_kernel_probe.cpp', '-o', str(output / 'probe')])
        run('reference', [sys.executable, 'research/sta-rate-control/scripts/reference_m07.py',
                          '--probe', str(output / 'probe'), '--output', str(output / 'reference')])
        evidence['reference'] = json.loads((output / 'reference/summary.json').read_text())
        run('ubsan_build', ['g++', '-std=c++14', '-pedantic-errors', '-O1', '-g',
                            '-fno-rtti', '-fno-exceptions',
                            '-fsanitize=undefined,float-cast-overflow', '-fno-sanitize-recover=all',
                            '-Ibuild/px4_sitl_test/googletest-src/googletest/include',
                            str(source / 'IstaRateControl.cpp'), str(source / 'IstaRateControlTest.cpp'),
                            'build/px4_sitl_test/lib/libgtest_main.a', 'build/px4_sitl_test/lib/libgtest.a',
                            '-pthread', '-o', str(output / 'ista_ubsan')])
        run('ubsan_tests', [str(output / 'ista_ubsan'), '--gtest_output=xml:' + str(output / 'ubsan.xml')])
        attrs = ET.parse(output / 'ubsan.xml').getroot().attrib
        assert int(attrs['tests']) == 13 and all(int(attrs[k]) == 0 for k in ('failures', 'disabled', 'errors'))
        evidence['ubsan_repeat_tests'] = 13  # repeated tests, not extra unique cases
        for name, folder, pattern, count in [
                ('python_research', 'research/sta-rate-control/scripts', 'test_m*.py', 27),
                ('python_convenience', 'sim_scripts/_internal', 'test_*.py', 12)]:
            run(name, [sys.executable, '-m', 'unittest', 'discover', '-s', folder, '-p', pattern])
            match = re.search(r'Ran (\d+) tests?', (output / (name + '.log')).read_text())
            assert match and int(match[1]) == count, (name, match)
            evidence['tests'][name] = dict(tests=count)
        run('sitl_build', ['make', 'px4_sitl_default'])
        run('firmware_symbols', ['nm', '-C', 'build/px4_sitl_default/bin/px4'])
        assert 'IstaRateControl::' not in (output / 'firmware_symbols.log').read_text()
        assert 'StaRateControl::update' in (output / 'firmware_symbols.log').read_text()
        run('unchanged_runtime', ['git', 'diff', '--exit-code', 'HEAD', '--',
                                  'src/modules/mc_rate_control/RateControl',
                                  'src/modules/mc_rate_control/MulticopterRateControl.cpp',
                                  'src/modules/mc_rate_control/MulticopterRateControl.hpp',
                                  'src/modules/mc_rate_control/mc_rate_control_params.c',
                                  'src/modules/mc_att_control', 'msg', 'ROMFS', 'boards', 'sitl',
                                  str(source / 'StaRateControl.cpp'), str(source / 'StaRateControl.hpp'),
                                  str(source / 'StaProtection.cpp'), str(source / 'StaProtection.hpp'),
                                  str(source / 'StaAxesApplication.hpp'), 'research/sta-rate-control/m06'])
        assert evidence['sources'] == {str(p): digest(repo / p) for p in paths}, 'Sources changed during test'
        evidence['firmware_sha256'] = digest(repo / 'build/px4_sitl_default/bin/px4')
        evidence['probe_sha256'] = digest(output / 'probe')
        evidence['passed'] = True
    except Exception as error:
        evidence['failure'] = repr(error)
        raise
    finally:
        (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
        artifacts = sorted(p for p in output.rglob('*') if p.is_file() and p.name != 'artifacts.sha256')
        (output / 'artifacts.sha256').write_text(''.join(f'{digest(p)}  {p}\n' for p in artifacts))
    print('M07 PASSED; no simulator started, no Git commit/push performed.')


if __name__ == '__main__':
    main()
