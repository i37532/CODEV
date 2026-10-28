"""Read-only PV01 verifier review tests; isolated synthetic wiring is not flight."""
import decimal
import importlib.util
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
sys.path.insert(0,str(HERE))
spec=importlib.util.spec_from_file_location('pv01_verified',HERE/'verify.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)

def adjacent32(x,direction):
    bits=struct.unpack('I',struct.pack('f',x))[0]
    return struct.unpack('f',struct.pack('I',bits+direction))[0]

class ReferenceReview(unittest.TestCase):
    def test_exact_two_boundaries(self):
        for sign in (-1,1):
            z,a,n,xi=v.reference(sign*.03125,.25,.125,3.,2.)
            self.assertEqual((z,xi),(0.,sign))
            self.assertEqual(n,.25-sign*.25)
            self.assertEqual(a,.25-sign*.5)
    def test_boundary_neighbours(self):
        for sign in (-1,1):
            z,_,_,xi=v.reference(sign*adjacent32(.03125,-1),.25,.125,3.,2.)
            self.assertEqual(z,0.);self.assertLess(abs(xi),1.)
            z,_,_,xi=v.reference(sign*adjacent32(.03125,1),.25,.125,3.,2.)
            self.assertGreater(z*sign,0.);self.assertEqual(xi,sign)
    def test_symmetry(self):
        for s in (v.ETA,1e-35,.0001,.03,3.):
            positive=v.reference(s,.13,.008)
            negative=v.reference(-s,-.13,.008)
            for a,b in zip(positive,negative):self.assertEqual(a,-b)
    def test_tiny_xi_not_zero(self):
        z,a,n,xi=v.reference(v.ETA,0.,1.,1.,v.MAX)
        self.assertEqual(z,0.);self.assertGreater(xi,0.);self.assertLess(xi,v.ETA)
        self.assertEqual(n,-v.ETA);self.assertEqual(a,-2*v.ETA)
    def test_deep_bisection_against_decimal(self):
        s,nu,h,l1,l2=map(v.f32,(1.,0.,.008,1e20,1.))
        oracle=v.high_precision(s,nu,h,l1,l2)
        z,a,n,xi=v.reference(s,nu,h,l1,l2)
        self.assertGreater(z,0.);self.assertLess(z,1e-30)
        self.assertLess(abs(z/float(oracle['z'])-1.),3e-14)
        self.assertLess(abs(a/float(oracle['a'])-1.),3e-14)
    def test_decimal_cancellation_endpoint(self):
        maximum=decimal.Decimal.from_float(v.MAX)
        for s in (-1.,1.):
            r=v.high_precision(s,v.MAX,v.f32(.008),2.,1.)
            # copy_abs is context-free; abs(Decimal) applies default precision.
            precise=decimal.Decimal(r['nu_next'])
            self.assertEqual(float(precise),v.MAX)
            self.assertEqual(precise.copy_abs()>maximum,s<0)
    def test_decimal_extreme_inclusion(self):
        for values in ((v.ETA,0.,v.f32(.0001),v.MAX,2.**-126),
                       (1.,0.,2.**-126,2.**-126,2.**-126),
                       (v.ETA,0.,1.,1.,v.MAX)):
            result=v.high_precision(*values)
            with decimal.localcontext() as ctx:
                ctx.prec=100
                D=decimal.Decimal.from_float
                s,nu,h,l1,l2=map(D,map(v.f32,values));z=decimal.Decimal(result['z']);xi=decimal.Decimal(result['xi'])
                residual=z+h*l1*z.copy_abs().sqrt()*xi+h*h*l2*xi-s
                scale=max(s.copy_abs(),decimal.Decimal('1e-300'))
                self.assertLess(residual.copy_abs()/scale,decimal.Decimal('1e-85'))
    def test_original_stop_bits(self):
        path=v.PV00_DATA/'numerical01/summary.json'
        cases=[r for r in json.loads(path.read_text())['stops'] if r['algorithm']=='proper']
        self.assertEqual(len(cases),4)
        for row in cases:
            args=[struct.unpack('>f',bytes.fromhex(row['input_bits'][k]))[0] for k in ('velocity','nu','h')]
            ref=v.high_precision(*args)
            self.assertTrue(all(math.isfinite(float(ref[k])) for k in ('a','nu_next','z','xi')))
            self.assertNotEqual(v.f32(float(ref['nu_next'])),0.)

class BudgetReview(unittest.TestCase):
    def candidate(self):
        s,nu,h=.00390625,.25,.125
        z,a,n,xi=v.reference(s,nu,h)
        return [s,z,v.f32(a),nu,v.f32(n),xi,2],h
    def test_correct_rounded_candidate(self):
        c,h=self.candidate();self.assertLessEqual(v.budget_check(c,h),1.)
    def test_bad_output(self):
        c,h=self.candidate();c[2]+=.01
        with self.assertRaises(AssertionError):v.budget_check(c,h)
    def test_bad_state(self):
        c,h=self.candidate();c[4]+=.01
        with self.assertRaises(AssertionError):v.budget_check(c,h)
    def test_bad_virtual_state(self):
        c,h=self.candidate();c[1]=.01
        with self.assertRaises(AssertionError):v.budget_check(c,h)
    def test_bad_branch(self):
        c,h=self.candidate();c[6]=1
        with self.assertRaises(AssertionError):v.budget_check(c,h)
    def test_bad_graph(self):
        c,h=self.candidate();c[5]=1.01
        with self.assertRaises(AssertionError):v.budget_check(c,h)
    def test_tiny_output_tamper_not_hidden_by_floor(self):
        s,nu,h=v.ETA,0.,2.
        z,a,n,xi=v.reference(s,nu,h)
        c=[s,z,v.f32(a),nu,v.f32(n),xi,2]
        self.assertLessEqual(v.budget_check(c,h),1.)
        c[2]+=20*v.ETA
        with self.assertRaises(AssertionError):v.budget_check(c,h)
    def test_nan_not_accepted(self):
        for column in range(7):
            c,h=self.candidate();c[column]=math.nan
            with self.assertRaises((AssertionError,ValueError)):v.budget_check(c,h)

class ObjectAndManifestReview(unittest.TestCase):
    def test_manifest_and_input_counts(self):
        matrix=[(p,s) for p in v.old.PERIODS for s in v.old.SCENARIOS]
        matrix += [('recorded8_12ms',s) for s in ('constant_positive','lag','noise','lag_noise')]
        self.assertEqual(len(matrix),52);self.assertEqual(len(set(matrix)),52)
        inputs=v.normal_cases();self.assertEqual(len(inputs),6018);self.assertEqual(inputs,v.normal_cases())
        self.assertEqual(len(json.loads((v.PV00_DATA/'numerical01/summary.json').read_text())['grid']),122)
    def test_recorded_cadence_never_needs_wrap(self):
        path=REPO/'research/sta-velocity-control/regularized_ista/ri00/results/cadence.json'
        series=json.loads(path.read_text())['delta_us'];self.assertEqual(len(series),6399)
        total=0;count=0
        while total<36_000_000:total+=series[count];count+=1
        self.assertEqual(total,36_000_000);self.assertLess(count,len(series))
        self.assertEqual(set(series[:count]),{8000,12000})
    def test_cascade_32_cases_independent_rk4(self):
        def derivative(y,u):return [(u-y[0])/.06,(y[0]-y[1])/.02,y[1]]
        for h in (.004,.008,.012,.016):
            for u in (-.3,.7):
                for initial in ((0.,0.),(.2,-.1),(-.4,.3),(.5,.5)):
                    y=[*initial,0.];dt=h/128
                    for _ in range(128):
                        k1=derivative(y,u);k2=derivative([x+dt*k/2 for x,k in zip(y,k1)],u)
                        k3=derivative([x+dt*k/2 for x,k in zip(y,k2)],u);k4=derivative([x+dt*k for x,k in zip(y,k3)],u)
                        y=[x+dt*(a+2*b+2*c+d)/6 for x,a,b,c,d in zip(y,k1,k2,k3,k4)]
                    states,integral=v.old.cascade(initial,u,h)
                    for actual,reference in zip([*states,integral],y):self.assertLess(abs(actual-reference),2e-11)
    def wiring(self,scenario):
        calls=[]
        class FakeCore:
            def __init__(self,*args):self.nu=0.
            def reset(self,nu=0.):self.nu=nu;return True
            def state(self):return self.nu
            def evaluate(self,measured,sp,h):
                calls.append((measured,sp,h));return 0,[measured-sp,0.,.2,self.nu,self.nu,0.,2]
            def commit(self,nu=None):
                if nu is not None:self.nu=nu
                return True
            def close(self):pass
        with tempfile.TemporaryDirectory(prefix='pv01-wire-',dir='/tmp') as path:
            with patch.object(v.old,'Kernel',FakeCore),patch.object(v.old,'target',return_value=(0.,1.)), \
                 patch.object(v,'budget_check',return_value=0.),patch.object(v,'reference',return_value=(0.,.2,.1,0.)):
                result=v.trajectory(None,'synthetic_wire_only',scenario,(18_000_000,),Path(path)/'trace.gz')
        self.assertEqual(result['updates'],2)
        return calls
    def test_feedforward_added_once_to_physical_integral(self):
        calls=self.wiring('target_with_ff')
        self.assertAlmostEqual(calls[1][0],.03+18*(.2+1.+.15),places=12)
    def test_no_implicit_feedforward_for_velocity_target(self):
        calls=self.wiring('velocity_target')
        self.assertAlmostEqual(calls[1][0],.03+18*(.2+.15),places=12)

if __name__=='__main__':unittest.main(verbosity=2)
