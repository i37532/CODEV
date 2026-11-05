"""V08 preregistered equal-budget tuning. Imports never authorize a flight."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

CONFIG = Path(__file__).resolve().parent
REPO = CONFIG.parents[3]
ROOT = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260929/V08')
sys.path.insert(0, str(REPO/'research/sta-velocity-control/scripts'))
from v04_protocol10 import load_protocol as inherited
from check_v04_protocol02 import seed_audit

def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def design():
    return json.loads((CONFIG/'execution.json').read_text())

def candidates():
    d = design()
    qualified = json.loads((REPO/'research/sta-velocity-control/v05/qualified_xy.json').read_text())['parameters']
    sta = {k:v for k,v in qualified.items() if k.startswith(('MPC_VC_L','MPC_VC_NU','MPC_VC_A_'))}
    result = {}
    for mode in (0,1):
        for index, factor in enumerate(d['candidate_factors'][str(mode)]):
            p = {**sta, 'MPC_VC_MODE':mode, 'MPC_VC_AXES':3*mode, 'MPC_VC_DIV':1}
            p.update({f'MPC_XY_VEL_{k}_ACC':v*(factor if mode==0 else 1.) for k,v in [('P',1.8),('I',.4),('D',.2)]})
            if mode:
                for axis in ('X','Y'):
                    p['MPC_VC_L1_'+axis] = factor
                    p['MPC_VC_L2_'+axis] = .2*factor
            result[f'{"pid" if mode==0 else "esta"}{index}'] = p
    return result

def jobs(phase='training', selected=None):
    d=design(); result=[]; c=candidates()
    if phase=='training':
        # Block each scenario/seed; reverse algorithm and candidate order by block.
        for ti,task in enumerate(d['training_tasks']):
            for si,seed in enumerate(d['training_seeds']):
                order=range(3) if (ti+si)%2==0 else range(2,-1,-1)
                for candidate in order:
                    for mode in ((0,1) if (ti+si+candidate)%2==0 else (1,0)):
                        name=f'{"pid" if mode==0 else "esta"}{candidate}'
                        result.append(make_job(len(result)+1,phase,task,seed,name,c[name]))
    elif phase=='validation':
        if not selected or set(selected)!= {'0','1'}: raise ValueError('Two frozen selections required')
        for ti,task in enumerate(d['validation_tasks']):
            for si,seed in enumerate(d['validation_seeds']):
                for mode in ((0,1) if (ti+si)%2==0 else (1,0)):
                    name=selected[str(mode)]
                    if c[name]['MPC_VC_MODE']!=mode: raise ValueError('Wrong selected algorithm')
                    result.append(make_job(len(result)+1,phase,task,seed,name,c[name]))
    else:
        raise ValueError('Formal and pilot flights are NOT enabled in the training entry')
    return result

def make_job(index,phase,task,seed,name,p):
    return dict(id=f'run{index:02d}',phase=phase,task=task,gate=phase,seed=seed,
                candidate=name,mode=p['MPC_VC_MODE'],axes=p['MPC_VC_AXES'],divisor=1,
                parameters={**p,'MPC_VCT_TEST':{'hover':5,'figure8':6,'heading':7}[task]})

def load_protocol():
    d=design(); p=inherited()
    p.update(stage=d['stage'],seeds=d['training_seeds'],maximum_attempts=24,
             flight_authorized=True,execution_ready=True)
    p['candidate']={k:v for k,v in candidates()['esta2'].items() if k.startswith(('MPC_VC_L','MPC_VC_NU','MPC_VC_A_'))}
    p['startup_overrides']={**p['startup_overrides'],'MPC_Z_VEL_MAX_DN':.55,
        'MPC_LAND_SPEED':.6,'MPC_VCT_TEST':0,'MPC_VC_DIV':1}
    p['jobs']=jobs(); p['artifacts']={**p['artifacts'],'new_run_root':str(ROOT/'training01')}
    return p

def fresh_seeds():
    d=design(); seeds=d['training_seeds']+d['validation_seeds']+d['pilot_seeds']+d['formal_seeds']
    r=seed_audit(seeds)
    allowed={str(CONFIG/'execution.json'),str(CONFIG/'seed_audit.json')}
    r['design_registrations']=[x for x in r['matches'] if x['path'] in allowed]
    r['matches']=[x for x in r['matches'] if x['path'] not in allowed]
    r['accepted']=not r['matches'] and not r['invalid_json']
    return r

def require_authorization(path,p):
    f=Path(path) if path else None
    if f is None or not f.is_absolute() or not f.is_file(): raise RuntimeError('Missing V08 authority binding')
    r=json.loads(f.read_text())
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    if (r.get('approved') is not True or r.get('source_head')!=head or r.get('stage')!=p['stage']
        or r.get('execution_sha256')!=fingerprint(CONFIG/'execution.json')
        or r.get('maximum_attempts')!=p['maximum_attempts']
        or r.get('basis')!='User explicitly requested V08 continuous execution, not V09'):
        raise RuntimeError('Wrong V08 source/protocol/budget/authority')
    return r
