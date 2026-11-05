#!/usr/bin/env python3
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3]
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load():
 f=json.loads((HERE/'FROZEN_RB.json').read_text())
 for x in f['sources'].values():
  p=Path(x['path']) if Path(x['path']).is_absolute() else REPO/x['path']
  if digest(p)!=x['sha256']:raise RuntimeError('Frozen source changed: '+str(p))
 m=json.loads((REPO/f['sources']['m10_frozen']['path']).read_text());return f,m,Path(f['sources']['plugins_manifest']['path']).parent
def jobs(head):
 f,m,_=load();rows=[]
 for seed,alg in f['ordered_jobs']:
  p=dict(m['selection']['1']['parameters']);p.update(f['parameters']);p.update(MC_RTC_MODE=1 if alg=='esta' else 3,MC_STA_AXES=7,MC_RTC_DIV=1)
  rows.append(dict(subgate='A',remediation_subgate='R-B',algorithm=alg,mode=p['MC_RTC_MODE'],scene='nominal',seed=seed,parameters=p,fixed_parameters=m['fixed_parameters'],formal=True,frozen_head=head,flight_protocol=f['flight_protocol'],simulation_speed_requested=5))
 return f,rows
