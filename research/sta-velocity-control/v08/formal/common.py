"""Frozen V09-only manifest adapter. V08 authority NEVER enables execution."""
import importlib.util
import json
from pathlib import Path
import subprocess
CONFIG=Path(__file__).resolve().parent
REPO=Path('/home/yr/Desktop/Codev-autopilot')
TRAIN=REPO/'research/sta-velocity-control/v08/protocol02'
spec=importlib.util.spec_from_file_location('v09_training_design',TRAIN/'common.py')
training=importlib.util.module_from_spec(spec);spec.loader.exec_module(training)
ROOT=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-V09-FORMAL01')
fingerprint=training.fingerprint
candidates=training.candidates

def design():return json.loads((CONFIG/'execution.json').read_text())

def jobs():
    d=design();path=CONFIG/'manifest.json'
    if fingerprint(path)!=d['manifest_sha256']:raise RuntimeError('Formal manifest changed')
    result=json.loads(path.read_text())
    if len(result)!=200 or any(j['phase']!='formal' for j in result):raise RuntimeError('Not exact formal manifest')
    return result

def load_protocol():
    d=design()
    if fingerprint(CONFIG/'selection.json')!=d['selection_sha256']:raise RuntimeError('Formal selection changed')
    if d['execution_ready']:
        qpath=CONFIG/'qualification.json'
        if fingerprint(qpath)!=d['qualification_sha256']:raise RuntimeError('Qualification evidence changed')
        q=json.loads(qpath.read_text())
        if q.get('accepted') is not True or set(q['qualified_scenes'])!={'hover','figure8','heading','force','mass'}:
            raise RuntimeError('Formal scenes have not all passed development gates')
        if q['selection_sha256']!=d['selection_sha256']:raise RuntimeError('Qualified parameters differ')
    p=training.load_protocol()
    p.update(stage=d['stage'],seeds=d['formal_seeds'],maximum_attempts=200,
             flight_authorized=True,execution_ready=d['execution_ready'],jobs=jobs())
    p['artifacts']={**p['artifacts'],'new_run_root':str(ROOT)}
    return p

def fresh_seeds():
    d=design();r=training.seed_audit(d['formal_seeds'])
    allowed={str(CONFIG/'execution.json'),str(CONFIG/'manifest.json'),str(CONFIG/'seed_audit.json'),str(CONFIG/'outcomes_unattempted.json'),str(CONFIG/'zero_holdout_statistics_reference.json')}
    for path,expected in d['seed_reservations'].items():
        if fingerprint(path)!=expected:raise RuntimeError('Changed design-only seed reservation '+path)
        allowed.add(path)
    reference=CONFIG/'zero_holdout_statistics_reference.json'
    if reference.exists():
        expected=fingerprint(reference)
        for match in r['matches']:
            path=Path(match['path'])
            # An offline verification of the EXACT all-unattempted table
            # consumes no flight RNG. No directory blanket exclusion, and
            # even a one-byte changed/nonempty outcome is NOT exempted.
            if path.name=='zero_holdout_statistics.json' and fingerprint(path)==expected:
                allowed.add(str(path))
    r['design_registrations']=[x for x in r['matches'] if x['path'] in allowed]
    r['matches']=[x for x in r['matches'] if x['path'] not in allowed]
    r['accepted']=not r['matches'] and not r['invalid_json']
    return r

def require_authorization(path,p):
    f=Path(path) if path else None
    if f is None or not f.is_absolute() or not f.is_file():raise RuntimeError('V09 requires NEW explicit user authority; V08 is insufficient')
    r=json.loads(f.read_text());head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    if (r.get('approved') is not True or r.get('source_head')!=head or r.get('stage')!=p['stage']
            or r.get('execution_sha256')!=fingerprint(CONFIG/'execution.json') or r.get('maximum_attempts')!=200
            or r.get('basis')!='User explicitly authorized V09 formal holdout execution, not V08'):
        raise RuntimeError('Wrong V09 source/protocol/budget/authority')
    return r
