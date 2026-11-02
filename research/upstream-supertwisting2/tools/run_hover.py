#!/usr/bin/env python3
"""One explicitly frozen, native-topic SITL hover attempt; no retries or tuning.

This small system-level runner deliberately does not impersonate the old RI07
diagnostic/acceptance chain. Nothing runs without --execute. All commands target
the single locally launched PX4 instance and only its own process group is stopped.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import threading
import time


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def parse_topic(text):
    result = {}
    for line in text.splitlines():
        match = re.match(r'\s+(\w+):\s+(.+)', line)
        if not match:
            continue
        key, value = match.groups()
        if value.startswith('['):
            result[key] = [float(x) for x in value.split(']', 1)[0][1:].split(',')]
        elif value.split()[0] in ('True', 'False'):
            result[key] = value.split()[0] == 'True'
        else:
            try:
                result[key] = float(value.split()[0])
            except ValueError:
                pass
    return result


def parse_parameters(text):
    return {name: float(value) for name, value in re.findall(
        r'^.*?\b([A-Z][A-Z0-9_]+)\s+\[[^\]]+\]\s*:\s*([-+0-9.eE]+)', text, re.M)}


def native_topics_ready(topics):
    return bool(topics) and all(math.isfinite(t.get('timestamp', 0)) and t.get('timestamp', 0) > 0
                               for t in topics.values())


def diagnostic_json(value):
    """Preserve documented N/A states without invalid JSON or substituting zero.

    Only diagnostic receipts use this conversion. Manifest, parameters, flight
    states and metrics retain their existing finite-value validation.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return 'NaN' if math.isnan(value) else ('+Inf' if value > 0 else '-Inf')
    if isinstance(value, dict):
        return {k:diagnostic_json(v) for k,v in value.items()}
    if isinstance(value, list):
        return [diagnostic_json(v) for v in value]
    return value


def check_parameters(actual, expected):
    for key, value in expected.items():
        require(key in actual and math.isfinite(actual[key]), 'Missing/invalid parameter ' + key)
        require(math.isclose(actual[key], value, rel_tol=2e-6, abs_tol=6e-5),
                'Parameter mismatch ' + key + ': ' + str(actual[key]) + ' != ' + str(value))


def active_simulators():
    found = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            name = (entry / 'comm').read_text().strip()
            if name in ('px4', 'gzserver', 'gzclient', 'gazebo', 'QGroundControl'):
                found.append([int(entry.name), name])
        except (OSError, ProcessLookupError):
            pass
    return found


def validate_manifest(manifest, job_id):
    count = len(manifest['jobs'])
    addition = manifest.get('pid_addition')
    if addition is not None:
        require(count == manifest['max_attempts'] == 4 and addition.get('new_attempts') == 1,
                'PID addition authorizes exactly one new attempt')
        require(job_id == manifest['jobs'][-1]['id'] and manifest['jobs'][-1]['label'] == 'PID',
                'Only the newly added PID may execute; prior flights are read-only')
        require(set(addition['preserved_results']) == {j['id'] for j in manifest['jobs'][:3]},
                'All three prior results must be frozen')
        check_parameters(manifest['jobs'][-1]['parameters'], dict(MPC_VC_MODE=0, MPC_VC_AXES=0,
            MPC_VC_DIV=1, MC_RTC_MODE=0, MC_STA_AXES=0, MC_RTC_DIV=1, MC_RATT_TEST=0))
    else:
        require(manifest['max_attempts'] == count == 3,
                'Exactly three finite system-level attempts required')
    require(manifest['hover_s'] == 10 and manifest['takeoff_alt_m'] == 2.5,
            'Task must be 2.5 m / 10 s')
    ids = [j['id'] for j in manifest['jobs']]
    require(len(set(ids)) == count and manifest['order'] == ids and job_id in ids, 'Invalid order/identity')
    require(all(re.fullmatch(r'[A-Za-z0-9_-]+', name) for name in ids), 'Unsafe output ID')
    job = manifest['jobs'][ids.index(job_id)]
    for key in ('repo', 'bin', 'rootfs'):
        require(Path(job[key]).is_absolute(), 'Require absolute ' + key)
    require(isinstance(job['launch_command'], list) and job['launch_command'] and
            all(isinstance(x, str) for x in job['launch_command']), 'Expected argv, not shell command')
    require(isinstance(job['launch_env'], dict), 'Expected environment mapping')
    require(job['parameters'].get('MPC_VCT_TEST', 0) in (0, 5), 'No waveform/pure-velocity task')
    require(job['parameters'].get('MIS_TAKEOFF_ALT') == 2.5, 'Explicit 2.5 m command required')
    require(job['parameters'].get('SDLOG_MODE') == 1, 'Prearm native logging required')
    require(all(isinstance(v, (int, float)) and math.isfinite(v)
                for mapping in (job['parameters'], job['expected_parameters']) for v in mapping.values()),
            'Nonfinite parameter')
    check_parameters(job['expected_parameters'], job['parameters'])
    return job


