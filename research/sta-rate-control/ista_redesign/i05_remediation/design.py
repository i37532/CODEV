#!/usr/bin/env python3
import hashlib, json
from pathlib import Path

HERE=Path(__file__).resolve().parent; REPO=HERE.parents[3]
def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load():
    f=json.loads((HERE/'FROZEN_RA.json').read_text())
    for spec in f['sources'].values():
        p=Path(spec['path']) if Path(spec['path']).is_absolute() else REPO/spec['path']
        if digest(p)!=spec['sha256']: raise RuntimeError('Frozen source changed: '+str(p))
    m10=json.loads((REPO/f['sources']['m10_frozen']['path']).read_text())
    return f,m10,Path(f['sources']['plugins_manifest']['path']).parent
def jobs(head):
    f,m10,_=load(); rows=[]
    old=json.loads((REPO/f['sources']['old_i05_frozen']['path']).read_text())
    for seed,algorithm in f['ordered_jobs']:
        params=dict(m10['selection']['1']['parameters']);params.update(f['parameters'])
        params.update(MC_RTC_MODE=1 if algorithm=='esta' else 3,MC_STA_AXES=3,MC_RTC_DIV=1)
        rows.append(dict(subgate='A',remediation_subgate='R-A',algorithm=algorithm,mode=params['MC_RTC_MODE'],scene='nominal',seed=seed,
                         parameters=params,fixed_parameters=m10['fixed_parameters'],formal=True,frozen_head=head,
                         flight_protocol=old['flight_protocol'],simulation_speed_requested=f['simulation_speed_requested']))
    return f,rows
