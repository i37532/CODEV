#!/usr/bin/env python3
"""Z-only offline prototype evidence. Does not start a simulator or set parameters."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[3]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    out = parser.parse_args().output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env['PATH'] = str(REPO / '.px4-python/bin') + ':' + env['PATH']
    env['PYTHONPATH'] = ':'.join([str(REPO / '.px4-python'),
        '/home/yr/Desktop/codev doc/experiments/M00-20260912/python', env.get('PYTHONPATH', '')])
    eeprom = REPO / 'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
    evidence = dict(scope='Z01 offline only; Z not admitted in production', success=False,
        new_flights=0, commands=[], head=subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(), eeprom_before=digest(eeprom))

    def save():
        (out / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')

    def run(name, command):
        with (out / (name + '.log')).open('w') as stream:
            result = subprocess.run(command, cwd=REPO, env=env, stdout=stream,
                                    stderr=subprocess.STDOUT, timeout=900)
        evidence['commands'].append(dict(name=name, argv=command, exit_code=result.returncode))
        save()
        print(name, result.returncode, flush=True)
        if result.returncode:
            raise RuntimeError(name + ' failed; evidence retained')

    save()
    try:
        run('status', ['git', 'status', '--short'])
        run('submodules', ['git', 'submodule', 'status', '--recursive'])
        run('build_z', ['make', 'tests', 'TESTFILTER=VelocityEstaZ', '-j4'])
        run('z_tests', [str(REPO / 'build/px4_sitl_test/unit-VelocityEstaZ'),
                        '--gtest_output=xml:' + str(out / 'z.xml')])
        attrs = ET.parse(out / 'z.xml').getroot().attrib
        evidence['z_tests'] = {k: int(attrs[k]) for k in ('tests', 'failures', 'errors', 'disabled')}
        assert evidence['z_tests']['tests'] > 0 and not any(
            evidence['z_tests'][k] for k in ('failures', 'errors', 'disabled'))
        run('inherited_regression', ['python3', str(REPO /
            'research/sta-velocity-control/scripts/verify_v04_repair.py'), '--output', str(out / 'regression')])
        reg = json.loads((out / 'regression/evidence.json').read_text())
        evidence['inherited_cpp_tests'] = reg['unique_cpp_tests']
        evidence['inherited_python_tests'] = int(re.search(r'Ran (\d+) tests',
            (out / 'regression/python_tools.log').read_text())[1])
        run('firmware_symbols', ['nm', '-C', str(REPO / 'build/px4_sitl_default/bin/px4')])
        assert 'StaVelocityZPrototype' not in (out / 'firmware_symbols.log').read_text()
        evidence['no_z_prototype_firmware_symbol'] = True
        evidence['firmware_sha256'] = digest(REPO / 'build/px4_sitl_default/bin/px4')
        evidence['eeprom_after'] = digest(eeprom)
        assert evidence['eeprom_after'] == evidence['eeprom_before']
        run('diff_check', ['git', 'diff', '--check'])
        evidence['source_fingerprints'] = {str(p.relative_to(REPO)): digest(p) for p in [
            Path(__file__), Path(__file__).with_name('StaVelocityZPrototype.hpp'),
            REPO / 'src/modules/mc_pos_control/PositionControl/VelocityEstaZTest.cpp',
            REPO / 'src/modules/mc_pos_control/PositionControl/CMakeLists.txt']}
        evidence['success'] = True
    finally:
        save()
        files = sorted(p for p in out.rglob('*') if p.is_file() and p.name != 'artifacts.sha256')
        (out / 'artifacts.sha256').write_text(''.join(f'{digest(p)}  {p}\n' for p in files))
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
