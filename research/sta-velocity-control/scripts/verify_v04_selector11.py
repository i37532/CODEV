#!/usr/bin/env python3
"""Offline real-uORB selector tests and read-only series09 fault audit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--expect-old-failure', action='store_true')
    args = p.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    e = dict(offline=True, flights=0, success=False, expected_old_failure=args.expect_old_failure,
             commands=[], head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip())
    env = os.environ.copy()
    env['PATH'] = str(REPO / '.px4-python/bin') + ':' + env['PATH']
    env['PYTHONPATH'] = ':'.join([str(REPO / '.px4-python'),
        '/home/yr/Desktop/codev doc/experiments/M00-20260912/python', env.get('PYTHONPATH', '')])
    def save():
        (out / 'evidence.json').write_text(json.dumps(e, indent=2) + '\n')
    def run(name, argv, expected=0):
        with (out / (name + '.log')).open('w') as stream:
            r = subprocess.run(argv, cwd=REPO, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=900)
        e['commands'].append(dict(name=name, argv=argv, exit_code=r.returncode, expected=expected)); save()
        print(name, r.returncode, flush=True)
        if r.returncode != expected:
            raise RuntimeError(name + ' failed; evidence retained')
    save()
    try:
        run('build_selector', ['cmake', '--build', 'build/px4_sitl_test', '--target', 'functional-EKF2Selector', '-j4'])
        run('selector', ['timeout', '60s', str(REPO / 'build/px4_sitl_test/functional-EKF2Selector'),
            '--gtest_output=xml:' + str(out / 'selector.xml')], 1 if args.expect_old_failure else 0)
        e['tests'] = {k: int(v) for k, v in ET.parse(out / 'selector.xml').getroot().attrib.items()
                      if k in ('tests', 'failures', 'errors', 'disabled')}
        assert e['tests']['tests'] > 0 and e['tests']['disabled'] == 0
        assert bool(e['tests']['failures']) == args.expect_old_failure
        from pyulog import ULog
        record = json.loads((REPO / 'research/sta-velocity-control/v04/results10/run01.json').read_text())
        entry = max(record['logs'], key=lambda x: x['bytes']); path = Path(entry['archive'])
        assert sha(path) == entry['sha256']
        log = ULog(str(path), message_name_filter_list=['estimator_status_flags', 'vehicle_local_position'])
        e['fault_transitions'] = []
        for topic in log.data_list:
            d = topic.data
            if topic.name == 'estimator_status_flags':
                for i, t in enumerate(d['timestamp']):
                    if 113400000 <= t <= 113600000:
                        e['fault_transitions'].append(dict(instance=topic.multi_id, timestamp=int(t),
                            sample=int(d['timestamp_sample'][i]), faults=[k for k in d if k.startswith('fs_') and d[k][i]],
                            changes=int(d['fault_status_changes'][i])))
            if topic.name == 'vehicle_local_position':
                s = d['timestamp_sample']
                e['local_sample_reversals'] = [dict(timestamp=int(d['timestamp'][i]), previous=int(s[i-1]), current=int(s[i]))
                    for i in range(1, len(s)) if int(s[i]) < int(s[i-1])]
        assert {x['instance'] for x in e['fault_transitions'] if x['faults'] == ['fs_bad_acc_clipping']} == set(range(6))
        assert e['local_sample_reversals']
        e['historical_ulog_sha256'] = sha(path)
        assert e['historical_ulog_sha256'] == entry['sha256']
        e['source_fingerprints'] = {str(p.relative_to(REPO)): sha(p) for p in [
            REPO / 'src/modules/ekf2/EKF2Selector.cpp', REPO / 'src/modules/ekf2/EKF2Selector.hpp',
            REPO / 'src/modules/ekf2/EKF2SelectorTest.cpp']}
        if not args.expect_old_failure:
            run('full_control_regression', ['python3', str(REPO /
                'research/sta-velocity-control/z_velocity/verify_z01.py'), '--output', str(out / 'control')])
        e['success'] = True
    finally:
        save()
        files = sorted(x for x in out.rglob('*') if x.is_file() and x.name != 'artifacts.sha256')
        (out / 'artifacts.sha256').write_text(''.join(f'{sha(x)}  {x}\n' for x in files))
    print(json.dumps(e, indent=2))


if __name__ == '__main__':
    main()
