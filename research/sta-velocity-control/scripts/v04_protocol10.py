"""Landing10 batch registration; execution requires a NEW explicit user receipt."""
import hashlib
import json
import subprocess
from pathlib import Path
from v04_protocol09 import REPO, load_protocol as previous_protocol

CONFIG = REPO/'research/sta-velocity-control/v04/protocol10'
CHANGED = {'stage','status','seeds','jobs','artifacts','authorization',
           'logcheck_contract','flight_authorized','landing_contract'}


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_protocol():
    if fingerprint(CONFIG.parent/'protocol09/execution.json') != '9e1e2a76a6498930a7af990b60b4c7ebabc7d1457c08b03d6e129cb767ca2921':
        raise ValueError('Historical execution changed')
    p = previous_protocol()
    execution = json.loads((CONFIG/'execution.json').read_text())
    for key, value in execution.items():
        if key not in CHANGED and value != p[key]:
            raise ValueError('Unexpected rule change: '+key)
    p.update(execution)
    if (p['seeds'] != [9901,9902,9903] or len(p['jobs']) != 6
            or p['maximum_attempts'] != 6 or p['flight_authorized'] is not False):
        raise ValueError('Wrong proposed budget/authorization')
    for n, job in enumerate(p['jobs']):
        mode=n%2
        if job != dict(id=f'run{n+1:02d}',seed=p['seeds'][n//2],mode=mode,axes=mode,
                       parameters={**p['candidate'],'MPC_VC_MODE':mode,'MPC_VC_AXES':mode}):
            raise ValueError('Wrong job order or parameters')
    if p['artifacts']['new_run_root'] != '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260926/V04/series09':
        raise ValueError('Wrong output root')
    return p


def require_authorization(receipt_path, protocol):
    """No magic token, inherited approval or automatic receipt creation.

    After explicit user approval the operator records an external JSON receipt.
    Its exact execution hash binds jobs, budget, paths, parameters and rules;
    source hash binds implementation. This records authority, not a signature.
    """
    path = Path(receipt_path) if receipt_path else None
    if path is None or not path.is_absolute() or not path.is_file():
        raise RuntimeError('New explicit user authorization receipt required')
    try:
        receipt = json.loads(path.read_text())
        head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
        if (not protocol['execution_ready'] or receipt['approved'] is not True
                or receipt['stage'] != protocol['stage']
                or receipt['source_head'] != head
                or receipt['execution_sha256'] != fingerprint(CONFIG/'execution.json')
                or receipt['maximum_attempts'] != 6
                or not isinstance(receipt['user_approval'], str) or not receipt['user_approval'].strip()):
            raise ValueError('Wrong source/protocol/budget/approval binding')
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError('Invalid new flight authorization receipt') from exc
    return receipt
