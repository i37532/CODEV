#!/usr/bin/env python3
"""Build/test M02 without starting a simulator or connecting to a vehicle.

Output must be a NEW directory. Capture real return codes and nonzero GTest
counts. Run from a staged implementation or a clean commit so git diff HEAD
captures new source files too. Does not stage, commit, push or change parameters.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
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
    env['PYTHONPATH'] = str(repo / '.px4-python') + os.pathsep + env.get('PYTHONPATH', '')
    env['PATH'] = str(repo / '.px4-python/bin') + os.pathsep + env['PATH']
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    commands = []

    def run(name, argv):
        print(f'RUN {name}: {argv}', flush=True)
        with (output / (name + '.log')).open('wb') as log:
            result = subprocess.run(argv, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
        commands.append(dict(name=name, argv=argv, returncode=result.returncode))
        (output / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        print(f'EXIT {name}: {result.returncode}', flush=True)
        if result.returncode:
            raise SystemExit(f'FAIL: inspect {output / (name + ".log")}')

    def git(*argv):
        return subprocess.check_output(['git', *argv], cwd=repo)

    kernel = Path('src/modules/mc_rate_control/StaRateControl')
    source_paths = [Path('src/modules/mc_rate_control/CMakeLists.txt'),
                    *sorted(path.relative_to(repo) for path in (repo / kernel).rglob('*') if path.is_file()),
                    *(Path('research/sta-rate-control/scripts') / name for name in
                      ('reference_m02.py', 'verify_m02.py', 'check_m02_matlab.m'))]
    for path in source_paths:
        subprocess.run(['git', 'ls-files', '--error-unmatch', str(path)], cwd=repo,
                       stdout=subprocess.DEVNULL, check=True)
    fingerprints = {str(path): digest(repo / path) for path in source_paths}
    (output / 'tested_source.patch').write_bytes(git('diff', '--binary', 'HEAD', '--', *map(str, source_paths)))
    (output / 'submodules.txt').write_bytes(git('submodule', 'status', '--recursive'))
    evidence = dict(source_head=git('rev-parse', 'HEAD').decode().strip(),
                    branch=git('branch', '--show-current').decode().strip(),
                    worktree=git('status', '--short').decode(),
                    source_files=fingerprints,
                    patch_sha256=digest(output / 'tested_source.patch'),
                    matlab=dict(executable=shutil.which('matlab'), executed=False),
                    octave=dict(executable=shutil.which('octave'), executed=False),
                    python=sys.version, tests={}, no_simulator_started=True)
    if evidence['branch'] != 'research/sta-rate-control':
        raise SystemExit('Wrong research branch')
    (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    run('fixture_check', [sys.executable, 'research/sta-rate-control/scripts/reference_m02.py',
                         '--check', str(kernel / 'test/ReferenceSamples.hpp'),
                         '--jsonl', str(output / 'reference_samples.jsonl')])
    run('compiler', ['g++', '--version'])
    run('cmake', ['cmake', '--version'])
    run('cxx14_standalone', ['g++', '-std=c++14', '-pedantic-errors', '-Wall', '-Wextra', '-Werror',
                            '-O2', '-fno-exceptions', '-fno-rtti', '-c', str(kernel / 'StaRateControl.cpp'),
                            '-o', str(output / 'StaRateControl.o')])
    for name, argv in [('esta_make', ['make', 'tests', 'TESTFILTER=StaRateControl']),
                       ('pid_make', ['make', 'tests', 'TESTFILTER=RateControl']),
                       ('selection_make', ['make', 'tests', 'TESTFILTER=ControllerSelection']),
                       ('sitl_build', ['make', 'px4_sitl_default'])]:
        run(name, argv)
    for name, expected in [('StaRateControl', 11), ('RateControl', 1),
                           ('RateControlDispatcher', 3), ('ControllerSelection', 5)]:
        xml_path = output / (name + '.xml')
        run(name, [str(repo / 'build/px4_sitl_test' / ('unit-' + name)), '--gtest_output=xml:' + str(xml_path)])
        root = ET.parse(xml_path).getroot()
        actual = {key: int(root.attrib.get(key, '0')) for key in ('tests', 'failures', 'disabled', 'errors')}
        if actual != dict(tests=expected, failures=0, disabled=0, errors=0):
            raise SystemExit(f'FAIL: nonzero test-count gate: {name}: {actual}')
        evidence['tests'][name] = actual
    run('unchanged_pid_runtime', ['git', 'diff', '--exit-code', 'HEAD', '--',
                                'src/modules/mc_rate_control/RateControl',
                                'src/modules/mc_rate_control/MulticopterRateControl.cpp',
                                'src/modules/mc_rate_control/MulticopterRateControl.hpp',
                                'src/modules/mc_rate_control/mc_rate_control_params.c'])
    run('firmware_symbols', ['nm', '-C', 'build/px4_sitl_default/bin/px4'])
    if 'StaRateControl::' in (output / 'firmware_symbols.log').read_text():
        raise SystemExit('FAIL: kernel unexpectedly linked into firmware')
    evidence['firmware_contains_sta_symbols'] = False
    evidence['firmware_sha256'] = digest(repo / 'build/px4_sitl_default/bin/px4')
    evidence['kernel_library_sha256'] = digest(repo / 'build/px4_sitl_default' / kernel / 'libStaRateControl.a')
    compile_commands = json.loads((repo / 'build/px4_sitl_default/compile_commands.json').read_text())
    evidence['kernel_compile_commands'] = [entry for entry in compile_commands
                                           if entry['file'].endswith('/StaRateControl.cpp')]
    if not evidence['kernel_compile_commands']:
        raise SystemExit('FAIL: no firmware-build kernel compile command')
    if fingerprints != {str(path): digest(repo / path) for path in source_paths}:
        raise SystemExit('FAIL: source changed while testing')
    evidence['commands'] = commands
    evidence['result'] = 'PASS: kernel unit tests, PID regression and SITL build only'
    (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(evidence['result'], flush=True)


if __name__ == '__main__':
    main()
