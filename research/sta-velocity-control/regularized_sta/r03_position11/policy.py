"""Opt-in position publication/sample policy; no controller or ULog mutation.

The public position and its queued copy, plus the two explicitly named velocity
callback diagnostics, are whitelisted. Publication time is nondecreasing; sample identity is strictly
increasing. Original records, values and ordering are never discarded. Exact
consumption uses BOTH recorded clocks, never an arbitrary member of a tie.
"""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from pyulog import ULog as RawULog

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parents[1]
spec = importlib.util.spec_from_file_location('_position11_original_view', RESEARCH/'v08/protocol02/position_log.py')
legacy = importlib.util.module_from_spec(spec); spec.loader.exec_module(legacy)
POSITION_FIELDS = legacy.POSITION_FIELDS
TOPIC = legacy.TOPIC
RESET_FIELDS = ('xy_reset_counter','z_reset_counter','vxy_reset_counter','vz_reset_counter','heading_reset_counter')
REFERENCE_FIELDS = ('ref_timestamp','ref_lat','ref_lon','ref_alt')


def clock(value):
    x = np.asarray(value)
    if x.ndim != 1 or not len(x) or x.dtype.kind not in 'iu' or np.any(x <= 0) or int(x.max()) > 2**63-1:
        raise ValueError('Position clock must be positive int64-range integers')
    return x.astype(np.int64)


def validate(d):
    p, s = clock(d['timestamp']), clock(d['timestamp_sample'])
    if p.shape != s.shape or any(np.asarray(v).shape != p.shape for v in d.values()):
        raise ValueError('Invalid position column lengths')
    if np.any(np.diff(p) < 0): raise ValueError('Backward position publication')
    if np.any(np.diff(s) <= 0): raise ValueError('Repeated/backward position sample')
    if np.any(s > p): raise ValueError('Future position sample')
    return p, s


def exact_indices(d, publication, sample):
    """Search the unique sample, then require its publication clock verbatim."""
    p, s = validate(d)
    q, r = clock(publication), clock(sample)
    if q.shape != r.shape: raise ValueError('Mismatched composite position key')
    i = np.searchsorted(s, r)
    if np.any(i >= len(s)) or not np.array_equal(s[i], r) or not np.array_equal(p[i], q):
        raise ValueError('Missing exact position publication/sample pair')
    return i


def unique_at(d, publication, sample=None):
    p, _ = validate(d)
    left, right = np.searchsorted(p, publication, side='left'), np.searchsorted(p, publication, side='right')
    if sample is not None:
        return int(exact_indices(d, [publication], [sample])[0])
    if right-left != 1: raise ValueError('Ambiguous/missing position publication without sample key')
    return int(left)


def window(d, start, end, *, predecessor=True):
    """All boundary rows and full previous group, never a last-row shortcut."""
    p, s = validate(d)
    if not 0 < start <= end or end > p[-1]: raise ValueError('Invalid position interval')
    first = int(np.searchsorted(p, start, side='left'))
    stop = int(np.searchsorted(p, end, side='right'))
    if predecessor:
        if first == 0: raise ValueError('Missing position boundary predecessor')
        first = int(np.searchsorted(p, p[first-1], side='left'))
    ix = np.arange(first, stop)
    if len(ix) < 2 or not np.any(p[ix] >= start): raise ValueError('Missing position interval')
    for t in (p, s):
        if np.any(np.diff(t[ix]) > 40000): raise ValueError('Position/sample gap')
    if start-s[ix[0]] > 40000 or end-s[ix[-1]] > 40000:
        raise ValueError('Stale position interval boundary')
    return ix


def reference_window(d, reference, end):
    """Observe the opening reset edge before preserving original heading replay."""
    start = reference['timestamp']
    reference_index = unique_at(d, start, reference['timestamp_sample'])
    # A prearm anchor must be a complete unique publication. A same-time
    # prearm reset cannot be made harmless by selecting its last sample.
    unique_at(d, start)
    ix = window(d, start, end)
    opening = ix[d['timestamp'][ix] <= start]
    for key in RESET_FIELDS+REFERENCE_FIELDS:
        if not np.all(np.isfinite(d[key][opening])) or np.any(d[key][opening] != reference[key]):
            raise ValueError('Position opening reset/reference edge '+key)
    for key in ('xy_valid','z_valid','v_xy_valid','v_z_valid'):
        if not np.all(d[key][ix]): raise ValueError('Invalid position boundary estimate '+key)
    return np.arange(reference_index, ix[-1]+1)


