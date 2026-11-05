#!/usr/bin/env python3
import hashlib, json
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]

def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load(name='A'):
    frozen=json.loads((HERE/f'FROZEN_{name}.json').read_text())
    for spec in frozen['sources'].values():
        path=Path(spec['path']) if Path(spec['path']).is_absolute() else REPO/spec['path']
        if digest(path)!=spec['sha256']: raise RuntimeError('Frozen source changed: '+str(path))
    m10=json.loads((REPO/frozen['sources']['m10_frozen']['path']).read_text())
    plugins=Path(frozen['sources']['plugins_manifest']['path']).parent
    return frozen,m10,plugins

def jobs(head,name='A'):
    frozen,m10,_=load(name); rows=[]
    for seed,algorithm in frozen['ordered_jobs']:
        mode=1 if algorithm=='esta' else 3
        parameters=dict(m10['selection']['1']['parameters']); parameters.update(frozen['parameters'])
        parameters.update(MC_RTC_MODE=mode,MC_STA_AXES=frozen['axes'],MC_RTC_DIV=frozen['divisor'])
        rows.append(dict(subgate=name,algorithm=algorithm,mode=mode,scene='nominal',seed=seed,
                         parameters=parameters,fixed_parameters=m10['fixed_parameters'],formal=True,
                         frozen_head=head,flight_protocol=frozen['flight_protocol'],
                         simulation_speed_requested=frozen['simulation_speed_requested']))
    return frozen,rows
