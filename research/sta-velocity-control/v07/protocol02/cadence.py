"""Strict recorded update/hold checks. No interpolation, dedup or inferred modes."""
import numpy as np
from analyze_v03 import vector

def aligned(d,selection):
    seq=d['publish_seq']; j=np.searchsorted(selection['publish_seq'],seq)
    if np.any(j>=len(selection['publish_seq'])) or not np.array_equal(selection['publish_seq'][j],seq):
        raise ValueError('Missing paired cadence publication')
    q={k:v[j] for k,v in selection.items()}
    for key in ('timestamp_sample','input_timestamp','pid_calls','enabled','armed','effective_mode','effective_axes'):
        if not np.array_equal(q[key],d[key]): raise ValueError('Cadence alignment '+key)
    return q

def check(x,q,job,steady=False):
    n=job['divisor']; mode=job['mode']; tm=x['timestamp_sample'].astype(np.int64)
    for key,value in dict(div_req=n,div_eff=n,div_pending=0,div_reject=0,control_fault=0,clock=1).items():
        if np.any(q[key]!=value): raise ValueError('Cadence '+key)
    enabled=x['enabled'].astype(bool); updated=q['control_updated'].astype(bool); held=q['control_held'].astype(bool)
    if np.any((updated|held)!=enabled) or np.any(updated&held): raise ValueError('Invalid update/hold ownership')
    if np.any(np.diff(q['control_seq'].astype(np.int64))!=updated[1:].astype(int)):
        raise ValueError('True update sequence gap')
    steps=np.flatnonzero(updated)
    if len(steps)<2: raise ValueError('No true updates')
    if steady and np.any(np.diff(steps)!=n): raise ValueError('Wrong steady update count')
    if n==1:
        if np.any(held) or not np.allclose(q['h'][updated],x['used_dt'][updated],atol=1e-7,rtol=0):
            raise ValueError('DIV1 legacy dt changed')
    else:
        h=np.diff(tm[steps])*1e-6
        continuous=np.array([np.all(enabled[a:b+1]) for a,b in zip(steps[:-1],steps[1:])])
        if not np.allclose(q['h'][steps[1:]][continuous],h[continuous],atol=1e-7,rtol=0):
            raise ValueError('Not real sensor update h')
        if not np.all(np.isnan(q['h'][held])): raise ValueError('Held step claims integration h')
    for name in ('path_ns','module_ns'):
        if not np.all(q[name][enabled]>0): raise ValueError('Unavailable host clock '+name)
    # Current raw FF is combined with the retained PRE-FF correction exactly once.
    c=vector(q,'correction'); ff=vector(x,'a_ff')
    expected=np.where(np.isfinite(c),np.where(np.isfinite(ff),ff,0)+c,ff)
    if not np.allclose(vector(x,'a_req')[enabled],expected[enabled],atol=2e-6,rtol=0):
        raise ValueError('Correction/FF cache mismatch')
    indices=np.flatnonzero(held); indices=indices[indices>0]
    integ=vector(q,'integral')
    if len(indices):
        if not np.array_equal(c[indices,:2],c[indices-1,:2],equal_nan=True): raise ValueError('Held XY correction changed')
        if not np.array_equal(integ[indices,:2],integ[indices-1,:2]): raise ValueError('Held XY integrated')
        shift=(x['hover_thrust'][indices]-x['hover_thrust'][indices-1])*(9.80665/x['hover_thrust'][indices])
        if not np.allclose(integ[indices,2]-integ[indices-1,2],shift,atol=2e-6,rtol=0): raise ValueError('Held PID HTE/integration')
        if not np.allclose(c[indices,2]-c[indices-1,2],shift,atol=2e-6,rtol=0): raise ValueError('HTE cache not synchronized')
    if np.any(x['z_phase']) or np.any(x['z_hte_shift']): raise ValueError('Z ESTA was not authorized')
    if mode:
        active=x['active_axes']==3; commits=x['committed_axes']==3
        if np.any((x['committed_axes']!=0)&~commits) or np.any(commits&~updated): raise ValueError('Partial/held nu commit')
        if steady and (not np.all(active) or not np.array_equal(commits,updated)):
            raise ValueError('Wrong active/committed axes')
        if steady and np.any(x['pid_axes']!=4): raise ValueError('XY ESTA calculated idle horizontal PID')
        if steady and np.any(x['sta_flags'].astype(int)&(1|2|4|64|128)): raise ValueError('Unexpected steady reset/priming/latch')
        if steady and not np.array_equal((x['sta_flags'].astype(int)&256)!=0,held): raise ValueError('Wrong held-candidate flag')
        for axis in (0,1):
            before=x[f'nu_before[{axis}]']; applied=x[f'nu_applied[{axis}]']; ideal=x[f'nu_ideal[{axis}]']; a=x[f'a_sta[{axis}]']; s=x[f's[{axis}]']
            if np.any(abs(applied[enabled])>.400001): raise ValueError('nu limit')
            if not np.all(np.isfinite(applied[enabled])): raise ValueError('Nonfinite nu')
            if len(indices) and not np.array_equal(applied[indices],applied[indices-1]): raise ValueError('Hold integrated nu')
            if np.any(commits):
                h=q['h'] if n>1 else x['raw_dt']
                raw=-np.sqrt(abs(s))*np.sign(s)+before
                if not np.allclose(a[commits],raw[commits],atol=2e-6,rtol=0): raise ValueError('Wrong old-nu output')
                if not np.allclose(ideal[commits],(before-h*.2*np.sign(s))[commits],atol=2e-7,rtol=0): raise ValueError('Wrong nu candidate h')
                if not np.allclose(c[commits,axis],np.clip(raw[commits],-.8,.8),atol=2e-6,rtol=0): raise ValueError('Applied correction limit')
                next_nu=np.clip(ideal,-.4,.4); delta=next_nu-before
                constrained=x['constraint_bits']!=0
                outward=(delta*(raw-np.clip(raw,-.8,.8))>0)|(constrained&(delta*(x[f'a_req[{axis}]']-x[f'a_proxy[{axis}]'])>0))
                if n>1:
                    pos=np.r_[0,q['interval_pos'][:-1]].astype(int); neg=np.r_[0,q['interval_neg'][:-1]].astype(int)
                    outward|=((delta>0)&((pos&(1<<axis))!=0))|((delta<0)&((neg&(1<<axis))!=0))
                next_nu=np.where(outward,before,next_nu)
                if not np.allclose(applied[commits],next_nu[commits],atol=2e-7,rtol=0): raise ValueError('Protected interval state mismatch')
            if n>1 and np.any(held&active):
                if not np.all(np.isnan(a[held&active])) or not np.all(np.isnan(ideal[held&active])):
                    raise ValueError('Hold claims ideal candidate')
            if steady and not np.array_equal(before[1:],applied[:-1]): raise ValueError('Stale state or cross-axis contamination')
        for name in ('nu_before','nu_ideal','nu_applied','a_sta'):
            if not np.all(np.isnan(x[f'{name}[2]'])): raise ValueError('STA state on Z PID')
    else:
        if steady and np.any(x['pid_axes']!=7): raise ValueError('Wrong PID axes')
        for name in ('nu_before','nu_ideal','nu_applied','a_sta'):
            if not np.all(np.isnan(vector(x,name))): raise ValueError('STA state on PID')
    return dict(updates=int(updated.sum()),holds=int(held.sum()),update_hz=(len(steps)-1)/((tm[steps[-1]]-tm[steps[0]])*1e-6),
                h_min=float(q['h'][updated].min()),h_max=float(q['h'][updated].max()),
                host_cost={name:{phase:{k:float(v) for k,v in zip(('median','p95','p99','max'),np.percentile(q[name][mask]*1e-3,[50,95,99,100]))}
                    for phase,mask in [('update',updated),('hold',held)] if np.any(mask)} for name in ('path_ns','module_ns')},
                host_us_per_sim_second={name:float(q[name][enabled].sum()*1e-3/((tm[-1]-tm[0])*1e-6)) for name in ('path_ns','module_ns')})

