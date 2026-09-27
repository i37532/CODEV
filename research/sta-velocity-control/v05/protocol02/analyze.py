#!/usr/bin/env python3
from common import REPO
"""Protocol10 analysis: inherited metrics, explicit XY provenance."""
import argparse
import json
import shutil
from pathlib import Path
import numpy as np
from pyulog import ULog
import xycore as historical
from xycore import compare
from analyze_v00 import previous_indices
from run_v00 import save
from v04_attitude_clock09 import AttitudeClockPolicy
from analyze_v04_height16 import height_evidence
from common import load_protocol, CONFIG, fingerprint
from analyze_v04_handoff09 import check_handoff
from landing_complete import check_complete
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
    if not start < hover_start < hover_end <= land < end or not 90e6 <= hover_end-hover_start <= 92e6:
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
        excitation_class(int(d['excitation_fault'][j]), bool(d['armed'][j]), int(n),
                         t >= land, t >= hover_end, d['excitation_y'][j])
        counts[category] += 1
    # Check all armed data, including gaps before host takeoff event; no exceptions there.
    pre = d['armed'].astype(bool) & (d['timestamp'] < start)
    if np.any(d['excitation_fault'][pre]): raise ValueError('Fault before flight window')
    disarmed = (d['timestamp'] >= end) & ~d['armed'].astype(bool)
    if not np.any(disarmed) or np.any(d['excitation_fault'][disarmed]): raise ValueError('Disarm did not clear')
    if not counts['expected_planned_landing_gate']: raise ValueError('No nominal landing gate evidence')
    return dict(raw_fault_counts={str(int(k)): int(v) for k,v in zip(*np.unique(d['excitation_fault'][m],return_counts=True))},
                classification=counts, raw_values_preserved=True)



def analyze(run, protocol, job):
    out=dict(accepted=False,job=job)
    original=historical.CONFIG
    original_baseline=historical.analyze_v00.CONFIG
    policy=AttitudeClockPolicy()
    try:
        if job not in protocol['jobs']:
            raise ValueError('Job is not in the new frozen batch; historical results cannot be accepted')
        record=json.loads((run/'result.json').read_text())
        approval=json.loads((run/'authorization.json').read_text())
        if (approval.get('approved') is not True or approval.get('stage') != protocol['stage']
                or approval.get('source_head') != record.get('source_head')
                or approval.get('execution_sha256') != fingerprint(CONFIG/'execution.json')
                or approval.get('maximum_attempts') != protocol['maximum_attempts']
                or record.get('scenario_sha256') != approval['execution_sha256']
                or record.get('scenario_path') != str(CONFIG/'execution.json')
                or json.loads((run/'job.json').read_text()) != job):
            raise ValueError('Wrong frozen source/protocol/job authorization provenance')
        historical.CONFIG=CONFIG
        out=historical.analyze(run,protocol,job,attitude_policy=policy)
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
        out['height_task']=height_evidence(u,run,d,events,attitude_policy=policy)
        out['landing10']=check_complete(u,events,json.loads((run/'landing_context.json').read_text()))
        out['accepted']=bool(base_accepted)
    except (KeyError,ValueError,IndexError,FileNotFoundError) as exc:
        out['error']=str(exc); out['accepted']=False
    finally:
        historical.CONFIG=original
        historical.analyze_v00.CONFIG=original_baseline
    save(run/'v05_metrics.json',out)
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
