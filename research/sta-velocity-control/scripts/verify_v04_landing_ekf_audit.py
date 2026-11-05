#!/usr/bin/env python3
"""Offline verification only; preserves every output and expected UB diagnostic."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[3]


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True)
    out = p.parse_args().output.resolve(); out.mkdir(parents=True, exist_ok=False)
    evidence = dict(kind='offline_only_no_flight', new_flights=0, commands=[])

    def run(name, argv, expected=0):
        with (out / (name + '.log')).open('w') as stream:
            result = subprocess.run(argv, cwd=REPO, stdout=stream, stderr=subprocess.STDOUT, timeout=900)
        evidence['commands'].append(dict(name=name, argv=argv, exit_code=result.returncode, expected_exit=expected))
        (out/'evidence.json').write_text(json.dumps(evidence, indent=2)+'\n')
        print(name, result.returncode, flush=True)
        if result.returncode != expected:
            raise RuntimeError(name + ' failed; outputs preserved')

    run('regression', ['python3', 'research/sta-velocity-control/scripts/verify_v04_repair.py',
                       '--output', str(out/'regression')])
    run('attitude', ['build/px4_sitl_test/unit-AttitudeControl', '--gtest_output=xml:'+str(out/'attitude.xml')])
    source = 'research/sta-velocity-control/v04/landing_ekf_audit01/fifo_narrowing_probe.cpp'
    run('compiler', ['c++', '--version'])
    run('compile_probe', ['c++', '-std=c++14', '-O2', source, '-o', str(out/'fifo_probe')])
    run('probe_in_range', [str(out/'fifo_probe'), '-9.81'])
    run('probe_out_of_range_nonportable', [str(out/'fifo_probe'), '-250'])
    run('compile_sanitized', ['c++', '-std=c++14', '-O2', '-fsanitize=float-cast-overflow',
                             '-fno-sanitize-recover=float-cast-overflow', source, '-o', str(out/'fifo_sanitized')])
    run('sanitized_in_range', [str(out/'fifo_sanitized'), '-9.81'])
    run('sanitized_out_of_range_expected_failure', [str(out/'fifo_sanitized'), '-250'], expected=1)
    text = (out/'sanitized_out_of_range_expected_failure.log').read_text()
    if 'outside the range of representable values' not in text:
        raise ValueError('Expected float-to-int range diagnostic absent')
    reg = json.loads((out/'regression/evidence.json').read_text())
    evidence['cpp_gtests'] = reg['unique_cpp_tests'] + int(ET.parse(out/'attitude.xml').getroot().get('tests'))
    evidence['python_tests'] = int(re.search(r'Ran (\d+) tests', (out/'regression/python_tools.log').read_text())[1])
    evidence['probe_scope'] = 'Synthetic -250 m/s² only. UB in conversion reproduced, not proof that the old HIL input had this value.'
    evidence['passed'] = True
    (out/'evidence.json').write_text(json.dumps(evidence, indent=2)+'\n')
    files = sorted(p for p in out.rglob('*') if p.is_file() and p.name != 'artifacts.sha256')
    (out/'artifacts.sha256').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p}\n' for p in files))
    print(json.dumps(dict(cpp_gtests=evidence['cpp_gtests'], python_tests=evidence['python_tests'], passed=True)))


if __name__ == '__main__':
    main()
