#!/usr/bin/env python3
"""Offline RI03 tool test receipt; never launches simulation or touches EEPROM."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from bindings import HERE, REPO, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    before = {str(p.relative_to(REPO)): digest(p) for p in sorted(HERE.glob('*')) if p.is_file()}
    command = [sys.executable, '-B', str(HERE / 'test_tools.py')]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=':'.join(map(str, (
        REPO / '.px4-python', REPO / 'research/sta-velocity-control/scripts',
        Path('/home/yr/Desktop/codev doc/experiments/M00-20260912/python')))))
    log = output / 'tools_unit.log'; began = time.monotonic()
    with log.open('xb') as stream:
        result = subprocess.run(command, cwd=REPO, env=env, stdout=stream, stderr=subprocess.STDOUT)
    count = sum(map(int, re.findall(r'Ran (\d+) tests? in', log.read_text())))
    after = {str(p.relative_to(REPO)): digest(p) for p in sorted(HERE.glob('*')) if p.is_file()}
    evidence = dict(stage='RI03-tools', success=result.returncode == 0 and count > 0 and before == after,
        python_tests=count, new_flights=0, real_parameter_mutations=0, source_sha256_before=before,
        source_sha256_after=after, source_unchanged=before == after,
        commands=[dict(argv=command, cwd=str(REPO), exit_code=result.returncode, tests=count,
                       elapsed_s=time.monotonic() - began, log=str(log), sha256=digest(log))])
    (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({k: v for k, v in evidence.items() if k not in ('source_sha256_before', 'source_sha256_after')}, indent=2))
    return 0 if evidence['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
