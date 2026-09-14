#!/usr/bin/env python3
"""Decode failed ESTA attempts, preserving failure and full-rate evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from pyulog import ULog
from analyze_m03 import vector, pid_output, require


def inspect(run):
    result=json.loads((run/'result.json').read_text())
    logs=[(item,ULog(item['archive'])) for item in result['logs']]
    item,log=next((item,log) for item,log in logs if log.initial_parameters.get('SDLOG_PROFILE')==147)
    require(hashlib.sha256(Path(item['archive']).read_bytes()).hexdigest()==item['sha256'],'ULog hash')
    d=log.get_dataset('sta_rate_ctrl_status').data
    armed=d['armed'].astype(bool)
    require(np.all(d['effective_mode']==1),'ESTA-only diagnosis')
    s=d['s[0]'];old=d['nu_before[0]']
    alpha=-(d['lambda1[0]']*np.sqrt(abs(s)))*np.sign(s)+old
    np.testing.assert_allclose(d['a_raw[0]'][armed],alpha[armed],rtol=1e-6,atol=1e-7)
    np.testing.assert_allclose(d['c_raw[0]'][armed],(alpha/d['g[0]'])[armed],rtol=1e-6,atol=1e-7)
    p=pid_output(d)[armed,1:].copy();actual=vector(d,'c_raw')[armed,1:].copy()
    mismatch=int(np.count_nonzero(p.view(np.uint32)!=actual.view(np.uint32)))
    a=log.get_dataset('vehicle_attitude').data
    tilt=np.degrees(np.arccos(np.clip(1-2*(a['q[1]']**2+a['q[2]']**2),-1,1)))
    fields=['timestamp_sample','armed','landed','maybe_landed','rate[0]','rate_sp[0]','nu_before[0]',
            'nu[0]','a_raw[0]','c_applied[0]','limits[0]','experiment_updated','fault']
    first=d['timestamp_sample'][armed][0]
    indices=np.unique(np.minimum(np.searchsorted(d['timestamp_sample'],np.arange(first,d['timestamp_sample'][-1]+1,250000)),len(s)-1))
    return dict(note='Diagnostic only; scenario failure remains failure. No hover RMSE invented.',
        flight_completed=result['success'],error=result.get('error'),ulog_sha256=item['sha256'],
        binary_sha256=result['binary_sha256'],pid_pitch_yaw_bit_mismatches=mismatch,
        formula_checked_samples=int(np.count_nonzero(armed)),max_tilt_deg=float(np.max(tilt)),
        nu_peak=float(np.max(abs(d['nu[0]']))),nu_limit_samples=int(np.count_nonzero(d['limits[0]']&4)),
        fault_samples=int(np.count_nonzero(d['fault'])),timing_bad_armed=int(np.count_nonzero(d['timing_status'][armed])),
        max_abs_rate=float(np.max(abs(vector(d,'rate')[armed]))),
        samples_250ms=[{k:d[k][i].item() for k in fields} for i in indices])


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('run',type=Path); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    with args.output.open('x') as stream:
        json.dump(inspect(args.run),stream,indent=2); stream.write('\n')
