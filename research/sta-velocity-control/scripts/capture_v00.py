#!/usr/bin/env python3
"""Read-only source/environment/parameter archive; no PX4 launch or writes."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess

REPO = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def persisted_bson(data):
    """PX4 scalar BSON. Reject unknown types rather than guess defaults."""
    if len(data) < 5:
        raise ValueError('Invalid BSON length/terminator')
    length = struct.unpack_from('<i', data)[0]
    if length < 5 or length > len(data) or data[length - 1] != 0:
        raise ValueError('Invalid BSON length/terminator')
    # PX4's file decoder stops at EOO. The backing file may retain trailing
    # bytes from older saves. Archive all bytes; decode only this document.
    data = data[:length]
    values, offset = {}, 4
    formats = {1: '<d', 16: '<i', 18: '<q', 8: '<?'}
    while offset < len(data) - 1:
        kind = data[offset]
        end = data.index(0, offset + 1)
        name = data[offset + 1:end].decode('utf-8')
        if kind not in formats or name in values:
            raise ValueError('Unsupported or duplicate BSON field: ' + name)
        fmt = formats[kind]
        values[name] = struct.unpack_from(fmt, data, end + 1)[0]
        offset = end + 1 + struct.calcsize(fmt)
    if offset != len(data) - 1:
        raise ValueError('Invalid BSON payload')
    return values


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    out = p.parse_args().output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    result = {'assets': {}, 'commands': {}, 'runtime_verified': False,
              'note': 'Offline audit only. Persisted overrides are NOT complete runtime parameters.'}
    commands = {
        'head': ['git', 'rev-parse', 'HEAD'],
        'branch': ['git', 'branch', '--show-current'],
        'status': ['git', 'status', '--short', '--branch'],
        'submodules': ['git', 'submodule', 'status', '--recursive'],
        'submodule_worktrees': ['git', 'submodule', 'foreach', '--recursive', '--quiet', 'git status --porcelain'],
        'takeoff_history': ['git', 'show', '317ee4c9cca25c33bc4ef81fc48056fb1d82800d', '--',
                            'src/modules/mc_pos_control/Takeoff/Takeoff.cpp'],
        'takeoff_blame': ['git', 'blame', '-L', '43,47', 'src/modules/mc_pos_control/Takeoff/Takeoff.cpp'],
        'ninja': ['ninja', '--version'],
    }
    for name, cmd in commands.items():
        r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
        result['commands'][name] = dict(command=cmd, exit_code=r.returncode, stdout=r.stdout, stderr=r.stderr)
        if r.returncode:
            raise RuntimeError(name)
    paths = ['src/modules/ekf2/EKF2Selector.cpp', 'src/modules/logger/logged_topics.cpp',
             'src/modules/mc_rate_control/MulticopterRateControl.cpp',
             'src/modules/mc_rate_control/mc_rate_control_params.c',
             'src/modules/mc_rate_control/RateControl/RateControl.cpp',
             'src/modules/mc_att_control/mc_att_control_main.cpp',
             'ROMFS/px4fmu_common/init.d/airframes/4065_codev_dp_1000',
             'ROMFS/px4fmu_common/init.d/rc.mc_defaults',
             'ROMFS/px4fmu_common/init.d-posix/rcS',
             'Tools/setup_gazebo.bash', 'Tools/sitl_gazebo/models/iris/iris.sdf.jinja',
             'Tools/sitl_gazebo/models/iris/iris.sdf', 'Tools/sitl_gazebo/models/gps/gps.sdf',
             'sitl/worlds/empty_grey.world', 'build/px4_sitl_default/CMakeCache.txt',
             'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016']
    for sensor in ('imu', 'gps', 'magnetometer', 'barometer'):
        paths += [f'Tools/sitl_gazebo/src/gazebo_{sensor}_plugin.cpp',
                  f'Tools/sitl_gazebo/include/gazebo_{sensor}_plugin.h']
    for rel in paths:
        src = REPO / rel
        dest = out / 'snapshot' / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        result['assets'][rel] = dict(sha256=sha(src), bytes=src.stat().st_size, copied=True)
    binaries = [REPO / 'build/px4_sitl_default/bin/px4']
    binaries += sorted((REPO / 'build/px4_sitl_default/build_gazebo').glob('libgazebo*.so'))
    result['gazebo_plugin_count'] = len(binaries) - 1
    for src in binaries:
        result['assets'][str(src.relative_to(REPO))] = dict(sha256=sha(src), bytes=src.stat().st_size, copied=False)
    saved = REPO / 'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
    result['persisted_overrides_not_runtime'] = persisted_bson(saved.read_bytes())
    result['persisted_bson_document_bytes'] = struct.unpack_from('<i', saved.read_bytes())[0]
    result['persisted_bson_trailing_bytes'] = saved.stat().st_size - result['persisted_bson_document_bytes']
    shutil.copyfile(__file__, out / 'capture_v00.py')
    (out / 'manifest.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'assets': len(result['assets']), 'gazebo_plugins': result['gazebo_plugin_count'],
                      'runtime_verified': False}))


if __name__ == '__main__':
    main()
