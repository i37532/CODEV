#!/usr/bin/env python3
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3]
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load():
 f=json.loads((HERE/'FROZEN_RC.json').read_text())
 for x in f['sources'].values():
  p=Path(x['path']) if Path(x['path']).is_absolute() else REPO/x['path']
  if digest(p)!=x['sha256']:raise RuntimeError('Frozen source changed: '+str(p))
 m=json.loads((REPO/f['sources']['m10_frozen']['path']).read_text());rb=json.loads(Path(f['sources']['rb_summary']['path']).read_text());protocol=json.loads((REPO/'research/sta-rate-control/m06/protocol.json').read_text());protocol['milestone']='I05R-C';protocol['limits']['selected_command_abs']=.15;protocol['limits']['nu_abs_rad_s2']=3.;return f,m,Path(f['sources']['plugins_manifest']['path']).parent,protocol
def jobs(head):
 f,m,_,protocol=load();rows=[]
 for div in f['divisors']:
  for i,seed in enumerate(f['paired_seeds']):
   order=('esta','proper_ista') if i%2==0 else ('proper_ista','esta')
   for alg in order:
    p=dict(m['selection']['1']['parameters']);p.update(f['parameters']);p.update(MC_RTC_MODE=1 if alg=='esta' else 3,MC_STA_AXES=7,MC_RTC_DIV=div)
    rows.append(dict(subgate='A',remediation_subgate='R-C',algorithm=alg,mode=p['MC_RTC_MODE'],divisor=div,scene='nominal',seed=seed,parameters=p,fixed_parameters=m['fixed_parameters'],formal=True,frozen_head=head,flight_protocol=protocol,simulation_speed_requested=5))
 return f,rows
