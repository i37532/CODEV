#!/usr/bin/env python3
import unittest
import numpy as np
from analyze import missing_fraction, summarize
from design import build_jobs


class I03DesignTest(unittest.TestCase):
    def test_exact_matrix(self):
        _, jobs = build_jobs('deadbeef')
        self.assertEqual(len(jobs), 12)
        cells = {(j['algorithm'], j['protection']): 0 for j in jobs}
        for job in jobs: cells[(job['algorithm'], job['protection'])] += 1
        self.assertEqual(set(cells.values()), {3})

    def test_fresh_seed_plan(self):
        _, jobs = build_jobs('deadbeef')
        self.assertEqual({j['seed'] for j in jobs}, {6101, 6102, 6103})

    def test_only_manager_parameter_differs(self):
        _, jobs = build_jobs('deadbeef')
        for algorithm in ('esta', 'original_ista'):
            old = next(j for j in jobs if j['algorithm'] == algorithm and j['protection'] == 'established')
            new = next(j for j in jobs if j['algorithm'] == algorithm and j['protection'] == 'takeoff_nu_manager')
            changed = {k for k in old['parameters'] if old['parameters'][k] != new['parameters'][k]}
            self.assertEqual(changed, {'MC_STA_TKO_MGT'})

    def test_proper_ista_not_selected(self):
        _, jobs = build_jobs('deadbeef')
        self.assertEqual({j['mode'] for j in jobs}, {1, 2})

    def test_missing_fraction(self):
        fraction, missing = missing_fraction([9, 10, 13])
        self.assertEqual(missing, 2)
        self.assertAlmostEqual(fraction, 2/5)

    def test_summary_selects_new_only_when_all_gates_pass(self):
        rows = []
        for algorithm in ('esta', 'original_ista'):
            for seed in (6101, 6102, 6103):
                for protection, nu in (('established', 1.), ('takeoff_nu_manager', .1)):
                    rows.append(dict(algorithm=algorithm, seed=seed, protection=protection, accepted=True,
                                     checks={'manager_ok': True}, liftoff_nu_l2=nu,
                                     early_rate_rmse=[1., 1., 1.], early_peak_tilt_deg=2.))
        self.assertEqual(summarize(rows)['selected_common_protection'], 'takeoff_nu_manager')
        rows[-1]['accepted'] = False
        self.assertEqual(summarize(rows)['selected_common_protection'], 'established')


if __name__ == '__main__': unittest.main()
