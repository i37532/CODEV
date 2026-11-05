"""Reproducible read-only diagnostic figure; no control/runtime writes."""
import argparse
import json
from pathlib import Path
import numpy as np
from pyulog import ULog
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root=Path('/home/yr/Desktop/codev doc/experiments/ISTA-OPT01-20260918/search01/screen')
parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
labels=['0002_C01_m2_inertia_s4101','0004_C02_m2_inertia_s4101','0006_C03_m2_inertia_s4101']
fig,ax=plt.subplots(4,3,figsize=(12,10),sharex=True,layout='constrained')
for col,label in enumerate(labels):
    result=json.loads((root/label/'result.json').read_text());u=ULog(result['logs'][-1]['archive'])
    d=u.get_dataset('sta_rate_ctrl_status').data;t=d['timestamp_sample']*1e-6
    armed=d['armed'].astype(bool);origin=t[armed][0];mask=armed&(t-origin<=10);x=t-origin
    z=u.get_dataset('vehicle_local_position_groundtruth').data;zt=z['timestamp']*1e-6
    z0=np.median(z['z'][(zt<origin)&(zt>origin-1)]);height=np.interp(t,zt,z0-z['z'])
    release=np.flatnonzero(armed&~d['landed'].astype(bool)&~d['maybe_landed'].astype(bool))[0]
    lift=np.flatnonzero(armed&(height>.02))[0]
    attitude=u.get_dataset('vehicle_attitude').data
    tilt=np.degrees(np.arccos(np.clip(1-2*(attitude['q[1]'].astype(float)**2+attitude['q[2]'].astype(float)**2),-1,1)))
    ax[0,col].plot(x[mask],height[mask]);ax[0,col].set_title(['Base lambda2','lambda2 x4','lambda2 x16'][col])
    ax[1,col].plot(x[mask],d['nu[1]'][mask],label='applied nu pitch');ax[1,col].axhline(0,color='gray',lw=.7)
    ax[2,col].plot(x[mask],d['rate_sp[1]'][mask],label='rate setpoint',lw=1)
    ax[2,col].plot(x[mask],d['rate[1]'][mask],label='measured rate',lw=1)
    at=attitude['timestamp']*1e-6-origin
    valid=(at>=0)&(at<=x[np.flatnonzero(armed)[-1]])
    ax[3,col].plot(at[valid],tilt[valid])
    ax[3,col].axhline(15,color='red',ls=':',label='abort threshold')
    for row in range(4):
        ax[row,col].axvspan(x[release],x[lift],alpha=.12,color='orange')
        ax[row,col].axvline(x[release],color='#9a6500',ls='--',lw=.8)
        ax[row,col].axvline(x[lift],color='#228855',ls='--',lw=.8)
        ax[row,col].set_xlim(0,10);ax[row,col].grid(alpha=.2)
    ax[3,col].set_xlabel('Seconds after arm')
for row,label in enumerate(['True height change (m)','nu pitch (rad/s2)','Pitch rate (rad/s)','Tilt (deg)']):ax[row,0].set_ylabel(label)
ax[2,0].legend(fontsize=8);ax[3,0].legend(fontsize=8)
fig.suptitle('Historical paired seed 4101: state freeze released before physical liftoff\nOrange: released flags to +2 cm true height (offline diagnostic event)',fontsize=13)
fig.savefig(out/'takeoff_diagnosis.png',dpi=160);fig.savefig(out/'takeoff_diagnosis.svg');plt.close(fig)
svg=out/'takeoff_diagnosis.svg'
svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
