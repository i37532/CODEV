#!/usr/bin/env python3
"""Protocol08 analysis: inherited metrics, explicit XY provenance."""
import argparse
import json
import shutil
from pathlib import Path
import numpy as np
from pyulog import ULog
import analyze_v04_core04 as historical
from analyze_v04 import compare
from analyze_v00 import previous_indices
from run_v00 import save
from v04_heading_stream import replay
from v04_protocol08 import load_protocol, CONFIG
from analyze_v04_handoff07 import check_handoff
from v04_task04 import REFERENCE, excitation_class

def check_first_invocation(d, mask):
    for key in ('first_fail', 'first_input', 'retry_result', 'excitation_fault'):
        if key not in d: raise ValueError('Missing field '+key)
    active = mask & d['enabled'].astype(bool)
    if not np.any(active): raise ValueError('No active samples')
    if np.any(d['first_fail'][active]) or np.any(d['retry_result'][active]):
        raise ValueError('First invocation failed/retried')
    expected = np.zeros(np.count_nonzero(active), dtype=np.uint16)
    for group, field in enumerate(('p_sp', 'v_ff', 'a_ff', 'v', 'v_dot')):
        for axis in range(3):
            expected |= np.isfinite(d[f'{field}[{axis}]'][active]).astype(np.uint16) << (3*group+axis)
    if not np.array_equal(expected, d['first_input'][active]): raise ValueError('Input validity mask mismatch')
    return dict(samples=int(active.sum()), first_failures=0, retries=0,
                first_input_masks=np.unique(expected).tolist())


def check_excitation_exit(d, status, events):
    start, end = events['takeoff_command'], events['landed_disarmed']
    hover_start, hover_end, land = (events[k] for k in ('hover_start', 'hover_end', 'land_command'))
    if not start < hover_start < hover_end <= land < end or not 60e6 <= hover_end-hover_start <= 62e6:
        raise ValueError('Invalid observation/landing event order')
    m = (d['timestamp'] >= start) & (d['timestamp'] <= end)
    i, _ = previous_indices(status['timestamp'], d['timestamp'][m])
    nav = status['nav_state'][i]
    # Once actual AUTO_LAND is observed, no return to LOITER/restart is allowed.
    landed = np.flatnonzero((nav == 18) & (d['timestamp'][m] >= land))
    if not len(landed) or np.any(nav[landed[0]:] != 18): raise ValueError('Missing/left planned AUTO_LAND')
    counts = {'clear': 0, 'expected_planned_landing_gate': 0}
    for j, n in zip(np.flatnonzero(m), nav):
        t = d['timestamp'][j]
        category = excitation_class(int(d['excitation_fault'][j]), bool(d['armed'][j]), int(n),
                                    t >= land, t >= hover_end, d['excitation'][j])
        counts[category] += 1
    # Check all armed data, including gaps before host takeoff event; no exceptions there.
    pre = d['armed'].astype(bool) & (d['timestamp'] < start)
    if np.any(d['excitation_fault'][pre]): raise ValueError('Fault before flight window')
    disarmed = (d['timestamp'] >= end) & ~d['armed'].astype(bool)
    if not np.any(disarmed) or np.any(d['excitation_fault'][disarmed]): raise ValueError('Disarm did not clear')
    if not counts['expected_planned_landing_gate']: raise ValueError('No nominal landing gate evidence')
    return dict(raw_fault_counts={str(int(k)): int(v) for k,v in zip(*np.unique(d['excitation_fault'][m],return_counts=True))},
                classification=counts, raw_values_preserved=True)


def height_evidence(u, run, d, events):
    ref = json.loads((run/'height_reference.json').read_text())
    frozen=json.loads((run/'task_yaw.json').read_text())
    heading=replay(u,ref,end=events['landed_disarmed'],frozen=frozen)
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


def analyze(run, protocol, job):
    out=dict(accepted=False,job=job)
    original=historical.CONFIG
    try:
        if job not in protocol['jobs']:
            raise ValueError('Job is not in the new frozen batch; historical results cannot be accepted')
        historical.CONFIG=CONFIG
        out=historical.analyze(run,protocol,job)
        base_accepted=out['accepted']; out['accepted']=False
        r=json.loads((run/'result.json').read_text()); events={x['name']:x['timestamp_us'] for x in r['events']}
        base=json.loads((run/'v00_metrics.json').read_text())
        u=ULog(base['ulog']['archive']); d=u.get_dataset('sta_velocity_ctrl_status').data
        mask=(d['timestamp']>=events['takeoff_command'])&(d['timestamp']<events['landed_disarmed'])
        out['first_invocation']=check_first_invocation(d,mask)
        commands=[json.loads(line) for line in (run/'commands.jsonl').read_text().splitlines()]
        lands=[c for c in commands if c['cmd'][-3:]==['commander','mode','auto:land'] or c['cmd'][-2:]==['mode','auto:land']]
        if len(lands)!=1 or lands[0]['returncode']!=0: raise ValueError('Planned land command not unique/successful')
        out['exit']=check_excitation_exit(d,u.get_dataset('vehicle_status').data,events)
        out['height_task']=height_evidence(u,run,d,events)
        out['accepted']=bool(base_accepted)
    except (KeyError,ValueError,IndexError,FileNotFoundError) as exc:
        out['error']=str(exc); out['accepted']=False
    finally:
        historical.CONFIG=original
    save(run/'v04_protocol08_metrics.json',out)
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('run',type=Path); p.add_argument('--output',type=Path,required=True); args=p.parse_args()
    # CLI replay is always isolated: never rewrite historical metrics/result files.
    source=args.run.resolve(); target=args.output.resolve()
    if source==target or source in target.parents: raise ValueError('Use independent new analysis directory')
    target.mkdir(parents=True,exist_ok=False)
    for item in source.iterdir():
        if item.is_file() and item.suffix in ('.json','.jsonl','.txt','.log'):
            shutil.copyfile(item,target/item.name)
    job=json.loads((target/'job.json').read_text()); protocol=load_protocol()
    protocol['startup_overrides'].update(job['parameters'])
    result=analyze(target,protocol,job); print(json.dumps(result,indent=2)); raise SystemExit(0 if result['accepted'] else 1)
