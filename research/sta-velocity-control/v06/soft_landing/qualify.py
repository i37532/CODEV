"""Freeze one complete soft-contact qualification, never pool historical batches."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from contact_model import SETTINGS

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[3]
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(); p.add_argument('--batch',type=Path,required=True)
    p.add_argument('--replay',type=Path,required=True); p.add_argument('--verification',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    ledger_path=a.batch/'ledger.json'; ledger=json.loads(ledger_path.read_text())
    replay_path=a.replay/'evidence.json'; replay=json.loads(replay_path.read_text())
    verification=json.loads(a.verification.read_text())
    assert ledger['planned']==6 and ledger['success'] and len(ledger['attempts'])==6
    assert ledger['parameter_restore_exact'] and not ledger['remaining_simulators']
    assert len(ledger['pairs'])==3 and all(p['accepted'] for p in ledger['pairs'])
    assert replay['success'] and len(replay['commands'])==6 and all(x['identical_metrics'] and x['exit_code']==0 for x in replay['commands'])
    assert verification['success'] and verification['cpp_tests']>0 and verification['python_tests']>0
    assert ledger['source_head']==verification['head']
    rows=[]; artifacts={str(f):sha(f) for f in (ledger_path,replay_path,a.verification)}
    for attempt in ledger['attempts']:
        assert attempt['status']=='accepted'
        directory=Path(attempt['directory']); f=directory/'xyz_metrics.json'; metrics=json.loads(f.read_text())
        assert metrics['accepted'] and sha(f)==attempt['metrics_sha256']
        artifacts[str(f)]=sha(f)
        record=json.loads((directory/'result.json').read_text()); assert record['success']
        for entry in record['logs']:
            assert sha(Path(entry['archive']))==entry['sha256']; artifacts[entry['archive']]=entry['sha256']
        health=metrics['landing_health']
        assert len(health['imu'])==3 and all(x['clipping']==0 for x in health['imu'].values())
        assert len(health['estimator'])==6 and all(x['faults']==0 for x in health['estimator'].values())
        rows.append(dict(id=attempt['job']['id'],seed=attempt['job']['seed'],mode=attempt['job']['mode'],
            velocity_rmse=metrics['diagnostic']['error']['rmse'],acceleration_tv=metrics['diagnostic']['acceleration_tv'],
            position_rmse=metrics['position_rmse'],yaw_rmse=metrics['yaw_rmse'],hz=metrics['diagnostic']['hz'],
            peak_abs_acceleration=max(max(x['peak_abs']) for x in health['accel'].values()),
            tail_reads=len(metrics['postland_tail']['snapshots'])))
    means={}
    for mode in (0,1):
        group=[r for r in rows if r['mode']==mode]; assert len(group)==3
        means[str(mode)]={k:np.mean([r[k] for r in group],axis=0).tolist() for k in ('velocity_rmse','position_rmse','yaw_rmse','acceleration_tv')}
    output=dict(qualified=True,scope='Iris compliant-contact SITL qualification only; not hardware or controller superiority',
        source_head=ledger['source_head'],firmware_sha256=ledger['firmware_sha256'],
        protocol_sha256=sha(ROOT.parent/'sl_protocol02/execution.json'),contact_settings=SETTINGS,
        contact_source_sha256=sha(ROOT/'contact_model.py'),original_iris_sha256=sha(REPO/'Tools/sitl_gazebo/models/iris/iris.sdf'),
        planned=6,accepted=6,pairs=3,rows=rows,means=means,evidence_sha256=artifacts,
        cpp_tests=verification['cpp_tests'],python_tests=verification['python_tests'])
    with a.output.open('x') as f: json.dump(output,f,indent=2,ensure_ascii=False); f.write('\n')
    print(json.dumps(dict(accepted=6,pairs=3,means=means,peaks=[r['peak_abs_acceleration'] for r in rows])))


if __name__=='__main__': main()
