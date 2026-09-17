#!/usr/bin/env python3
"""Build isolated research plugins, leaving the Gazebo submodule untouched.

The original Apache-2.0 IMU implementation is mechanically copied with two
auditable additions: explicit engine seed and measured noise-realization log.
No equation, filter, update rate, or standard-library RNG is replaced.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

REPO = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(out):
    out.mkdir(parents=True, exist_ok=False)
    upstream = REPO/'Tools/sitl_gazebo'
    generated = REPO/'build/px4_sitl_default/build_gazebo'
    source = (upstream/'src/gazebo_imu_plugin.cpp').read_text()
    anchor = '  // Store the pointer to the model'
    assert source.count(anchor) == 1
    source = source.replace('#include <chrono>', '#include <chrono>\n#include <fstream>\n#include <iomanip>\n#include <cstdlib>\n#include <stdexcept>')
    source = source.replace(anchor, '''  const char *seed = std::getenv("M10_IMU_SEED");
  if (!seed) throw std::runtime_error("M10 IMU seed missing");
  random_generator_.seed(std::stoul(seed));
  std::cerr << "M10_IMU_SEED_ACCEPTED=" << seed << std::endl;
''' + anchor)
    anchor = '  addNoise(&linear_acceleration_I, &angular_velocity_I, dt);'
    assert source.count(anchor) == 1
    source = source.replace(anchor, '''  const auto original_g = angular_velocity_I;
  const auto original_a = linear_acceleration_I;
''' + anchor + '''
  static std::ofstream innovations(std::getenv("M10_IMU_LOG"));
  if (!innovations) throw std::runtime_error("Cannot record IMU innovations");
  if (seq_ == 0) innovations << "seq,sim_s,dt,gx,gy,gz,ax,ay,az\\n";
  innovations << std::setprecision(17) << seq_ << ',' << current_time.Double() << ',' << dt;
  for (int i=0;i<3;++i) innovations << ',' << angular_velocity_I[i]-original_g[i];
  for (int i=0;i<3;++i) innovations << ',' << linear_acceleration_I[i]-original_a[i];
  innovations << '\\n';
  innovations.flush();
''')
    copied = out/'seeded_imu.cpp'
    copied.write_text(source)
    flags = shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','gazebo'],text=True))
    common = ['g++','-std=c++17','-O2','-shared','-fPIC','-Wno-deprecated-declarations',
              '-I'+str(upstream/'include'),'-I'+str(generated),'-I/usr/include/eigen3',
              '-I/usr/include/gazebo-11/gazebo/msgs']
    commands = []
    for name, src in [('imu',copied),('torque',REPO/'research/sta-rate-control/m10/TorquePlugin.cpp')]:
        library = out/f'libm10_{name}.so'
        cmd = common+[str(src),'-o',str(library)]+flags
        if name == 'imu':
            cmd += ['-L'+str(generated),'-lsensor_msgs','-Wl,-rpath,'+str(generated)]
        with (out/f'build_{name}.log').open('w') as stream:
            r = subprocess.run(cmd,stdout=stream,stderr=subprocess.STDOUT)
        commands.append(dict(command=cmd,returncode=r.returncode))
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        if r.returncode: raise RuntimeError(f'{name} plugin build failed; see {out}')
    files = [upstream/'src/gazebo_imu_plugin.cpp',upstream/'include/gazebo_imu_plugin.h',copied,
             REPO/'research/sta-rate-control/m10/TorquePlugin.cpp',out/'libm10_imu.so',out/'libm10_torque.so']
    (out/'manifest.json').write_text(json.dumps({str(p):sha(p) for p in files},indent=2)+'\n')
    print('Built isolated M10 plugins:',out)


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    build(p.parse_args().output.resolve())
