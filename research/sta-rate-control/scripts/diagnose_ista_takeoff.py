#!/usr/bin/env python3
"""Read-only post-hoc ground-truth/state audit, including aborted flights.

Ground truth is used ONLY offline, never as a controller input. Two centimetres
is a diagnostic event, not an online flight detector or a safety guarantee.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from pyulog import ULog
from analyze_m03 import vector
from m08_ista_reference import ideal
from ista_opt01 import digest, immutable


def diagnose(run):
    result=json.loads((run/'result.json').read_text())
    candidates=[]
    for item in result['logs']:
        if digest(item['archive'])!=item['sha256']:raise ValueError('ULog fingerprint changed')
        log=ULog(item['archive']);d=log.get_dataset('sta_rate_ctrl_status').data
        candidates.append((int(np.count_nonzero(d['armed'])),log,d,item))
    _,log,d,item=max(candidates,key=lambda v:v[0])
    t=d['timestamp_sample'].astype(np.int64)*1e-6;armed=d['armed'].astype(bool)
    ai=np.flatnonzero(armed)
    if len(ai)==0:raise ValueError('No armed diagnostics')
    origin=t[ai[0]];gt=log.get_dataset('vehicle_local_position_groundtruth').data
    gt_t=gt['timestamp'].astype(np.int64)*1e-6
    before=(gt_t<origin)&(gt_t>origin-1)
    if not np.any(before):raise ValueError('No pre-arm height reference')
    z0=float(np.median(gt['z'][before]));height=np.interp(t,gt_t,z0-gt['z'])
    vz=np.interp(t,gt_t,gt['vz'])
    released=armed&~d['landed'].astype(bool)&~d['maybe_landed'].astype(bool)
    release=np.flatnonzero(released)[0];lift=np.flatnonzero(armed&(height>.02))[0]
    at=log.get_dataset('vehicle_attitude').data
    q=np.column_stack([at[f'q[{i}]'] for i in range(4)])
    tilt_at=np.degrees(np.arccos(np.clip(1-2*(q[:,1].astype(float)**2+q[:,2].astype(float)**2),-1,1)))
    tilt=np.interp(t,at['timestamp']*1e-6,tilt_at)
    fields={k:vector(d,k) for k in ('rate','rate_sp','s','nu','nu_before','nu_candidate','lambda1','lambda2','g','a_raw','a_protected','c_applied','limits','xi')}
    def snapshot(i):
        return dict(time_after_arm_s=float(t[i]-origin),height_m=float(height[i]),vz=float(vz[i]),
                    tilt_deg=float(tilt[i]),thrust=float(d['thrust'][i]),
                    **{k:fields[k][i].astype(float).tolist() for k in ('rate','rate_sp','s','nu','a_raw','a_protected','c_applied','limits')})
    ground=released&(np.arange(len(t))<lift)&(abs(height)<.002)&(abs(vz)<.02)
    idx=np.flatnonzero(armed&d['updated'].astype(bool)&(d['effective_mode']==2))
    h=d['dt'][idx,None].astype(float)
    reference=ideal(fields['s'][idx],fields['nu_before'][idx],h,fields['lambda1'][idx],fields['lambda2'][idx],fields['g'][idx])
    errors={k:float(np.max(abs(fields[field][idx]-reference[k]))) for k,field in (('a','a_raw'),('nu','nu_candidate'),('xi','xi'))}
    if errors['a']>2e-5 or errors['nu']>2e-6 or errors['xi']>2e-5:raise ValueError('Independent ideal equation audit failed')
    frozen=armed&(d['landed'].astype(bool)|d['maybe_landed'].astype(bool))
    if not np.array_equal(fields['nu'][frozen],fields['nu_before'][frozen]):raise ValueError('Frozen state moved')
    opposing=(fields['s'][:,1]*fields['nu'][:,1]>0)&armed&(t>=t[lift])
    job=json.loads((run/'m10_job.json').read_text())
    out=dict(run=str(run),candidate=job.get('candidate'),scene=job['scene'],seed=job['seed'],
        flight_success=result['success'],failure=result.get('error'),ulog=item,
        source_head=result['source_head'],binary_sha256=result['binary_sha256'],
        release=snapshot(release),height_20mm=snapshot(lift),last_armed=snapshot(ai[-1]),
        release_to_20mm_s=float(t[lift]-t[release]),
        released_but_stationary_ground_samples=int(ground.sum()),
        ground_nu_peak=np.max(abs(fields['nu'][ground]),axis=0).tolist(),
        ground_rate_peak=np.max(abs(fields['rate'][ground]),axis=0).tolist(),
        ground_limit_counts=np.count_nonzero(fields['limits'][ground],axis=0).tolist(),
        fault_samples=int(np.count_nonzero(d['fault'][armed])),
        diagnostic_missing=int(np.maximum(np.diff(d['publish_seq'].astype(np.int64))-1,0).sum()),
        independent_equation_errors=errors,frozen_state_equal=True,
        post_lift_pitch_nu_opposes_correction_samples=int(opposing.sum()),
        max_tilt_deg=float(tilt[armed].max()),ground_truth_scope='Offline interpolation; 20mm event is not exact contact loss')
    # A fixed early window helps compare identical launch phases without choosing peaks.
    out['at_4s_after_arm']=snapshot(ai[np.argmin(abs(t[ai]-origin-4))])
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--runs',nargs='+',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();data=[diagnose(r.resolve()) for r in a.runs];immutable(a.output,data)
    print(json.dumps([dict(candidate=r['candidate'],scene=r['scene'],release_to_20mm_s=r['release_to_20mm_s'],
        pitch_nu_4s=r['at_4s_after_arm']['nu'][1],fault_samples=r['fault_samples'],max_tilt_deg=r['max_tilt_deg']) for r in data],indent=2))
