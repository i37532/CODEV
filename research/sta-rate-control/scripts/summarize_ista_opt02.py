#!/usr/bin/env python3
"""Complete OPT02 evidence, conditional metrics, paired RNG and ULog hashes."""
import argparse
import json
import shutil
from collections import Counter
from pathlib import Path
import numpy as np
from ista_opt01 import rows
from ista_opt02 import SCENES
from archive_m10 import sha


def main(root,out):
    out.mkdir(parents=True,exist_ok=False);runs=[];stages=[]
    for stage in ('diagnosis','reference','screen','training','validation'):
        if not (root/stage).exists():continue
        data=rows(root/stage)
        for r in data:
            r['stage']=stage
            r['partition']=stage if stage in ('diagnosis','validation') else 'training'
        runs+=data;stages.append(dict(stage=stage,attempted=len(data),accepted=sum(r['success'] for r in data)))
    verified=0
    for r in runs:
        for log in r['logs']:
            if sha(Path(log['archive']))!=log['sha256']:raise ValueError('ULog fingerprint changed')
            verified+=1
    cells=[]
    for partition,cid in sorted({(r['partition'],r['candidate']) for r in runs}):
        for scene in SCENES:
            data=[r for r in runs if (r['partition'],r['candidate'],r['scene'])==(partition,cid,scene)]
            if not data:continue
            ok=[r for r in data if r['success']]
            c=dict(partition=partition,candidate=cid,scene=scene,attempted=len(data),accepted=len(ok),seeds=[r['seed'] for r in data],
                conditional_on_accepted=True)
            for key in ('rmse_tracking','iae_tracking_rad','rmse_steady','control_rms','control_peak',
                        'protected_fraction','native_highband_rms','common_0_20hz_rms','mixer_saturation_fraction',
                        'kernel_wall_ns_per_sim_second','module_wall_ns_per_sim_second'):
                c[key+'_mean']=np.mean([r[key] for r in ok],axis=0).tolist() if ok else None
            if ok:
                c['tv_per_s_mean']=np.mean([r['tv_actual_updates']['tv_per_s'] for r in ok],axis=0).tolist()
                for key in ('kernel_cost','module_cost'):
                    c[key]={q:float(np.mean([r[key][q] for r in ok])) for q in ('median_ns','p95_ns','p99_ns')}
                c['max_tilt_deg']=max(r['max_armed_tilt_deg'] for r in ok)
                c['max_height_error_m']=max(r['max_hover_height_error_m'] for r in ok)
                c['motor_original_missing']=sum(r['motor_original']['missing'] for r in ok)
            cells.append(c)
    # Diagnostic, training and validation cells remain distinct above.
    pairing=[];diversity=[]
    for scene in SCENES:
        streams={}
        for seed in sorted({r['seed'] for r in runs}):
            data=[r for r in runs if r['scene']==scene and r['seed']==seed and r['success']]
            if not data:continue
            prefix=[]
            for r in data:
                v=np.genfromtxt(Path(r['path']).parent/'imu_innovations.csv',delimiter=',',names=True,max_rows=5000)
                prefix.append(np.column_stack([v[k] for k in ('gx','gy','gz')]))
            n=min(map(len,prefix));v=np.array([a[:n] for a in prefix]);gap=float(np.max(abs(v-v[0])))
            if n!=5000 or gap>=1e-10:raise ValueError('Noise pairing audit failed')
            pairing.append(dict(scene=scene,seed=seed,runs=len(data),samples=n,max_difference=gap))
            streams[seed]=v[0]
        keys=sorted(streams)
        for i,k in enumerate(keys):
            for other in keys[i+1:]:
                a,b=streams[k],streams[other]
                diversity.append(dict(scene=scene,seeds=[k,other],max_difference=float(np.max(abs(a-b))),
                    correlations=[float(np.corrcoef(a[:,axis],b[:,axis])[0,1]) for axis in range(3)]))
    summary=dict(stages=stages,attempted=len(runs),accepted=sum(r['success'] for r in runs),
        failure_classes=dict(Counter(r.get('failure_class') for r in runs if not r['success'])),
        conclusion=json.loads((root/'conclusion.json').read_text()),cells=cells,
        verified_ulog_count=verified,seed_pairing=pairing,seed_diversity=diversity,
        scope='Diagnostic/training cells are not independent performance evidence; validation is a separate partition if actually present')
    for name,data in [('summary.json',summary),('runs.json',runs),('failures.json',[r for r in runs if not r['success']])]:
        (out/name).write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    for name in ('provenance.json','candidates.json','scalar.json','diagnosis_audit.json','diagnosis_gate.json',
                 'screen_selection.json','training_scores.json','conclusion.json','selected.json',
                 'VALIDATION_FREEZE.json','validation_comparison.json'):
        if (root/name).exists():shutil.copy2(root/name,out/name)
    print(json.dumps({k:summary[k] for k in ('stages','attempted','accepted','verified_ulog_count')},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();main(a.root.resolve(),a.output.resolve())
