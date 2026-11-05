#!/usr/bin/env python3
import copy
import math
import unittest
from analyze import aggregate, verify


class AnalysisTests(unittest.TestCase):
    def points(self):
        return [dict(t=0., h=.008, v=1., v_sp=0., measurement=2., a_applied=.1, nu_applied=.2, constrained=False),
                dict(t=.008, h=.012, v=2., v_sp=0., measurement=3., a_applied=-.3, nu_applied=-.4, constrained=True)]

    def test_nonuniform_weighting(self):
        result = aggregate(self.points())
        self.assertAlmostEqual(result['rmse'], math.sqrt(2.8))
        self.assertAlmostEqual(result['measured_rmse'], math.sqrt(7.))
        self.assertAlmostEqual(result['measured_mean'], 2.6)
        self.assertAlmostEqual(result['constrained_fraction'], .6)

    def test_tv_uses_actual_update_differences(self):
        self.assertAlmostEqual(aggregate(self.points())['correction_tv_per_s'], 20.)

    def test_empty_not_zero_error(self):
        self.assertIsNone(aggregate([]))
        with self.assertRaises(AssertionError):
            verify(None, aggregate(self.points()))

    def test_modified_metric_rejected(self):
        result = aggregate(self.points())
        corrupt = copy.deepcopy(result)
        corrupt['rmse'] = 0.
        with self.assertRaises(AssertionError):
            verify(result, corrupt)

    def test_missing_metric_rejected(self):
        result = aggregate(self.points())
        corrupt = copy.deepcopy(result)
        del corrupt['measured_peak_error']
        with self.assertRaises(AssertionError):
            verify(result, corrupt)

    def test_valid_roundoff_accepted(self):
        result = aggregate(self.points())
        rounded = copy.deepcopy(result)
        rounded['rmse'] += 1e-15
        verify(result, rounded)


if __name__ == '__main__':
    unittest.main()
