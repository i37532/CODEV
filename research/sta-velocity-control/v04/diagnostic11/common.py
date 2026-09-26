"""Single-attempt diagnosis registration; no simulator side effects on import."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

CONFIG = Path(__file__).resolve().parent
REPO = CONFIG.parents[3]
sys.path.insert(0, str(REPO / 'research/sta-velocity-control/scripts'))
from v04_protocol10 import load_protocol as inherited_protocol
from check_v04_protocol02 import seed_audit


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_protocol():
    registered = json.loads((CONFIG / 'execution.json').read_text())
    if registered['maximum_attempts'] != 1 or registered['seed'] != 11001 or registered['formal_acceptance']:
        raise ValueError('Wrong one-shot diagnostic registration')
    p = inherited_protocol()
    p.update(stage=registered['stage'], maximum_attempts=1, seeds=[registered['seed']],
             formal_acceptance=False, diagnostic=registered)
    p['jobs'] = [dict(id='run01', seed=registered['seed'], mode=0, axes=0,
        parameters={**p['candidate'], 'MPC_VC_MODE': 0, 'MPC_VC_AXES': 0})]
    return p


def fresh_seeds():
    p = load_protocol(); result = seed_audit(p['seeds'])
    allowed = {str(CONFIG / 'execution.json'), str(CONFIG / 'seed_audit.json')}
    result['design_registrations'] = [m for m in result['matches'] if m['path'] in allowed]
    result['matches'] = [m for m in result['matches'] if m['path'] not in allowed]
    result['accepted'] = not result['matches'] and not result['invalid_json']
    return result


def require_authorization(path, protocol):
    receipt_path = Path(path) if path else None
    if receipt_path is None or not receipt_path.is_absolute() or not receipt_path.is_file():
        raise RuntimeError('Missing recorded standing-authorization/source binding')
    r = json.loads(receipt_path.read_text())
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
    if (r.get('approved') is not True or r.get('source_head') != head
            or r.get('stage') != protocol['stage'] or r.get('maximum_attempts') != 1
            or r.get('execution_sha256') != digest(CONFIG / 'execution.json')
            or r.get('basis') != 'standing user authorization for ordinary repairs and new SITL batches'):
        raise RuntimeError('Wrong diagnostic authorization/source/protocol binding')
    return r
