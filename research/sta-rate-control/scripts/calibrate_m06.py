#!/usr/bin/env python3
"""Iris yaw reaction torque calibration, including full FRD inertia coupling."""
import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from calibrate_m04 import ROOT
from calibrate_m05 import calculate as pitch_calibration


def calculate():
    rp = pitch_calibration()
    model = ET.parse(ROOT/'Tools/sitl_gazebo/models/iris/iris.sdf').getroot().find('model')
    path = ROOT/'build/px4_sitl_default/src/lib/mixer/MultirotorMixer/mixer_multirotor_normalized.generated.h'
    section = path.read_text().split('_config_quad_wide[] {')[1].split('};')[0]
    mixer = np.array([[float(x) for x in row.split(',')] for row in re.findall(r'\{([^}]+)\}', section)])
    motors = sorted([p for p in model.findall('plugin') if p.find('motorNumber') is not None], key=lambda p: int(p.findtext('motorNumber')))
    positions = np.array([[float(x) for x in model.find("link[@name='%s']" % p.findtext('linkName')).findtext('pose').split()[:3]] for p in motors])
    relative = positions - np.array(rp['com_flu_m'])
    channels = model.find("plugin[@name='mavlink_interface']/control_channels").findall('channel')[:4]
    scale = np.array([float(c.findtext('input_scaling')) for c in channels])
    idle = np.array([float(c.findtext('zero_position_armed')) for c in channels])
    k = np.array([float(p.findtext('motorConstant')) for p in motors])
    km = np.array([float(p.findtext('momentConstant')) for p in motors])
    # Plugin: CCW=+1, CW=-1; drag FLU z=-direction*force*momentConstant.
    directions = np.array([{'ccw': 1., 'cw': -1.}[p.findtext('turningDirection')] for p in motors])
    inertia = np.array(rp['inertia_frd_kg_m2'])

    def acceleration(r, p, y, throttle):
        q = mixer @ np.array([r, p, y, throttle])
        assert np.all((q > 0) & (q < 1))
        omega = idle + scale*q
        assert np.all(omega < np.array([float(m.findtext('maxRotVelocity')) for m in motors]))
        force = k*omega**2
        torque = [np.sum(relative[:, 1]*force), np.sum(relative[:, 0]*force), np.sum(directions*force*km)]
        return np.linalg.solve(inertia, torque)

    point = np.array([0., .004, 0., .707])
    jacobian = np.column_stack([(acceleration(*(point + np.eye(4)[i]*.0001))-acceleration(*(point - np.eye(4)[i]*.0001)))/.0002 for i in range(3)])
    gy = float(jacobian[2, 2])
    samples = []
    for throttle in (.65, .707, .75):
        for c in (-.01, -.005, -.001, .001, .005, .01):
            delta = acceleration(0, .004, c, throttle)-acceleration(0, .004, 0, throttle)
            samples.append(dict(throttle=throttle, delta_c_yaw=c, delta_alpha=delta.tolist(), gain=float(delta[2]/c)))
    files = dict(rp['files'])
    for name in ['Tools/sitl_gazebo/include/gazebo_motor_model.h', 'Tools/sitl_gazebo/src/gazebo_motor_model.cpp']:
        files[name] = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    return dict(method='model-only quasi-static reaction torque, complete FRD inertia solve', g_Y=gy,
                g_R_retained=rp['g_R_retained'], g_P_retained=rp['g_P'],
                inertia_frd_kg_m2=inertia.tolist(), yaw_mixer=mixer[:, 2].tolist(),
                turning_directions=directions.tolist(), moment_constants_m=km.tolist(),
                acceleration_jacobian=jacobian.tolist(), working_point=dict(zip(['roll','pitch','yaw','throttle'],point)),
                samples=samples, local_gain_variation=max(abs(x['gain']/gy-1) for x in samples),
                unit='rad/s^2 per normalized yaw command', uncertainty=rp['uncertainty'], files=files)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    with parser.parse_args().output.open('x') as stream:
        json.dump(calculate(), stream, indent=2); stream.write('\n')
