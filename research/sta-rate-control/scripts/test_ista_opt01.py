import tempfile
import json
import unittest
from pathlib import Path
import numpy as np
from ista_opt01 import implicit, immutable, metrics, compare_final, proxy, BASE, TRAIN, VALIDATE, HOLDOUT, SCENES
from m08_ista_reference import ideal


class IstaOpt01Test(unittest.TestCase):
    def test_disjoint_seeds(self):
        groups=[set((1101,1102,2101,2102,2103,*range(3101,3121))),set((4001,)),set(TRAIN),set(VALIDATE),set(HOLDOUT)]
        for i,a in enumerate(groups):
            for b in groups[i+1:]:self.assertFalse(a&b)

    def test_proxy_root_against_independent_bisection(self):
        rng=np.random.default_rng(411)
        for h in (.004,.008,.016):
            s=rng.uniform(-1,1,256);old=rng.uniform(-3,3,256);l1=rng.uniform(1.2,3.2,256);l2=rng.uniform(.02,1.6,256)
            a,nu=implicit(s,old,h,l1,l2);r=ideal(s,old,h,l1,l2,np.ones(256))
            np.testing.assert_allclose(a,r['a'],atol=1e-13,rtol=1e-13)
            np.testing.assert_allclose(nu,r['nu'],atol=1e-13,rtol=1e-13)

    def test_proxy_zero_and_symmetry(self):
        a,n=implicit(np.zeros(3),np.zeros(3),.004,np.ones(3),np.ones(3));np.testing.assert_array_equal(a,0);np.testing.assert_array_equal(n,0)
        x=np.array([-.2,0,.2]);a,n=implicit(x,x,.016,2.,.1);b,m=implicit(-x,-x,.016,2.,.1)
        np.testing.assert_array_equal(a,-b);np.testing.assert_array_equal(n,-m)

    def dataset(self,ratio=1.,seeds=TRAIN):
        return [dict(scene=s,seed=k,success=True,rmse_tracking=[ratio]*3) for s in SCENES for k in seeds]

    def test_complete_pairs_required(self):
        a=self.dataset();b=self.dataset()
        with self.assertRaises(ValueError):metrics(a[:-1],b)
        with self.assertRaises(ValueError):metrics(a+[a[0]],b)

    def test_goal_threshold(self):
        self.assertTrue(metrics(self.dataset(.98),self.dataset())['goal_met'])
        self.assertFalse(metrics(self.dataset(.999),self.dataset())['goal_met'])

    def test_failure_never_imputed(self):
        a=self.dataset(.5);a[0]['success']=False
        self.assertFalse(metrics(a,self.dataset())['eligible'])
        c=compare_final(a,self.dataset(),TRAIN);self.assertNotIn('goal_met',c);self.assertEqual(c['ista_accepted'],11)

    def test_degradation_gates(self):
        a=self.dataset(.5);a[0]['rmse_tracking']=[3.,.5,.5]
        self.assertFalse(metrics(a,self.dataset())['eligible'])

    def test_immutable(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'record.json';immutable(p,dict(a=(1,2)));immutable(p,dict(a=(1,2)))
            with self.assertRaises(RuntimeError):immutable(p,dict(a=2))

    def test_invalid_metrics_rejected(self):
        for bad in (float('nan'),float('inf'),0.,-1.):
            a=self.dataset();a[0]['rmse_tracking']=[bad]*3
            with self.assertRaises(ValueError):metrics(a,self.dataset())

    def test_holdout_budget(self):
        self.assertEqual(len(SCENES)*len(HOLDOUT)*2,240)
        self.assertEqual(12+12*2+3*10+len(SCENES)*len(VALIDATE)*2+240,342)

    def test_proxy_candidates_and_fixed_fields(self):
        p=proxy();self.assertLessEqual(len(p['candidates']),12)
        base=json.loads(BASE.read_text())['selection']['2']['parameters']
        changed={f'MC_STA_L{i}_{axis}' for i in (1,2) for axis in 'RPY'}
        self.assertEqual(len(p['scenes']),6)
        for c in p['candidates']:
            self.assertEqual(set(c['parameters']),set(base))
            for key,value in base.items():
                if key not in changed:self.assertEqual(c['parameters'][key],value)


if __name__=='__main__':unittest.main()
