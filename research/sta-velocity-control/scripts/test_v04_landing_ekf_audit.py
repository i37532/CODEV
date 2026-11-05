"""Audit helper tests; these do not grant flight acceptance."""
import math
import unittest
import numpy as np
from audit_v04_landing_ekf import clean, combined, exact_index, source_target_comparison


class LandingAudit(unittest.TestCase):
    def test_exact_join(self):
        self.assertEqual(exact_index({'timestamp': np.array([10, 12])}, 12), 1)

    def test_no_nearest_neighbor_for_missing(self):
        with self.assertRaises(ValueError):
            exact_index({'timestamp': np.array([10, 12])}, 11)

    def test_duplicate_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            exact_index({'timestamp': np.array([12, 12])}, 12)

    def test_selector_metric(self):
        self.assertAlmostEqual(combined(.473488420248, .005579378922, .00034722), .239533899585)
        self.assertEqual(combined(.01, .01, .7), .7)

    def test_selector_invalid_ratio_is_not_zero_error(self):
        for value in [0, -1, math.nan, math.inf]:
            self.assertEqual(combined(value, value, value), 1)

    def test_cache_and_fresh_comparison(self):
        target = dict(x=1., y=2., z=3., vx=.5, vy=0., vz=.7)
        local = dict(zip(['delta_xy[0]', 'delta_xy[1]', 'delta_z', 'delta_vxy[0]', 'delta_vxy[1]', 'delta_vz'],
                         [2., -3., .4, .1, -.2, -1.27]))
        diag = dict(zip(['p_sp[0]', 'p_sp[1]', 'p_sp[2]', 'v_ff[0]', 'v_ff[1]', 'v_ff[2]'],
                        (float(np.float32(v)) for v in target.values())))
        self.assertTrue(all(x['exactly_equal'] for x in source_target_comparison(diag, target, local, False).values()))
        self.assertFalse(all(x['exactly_equal'] for x in source_target_comparison(diag, target, local, True).values()))
        translated = {k: v['expected'] for k, v in source_target_comparison(diag, target, local, True).items()}
        self.assertTrue(all(x['exactly_equal'] for x in source_target_comparison(translated, target, local, True).values()))

    def test_nonfinite_not_forged_zero(self):
        self.assertEqual(clean({'x': np.float32(math.nan), 'z': [math.inf]}), {'x': 'nan', 'z': ['inf']})


if __name__ == '__main__':
    unittest.main()
