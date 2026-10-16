#!/usr/bin/env python3
import math
import unittest
from model_reference import (GAINS, apply_proxy, disturbance_average, f32, matrix,
                             next_float, noise, numerical_terminal_eligible, plant_step, reference, target, TerminalClock)


class ReferenceTests(unittest.TestCase):
    def test_01_matrix_fixed_finite(self):
        rows = matrix()
        self.assertEqual(len(rows), 160)
        self.assertEqual(len({tuple(r.values()) for r in rows}), 160)

    def test_02_reference_odd_and_old_nu(self):
        g = GAINS["z"]
        for s in [-.04, -.01, 0., .01, .04]:
            a, n = reference(s, .2, .01, g, True)
            b, m = reference(-s, -.2, .01, g, True)
            self.assertEqual((a, n), (-b, -m))
        a, n = reference(.01, .2, .01, g, True)
        self.assertNotEqual(a, -g["l1"] * .01 / math.sqrt(g["epsilon"]) + n)

    def test_03_zero_constant_equilibrium(self):
        for d in [-.08, 0., .08]:
            a, nu = reference(0., -d, .012, GAINS["z"], True)
            self.assertEqual(plant_step((0., a, a), a, .012, d, False)[0], 0.)
            self.assertEqual(nu, -d)

    def test_04_ff_once_and_limit_order(self):
        g = dict(GAINS["xy"], correction_limit=1.)
        output, _, corr, _, _ = apply_proxy(3., 0., -.01, 3., g, 100.)
        self.assertEqual((output, corr), (4., 1.))

    def test_05_freeze_and_unwind(self):
        g = dict(GAINS["xy"], correction_limit=1.)
        self.assertEqual(apply_proxy(2., .1, .11, 0., g, 100.)[1], .1)
        self.assertEqual(apply_proxy(2., .1, .09, 0., g, 100.)[1], .09)

    def test_06_lag_exact_vs_independent_rk4(self):
        initial = (.13, -.07, .03)
        command, d, h = .2, .08, .012
        expected = plant_step(initial, command, h, d, True)
        state = initial
        def derivative(q):
            v, x, y = q
            return y + d, (command - x) / .04, (x - y) / .025
        step = h / 1000
        for _ in range(1000):
            k1 = derivative(state)
            k2 = derivative(tuple(x + step * y / 2 for x, y in zip(state, k1)))
            k3 = derivative(tuple(x + step * y / 2 for x, y in zip(state, k2)))
            k4 = derivative(tuple(x + step * y for x, y in zip(state, k3)))
            state = tuple(x + step * (a + 2*b + 2*c + e) / 6
                          for x, a, b, c, e in zip(state, k1, k2, k3, k4))
        for a, b in zip(state, expected):
            self.assertAlmostEqual(a, b, places=13)

    def test_07_ramp_exact_integral(self):
        for name, sign in [("ramp_positive", 1), ("ramp_negative", -1)]:
            t, h = 1.1, .012
            integral = disturbance_average(t, h, name) * h
            self.assertAlmostEqual(integral, sign * (.02 * h + .001 * ((t+h)**2 - t*t)), places=15)

    def test_08_reference_target_derivative(self):
        for t in [0., .7, 4., 8.]:
            _, ff = target(t, "tracking_ff")
            numerical = (target(t+1e-5, "tracking_ff")[0] - target(t-1e-5, "tracking_ff")[0]) / 2e-5
            self.assertAlmostEqual(ff, numerical, places=10)

    def test_09_float_neighbors(self):
        for v in [.001, .01, .02, 1.]:
            self.assertLess(next_float(v, -math.inf), f32(v))
            self.assertGreater(next_float(v, math.inf), f32(v))

    def test_10_deterministic_noise_bounded(self):
        values = [noise(i * .008, "noise") for i in range(1000)]
        self.assertGreater(max(values), .002)
        self.assertLessEqual(max(abs(x) for x in values), .003)

    def test_11_terminal_restricted_to_zero_and_both_states(self):
        self.assertTrue(numerical_terminal_eligible(True, "zero", 1e-13, -1e-13, 1e-13, 1e-13))
        self.assertFalse(numerical_terminal_eligible(False, "zero", 0., 0., 0., 0.))
        self.assertFalse(numerical_terminal_eligible(True, "constant_positive", 0., 0., 0., 0.))
        for index in range(4):
            values = [0., 0., 0., 0.]
            values[index] = 1e-12
            self.assertFalse(numerical_terminal_eligible(True, "zero", *values))

    def test_12_terminal_first_observation_no_prior_interval(self):
        clock = TerminalClock()
        self.assertEqual(clock.observe(True, 12.), 0.)
        self.assertAlmostEqual(clock.observe(True, 12.012), .012)

    def test_13_terminal_precise_boundary(self):
        clock = TerminalClock()
        clock.observe(True, 2.)
        self.assertLess(clock.observe(True, math.nextafter(3., 0.)), 1.)
        self.assertEqual(clock.observe(True, 3.), 1.)

    def test_14_terminal_invalid_observation_resets(self):
        clock = TerminalClock()
        clock.observe(True, 2.)
        self.assertEqual(clock.observe(False, 2.5), 0.)
        self.assertEqual(clock.observe(True, 3.), 0.)
        self.assertEqual(clock.observe(True, 4.), 1.)


if __name__ == "__main__":
    unittest.main(verbosity=2)
