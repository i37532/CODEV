"""Protocol05: separately authorized budget; inherited numerical rules unchanged."""
import hashlib
import json
from v04_protocol04 import REPO, load_protocol as previous_protocol

CONFIG = REPO/'research/sta-velocity-control/v04/protocol05'
TOKEN = 'V04-protocol05-series04-six-attempts'


def load_protocol():
    # Hash-pin historical inheritance; never rewrite earlier execution files.
    for name, expected in {
        'protocol.json': 'c071d1648ee260fcfde411514d11feef6926cf165113739c61bbfd63b4d1db8d',
        'execution.json': 'd910b97a31075d609668d6b955d1dc2f2c779a7ff164a06b03afeda2337d7238',
    }.items():
        if hashlib.sha256((CONFIG.parent/'protocol04'/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Historical protocol04 changed: '+name)
    p = previous_protocol()
    execution = json.loads((CONFIG/'execution.json').read_text())
    # Only batch identity/authorization/CLI representation documentation may change.
    allowed = {'stage', 'status', 'flight_authorized', 'seeds', 'jobs', 'artifacts', 'authorization', 'cli_reference'}
    for key, value in execution.items():
        if key not in allowed and value != p[key]:
            raise ValueError('Unexpected rule change: '+key)
    p.update(execution)
    if p['seeds'] != [9401, 9402, 9403] or len(p['jobs']) != 6 or p['maximum_attempts'] != 6:
        raise ValueError('Wrong new budget')
    for n, job in enumerate(p['jobs']):
        mode = n % 2
        if job != dict(id=f'run{n+1:02d}', seed=p['seeds'][n//2], mode=mode, axes=mode,
                       parameters={**p['candidate'], 'MPC_VC_MODE':mode, 'MPC_VC_AXES':mode}):
            raise ValueError('Wrong new job order or parameters')
    if p['artifacts']['new_run_root'] != '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series04':
        raise ValueError('Wrong new output root')
    return p


def require_authorization(token, protocol):
    if token != TOKEN or not protocol['execution_ready'] or not protocol['flight_authorized']:
        raise RuntimeError('Exact protocol05 authorization and ready protocol required')
