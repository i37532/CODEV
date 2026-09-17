#!/usr/bin/env python3
"""Decode the deliberately changed-request lifecycle ULog, not performance data."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from pyulog import ULog
from analyze_m00 import analyze
from analyze_m03 import vector, require
from analyze_m04 import check_gyro_events


def main(run):
    result=json.loads((run/'result.json').read_text());require(result['success'],'Flight failed')
    events=json.loads((run/'armed_lifecycle.json').read_text());require(len(events)==2,'Missing armed checks')
    matches=[]
    for i,item in enumerate(result['logs']):
        require(hashlib.sha256(Path(item['archive']).read_bytes()).hexdigest()==item['sha256'],'ULog fingerprint')
        log=ULog(item['archive'])
        if log.initial_parameters.get('SDLOG_PROFILE')==147:matches.append((i,log,item))
    require(len(matches)==1,'Expected one research log');idx,log,item=matches[0]
    analyze(run,log_index=idx)
    d=log.get_dataset('sta_rate_ctrl_status').data;armed=d['armed'].astype(bool)
    require(np.count_nonzero(armed)>10000,'Insufficient flight data')
    require(np.all(d['effective_mode']==2)&np.all(d['effective_axes']==7),'Effective mode changed')
    require(np.all(d['fault']==0)&np.all(d['abort_requested']==0),'Fault/abort')
    require(np.all(d['output_valid'][armed])&np.all(d['measurement_valid'][armed]),'Invalid output/measurement')
    require(np.all(d['timing_status'][armed]==0)&np.all(d['pid_updated'][armed]==0),'Time or idle PID')
    check_gyro_events(log.get_dataset('gyro_sample_status').data,d['timestamp_sample'])
    require(np.all(d['config_seq'][armed]==d['config_seq'][armed][0]),'Active config changed')
    require(np.all(vector(d,'lambda1')[armed,0]==np.float32(2.2)),'Active gain changed')
    pending=armed&d['pending'].astype(bool)&d['config_pending'].astype(bool)
    require(np.count_nonzero(pending)>100 and np.all(d['requested_mode'][pending]==1),'Missing deferred mode')
    require(np.all(d['reset_reason'][pending]==0),'Pending request reset state')
    contiguous=armed[1:]&armed[:-1]&(d['reset_reason'][1:]==0)
    np.testing.assert_array_equal(vector(d,'nu_before')[1:][contiguous],vector(d,'nu')[:-1][contiguous])
    require(np.all(vector(d,'nu')[~armed][-1]==0),'Post-disarm state not reset')
    changes=[(int(t),k,float(v)) for t,k,v in log.changed_parameters if k in ('MC_RTC_MODE','MC_STA_L1_R')]
    require({k for _,k,_ in changes}=={'MC_RTC_MODE','MC_STA_L1_R'},'Missing parameter changes')
    summary=dict(success=True,scope='separate lifecycle flight, not performance comparison',
                 pending_samples=int(np.count_nonzero(pending)),parameter_changes=changes,
                 ulog_sha256=item['sha256'],post_disarm_nu=vector(d,'nu')[~armed][-1].tolist(),
                 pid_updates_armed=int(np.sum(d['pid_updated'][armed])))
    (run/'lifecycle_analysis.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);main(p.parse_args().run)
