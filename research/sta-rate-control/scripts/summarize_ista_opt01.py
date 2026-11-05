#!/usr/bin/env python3
"""Archive bounded-search outcomes, without changing raw evidence or selection."""
import argparse
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path
import numpy as np
from ista_opt01 import rows, SCENES


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for b in iter(lambda:stream.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def main(root,out):
    out.mkdir(parents=True,exist_ok=False)
    allrows=[];stages=[]
    for stage in ('reference','screen','training','validation','holdout'):
        p=root/stage
        if not p.exists():continue
        r=rows(p)
        for x in r:x['stage']=stage
        allrows+=r
        stages.append(dict(stage=stage,attempted=len(r),accepted=sum(x['success'] for x in r)))
    verified=0
    for r in allrows:
        for log in r.get('logs',[]):
            if sha(Path(log['archive']))!=log['sha256']:raise ValueError('ULog hash mismatch')
            verified+=1
    cells=[]
    for cid in sorted({r['candidate'] for r in allrows}):
        for scene in SCENES:
            data=[r for r in allrows if (r['candidate'],r['scene'])==(cid,scene)]
            if not data:continue
            ok=[r for r in data if r['success']]
            cell=dict(candidate=cid,scene=scene,attempted=len(data),accepted=len(ok),
                      seeds=[r['seed'] for r in data],conditional_on_accepted=True)
            for key in ('rmse_tracking','iae_tracking_rad','rmse_steady','control_rms','control_peak',
                        'protected_fraction','native_highband_rms','common_0_20hz_rms',
                        'mixer_saturation_fraction','kernel_wall_ns_per_sim_second','module_wall_ns_per_sim_second'):
                cell[key+'_mean']=np.mean([r[key] for r in ok],axis=0).tolist() if ok else None
            if ok:
                cell['tv_per_s_mean']=np.mean([r['tv_actual_updates']['tv_per_s'] for r in ok],axis=0).tolist()
                for key in ('kernel_cost','module_cost'):
                    cell[key]={q:float(np.mean([r[key][q] for r in ok])) for q in ('median_ns','p95_ns','p99_ns')}
                cell['max_tilt_deg']=max(r['max_armed_tilt_deg'] for r in ok)
                cell['max_height_error_m']=max(r['max_hover_height_error_m'] for r in ok)
                cell['motor_original_missing']=sum(r['motor_original']['missing'] for r in ok)
            cells.append(cell)
    pairing=[];diversity=[]
    for scene in SCENES:
        streams={}
        for seed in sorted({r['seed'] for r in allrows}):
            data=[r for r in allrows if r['scene']==scene and r['seed']==seed and r['success']]
            if not data:continue
            values=[]
            for r in data:
                v=np.genfromtxt(Path(r['path']).parent/'imu_innovations.csv',names=True,delimiter=',',max_rows=5000)
                values.append(np.column_stack([v[k] for k in ('gx','gy','gz')]))
            n=min(map(len,values));values=np.array([v[:n] for v in values])
            gap=float(np.max(abs(values-values[0])))
            if n!=5000 or gap>=1e-10:raise ValueError('Noise pairing failed')
            streams[seed]=values[0]
            pairing.append(dict(scene=scene,seed=seed,runs=len(data),samples=n,max_difference=gap))
        if len(streams)==2:
            a,b=streams.values()
            diversity.append(dict(scene=scene,max_between_seed_difference=float(np.max(abs(a-b))),
                axis_correlations=[float(np.corrcoef(a[:,j],b[:,j])[0,1]) for j in range(3)]))
    summary=dict(stages=stages,attempted=len(allrows),accepted=sum(r['success'] for r in allrows),
        failure_classes=dict(Counter(r.get('failure_class') for r in allrows if not r['success'])),
        conclusion=json.loads((root/'conclusion.json').read_text()),cells=cells,seed_pairing=pairing,
        seed_diversity=diversity,verified_ulog_count=verified,
        limitations='Training-only adaptive candidate selection; no independent validation/holdout inference. Seeded gyro/torque only; other original random sources unchanged.')
    for name,data in [('summary.json',summary),('runs.json',allrows),('failures.json',[r for r in allrows if not r['success']])]:
        (out/name).write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    for name in ('provenance.json','candidates.json','proxy.json','screen_selection.json','training_scores.json','conclusion.json'):
        shutil.copy2(root/name,out/name)
    print(json.dumps({k:summary[k] for k in ('stages','attempted','accepted','failure_classes','verified_ulog_count')},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();main(a.root.resolve(),a.output.resolve())
