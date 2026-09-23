"""Explicit design inheritance and separate execution proposal; no old budget."""
import copy
import hashlib
import json
from pathlib import Path

REPO=Path(__file__).resolve().parents[3]
CONFIG=REPO/'research/sta-velocity-control/v04/protocol04'
TOKEN='V04-protocol04-series03-six-attempts'


def load_protocol():
    design=json.loads((CONFIG/'protocol.json').read_text())
    parent=REPO/design['parent']['path']
    if hashlib.sha256(parent.read_bytes()).hexdigest()!=design['parent']['sha256']:
        raise ValueError('Historical protocol changed')
    old=json.loads(parent.read_text())
    p={k:copy.deepcopy(old[k]) for k in design['parent']['inherit_unchanged']}
    p.update(json.loads((CONFIG/'execution.json').read_text()))
    p['heading_design']=design
    p['height_task']=copy.deepcopy(old['height_task'])
    p['height_task']['ground_freeze']=design['reference_policy']['before_arm']
    p['height_task']['reposition']['param4']=design['task_yaw_policy']['command']
    p['height_task']['reposition']['coordinate_reference_change']=design['reference_policy']
    p['height_task']['entry']['require']='Original entry plus verified protocol04 alignment and once-only task yaw'
    if p['seeds']!=[9301,9302,9303] or len(p['jobs'])!=6 or p['maximum_attempts']!=6:
        raise ValueError('Unexpected execution proposal')
    for n,j in enumerate(p['jobs']):
        mode=n%2
        if j!={'id':f'run{n+1:02d}','seed':p['seeds'][n//2],'mode':mode,'axes':mode,
              'parameters':{**p['candidate'],'MPC_VC_MODE':mode,'MPC_VC_AXES':mode}}:
            raise ValueError('Job order/parameter mismatch')
    return p


def require_authorization(token,protocol):
    # Operator must supply this only AFTER the separate user flight approval.
    # The present implementation task supplies no token and never executes.
    if token!=TOKEN or not protocol['execution_ready']:
        raise RuntimeError('Separate user flight approval and exact batch token required')