def checked(raw):
    mirror = raw.get_dataset(TOPIC, multi_instance=0).data
    original = raw.get_dataset('vehicle_local_position', multi_instance=0).data
    if raw.dropouts or getattr(raw, 'file_corruption', False):
        raise ValueError('Position log transport dropout/corruption')
    for d in (original, mirror):
        if set(POSITION_FIELDS)-set(d): raise ValueError('Missing position payload fields')
        validate(d)
    seq = np.asarray(mirror.get('log_seq', []))
    if (seq.shape != np.asarray(mirror['timestamp']).shape or seq.dtype.kind not in 'iu'
            or np.any(seq < 0) or np.any(seq > 0xffffffff)
            or np.any(np.diff(seq.astype(np.int64)) % 2**32 != 1)):
        raise ValueError('Position log sequence gap/reset')
    p, s = validate(mirror); op, os = validate(original)
    # In a live snapshot either transport can end within a publication group.
    # Compare every complete overlapping sample; only boundary tails may be
    # pending. Sequence continuity and sealed-window checks still apply.
    indices = np.flatnonzero((os >= s[0]) & (os <= s[-1]))
    if not len(indices): raise ValueError('Missing original/mirror overlap')
    j = exact_indices(mirror, op[indices], os[indices])
    for key in POSITION_FIELDS:
        a, b = np.asarray(original[key][indices]), np.asarray(mirror[key][j])
        if a.dtype != b.dtype or a.tobytes() != b.tobytes():
            raise ValueError('Position log payload mismatch '+key)
    diag = raw.get_dataset('sta_velocity_ctrl_status').data
    dp, ds = clock(diag['input_timestamp']), clock(diag['timestamp_sample'])
    if dp.shape != ds.shape: raise ValueError('Invalid consumed position key lengths')
    in_window = (ds >= s[0]) & (ds <= s[-1])
    if np.any(in_window): exact_indices(mirror, dp[in_window], ds[in_window])
    # A consumer cannot hide an interior hole by supplying an outside sample.
    interior = (dp > p[0]) & (dp < p[-1])
    if np.any(interior & ~in_window): raise ValueError('Consumed position sample outside interior clock range')
    evidence = dict(source_topic=TOPIC,control_topic_unchanged=True,queue_length=32,
        records=len(p),sequence_first=int(seq[0]),sequence_last=int(seq[-1]),sequence_gaps=0,
        raw_overlap_records=len(indices),raw_missing_records=int(len(p)-len(indices)),
        consumed_records=int(in_window.sum()),publication_end_us=int(p[-1]),
        no_interpolation=True,no_deduplication=True,raw_records_preserved=True,
        clock_policy='position11',association_key=['timestamp','timestamp_sample'],
        equal_publications=int(np.count_nonzero(np.diff(p)==0)),sample_end_us=int(s[-1]),
        raw_boundary_tail_records=int(np.count_nonzero(os>s[-1])),
        consumed_boundary_tail_records=int(np.count_nonzero(ds>s[-1])))
    return SimpleNamespace(name=TOPIC,multi_id=0,data={k:mirror[k] for k in POSITION_FIELDS}), evidence


class PositionLogView(legacy.PositionLogView):
    def get_dataset(self,name,multi_instance=0):
        if name == 'vehicle_local_position' and multi_instance == 0:
            if self._position is None: self._position,self.position_log_evidence=checked(self.raw)
            return self._position
        return self.raw.get_dataset(name,multi_instance=multi_instance)


def ULog(*args,**kwargs):
    return PositionLogView(RawULog(*args,**kwargs))


def data(log,name,instance=0):
    d=log.get_dataset(name,instance).data
    if name == 'vehicle_local_position':
        if instance != 0: raise ValueError('Position whitelist is public instance 0 only')
        validate(d)
    elif name in ('sta_velocity_ctrl_status','velocity_ctrl_selection') and instance==0:
        # Explicit callback identity, not a blanket sampled-topic relaxation.
        p,s=validate(d); inp=clock(d['input_timestamp']); seq=np.asarray(d['publish_seq'])
        if (seq.dtype.kind not in 'iu' or np.any(np.diff(seq.astype(np.int64))!=1)
                or np.any(s>inp) or np.any(inp>p) or np.any(np.diff(inp)<0)):
            raise ValueError('Invalid velocity callback identity/clock')
    else:
        t=clock(d['timestamp'])
        if np.any(np.diff(t)<=0): raise ValueError('Empty/nonmonotonic '+name)
    return d