def check_order(manifest, job_id):
    root = Path(manifest['data_root'])
    index = manifest['order'].index(job_id)
    def output(name):
        job = next(j for j in manifest['jobs'] if j['id'] == name)
        return Path(job['result_path']).parent if job.get('result_path') else root/'runs'/name
    require(not output(job_id).exists(), 'Attempt already exists: no rerun/replacement')
    for previous in manifest['order'][:index]:
        path = output(previous) / 'result.json'
        require(path.is_file() and json.loads(path.read_text()).get('success') is True,
                'Previous attempt missing/failed; stop batch')
        if manifest.get('pid_addition'):
            require(digest(path) == manifest['pid_addition']['preserved_results'][previous],
                    'Preserved result changed')
    for later in manifest['order'][index + 1:]:
        require(not output(later).exists(), 'Out-of-order attempt already exists')


def tilt(q):
    require(len(q) == 4 and all(math.isfinite(x) for x in q), 'Invalid attitude quaternion')
    norm = sum(x*x for x in q)
    require(abs(norm - 1) < .02, 'Unnormalised attitude quaternion')
    return math.degrees(math.acos(max(-1., min(1., 1 - 2*(q[1]**2 + q[2]**2)))))


def check_envelope(position, attitude, origin, phase):
    values = [position[k] for k in ('x', 'y', 'z', 'vx', 'vy', 'vz')]
    require(all(math.isfinite(x) for x in values), 'Invalid estimated position/velocity')
    require(all(position.get(k) for k in ('xy_valid', 'z_valid', 'v_xy_valid', 'v_z_valid')),
            'Invalid position/velocity estimate')
    height = origin['z'] - position['z']
    require(-.5 <= height <= 4 and abs(position['vz']) <= 3.5, 'Full-flight height/vertical speed envelope')
    require(math.hypot(position['vx'], position['vy']) <= 1, 'Horizontal speed envelope')
    require(math.hypot(position['x']-origin['x'], position['y']-origin['y']) <= 2, 'Horizontal position envelope')
    require(tilt(attitude['q']) <= 15, 'Tilt envelope')
    if phase == 'hover':
        require(abs(height - 2.5) <= 1 and abs(position['vz']) <= .6, 'Hover vertical envelope')
    return height


def entry_ok(state, origin):
    p, s, land = state['position'], state['status'], state['land']
    return (s.get('nav_state') == 4 and s.get('arming_state') == 2 and not s.get('failsafe') and
            not land.get('landed', True) and abs(origin['z']-p['z']-2.5) <= .3 and abs(p['vz']) < .2)


def hold_target(position, height=2.5):
    """Explicit global Hold target for CODEV's takeoff-to-POSCTL handoff.

    Do not capture the intermediate altitude when requesting AUTO_LOITER.
    Small local NED offsets use the same spherical map radius as PX4 geo.
    """
    required = ('ref_lat', 'ref_lon', 'ref_alt', 'x', 'y', 'z')
    require(all(k in position and math.isfinite(position[k]) for k in required), 'Missing global reference')
    latitude = position['ref_lat'] + math.degrees(position['x']/6371000.)
    scale = math.cos(math.radians(position['ref_lat']))
    require(abs(scale) > .1, 'Polar projection unsupported by simple hover task')
    longitude = position['ref_lon'] + math.degrees(position['y']/(6371000.*scale))
    return dict(latitude_e7=round(latitude*1e7), longitude_e7=round(longitude*1e7),
                altitude_m=position['ref_alt']-position['z']+height)


