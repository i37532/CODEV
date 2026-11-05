#!/usr/bin/env python3
"""I00 test harness checks. Library path must name an actually compiled bridge."""
import math
import os
import unittest

import numpy as np

from audit import Kernel, case_grid, disturbance_average, f32, implicit, moments, plant_step


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kernel = Kernel(os.environ['I00_KERNEL_LIBRARY'])

    def test_constant_equilibrium(self):
        for h0 in (.004, .008, .016):
            for d in (-.45, 0., .45):
                for g0 in (1., 112.763533):
                    h, g = f32(h0), f32(g0)
                    r = self.kernel.step(2, h*d, -d, h, 2.4, .08, g, reset=True)
                    self.assertLess(abs(h*d+h*(g*r['c']+d)-h*d), 1e-8)
                    self.assertLess(abs(r['nu']+d), 1e-6)
                    self.assertLess(abs(r['z']), 1e-10)

    def test_zero_equilibrium(self):
        for mode in (1, 2):
            r = self.kernel.step(mode, 0., 0., .004, 2.4, .08, 1., reset=True)
            self.assertEqual(r['a'], 0.)
            self.assertEqual(r['nu'], 0.)

    def test_independent_reference_equations(self):
        for s in (-1., -.000001, 0., .000001, 1.):
            r = implicit(s, .3, .008, 2.4, .08, 13.)
            self.assertAlmostEqual(r['z'], s+.008*r['a'], places=12)
            self.assertAlmostEqual(r['nu'], .3-.008*.08*r['xi'], places=12)
            self.assertLessEqual(abs(r['xi']), 1.)

    def test_reference_three_branches(self):
        self.assertEqual([implicit(s, 0., .01, 2., 1., 1.)['branch'] for s in (1., 0., -1.)], [1, 2, 3])

    def test_sign_symmetry(self):
        for mode in (1, 2):
            a = self.kernel.step(mode, .12, .3, .004, 2.4, .08, 11., reset=True)
            b = self.kernel.step(mode, -.12, -.3, .004, 2.4, .08, 11., reset=True)
            for field in ('a', 'c', 'nu'):
                self.assertEqual(a[field], -b[field])

    def test_axis_state_isolation(self):
        self.kernel.step(2, .2, .7, .004, 2.4, .08, 1., reset=True, axis=0)
        a = self.kernel.step(2, -.2, -.4, .004, 2.4, .08, 1., reset=True, axis=1)
        self.kernel.step(2, .2, 0., .004, 2.4, .08, 1., axis=0)
        b = self.kernel.step(2, -.2, 0., .004, 2.4, .08, 1., axis=1)
        self.assertEqual(b['old'], a['nu'])

    def test_nonunit_mapping(self):
        a = self.kernel.step(2, .12, .3, .008, 2.4, .08, 1., reset=True)
        b = self.kernel.step(2, .12, .3, .008, 2.4, .08, 130., reset=True)
        self.assertEqual(a['a'], b['a'])
        self.assertEqual(a['nu'], b['nu'])
        self.assertAlmostEqual(a['a'], 130*b['c'], places=6)

    def test_ramp_average_and_index(self):
        h, d, m, k = .008, .15, .01, 100
        previous = disturbance_average(d, m, (k-1)*h, h)
        previous2 = disturbance_average(d, m, (k-2)*h, h)
        r = implicit(h*previous, -previous2, h, 2.4, .08, 1.)
        self.assertAlmostEqual(r['a'], -previous, places=12)
        self.assertAlmostEqual(r['nu'], -previous, places=12)
        self.assertAlmostEqual(disturbance_average(d, m, 1., h), d+m*(1.+h/2))

    def test_plant_not_virtual_assignment(self):
        x, _, _ = plant_step(.2, 0., -.1, 2., .45, .01, 'ideal')
        self.assertAlmostEqual(x, .2025)
        self.assertNotEqual(x, .2+.01*(-.2))

    def test_lag_exact_integral(self):
        x, motor, _ = plant_step(0., 0., 1., 1., 0., .01, 'lag')
        self.assertAlmostEqual(x, .01-.025*(1-math.exp(-.01/.025)))
        self.assertAlmostEqual(motor, 1-math.exp(-.01/.025))

    def test_constraints_do_not_hide_prediction_change(self):
        x, _, clipped = plant_step(.2, 0., -1., 1., .45, .01, 'saturation')
        self.assertTrue(clipped)
        self.assertAlmostEqual(x, .2025)

    def test_moments_and_reject_bad_data(self):
        m = moments(np.array([1., 2., 3.]))
        self.assertAlmostEqual(m['rmse']**2, m['mean']**2+m['std']**2)
        for data in ([], [float('nan')]):
            with self.assertRaises(ValueError):
                moments(data)

    def test_fixed_case_grid(self):
        cases = case_grid()
        self.assertEqual(len(cases), 138)
        self.assertEqual(sum(x['scenario']=='ideal' for x in cases), 108)
        self.assertEqual(sum(x['scenario']=='ramp' for x in cases), 12)
        self.assertEqual(sum(x['scenario'] in ('noise', 'lag', 'saturation') for x in cases), 18)


if __name__ == '__main__':
    unittest.main()
