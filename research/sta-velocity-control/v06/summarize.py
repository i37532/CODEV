#!/usr/bin/env python3
"""Require all 18 accepted trials and equal independent full-chain replay."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser()
    for name in ('batch','replay','verification','output'): p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args(); ledger=read(a.batch/'ledger.json'); evidence=read(a.verification/'evidence.json')
    assert ledger['success'] and ledger['parameter_restore_exact'] and not ledger['remaining_simulators']
    assert len(ledger['attempts'])==18 and len(ledger['pairs'])==9
    assert all(x['accepted'] and x['paired_noise'] for x in ledger['pairs'])
    assert evidence['success'] and evidence['head']==ledger['source_head']
    assert all(c['exit_code']==0 for c in evidence['commands'])
    rows=[]
    for item in ledger['attempts']:
        assert item['status']=='accepted'
        run=Path(item['directory']); row=read(run/'xyz_metrics.json')
        assert row['accepted'] and read(a.replay/run.name/'xyz_metrics.json')==row
        rows.append(row)
    groups=[]
    for task in ('hover','figure8','heading'):
        for mode in (0,1):
            group=[r for r in rows if r['job']['mode']==mode and r['job']['task']==task]; assert len(group)==3
            windows={}
            for window in ('first_loop','second_loop','combined'):
                ds=[r['diagnostic'] if window=='combined' else r['diagnostic']['windows'][window] for r in group]
                windows[window]=dict(velocity_rmse_mean=[statistics.mean(d['error']['rmse'][i] for d in ds) for i in range(3)],
                    acceleration_request_tv_mean=[statistics.mean(d['acceleration_tv'][i] for d in ds) for i in range(3)],
                    normalized_thrust_tv_mean=[statistics.mean(d['normalized_thrust_tv'][i] for d in ds) for i in range(3)],
                    constraint_fraction_max=max(d['constraint_fraction'] for d in ds),
                    constraint_continuous_max_s=max(d['maximum_continuous_constraint_s'] for d in ds))
            groups.append(dict(task=task,mode=mode,n=3,windows=windows,
                height_rmse_mean=statistics.mean(d['height']['rmse'] for d in group),
                yaw_rmse_mean=statistics.mean(d['yaw_rmse'] for d in group),
                position_rmse_mean=[statistics.mean(d['position_rmse'][i] for d in group) for i in range(3)]))
    for line in (a.output.parent/'raw_artifacts.sha256').read_text().splitlines():
        expected,path=line.split('  ',1); assert sha(Path(path))==expected,path
    paths=[a.batch/'ledger.json']+[f for root in (a.verification,a.replay) for f in root.rglob('*') if f.is_file()]
    result=dict(accepted=True,source_head=ledger['source_head'],verification=evidence,isolated_replays_equal=18,
        groups=groups,evidence_sha256={str(f):sha(f) for f in sorted(set(paths))})
    with a.output.open('x') as stream: json.dump(result,stream,indent=2,ensure_ascii=False); stream.write('\n')
    print(json.dumps(dict(accepted=True,groups=groups,replay_count=18)))
if __name__=='__main__': main()
