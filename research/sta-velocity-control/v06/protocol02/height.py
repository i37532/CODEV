"""Protocol09 wired clock09 height checks, versioned from protocol08 (5f791eac46).

Only the explicit attitude_policy binding changes; all numerical gates and
handoff logic are retained. A source-equivalence test prevents silent drift.
"""
import json
import numpy as np
from analyze_v00 import previous_indices
from handoff import check_handoff
from v04_heading_stream import replay
from v04_task04 import REFERENCE


def height_evidence(u, run, d, events, *, attitude_policy):
    ref = json.loads((run/'height_reference.json').read_text())
    frozen=json.loads((run/'task_yaw.json').read_text())
    heading=replay(u,ref,end=events['landed_disarmed'],frozen=frozen,attitude_policy=attitude_policy)
    if not frozen['timestamp']<events['reposition_command']<events['hover_start']:
        raise ValueError('Wrong heading freeze/command order')
    ref['yaw']=frozen['yaw']
    handoff = check_handoff(u, run, ref, frozen, events)
    pos=u.get_dataset('vehicle_local_position').data
    armed=(pos['timestamp']>=events['takeoff_command'])&(pos['timestamp']<=events['landed_disarmed'])
    for key in REFERENCE:
        # CLI serializes ref_alt to 4 decimals; log has float32. No reset/reference changes allowed.
        values=pos[key][armed]
        tol=1e-3 if key=='ref_alt' else 0
        if not len(values) or np.any(np.abs(values.astype(float)-ref['position'][key])>tol) or np.any(values!=values[0]):
            raise ValueError('Changed local reference '+key)
    # Verify >=3 contiguous seconds immediately before recorded hover_start from actual samples.
    start=events['hover_start']-3e6; end=events['hover_start']
    ix=np.flatnonzero((pos['timestamp']>=start)&(pos['timestamp']<=end))
    if len(ix)<250 or pos['timestamp'][ix[0]]-start>40000 or end-pos['timestamp'][ix[-1]]>40000:
        raise ValueError('Missing 3s entry window')
    if np.any(np.diff(pos['timestamp'][ix].astype(np.int64))<=0) or np.max(np.diff(pos['timestamp'][ix].astype(np.int64)))>40000:
        raise ValueError('Entry log gap')
    height=ref['position']['z']-pos['z'][ix]
    if np.any((height<2)|(height>3)) or np.any(np.abs(pos['vz'][ix])>=.2): raise ValueError('Unstable 3s height entry')
    for key in ('xy_valid','z_valid','v_xy_valid','v_z_valid'):
        if not np.all(pos[key][ix]): raise ValueError('Invalid entry estimate')
    for name,fields in [('vehicle_status',dict(arming_state=2,nav_state=4,failsafe=0)),
                        ('vehicle_land_detected',dict(landed=0,ground_contact=0))]:
        src=u.get_dataset(name).data; j,_=previous_indices(src['timestamp'],pos['timestamp'][ix])
        for key,val in fields.items():
            if np.any(src[key][j]!=val): raise ValueError('Invalid entry '+key)
    trajectory=u.get_dataset('trajectory_setpoint').data
    j,_=previous_indices(trajectory['timestamp'],pos['timestamp'][ix],40000)
    if not all(np.all(np.isfinite(trajectory[key][j])) for key in ('z','vz','yaw')):
        raise ValueError('Nonfinite entry trajectory')
    if (np.any(np.abs(trajectory['z'][j]-ref['target_z'])>.05)
            or np.any(np.abs(trajectory['vz'][j])>.05)
            or np.any(np.abs(np.angle(np.exp(1j*(trajectory['yaw'][j]-ref['yaw']))))>.001)):
        raise ValueError('Wrong entry trajectory')
    dm=(d['timestamp']>=start)&(d['timestamp']<events['hover_end'])
    if not np.all(np.isfinite(d['p_sp[2]'][dm])) or np.any(np.abs(d['p_sp[2]'][dm]-ref['target_z'])>.05):
        raise ValueError('Wrong consumed height target')
    em=(d['excitation_time']>=0)&(d['excitation_time']<32)&(d['timestamp']>=events['takeoff_command'])
    if not np.any(em) or np.any(d['timestamp'][em]<events['hover_start']) or np.any(d['timestamp'][em]>=events['hover_end']):
        raise ValueError('Excitation outside observation')
    gate=d['timestamp_sample'][em].astype(float)-(d['excitation_time'][em].astype(float)+12)*1e6
    if np.ptp(gate)>10 or events['hover_start']-np.median(gate)>10e6: raise ValueError('Excitation clock/deadline')
    return dict(heading=heading,handoff=handoff,entry_samples=len(ix),entry_min_height_m=float(height.min()),entry_max_height_m=float(height.max()),
                reference=ref,excitation_gate_timestamp_us=float(np.median(gate)),
                ready_after_gate_s=float((events['hover_start']-np.median(gate))*1e-6))
