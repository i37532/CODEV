"""Read-only full-file diagnosis; expected rejection is not flight acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from pyulog import ULog
from v04_live_clock09 import replay

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=False)
    files=sorted(p for p in args.run.rglob('*') if p.is_file())
    before={str(p):sha(p) for p in files}
    record=json.loads((args.run/'result.json').read_text())
    paths=sorted(args.run.glob('*.ulg'),key=lambda p:p.stat().st_size)
    source=paths[-1]; u=ULog(str(source))
    assert not u.dropouts and not u.file_corruption
    ref=json.loads((args.run/'height_reference.json').read_text())
    task=json.loads((args.run/'task_yaw.json').read_text())
    pos=u.get_dataset('vehicle_local_position').data
    diag=u.get_dataset('sta_velocity_ctrl_status').data
    consumed=diag['input_timestamp']>=ref['position']['timestamp']
    missing=np.flatnonzero(consumed & ~np.isin(diag['input_timestamp'],pos['timestamp']))
    assert len(missing)==1
    i=int(missing[0]); t=int(diag['input_timestamp'][i]); assert t==99316000
    j=int(np.searchsorted(pos['timestamp'],t))
    assert int(pos['timestamp'][j])>t and int(pos['timestamp'][-1])>t
    try:
        replay(u,ref,end=int(pos['timestamp'][j+1]),frozen=task)
    except ValueError as e:
        rejection=str(e)
    else:
        raise AssertionError('Historical missing sample unexpectedly accepted')
    assert rejection=='Missing consumed local position sample',rejection
    logger=u.get_dataset('logger_status').data
    n=int(np.searchsorted(logger['timestamp'],t))
    nearby=lambda d,fields,a,b:{k:d[k][a:b].tolist() for k in fields}
    evidence=dict(diagnosis_completed=True,flight_accepted=False,new_flights=0,
        source=str(source),sha256=sha(source),bytes=source.stat().st_size,
        dropout_records=0,file_corruption=False,missing_consumed_samples=len(missing),
        missing_timestamp=t,full_file_rejection=rejection,
        diagnostic=nearby(diag,['timestamp','timestamp_sample','input_timestamp','publish_seq','update_seq','raw_dt'],i-1,i+2),
        position=nearby(pos,['timestamp','timestamp_sample','x','y','z','vx','vy','vz'],j-2,j+3),
        logger_status=nearby(logger,['timestamp','dropouts','message_gaps','buffer_used_bytes','buffer_size_bytes'],n-1,n+1),
        caution='Aggregate logger message_gaps are not per-topic attribution or exact scheduling proof.',
        original_result=record,inputs_unchanged=all(sha(Path(p))==h for p,h in before.items()))
    assert evidence['inputs_unchanged']
    (args.output/'audit.json').write_text(json.dumps(evidence,indent=2)+'\n')
    (args.output/'inputs.sha256').write_text(''.join(f'{h}  {p}\n' for p,h in before.items()))
    print(json.dumps({k:evidence[k] for k in ('diagnosis_completed','flight_accepted','missing_timestamp','inputs_unchanged')}))

if __name__=='__main__':main()
