"""Offline-developed landing evidence policy; no commands, flights or regrading.

Publication-time association is observational, not proof of controller consumption.
Only past/equal status is eligible. A future AUTO_LAND never repairs an earlier
Gate. Live incomplete evidence may be pending for <=0.5 s, never accepted.
"""
import math
import time
import numpy as np
from v04_heading_stream import data, index
from v04_logcheck07 import event_data
from v04_task04 import excitation_class

PENDING_US = 500000


class LandingPending(ValueError):
    pass


def healthy(d):
    """Do not let stale CLI arming state suppress a current diagnostic fault."""
    for key in ('first_fail', 'retry_result', 'fault', 'sta_fault', 'failsafe', 'timing'):
        if key not in d or not math.isfinite(d[key]) or d[key] != 0:
            raise ValueError('Landing diagnostic failure: '+key)
    for key in ('timestamp', 'first_input', 'excitation_fault', 'excitation', 'armed', 'enabled'):
        if key not in d or not math.isfinite(d[key]):
            raise ValueError('Missing/nonfinite landing diagnostic: '+key)
    if d['armed'] not in (0, 1) or d['enabled'] not in (0, 1):
        raise ValueError('Invalid diagnostic boolean')
    if d['armed'] and d['enabled']:
        for key, value in dict(inner_mode=0, inner_axes=0, inner_divisor=1, inner_valid=1,
                               pid_calls=1, valid=1, config_pending=0).items():
            if d.get(key) != value:
                raise ValueError('Landing diagnostic failure: '+key)
    if not math.isfinite(d.get('excitation_y',math.nan)):
        raise ValueError('Missing/nonfinite Y excitation')
    if d['excitation_fault']==2 and d['excitation_y']!=0:
        raise ValueError('Nonzero Y after Gate')
    if not math.isfinite(d.get('excitation_z',math.nan)):
        raise ValueError('Missing/nonfinite Z excitation')
    if d['excitation_fault']==2 and d['excitation_z']!=0:
        raise ValueError('Nonzero Z after Gate')
    if d['excitation_fault'] not in (0, 2):
        raise ValueError('Unexpected excitation fault '+str(d['excitation_fault']))
    if d['excitation_fault'] == 2 and (not d['armed'] or d['excitation'] != 0):
        raise ValueError('Invalid Gate armed/output state')


def validate_context(context):
    a, b, c = (context[k] for k in ('hover_start_us', 'hover_end_us', 'command_lower_us'))
    if not all(math.isfinite(x) and int(x) == x for x in (a, b, c)):
        raise ValueError('Invalid landing context clock')
    if not 0 < a < b <= c or not 90e6 <= b-a <= 92e6 or context.get('cli_success') is not True:
        raise ValueError('Incomplete observation/unsuccessful planned land')