def parameter_paths(rootfs, extra=()):
    """Explicit parameter namespaces only; never walk/delete raw ULog files."""
    rootfs = Path(rootfs)
    folder = Path(rootfs) / 'eeprom'
    paths = set(p for p in folder.rglob('*') if p.is_file()) if folder.exists() else set()
    if rootfs.exists():
        paths.update(p for p in rootfs.rglob('*param*.bson') if p.is_file() and
                     not any(part in ('log', 'logs') for part in p.relative_to(rootfs).parts))
    paths.update(Path(rootfs) / name for name in extra)
    return paths


def snapshot_parameters(rootfs, output, extra=()):
    paths = parameter_paths(rootfs, extra)
    snapshot = {}
    for index, path in enumerate(sorted(paths)):
        require(path.resolve().is_relative_to(Path(rootfs).resolve()) and not path.is_symlink(), 'Unsafe parameter path')
        name = str(path.relative_to(rootfs))
        if path.exists():
            backup = output / ('parameter_backup_%03d.bin' % index)
            shutil.copy2(path, backup)
            snapshot[name] = dict(existed=True, backup=str(backup), sha256=digest(path))
        else:
            snapshot[name] = dict(existed=False)
    save(output / 'parameter_backup.json', snapshot)
    return snapshot


def restore_parameters(rootfs, snapshot):
    rootfs = Path(rootfs)
    current = set(str(p.relative_to(rootfs)) for p in parameter_paths(rootfs))
    current.update(snapshot)
    removed = []
    for name in sorted(current):
        path = rootfs / name
        require(path.resolve().is_relative_to(rootfs.resolve()) and not path.is_symlink(), 'Unsafe restore path')
        old = snapshot.get(name, {'existed': False})
        if old['existed']:
            require(digest(old['backup']) == old['sha256'], 'Backup changed')
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old['backup'], path)
            require(digest(path) == old['sha256'], 'Parameter restoration differs')
        elif path.exists():
            path.unlink()
            removed.append(name)
    return dict(parameter_restore_exact=True, removed_new_parameter_files=removed,
                original_files=len([x for x in snapshot.values() if x['existed']]))


def new_logs(roots, old):
    found = set()
    for root in roots:
        if root.exists():
            found.update(p.resolve() for p in root.rglob('*.ulg'))
    return sorted(found - old)


