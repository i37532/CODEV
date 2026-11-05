"""Draft protocol03 common; install under repository only AFTER training02 stops."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

CONFIG=Path(__file__).resolve().parent
REPO=CONFIG.parents[3]
TRAIN=REPO/'research/sta-velocity-control/v08/protocol02'
spec=importlib.util.spec_from_file_location('v08_frozen_training_design',TRAIN/'common.py')
training=importlib.util.module_from_spec(spec);spec.loader.exec_module(training)
ROOT=training.ROOT
fingerprint=training.fingerprint
candidates=training.candidates
jobs=training.jobs

def design():return json.loads((CONFIG/'execution.json').read_text())

def load_protocol():
    d=design();selection=json.loads((CONFIG/'selection.json').read_text())
    if fingerprint(CONFIG/'selection.json')!=d['selection_sha256']:raise RuntimeError('Frozen training selection changed')
    p=training.load_protocol()
    p.update(stage=d['stage'],seeds=training.design()['validation_seeds'],maximum_attempts=12,
             flight_authorized=True,execution_ready=True)
    p['jobs']=jobs('validation',selection['selected'])
    if p['jobs']!=selection['validation_jobs'] or p['jobs']!=d['jobs']:raise RuntimeError('Wrong frozen validation list')
    p['artifacts']={**p['artifacts'],'new_run_root':str(ROOT/'validation01')}
    return p

def fresh_seeds():
    d=design();r=training.seed_audit(load_protocol()['seeds'])
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
    if f is None or not f.is_absolute() or not f.is_file():raise RuntimeError('Missing V08 validation authority binding')
    r=json.loads(f.read_text());head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    if (r.get('approved') is not True or r.get('source_head')!=head or r.get('stage')!=p['stage']
            or r.get('execution_sha256')!=fingerprint(CONFIG/'execution.json') or r.get('maximum_attempts')!=12
            or r.get('basis')!='User explicitly requested V08 continuous execution, not V09'):
        raise RuntimeError('Wrong V08 validation source/protocol/budget/authority')
    return r
