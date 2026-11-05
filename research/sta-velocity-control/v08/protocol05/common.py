"""Finite independent V08 safety pilots, no holdout execution."""
import importlib.util
import json
from pathlib import Path
import subprocess
CONFIG=Path(__file__).resolve().parent
REPO=CONFIG.parents[3]
TRAIN=REPO/'research/sta-velocity-control/v08/protocol02'
spec=importlib.util.spec_from_file_location('v08_pilot_training_design',TRAIN/'common.py')
training=importlib.util.module_from_spec(spec);spec.loader.exec_module(training)
ROOT=training.ROOT
fingerprint=training.fingerprint
candidates=training.candidates

def design():return json.loads((CONFIG/'execution.json').read_text())

def jobs():
    d=design();result=[];selected=json.loads((CONFIG/'selection.json').read_text())['selected']
    for ti,scene in enumerate(('mass',)):
        task='heading' if scene=='heading' else 'figure8'
        for si,seed in enumerate(d['pilot_seeds']):
            for mode in ((0,1) if (ti+si)%2==0 else (1,0)):
                name=selected[str(mode)]
                job=training.make_job(len(result)+1,'pilot',task,seed,name,candidates()[name])
                job.update(scene=scene,gate=scene)
                result.append(job)
    return result

def load_protocol():
    d=design()
    if fingerprint(CONFIG/'selection.json')!=d['selection_sha256']:raise RuntimeError('Pilot selection changed')
    p=training.load_protocol()
    p.update(stage=d['stage'],seeds=d['pilot_seeds'],maximum_attempts=6,flight_authorized=True,execution_ready=True,jobs=jobs())
    if p['jobs']!=d['jobs']:raise RuntimeError('Pilot list/order changed')
    p['artifacts']={**p['artifacts'],'new_run_root':str(ROOT/'pilots02_mass')}
    return p

def fresh_seeds():
    d=design();r=training.seed_audit(d['pilot_seeds'])
    allowed={str(CONFIG/'execution.json'),str(CONFIG/'seed_audit.json')}
    for path,expected in d['seed_reservations'].items():
        if fingerprint(path)!=expected:raise RuntimeError('Changed explicit seed reservation '+path)
        allowed.add(path)
    r['design_registrations']=[x for x in r['matches'] if x['path'] in allowed]
    r['matches']=[x for x in r['matches'] if x['path'] not in allowed]
    r['accepted']=not r['matches'] and not r['invalid_json']
    return r

def require_authorization(path,p):
    f=Path(path) if path else None
    if f is None or not f.is_absolute() or not f.is_file():raise RuntimeError('Missing pilot source/budget authority')
    r=json.loads(f.read_text());head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    if (r.get('approved') is not True or r.get('source_head')!=head or r.get('stage')!=p['stage']
            or r.get('execution_sha256')!=fingerprint(CONFIG/'execution.json') or r.get('maximum_attempts')!=6
            or r.get('basis')!='User explicitly requested V08 continuous execution, not V09'):
        raise RuntimeError('Wrong pilot source/protocol/budget/authority')
    return r
