import decimal
import math
import unittest

import diagnostic as d
import numerical as n
import collect
from common import analysis, probe


class PV00Tests(unittest.TestCase):
    def test_log_format_retains_padding(self):
        self.assertEqual(collect.format_length('t','uint8_t x;uint8_t[7] _padding0;'),34)

    def test_generated_log_format_capacity(self):
        import re
        from common import REPO
        for name,expected in (('sta_velocity_ctrl_status',1475),('velocity_ctrl_selection',1018)):
            text=(REPO/f'build/px4_sitl_default/msg/topics_sources/{name}.cpp').read_text()
            fields=re.search(r'__orb_\w+_fields\[\] = "([^"]+)"',text)[1]
            self.assertEqual(collect.format_length(name,fields),expected)
            self.assertLess(expected,1500)

    def test_exact_matrix_counts(self):
        rows = d.manifest()
        self.assertEqual(len(rows),69)
        self.assertEqual(len({r['id'] for r in rows}),69)
        self.assertEqual(sum(r['group']=='recorded' for r in rows),12)
        self.assertEqual(len(n.grid()),122)

    def test_manifest_one_factor(self):
        for r in d.manifest():
            if r['group']=='lag':
                self.assertEqual((r['noise_scale'],r['period']),(0.,[10000]))
            if r['group'].startswith('noise'):
                self.assertEqual((r['lag_scale'],r['period']),(0.,[10000]))
            if r['group']=='period':
                self.assertEqual((r['lag_scale'],r['noise_scale']),(1.,0.))

    def test_all_synthetic_durations(self):
        for r in d.manifest():
            self.assertEqual(sum(d.periods(r,[12000,8000]*1800)),36_000_000)

    def test_recorded_not_repeated(self):
        with self.assertRaises(ValueError): d.periods({'period':None},[8000,12000])

    def test_invalid_raw_interval(self):
        for values in ([0],[1000],[40001],[10000.0]):
            with self.assertRaises(ValueError): d.periods({'period':values},[])

    def test_no_short_final_interval(self):
        with self.assertRaises(ValueError): d.periods({'period':[14000]},[])

    def test_zoh_integral_against_rk4(self):
        # Separate differential equations and numerical integration, not a copied solution.
        for scale in (.25,.5,1.,2.):
            for h in (.004,.008,.012,.016):
                for command in (-.3,.2):
                    x=[.1,-.07,0.]
                    def rhs(v): return [(command-v[0])/(.06*scale),(v[0]-v[1])/(.02*scale),v[1]]
                    dt=h/400
                    for _ in range(400):
                        k1=rhs(x)
                        k2=rhs([a+dt*b/2 for a,b in zip(x,k1)])
                        k3=rhs([a+dt*b/2 for a,b in zip(x,k2)])
                        k4=rhs([a+dt*b for a,b in zip(x,k3)])
                        x=[a+dt*(b+2*c+2*e+f)/6 for a,b,c,e,f in zip(x,k1,k2,k3,k4)]
                    lag,integral=d.cascade([.1,-.07],command,h,scale)
                    for actual,expected in zip([*lag,integral],x):
                        self.assertLess(abs(actual-expected),2e-11)

    def test_cascade_matches_old_at_unit_scale(self):
        for h in (.008,.010,.012):
            self.assertEqual(d.cascade([.1,.2],-.4,h,1.),probe.cascade([.1,.2],-.4,h))

    def test_cascade_zero_is_physical_integrator(self):
        self.assertEqual(d.cascade([1.,2.],.3,.01,0.),([.3,.3],.003))

    def test_implicit_residual_detects_wrong_output(self):
        s,h,nu=.03,.008,.1
        z,a,nxt,xi=probe.reference(2,(2.,1.,0.),s,nu,h)
        c=[s,z,a,nu,nxt,xi,1]
        self.assertLess(probe.candidate_residual(2,(2.,1.,0.),c,h),1e-12)
        c[2]+=1e-3
        self.assertGreater(probe.candidate_residual(2,(2.,1.,0.),c,h),1e-4)

    def test_decimal_oracle_and_symmetry(self):
        for h in (.008,.012):
            for s in (.0,1e-38,.0001,.03,1.):
                v=n.decimal_reference(s,.1,h)
                mirror=n.decimal_reference(-s,-.1,h)
                for key in ('a','nu_next','z','xi'):
                    self.assertAlmostEqual(float(v[key]),-float(mirror[key]),places=14)
                z,a,nxt,xi=probe.reference(2,(2.,1.,0.),probe.f32(s),probe.f32(.1),probe.f32(h))
                self.assertAlmostEqual(a,float(v['a']),places=13)
                self.assertAlmostEqual(nxt,float(v['nu_next']),places=13)

    def test_exact_sliding_boundary_and_neighbours(self):
        h=2.**-7
        q=h*h
        for sign in (-1,1):
            for offset in (-1,0,1):
                s=sign*n.neighbour(q,offset)
                r=n.proper_arithmetic(s,0.,h)
                self.assertEqual(r['branch'],'outer' if offset==1 else 'sliding')

    def test_special_gain_outer_equals_explicit_sta(self):
        for s in (-.03,-.001,.001,.03):
            z,a,nxt,xi=probe.reference(2,(2.,1.,0.),s,.1,.01)
            self.assertAlmostEqual(a,.1-2*math.copysign(math.sqrt(abs(s)),s),places=14)
            self.assertNotEqual(z,0.)

    def test_deadbeat_physical_two_steps(self):
        s,nu,h,d0=1e-6,-.1499,.01,.15
        for _ in range(2):
            z,a,nu,xi=probe.reference(2,(2.,1.,0.),s,nu,h)
            s+=h*(a+d0)
        self.assertLess(abs(s),1e-18)
        self.assertLess(abs(nu+d0),1e-15)

    def test_subnormal_classification_not_deadzone(self):
        self.assertEqual(n.classify(n.DENORM),'subnormal_or_round_to_zero')
        self.assertEqual(n.classify(0.),'zero')
        self.assertEqual(n.classify(n.MIN),'normal')
        self.assertNotEqual(n.bits(n.DENORM),n.bits(0.))

    def test_true_overflow_distinct(self):
        self.assertEqual(n.classify(2*n.MAX),'overflow_float')
        self.assertEqual(n.classify(float('inf')),'nonfinite')
        self.assertEqual(n.classify(n.MAX),'normal')

    def test_binary64_intermediate_wide_domain(self):
        r=n.proper_arithmetic(1.,0.,n.MIN,n.MIN,n.MIN)
        self.assertGreater(r['terms']['q']['double'],0.)
        self.assertEqual(r['terms']['q']['float_value'],0.)
        r=n.proper_arithmetic(1.,0.,n.MAX,n.MAX,n.MAX)
        self.assertTrue(math.isfinite(r['terms']['q']['double']))
        self.assertEqual(r['terms']['q']['float_value'],'inf')

    def test_subtractive_root_loses_small_root(self):
        r=n.proper_arithmetic(1.,0.,.008,1e20,1.)
        self.assertEqual(r['subtractive_root'],0.)
        self.assertGreater(r['rational_root'],0.)

    def test_report_replay_rejects_metric_tamper(self):
        with self.assertRaises(AssertionError): analysis.verify({'rmse':1.},{'rmse':0.})

    def test_local_matrix_ideal_deadbeat(self):
        for row in d.linear_mechanism():
            if row['lag_scale']==0:
                self.assertLess(row['radius'],1e-6)


if __name__=='__main__':
    unittest.main(verbosity=2)
