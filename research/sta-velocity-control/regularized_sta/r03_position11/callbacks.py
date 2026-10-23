"""Audited velocity-callback clocks and single-publisher output group joins.

Not a universal timestamp exemption. Controller identity is publish_seq plus
strict sample time; output groups need equal multiplicity, preserved order and
exact payload equality. Missing/ambiguous group members fail closed.
"""
import importlib.util
from pathlib import Path
import numpy as np

spec=importlib.util.spec_from_file_location('_callback11_policy',Path(__file__).with_name('policy.py'))
policy=importlib.util.module_from_spec(spec); spec.loader.exec_module(policy)


def publication(values):
    t=policy.clock(values)
    if np.any(np.diff(t)<0): raise ValueError('Backward callback publication')
    return t


def sample(values):
    t=policy.clock(values)
    if np.any(np.diff(t)<=0): raise ValueError('Repeated/backward callback sample')
    return t


def callback_clock(name,values):
    if name=='timestamp_sample': return sample(values)
    if name not in ('timestamp','input_timestamp'): raise ValueError('Clock outside callback whitelist')
    return publication(values)


def validate(d):
    t=publication(d['timestamp']); s=sample(d['timestamp_sample']); i=publication(d['input_timestamp'])
    seq=np.asarray(d['publish_seq'])
    if (any(np.asarray(v).shape!=t.shape for v in d.values()) or seq.dtype.kind not in 'iu'
            or np.any(np.diff(seq.astype(np.int64))!=1)):
        raise ValueError('Invalid callback columns/sequence')
    if np.any(s>i) or np.any(i>t): raise ValueError('Future callback clock')
    return t,s


def grouped_indices(wanted,source):
    """Exact whole groups in single-publisher log order; no dedup or sorting."""
    a,b=publication(wanted),publication(source)
    # np.unique identifies boundaries only; ALL original row indices survive.
    ak,ai,ac=np.unique(a,return_index=True,return_counts=True)
    bk,bi,bc=np.unique(b,return_index=True,return_counts=True)
    _,x,y=np.intersect1d(ak,bk,return_indices=True)
    if np.any(ac[x]!=bc[y]): raise ValueError('Incomplete/ambiguous same-publication output group')
    left=np.concatenate([np.arange(ai[i],ai[i]+ac[i]) for i in x]) if len(x) else np.array([],dtype=int)
    right=np.concatenate([np.arange(bi[i],bi[i]+bc[i]) for i in y]) if len(y) else np.array([],dtype=int)
    return left,right


def exact_output_match(d,output,dtime,pairs,start,end):
    if dtime not in ('output_timestamp','attitude_timestamp'): raise ValueError('Output key outside velocity whitelist')
    validate(d); publication(output['timestamp'])
    if any(np.asarray(v).shape!=np.asarray(output['timestamp']).shape for v in output.values()):
        raise ValueError('Invalid output columns')
    m=(d['timestamp']>=start)&(d['timestamp']<end)
    keys=d[dtime][m]; a,b=grouped_indices(keys,output['timestamp'])
    common=keys[a]; coverage=len(common)/len(keys) if len(keys) else 0
    gap=np.max(np.diff(common.astype(np.int64)))*1e-6 if len(common)>1 else float('inf')
    if coverage<.8 or gap>.25: raise ValueError('Insufficient downstream exact coverage '+dtime)
    maximum=0.
    for left,right in pairs:
        x,y=d[left][m][a],output[right][b]
        if not np.array_equal(x,y,equal_nan=True): raise ValueError('Published output differs '+left)
        finite=np.isfinite(x)&np.isfinite(y)
        if np.any(finite): maximum=max(maximum,float(np.abs(x[finite]-y[finite]).max()))
    return dict(matched=len(common),denominator=len(keys),coverage=coverage,max_gap_s=float(gap),max_abs_error=maximum)


def yaw_previous(target,queries,max_age_us=20000):
    """All candidate yaw values must agree; this is not a consumption proof."""
    p=publication(target['timestamp']); q=policy.clock(queries)
    last=np.searchsorted(p,q,side='right')-1
    if np.any(last<0): raise ValueError('Missing previous yaw target')
    age=q-p[last]
    if np.any(age>max_age_us): raise ValueError('Stale yaw target')
    yaw=np.asarray(target['yaw_body'])
    if yaw.shape!=p.shape or not np.all(np.isfinite(yaw)): raise ValueError('Invalid yaw target')
    # Check every whole group globally, including the first/boundary member.
    tied=np.flatnonzero(np.diff(p)==0)
    if np.any(yaw[tied]!=yaw[tied+1]): raise ValueError('Ambiguous same-publication yaw target')
    return last,age
