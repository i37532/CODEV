"""V04 common descent-cap scenario; original safety/performance rules unchanged."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

CONFIG = Path(__file__).resolve().parent
REPO = CONFIG.parents[3]
sys.path.insert(0, str(REPO / 'research/sta-velocity-control/scripts'))
from v04_protocol10 import load_protocol as old_protocol
from check_v04_protocol02 import seed_audit


def fingerprint(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_protocol():
    p = old_protocol(); e = json.loads((CONFIG / 'execution.json').read_text())
    if e['seeds'] != [13001, 13002, 13003] or e['maximum_attempts'] != 6 or e['descent_cap'] != .55 or e['land_speed'] != .6:
        raise ValueError('Wrong frozen scenario/budget')
    p.update(stage=e['stage'], seeds=e['seeds'], maximum_attempts=6)
    p['startup_overrides'] = {**p['startup_overrides'], 'MPC_Z_VEL_MAX_DN': .55, 'MPC_LAND_SPEED': .6}
    p['jobs'] = [dict(id=f'run{2*i+mode+1:02d}', seed=seed, mode=mode, axes=mode,
        parameters={**p['candidate'], 'MPC_VC_MODE': mode, 'MPC_VC_AXES': mode})
        for i, seed in enumerate(e['seeds']) for mode in (0, 1)]
    p['artifacts'] = {**p['artifacts'], 'new_run_root': e['new_run_root']}
    return p


def fresh_seeds():
    r = seed_audit(load_protocol()['seeds'])
    allowed = {str(CONFIG / 'execution.json'), str(CONFIG / 'seed_audit.json')}
    r['design_registrations'] = [x for x in r['matches'] if x['path'] in allowed]
    r['matches'] = [x for x in r['matches'] if x['path'] not in allowed]
    r['accepted'] = not r['matches'] and not r['invalid_json']
    return r


def require_authorization(path, p):
    f = Path(path) if path else None
    if f is None or not f.is_absolute() or not f.is_file(): raise RuntimeError('Missing standing authorization binding')
    r = json.loads(f.read_text())
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
    if (r.get('approved') is not True or r.get('source_head') != head or r.get('stage') != p['stage']
            or r.get('execution_sha256') != fingerprint(CONFIG / 'execution.json') or r.get('maximum_attempts') != 6
            or r.get('basis') != 'standing user authorization for ordinary repairs and new SITL batches'):
        raise RuntimeError('Wrong source/protocol/budget/authority')
    return r
