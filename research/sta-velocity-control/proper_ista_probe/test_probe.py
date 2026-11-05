#!/usr/bin/env python3
import json
import math
import os
import struct
import subprocess
import sys
import unittest
from probe import (CONFIGS, HERE, Kernel, Metrics, candidate_residual, cascade, f32, manifest,
                   protect, reference, shape, target, theoretical)


def neighbor(x, offset):
    bits = struct.unpack('<I', struct.pack('<f', x))[0]
    return struct.unpack('<f', struct.pack('<I', bits + offset))[0]


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.cores = []

    def tearDown(self):
        for core in self.cores:
            core.close()

    def core(self, name):
        mode, params = CONFIGS[name]
        core = Kernel(os.environ['PROPER_VELOCITY_LIBRARY'], mode, params)
        self.cores.append(core)
        return core

    def test_manifest_no_flight_or_parameter_search(self):
        rows = manifest()
        self.assertEqual(len(rows), 144)
        self.assertEqual(len({tuple(row.values()) for row in rows}), 144)
        self.assertEqual(CONFIGS['proper'], (2, (2., 1., 0.)))
        self.assertEqual(CONFIGS['rsta'][1], CONFIGS['rista'][1])

    def test_default_cli_is_dry_run(self):
        result = subprocess.run([sys.executable, '-B', str(HERE / 'probe.py')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertFalse(data['flight_authorized'])
        self.assertEqual(data['trajectory_count'], 144)

    def test_reference_rejects_invalid_inputs(self):
        for mode, params in ((2, (2., 1., .02)), (1, (2., 1., 0.)), (0, (0., 1., .02))):
            with self.assertRaises(ValueError):
                reference(mode, params, 0., 0., .01)
        for h in (0., -.01, math.nan, math.inf):
            with self.assertRaises(ValueError):
                reference(2, (2., 1., 0.), 0., 0., h)

    def test_independent_grid(self):
        for name, (mode, nominal) in CONFIGS.items():
            core = self.core(name)
            params = tuple(map(f32, nominal))
            for h in (.008, .01, .012):
                for s in (-.2, -.02, -.001, -.00001, 0., .00001, .001, .02, .2):
                    for nu in (-.3, 0., .3):
                        self.assertTrue(core.reset(nu))
                        code, c = core.evaluate(s, 0., h)
                        self.assertEqual(code, 0)
                        p, a, nxt, _ = reference(mode, params, c[0], c[3], f32(h))
                        self.assertAlmostEqual(c[2], a, delta=4e-7)
                        self.assertAlmostEqual(c[4], nxt, delta=4e-7)
                        if mode:
                            self.assertAlmostEqual(c[1], p, delta=4e-8)

    def test_proper_three_equations_and_inclusion(self):
        core = self.core('proper')
        for h in (.008, .012, 1 / 128):
            h = f32(h)
            for s in (-.1, -.00002, 0., .00002, .1):
                for nu in (-.2, 0., .2):
                    core.reset(nu)
                    code, c = core.evaluate(s, 0., h)
                    self.assertEqual(code, 0)
                    error, z, a, old, nxt, xi, _ = c
                    self.assertLessEqual(abs(xi), 1.)
                    if z:
                        self.assertEqual(xi, math.copysign(1., z))
                    residuals = (z - (error + h * (a - nxt)),
                                 nxt - (old - h * xi),
                                 a - (-2 * math.sqrt(abs(z)) * xi + 2 * nxt - old))
                    self.assertLess(max(map(abs, residuals)), 3e-7)

    def test_exact_proper_boundaries_and_adjacent_float(self):
        core = self.core('proper')
        h, q = 1 / 128, 1 / 16384
        for sign in (-1, 1):
            for offset in (-1, 0, 1):
                s = sign * neighbor(q, offset)
                core.reset(.125)
                code, c = core.evaluate(s, 0., h)
                self.assertEqual(code, 0)
                self.assertEqual(c[6], 2 if offset <= 0 else (1 if sign > 0 else 3))
                p = reference(2, (2., 1., 0.), c[0], c[3], h)[0]
                self.assertLess(abs(p-c[1]) / max(abs(p), 1e-30), 2e-6)
                self.assertLess(candidate_residual(2, (2., 1., 0.), c, h), 2e-6)
                if offset <= 0:
                    self.assertEqual(c[1], 0.)
                    self.assertEqual(c[2], f32(.125 - 2 * s / h))

    def test_regularized_boundaries(self):
        core = self.core('rista')
        params = tuple(map(f32, CONFIGS['rista'][1]))
        for h in (.008, .012):
            h = f32(h)
            boundary = f32(params[2] + h * params[0] * math.sqrt(params[2]) + h*h*params[1])
            for sign in (-1, 1):
                for offset in (-1, 0, 1):
                    core.reset(.1)
                    code, c = core.evaluate(sign * neighbor(boundary, offset), 0., h)
                    self.assertEqual(code, 0)
                    p, a, nxt, _ = reference(1, params, c[0], c[3], h)
                    self.assertAlmostEqual(c[1], p, delta=4e-8)
                    self.assertAlmostEqual(c[2], a, delta=4e-7)
                    self.assertAlmostEqual(c[4], nxt, delta=4e-7)

    def test_float_branch_boundary_is_not_double_boundary(self):
        core = self.core('rista')
        params = tuple(map(f32, CONFIGS['rista'][1]))
        h = f32(.008)
        boundary = f32(f32(params[2] + f32(f32(h*params[0])*f32(math.sqrt(params[2])))) + f32(h*f32(h*params[1])))
        self.assertGreater(boundary, params[2] + h*params[0]*math.sqrt(params[2]) + h*h*params[1])
        for sign in (-1, 1):
            core.reset(.1)
            code, c = core.evaluate(sign*boundary, 0., h)
            self.assertEqual(code, 0)
            self.assertEqual(c[6], 0)
            self.assertLess(candidate_residual(1, params, c, h), 2e-6)
            c[6] = 1
            with self.assertRaises(AssertionError):
                candidate_residual(1, params, c, h)

    def test_residual_checks_reject_wrong_output_and_graph(self):
        core = self.core('proper')
        code, c = core.evaluate(.1, 0., .01)
        self.assertEqual(code, 0)
        c[2] += .01
        self.assertGreater(candidate_residual(2, (2., 1., 0.), c, f32(.01)), 2e-6)
        c[5] = -1.
        with self.assertRaises(AssertionError):
            candidate_residual(2, (2., 1., 0.), c, f32(.01))

    def test_symmetry_and_zero_nonzero_nu(self):
        for name in CONFIGS:
            core = self.core(name)
            for s in (.00001, .001, .1):
                core.reset(.2)
                code, positive = core.evaluate(s, 0., .008)
                core.reset(-.2)
                other_code, negative = core.evaluate(-s, 0., .008)
                self.assertEqual((code, other_code), (0, 0))
                self.assertEqual(positive[2], -negative[2])
                self.assertEqual(positive[4], -negative[4])
            core.reset(.2)
            code, c = core.evaluate(0., 0., .008)
            self.assertEqual(code, 0)
            self.assertEqual(c[2], f32(.2))
            self.assertEqual(c[4], f32(.2))

    def test_invalid_inputs_and_no_stale_commit(self):
        for name in CONFIGS:
            core = self.core(name)
            for velocity, h in ((math.nan, .01), (math.inf, .01), (.1, 0.), (.1, -.01), (.1, math.nan)):
                core.reset(.1)
                self.assertEqual(core.evaluate(.01, 0., .01)[0], 0)
                self.assertNotEqual(core.evaluate(velocity, 0., h)[0], 0)
                self.assertFalse(core.commit())
                self.assertEqual(core.state(), f32(.1))

    def test_state_isolation_and_reset_invalidation(self):
        for name in CONFIGS:
            core = self.core(name)
            core.reset(.1, 0)
            core.reset(-.2, 1)
            self.assertEqual(core.evaluate(.01, 0., .01, 0)[0], 0)
            self.assertEqual(core.evaluate(.01, 0., .01, 1)[0], 0)
            core.reset(.3, 0)
            self.assertFalse(core.commit(axis=0))
            self.assertTrue(core.commit(axis=1))
            self.assertFalse(core.commit(axis=1))
            self.assertEqual(core.state(0), f32(.3))
            self.assertEqual(core.state(2), 0.)

    def test_proper_is_not_compensated_regularized_kernel(self):
        proper, rista = self.core('proper'), self.core('rista')
        for core in (proper, rista):
            core.reset(.1)
        c = proper.evaluate(.00001, 0., .01)[1]
        other = rista.evaluate(.00001, 0., .01)[1]
        self.assertGreater(abs(c[2] - other[2]), .001)

    def test_target_derivative_and_zero_integral(self):
        for t in (0., 2., 11., 25., 36.):
            finite = (target(t + 1e-5)[0] - target(t - 1e-5)[0]) / 2e-5
            self.assertAlmostEqual(target(t)[1], finite, delta=1e-9)
        self.assertAlmostEqual(sum(target(i * .0036)[0] * .0036 for i in range(10000)), 0., delta=1e-12)
        for t in (0., 36.):
            self.assertAlmostEqual(target(t)[0], 0.)
            self.assertAlmostEqual(target(t)[1], 0.)

    def test_cascade_exact_semigroup_and_equilibrium(self):
        whole, integral = cascade([.3, -.2], .7, .012)
        half, part1 = cascade([.3, -.2], .7, .006)
        end, part2 = cascade(half, .7, .006)
        for actual, expected in zip(end, whole):
            self.assertAlmostEqual(actual, expected, delta=1e-15)
        self.assertAlmostEqual(part1 + part2, integral, delta=1e-15)
        end, area = cascade([.7, .7], .7, .012)
        self.assertEqual(end, [.7, .7])
        self.assertAlmostEqual(area, .7 * .012, delta=1e-15)

    def test_protection_is_not_output_reconstruction(self):
        self.assertEqual(protect(1., .3, .2, 'feasible_clipping'), (.25, .2, True))
        self.assertEqual(protect(-1., .1, .2, 'feasible_clipping'), (-.25, .2, True))
        self.assertEqual(protect(1., .1, .2, 'feasible_clipping'), (.25, .1, True))
        self.assertEqual(protect(.1, 5., 3., 'feasible_clipping'), (.1, 4., True))
        self.assertEqual(protect(1., .3, .2, 'ramp_positive'), (1., .3, False))

    def test_metrics_are_time_weighted_and_tv_not_error(self):
        metrics = Metrics()
        metrics.add(.008, 1., 2., .1, .2, False)
        metrics.add(.012, 2., 3., -.3, -.4, True)
        row = metrics.result()
        self.assertAlmostEqual(row['rmse'], math.sqrt(2.8))
        self.assertAlmostEqual(row['mean'], 1.6)
        self.assertAlmostEqual(row['correction_tv_per_s'], 20.)
        self.assertAlmostEqual(row['constrained_fraction'], .6)
        self.assertAlmostEqual(row['measured_mean'], 2.6)
        self.assertEqual(row['measured_peak_error'], 3.)

    def test_theory_not_claimed_for_alternating_or_engineering(self):
        for name in CONFIGS:
            self.assertIsNone(theoretical(name, 'alternating8_12ms', 'ramp_positive'))
            self.assertIsNone(theoretical(name, '8ms', 'noise'))
        self.assertAlmostEqual(theoretical('proper', '8ms', 'ramp_positive'), 6.4e-6)
        self.assertAlmostEqual(theoretical('proper', '12ms', 'ramp_negative'), -1.44e-5)


if __name__ == '__main__':
    unittest.main()
