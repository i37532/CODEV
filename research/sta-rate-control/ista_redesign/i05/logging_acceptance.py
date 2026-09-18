"""Amended finite-sample actuator evidence; never infers unlogged outputs."""
import numpy as np


def check(condition, reason):
    if not condition:
        raise ValueError(reason)


def validate(d, a, masks, divisor, commanded):
    t=d['timestamp_sample'].astype(np.int64); at=a['timestamp_sample'].astype(np.int64)
    check(np.all(np.diff(t)>0) and np.all(np.diff(at)>0),'Duplicate or reversed timestamps')
    common,si,ai=np.intersect1d(t,at,return_indices=True)
    valid=d['output_valid'].astype(bool)
    flight=masks['flight']
    check(np.any(flight),'Empty flight window')
    ft=t[flight]; am=(at>=ft[0])&(at<=ft[-1])
    check(np.all(np.isin(at[am],t[flight&valid])),'Unmatched actuator timestamp in flight')
    keep=flight[si]&valid[si]; fi,fai=si[keep],ai[keep]
    check(len(fi)>0,'No comparable actuator samples')
    expected=np.column_stack([d[f'c_applied[{i}]'] for i in range(3)]+[d['thrust']]).astype(np.float32)
    actual=np.column_stack([a[f'control[{i}]'] for i in range(4)]).astype(np.float32)
    check(np.all(np.isfinite(expected[fi])) and np.all(np.isfinite(actual[fai])),'Nonfinite matched actuator values')
    check(np.array_equal(expected[fi].view(np.uint32),actual[fai].view(np.uint32)),'Matched torque/thrust mismatch')
    updated=d['updated'].astype(bool); held=d['held'].astype(bool)
    check(np.count_nonzero(updated[si])>10000/divisor,'Insufficient full-run actuator update evidence')
    matched=np.isin(t,common)
    def counts(mask):
        n=int(mask.sum()); missing=int(np.count_nonzero(mask&~matched))
        return dict(total=n,matched=n-missing,missing=missing,missing_fraction=missing/n if n else None)
    report={}
    for name,mask in masks.items():
        mask=mask&valid
        check(np.any(mask&matched&updated),'No matched updates in '+name)
        if divisor>1:check(np.any(mask&matched&held),'No matched held samples in '+name)
        present=t[mask&matched]
        entry=dict(callbacks=counts(mask),updates=counts(mask&updated),held=counts(mask&held),
                   maximum_logged_gap_us=int(np.diff(present).max()) if len(present)>1 else None,excitation={})
        for axis in commanded.get(name,()):
            field=('research_roll_addition','research_pitch_addition','research_yaw_addition')[axis]
            for sign,label in [(1,'positive'),(-1,'negative')]:
                segment=mask&(sign*d[field]>0)
                check(np.any(segment&matched),'No matched '+label+' excitation in '+name)
                entry['excitation'][str(axis)+'_'+label]=dict(callbacks=counts(segment),
                    updates=counts(segment&updated),held=counts(segment&held))
        report[name]=entry
    return dict(protocol='amended-v1',matched_torque_thrust_bitwise_equal=True,windows=report,
                limitation='Consistency of recorded samples only; no full publication coverage claim')
