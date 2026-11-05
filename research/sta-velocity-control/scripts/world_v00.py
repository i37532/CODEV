"""Read-only Linux process evidence; never infer the world from console text."""
import hashlib
import os
from pathlib import Path

ENV_KEYS = ('PX4_SITL_WORLD', 'GAZEBO_MASTER_URI')


def process_record(pid):
    root = Path('/proc') / str(pid)
    env = dict(item.split('=', 1) for item in
               root.joinpath('environ').read_bytes().decode().split('\0') if '=' in item)
    return dict(pid=pid, sid=os.getsid(pid),
                comm=root.joinpath('comm').read_text().strip(),
                argv=[v for v in root.joinpath('cmdline').read_bytes().decode().split('\0') if v],
                environment={k: env[k] for k in ENV_KEYS if k in env})


def server_records():
    records = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.joinpath('comm').read_text().strip().startswith('gzserver'):
                records.append(process_record(int(entry.name)))
        except (FileNotFoundError, ProcessLookupError):
            continue  # Process exited during snapshot; missing server fails validation.
    return records


def validate_world(records, launcher_pid, launcher_sid, world, master_uri):
    if launcher_pid <= 0 or launcher_sid != launcher_pid:
        raise RuntimeError('Launcher is not its own session leader')
    if len(records) != 1:
        raise RuntimeError('Expected exactly one Gazebo server; found ' + str(len(records)))
    record = records[0]
    if record['sid'] != launcher_sid or not record['comm'].startswith('gzserver'):
        raise RuntimeError('Gazebo server does not belong to this launch session')
    worlds = [a for a in record['argv'][1:] if a.endswith('.world')]
    if worlds != [str(world)] or not Path(world).is_absolute():
        raise RuntimeError('Actual Gazebo world argv mismatch: ' + repr(worlds))
    if record['environment'].get('PX4_SITL_WORLD') != str(world):
        raise RuntimeError('World environment mismatch')
    if record['environment'].get('GAZEBO_MASTER_URI') != master_uri:
        raise RuntimeError('Gazebo master mismatch')
    return record


def snapshot(launcher_pid, world):
    return dict(launcher_pid=launcher_pid, launcher_sid=os.getsid(launcher_pid),
                servers=server_records(), world=str(world),
                world_sha256=hashlib.sha256(world.read_bytes()).hexdigest())
