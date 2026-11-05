"""V07 finite DIV1 -> DIV2 -> DIV4 gates; no automatic flight by import."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
CONFIG=Path(__file__).resolve().parent
REPO=CONFIG.parents[3]
sys.path.insert(0,str(REPO/'research/sta-velocity-control/scripts'))
from v04_protocol10 import load_protocol as inherited
from check_v04_protocol02 import seed_audit

def fingerprint(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_protocol():
    e=json.loads((CONFIG/'execution.json').read_text()); p=inherited()
    assert e['maximum_attempts']==18 and e['divisors']==[1,2,4]
    assert e['seeds']==list(range(33001,33010)) and e['modes']==[0,1]
    p.update(stage=e['stage'],seeds=e['seeds'],maximum_attempts=18)
    q=json.loads((REPO/'research/sta-velocity-control/v05/qualified_xy.json').read_text())['parameters']
    p['candidate']={k:v for k,v in q.items() if k.startswith(('MPC_VC_L','MPC_VC_NU','MPC_VC_A_'))}
    p['startup_overrides']={**p['startup_overrides'],'MPC_Z_VEL_MAX_DN':.55,'MPC_LAND_SPEED':.6,'MPC_VCT_TEST':0,'MPC_VC_DIV':1}
    p['jobs']=[]
    for gi,divisor in enumerate(e['divisors']):
        for seed in e['seeds'][gi*3:gi*3+3]:
            for mode in e['modes']:
                p['jobs'].append(dict(id=f'run{len(p["jobs"])+1:02d}',task='figure8',gate=f'n{divisor}',divisor=divisor,seed=seed,mode=mode,axes=3*mode,
                    parameters={**p['candidate'],'MPC_VC_MODE':mode,'MPC_VC_AXES':3*mode,'MPC_VC_DIV':divisor,'MPC_VCT_TEST':6}))
    p['artifacts']={**p['artifacts'],'new_run_root':e['new_run_root']}
    return p

def fresh_seeds():
    r=seed_audit(load_protocol()['seeds']); allowed={str(CONFIG/'execution.json'),str(CONFIG/'seed_audit.json')}
    r['design_registrations']=[x for x in r['matches'] if x['path'] in allowed]
    r['matches']=[x for x in r['matches'] if x['path'] not in allowed]
    r['accepted']=not r['matches'] and not r['invalid_json']; return r

def require_authorization(path,p):
    f=Path(path) if path else None
    if f is None or not f.is_absolute() or not f.is_file(): raise RuntimeError('Missing standing authority binding')
    r=json.loads(f.read_text()); head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    if (r.get('approved') is not True or r.get('source_head')!=head or r.get('stage')!=p['stage']
        or r.get('execution_sha256')!=fingerprint(CONFIG/'execution.json') or r.get('maximum_attempts')!=18
        or r.get('basis')!='V07 bounded landing polling standing authorization 2026-09-29; new eighteen-attempt budget'):
        raise RuntimeError('Wrong source/protocol/budget/authority')
    return r
