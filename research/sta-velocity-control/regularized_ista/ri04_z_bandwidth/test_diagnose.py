#!/usr/bin/env python3
import unittest
import copy
import json
from pathlib import Path
import numpy as np
from diagnose import align, harmonics, local_gains, stats


class DiagnosticTests(unittest.TestCase):
    def test_candidate_model_binding_and_drift_rejected(self):
        from model_check import MATCHED
        from verify import validate_candidate
        candidate=json.loads((Path(__file__).parent/'candidate.json').read_text())
        model=dict(success=True,fixed_candidate=list(MATCHED))
        validate_candidate(candidate,model)
        for key,value in (('candidate',dict(lambda1=2.,lambda2=1.,epsilon=.02)),
                          ('flight_authorized',True),('reference_h_seconds',.008),
                          ('unchanged_limits',dict(nu_m_per_s2=40.,correction_m_per_s2=6.))):
            changed=copy.deepcopy(candidate);changed[key]=value
            with self.assertRaises(ValueError): validate_candidate(changed,model)
        with self.assertRaises(ValueError): validate_candidate(candidate,dict(success=True,fixed_candidate=[2.,1.,.02]))

    def test_gains_follow_implicit_relation(self):
        k,i,p,j=local_gains(2,1,.02,np.array([.008,.01,.012]))
        self.assertAlmostEqual(k,14.142135623730951)
        self.assertEqual(i,50.)
        self.assertTrue(np.all(p<k) and np.all(j<i))
        self.assertAlmostEqual(p[1],12.772036689710818,places=9)

    def test_bad_gain_or_dt(self):
        for l1,l2,e,h in ((0,1,.02,.01),(2,-1,.02,.01),(2,1,0,.01),
                          (2,1,.02,0),(2,1,.02,np.nan),(np.inf,1,.02,.01)):
            with self.assertRaises(ValueError): local_gains(l1,l2,e,h)

    def test_bias_variance_decomposition(self):
        r=stats([1,2,3],[1,2,1])
        self.assertAlmostEqual(r['mean'],2.)
        self.assertAlmostEqual(r['variance'],.5)
        self.assertAlmostEqual(r['rmse']**2,r['mean']**2+r['variance'])

    def test_stats_rejects_bad_weights_and_nonfinite(self):
        for x,w in (([1,2],[1,0]),([1,2],[1,-1]),([1,np.nan],[1,1]),([1,2],[1,np.inf]),([],[])):
            with self.assertRaises(ValueError): stats(x,w)

    def test_exact_sequence_join(self):
        d=dict(publish_seq=np.array([2,4]),timestamp_sample=np.array([20,40]),
               effective_mode=np.array([4,4]),effective_axes=np.array([4,4]))
        q=dict(publish_seq=np.array([1,2,3,4]),timestamp_sample=np.array([10,20,30,40]),
               effective_mode=np.array([4]*4),effective_axes=np.array([4]*4))
        self.assertTrue(np.array_equal(align(d,q)['timestamp_sample'],d['timestamp_sample']))
        for seq in ([1,2,2,4],[1,2,3,3],[1,2,4,3]):
            with self.assertRaises(ValueError): align(d,{**q,'publish_seq':np.array(seq)})
        with self.assertRaises(ValueError): align(d,{**q,'effective_axes':np.array([4,4,4,1])})

    def test_harmonic_phase_sign_and_energy(self):
        t=np.arange(0,32,.01); w=np.full(len(t),.01)
        ref=.1*np.sin(2*np.pi*t/8); v=.09*np.sin(2*np.pi*t/8-.05)
        r=harmonics(t,v-ref,ref,v,w)
        self.assertAlmostEqual(r['central_gain'],.9,places=12)
        self.assertAlmostEqual(r['central_phase_deg'],-.05*180/np.pi,places=10)
        self.assertLess(r['residual_error_rmse'],1e-14)
        self.assertAlmostEqual(r['projected_error_rmse'],stats(v-ref,w)['rmse'],places=12)

    def test_unidentifiable_harmonic_rejected(self):
        t=np.arange(0,32,.01); zero=np.zeros(len(t));w=np.ones(len(t))
        with self.assertRaises(ValueError): harmonics(t,zero,zero,zero,w)


if __name__=='__main__': unittest.main()