def replay(log, context, through_us, *, final=False):
    """All retained diagnostic rows after observation; no dedup or future matching.

    Final caller additionally requires complete flight/end events and old full
    metrics, waveform, reset, mode and coverage checks. This is one component.
    """
    validate_context(context)
    if log.dropouts or getattr(log, 'file_corruption', False):
        raise ValueError('Landing ULog dropout/corruption')
    d, status = data(log, 'sta_velocity_ctrl_status'), data(log, 'vehicle_status')
    start = context['hover_start_us']
    if not math.isfinite(through_us) or through_us < start:
        raise ValueError('Invalid landing replay interval')
    if np.any(~np.isfinite(status['nav_state_timestamp'])) or np.any(status['nav_state_timestamp'] > status['timestamp']):
        raise ValueError('Future/nonfinite nav transition timestamp')
    sm = (status['timestamp'] >= start) & (status['timestamp'] <= through_us)
    before = int(index(status, start))
    si = np.unique(np.r_[before, np.flatnonzero(sm)])
    if np.any(status['failsafe'][si]) or np.any(status['failure_detector_status'][si]):
        raise ValueError('Landing vehicle failsafe/failure detector')
    rows = np.flatnonzero((d['timestamp'] >= start) & (d['timestamp'] <= through_us))
    if not len(rows):
        raise ValueError('Missing landing diagnostic history')
    # Vectorized full-history validation: do not hide a short fault between polls.
    for key in ('first_fail', 'retry_result', 'fault', 'sta_fault', 'failsafe', 'timing'):
        if key not in d or np.any(~np.isfinite(d[key][rows])) or np.any(d[key][rows] != 0):
            raise ValueError('Landing diagnostic failure: '+key)
    for key in ('armed', 'enabled'):
        if np.any(~np.isin(d[key][rows], [0, 1])):
            raise ValueError('Invalid diagnostic boolean')
    if 'first_input' not in d or np.any(~np.isfinite(d['first_input'][rows])):
        raise ValueError('Missing/nonfinite first_input diagnostic')
    active = rows[d['armed'][rows].astype(bool) & d['enabled'][rows].astype(bool)]
    for key, value in dict(inner_mode=0, inner_axes=0, inner_divisor=1, inner_valid=1,
                           pid_calls=1, valid=1, config_pending=0).items():
        if key not in d or np.any(d[key][active] != value):
            raise ValueError('Landing diagnostic failure: '+key)
    faults = d['excitation_fault'][rows]
    if np.any(~np.isin(faults, [0, 2])) or np.any(~np.isfinite(d['excitation'][rows])):
        raise ValueError('Unexpected excitation fault/nonfinite output')
    if 'excitation_y' not in d or np.any(~np.isfinite(d['excitation_y'][rows])):
        raise ValueError('Missing/nonfinite Y excitation')
    gates = rows[faults == 2]
    if np.any(d['excitation_y'][gates]!=0): raise ValueError('Nonzero Y after Gate')
    if 'excitation_z' not in d or np.any(~np.isfinite(d['excitation_z'][rows])):
        raise ValueError('Missing/nonfinite Z excitation')
    if np.any(d['excitation_z'][gates]!=0): raise ValueError('Nonzero Z after Gate')
    if np.any(~d['armed'][gates].astype(bool)) or np.any(d['excitation'][gates] != 0):
        raise ValueError('Invalid Gate armed/output state')
    if np.any(d['timestamp'][gates] < context['command_lower_us']):
        raise ValueError('Gate before planned command')
    commands = event_data(log, 'vehicle_command')
    mode = (commands['command'] == 176) & (commands['timestamp'] >= context['command_lower_us']) & (commands['timestamp'] <= through_us)
    ci = np.flatnonzero(mode)
    if len(ci) > 1:
        raise ValueError('Repeated/conflicting mode command after plan')
    if len(ci):
        c = int(ci[0])
        for key, value in dict(param1=1, param2=4, param3=6, target_system=1, target_component=1).items():
            if commands[key][c] != value:
                raise ValueError('Wrong planned AUTO_LAND command '+key)
        command_us = int(commands['timestamp'][c])
    else:
        command_us = None
    land_status = si[status['nav_state'][si] == 18]
    if len(land_status):
        first = int(land_status[0])
        if command_us is not None and status['nav_state_timestamp'][first] < command_us:
            raise ValueError('AUTO_LAND before planned command')
        subsequent = si[si >= first]
        if np.any(status['nav_state'][subsequent] != 18):
            raise ValueError('Left planned AUTO_LAND')
    counts = dict(clear=int(np.count_nonzero(faults == 0)), expected_planned_landing_gate=0)
    unresolved = []
    for j in gates:
        t = int(d['timestamp'][j]); fault = int(d['excitation_fault'][j])
        if command_us is not None and t < command_us:
            raise ValueError('Gate before raw planned command')
        k = int(index(status, t))
        nav = int(status['nav_state'][k])
        if command_us is None or nav != 18:
            # A later state seals the earlier mismatch, not permission to borrow it.
            if final or (nav != 18 and int(status['timestamp'][-1]) > t):
                raise ValueError('Gate lacks past/equal planned AUTO_LAND')
            unresolved.append(t)
            continue
        counts[excitation_class(fault, bool(d['armed'][j]), nav, True, True, d['excitation'][j])] += 1
    if unresolved or command_us is None or int(d['timestamp'][-1]) < through_us:
        if final:
            raise ValueError('Incomplete final landing evidence')
        raise LandingPending('Landing raw command/status/diagnostic evidence pending')
    if final and (not len(land_status) or not counts['expected_planned_landing_gate']):
        raise ValueError('Missing nominal landing evidence')
    return dict(command_us=command_us, through_us=int(through_us), diagnostic_rows=len(rows),
                classification=counts, raw_values_preserved=True, consumed_status_proven=False)


class LandingMonitor:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.context = None
        self.pending_since = None
        self.last_now = None
        self.last_wall = None
        self.failed = False
        self.last_evidence = None

    def begin(self, hover_start_us, hover_end_us, command_lower_us, cli_success):
        if self.context is not None or self.failed:
            raise ValueError('Repeated/latched landing plan')
        self.context = dict(hover_start_us=hover_start_us, hover_end_us=hover_end_us,
                            command_lower_us=command_lower_us, cli_success=cli_success)
        validate_context(self.context)

    def update(self, log, diagnostic, now_us):
        if self.failed:
            raise ValueError('Landing monitor latched')
        wall = self.clock()
        try:
            healthy(diagnostic)
            if not math.isfinite(now_us) or not math.isfinite(wall):
                raise ValueError('Invalid monitor clock')
            if self.last_now is not None and (now_us < self.last_now or wall < self.last_wall):
                raise ValueError('Backward monitor clock')
            self.last_now, self.last_wall = now_us, wall
            age = now_us-diagnostic['timestamp']
            if not 0 <= age <= PENDING_US:
                raise ValueError('Landing diagnostic stale/future')
            if self.context is None:
                if diagnostic['excitation_fault']:
                    raise ValueError('Unplanned Gate')
                return dict(category='clear', pending=False)
            if self.pending_since is not None:
                sim, host = self.pending_since
                if now_us-sim > PENDING_US or wall-host > PENDING_US*1e-6:
                    raise ValueError('Landing evidence pending timeout')
            try:
                raw = data(log, 'sta_velocity_ctrl_status')
                through = int(raw['timestamp'][-1])
                if not 0 <= now_us-through <= PENDING_US:
                    raise ValueError('Landing raw transport stale/future')
                evidence = replay(log, self.context, through)
                if diagnostic['excitation_fault'] == 2 and not evidence['classification']['expected_planned_landing_gate']:
                    raise LandingPending('CLI Gate awaiting raw Gate evidence')
                if not diagnostic['armed'] and raw['armed'][-1]:
                    raise LandingPending('Disarm awaiting raw diagnostic')
            except LandingPending:
                if self.pending_since is None:
                    self.pending_since = (now_us, wall)
                self.last_evidence = dict(category='pending_raw_landing_evidence', pending=True)
                return self.last_evidence
            self.pending_since = None
            self.last_evidence = dict(category='raw_landing_verified', pending=False, evidence=evidence)
            return self.last_evidence
        except (ValueError, KeyError, IndexError):
            self.failed = True
            raise

    def require_complete(self):
        if self.failed or self.context is None or not self.last_evidence or self.last_evidence['pending']:
            raise ValueError('Landing completion lacks resolved evidence')