def check_pid_path(d,q,job,parameters):
    """Independent binary64 reconstruction on the steady observation window."""
    integral=vector(q,'integral'); before=integral[:-1].copy()
    before[:,2]+=(d['hover_thrust'][1:]-d['hover_thrust'][:-1])*(9.80665/d['hover_thrust'][1:])
    updated=q['control_updated'][1:].astype(bool); steps=np.flatnonzero(updated)
    correction=vector(q,'correction')[1:]; error=-vector(d,'s')[1:]
    for axis in ((2,) if job['mode'] else (0,1,2)):
        group='XY' if axis<2 else 'Z'
        kp,ki,kd=[parameters[f'MPC_{group}_VEL_{name}_ACC'] for name in ('P','I','D')]
        expected=error[:,axis]*kp+before[:,axis]-d[f'v_dot[{axis}]'][1:]*kd
        if not np.allclose(correction[steps,axis],expected[steps],atol=3e-6,rtol=0): raise ValueError('PID correction reconstruction')
        e=error[:,axis].copy()
        if axis<2: e-=2./kp*(d[f'a_req[{axis}]'][1:]-d[f'a_proxy[{axis}]'][1:])
        else:
            thrust=d['thrust[2]'][1:]
            e=np.where(((thrust>=-d['thrust_min'][1:])&(e>=0))|((thrust<=-d['thrust_max'][1:])&(e<=0)),0.,e)
        if job['divisor']>1:
            frozen=((q['interval_pos'][:-1].astype(int)|q['interval_neg'][:-1].astype(int))&(1<<axis))!=0
            e=np.where(frozen,0.,e)
        post=before[:,axis].copy(); post[updated]+=e[updated]*ki*q['h'][1:][updated]
        if axis==2: post=np.clip(post,-9.80665,9.80665)
        if not np.allclose(integral[1:,axis],post,atol=3e-6,rtol=0): raise ValueError('PID state reconstruction')
    return dict(samples=len(integral)-1,updates=len(steps),axes=[2] if job['mode'] else [0,1,2],reference='independent binary64, actual consumed error/derivative/HTE and interval constraints')
