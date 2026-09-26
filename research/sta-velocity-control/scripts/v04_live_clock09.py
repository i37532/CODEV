"""Protocol09 live heading checks; no flight, deduplication or new tolerances.

The newest publication group in a growing ULog is unsealed. A strictly later
attitude publication seals the preceding group (under the checked monotonic
publisher contract). Replay the entire reference-to-watermark history on each
poll; retained tail rows are checked as soon as sealed, never discarded.
The final complete ULog uses the complete closed flight window, not this tail.
"""
import numpy as np
from v04_attitude_clock09 import AttitudeClockPolicy
from v04_heading_stream import data, row, replay as heading_replay


def sealed_time(log):
    policy=AttitudeClockPolicy()
    a=policy.data(log)
    pos=data(log,'vehicle_local_position')
    # Integer publication time strictly before the latest (possibly partial) group.
    latest=int(a['timestamp'][-1])
    valid=np.flatnonzero(pos['timestamp'] < latest)
    if not len(valid):
        raise ValueError('No sealed attitude/position watermark')
    return int(pos['timestamp'][valid[-1]])


def reference_row(log):
    t=sealed_time(log)
    p=data(log,'vehicle_local_position')
    return row(p,int(np.searchsorted(p['timestamp'],t)))


def replay(log, ref, end=None, frozen=None, allow_pending=False):
    policy=AttitudeClockPolicy()
    sealed=sealed_time(log)
    if end is not None and end > sealed:
        raise ValueError('Requested live interval includes unsealed attitude group')
    stop=sealed if end is None else end
    result=heading_replay(log,ref,end=stop,frozen=frozen,
                          allow_pending=allow_pending,attitude_policy=policy)
    a=policy.data(log)
    ix=policy.window(a,ref['position']['timestamp'],stop)
    # Same existing 15-degree safety limit, all rows including tied boundary group.
    q1,q2=a['q[1]'][ix],a['q[2]'][ix]
    tilt=np.rad2deg(np.arccos(np.clip(1-2*(q1*q1+q2*q2),-1,1)))
    if np.any(tilt > 15):
        raise ValueError('Live attitude tilt exceeds existing 15 deg bound')
    result['clock09']=dict(sealed_through_us=stop,
        unsealed_publish_us=int(a['timestamp'][-1]),checked_attitude_records=len(ix),
        max_tilt_deg=float(tilt.max()),consumed_attitude_proven=False)
    return result
