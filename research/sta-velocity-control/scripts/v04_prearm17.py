"""Choose a raw prearm reference with an observable sealed attitude interval.

Position and attitude publications are not phase-locked. The latest position
below the watermark need not coincide with an attitude publication. Do not
change the safety window policy to permit an empty interval.
"""
import numpy as np
from v04_attitude_clock09 import AttitudeClockPolicy
from v04_heading_stream import data, row
from v04_live_clock09 import sealed_time


def reference_row(log):
    policy=AttitudeClockPolicy()
    stop=sealed_time(log)
    attitude=policy.data(log)
    complete=np.flatnonzero(attitude['timestamp'] <= stop)
    if not len(complete):
        raise ValueError('Missing sealed attitude at prearm watermark')
    last=int(attitude['timestamp'][complete[-1]])
    position=data(log,'vehicle_local_position')
    i=int(np.searchsorted(position['timestamp'],last,side='right'))-1
    if i < 0:
        raise ValueError('No causal prearm position before sealed attitude')
    reference=row(position,i)
    # Same predecessor/all-boundary rows and original age/gap/reset rules.
    policy.window(attitude,reference['timestamp'],stop)
    return reference
