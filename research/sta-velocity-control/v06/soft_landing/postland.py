"""Read-only tail collection after auto-disarm; no extrapolation or relaxed checks."""
import io
import time
from pathlib import Path
import numpy as np
from pyulog import ULog
from landing_health import check_health
from v04_heading_stream import complete_prefix

TOPICS={'sensor_accel':3,'vehicle_imu':3,'estimator_status':6,'estimator_selector_status':1}


def complete_tail(log,start,end):
    pending=[]
    for name,count in TOPICS.items():
        for i in range(count):
            # Missing topic/start is not a late post-disarm boundary.
            d=log.get_dataset(name,i).data; t=d['timestamp'].astype(np.int64)
            if not len(t) or np.any(t<=0) or np.any(np.diff(t)<=0) or t[0]>start:
                raise ValueError('Invalid pre-existing health timeline')
            if t[-1]<end: pending.append(f'{name}:{i}')
    return pending


def read(path):
    path=Path(path)
    if path.stat().st_size>128*1024*1024: raise ValueError('Oversized tail log')
    log=ULog(io.BytesIO(complete_prefix(path.read_bytes())),message_name_filter_list=list(TOPICS))
    if log.dropouts or log.file_corruption: raise ValueError('Corrupt tail log')
    return log


def collect(reader, ground_state, start, end, *, now=time.monotonic, sleep=time.sleep):
    deadline=now()+15.; snapshots=[]
    while now()<deadline:
        state=ground_state()
        if state.get('arming_state')!=1 or not state.get('landed') or state.get('failsafe'):
            raise ValueError('No longer safely disarmed during log tail')
        log=reader(); pending=complete_tail(log,start,end)
        snapshots.append(dict(pending=pending))
        if not pending:
            return dict(landing_start_us=int(start),landed_disarmed_us=int(end),
                        snapshots=snapshots,health=check_health(log,start,end))
        sleep(.2)
    raise TimeoutError('Post-disarm health boundary not collected in15s')
