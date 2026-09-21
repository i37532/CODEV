#!/usr/bin/env python3
"""V00 flight gates plus V01 selector evidence, with separate original metrics."""
import argparse
import json
from pathlib import Path
import numpy as np
from pyulog import ULog
import analyze_v00
from run_v00 import save, digest
from audit_v00_results import saturation_summary, perf_counts

CONFIG = Path(__file__).resolve().parents[1]/'v01/protocol01'


def check_selection(d, start, end):
    mask=(d['timestamp']>=start)&(d['timestamp']<end)
    t=d['timestamp'][mask].astype(np.int64)
    if len(t)<600 or np.any(np.diff(t)<=0) or np.max(np.diff(t))>250000:
        raise ValueError('Selector coverage/nonmonotonic timestamp')
    if np.any(np.diff(d['publish_seq'][mask].astype(np.int64))!=1):
        raise ValueError('Selector sequence missing')
    for field in ('requested_mode','requested_axes','effective_mode','effective_axes','pending','reject'):
        if np.any(d[field][mask]!=0):
            raise ValueError('Unexpected selector field '+field)
    for field in ('timestamp_sample','input_timestamp'):
        if np.any(np.diff(d[field][mask].astype(np.int64))<=0):
            raise ValueError('Selector input timestamp not monotonic')
    active=d['enabled'][mask].astype(bool)
    if np.any(d['pid_calls'][mask][active]!=1) or np.any(d['pid_calls'][mask][~active]!=0):
        raise ValueError('Unexpected PID update count/failsafe retry')
    if not np.any(active & d['armed'][mask].astype(bool)):
        raise ValueError('No armed PID control samples')
    return dict(n=len(t),hz=(len(t)-1)*1e6/(t[-1]-t[0]),maximum_gap_s=float(np.diff(t).max()*1e-6),
                active_pid_samples=int(active.sum()),publish_sequence_complete=True)


def analyze(run, protocol):
    # Explicitly select the V01 frozen parameters for the reused V00 checks.
    analyze_v00.CONFIG=CONFIG
    baseline=analyze_v00.analyze(run,protocol)
    r=json.loads((run/'result.json').read_text())
    events={v['name']:v['timestamp_us'] for v in r['events']}
    log=ULog(baseline['ulog']['archive'])
    summary=dict(accepted=False,baseline_accepted=baseline['accepted'],
                 original_v00_metrics_sha256=digest(run/'v00_metrics.json'))
    try:
        summary['selection']=check_selection(log.get_dataset('velocity_ctrl_selection').data,
                                             events['takeoff_command'],events['landed_disarmed'])
        rate=log.get_dataset('sta_rate_ctrl_status').data
        hm=(rate['timestamp']>=events['hover_start'])&(rate['timestamp']<events['hover_end'])
        summary['saturation_corrected']=saturation_summary(rate['sat_bits'][hm],rate['sat_valid'][hm])
        summary['position_perf_corrected']=perf_counts((run/'console.log').read_text(),baseline['hover_seconds'])
        summary['accepted']=baseline['accepted']
    except (KeyError,ValueError) as error:
        summary['error']=str(error)
    save(run/'v01_metrics.json',summary)
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);args=p.parse_args()
    result=analyze(args.run,json.loads((CONFIG/'protocol.json').read_text()))
    print(json.dumps(result,indent=2));raise SystemExit(0 if result['accepted'] else 1)
