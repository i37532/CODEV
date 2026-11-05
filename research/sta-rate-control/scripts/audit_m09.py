#!/usr/bin/env python3
"""Supplementary whole-flight boundary/state audit, no simulator/control writes."""
import argparse
import json
from pathlib import Path
import numpy as np
from pyulog import ULog
from analyze_m03 import require, vector, pid_output


def audit(run):
    source=run/'m09_analysis_v2.json'
    if not source.exists():source=run/'m09_analysis.json'
    m=json.loads(source.read_text());log=ULog(m['ulog'])
    d=log.get_dataset('sta_rate_ctrl_status').data;t=d['timestamp_sample'].astype(np.int64)
    armed=d['armed'].astype(bool);mode=m['mode'];div=m['div']
    require(np.any(armed),'No armed samples')
    update=d['updated'].astype(bool)
    if mode==0:
        require(np.array_equal(pid_output(d)[update].view(np.uint32),vector(d,'c_held')[update].view(np.uint32)),
                'PID differs at float bit level')
    act=log.get_dataset('actuator_controls_0').data
    common,di,ai=np.intersect1d(t[armed],act['timestamp_sample'],return_indices=True)
    di=np.flatnonzero(armed)[di]
    actual=np.column_stack([act[f'control[{i}]'][ai] for i in range(3)])
    require(len(common)>1000 and np.array_equal(actual.view(np.uint32),vector(d,'c_applied')[di].view(np.uint32)),
            'Actuator differs at float bit level')
    require(np.array_equal(act['control[3]'][ai].view(np.uint32),d['thrust'][di].view(np.uint32)), 'Thrust bit mismatch')
    at=log.get_dataset('vehicle_attitude').data
    ai=np.searchsorted(t,at['timestamp'],side='right')-1;ok=ai>=0
    flying=ok & armed[np.maximum(ai,0)]
    q=np.column_stack([at[f'q[{i}]'] for i in range(4)])
    tilt=np.degrees(np.arccos(np.clip(1-2*(q[:,1].astype(float)**2+q[:,2].astype(float)**2),-1,1)))
    require(np.max(tilt[flying])<=15,'Whole-flight tilt boundary')
    before=vector(d,'nu_before');nu=vector(d,'nu');update=d['updated'].astype(bool)
    limits=vector(d,'limits').astype(np.uint8);candidate=vector(d,'nu_candidate')
    if mode:
        idx=np.flatnonzero(armed & update)
        frozen=d['landed'][idx].astype(bool)|d['maybe_landed'][idx].astype(bool)
        g=vector(d,'g')[idx]
        delta=(candidate[idx]-before[idx])/g
        bits=d['sat_bits'][idx].astype(np.uint16)
        expected=candidate[idx].copy()
        for axis in range(3):
            feedback_bad=~d['sat_valid'][idx].astype(bool)
            direction=((delta[:,axis]>0)&((bits&(1<<(3+2*axis)))!=0))|((delta[:,axis]<0)&((bits&(1<<(4+2*axis)))!=0))
            raw=vector(d,'c_raw')[idx,axis]
            outward=((raw>.15)&(delta[:,axis]>0))|((raw<-.15)&(delta[:,axis]<0))
            freeze=feedback_bad|direction|outward|frozen
            expected[freeze,axis]=before[idx[freeze],axis]
            expected[:,axis]=np.clip(expected[:,axis],-3,3)
        require(np.array_equal(expected,nu[idx]),'Protected nu/freeze is inconsistent')
        require(np.all(before[np.flatnonzero(armed)[0]]==0),'Initial armed nu not reset')
    hold=np.flatnonzero(d['held'].astype(bool)&armed);hold=hold[hold>0]
    changed=int(np.count_nonzero(d['thrust'][hold]!=d['thrust'][hold-1]))
    metrics=json.loads((run/'metrics.json').read_text())
    hover=(t>=metrics['hover_start_us'])&(t<=metrics['hover_end_us'])
    # Embedded consumed sequence can legitimately repeat if no new mixer data;
    # report it separately from loss in the original logged motor topic.
    consumed=d['motor_update_seq'][hover].astype(np.int64);delta_seq=np.diff(consumed)
    out=dict(success=True,mode=mode,div=div,armed_samples=int(armed.sum()),
             actuator_bitwise_samples=len(common),pid_bitwise_samples=int(update.sum()) if mode==0 else 0,
             max_armed_tilt_deg=float(tilt[flying].max()),max_hover_height_error_m=metrics['position_error_m']['max_abs'][2],
             hold_thrust_changes=changed,nu_frozen_or_limited_samples=np.sum(limits[armed]!=0,axis=0).tolist(),
             actual_armed_pid_calls=int(np.count_nonzero(d['pid_updated'][armed])),
             consumed_motor_missing=int(np.sum(np.maximum(delta_seq-1,0))),
             consumed_motor_repeated=int(np.count_nonzero(delta_seq==0)),
             dropout_count=len(log.dropouts),hover_seconds=metrics['hover_duration_s'])
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('series',type=Path);a=p.parse_args()
    rows=[]
    for mode in ('pid','esta','ista'):
        for div in (1,2,4):rows.append(audit(a.series/f'{mode}_div{div}'))
    (a.series/'supplementary_audit.json').write_text(json.dumps(dict(success=True,runs=rows),indent=2)+'\n')
    print(json.dumps(rows,indent=2))
