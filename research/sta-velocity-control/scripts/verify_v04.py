#!/usr/bin/env python3
"""Archive nonzero offline tests/builds; never starts SITL. New output each time."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[3]


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True)
    out = p.parse_args().output.resolve(); out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env['PYTHONPATH'] = str(REPO/'.px4-python') + ':' + env.get('PYTHONPATH', '')
    env['PATH'] = str(REPO/'.px4-python/bin') + ':' + env['PATH']
    e = dict(success=False, commands=[], tests={}, source_sha256={})

    def save():
        (out/'evidence.json').write_text(json.dumps(e, indent=2)+'\n')

    def run(name, cmd):
        with (out/(name+'.log')).open('w') as f:
            r = subprocess.run(cmd, cwd=REPO, env=env, stdout=f, stderr=subprocess.STDOUT)
        e['commands'].append(dict(name=name, command=cmd, exit_code=r.returncode)); save()
        print(name, r.returncode, flush=True)
        if r.returncode: raise RuntimeError(name+' failed; preserved logs')

    try:
        run('v01_regression', ['python3', 'research/sta-velocity-control/scripts/verify_v01.py', '--output', str(out/'v01')])
        e['tests'].update(json.loads((out/'v01/evidence.json').read_text())['tests'])
        run('build_v04_tests', ['make','tests','TESTFILTER=VelocityEsta','-j4'])
        for name in ('StaVelocityControl', 'StaVelocityProtection', 'StaRateControl', 'VelocityDiagnosticInput', 'VelocityEsta'):
            xml = out/(name+'.xml')
            prefix = 'functional-' if name == 'VelocityDiagnosticInput' else 'unit-'
            run(name, [str(REPO/'build/px4_sitl_test'/(prefix+name)), '--gtest_output=xml:'+str(xml)])
            a = ET.parse(xml).getroot().attrib
            e['tests'][name] = {k:int(a[k]) for k in ('tests','failures','errors','disabled')}
            assert e['tests'][name]['tests'] > 0 and not any(e['tests'][name][k] for k in ('failures','errors','disabled'))
        # Re-run the original three failed audit probes against the repaired kernel.
        inc = REPO/'src/modules/mc_pos_control/PositionControl'
        gt = REPO/'build/px4_sitl_test'
        run('candidate_compile', ['g++','-std=c++14','-O2','-fno-rtti','-fno-exceptions','-pthread',
            '-I'+str(inc),'-I'+str(gt/'googletest-src/googletest/include'),
            str(inc/'StaVelocityControl.cpp'),str(REPO/'research/sta-velocity-control/v03/preflight/CandidateAuditTest.cpp'),
            str(gt/'lib/libgtest_main.a'),str(gt/'lib/libgtest.a'),'-o',str(out/'candidate_audit')])
        run('candidate_audit', [str(out/'candidate_audit'),'--gtest_output=xml:'+str(out/'candidate_audit.xml')])
        a = ET.parse(out/'candidate_audit.xml').getroot().attrib
        e['tests']['candidate_audit'] = {k:int(a[k]) for k in ('tests','failures','errors','disabled')}
        assert e['tests']['candidate_audit']['tests'] == 3
        generated = REPO/'build/px4_sitl_default/msg/topics_sources/sta_velocity_ctrl_status.cpp'
        fields = re.search(r'__orb_sta_velocity_ctrl_status_fields\[\] = "([^"]+)"', generated.read_text())
        if not fields: raise ValueError('Missing generated ULog format')
        e['ulog_format_bytes'] = len('sta_velocity_ctrl_status:') + len(fields[1]) + 1
        assert e['ulog_format_bytes'] < 1500
        symbols = subprocess.check_output(['nm','-C',str(REPO/'build/px4_sitl_default/bin/px4')], text=True)
        assert 'StaVelocityControl::' in symbols and 'StaVelocityProtection::' in symbols
        e['sta_linked_for_guarded_sitl_x_only'] = True
        run('gazebo_build_only', ['env','DONT_RUN=1','make','px4_sitl_default','gazebo_iris','-j4'])
        for rel in subprocess.check_output(['git','diff','--name-only'], cwd=REPO, text=True).splitlines():
            e['source_sha256'][rel] = hashlib.sha256((REPO/rel).read_bytes()).hexdigest()
        e['unique_cpp_tests'] = sum(v['tests'] for v in e['tests'].values())
        e['success'] = True
    finally:
        save()


if __name__ == '__main__': main()
