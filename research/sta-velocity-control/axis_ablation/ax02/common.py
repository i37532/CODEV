"""Independent AX02 design. Import/dry-run never authorizes AX03 flights."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

CONFIG = Path(__file__).resolve().parent
REPO = CONFIG.parents[3]
LEGACY = REPO/'research/sta-velocity-control/v08/protocol02'
for path in (LEGACY, REPO/'research/sta-velocity-control/scripts',
             REPO/'research/sta-velocity-control/v06/soft_landing'):
    if str(path) not in sys.path: sys.path.append(str(path))
from v04_protocol10 import load_protocol as inherited

def fingerprint(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def design(): return json.loads((CONFIG/'execution.json').read_text())
def expanded(d): return [{**j,'parameters':{**d['fixed_parameters'],**j['parameters']}} for j in d['jobs']]
def jobs(): return expanded(design())

def load_protocol():
    d=design(); p=inherited()
    p.update(d['protocol_overrides'])
    p.update(stage=d['stage'],jobs=expanded(d),seeds=d['seeds'],maximum_attempts=48,
             flight_authorized=False,execution_ready=True)
    p['startup_overrides']={**p['startup_overrides'],**d['fixed_parameters']}
    p['candidate']={k:v for k,v in d['fixed_parameters'].items() if k.startswith(('MPC_VC_L','MPC_VC_NU','MPC_VC_A_'))}
    p['artifacts']={**p['artifacts'],'new_run_root':d['output_root']}
    return p

def validate_manifest(d=None):
    d=design() if d is None else d
    jobs=expanded(d); masks={'PID':0,'X':1,'Y':2,'Z':4,'XY':3,'XZ':5,'YZ':6,'XYZ':7}
    if len(jobs)!=48 or d['maximum_attempts']!=48: raise ValueError('Exactly 48 attempts required')
    if len(set(d['seeds']))!=6 or set(d['seeds']) & set(range(41001,41021)): raise ValueError('Seed conflict')
    if (set(d['task_seeds'])!={'H','V'} or any(len(v)!=3 for v in d['task_seeds'].values())
        or set(d['seeds'])!=set(sum(d['task_seeds'].values(),[]))): raise ValueError('Inconsistent seed registration')
    for number,j in enumerate(jobs,1):
        task='H' if number<=24 else 'V'; axis=masks.get(j['candidate'])
        if (j['id']!=f'run{number:02d}' or j['task']!=task or j['gate']!=task
            or axis is None or j['axes']!=axis or j['mode']!=int(bool(axis)) or j['divisor']!=1):
            raise ValueError('Invalid order/mask/mode')
        expected={**d['fixed_parameters'],'MPC_VC_MODE':int(bool(axis)),'MPC_VC_AXES':axis,
                  'MPC_VCT_TEST':6 if task=='H' else 8}
        if j['parameters']!=expected: raise ValueError('Per-combination tuning or parameter drift')
    for task,seeds in d['task_seeds'].items():
        subset=[j for j in jobs if j['task']==task]
        if len(subset)!=24 or {j['seed'] for j in subset}!=set(seeds): raise ValueError('Wrong task seeds')
        for seed in seeds:
            block=[j for j in subset if j['seed']==seed]
            if len(block)!=8 or {j['axes'] for j in block}!=set(range(8)) or block[0]['axes']!=0:
                raise ValueError('Incomplete paired block/PID reference')
    if jobs[24]['candidate']!='PID' or jobs[24]['seed']!=d['task_seeds']['V'][0]: raise ValueError('Missing V PID safety gate')
    return True

def fresh_seeds():
    # Unlike the old helper, skip NO directory. Exempt only exact, frozen,
    # design-only JSON records; attempts anywhere remain a conflict.
    import check_v04_protocol02 as audit
    old=audit.CONFIG
    try:
        audit.CONFIG=Path('/__AX02_no_directory_exemption__')
        r=audit.seed_audit(design()['seeds'])
    finally: audit.CONFIG=old
    allowed=json.loads((CONFIG/'seed_reservations.json').read_text())
    for name,expected in allowed.items():
        if fingerprint(name)!=expected: raise RuntimeError('Changed seed reservation '+name)
    r['design_registrations']=[x for x in r['matches'] if x['path'] in allowed]
    r['matches']=[x for x in r['matches'] if x['path'] not in allowed]
    r['accepted']=not r['matches'] and not r['invalid_json']
    r['excluded']='none; exact fingerprinted design registrations only'
    return r

def require_authorization(path,p):
    f=Path(path) if path else None
    if f is None or not f.is_absolute() or not f.is_file():
        raise RuntimeError('AX02 is offline; AX03 needs its own explicit authority receipt')
    r=json.loads(f.read_text()); head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    if (r.get('approved') is not True or r.get('source_head')!=head or r.get('stage')!=p['stage']
        or r.get('execution_sha256')!=fingerprint(CONFIG/'execution.json') or r.get('maximum_attempts')!=48
        or r.get('basis')!='User explicitly requested AX03, limited to this frozen 48-attempt batch'):
        raise RuntimeError('Wrong AX03 source/protocol/budget/authority')
    validate_manifest()
    return r

class Admission:
    """State machine shared by runner and offline wiring tests; no retry/resume."""
    def __init__(self):
        self.jobs=jobs(); self.accepted=[]; self.reference={}; self.failed=False

    def before(self,job):
        if self.failed or len(self.accepted)>=48 or self.jobs[len(self.accepted)]!=job:
            raise RuntimeError('Failed/exhausted/out-of-order batch')
        if job['task']=='V' and len(self.accepted)<24: raise RuntimeError('H gate incomplete')
        if job['axes'] and (job['task'],job['seed']) not in self.reference:
            raise RuntimeError('Missing accepted paired PID')

    def accept(self,job,metrics):
        self.before(job)
        if not metrics.get('accepted') or metrics.get('job')!=job:
            self.failed=True; raise RuntimeError('Required flight/log gate failed')
        key=(job['task'],job['seed']); pair=None
        if job['axes']:
            from core import compare
            pair=compare(self.reference[key],metrics)
            if not pair['accepted']:
                self.failed=True; raise RuntimeError('Frozen paired development risk gate failed')
        else: self.reference[key]=metrics
        self.accepted.append(job)
        return pair

    def abort(self): self.failed=True
