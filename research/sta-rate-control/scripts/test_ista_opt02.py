import copy
import unittest
from ista_opt02 import candidates,ablations,scalar_checks,diagnostic_gate,TRAIN,VALIDATE,DIAG
from m10_design import equal_gains


class IstaOpt02Test(unittest.TestCase):
    def test_local_candidates(self):
        c=candidates();self.assertEqual(len(c),12)
        self.assertEqual(len({tuple(sorted(v['parameters'].items())) for v in c}),12)
        base=equal_gains(2);allowed={f'MC_STA_L{i}_{a}' for i in (1,2) for a in 'RPY'}
        for v in c:
            self.assertEqual(set(v['parameters']),set(base))
            for k,value in base.items():
                if k not in allowed:self.assertEqual(v['parameters'][k],value)
            for a in 'RPY':
                self.assertLessEqual(v['parameters']['MC_STA_L2_'+a],base['MC_STA_L2_'+a])
                self.assertGreater(v['parameters']['MC_STA_L2_'+a],0)

    def test_ablation_only_selected_lambda2(self):
        base=equal_gains(2)
        for c in ablations():
            for k,v in c['parameters'].items():
                expected=base[k]*4 if k in ['MC_STA_L2_'+a for a in c['scaled_axes']] else base[k]
                self.assertEqual(v,expected)

    def test_seed_separation(self):
        groups=[set(DIAG),set(TRAIN),set(VALIDATE),set([5001]),set(range(3101,3121)),set(range(4001,4400))]
        for i,a in enumerate(groups):
            for b in groups[i+1:]:self.assertFalse(a&b)

    def test_scalar_boundedness(self):
        r=scalar_checks();self.assertEqual(len(r['cases']),6)
        self.assertTrue(all(len(c['peak_rate_by_candidate'])==12 for c in r['cases']))

    def test_diagnostic_gate(self):
        d=[dict(candidate=f'D{i}',seed=k,flight_success=i==0,fault_samples=0,diagnostic_missing=0,
            frozen_state_equal=True,released_but_stationary_ground_samples=700,release_to_20mm_s=3,
            ground_nu_peak=[.1, .8 if i==1 else .2, .1]) for i in range(4) for k in DIAG]
        self.assertTrue(diagnostic_gate(d))
        bad=copy.deepcopy(d);bad[0]['flight_success']=False;self.assertFalse(diagnostic_gate(bad))
        bad=copy.deepcopy(d);bad[-1]['diagnostic_missing']=1;self.assertFalse(diagnostic_gate(bad))
        self.assertFalse(diagnostic_gate(d[:-1]))

    def test_budget(self):
        self.assertEqual(8+12+24+20+36,100)


if __name__=='__main__':unittest.main()
