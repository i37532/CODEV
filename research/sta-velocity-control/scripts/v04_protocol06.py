"""New six-attempt authorization; immutable handoff06 design and old numerical gates."""
import hashlib
import json
from v04_protocol05 import REPO, load_protocol as previous_protocol

CONFIG = REPO/'research/sta-velocity-control/v04/protocol06'
TOKEN = 'V04-protocol06-series05-six-attempts'


def load_protocol():
    for rel, expected in {
        'protocol05/execution.json': 'a61ffac6b782ad91d744a1cf1af65c0150a8b4ebc088c64611cf9f060248a143',
        'handoff06/protocol.json': '073f24c82a98ba108f418e6a163a5563af53f86634c05ac7071c32c80648eae9',
    }.items():
        if hashlib.sha256((CONFIG.parent/rel).read_bytes()).hexdigest() != expected:
            raise ValueError('Historical design changed: '+rel)
    p = previous_protocol()
    execution = json.loads((CONFIG/'execution.json').read_text())
    allowed = {'stage','status','flight_authorized','seeds','jobs','artifacts','authorization','handoff_contract'}
    for key, value in execution.items():
        if key not in allowed and value != p[key]:
            raise ValueError('Unexpected rule change: '+key)
    p.update(execution)
    if p['seeds'] != [9501,9502,9503] or len(p['jobs']) != 6 or p['maximum_attempts'] != 6:
        raise ValueError('Wrong new budget')
    for n, job in enumerate(p['jobs']):
        mode = n % 2
        if job != dict(id=f'run{n+1:02d}',seed=p['seeds'][n//2],mode=mode,axes=mode,
                       parameters={**p['candidate'],'MPC_VC_MODE':mode,'MPC_VC_AXES':mode}):
            raise ValueError('Wrong job order or parameters')
    if p['artifacts']['new_run_root'] != '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series05':
        raise ValueError('Wrong output root')
    # Supersede only the invalid-triplet/NaN-XY handoff, not original height or flight gates.
    p['height_task']['reposition'].update(
        command='MAV_CMD_DO_REPOSITION in one COMMAND_INT, frame5, target1/1',
        param5='COMMAND_INT.x = nearest integer latitude degrees * 1e7',
        param6='COMMAND_INT.y = nearest integer longitude degrees * 1e7',
        xy='Once-captured fresh onboard trajectory XY, projected with immutable original NED reference; never measured-position or truth substitution',
        require='Fresh accepted addressed ACK, AUTO_LOITER and exact encoded target within 5s; pending only before qualification; no resend; raw/CLI representations checked separately')
    design=json.loads((CONFIG.parent/'handoff06/protocol.json').read_text())
    p['handoff_design']={k:design[k] for k in ('source','wire','projection','handoff','downstream')}
    return p


def require_authorization(token, protocol):
    if token != TOKEN or not protocol['execution_ready'] or not protocol['flight_authorized']:
        raise RuntimeError('Exact protocol06 authorization and ready protocol required')
