#!/usr/bin/env python3
"""Read-only eight-attempt draft and dependency check; never launches PX4."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from task_contract import BATCH_ORDER, ENTRY_LIMITS, PHASE_DURATION_S, SAFETY_LIMITS


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'results/four_systems/manifest04_pid.json'
RUNTIME = Path('/home/yr/.local/share/codev-ros-offboard/preflight.py')
LABELS = {'PID': 'PID', 'STA2': 'Upstream STA2', 'RSTA': 'RSTA', 'RISTA': 'RISTA'}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def draft(source):
    """Keep source parameters/firmware, never carry old attempts into new evidence."""
    by_label = {job['label']: job for job in source['jobs']}
    if len(by_label) != 4 or set(by_label) != set(LABELS.values()):
        raise ValueError('Require exactly the four separately identified source systems')
    jobs = []
    for index, (task, system) in enumerate(BATCH_ORDER, 1):
        old = by_label[LABELS[system]]
        parameters = copy.deepcopy(old['parameters'])
        if parameters.get('MPC_VCT_TEST', 0) != 0:
            raise ValueError('Internal task generator must remain disabled')
        if system != 'STA2':
            required = dict(MC_RTC_MODE=0, MC_STA_AXES=0, MC_RTC_DIV=1,
                            MC_RATT_TEST=0, MPC_VC_DIV=1)
            expected_mode = {'PID': 0, 'RSTA': 3, 'RISTA': 4}[system]
            required.update(MPC_VC_MODE=expected_mode, MPC_VC_AXES=0 if system == 'PID' else 7)
            if any(parameters.get(key) != value for key, value in required.items()):
                raise ValueError('Wrong selected velocity/rate configuration: ' + system)
        jobs.append(dict(id='O%03d' % index, task=task, system=system,
                         status='unattempted', repo=old['repo'],
                         firmware=str(Path(old['bin']) / 'px4'),
                         firmware_sha256=old['firmware_sha256'],
                         parameters=parameters,
                         expected_parameters=copy.deepcopy(old['expected_parameters']),
                         source_head=old['source_head']))
    return dict(schema=1, status='draft_not_flight_qualified', max_attempts=8,
                order=[job['id'] for job in jobs], jobs=jobs,
                phase_duration_s=dict(PHASE_DURATION_S), safety_limits=dict(SAFETY_LIMITS),
                entry_limits=dict(ENTRY_LIMITS), stop_on_first_failure=True,
                automatic_retry=False, retuning=False, new_flight_samples=0,
                comparison='system-level; n=1 per system/task; not formal inference',
                outstanding=['real ROS runtime and separate-process DDS roundtrip',
                             'end-to-end runner, native ULog acceptance and regression tests',
                             'preflight freeze of complete sources/assets/runtime and exact output paths'])


def check_assets(plan):
    seen = {}
    for job in plan['jobs']:
        path = job['firmware']
        if path not in seen:
            actual = sha256(path) if Path(path).is_file() else None
            seen[path] = dict(expected=job['firmware_sha256'], actual=actual,
                              match=actual == job['firmware_sha256'])
    return seen


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight', action='store_true', help='Read-only runtime/firmware checks')
    parser.add_argument('--report', type=Path, help='Save new JSON evidence, refusing an existing path')
    args = parser.parse_args(argv)
    plan = draft(json.loads(SOURCE.read_text()))
    plan['source_manifest_sha256'] = sha256(SOURCE)
    plan['tool_sha256'] = {path.name: sha256(path) for path in sorted(HERE.glob('*.py'))}
    if args.preflight:
        plan['firmware_checks'] = check_assets(plan)
        if RUNTIME.is_file():
            try:
                process = subprocess.run([sys.executable, str(RUNTIME)], capture_output=True,
                                         text=True, timeout=45)
                plan['runtime_check'] = dict(exit_code=process.returncode,
                                             stdout=process.stdout, stderr=process.stderr)
            except subprocess.TimeoutExpired:
                plan['runtime_check'] = dict(exit_code=None, error='45 s preflight timeout')
        else:
            plan['runtime_check'] = dict(exit_code=None, error='ROS preflight not installed')
    # A dependency check alone never grants flight qualification.
    plan['flight_qualified'] = False
    encoded = json.dumps(plan, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    if args.report:
        with args.report.open('x') as stream:
            stream.write(encoded)
    print(encoded, end='')
    return 2 if args.preflight else 0


if __name__ == '__main__':
    raise SystemExit(main())
