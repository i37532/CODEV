#!/usr/bin/env python3
"""Compile unchanged production kernels; run I00 tests/scalars without flying."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from audit import digest, write_json


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    folder = Path(__file__).resolve().parent
    repo = folder.parents[3]
    kernel = repo/'src/modules/mc_rate_control/StaRateControl'
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', I00_KERNEL_LIBRARY=str(out/'kernel.so'))
    evidence = dict(success=False, commands=[],
                    head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(),
                    submodules=subprocess.check_output(['git', 'submodule', 'status', '--recursive'], cwd=repo, text=True),
                    sources={str(p): digest(p) for p in sorted(folder.glob('*')) if p.is_file()},
                    production={str(kernel/p): digest(kernel/p) for p in
                                ('IstaRateControl.cpp', 'IstaRateControl.hpp', 'StaRateControl.cpp', 'StaRateControl.hpp')})

    def run(name, argv):
        print('RUN', name, flush=True)
        with (out/(name+'.log')).open('x') as log:
            r = subprocess.run(argv, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT)
        evidence['commands'].append(dict(name=name, argv=list(map(str, argv)), returncode=r.returncode))
        if r.returncode:
            raise RuntimeError(name+' failed')

    try:
        run('build', ['g++', '-std=c++14', '-pedantic-errors', '-Wall', '-Wextra', '-Werror',
                      '-Wdouble-promotion', '-O2', '-fno-exceptions', '-fno-rtti', '-fPIC', '-shared',
                      '-I'+str(kernel), str(kernel/'IstaRateControl.cpp'), str(kernel/'StaRateControl.cpp'),
                      str(folder/'kernel_bridge.cpp'), '-o', str(out/'kernel.so')])
        run('tests', [sys.executable, '-m', 'unittest', 'discover', '-s', str(folder), '-p', 'test_audit.py', '-v'])
        match = re.search(r'Ran (\d+) tests', (out/'tests.log').read_text())
        if not match or int(match.group(1)) != 13:
            raise AssertionError('Expected 13 actual harness tests')
        evidence['tests'] = int(match.group(1))
        run('scalar', [sys.executable, str(folder/'audit.py'), '--library', str(out/'kernel.so'), '--output', str(out/'scalar')])
        evidence['scalar'] = json.loads((out/'scalar/summary.json').read_text())
        if not evidence['scalar']['success'] or len(evidence['scalar']['cases']) != 138:
            raise AssertionError('Incomplete scalar matrix')
        if any(digest(p) != sha for p, sha in evidence['production'].items()):
            raise AssertionError('Production changed during audit')
        evidence['success'] = True
    except Exception as exc:
        evidence['failure'] = repr(exc)
        raise
    finally:
        write_json(out/'evidence.json', evidence)


if __name__ == '__main__':
    main()
