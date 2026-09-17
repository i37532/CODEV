#!/usr/bin/env python3
"""Explicitly retain ONE pre-arm diagnostic loss as invalid, then allow resume.

Never marks the flight accepted, supplies missing metrics, retries, or changes
source. All other infrastructure/data failures remain blocking by default.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from pyulog import ULog


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def check_gap(d,dropouts,mode):
    delta=np.diff(d['publish_seq'].astype(np.int64));gap=np.flatnonzero(delta!=1)
    assert len(gap)==1 and delta[gap[0]]==2, 'Only one missing diagnostic sample'
    i=int(gap[0]);assert not d['armed'][i] and not d['armed'][i+1]
    assert np.any(d['armed'])
    assert np.all(d['timestamp_sample'][d['armed'].astype(bool)]>d['timestamp_sample'][i+1])
    assert np.all(np.diff(d['timestamp_sample'].astype(np.int64))==4000*delta)
    assert not dropouts
    for field in ('fault','abort_requested','termination','pending','config_pending','div_wait'):
        assert not np.any(d[field]), field
    assert np.all(d['effective_mode']==mode)
    assert np.all(d['effective_axes']==(7 if mode else 0))
    return i


def review(root,label):
    run=root/label;analysis=run/'m10_analysis.json'
    row=json.loads(analysis.read_text());result=json.loads((run/'result.json').read_text())
    assert not row['success'] and result['success'], 'Only completed but rejected flights'
    assert row.get('failure_class')=='analysis_or_data_quality'
    assert row.get('error')=="ValueError('Missing diagnostics: no TV/spectrum acceptance')"
    logs=[]
    for item in result['logs']:
        assert sha(Path(item['archive']))==item['sha256']
        log=ULog(item['archive'])
        if log.initial_parameters.get('SDLOG_PROFILE',0)&16:logs.append(log)
    assert len(logs)==1
    log=logs[0];d=log.get_dataset('sta_rate_ctrl_status').data
    i=check_gap(d,log.dropouts,row['mode'])
    target=root/(label+'.adjudication.json')
    assert not target.exists(), 'Never overwrite an earlier adjudication'
    data=dict(disposition='retain_failed_attempt_and_continue',retained_prearm_gap=True,
              analysis_resolved_without_reflight=False,flight_repeated=False,accepted=False,
              reason='Exactly one pre-arm diagnostic sample lost; all other diagnostic sequence increments valid. Keep data-quality failure and no accepted TV/PSD; do not replace the attempt.',
              original_execution=str(root/(label+'.execution.json')),
              new_analysis_sha256=sha(analysis),result_sha256=sha(run/'result.json'),
              gap=dict(before_seq=int(d['publish_seq'][i]),after_seq=int(d['publish_seq'][i+1]),
                       before_sample_us=int(d['timestamp_sample'][i]),after_sample_us=int(d['timestamp_sample'][i+1])),
              ulogs={item['archive']:item['sha256'] for item in result['logs']})
    target.write_text(json.dumps(data,indent=2)+'\n');print(json.dumps(data,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('label')
    a=p.parse_args();review(a.root.resolve(),a.label)
