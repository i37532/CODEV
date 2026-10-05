#!/usr/bin/env python3
"""AX01 offline verification; no launcher execution, seeds or flight budget."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
BASE = 'c5f240fb638fd94669d86c8f9e1c37d7c2efec38'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env['PATH'] = str(REPO/'.px4-python/bin')+':'+env['PATH']
    env['PYTHONPATH'] = ':'.join([str(REPO/'.px4-python'), str(REPO/'research/sta-velocity-control/scripts'),
        '/home/yr/Desktop/codev doc/experiments/M00-20260912/python', env.get('PYTHONPATH', '')])
    eeprom = REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
    e = dict(success=False, new_flights=0, seeds_used=[], commands=[],
             baseline=BASE, eeprom_before=sha(eeprom))

    def save():
        (out/'evidence.json').write_text(json.dumps(e, indent=2)+'\n')

    def run(name, argv):
        with (out/(name+'.log')).open('x') as stream:
            r = subprocess.run(argv, cwd=REPO, env=env, stdout=stream,
                               stderr=subprocess.STDOUT, timeout=3600)
        e['commands'].append(dict(name=name, argv=argv, exit_code=r.returncode))
        save()
        print(name, r.returncode, flush=True)
        if r.returncode:
            raise RuntimeError(name+' failed; evidence retained')

    try:
        run('head', ['git', 'rev-parse', 'HEAD'])
        run('workspace', ['git', 'status', '--short'])
        run('submodules', ['git', 'submodule', 'status', '--recursive'])
        e['reference'] = {}
        for name in ('PositionControl.cpp', 'PositionControl.hpp', 'StaVelocityProtection.cpp',
                     'StaVelocityProtection.hpp', 'VelocityControlSelector.hpp'):
            original = subprocess.check_output(['git', 'show', BASE+':src/modules/mc_pos_control/PositionControl/'+name], cwd=REPO).decode()
            for old in ('StaVelocityProtection', 'VelocityControlSelector', 'PositionControl'):
                original = original.replace(old, 'AX00'+old)
            path = HERE/'reference'/('AX00'+name)
            assert path.read_text() == original, name
            e['reference'][name] = sha(path)
        run('build_velocity', ['make', 'tests', 'TESTFILTER=Velocity', '-j4'])
        run('interface_tests', ['python3', str(HERE/'test_interface.py')])
        # V08's unchanged-since-V07 provenance assertion is intentionally false
        # after AX01. Keep it untouched and disclose its exclusion, not a pass.
        run('historical', ['python3', str(REPO/'research/sta-velocity-control/v07/protocol07/verify.py'), '--output', str(out/'historical')])
        previous = json.loads((out/'historical/evidence.json').read_text())
        assert previous['success']
        v08 = REPO/'research/sta-velocity-control/v08'
        additional = [('tuning_applicable', HERE/'legacy_tuning.py')]
        additional += [(folder+'_'+file, v08/folder/(file+'.py')) for folder,file in (
            ('protocol02','test_cli_clock'), ('protocol03b','test_validation'), ('protocol03b','test_task_output'),
            ('protocol04','test_pilot'), ('protocol04','test_design'), ('protocol04','test_formal_design'),
            ('evidence_tools','test_replay_batch'), ('protocol05','test_mass'), ('formal','test_runtime'),
            ('formal','test_formal_package'), ('evidence_tools','test_qualified_gate_summary'))]
        extra_count = 0
        for name, path in additional:
            run(name, ['python3', str(path)])
            extra_count += int(re.search(r'Ran (\d+) tests?', (out/(name+'.log')).read_text())[1])
        e['v08_provenance_not_applicable'] = 'protocol02.test_tuning.TuningTest.test_original_production_and_launcher_unchanged'
        xml = out/'VelocityAxes.xml'
        run('VelocityAxes', [str(REPO/'build/px4_sitl_test/unit-VelocityAxes'), '--gtest_output=xml:'+str(xml)])
        counts = {k: int(v) for k,v in ET.parse(xml).getroot().attrib.items() if k in ('tests', 'failures', 'errors', 'disabled')}
        assert counts['tests'] > 0 and not any(counts[k] for k in ('failures', 'errors', 'disabled'))
        e['new_axes_tests'] = counts
        e['cpp_tests'] = previous['cpp_tests'] + counts['tests']
        e['python_tests'] = previous['python_tests'] + extra_count + int(re.search(r'Ran (\d+) tests?', (out/'interface_tests.log').read_text())[1])
        logs = list((out/'historical').rglob('VelocityModule.log'))
        assert len(logs) == 1
        run('actual_module_trace', ['python3', str(HERE/'interface.py'), '--trace-log', str(logs[0])])
        e['trace'] = json.loads((out/'actual_module_trace.log').read_text())
        run('configuration', ['python3', str(HERE/'interface.py'), 'yz'])
        run('diff_check', ['git', 'diff', '--check'])
        assert not subprocess.check_output(['git', 'diff', BASE, '--', 'research/sta-velocity-control/v08/formal',
            'src/modules/ekf2', 'src/modules/sensors', 'src/modules/land_detector', 'Tools/sitl_gazebo', 'ROMFS'], cwd=REPO)
        generated = REPO/'build/px4_sitl_default/msg/topics_sources/sta_velocity_ctrl_status.cpp'
        fields = re.search(r'__orb_sta_velocity_ctrl_status_fields\[\] = "([^"]+)"', generated.read_text())[1]
        e['ulog_format_bytes'] = len('sta_velocity_ctrl_status:') + len(fields) + 1
        assert e['ulog_format_bytes'] < 1500
        assert 'ORB_QUEUE_LENGTH = 8' in (REPO/'msg/sta_velocity_ctrl_status.msg').read_text()
        params = (REPO/'src/modules/mc_pos_control/mc_pos_control_params.c').read_text()
        metadata = {p.attrib['name']: p for p in ET.parse(REPO/'build/px4_sitl_default/parameters.xml').iter('parameter')}
        e['generated_metadata'] = {}
        for name, default in [('MPC_VC_MODE', 0), ('MPC_VC_AXES', 0), ('MPC_VC_DIV', 1)]:
            assert f'PARAM_DEFINE_INT32({name}, {default});' in params
            assert metadata[name].attrib['default'] == str(default)
            e['generated_metadata'][name] = dict(default=default, description=metadata[name].findtext('long_desc'))
        assert '5 XZ, 6 YZ' in e['generated_metadata']['MPC_VC_AXES']['description']
        assert 'Y/Z/XZ/YZ/XYZ require DIV1' in e['generated_metadata']['MPC_VC_DIV']['description']
        e['eeprom_after'] = sha(eeprom)
        assert e['eeprom_after'] == e['eeprom_before']
        e['firmware_sha256'] = sha(REPO/'build/px4_sitl_default/bin/px4')
        e['success'] = True
    finally:
        save()
        (out/'artifacts.sha256').write_text(''.join(f'{sha(f)}  {f}\n' for f in sorted(out.rglob('*')) if f.is_file() and f.name != 'artifacts.sha256'))
    print(json.dumps(e, indent=2))


if __name__ == '__main__':
    main()
