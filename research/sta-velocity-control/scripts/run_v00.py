#!/usr/bin/env python3
"""One-shot, three-attempt PID baseline; dry-run unless --execute is supplied."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'research/sta-rate-control/scripts'))
from run_m00 import main as legacy_run, active_simulators, ROOTFS, save, digest
from run_m04 import arrays
from capture_v00 import persisted_bson
from world_v00 import snapshot, validate_world

CONFIG = REPO / 'research/sta-velocity-control/v00/resume02'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO, text=True).strip()


def parse_params(raw):
    return {m[0]: float(m[1]) for m in re.findall(
        r'\b([A-Za-z0-9_]+)\s+\[[\d,]+\]\s*:\s*([-+\d.eE]+)', raw)}


def check_parameters(actual, expected):
    for k, v in expected.items():
        if k not in actual or not math.isfinite(actual[k]) or not math.isclose(actual[k], v, rel_tol=2e-5, abs_tol=2e-6):
            raise RuntimeError(f'Parameter mismatch {k}: {actual.get(k)} != {v}')


def encode_bson(values, types):
    payload = bytearray()
    for name, value in sorted(values.items()):
        is_int = types[name] == 'Int32'
        payload += bytes([16 if is_int else 1]) + name.encode() + b'\0'
        payload += struct.pack('<i' if is_int else '<d', int(value) if is_int else float(value))
    return struct.pack('<i', len(payload) + 5) + payload + b'\0'


def check_inner(d):
    for k, v in {'requested_mode': 0, 'requested_axes': 0, 'effective_mode': 0,
                 'effective_axes': 0, 'div_req': 1, 'div_eff': 1, 'fault': 0,
                 'abort_requested': 0, 'termination': 0}.items():
        if d.get(k) != v:
            raise RuntimeError(f'Inner PID mismatch: {k}={d.get(k)}')
    if d.get('armed') and d.get('rate_enabled'):
        if not d.get('measurement_valid') or not d.get('output_valid') or d.get('timing_status') != 0:
            raise RuntimeError('Invalid active inner-loop sample')


class Checks:
    simulation_speed = 1

    def __init__(self, protocol, expected):
        self.p = protocol
        self.expected = expected
        self.ground = None
        self.last_seq = None

    def prepare_environment(self, output):
        return {'GAZEBO_MODEL_PATH': '', 'GAZEBO_PLUGIN_PATH': '',
                'LD_LIBRARY_PATH': '', 'PX4_SIM_SPEED_FACTOR': '1'}

    def __call__(self, phase, cli, topic, output):
        if phase == 'preflight':
            if topic('vehicle_status').get('arming_state') != 1:
                raise RuntimeError('Must begin disarmed')
            params = parse_params(cli('param', 'show', '-a'))
            check_parameters(params, self.expected)
            save(output / 'runtime_parameters_start.json', params)
            console = (output / 'console.log').read_text()
            model = str(REPO / 'Tools/sitl_gazebo/models/iris/iris.sdf')
            if 'Using: ' + model not in console:
                raise RuntimeError('Actual model not confirmed')
            launcher_pid = json.loads((output / 'result.json').read_text())['launcher_pid']
            world = REPO / 'sitl/worlds/empty_grey.world'
            evidence = snapshot(launcher_pid, world)
            save(output / 'world_process.json', evidence)
            validate_world(evidence['servers'], launcher_pid, evidence['launcher_sid'],
                           world, 'http://127.0.0.1:11345')
            expected_hash = json.loads((CONFIG / 'frozen.json').read_text())['assets'][str(world.relative_to(REPO))]
            if evidence['world_sha256'] != expected_hash:
                raise RuntimeError('World changed after frozen-asset check')
            (output / 'uorb_start.txt').write_text(cli('uorb', 'status'))
            cli('logger', 'stop')
            time.sleep(1.1)
            cli('logger', 'start', '-b', '256', '-r', '1000', '-t', '-f')
        elif phase == 'hover':
            pos = topic('vehicle_local_position')
            if self.ground is None or abs(self.ground[2] - pos['z'] - 2.5) > .5:
                raise RuntimeError('Did not reach target altitude 2.5 +/- .5m')
            (output / 'uorb_hover.txt').write_text(cli('uorb', 'status'))
        elif phase == 'disarmed':
            params = parse_params(cli('param', 'show', '-a'))
            check_parameters(params, self.expected)
            save(output / 'runtime_parameters_end.json', params)
            cli('param', 'save', str(output / 'runtime_parameters_end.bson'))
        elif phase == 'cleanup':
            cli('logger', 'stop', check=False)

    def monitor(self, phase, cli, topic, output, state):
        pos, vehicle = state['position'], state['status']
        d = topic('sta_rate_ctrl_status')
        if phase == 'warmup' and ('timestamp' not in d or 'timestamp' not in pos):
            return
        check_inner(d)
        if abs(pos['timestamp'] - d['timestamp']) > 1e6 or d['publish_seq'] == self.last_seq:
            raise RuntimeError('Stale diagnostic')
        self.last_seq = d['publish_seq']
        if phase == 'warmup' and pos.get('xy_valid') and pos.get('z_valid'):
            self.ground = [pos['x'], pos['y'], pos['z']]
            save(output / 'ground.json', self.ground)
        if vehicle.get('arming_state') == 2:
            if vehicle.get('failsafe') or vehicle.get('failure_detector_status'):
                raise RuntimeError('Vehicle failsafe/failure detector')
            for k in ('xy_valid', 'z_valid', 'v_xy_valid', 'v_z_valid'):
                if not pos.get(k):
                    raise RuntimeError('Invalid local position: ' + k)
            q = arrays(cli('listener', 'vehicle_attitude', '-n', '1'), 'q')
            if len(q) != 4 or not all(math.isfinite(v) for v in q):
                raise RuntimeError('Invalid attitude')
            tilt = math.degrees(math.acos(max(-1., min(1., 1 - 2*(q[1]**2 + q[2]**2)))))
            xy_speed = math.hypot(pos['vx'], pos['vy'])
            xy_dist = math.hypot(pos['x'] - self.ground[0], pos['y'] - self.ground[1])
            height = self.ground[2] - pos['z']
            if tilt > 15 or xy_speed > 1 or xy_dist > 2 or not -.5 <= height <= 4:
                raise RuntimeError('Position/tilt/velocity flight envelope')
            if abs(pos['vz']) > (.6 if phase == 'hover' else 3.5):
                raise RuntimeError('Vertical velocity envelope')
            if phase == 'hover' and abs(height - 2.5) > 1:
                raise RuntimeError('Hover altitude envelope')
        with (output / 'v00_monitor.jsonl').open('a') as stream:
            stream.write(json.dumps({'phase': phase, 'inner': d}) + '\n')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--execute', action='store_true')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--source-head', required=True)
    args = p.parse_args()
    protocol = json.loads((CONFIG / 'protocol.json').read_text())
    frozen = json.loads((CONFIG / 'frozen.json').read_text())
    print(json.dumps(protocol, ensure_ascii=False, indent=2), flush=True)
    if not args.execute:
        print('DRY RUN: no process, file or parameter changes')
        return
    if git('branch', '--show-current') != 'research/sta-velocity-control' or git('rev-parse', 'HEAD') != args.source_head:
        raise RuntimeError('Wrong branch/HEAD')
    if git('status', '--porcelain') or git('submodule', 'foreach', '--recursive', '--quiet', 'git status --porcelain'):
        raise RuntimeError('Dirty source/submodules')
    if any(x[:1] in ('+', '-', 'U') for x in git('submodule', 'status', '--recursive').splitlines()):
        raise RuntimeError('Submodule revision mismatch')
    if active_simulators():
        raise RuntimeError('Conflicting simulator/GCS')
    if shutil.disk_usage(ROOTFS).free < 10 * 1024**3:
        raise RuntimeError('Need at least 10 GiB free; never delete old logs')
    if (ROOTFS / 'etc/logging/logger_topics.txt').exists():
        raise RuntimeError('Custom logging file would override profile')
    if any((REPO / 'Tools/sitl_gazebo/models/iris').glob('*-gen.sdf')):
        raise RuntimeError('Unexpected generated Iris model override')
    for port in (14550, 11345):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM if port == 14550 else socket.SOCK_STREAM) as sock:
            sock.bind(('127.0.0.1', port))
    for rel, expected in frozen['assets'].items():
        if digest(REPO / rel) != expected:
            raise RuntimeError('Frozen asset mismatch: ' + rel)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    parameter_file = ROOTFS / 'eeprom/parameters_10016'
    original = parameter_file.read_bytes()
    (out / 'original_parameters_10016.bson').write_bytes(original)
    original_values = persisted_bson(original)
    defaults = json.loads((REPO / 'build/px4_sitl_default/parameters.json').read_text())['parameters']
    types = {x['name']: x['type'] for x in defaults}
    overrides = {**original_values, **protocol['startup_overrides']}
    before_profile = int(original_values.get('SDLOG_PROFILE', 131))
    overrides['SDLOG_PROFILE'] = before_profile | 16
    # Freeze current baseline gains; do not silently retune to generated defaults.
    check_parameters({**{x['name']: x['default'] for x in defaults}, **original_values}, frozen['control_parameters'])
    baseline = encode_bson(overrides, types)
    ledger = dict(source_head=args.source_head, attempts=[], success=False, planned=3,
                  original_parameter_sha256=hashlib.sha256(original).hexdigest(),
                  firmware_sha256=digest(REPO / 'build/px4_sitl_default/bin/px4'),
                  before_profile=before_profile, applied_profile=before_profile | 16)
    save(out / 'ledger.json', ledger)
    try:
        for index in range(1, 4):
            if active_simulators() or git('status', '--porcelain') or git('rev-parse', 'HEAD') != args.source_head:
                raise RuntimeError('State changed before next attempt')
            parameter_file.write_bytes(baseline)
            run = out / f'run{index:02d}'
            item = dict(attempt=index, seed=None, directory=str(run), status='running')
            ledger['attempts'].append(item)
            save(out / 'ledger.json', ledger)
            old_argv = sys.argv
            try:
                sys.argv = [__file__, '--output', str(run)]
                expected = {**frozen['control_parameters'], **protocol['startup_overrides'],
                            'SYS_AUTOSTART': 10016, 'SDLOG_PROFILE': before_profile | 16}
                legacy_run(checks=Checks(protocol, expected), scenario_path=CONFIG / 'protocol.json')
                if digest(REPO / 'build/px4_sitl_default/bin/px4') != ledger['firmware_sha256']:
                    raise RuntimeError('Launcher changed firmware; stop without retry')
                from analyze_v00 import analyze
                metrics = analyze(run, protocol)
                save(run / 'v00_metrics.json', metrics)
                if not metrics['accepted']:
                    raise RuntimeError('ULog validation rejected')
                item['status'] = 'accepted'
            except BaseException as exc:
                item['status'], item['error'] = 'failed', repr(exc)
                raise
            finally:
                sys.argv = old_argv
                save(out / 'ledger.json', ledger)
                if not active_simulators():
                    parameter_file.write_bytes(original)
            if parameter_file.read_bytes() != original:
                raise RuntimeError('Parameter restoration failed')
        ledger['success'] = True
    finally:
        if not active_simulators():
            parameter_file.write_bytes(original)
        ledger['parameter_restore_exact'] = parameter_file.read_bytes() == original
        ledger['remaining_simulators'] = active_simulators()
        save(out / 'ledger.json', ledger)


if __name__ == '__main__':
    main()
