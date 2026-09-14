#!/usr/bin/env python3
"""Iris-specific quasi-static roll gain from the actual SDF + generated mixer.

Not a dynamic flight identification or a hardware calibration. Outputs JSON.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import numpy as np

ROOT = Path(__file__).resolve().parents[3]


def calculate():
    sdf = ROOT/'Tools/sitl_gazebo/models/iris/iris.sdf'
    gps = ROOT/'Tools/sitl_gazebo/models/gps/gps.sdf'
    generated = ROOT/'build/px4_sitl_default/src/lib/mixer/MultirotorMixer/mixer_multirotor_normalized.generated.h'
    model = ET.parse(sdf).getroot().find('model')
    links = []
    for link in model.findall('link') + ET.parse(gps).getroot().findall('model/link'):
        origin = np.array([float(x) for x in link.findtext('pose', '0 0 0 0 0 0').split()[:3]])
        if link.attrib['name'] == 'link':
            origin += np.array([.1, 0, 0])
        inertia = link.find('inertial')
        origin += np.array([float(x) for x in inertia.findtext('pose', '0 0 0 0 0 0').split()[:3]])
        mass = float(inertia.findtext('mass'))
        tensor = np.array([[float(inertia.findtext('inertia/'+k)) for k in row]
                           for row in [('ixx','ixy','ixz'),('ixy','iyy','iyz'),('ixz','iyz','izz')]])
        links.append((mass, origin, tensor))
    total_mass = sum(x[0] for x in links)
    com = sum(m*r for m,r,_ in links)/total_mass
    tensor = sum(I + m*(np.dot(r-com,r-com)*np.eye(3)-np.outer(r-com,r-com)) for m,r,I in links)
    section = generated.read_text().split('_config_quad_wide[] {')[1].split('};')[0]
    mixer = np.array([[float(x) for x in row.split(',')] for row in re.findall(r'\{([^}]+)\}', section)])
    assert mixer.shape == (4,4)
    motors = sorted([p for p in model.findall('plugin') if p.find('motorNumber') is not None],
                    key=lambda p:int(p.findtext('motorNumber')))
    positions = np.array([[float(x) for x in model.find("link[@name='%s']" % p.findtext('linkName')).findtext('pose').split()[:3]] for p in motors])
    # SDF body FLU -> PX4 FRD; roll x is unchanged and lift is +z in SDF.
    lever = positions[:,1]-com[1]
    k = np.array([float(p.findtext('motorConstant')) for p in motors])
    channels = model.find("plugin[@name='mavlink_interface']/control_channels").findall('channel')[:4]
    scale = np.array([float(c.findtext('input_scaling')) for c in channels])
    armed = np.array([float(c.findtext('zero_position_armed')) for c in channels])
    assert all(float(c.findtext('input_offset')) == 0 for c in channels)
    params = json.loads((ROOT/'research/sta-rate-control/baseline/pid_initial_parameters.json').read_text())
    assert params['THR_MDL_FAC'] == 0
    def torque(c, throttle):
        q = mixer @ np.array([c,.004,0,throttle])
        assert np.all((q>0)&(q<1))
        omega = armed+scale*q
        assert np.all(omega < np.array([float(p.findtext('maxRotVelocity')) for p in motors]))
        return float(np.sum(lever*k*omega**2))
    def gain(t):
        return (torque(.0001,t)-torque(-.0001,t))/.0002/tensor[0,0]
    g = gain(.707)
    samples = [dict(throttle=t, c=c, delta_alpha=(torque(c,t)-torque(0,t))/tensor[0,0],
                    gain=(torque(c,t)-torque(0,t))/tensor[0,0]/c)
               for t in (.65,.707,.75) for c in (-.01,-.005,-.001,.001,.005,.01)]
    paths = [sdf,gps,generated,ROOT/'src/drivers/pwm_out_sim/PWMSim.hpp',
             ROOT/'src/modules/simulator/simulator_mavlink.cpp',
             ROOT/'Tools/sitl_gazebo/src/gazebo_motor_model.cpp',
             ROOT/'Tools/sitl_gazebo/src/gazebo_mavlink_interface.cpp']
    return dict(method='model-only quasi-static, Iris-specific', mass_kg=total_mass, com_m=com.tolist(),
                inertia_kg_m2=tensor.tolist(), roll_mixer=mixer[:,0].tolist(), lever_flu_m=lever.tolist(),
                g_R=g, unit='rad/s^2 per normalized roll command', working_point=dict(throttle=.707,pitch=.004,yaw=0),
                samples=samples, local_gain_variation=max(abs(x['gain']/g-1) for x in samples),
                dynamic_uncertainty='Not measured: 12.5/25 ms motor lag, filters, drag and coupling. +/-20% is an engineering sensitivity range, NOT a confidence interval.',
                files={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    with args.output.open('x') as stream:
        json.dump(calculate(),stream,indent=2)
        stream.write('\n')
