#!/usr/bin/env python3
"""One bounded offline qualification; no flight, no parameter writes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
import argparse

HERE = Path(__file__).resolve().parent
MAIN = HERE.parents[2]
REPAIR = Path('/home/yr/Desktop/Codev-SuperTwisting2-imu-fix')
ROOT = Path('/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-QUICK-20261102')


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', default='qualification01')
    args = parser.parse_args()
    assert args.name.isidentifier()
    out = ROOT / args.name
    out.mkdir(parents=True, exist_ok=False)
    report = dict(commands=[], new_flights=0, passed=False)
    env = dict(os.environ, PYTHONPATH=str(MAIN / '.px4-python') + ':/home/yr/Desktop/codev doc/experiments/M00-20260912/python:/home/yr/Desktop/codev doc/experiments/M10-20260917/plot_dependencies01/python',
               PYTHONDONTWRITEBYTECODE='1')
    def run(name, argv, cwd=MAIN):
        with (out / (name + '.log')).open('x') as f:
            c = subprocess.run([str(a) for a in argv], cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=180)
        report['commands'].append(dict(name=name, argv=list(map(str, argv)), cwd=str(cwd), exit_code=c.returncode,
                                       log=str(out/(name+'.log')), log_sha256=sha(out/(name+'.log'))))
        (out/'qualification.json').write_text(json.dumps(report, indent=2)+'\n')
        print(name, c.returncode, flush=True)
        if c.returncode: raise RuntimeError(name)
    for target in ('functional-ImuConversion', 'unit-PositionControl', 'unit-ControlMath', 'unit-Takeoff',
                   'unit-rate_control_test', 'unit-AttitudeControl'):
        run(target, [REPAIR/'build/px4_sitl_test'/target, '--gtest_output=xml:'+str(out/(target+'.xml'))])
    report['cpp'] = {p.stem: dict(ET.parse(p).getroot().attrib) for p in out.glob('*.xml')}
    assert all(int(x['tests']) > 0 and int(x['failures']) == int(x['errors']) == int(x['disabled']) == 0
               for x in report['cpp'].values())
    run('quick_tests', [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', HERE, '-p', 'test_*.py', '-v'])
    run('old_offboard_tests', [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', HERE.parent/'offboard', '-p', 'test_*.py', '-v'])
    run('runtime', [sys.executable, '/home/yr/.local/share/codev-ros-offboard/preflight.py'])
    report['source_sha256'] = {str(p): sha(p) for p in HERE.glob('*.py')}
    report['firmware_sha256'] = sha(REPAIR/'build/px4_sitl_default/bin/px4')
    report['passed'] = True
    (out/'qualification.json').write_text(json.dumps(report, indent=2)+'\n')
    print('qualified', out, flush=True)


if __name__ == '__main__': main()
