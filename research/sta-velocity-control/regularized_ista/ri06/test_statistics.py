import unittest
import numpy as np
import statistical_plan as s

class Statistics(unittest.TestCase):
    def test_eight_predeclared(self):self.assertEqual(sum(map(len,s.COMPARISONS.values())),8)
    def test_constant_exact_intervals(self):
        r=s.summarize(np.full((20,2),-.001),'A',replicates=1000)
        self.assertEqual(r['common_complete_blocks'],20)
        self.assertTrue(all(v['adjusted_interval_below_practical'] for v in r['primary_ci']))
    def test_same_block_covariance_preserved(self):
        a=np.tile(np.arange(20)[:,None],(1,2));r=s.summarize(a,'A',replicates=1000)
        self.assertEqual(r['primary_ci'][0]['ci95'],r['primary_ci'][1]['ci95'])
    def test_deterministic(self):
        a=np.arange(120).reshape(20,6)
        self.assertEqual(s.summarize(a,'B',replicates=1000),s.summarize(a,'B',replicates=1000))
    def test_bonferroni_not_narrower(self):
        r=s.summarize(np.arange(40).reshape(20,2),'A',replicates=1000)
        for v in r['primary_ci']:
            self.assertLessEqual(v['family95_bonferroni'][0],v['ci95'][0]);self.assertGreaterEqual(v['family95_bonferroni'][1],v['ci95'][1])
    def test_missing_not_zero_imputed(self):
        a=np.ones((20,2));a[0,0]=np.nan;r=s.summarize(a,'A',replicates=1000)
        self.assertEqual(r['common_complete_blocks'],19);self.assertEqual(r['available_pairs'][1]['n'],20)
        self.assertEqual(r['primary_ci'][0]['mean_difference'],1.)
    def test_empty_no_ci(self):self.assertIsNone(s.summarize(np.full((20,2),np.nan),'A')['primary_ci'])
    def test_single_block_no_ci(self):
        a=np.full((20,2),np.nan);a[0]=0
        self.assertIsNone(s.summarize(a,'A')['primary_ci'])
    def test_infinity_rejected(self):
        with self.assertRaises(ValueError):s.summarize(np.full((20,2),np.inf),'A')
    def test_wrong_matrix_rejected(self):
        with self.assertRaises(ValueError):s.summarize(np.ones((21,2)),'A')
    def test_no_positive_gain_requirement(self):
        r=s.summarize(np.full((20,2),.001),'A',replicates=100)
        self.assertFalse(r['primary_ci'][0]['adjusted_interval_below_zero'])
    def test_zero_signflip(self):
        r=s.exploratory_sign_flip(np.zeros((20,2)),'A',replicates=100)
        self.assertEqual(r['p_two_sided'],[1.,1.])
    def test_signflip_positive_lowerbound(self):
        r=s.exploratory_sign_flip(np.ones((20,2)),'A',replicates=100)
        self.assertGreaterEqual(r['p_two_sided'][0],1/101)
    def test_precision_not_power(self):
        r=s.precision_estimate([.1,.2,.3]);self.assertEqual(r['n'],3);self.assertGreater(r['halfwidth_n20'],0)

if __name__=='__main__':unittest.main()
