#!/usr/bin/env python3
"""Offline-only V00 capture/build/test. Never starts a simulator."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    out = p.parse_args().output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, out / 'verify_v00.py')
    env = os.environ.copy()
    env['PYTHONPATH'] = str(REPO / '.px4-python') + ':' + env.get('PYTHONPATH', '')
    env['PATH'] = str(REPO / '.px4-python/bin') + ':' + env['PATH']
    evidence = {'commands': [], 'tests': {}, 'references': {}, 'success': False}

    def save():
        (out / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')

    def run(name, cmd, required=True):
        with (out / (name + '.log')).open('w') as stream:
            r = subprocess.run(cmd, cwd=REPO, env=env, stdout=stream, stderr=subprocess.STDOUT)
        evidence['commands'].append({'name': name, 'command': cmd, 'exit_code': r.returncode})
        save()
        print(name, r.returncode, flush=True)
        if required and r.returncode:
            raise RuntimeError(name + ' failed')

    try:
        for name, cmd in {
            'head': ['git', 'rev-parse', 'HEAD'],
            'status': ['git', 'status', '--short', '--branch'],
            'submodules': ['git', 'submodule', 'status', '--recursive'],
            'compiler': ['g++', '--version'], 'cmake': ['cmake', '--version'],
            'gazebo': ['pkg-config', '--modversion', 'gazebo'], 'kernel': ['uname', '-a'],
            'os': ['lsb_release', '-a'], 'python': ['python3', '--version'],
        }.items():
            run(name, cmd)
        refs = list((REPO / 'src/modules/mc_pos_control').rglob('*'))
        refs += [REPO / x for x in ('sitl/run.sh', 'Tools/sitl_run.sh',
            'sitl/worlds/empty_grey.world', 'Tools/sitl_gazebo/models/iris/iris.sdf',
            'Tools/sitl_gazebo/models/gps/gps.sdf',
            'ROMFS/px4fmu_common/init.d-posix/airframes/10016_iris',
            'ROMFS/px4fmu_common/mixers/quad_w.main.mix',
            'msg/vehicle_local_position.msg', 'msg/vehicle_local_position_setpoint.msg',
            'src/modules/ekf2/EKF2.cpp')]
        for f in refs:
            if not f.exists():
                raise FileNotFoundError(f)
            if f.is_file():
                rel = f.relative_to(REPO)
                dest = out / 'references' / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(f, dest)
                evidence['references'][str(rel)] = sha(f)
        for name in ('VELOCITY_STA_TODO_CN.md', 'VELOCITY_STA_PROMPTS_CN.md', 'VELOCITY_STA_STATUS_CN.md'):
            external = Path('/home/yr/Desktop/codev doc/plan') / name
            snapshot = REPO / 'research/sta-velocity-control/plan/v1' / name
            # v1 is immutable; the live progress table is expected to evolve.
            if name != 'VELOCITY_STA_STATUS_CN.md':
                assert external.read_bytes() == snapshot.read_bytes(), name
            shutil.copyfile(external, out / name)
            evidence.setdefault('initial_plan_sha256', {})[name] = sha(snapshot)
        save()
        run('build_sitl', ['make', 'px4_sitl_default', '-j4'])
        # This target configures/builds all existing unit targets. A single safe
        # TESTFILTER avoids shell metacharacter ambiguity in the legacy Makefile.
        run('build_tests', ['make', 'tests', 'TESTFILTER=PositionControl', '-j4'])
        for name in ('PositionControl', 'ControlMath', 'Takeoff', 'RateControl', 'RateControlDispatcher'):
            xml = out / (name + '.xml')
            run(name, [str(REPO / 'build/px4_sitl_test' / ('unit-' + name)),
                       '--gtest_output=xml:' + str(xml)], required=False)
            attrs = ET.parse(xml).getroot().attrib
            evidence['tests'][name] = {k: int(attrs[k]) for k in ('tests', 'failures', 'errors', 'disabled')}
            save()
        evidence['binary_sha256'] = sha(REPO / 'build/px4_sitl_default/bin/px4')
        run('python_tools', ['python3', '-m', 'unittest', 'discover', '-s',
                            'research/sta-velocity-control/scripts', '-p', 'test_*.py', '-v'])
        evidence['success'] = all(t['tests'] > 0 and not (t['failures'] or t['errors'] or t['disabled'])
                                  for t in evidence['tests'].values())
        evidence['success'] &= all(c['exit_code'] == 0 for c in evidence['commands'])
    finally:
        save()
    if not evidence['success']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
