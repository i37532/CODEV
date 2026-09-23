"""Protocol04 pure gates. No simulator, parameter writes or implicit retries."""
import math
import re
from check_v04_protocol02 import target_altitude

REFERENCE = ('ref_timestamp', 'ref_alt', 'xy_reset_counter', 'z_reset_counter',
             'vxy_reset_counter', 'vz_reset_counter', 'ref_lat', 'ref_lon')


def scalars(raw):
    out = {}
    for key, val in re.findall(r'^\s+(\w+):\s+([^\s]+)', raw, re.M):
        if val in ('True', 'False'):
            out[key] = val == 'True'
        else:
            try: out[key] = float(val)
            except ValueError: pass
    return out


def current_triplet(raw):
    # Generated nested uORB printer: member name then print_message().
    match = re.search(r'\n\s*current\s+position_setpoint_s\b(.*?)(?=\n\s*next\s+position_setpoint_s|\Z)', raw, re.S)
    if not match: raise ValueError('Missing current navigator triplet')
    d = scalars(match[1])
    if not d.get('valid') or not all(math.isfinite(d.get(k, math.nan)) for k in ('lat', 'lon', 'alt')):
        raise ValueError('Invalid navigator target')
    return d


def freeze_reference(p):
    required = (*REFERENCE, 'timestamp', 'timestamp_sample', 'x', 'y', 'z', 'heading')
    if not all(math.isfinite(p.get(k, math.nan)) for k in required):
        raise ValueError('Missing/nonfinite ground reference')
    if not all(p.get(k) for k in ('xy_valid', 'z_valid', 'v_xy_valid', 'v_z_valid', 'xy_global', 'z_global')):
        raise ValueError('Invalid ground estimate')
    z, alt = target_altitude(p['z'], p['ref_alt'])
    return dict(position=dict(p), target_z=z, command_alt=alt, yaw=p['heading'])


def check_reference(p, ref):
    for k in REFERENCE:
        if not math.isfinite(p.get(k, math.nan)) or abs(p[k]-ref['position'][k]) > (1e-3 if k=='ref_alt' else 1e-7 if k in ('ref_lat','ref_lon') else 0): raise ValueError('Coordinate/reset changed: '+k)


def command_params(ref):
    # This pinned receiver copies param4 directly as radians; not a portable MAVLink API.
    if not math.isfinite(ref['yaw']): raise ValueError('Invalid heading')
    return [-1, 1, 0, ref['yaw'], math.nan, math.nan, ref['command_alt']]


def check_readback(before, after, ref):
    if not after.get('valid') or not after.get('yaw_valid'): raise ValueError('Invalid reposition target')
    for k in ('lat', 'lon'):
        if after.get(k) != before[k]: raise ValueError('Reposition changed XY')
    if abs(after.get('alt', math.inf)-ref['command_alt']) > .02: raise ValueError('Wrong target altitude')
    if abs(math.remainder(after.get('yaw', math.inf)-ref['yaw'], 2*math.pi)) > .001:
        raise ValueError('Wrong target yaw/radian units')


def accepted_ack(record, sent):
    return (record['received_monotonic'] >= sent and record['system'] == 1
            and record['component'] == 1 and record['message'].get('command') == 192
            and record['message'].get('result') == 0)


def entry_ok(p, status, land, target, ref):
    check_reference(p, ref)
    h = ref['position']['z'] - p['z']
    return (status.get('arming_state') == 2 and status.get('nav_state') == 4
            and not status.get('failsafe') and not land.get('landed', True)
            and not land.get('ground_contact', True)
            and all(p.get(k) for k in ('xy_valid', 'z_valid', 'v_xy_valid', 'v_z_valid'))
            and 2 <= h <= 3 and abs(p['vz']) < .2
            and abs(target.get('z', math.inf)-ref['target_z']) <= .05
            and abs(target.get('vz', math.inf)) <= .05
            and abs(math.remainder(target.get('yaw', math.inf)-ref['yaw'], 2*math.pi)) <= .001)


class EntryGate:
    def __init__(self):
        self.last = None
        self.start = None
        self.gate_start = None

    def update(self, sample, valid, diagnostic):
        if self.last is not None and not 0 < sample-self.last <= 1e6:
            raise ValueError('Entry sample duplicate/backward/gap')
        self.last = sample
        t = diagnostic['excitation_time']
        if t < -1:  # -1 is the pre-start sentinel; first active samples are near -12.
            self.gate_start = diagnostic['timestamp_sample']-(t+12)*1e6
        if self.gate_start is not None and sample-self.gate_start > 10e6:
            raise ValueError('Height not ready before gate+10s')
        self.start = (sample if self.start is None else self.start) if valid else None
        return self.start is not None and sample-self.start >= 3e6


def excitation_class(fault, armed, nav, planned_landing, completed, output):
    """Preserve the raw mask. Only exact Gate=2 after planned AUTO_LAND is expected."""
    if fault == 0: return 'clear'
    if (fault == 2 and armed and nav == 18 and planned_landing and completed and output == 0):
        return 'expected_planned_landing_gate'
    raise ValueError('Unexpected excitation fault '+str(fault))
