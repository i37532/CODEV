#!/usr/bin/env python3
"""Execute one prequalified local ROS/SITL attempt, never retry a failed attempt."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'tools'))
from run_hover import (active_simulators, check_envelope, check_parameters, diagnostic_json,
                       digest, native_topics_ready, new_logs, parse_parameters, parse_topic,
                       require, restore_parameters, save, snapshot_parameters)
from ros_bridge import atomic_json
from task_contract import PHASE_DURATION_S
from runner_contract import (SCORED_PHASES, diagnostic_expectations, check_diagnostics,
                             landing_confirmation_ready)


def wait_for_landing_confirmation(sample, record_event):
    """Keep sampling the existing safety path within the original 150 s budget.

    Never latch a landed/disarmed flag from a different snapshot. Only record
    the very snapshot whose publication times pass the frozen final-state rule.
    This helper is also exercised offline with a virtual clock and saved data.
    """
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline:
        state = sample('landing')
        ready = landing_confirmation_ready(state)
        # A blocking listener must not turn a late receipt into an on-time pass.
        if time.monotonic() >= deadline:
            break
        if ready:
            record_event('landed_disarmed', state)
            return state
        time.sleep(.1)
    raise TimeoutError('Landing and automatic disarm with fresh final state receipts')


def collect_diagnostics(job, scored, read_topic):
    """Read every required topic afresh; never substitute an empty/cached state."""
    expected = diagnostic_expectations(job, scored)
    observed = {name: read_topic(name) for name in expected}
    check_diagnostics(observed, expected)
    return observed


def terminate_owned(process):
    if process is None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def check_frozen(manifest, job):
    require(manifest.get('flight_qualified') is True, 'Draft is not flight qualified')
    require(not active_simulators(), 'Another simulator or QGC is active')
    for name, expected in manifest['assets'].items():
        require(digest(name) == expected, 'Frozen asset changed: ' + name)
    for row in manifest['jobs']:
        require(digest(Path(row['bin']) / 'px4') == row['firmware_sha256'], 'Firmware changed')
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=row['repo'], text=True).strip()
        require(head == row['source_head'], 'Repository HEAD changed')
        for name, expected in row.get('source_assets', {}).items():
            require(digest(Path(row['repo']) / name) == expected, 'Source changed: ' + name)
    process = subprocess.run([sys.executable, manifest['runtime']['preflight']],
                             capture_output=True, text=True, timeout=45)
    require(process.returncode == 0, 'Real ROS dependency preflight failed: ' + process.stdout)
    ready = json.loads(process.stdout)
    require(ready.get('ready') is True and ready.get('roundtrip_passed') is True,
            'No real DDS qualification')
    return ready


def execute(manifest_path, manifest, job):
    from pymavlink import mavutil
    from runner_contract import (check_order, check_active_state, stable_gate,
                                 position_time_us, receipt_ready)
    check_order(manifest, job['id'])
    runtime_receipt = check_frozen(manifest, job)
    output = Path(manifest['data_root']) / 'runs' / job['id']
    output.mkdir(parents=True, exist_ok=False)
    rootfs, binary_dir = Path(job['rootfs']), Path(job['bin'])
    result = dict(id=job['id'], system=job['system'], task=job['task'], success=False,
                  independent_replay_passed=False, events=[], logs=[],
                  manifest_sha256=digest(manifest_path), parameter_restore_exact=False,
                  started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
    save(output / 'manifest.json', manifest)
    save(output / 'job.json', job)
    save(output / 'runtime.json', runtime_receipt)
    save(output / 'result.json', result)
    snapshot = snapshot_parameters(rootfs, output, job.get('parameter_files', ()))
    log_roots = [rootfs / 'log', *[Path(p) for p in job.get('log_roots', [])]]
    old_logs = set(new_logs(log_roots, set()))
    proc = bridge_proc = link = worker = None
    stop = threading.Event()
    worker_errors, telemetry = [], {}
    origin = None
    generation = 0
    last_position = last_position_wall = None
    console = (output / 'console.log').open('x')
    bridge_console = (output / 'ros_console.log').open('x')
    commands = (output / 'commands.jsonl').open('x')
    samples = (output / 'samples.jsonl').open('x')

    def cli(module, *args, check=True):
        argv = [str(binary_dir / ('px4-' + module)), *map(str, args)]
        cp = subprocess.run(argv, cwd=rootfs, capture_output=True, text=True, timeout=10)
        commands.write(json.dumps(dict(argv=argv, exit_code=cp.returncode,
                                       stdout=cp.stdout, stderr=cp.stderr)) + '\n')
        commands.flush()
        require(not check or cp.returncode == 0, 'PX4 CLI failed: ' + repr(argv))
        return cp.stdout

    def topic(name):
        value = parse_topic(cli('listener', name, '-n', '1'))
        require(value.get('timestamp', 0) > 0, 'Missing native topic: ' + name)
        return value

    def diagnostics(scored=False):
        return collect_diagnostics(job, scored, topic)

    def verify_configuration(name, airborne=False):
        raw = cli('param', 'show', '-a')
        (output / ('parameters_' + name + '.txt')).write_text(raw)
        check_parameters(parse_parameters(raw), job['expected_parameters'])
        save(output / ('diagnostics_' + name + '.json'), diagnostic_json(diagnostics(airborne)))

    def receipt(required=False):
        if bridge_proc is None:
            require(not required, 'ROS bridge not started')
            return None
        require(bridge_proc.poll() is None, 'ROS bridge exited')
        require(not (output / 'ros/fatal.json').exists(), 'ROS bridge fatal evidence')
        path = output / 'ros/receipt.json'
        if not path.exists():
            require(not required, 'Missing ROS receipt')
            return None
        value = json.loads(path.read_text())
        require(value.get('status') != 'fatal', 'ROS fatal status')
        if required:
            require(value.get('status') == 'running' and value.get('dry_run') is False,
                    'ROS is not actually running')
            require(0 <= time.time() - value['wall_stamp'] <= .5, 'Stale ROS receipt')
            require(value.get('publisher_count') == 1 and value.get('subscriber_count', 0) >= 1,
                    'Wrong ROS publisher graph')
            require(value.get('telemetry_age') is not None and value['telemetry_age'] <= .5,
                    'Stale native ROS telemetry')
            require(value.get('native_clock_age') is not None and value['native_clock_age'] <= .5,
                    'ROS simulation clock stagnated')
            if value.get('sent_count', 0):
                require(0 <= value['latest_native_sim_us'] - value['last_sent_sim_us'] <= 500000,
                        'Target publication stalled despite live telemetry')
        return value

    def sample(phase, airborne=False):
        nonlocal last_position, last_position_wall
        require(proc is not None and proc.poll() is None and not worker_errors, 'Simulator/GCS monitor failed')
        state = dict(phase=phase, position=topic('vehicle_local_position'), status=topic('vehicle_status'),
                     land=topic('vehicle_land_detected'), attitude=topic('vehicle_attitude'),
                     takeoff=topic('takeoff_status'))
        p = state['position']
        timestamp = position_time_us(state)
        require(math.isfinite(timestamp) and p.get('timestamp_sample', timestamp) <= timestamp,
                'Invalid native position clocks')
        if last_position is not None:
            require(timestamp >= last_position, 'Native position publication regressed')
        if timestamp != last_position:
            last_position_wall = time.monotonic()
        require(last_position_wall is not None and time.monotonic() - last_position_wall <= 2,
                'Native simulation clock stopped')
        last_position = timestamp
        if origin is not None:
            state['diagnostics'] = diagnostics(phase in SCORED_PHASES)
            check_active_state(state, job, phase, origin)
        samples.write(json.dumps(diagnostic_json(state), allow_nan=False) + '\n')
        samples.flush()
        if bridge_proc is not None:
            receipt(required=airborne)
        return state

    def event(name, state):
        result['events'].append(dict(name=name, timestamp_us=int(state['position']['timestamp']),
                                     status_timestamp_us=int(state['status']['timestamp']),
                                     land_timestamp_us=int(state['land']['timestamp']),
                                     generation=generation))
        save(output / 'result.json', result)
        print(job['id'], name, flush=True)

    def control(phase, state, enabled=True):
        nonlocal generation
        generation += 1
        start = int(state['position']['timestamp'])
        atomic_json(output / 'control.json', dict(generation=generation, phase=phase, start_us=start,
                                                 origin=origin, enabled=enabled))
        result['events'].append(dict(name='control_change', timestamp_us=start, generation=generation,
                                     phase=phase, enabled=enabled))
        save(output / 'result.json', result)
        return start

    def phase_handshake(phase):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            value = receipt(required=True)
            if receipt_ready(value, generation, phase, 0, time.time()):
                return value
            time.sleep(.05)
        raise TimeoutError('New ROS phase was never actually sent: ' + phase)

    def phase(phase_name, state, stable=False):
        stable_start = position_time_us(state)
        start = control(phase_name, state)
        phase_handshake(phase_name)
        event(phase_name + '_start', state)
        duration = 15.0 if stable else PHASE_DURATION_S[phase_name]
        deadline, stable_since = time.monotonic() + duration * 3 + 15, None
        while time.monotonic() < deadline:
            state = sample(phase_name, airborne=True)
            elapsed = (state['position']['timestamp'] - start) * 1e-6
            if stable:
                stable_since, ready = stable_gate(state, origin, stable_start, stable_since)
                if ready:
                    event(phase_name + '_end', state)
                    return state
            elif elapsed >= duration:
                event(phase_name + '_end', state)
                return state
            time.sleep(.1)
        raise TimeoutError('Phase simulation-clock deadline: ' + phase_name)

    def receiver():
        last_heartbeat = last_manual = 0.0
        try:
            with (output / 'mavlink_events.jsonl').open('x') as stream:
                while not stop.is_set():
                    message = link.recv_match(blocking=True, timeout=.1)
                    if message:
                        telemetry[message.get_type()] = message
                        if message.get_type() in ('HEARTBEAT', 'STATUSTEXT', 'EXTENDED_SYS_STATE'):
                            stream.write(json.dumps(message.to_dict()) + '\n')
                            stream.flush()
                    now = time.monotonic()
                    if telemetry and now - last_heartbeat >= .5:
                        link.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,
                            mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, mavutil.mavlink.MAV_STATE_ACTIVE)
                        last_heartbeat = now
                    if telemetry and now - last_manual >= .1:
                        link.mav.manual_control_send(1, 0, 0, 500, 0, 0)
                        last_manual = now
        except BaseException as exc:
            worker_errors.append(repr(exc))

    try:
        link = mavutil.mavlink_connection('udpin:127.0.0.1:14550', source_system=255, source_component=190)
        worker = threading.Thread(target=receiver, daemon=True)
        worker.start()
        env = dict(os.environ)
        for key in ('DONT_RUN', 'NO_PXH', 'PYTHONPATH', 'AMENT_PREFIX_PATH', 'COLCON_PREFIX_PATH', 'ROS_DISTRO'):
            env.pop(key, None)
        env.update({key: str(value) for key, value in job['launch_env'].items()})
        proc = subprocess.Popen(job['launch_command'], cwd=job['repo'], env=env,
                                stdin=subprocess.PIPE, stdout=console, stderr=subprocess.STDOUT,
                                start_new_session=True)
        result['launcher_pid'] = proc.pid
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            require(proc.poll() is None, 'Simulator startup exited')
            if 'Startup script returned successfully' in (output / 'console.log').read_text(errors='replace'):
                break
            time.sleep(.5)
        else:
            raise TimeoutError('Simulator startup')
        require(digest(binary_dir / 'px4') == job['firmware_sha256'], 'Launcher changed firmware')
        (output / 'parameters_before.txt').write_text(cli('param', 'show', '-a'))
        for name, value in job['parameters'].items():
            cli('param', 'set', name, value)
        time.sleep(1)
        verify_configuration('start')
        cli('logger', 'on')
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            initial = {name: parse_topic(cli('listener', name, '-n', '1')) for name in
                       ('vehicle_local_position', 'vehicle_attitude', 'vehicle_status', 'vehicle_land_detected', 'takeoff_status')}
            if native_topics_ready(initial):
                break
            time.sleep(.5)
        else:
            raise TimeoutError('Native startup topics absent')
        warmup_start = initial['vehicle_local_position']['timestamp']
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            state = sample('warmup')
            require(state['status'].get('arming_state') == 1, 'Unexpected armed startup')
            if (state['position']['timestamp'] - warmup_start >= 30e6
                    and state['position'].get('xy_global') and telemetry):
                break
            time.sleep(.25)
        else:
            raise TimeoutError('Relative native 30 s warmup')
        logs = new_logs(log_roots, old_logs)
        require(logs and any(p.stat().st_size > 16 for p in logs), 'No native ULog before arm')
        require(state['land'].get('landed') is True, 'Not on ground')
        origin = {key: state['position'][key] for key in ('x', 'y', 'z', 'heading')}
        require(all(math.isfinite(value) for value in origin.values()), 'Invalid origin/yaw')
        save(output / 'origin.json', origin)
        control('prestream', state, enabled=False)
        ros_env = dict(os.environ, **manifest['runtime']['environment'])
        bridge_proc = subprocess.Popen([*manifest['runtime']['launcher'], str(HERE / 'ros_bridge.py'),
            '--control', str(output / 'control.json'), '--output', str(output / 'ros'), '--execute'],
            cwd=HERE, env=ros_env, stdout=bridge_console, stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            value = receipt()
            if (value and value.get('status') == 'running' and value.get('publisher_count') == 1
                    and value.get('telemetry_count', 0) > 0 and value.get('native_heartbeat_count', 0) > 0):
                break
            time.sleep(.1)
        else:
            raise TimeoutError('ROS native telemetry/graph')
        state = sample('prestream')
        start = control('prestream', state)
        phase_handshake('prestream')
        event('prestream_start', state)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            state = sample('prestream')
            value = receipt(required=True)
            if state['position']['timestamp'] - start >= 2e6 and value['sent_count'] >= 20:
                break
            time.sleep(.1)
        else:
            raise TimeoutError('Offboard prestream')
        event('prestream_end', state)
        cli('commander', 'mode', 'offboard')
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = sample('prestream')
            if state['status'].get('nav_state') == 14:
                break
            time.sleep(.1)
        else:
            raise TimeoutError('Offboard mode denied before arm')
        cli('commander', 'arm')
        event('arm_command', state)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = sample('prestream')
            if state['status'].get('arming_state') == 2:
                break
            time.sleep(.1)
        else:
            raise TimeoutError('Arm denied')
        state = phase('climb', state)
        state = phase('recover', state, stable=True)
        verify_configuration('hover', airborne=True)
        state = sample('recover', airborne=True)
        state = phase('hover', state)
        if job['task'] == 'position':
            state = phase('step_up', state)
            state = phase('step_down', state)
        elif job['task'] == 'velocity':
            state = phase('velocity', state)
        state = phase('recover', state, stable=True)
        state = phase('descend', state)
        cli('commander', 'mode', 'auto:land')
        event('land_command', state)
        # Keep the valid stream until the new mode is actually observed.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = sample('landing')
            if state['status'].get('nav_state') == 18:
                break
            time.sleep(.1)
        else:
            raise TimeoutError('AUTO_LAND not accepted')
        control('descend', state, enabled=False)
        state = wait_for_landing_confirmation(sample, event)
        verify_configuration('end')
        time.sleep(2)
        result['task_completed'] = True
    except BaseException as exc:
        result['error'] = repr(exc)
        print(job['id'], 'FAILED', repr(exc), flush=True)
    finally:
        for name, process in (('ros', bridge_proc), ('simulator', proc)):
            try:
                if name == 'simulator' and process is not None and process.poll() is None:
                    try:
                        cli('shutdown', check=False)
                        process.wait(timeout=10)
                    except (OSError, subprocess.TimeoutExpired, ValueError):
                        pass
                terminate_owned(process)
            except BaseException as exc:
                result[name + '_cleanup_error'] = repr(exc)
        stop.set()
        if worker:
            worker.join(timeout=2)
        if link:
            link.close()
        for stream in (console, bridge_console, commands, samples):
            stream.close()
        try:
            for index, source in enumerate(new_logs(log_roots, old_logs)):
                target = output / ('native_%02d.ulg' % index)
                shutil.copy2(source, target)
                result['logs'].append(dict(source=str(source), archive=str(target),
                    sha256=digest(target), bytes=target.stat().st_size))
        except BaseException as exc:
            result['archive_error'] = repr(exc)
        try:
            result.update(restore_parameters(rootfs, snapshot))
        except BaseException as exc:
            result['restore_error'] = repr(exc)
        result['remaining_simulators'] = active_simulators()
        save(output / 'result.json', result)
    if (result.get('task_completed') and result['parameter_restore_exact'] and not result['remaining_simulators']
            and not any(key.endswith('error') for key in result)):
        try:
            from analyze import audit_native_log
            require(bool(result['logs']), 'No raw ULog archived')
            selected = max(result['logs'], key=lambda row: row['bytes'])
            metrics = audit_native_log(selected['archive'], result['events'], origin, job, output / 'ros/sent.jsonl')
            save(output / 'metrics.json', metrics)
            replay = audit_native_log(selected['archive'], result['events'], origin, job, output / 'ros/sent.jsonl')
            require(metrics == replay and digest(selected['archive']) == selected['sha256'], 'Replay/fingerprint mismatch')
            save(output / 'independent_replay.json', replay)
            result['independent_replay_passed'] = True
            result['success'] = metrics['accepted'] is True
        except BaseException as exc:
            result['analysis_error'] = repr(exc)
    result['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    save(output / 'result.json', result)
    require(result['success'], 'Attempt failed; stop finite batch and preserve all evidence')


def main(argv=None):
    from runner_contract import validate_manifest
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--job', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text())
    job = validate_manifest(manifest, args.job)
    print(json.dumps(dict(id=job['id'], system=job['system'], task=job['task'], execute=args.execute)))
    if not args.execute:
        print('DRY RUN: no process, ROS, parameter write or arm command')
        return 0
    import fcntl
    with (Path(manifest['data_root']) / '.runner.lock').open('a') as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        execute(args.manifest.resolve(), manifest, job)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
