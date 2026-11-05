"""No flight, archive mutation, or qualification: independent audit helpers."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('ri04_failure_audit', Path(__file__).with_name('audit_failure.py'))
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class FailureAudit(unittest.TestCase):
    def test_zero_and_odd_root(self):
        self.assertEqual(a.solve(0., .008, 0., 2., 1., .02)['p'], 0.)
        for s in (.005, .2, 3.):
            left = a.solve(s, .012, 0., 2., 1., .02)
            right = a.solve(-s, .012, 0., 2., 1., .02)
            self.assertAlmostEqual(left['p'], -right['p'], places=14)
            self.assertAlmostEqual(left['correction'], -right['correction'], places=14)
            self.assertLess(abs(left['root_residual']), 1e-14)

    def test_real_boundary_candidate_matches_float_log(self):
        result = a.solve(.005483005195856094, .00800000037997961, -4., 2., 1., .019999999552965164)
        self.assertLess(abs(result['p']-.004911602940410376), 2e-6)
        self.assertLess(abs(result['nu_candidate']-(-4.001964569091797)), 2e-6)
        self.assertLess(abs(result['correction']-(-4.071424961090088)), 2e-6)
        self.assertLess(result['nu_candidate'], -4.)

    def test_real_seed_uses_eight_not_twelve_ms(self):
        seed = a.solve(.7574234008789062, .00800000037997961, 0., 2., 1., .019999999552965164)
        self.assertLess(abs((-3.276840925216675-seed['correction'])-(-1.5442395210266113)), 2e-6)
        wrong = a.solve(.7574234008789062, .012, 0., 2., 1., .02)
        self.assertGreater(abs(seed['correction']-wrong['correction']), 1e-3)

    def test_counterfactual_numeric_feasible_never_cache_admitted(self):
        out = a.hypothetical_hte(.5, .7190654277801514, -4.071424961090088, 0., -4., 4., 6.)
        self.assertTrue(out['nu_bound_ok'] and out['new_correction_bound_ok'])
        self.assertFalse(out['actually_executed'])
        self.assertFalse(out['cache_policy_admitted'])

    def test_bad_numeric_inputs_refused(self):
        for h in (0., -.1, float('nan')):
            with self.assertRaises(ValueError): a.solve(.1, h, 0., 2., 1., .02)

    def test_exact_pairing_never_approximate(self):
        left = dict(timestamp_sample=[1, 2], publish_seq=[3, 4])
        right = dict(timestamp_sample=[2, 1], publish_seq=[4, 3])
        self.assertEqual(a.exact_join(left, right), [1, 0])
        right['timestamp_sample'][0] = 3
        with self.assertRaises(ValueError): a.exact_join(left, right)

    def test_duplicate_identity_rejected(self):
        data = dict(timestamp_sample=[1, 1], publish_seq=[3, 3])
        with self.assertRaises(ValueError): a.exact_join(data, data)

    def test_nonfinite_report_values_explicit_not_invalid_json(self):
        self.assertEqual(a.native([float('nan'), float('inf'), -float('inf')]), ['NaN', 'Infinity', '-Infinity'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
