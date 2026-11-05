#!/usr/bin/env python3
import unittest

from analyze import summarize
from design import build_jobs


class I04Tests(unittest.TestCase):
    def test_jobs_are_exact_and_roll_only(self):
        frozen, jobs = build_jobs('a'*40)
        self.assertEqual(len(jobs), 8)
        self.assertEqual([j['algorithm'] for j in jobs], [x[1] for x in frozen['ordered_jobs']])
        self.assertEqual(sum(j['mode'] == 1 for j in jobs), 3)
        self.assertEqual(sum(j['mode'] == 3 for j in jobs), 3)
        for job in jobs:
            self.assertEqual(job['parameters']['MC_STA_AXES'], 0 if job['mode'] == 0 else 1)
            self.assertEqual(job['parameters']['MC_STA_TKO_MGT'], 0)
            self.assertEqual(job['parameters']['MC_RTC_DIV'], 1)
            self.assertEqual(job['parameters']['MC_STA_G_R'], 130.575283)

    @staticmethod
    def rows(proper_scale=1.0):
        rows=[]
        for algorithm, mode in [('pid_smoke',0),('original_ista_regression',2)]:
            rows.append(dict(success=True,algorithm=algorithm,mode=mode,seed=6201,
                             hover_rmse=[.01,.01,.01],tracking_rmse=[.01,.01,.01]))
        for seed in (6201,6202,6203):
            rows.append(dict(success=True,algorithm='esta',mode=1,seed=seed,
                             hover_rmse=[.01,.01,.01],tracking_rmse=[.02,.01,.01]))
            rows.append(dict(success=True,algorithm='proper_ista',mode=3,seed=seed,
                             hover_rmse=[.01*proper_scale,.01,.01],tracking_rmse=[.02*proper_scale,.01,.01]))
        # Match frozen order; summary deliberately does not rely on row order.
        return rows

    def test_summary_accepts_predeclared_boundary(self):
        summary=summarize(self.rows(1.25))
        self.assertTrue(summary['success']); self.assertEqual(summary['accepted'],8)

    def test_summary_rejects_ratio_and_retains_failure(self):
        rows=self.rows(1.251); self.assertFalse(summarize(rows)['success'])
        rows=self.rows(); rows[-1]['success']=False
        summary=summarize(rows); self.assertFalse(summary['success']); self.assertEqual(summary['accepted'],7)


if __name__ == '__main__': unittest.main()
