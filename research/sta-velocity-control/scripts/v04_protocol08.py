"""Separately authorized six-attempt batch after verified IMU0 conversion repair."""
import hashlib
import json
from v04_protocol07 import REPO, load_protocol as previous_protocol

CONFIG = REPO/'research/sta-velocity-control/v04/protocol08'
TOKEN = 'V04-protocol08-series07-six-attempts'

def load_protocol():
    if hashlib.sha256((CONFIG.parent/'protocol07/execution.json').read_bytes()).hexdigest() != 'b26942a6c63f009657585cd80b4e4d3b023a053cf62fcd037408d3bffcb87466':
        raise ValueError('Historical execution changed')
    p = previous_protocol()
    execution = json.loads((CONFIG/'execution.json').read_text())
    allowed = {'stage','status','seeds','jobs','artifacts','authorization','logcheck_contract'}
    for key, value in execution.items():
        if key not in allowed and value != p[key]:
            raise ValueError('Unexpected rule change: '+key)
    p.update(execution)
    if p['seeds'] != [9701,9702,9703] or len(p['jobs']) != 6 or p['maximum_attempts'] != 6:
        raise ValueError('Wrong new budget')
    for n, job in enumerate(p['jobs']):
        mode=n%2
        if job != dict(id=f'run{n+1:02d}',seed=p['seeds'][n//2],mode=mode,axes=mode,
                       parameters={**p['candidate'],'MPC_VC_MODE':mode,'MPC_VC_AXES':mode}):
            raise ValueError('Wrong job order or parameters')
    if p['artifacts']['new_run_root'] != '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series07':
        raise ValueError('Wrong output root')
    return p

def require_authorization(token, protocol):
    if token != TOKEN or not protocol['execution_ready'] or not protocol['flight_authorized']:
        raise RuntimeError('Exact protocol08 authorization and ready protocol required')
