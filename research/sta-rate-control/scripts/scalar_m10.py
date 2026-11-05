#!/usr/bin/env python3
"""Independent simplified rate object sanity check, NOT Gazebo/PX4 proof.

Binary64 controllers here supplement the compiled M09 regression; this program
does not claim to execute production protection/PID filter implementations.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from m10_design import candidate,equal_gains,SCENES,scenario
from m08_ista_reference import ideal


def run(params,scene,seed):
    h=.004;setting=scenario(scene,seed);div=setting['div'];mode=params['MC_RTC_MODE']
    g=np.array([params['MC_STA_G_'+a] for a in 'RPY'])
    l1=np.array([params['MC_STA_L1_'+a] for a in 'RPY']);l2=np.array([params['MC_STA_L2_'+a] for a in 'RPY'])
    p=np.array([params['MC_'+a+'RATE_P'] for a in ('ROLL','PITCH','YAW')])
    ki=np.array([params['MC_'+a+'RATE_I'] for a in ('ROLL','PITCH','YAW')])
    kd=np.array([params['MC_'+a+'RATE_D'] for a in ('ROLL','PITCH','YAW')])
    rate=np.zeros(3);nu=np.zeros(3);integ=np.zeros(3);motor=np.zeros(3);command=np.zeros(3);derivative=np.zeros(3);previous=np.zeros(3)
    rng=np.random.Generator(np.random.PCG64(seed));errors=[];peaks=[];clamps=0
    for k in range(10000):
        t=k*h
        sp=np.array([.04,.08,.12])*np.sin(2*np.pi*t/4)
        measured=rate+rng.normal(0,.003*setting['gyro_density_scale'],3)
        derivative=.5*derivative+.5*(measured-previous)/h;previous=measured.copy()
        s=measured-sp
        if k%div==0:
            dt=h*div
            if mode==0:
                command=-p*s+integ-kd*derivative
                integ=np.clip(integ-ki*s*dt,-.3,.3)
            elif mode==1:
                command=(-l1*np.sqrt(abs(s))*np.sign(s)+nu)/g
                nu=np.clip(nu-dt*l2*np.sign(s),-3,3)
            else:
                r=ideal(s,nu,dt,l1,l2,g);command=r['a']/g;nu=np.clip(r['nu'],-3,3)
            clamps+=int(np.any(abs(command)>.15));command=np.clip(command,-.15,.15)
        motor=command+(motor-command)*np.exp(-h/.025)
        torque=np.zeros(3)
        if scene=='torque' and 2<=t<=12:
            torque=np.array([.004,.004,.002])*np.sin(np.pi*(t-2)/10)**2*np.sin(2*np.pi*.4*(t-2)+np.array(setting['torque_phases']))
        # Gazebo FLU torque -> controller FRD axes (x forward, y right, z down).
        torque_frd=torque*np.array([1.,-1.,-1.])
        acceleration=g*motor/setting['inertia_scale']+torque_frd/np.array([.029125,.029125,.055225])/setting['inertia_scale']
        rate+=acceleration*h
        if not np.all(np.isfinite(rate)):raise RuntimeError('Nonfinite scalar object')
        errors.append(s);peaks.append(rate.copy())
    maximum=float(np.max(np.abs(peaks)))
    if maximum>1:raise RuntimeError('Scalar rate > 1 rad/s')
    return dict(scene=scene,mode=mode,seed=seed,rmse=np.sqrt(np.mean(np.array(errors)**2,axis=0)).tolist(),
                max_rate=maximum,clamped_updates=clamps,pass_sanity=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise RuntimeError('Refuse overwrite')
    rows=[run(candidate(m,i),scene,1101) for m in (0,1,2) for i in range(3) for scene in SCENES]
    rows += [run(equal_gains(2),scene,1101) for scene in SCENES]
    a.output.write_text(json.dumps(dict(scope='simplified independent binary64 object, not compiled flight controller',runs=rows),indent=2)+'\n')
    print(len(rows),'scalar sanity checks passed')
