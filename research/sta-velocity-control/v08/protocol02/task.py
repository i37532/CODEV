"""Independent double precision task reference and recorded-input checks."""
import numpy as np

def consumed_targets(src,x):
    """Exact recorded consumption, not latest target before position acquisition.

    No nearest-neighbour fallback, dedup or output-based choice among same-time
    messages. The topic must be strictly ordered and the consumed stamp unique.
    """
    keys=('timestamp','input_timestamp','setpoint_timestamp')
    clocks=[np.asarray(src['timestamp'])]+[np.asarray(x[k]) for k in keys]
    for t in clocks:
        if t.ndim!=1 or not len(t) or np.any(~np.isfinite(t)) or np.any(t<=0) or np.any(t!=np.floor(t)):
            raise ValueError('Invalid task clock')
    s,p,i,c=[t.astype(np.int64) for t in clocks]
    if not (len(p)==len(i)==len(c)) or np.any(np.diff(s)<=0) or np.any(np.diff(p)<=0) or np.any(np.diff(i)<=0) or np.any(np.diff(c)<0):
        raise ValueError('Ambiguous/reversed consumed task clock')
    if np.any(i>p) or np.any(c>p):raise ValueError('Future task source')
    age=p-c
    if np.any(age>40000):raise ValueError('Stale consumed task source')
    j=np.searchsorted(s,c)
    if np.any(j>=len(s)) or not np.array_equal(s[j],c):raise ValueError('Missing exact consumed task source')
    return j,age

def offsets(mode,t):
    t=np.asarray(t,dtype=float); active=(t>0)&(t<64)
    u=np.where(active,t,0); b=np.pi/64; w=2*np.pi/32
    q=np.sin(b*u); c=np.cos(b*u); e=q**4; ed=4*b*q**3*c; edd=4*b*b*(3*q*q*c*c-q**4)
    p=np.zeros((t.size,2)); v=p.copy(); a=p.copy(); yaw=np.zeros(t.size); yr=yaw.copy()
    if mode in (6,7):
        for i,amp in enumerate((.5,.25)):
            k=(i+1)*w; s=np.sin(k*u); co=np.cos(k*u)
            p[:,i]=amp*e*s; v[:,i]=amp*(ed*s+e*k*co); a[:,i]=amp*(edd*s+2*ed*k*co-e*k*k*s)
        if mode==7: yaw=np.pi/6*e*np.sin(w*u); yr=np.pi/6*(ed*np.sin(w*u)+e*w*np.cos(w*u))
    return dict(p=p,v=v,a=a,yaw=yaw,yaw_rate=yr)

def check_targets(u,d,events,job):
    m=(d['timestamp']>=events['hover_start'])&(d['timestamp']<events['hover_end']); x={k:v[m] for k,v in d.items()}
    if len(x['timestamp'])<8900: raise ValueError('Missing task target interval')
    mode=job['parameters']['MPC_VCT_TEST']; expected={'hover':5,'figure8':6,'heading':7}
    if expected.get(job['task'])!=mode: raise ValueError('Wrong task configuration')
    o=offsets(mode,x['excitation_time']); src=u.get_dataset('trajectory_setpoint').data
    j,age=consumed_targets(src,x)
    maximum={}
    for field,keys,add in [('p_sp',('x','y'),o['p']),('v_ff',('vx','vy'),o['v']),('a_ff',('acceleration[0]','acceleration[1]'),o['a'])]:
        errors=[]
        for i,key in enumerate(keys):
            original=src[key][j].astype(float)
            if field!='p_sp': original=np.where(np.isfinite(original),original,0.)
            actual=x[f'{field}[{i}]']
            if not np.all(np.isfinite(actual)) or not np.all(np.isfinite(original)): raise ValueError('Nonfinite task target')
            err=np.max(abs(actual-(original+add[:,i]))); errors.append(float(err))
            if err>2e-6: raise ValueError('Task target/FF not once '+field)
        maximum[field]=errors
    if not np.all(np.isfinite(x['p_sp[2]'])) or not np.all(np.isfinite(src['z'][j])) or np.any(abs(x['p_sp[2]']-src['z'][j])>2e-6): raise ValueError('Task changed Z target')
    attitude=u.get_dataset('vehicle_attitude_setpoint').data
    ai=np.searchsorted(attitude['timestamp'],x['attitude_timestamp'])
    if np.any(ai>=len(attitude['timestamp'])) or not np.array_equal(attitude['timestamp'][ai],x['attitude_timestamp']): raise ValueError('Missing attitude task output')
    yaw=src['yaw'][j]+o['yaw']; err=np.angle(np.exp(1j*(attitude['yaw_body'][ai]-yaw)))
    if not np.all(np.isfinite(err)) or np.max(abs(err))>2e-6: raise ValueError('Wrong applied heading target')
    # Module publishes yawspeed as yaw_sp_move_rate, before body-frame attitude conversion.
    base_rate=np.where(np.isfinite(src['yawspeed'][j]),src['yawspeed'][j],0.)
    if not np.all(np.isfinite(attitude['yaw_sp_move_rate'][ai])) or np.max(abs(attitude['yaw_sp_move_rate'][ai]-(base_rate+o['yaw_rate'])))>2e-6: raise ValueError('Wrong heading-rate FF')
    active=(x['excitation_time']>=0)&(x['excitation_time']<64)
    if active.sum()<6390 or x['excitation_time'][0]>=0 or x['excitation_time'][-1]<64: raise ValueError('Incomplete task clock')
    if mode!=5 and np.max(np.linalg.norm(o['p'],axis=1))<.25: raise ValueError('Missing figure8')
    if mode==7 and np.max(abs(o['yaw']))<.3: raise ValueError('Missing heading task')
    return dict(task=job['task'],samples=len(j),maximum_target_error=maximum,max_source_age_us=int(age.max()),
        source_association='exact diagnostic.setpoint_timestamp; unique raw trajectory timestamp; bounded by diagnostic publication',
        source_after_position_samples=int(np.count_nonzero(src['timestamp'][j]>x['input_timestamp'])),
        reference_displacement_max=float(np.max(np.linalg.norm(o['p'],axis=1))),reference_speed_max=float(np.max(np.linalg.norm(o['v'],axis=1))),
        heading_addition_max=float(np.max(abs(o['yaw']))),yaw_request_error_max=float(np.max(abs(err))),
        source='Navigator/FlightTask base + per-frame SITL adapter; original position P remains active')
