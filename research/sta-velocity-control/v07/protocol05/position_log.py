"""Explicit read-only evidence view, never a repaired/rewritten historical ULog.

Position queries use the new queued publication-edge copy. Raw original records
remain separately accessible and are compared bit-for-bit wherever both exist.
Only new protocol03 opts in. Missing copy/sequence/consumed sample still rejects.
"""
from types import SimpleNamespace
import numpy as np
from pyulog import ULog as RawULog

POSITION_FIELDS = ["timestamp","timestamp_sample","xy_valid","z_valid","v_xy_valid","v_z_valid","x","y","z","delta_xy[0]","delta_xy[1]","xy_reset_counter","delta_z","z_reset_counter","vx","vy","vz","z_deriv","delta_vxy[0]","delta_vxy[1]","vxy_reset_counter","delta_vz","vz_reset_counter","ax","ay","az","heading","delta_heading","heading_reset_counter","xy_global","z_global","ref_timestamp","ref_lat","ref_lon","ref_alt","dist_bottom","dist_bottom_valid","dist_bottom_sensor_bitfield","eph","epv","evh","evv","vxy_max","vz_max","hagl_min","hagl_max"]
TOPIC = 'vehicle_local_position_log'


def checked(raw):
    mirror = raw.get_dataset(TOPIC, multi_instance=0).data
    original = raw.get_dataset('vehicle_local_position', multi_instance=0).data
    if raw.dropouts or getattr(raw, 'file_corruption', False):
        raise ValueError('Position log transport dropout/corruption')
    for d in (original, mirror):
        if set(POSITION_FIELDS)-set(d): raise ValueError('Missing position payload fields')
        n=len(d['timestamp'])
        if not n or any(len(v)!=n for v in d.values()): raise ValueError('Invalid position column lengths')
        for k in ('timestamp','timestamp_sample'):
            x=np.asarray(d[k])
            if not np.issubdtype(x.dtype,np.integer) or np.any(x<=0) or np.any(x[1:]<=x[:-1]):
                raise ValueError('Invalid position clock '+k)
        if np.any(d['timestamp_sample']>d['timestamp']): raise ValueError('Future position sample')
    if 'log_seq' not in mirror: raise ValueError('Missing position log sequence')
    seq=np.asarray(mirror['log_seq'])
    if (not np.issubdtype(seq.dtype,np.integer) or np.any(seq<0) or np.any(seq>0xffffffff)
            or np.any((np.diff(seq.astype(np.int64)) % 2**32)!=1)):
        raise ValueError('Position log sequence gap/reset')
    # Only complete overlap is eligible. The online mirror may have a bounded
    # transport tail; unchanged live age/watermark checks still apply to it.
    t=mirror['timestamp']; o=original['timestamp']
    indices=np.flatnonzero((o>=t[0]) & (o<=t[-1]))
    j=np.searchsorted(t,o[indices])
    if not len(indices) or not np.array_equal(t[j],o[indices]):
        raise ValueError('Original publication missing in position log')
    for key in POSITION_FIELDS:
        a=np.asarray(original[key][indices]); b=np.asarray(mirror[key][j])
        if a.dtype != b.dtype or a.tobytes()!=b.tobytes():
            raise ValueError('Position log payload mismatch '+key)
    diag=raw.get_dataset('sta_velocity_ctrl_status').data
    consumed=diag['input_timestamp']; in_window=(consumed>=t[0]) & (consumed<=t[-1])
    ci=np.searchsorted(t,consumed[in_window])
    if not np.array_equal(t[ci],consumed[in_window]): raise ValueError('Missing consumed position log sample')
    if not np.array_equal(mirror['timestamp_sample'][ci],diag['timestamp_sample'][in_window]):
        raise ValueError('Consumed position log sample clock mismatch')
    evidence=dict(source_topic=TOPIC,control_topic_unchanged=True,queue_length=32,
        records=len(t),sequence_first=int(seq[0]),sequence_last=int(seq[-1]),sequence_gaps=0,
        raw_overlap_records=len(indices),raw_missing_records=int(len(t)-len(indices)),
        consumed_records=int(in_window.sum()),publication_end_us=int(t[-1]),
        no_interpolation=True,no_deduplication=True,raw_records_preserved=True)
    return SimpleNamespace(name=TOPIC,multi_id=0,data={k:mirror[k] for k in POSITION_FIELDS}),evidence


class PositionLogView:
    def __init__(self,raw): self.raw=raw; self._position=None; self.position_log_evidence=None
    def __getattr__(self,key): return getattr(self.raw,key)
    def get_dataset(self,name,multi_instance=0):
        if name=='vehicle_local_position' and multi_instance==0:
            if self._position is None: self._position,self.position_log_evidence=checked(self.raw)
            return self._position
        return self.raw.get_dataset(name,multi_instance=multi_instance)


def ULog(*args,**kwargs):
    return PositionLogView(RawULog(*args,**kwargs))
