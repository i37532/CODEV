"""Separately authorized six-attempt batch with offline-verified logcheck07."""
import hashlib
import json
from v04_protocol06 import REPO, load_protocol as previous_protocol

CONFIG = REPO/'research/sta-velocity-control/v04/protocol07'
TOKEN = 'V04-protocol07-series06-six-attempts'

def load_protocol():
    if hashlib.sha256((CONFIG.parent/'protocol06/execution.json').read_bytes()).hexdigest() != '77617c14d3c0ee13e0d7a1dc60e87e7ffccdf4a14b41e062f84b54e718da0af8':
        raise ValueError('Historical execution changed')
    p = previous_protocol()
    execution = json.loads((CONFIG/'execution.json').read_text())
    allowed = {'stage','status','seeds','jobs','artifacts','authorization','logcheck_contract'}
    for key, value in execution.items():
        if key not in allowed and value != p[key]:
            raise ValueError('Unexpected rule change: '+key)
    p.update(execution)
    if p['seeds'] != [9601,9602,9603] or len(p['jobs']) != 6 or p['maximum_attempts'] != 6:
        raise ValueError('Wrong new budget')
    for n, job in enumerate(p['jobs']):
        mode=n%2
        if job != dict(id=f'run{n+1:02d}',seed=p['seeds'][n//2],mode=mode,axes=mode,
                       parameters={**p['candidate'],'MPC_VC_MODE':mode,'MPC_VC_AXES':mode}):
            raise ValueError('Wrong job order or parameters')
    if p['artifacts']['new_run_root'] != '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series06':
        raise ValueError('Wrong output root')
    return p

def require_authorization(token, protocol):
    if token != TOKEN or not protocol['execution_ready'] or not protocol['flight_authorized']:
        raise RuntimeError('Exact protocol07 authorization and ready protocol required')
