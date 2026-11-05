import copy
import unittest
import numpy as np
from cadence import aligned,check,check_pid_path
from spectra import antialias,psd

def fixture(n=4):
    count=401; tm=np.arange(count,dtype=np.int64)*10000+1000000; updates=np.arange(count)%n==0
    d=dict(timestamp=tm,timestamp_sample=tm,input_timestamp=tm,publish_seq=np.arange(count),pid_calls=np.ones(count),
        enabled=np.ones(count),armed=np.ones(count),effective_mode=np.zeros(count),effective_axes=np.zeros(count),
        used_dt=np.full(count,.01),raw_dt=np.full(count,.01),hover_thrust=np.full(count,.5),z_phase=np.zeros(count),z_hte_shift=np.zeros(count),pid_axes=np.full(count,7))
    q={k:v.copy() for k,v in d.items() if k in ('timestamp','timestamp_sample','input_timestamp','publish_seq','pid_calls','enabled','armed','effective_mode','effective_axes')}
    q.update(div_req=np.full(count,n),div_eff=np.full(count,n),div_pending=np.zeros(count),div_reject=np.zeros(count),control_fault=np.zeros(count),
        control_seq=np.cumsum(updates),control_updated=updates,control_held=~updates,h=np.where(updates,.01*n,np.nan),
        path_ns=np.full(count,100),module_ns=np.full(count,200),clock=np.ones(count),interval_pos=np.zeros(count),interval_neg=np.zeros(count))
    q['h'][0]=.01
    for i in range(3):
        q[f'correction[{i}]']=np.full(count,.01*i); q[f'integral[{i}]']=np.zeros(count)
        d[f'a_ff[{i}]']=np.full(count,.1); d[f'a_req[{i}]']=q[f'correction[{i}]']+.1
        for name in ('nu_before','nu_ideal','nu_applied','a_sta'): d[f'{name}[{i}]']=np.full(count,np.nan)
    return d,q,dict(divisor=n,mode=0)

class CadenceTest(unittest.TestCase):
    def test_three_divisors(self):
        for n in (1,2,4):
            d,q,j=fixture(n); r=check(d,aligned(d,q),j,True); self.assertAlmostEqual(r['update_hz'],100/n)
    def test_wrong_mode_and_clock_and_divisor(self):
        for field,value in [('div_req',2),('div_eff',2),('div_pending',1),('div_reject',1),('control_fault',1),('clock',0)]:
            d,q,j=fixture(); q[field][7]=value
            with self.assertRaises(ValueError): check(d,q,j,True)
    def test_missing_or_misaligned_selection(self):
        for field in ('publish_seq','timestamp_sample','input_timestamp','effective_mode'):
            d,q,j=fixture(); q[field][7]+=1
            with self.assertRaises(ValueError): aligned(d,q)
    def test_update_sequence_and_wrong_h(self):
        for field,index,value in [('control_seq',20,99),('h',20,.01),('h',21,.01),('control_updated',21,1)]:
            d,q,j=fixture(); q[field][index]=value
            with self.assertRaises(ValueError): check(d,q,j,True)
    def test_hold_ff_and_integral_and_cache(self):
        for field in ('integral[0]','integral[2]','correction[0]','correction[2]'):
            d,q,j=fixture(); q[field][21]+=.001
            with self.assertRaises(ValueError): check(d,q,j,True)
        d,q,j=fixture(); d['a_req[0]'][21]+=.01
        with self.assertRaises(ValueError): check(d,q,j,True)
    def test_no_z_sta_or_fabricated_state(self):
        for field in ('z_phase','z_hte_shift','nu_applied[0]'):
            d,q,j=fixture(); d[field][20]=1
            with self.assertRaises(ValueError): check(d,q,j,True)
    def test_no_missing_or_empty_steps(self):
        d,q,j=fixture(); q['control_updated'][:]=0; q['control_held'][:]=1
        with self.assertRaises(ValueError): check(d,q,j,True)
    def test_antialias_keeps_low_rejects_folded_high(self):
        t=np.arange(6400)/100
        low=antialias(np.sin(2*np.pi*3*t)); high=antialias(np.sin(2*np.pi*18*t))
        self.assertAlmostEqual(float(np.sqrt(np.mean(low*low))),np.sqrt(.5),places=2)
        self.assertLess(float(np.sqrt(np.mean(high*high))),1e-4)
    def test_psd_odd_even_parseval(self):
        for n in (1000,1001):
            y=np.sin(np.arange(n)*.17); f,p=psd(y,100.)
            w=np.hanning(n); expected=np.sum(((y-y.mean())*w)**2)/np.sum(w*w)
            self.assertAlmostEqual(float(np.sum(p)*(f[1]-f[0])),expected,places=12)

    def test_nonzero_pid_reference_and_wrong_integral_rejected(self):
        for n in (1,2,4):
            d,q,j=fixture(n); count=len(d['timestamp']); integral=np.zeros((count,3)); c=integral.copy()
            d['thrust_min']=np.full(count,.12); d['thrust_max']=np.ones(count); d['thrust[2]']=np.full(count,-.5)
            params={f'MPC_{group}_VEL_{name}_ACC':v for group in ('XY','Z') for name,v in [('P',1.8),('I',.4),('D',.2)]}
            for i in range(3):
                d[f's[{i}]']=np.full(count,-.1); d[f'v_dot[{i}]']=np.full(count,.03)
                value=0.; cached=0.
                for k in range(count):
                    if q['control_updated'][k]:
                        cached=.18+value-.03*.2; value+=.1*.4*q['h'][k]
                    c[k,i]=cached; integral[k,i]=value
                q[f'correction[{i}]']=c[:,i]; q[f'integral[{i}]']=integral[:,i]
                d[f'a_req[{i}]']=c[:,i]+.1; d[f'a_proxy[{i}]']=d[f'a_req[{i}]'].copy()
            self.assertEqual(check_pid_path(d,q,j,params)['samples'],count-1)
            q['integral[0]'][50]+=.01
            with self.assertRaises(ValueError): check_pid_path(d,q,j,params)

if __name__=='__main__': unittest.main(verbosity=2)
