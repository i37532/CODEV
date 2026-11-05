#!/usr/bin/env python3
import math
import os
import unittest

import numpy as np

from audit import Kernel, disturbance, f32, grid, plant, reference, residuals


class ReferenceTest(unittest.TestCase):
    def test_sliding_exact(self):
        r = reference(.03125, .25, .125, 2., 4., 2.)
        self.assertEqual((r['nu'], r['a'], r['xi'], r['z']), (0., -.25, .5, 0.))

    def test_reference_equations_all_branches(self):
        for s in (-.2, -.0625, 0., .0625, .2):
            r = reference(s, .25, .125, 2., 4., 3.)
            self.assertLess(max(residuals(dict(r, s=s), .25, .125, 2., 4., 3.)), 1e-13)

    def test_reference_symmetric(self):
        a = reference(.2, .25, .125, 2., 4., 3.)
        b = reference(-.2, -.25, .125, 2., 4., 3.)
        for field in ('a', 'nu', 'xi', 'z', 'c'):
            self.assertEqual(a[field], -b[field])

    def test_bisection_convergence(self):
        # Comparing two iteration budgets tests oracle convergence, not production.
        s = float(np.nextafter(np.float32(1), np.float32(np.inf)))
        a, b = (reference(s, .25, 1., 16., 1., 3., iterations=n) for n in (100, 160))
        self.assertLess(abs(a['z']-b['z']), 1e-28)
        self.assertGreater(a['z'], 0.)

    def test_grid_is_fixed_and_complete(self):
        specs = grid()
        self.assertEqual(len(specs), 84)
        self.assertEqual(sum(s['kind'] == 'constant' for s in specs), 54)
        self.assertEqual(sum(s['kind'] == 'ramp' for s in specs), 12)

    def test_exact_disturbance_integrals(self):
        self.assertAlmostEqual(disturbance(dict(kind='ramp', d=.15, slope=.01), 2., .5), .1725)
        self.assertAlmostEqual(disturbance(dict(kind='sine', d=.15), 0., math.pi), .15+.04/math.pi)

    def test_plant_does_not_use_virtual_state(self):
        x, _ = plant(.1, 0., .2, 3., -.3, .01, 'constant')
        self.assertAlmostEqual(x, .103)

    def test_lag_and_insufficient_actuator_are_separate(self):
        x, motor = plant(0., 0., .2, 3., 0., .025, 'lag')
        self.assertAlmostEqual(motor, .6*(1-math.exp(-1)))
        self.assertAlmostEqual(x, .6*.025*math.exp(-1))
        x, _ = plant(0., 0., 1., 1., -.45, .1, 'saturation')
        self.assertAlmostEqual(x, -.025)


class ActualKernelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kernel = Kernel(os.environ['I01_KERNEL_LIBRARY']) # absence is a failure, never skip

    def test_actual_cpp_matches_reference(self):
        for s in (-.2, -.0625, 0., .0625, .2):
            actual = self.kernel.step(s, .25, .125, 2., 4., 3.)
            ref = reference(s, .25, .125, 2., 4., 3.)
            for key in ('a', 'nu', 'z', 'xi', 'c'):
                self.assertAlmostEqual(actual[key], ref[key], delta=1e-7)

    def test_cpp_state_continuity_and_axis_isolation(self):
        self.kernel.step(0., .25, .125, 2., 4., 3., axis=0)
        self.kernel.step(.2, -.5, .125, 2., 4., 3., axis=1)
        r = self.kernel.step(.01, 99., .125, 2., 4., 3., reset=False, axis=0)
        self.assertEqual(r['old'], .25)

    def test_cpp_invalid_time_preserves_state(self):
        self.kernel.step(0., .25, .125, 2., 4., 3.)
        code, r = self.kernel.raw(.1, 0., 0., 2., 4., 3., reset=False)
        self.assertEqual(code, 4)
        self.assertEqual(r['state'], .25)
        self.assertTrue(math.isnan(r['a']))

    def test_cpp_constant_disturbance_equilibrium(self):
        for h in (.004, .008, .016):
            for d in (-.5, 0., .5):
                r = self.kernel.step(0., -d, h, 2.4, .08, 2.)
                x, _ = plant(0., 0., r['c'], 2., d, f32(h), 'constant')
                self.assertEqual(x, 0.)


if __name__ == '__main__':
    unittest.main()
