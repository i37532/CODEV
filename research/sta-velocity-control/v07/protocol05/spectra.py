"""Analysis-only ZOH resampling, never used to repair log acceptance."""
import numpy as np

def psd(values,hz):
    y=np.asarray(values,dtype=float)
    if y.ndim==1: y=y[:,None]
    if len(y)<16 or not np.all(np.isfinite(y)): raise ValueError('Short/nonfinite spectrum')
    w=np.hanning(len(y)); z=np.fft.rfft((y-y.mean(axis=0))*w[:,None],axis=0)
    p=abs(z)**2/(hz*np.sum(w*w))
    p[1:-1 if len(y)%2==0 else None]*=2
    return np.fft.rfftfreq(len(y),1/hz),p

def antialias(values):
    taps=513; k=np.arange(taps)-(taps-1)/2
    b=2*.08*np.sinc(2*.08*k)*np.blackman(taps); b/=b.sum()
    y=np.asarray(values)
    if y.ndim==1: y=y[:,None]
    if len(y)<=taps: raise ValueError('Insufficient FIR margin')
    return np.column_stack([np.convolve(y[:,i],b,mode='valid')[::4] for i in range(y.shape[1])])

def analyze(d,q):
    m=(d['excitation_time']>=0)&(d['excitation_time']<64)
    t=d['timestamp_sample'][m].astype(float)*1e-6; updated=q['control_updated'][m].astype(bool)
    if len(t)<6300 or np.any(np.diff(t)<=0) or np.max(np.diff(t))>.040001: raise ValueError('Incomplete spectral source')
    c=np.column_stack([q[f'correction[{i}]'][m] for i in range(3)])
    step_time=t[updated]; rate=(len(step_time)-1)/(step_time[-1]-step_time[0])
    native_grid=np.arange(step_time[0],step_time[-1],1/rate)
    native=c[updated][np.searchsorted(step_time,native_grid,side='right')-1]
    callback_grid=np.arange(t[0],t[-1],.01)
    callback=c[np.searchsorted(t,callback_grid,side='right')-1]
    f,p=psd(native,rate); cf,cp=psd(antialias(callback),25.)
    band=cf<=7.; df=cf[1]-cf[0]
    return dict(update_hz=rate,correction_tv=np.abs(np.diff(c[updated],axis=0)).sum(axis=0).tolist(),
        correction_tv_per_second=(np.abs(np.diff(c[updated],axis=0)).sum(axis=0)/64.).tolist(),
        native_frequency_hz=f.tolist(),native_psd=p.tolist(),common_frequency_hz=cf.tolist(),common_psd=cp.tolist(),
        common_0_7hz_rms=np.sqrt(np.sum(cp[band],axis=0)*df).tolist(),
        notes='Analysis-only ZOH at measured update Hz and100Hz callbacks; common513tap8Hz BlackmanFIR then25Hz,2.56s boundary crop. TV only actual updates; not physical motor energy. HTE-only cache shifts between updates are not extra algorithm updates.')
