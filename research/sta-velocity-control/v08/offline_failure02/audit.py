"""Read-only audit of validation01/run06; does not change historical verdict."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

REPO=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(REPO/'research/sta-velocity-control/v08/protocol02'))
from position_log import ULog
from v04_attitude_clock09 import exact_output_match,strict_clock

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def audit(run):
    result=json.loads((run/'result.json').read_text());events={x['name']:x['timestamp_us'] for x in result['events']}
    baseline=json.loads((run/'v00_metrics.json').read_text());archive=Path(baseline['ulog']['archive'])
    log=ULog(str(archive));d=log.get_dataset('sta_velocity_ctrl_status').data;a=log.get_dataset('vehicle_attitude_setpoint').data
    start,end=events['hover_start'],events['hover_end'];m=(d['timestamp']>=start)&(d['timestamp']<end)
    x={k:v[m] for k,v in d.items()};source=strict_clock(a['timestamp']);wanted=strict_clock(x['attitude_timestamp'])
    common,di,ai=np.intersect1d(wanted,source,return_indices=True);missing=np.setdiff1d(wanted,source)
    evidence=dict(historical_accepted=False,flight_completed=bool(result['success']),logs=[dict(path=str(archive),sha256=digest(archive))],
        diagnostic_samples=len(wanted),recorded_exact_matches=len(common),missing_output_stamps=missing.tolist(),
        diagnostic_publish_contiguous=bool(np.all(np.diff(x['publish_seq'].astype(np.int64))==1)),
        ulog_dropout_count=len(log.dropouts),ulog_corrupt=bool(log.file_corruption),
        modes={k:np.unique(x[k]).tolist() for k in ('effective_mode','effective_axes','inner_mode','inner_axes','inner_divisor','fault','sta_fault')},
        exact_downstream_existing_v03_policy=exact_output_match(d,a,'attitude_timestamp',[(f'q_sp[{i}]',f'q_d[{i}]') for i in range(4)],start,end),
        missing_neighbors=[])
    for stamp in missing:
        j=int(np.searchsorted(source,stamp));i=int(np.searchsorted(wanted,stamp))
        evidence['missing_neighbors'].append(dict(stamp=int(stamp),diagnostic_index=i,
            diagnostic_publish=int(x['timestamp'][i]),sample=int(x['timestamp_sample'][i]),
            neighboring_recorded_stamps=source[max(0,j-2):j+2].tolist(),
            neighboring_diagnostic_stamps=wanted[max(0,i-2):i+3].tolist()))
    evidence['interpretation']='Task checker demanded100% attitude output while V03 downstream policy is bounded exact partial overlap. Missing row is not recreated; historical failed run stays failed. Queue1 overwrite is possible, not a measured scheduler cause.'
    return evidence

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result=audit(args.run)
    with args.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result,indent=2))
