#!/usr/bin/env python3
"""Iris pitch quasi-static calibration; FRD y is minus FLU y."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import numpy as np
from calibrate_m04 import calculate as roll_calibration, ROOT


def calculate():
    roll = roll_calibration()
    model = ET.parse(ROOT/'Tools/sitl_gazebo/models/iris/iris.sdf').getroot().find('model')
    generated = ROOT/'build/px4_sitl_default/src/lib/mixer/MultirotorMixer/mixer_multirotor_normalized.generated.h'
    section = generated.read_text().split('_config_quad_wide[] {')[1].split('};')[0]
    mixer = np.array([[float(x) for x in row.split(',')] for row in re.findall(r'\{([^}]+)\}', section)])
    motors = sorted([p for p in model.findall('plugin') if p.find('motorNumber') is not None],
                    key=lambda p: int(p.findtext('motorNumber')))
    positions = np.array([[float(x) for x in model.find("link[@name='%s']" % p.findtext('linkName')).findtext('pose').split()[:3]] for p in motors])
    relative = positions - np.array(roll['com_m'])
    k = np.array([float(p.findtext('motorConstant')) for p in motors])
    channels = model.find("plugin[@name='mavlink_interface']/control_channels").findall('channel')[:4]
    scale = np.array([float(c.findtext('input_scaling')) for c in channels])
    idle = np.array([float(c.findtext('zero_position_armed')) for c in channels])
    transform = np.diag([1., -1., -1.])
    inertia = transform @ np.array(roll['inertia_kg_m2']) @ transform

    def acceleration(r, p, throttle):
        q = mixer @ np.array([r, p, 0., throttle])
        assert np.all((q > 0) & (q < 1))
        omega = idle + scale*q
        assert np.all(omega < np.array([float(m.findtext('maxRotVelocity')) for m in motors]))
        force = k*omega**2
        # FLU moment (y*F, -x*F, reaction); FRD pitch is +x*F.
        moment = np.array([np.sum(relative[:, 1]*force), np.sum(relative[:, 0]*force), 0.])
        return np.linalg.solve(inertia, moment), moment

    origin, _ = acceleration(0, .004, .707)
    gp = (acceleration(0, .0041, .707)[0][1]-acceleration(0, .0039, .707)[0][1])/.0002
    jacobian = np.column_stack([(acceleration(.0001, .004, .707)[0]-acceleration(-.0001, .004, .707)[0])/.0002,
                               (acceleration(0, .0041, .707)[0]-acceleration(0, .0039, .707)[0])/.0002])
    samples = []
    for t in (.65, .707, .75):
        for c in (-.01, -.005, -.001, .001, .005, .01):
            delta = acceleration(0, .004+c, t)[0]-acceleration(0, .004, t)[0]
            samples.append(dict(throttle=t, delta_c_pitch=c, delta_alpha=delta.tolist(), gain=float(delta[1]/c)))
    return dict(method='model-only quasi-static, full inertia solve; no motor reaction in R/P derivative',
                mass_kg=roll['mass_kg'], com_flu_m=roll['com_m'], inertia_frd_kg_m2=inertia.tolist(),
                g_P=float(gp), g_R_retained=roll['g_R'], pitch_mixer=mixer[:, 1].tolist(),
                pitch_lever_frd_m=relative[:, 0].tolist(), rp_acceleration_jacobian=jacobian.tolist(),
                working_point=dict(throttle=.707, roll=0, pitch=.004, yaw=0), samples=samples,
                local_gain_variation=max(abs(x['gain']/gp-1) for x in samples),
                unit='rad/s^2 per normalized pitch command',
                uncertainty=roll['dynamic_uncertainty'], files=roll['files'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.output.open('x') as stream:
        json.dump(calculate(), stream, indent=2)
        stream.write('\n')