def audit_native_log(path, events, origin, diagnostic_expectations=None):
    """Common actual native fields, full-flight safety; no invented diagnostics."""
    import numpy as np
    from pyulog import ULog
    diagnostic_expectations = diagnostic_expectations or {}
    log = ULog(str(path), message_name_filter_list=['vehicle_local_position', 'vehicle_attitude',
        'vehicle_status', 'vehicle_land_detected', 'vehicle_local_position_setpoint', *diagnostic_expectations])
    require(not log.dropouts and not getattr(log, 'file_corruption', False), 'ULog dropout/corruption')
    e = {x['name']: x['timestamp_us'] for x in events}
    start, hs, he, end = [e[x] for x in ('takeoff_command', 'hover_start', 'hover_end', 'landed_disarmed')]
    require(start < hs < he < end and he-hs >= 10e6, 'Incomplete flight events')
    p = log.get_dataset('vehicle_local_position').data
    t = p['timestamp_sample'].astype(np.int64) if 'timestamp_sample' in p else p['timestamp'].astype(np.int64)
    require(np.all(np.diff(t) > 0), 'Position sample clock not strictly increasing')
    require(np.all(np.diff(p['timestamp'].astype(np.int64)) >= 0), 'Position publication time reversed')
    require(t[0] < start and t[-1] >= end-100000, 'Incomplete position log boundaries')
    full = (t >= start) & (t <= end)
    hover = (t >= hs) & (t < hs + 10_000_000)
    require(np.count_nonzero(hover) >= 20 and np.max(np.diff(t[full])) <= 500000, 'Insufficient native position coverage')
    xyz = np.column_stack([p[k] for k in ('x', 'y', 'z')]).astype(float)
    vel = np.column_stack([p[k] for k in ('vx', 'vy', 'vz')]).astype(float)
    require(np.isfinite(xyz[full]).all() and np.isfinite(vel[full]).all(), 'Nonfinite logged state')
    height = origin['z']-xyz[:, 2]
    require(np.min(height[full]) >= -.5 and np.max(height[full]) <= 4 and np.max(abs(vel[full, 2])) <= 3.5,
            'Logged full-flight vertical envelope')
    require(np.max(np.linalg.norm(vel[full, :2], axis=1)) <= 1 and
            np.max(np.linalg.norm(xyz[full, :2]-[origin['x'], origin['y']], axis=1)) <= 2, 'Logged XY envelope')
    require(np.max(abs(height[hover]-2.5)) <= 1 and np.max(abs(vel[hover, 2])) <= .6, 'Logged hover envelope')
    for key in ('xy_valid', 'z_valid', 'v_xy_valid', 'v_z_valid'):
        require(np.all(p[key][full]), 'Invalid logged estimate '+key)
    a = log.get_dataset('vehicle_attitude').data
    am = (a['timestamp'] >= start) & (a['timestamp'] <= end)
    qs = np.column_stack([a['q[%d]' % i][am] for i in range(4)])
    require(len(qs) > 20, 'Missing attitude log')
    angles = [tilt(q) for q in qs]
    require(max(angles) <= 15, 'Logged tilt envelope')
    def hold_check(name, field, left, right, value):
        data = log.get_dataset(name).data
        clock = data['timestamp'].astype(np.int64)
        require(np.all(np.diff(clock) >= 0) and len(clock), 'Invalid state topic clock '+name)
        before = np.searchsorted(clock, left, side='right')-1
        require(before >= 0, 'Missing state predecessor '+name)
        rows = np.r_[before, np.flatnonzero((clock > left) & (clock <= right))]
        require(np.all(data[field][rows] == value), 'Logged state '+name+'.'+field)
    for field, value in (('nav_state', 4), ('arming_state', 2), ('failsafe', 0)):
        hold_check('vehicle_status', field, hs, he, value)
    hold_check('vehicle_land_detected', 'landed', hs, he, 0)
    final = next(x for x in events if x['name'] == 'landed_disarmed')
    status_end = final.get('status_timestamp_us', end)
    land_end = final.get('land_timestamp_us', end)
    require(abs(status_end-end) <= 500000 and abs(land_end-end) <= 500000, 'Stale final state receipts')
    hold_check('vehicle_status', 'arming_state', status_end, status_end, 1)
    hold_check('vehicle_land_detected', 'landed', land_end, land_end, 1)
    for topic_name, fields in diagnostic_expectations.items():
        data = log.get_dataset(topic_name).data
        clock = data['timestamp'].astype(np.int64)
        window = (clock >= hs) & (clock < hs+10_000_000)
        require(np.count_nonzero(window) >= 20, 'Missing controller diagnostics '+topic_name)
        require(np.max(np.diff(clock[window])) <= 500000, 'Diagnostic gap '+topic_name)
        for field, value in fields.items():
            require(np.all(data[field][window] == value), 'Wrong logged controller '+topic_name+'.'+field)
    # Native unqueued logs are explicitly not the full-rate RI07 mirror contract.
    return dict(accepted=True, native_position_records=int(np.count_nonzero(full)),
        maximum_native_position_gap_s=float(np.max(np.diff(t[full]))*1e-6),
        hover_velocity_rms_xyz_m_s=np.sqrt(np.mean(vel[hover]**2, axis=0)).tolist(),
        nominal_height_rmse_m=float(np.sqrt(np.mean((height[hover]-2.5)**2))),
        takeoff_to_stable_s=(hs-start)*1e-6, maximum_tilt_deg=max(angles),
        maximum_height_m=float(np.max(height[full])),
        caveat='One native-topic system-level run; not RI07 formal/full-rate acceptance; EKF estimates, not truth')


