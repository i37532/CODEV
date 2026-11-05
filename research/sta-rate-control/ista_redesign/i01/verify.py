#!/usr/bin/env python3
"""I01 no-flight verification; record every command and nonzero actual count.

Use a fresh output directory for every attempt. Failed attempts are preserved.
--regression additionally builds SITL and runs existing M09/I00 regressions.
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

from audit import write_json


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True); p.add_argument('--regression', action='store_true')
    args = p.parse_args(); out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    folder = Path(__file__).resolve().parent; repo = folder.parents[3]
    kernel = repo/'src/modules/mc_rate_control/StaRateControl'
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', I01_KERNEL_LIBRARY=str(out/'kernel.so'))
    env['PYTHONPATH'] = str(repo/'.px4-python')+':/home/yr/Desktop/codev doc/experiments/M00-20260912/python'
    env['PATH'] = str(repo/'.px4-python/bin')+':'+env['PATH']
    evidence = dict(success=False, commands=[], tests={}, head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(),
                    branch=subprocess.check_output(['git', 'branch', '--show-current'], cwd=repo, text=True).strip(),
                    submodules=subprocess.check_output(['git', 'submodule', 'status', '--recursive'], cwd=repo, text=True),
                    matlab=shutil.which('matlab'), octave=shutil.which('octave'), flight_executed=False)
    source_files = sorted(folder.glob('*.py'))+sorted(folder.glob('*.cpp'))+sorted(folder.glob('*.md'))
    source_files += sorted(kernel.glob('ProperIsta*'))+[kernel/'CMakeLists.txt']
    snapshot = out/'source_snapshot'; snapshot.mkdir()
    evidence['source_hashes'] = {}
    for path in source_files:
        relative = path.relative_to(repo); target = snapshot/relative
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, target)
        evidence['source_hashes'][str(relative)] = sha(path)

    def run(name, argv):
        print('RUN', name, flush=True)
        with (out/(name+'.log')).open('x') as log:
            result = subprocess.run(list(map(str, argv)), cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT)
        evidence['commands'].append(dict(name=name, argv=list(map(str, argv)), returncode=result.returncode))
        if result.returncode:
            raise RuntimeError(f'{name} failed ({result.returncode})')

    try:
        run('diff_check', ['git', 'diff', '--check'])
        run('build_tests', ['make', 'tests', 'TESTFILTER=ProperIstaRateControl'])
        xml = out/'ProperIstaRateControl.xml'
        run('cpp_tests', [repo/'build/px4_sitl_test/unit-ProperIstaRateControl', '--gtest_output=xml:'+str(xml)])
        counts = {key: int(ET.parse(xml).getroot().attrib[key]) for key in ('tests', 'failures', 'errors', 'disabled')}
        assert counts == dict(tests=16, failures=0, errors=0, disabled=0), counts
        evidence['tests']['cpp_new'] = counts
        flags = ['g++', '-std=c++14', '-pedantic-errors', '-Wall', '-Wextra', '-Werror', '-Wdouble-promotion',
                 '-O2', '-fno-exceptions', '-fno-rtti', '-fPIC', '-shared', '-I'+str(kernel)]
        sources = [kernel/'ProperIstaRateControl.cpp', folder/'kernel_bridge.cpp']
        run('bridge_build', flags+sources+['-o', out/'kernel.so'])
        run('python_tests', [sys.executable, '-m', 'unittest', 'discover', '-s', folder, '-p', 'test_audit.py', '-v'])
        match = re.search(r'Ran (\d+) tests', (out/'python_tests.log').read_text())
        assert match and int(match.group(1)) == 12
        evidence['tests']['python_new'] = int(match.group(1))
        run('scalar', [sys.executable, folder/'audit.py', '--library', out/'kernel.so', '--output', out/'scalar'])
        evidence['scalar'] = json.loads((out/'scalar/summary.json').read_text())
        assert evidence['scalar']['success'] and len(evidence['scalar']['cases']) == 84
        # Same complete matrix under undefined/float-cast-overflow sanitizer.
        run('sanitizer_build', flags+['-fsanitize=undefined,float-cast-overflow', '-fno-sanitize-recover=all']+sources+['-o', out/'kernel_sanitized.so'])
        run('sanitizer_scalar', [sys.executable, folder/'audit.py', '--library', out/'kernel_sanitized.so', '--output', out/'sanitizer_scalar'])
        assert (out/'scalar/summary.json').read_bytes() == (out/'sanitizer_scalar/summary.json').read_bytes()
        if args.regression:
            run('m09_regression', [sys.executable, repo/'research/sta-rate-control/scripts/verify_m09.py', '--output', out/'m09'])
            run('i00_regression', [sys.executable, folder.parent/'i00/verify.py', '--output', out/'i00'])
            run('sitl_symbols', ['nm', '-C', repo/'build/px4_sitl_default/bin/px4'])
            symbols = (out/'sitl_symbols.log').read_text()
            assert 'ProperIstaRateControl' not in symbols
            assert 'IstaRateControl::update' in symbols and 'StaRateControl::update' in symbols
            evidence['firmware_sha256'] = sha(repo/'build/px4_sitl_default/bin/px4')
            evidence['existing'] = json.loads((out/'m09/evidence.json').read_text())
            evidence['i00'] = json.loads((out/'i00/evidence.json').read_text())
            run('unchanged_runtime', ['git', 'diff', '--exit-code', 'dd776d61710fa800b3374e75279ce244aa620d4b', '--',
                'src/modules/mc_rate_control/MulticopterRateControl.cpp', 'src/modules/mc_rate_control/MulticopterRateControl.hpp',
                'src/modules/mc_rate_control/RateControl', kernel/'StaProtection.cpp', kernel/'StaProtection.hpp',
                kernel/'IstaRateControl.cpp', kernel/'IstaRateControl.hpp', kernel/'StaRateControl.cpp', kernel/'StaRateControl.hpp',
                'src/modules/mc_rate_control/mc_rate_control_params.c', 'msg', 'boards', 'ROMFS', 'Tools', 'sitl', 'sim_scripts'])
        assert all(sha(repo/path) == digest for path, digest in evidence['source_hashes'].items()), 'Source changed during verification'
        evidence['success'] = True
    except Exception as exc:
        evidence['failure'] = repr(exc)
        raise
    finally:
        write_json(out/'evidence.json', evidence)
    print('I01 passed:', evidence['tests'], 'regression=', args.regression)


if __name__ == '__main__':
    main()