def execute(manifest_path, manifest, job):
    from pymavlink import mavutil
    job_id = job['id']
    check_order(manifest, job_id)
    require(not active_simulators(), 'Another simulator/QGC is active')
    repo, binary_dir, rootfs = (Path(job[k]).resolve() for k in ('repo', 'bin', 'rootfs'))
    binary = binary_dir / 'px4'
    require(digest(binary) == job['firmware_sha256'], 'Frozen firmware differs')
    actual_head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    require(actual_head == job['source_head'], 'Frozen source HEAD differs')
    for file, expected in manifest.get('assets', {}).items():
        require(digest(file) == expected, 'Frozen tool/model/plugin differs '+file)
    for file, expected in job.get('source_assets', {}).items():
        require(digest(repo / file) == expected, 'Frozen source asset differs '+file)
    output = Path(job['result_path']).parent if job.get('result_path') else Path(manifest['data_root'])/'runs'/job_id
    require(not job.get('result_path') or Path(job['result_path']).name == 'result.json', 'result_path must end result.json')
    output.mkdir(parents=True, exist_ok=False)
    save(output / 'manifest.json', manifest)
    save(output / 'job.json', job)
    snapshot = snapshot_parameters(rootfs, output, job.get('parameter_files', ()))
    log_roots = [rootfs/'log', *[Path(p) for p in job.get('log_roots', [])]]
    if job['launch_env'].get('PX4_SITL_LOG_DIR'):
        log_roots.append(Path(job['launch_env']['PX4_SITL_LOG_DIR']))
    old_logs = set(new_logs(log_roots, set()))
    result = dict(success=False, id=job_id, label=job['label'], source_head=actual_head,
        binary_sha256=job['firmware_sha256'], manifest_sha256=digest(manifest_path),
        runner_sha256=digest(__file__), events=[], logs=[], parameter_restore_exact=False,
        command=job['launch_command'], scope='single descriptive system-level hover; no retry or retune')
    save(output/'result.json', result)
    commands = (output/'commands.jsonl').open('x')
    samples = (output/'samples.jsonl').open('x')
    console = (output/'console.log').open('x')
    stop = threading.Event()
    link = mavutil.mavlink_connection('udpin:127.0.0.1:14550', source_system=255, source_component=190)
    telemetry = {}
    wire_lock = threading.Lock()
    worker_error = []
    proc = None
    origin = None
    def receiver():
        last_hb = last_manual = 0
        try:
            with (output/'mavlink_events.jsonl').open('x') as stream:
                while not stop.is_set():
                    message = link.recv_match(blocking=True, timeout=.1)
                    if message:
                        telemetry[message.get_type()] = message
                        if message.get_type() in ('HEARTBEAT', 'STATUSTEXT', 'EXTENDED_SYS_STATE'):
                            stream.write(json.dumps(message.to_dict())+'\n'); stream.flush()
                    now = time.monotonic()
                    if telemetry and now-last_hb >= .5:
                        with wire_lock:
                            link.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,
                                mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, mavutil.mavlink.MAV_STATE_ACTIVE)
                        last_hb = now
                    if telemetry and now-last_manual >= .1:
                        with wire_lock:
                            link.mav.manual_control_send(1, 0, 0, 500, 0, 0)
                        last_manual = now
        except BaseException as exc:
            worker_error.append(repr(exc))
    worker = threading.Thread(target=receiver, daemon=True)
    worker.start()
    def cli(module, *args, check=True):
        argv = [str(binary_dir/('px4-'+module)), *map(str, args)]
        command = subprocess.run(argv, cwd=rootfs, capture_output=True, text=True, timeout=10)
        commands.write(json.dumps(dict(argv=argv, returncode=command.returncode,
            stdout=command.stdout, stderr=command.stderr))+'\n'); commands.flush()
        require(not check or command.returncode == 0, 'CLI failed '+module+' '+str(args))
        return command.stdout
    def topic(name):
        data = parse_topic(cli('listener', name, '-n', '1'))
        require(data.get('timestamp', 0) > 0, 'Missing topic '+name)
        return data
    def sample(phase):
        require(not worker_error and proc.poll() is None, 'Simulator/telemetry stopped')
        state = dict(phase=phase, position=topic('vehicle_local_position'), status=topic('vehicle_status'),
                     land=topic('vehicle_land_detected'), attitude=topic('vehicle_attitude'))
        samples.write(json.dumps(state)+'\n'); samples.flush()
        p = state['position']
        require(math.isfinite(p['timestamp']) and p.get('timestamp_sample', p['timestamp']) <= p['timestamp'], 'Invalid position clocks')
        if origin is not None:
            require(not state['status'].get('failsafe'), 'Flight failsafe')
            require(not state['status'].get('failure_detector_status', 0), 'Failure detector active')
            check_envelope(p, state['attitude'], origin, phase)
        return state
    def event(name, state):
        result['events'].append(dict(name=name, timestamp_us=int(state['position']['timestamp']),
            status_timestamp_us=int(state['status']['timestamp']), land_timestamp_us=int(state['land']['timestamp'])))
        save(output/'result.json', result)
        print(job_id, name, flush=True)
    def verify_configuration(phase):
        raw = cli('param', 'show', '-a')
        (output/('parameters_'+phase+'.txt')).write_text(raw)
        check_parameters(parse_parameters(raw), job['expected_parameters'])
        diagnostics = {}
        for name, fields in job.get('diagnostic_expectations', {}).items():
            data = topic(name)
            for field, expected in fields.items():
                require(field in data and data[field] == expected, 'Wrong actual diagnostic '+name+'.'+field)
            diagnostics[name] = data
        save(output/('diagnostics_'+phase+'.json'), diagnostic_json(diagnostics))
    try:
        env = dict(os.environ)
        env.pop('DONT_RUN', None)
        env.pop('NO_PXH', None)
        env.update({k: str(v) for k, v in job['launch_env'].items()})
        proc = subprocess.Popen(job['launch_command'], cwd=repo, env=env, stdin=subprocess.PIPE,
            stdout=console, stderr=subprocess.STDOUT, start_new_session=True)
        result['launcher_pid'] = proc.pid
        save(output/'result.json', result)
        deadline = time.monotonic()+180
        while time.monotonic() < deadline:
            require(proc.poll() is None, 'Launcher exited during startup')
            if 'Startup script returned successfully' in (output/'console.log').read_text(errors='replace'):
                break
            time.sleep(.5)
        else:
            raise TimeoutError('Startup timeout')
        require(digest(binary) == job['firmware_sha256'], 'Launcher changed frozen firmware; no takeoff')
        (output/'parameters_before.txt').write_text(cli('param', 'show', '-a'))
        for name, value in job['parameters'].items():
            cli('param', 'set', name, value)
        time.sleep(1)
        verify_configuration('start')
        (output/'version.txt').write_text(cli('ver', 'all'))
        cli('logger', 'on')
        logger_text = cli('logger', 'status')
        (output/'logger_preflight.txt').write_text(logger_text)
        require('not running' not in logger_text.lower(), 'Logger not running')
        # A newly booted upstream EKF can advertise attitude before its first
        # publication. This bounded disarmed wait precedes the unchanged 30 s
        # warmup; flight observations remain strict and are never skipped.
        deadline = time.monotonic()+60
        while time.monotonic() < deadline:
            initial = {name:parse_topic(cli('listener', name, '-n', '1')) for name in
                       ('vehicle_local_position','vehicle_attitude','vehicle_status','vehicle_land_detected')}
            if native_topics_ready(initial):
                require(initial['vehicle_status'].get('arming_state') == 1, 'Unexpected armed startup')
                break
            time.sleep(.5)
        else:
            raise TimeoutError('Initial native topic publication timeout; no takeoff')
        start_time = topic('vehicle_local_position')['timestamp']
        deadline = time.monotonic()+180
        while time.monotonic() < deadline:
            state = sample('warmup')
            p = state['position']
            if (p['timestamp']-start_time >= 30e6 and p.get('xy_global') and p.get('z_valid') and telemetry):
                break
            time.sleep(.5)
        else:
            raise TimeoutError('Relative 30 s estimator warmup')
        paths = new_logs(log_roots, old_logs)
        require(paths and any(p.stat().st_size > 16 and p.open('rb').read(7) == b'ULog\x01\x12\x35' for p in paths),
                'No actual native ULog before takeoff')
        require(state['status'].get('arming_state') == 1 and state['land'].get('landed'), 'Not disarmed on ground')
        origin = {k: state['position'][k] for k in ('x', 'y', 'z', 'timestamp')}
        if 'timestamp_sample' in state['position']:
            origin['timestamp_sample'] = state['position']['timestamp_sample']
        save(output/'origin.json', origin)
        target = hold_target(state['position'])
        save(output/'hold_target.json', target)
        event('ready', state)
        cli('commander', 'takeoff')
        event('takeoff_command', state)
        stable_since = None
        hold_requested = False
        deadline = time.monotonic()+150
        while time.monotonic() < deadline:
            state = sample('takeoff')
            if state['status'].get('nav_state') == 2 and state['status'].get('arming_state') == 2 and not hold_requested:
                # One Navigator command, no offboard position/rate publisher.
                with wire_lock:
                    link.mav.command_int_send(1, 1, mavutil.mavlink.MAV_FRAME_GLOBAL,
                        mavutil.mavlink.MAV_CMD_DO_REPOSITION, 0, 0,
                        -1, 1, 0, float('nan'), target['latitude_e7'], target['longitude_e7'], target['altitude_m'])
                hold_requested = True
                event('hold_command_after_takeoff', state)
            if entry_ok(state, origin):
                stable_since = state['position']['timestamp'] if stable_since is None else stable_since
                if state['position']['timestamp']-stable_since >= 3e6:
                    break
            else:
                stable_since = None
            time.sleep(.25)
        else:
            raise TimeoutError('2.5 m stable entry not reached')
        verify_configuration('hover')
        event('hover_start', state)
        hover_start = state['position']['timestamp']
        deadline = time.monotonic()+90
        while state['position']['timestamp']-hover_start < 10e6:
            require(time.monotonic() < deadline, 'Hover simulation-clock timeout')
            time.sleep(.25)
            state = sample('hover')
            require(state['status'].get('nav_state') == 4 and state['status'].get('arming_state') == 2
                    and not state['land'].get('landed'), 'Unexpected hover mode/contact')
        event('hover_end', state)
        cli('commander', 'mode', 'auto:land')
        event('land_command', state)
        deadline = time.monotonic()+150
        while time.monotonic() < deadline:
            state = sample('landing')
            if state['land'].get('landed') and state['status'].get('arming_state') == 1:
                break
            time.sleep(.25)
        else:
            raise TimeoutError('Landing/automatic disarm timeout')
        event('landed_disarmed', state)
        verify_configuration('end')
        time.sleep(2)
        (output/'logger_end.txt').write_text(cli('logger', 'status'))
        result['task_completed'] = True
    except BaseException as exc:
        result['error'] = repr(exc)
        print(job_id, 'FAILED', repr(exc), flush=True)
    finally:
        if proc is not None:
            try:
                if proc.poll() is None:
                    try:
                        cli('shutdown', check=False)
                    except (OSError, subprocess.TimeoutExpired):
                        pass
                    try:
                        proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        pass
                # Own new-session process group only; no pkill/global process kills.
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=10)
                result['launcher_returncode'] = proc.returncode
            except BaseException as exc:
                result['cleanup_error'] = repr(exc)
        stop.set(); worker.join(timeout=2); link.close()
        console.close(); samples.close(); commands.close()
        try:
            for index, path in enumerate(new_logs(log_roots, old_logs)):
                target = output / ('native_%02d.ulg' % index)
                shutil.copy2(path, target)
                result['logs'].append(dict(source=str(path), archive=str(target), sha256=digest(target), bytes=target.stat().st_size))
        except BaseException as exc:
            result['archive_error'] = repr(exc)
        try:
            result.update(restore_parameters(rootfs, snapshot))
        except BaseException as exc:
            result['restore_error'] = repr(exc)
        deadline = time.monotonic()+3
        while active_simulators() and time.monotonic() < deadline:
            time.sleep(.1)
        result['remaining_simulators'] = active_simulators()
        result['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        save(output/'result.json', result)
    if result.get('task_completed') and not any(result.get(k) for k in ('error', 'cleanup_error', 'archive_error', 'restore_error')):
        try:
            require(result['logs'] and result['parameter_restore_exact'] and not result['remaining_simulators'], 'Incomplete archive/cleanup')
            selected = max(result['logs'], key=lambda row: row['bytes'])
            metrics = audit_native_log(selected['archive'], result['events'], origin,
                job.get('hover_diagnostic_expectations', job.get('diagnostic_expectations')))
            save(output/'metrics.json', metrics)
            result['success'] = metrics['accepted']
        except BaseException as exc:
            result['analysis_error'] = repr(exc)
    save(output/'result.json', result)
    require(result['success'], 'Attempt failed; preserve data and stop batch: '+str(output))
    print('PASS', output, flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--job', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    job = validate_manifest(manifest, args.job)
    print(json.dumps(dict(job=job, hover_s=10, takeoff_alt_m=2.5, execute=args.execute), ensure_ascii=False, indent=2))
    if args.execute:
        import fcntl
        root = Path(manifest['data_root'])
        root.mkdir(parents=True, exist_ok=True)
        with (root/'.runner.lock').open('a') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            execute(args.manifest.resolve(), manifest, job)
    else:
        print('DRY RUN: no launch, no parameter writes')


if __name__ == '__main__':
    main()
