#!/usr/bin/env python3
import math
import os
import unittest
from model_check import BASE, MATCHED, Kernel, effective, f32, prewarp, reference, shape, target

class BandwidthTests(unittest.TestCase):
    def setUp(self):
        self.kernels = []
    def tearDown(self):
        for kernel in self.kernels:
            kernel.close()
    def core(self, mode, parameters):
        kernel = Kernel(os.environ["RI04_BANDWIDTH_LIBRARY"], mode, parameters)
        self.kernels.append(kernel)
        return kernel
    def test_prewarp_domain(self):
        for params in ((0., 1., .02, .01), (2., 1., .02, .1), (.1, 100., .02, .01),
                       (2., 1., .02, math.nan), (math.inf, 1., .02, .01),
                       (1e308, 1., .001, .01), (2., 1e308, .001, .01),
                       (2., 1., 1e-300, .01), (2., 1., .02, 1e-300),
                       (1e-300, 1e-310, .02, .01)):
            with self.assertRaises(ValueError):
                prewarp(*params)
    def test_prewarp_matches_only_reference_period(self):
        self.assertEqual(prewarp(*BASE, .01), MATCHED)
        alpha, beta = BASE[0] / math.sqrt(BASE[2]), BASE[1] / BASE[2]
        at_reference = effective(MATCHED, .01)
        self.assertAlmostEqual(at_reference[0], alpha, places=12)
        self.assertAlmostEqual(at_reference[1], beta, places=12)
        for h in (.008, .012):
            actual = effective(MATCHED, h)
            self.assertGreater(abs(actual[0] - alpha), .1)
            self.assertLess(abs(actual[0] / alpha - 1), .04)
            self.assertLess(abs(actual[1] / beta - 1), .04)
    def test_actual_float_cores_local_equivalence(self):
        sta, ista = self.core(0, BASE), self.core(1, MATCHED)
        for s in (-.01, -.001, 0., .001, .01):
            for nu in (-.1, 0., .1):
                sta.reset(nu); ista.reset(nu)
                code0, c0 = sta.evaluate(s, 0., .01)
                code1, c1 = ista.evaluate(s, 0., .01)
                self.assertEqual((code0, code1), (0, 0))
                self.assertAlmostEqual(c0[2], c1[2], delta=8e-8)
                self.assertAlmostEqual(c0[4], c1[4], delta=8e-8)
    def test_reference_grid_and_residual(self):
        for mode, params in ((0, BASE), (1, BASE), (1, MATCHED)):
            core = self.core(mode, params)
            params = tuple(map(f32, params))
            for h in (.008, .01, .012):
                for s in (-.1, -.02, -.001, 0., .001, .02, .1):
                    for nu in (-.1, 0., .1):
                        core.reset(nu)
                        code, c = core.evaluate(s, 0., h)
                        self.assertEqual(code, 0)
                        p, a, nxt = reference(mode, params, c[0], f32(nu), f32(h))
                        self.assertAlmostEqual(c[2], a, delta=3e-7)
                        self.assertAlmostEqual(c[4], nxt, delta=3e-7)
                        if mode:
                            self.assertAlmostEqual(c[1], p, delta=3e-8)
                            psi, rho = shape(c[1], params[2])
                            residual = c[1] + f32(h)*params[0]*psi + f32(h)**2*params[1]*rho - c[0]
                            self.assertLess(abs(residual), 3e-8)
    def test_stable_small_and_large_finite_roots(self):
        core = self.core(1, MATCHED)
        params = tuple(map(f32, MATCHED))
        for s in (1e-20, -1e-20, 1e-10, -1e-10, 1e8, -1e8, 1e30, -1e30):
            core.reset(0.)
            code, c = core.evaluate(s, 0., .01)
            self.assertEqual(code, 0)
            p, a, nxt = reference(1, params, c[0], 0., f32(.01))
            self.assertLess(abs(c[1] - p) / abs(p), 3e-6)
            self.assertLess(abs(c[2] - a) / abs(a), 3e-6)
            self.assertLess(abs(c[4] - nxt) / abs(nxt), 3e-6)
    def test_inner_outer_boundary_neighbors(self):
        import struct
        for params in (BASE, MATCHED):
            core = self.core(1, params)
            for h in (.008, .012):
                boundary = f32(params[2] + h * params[0] * math.sqrt(params[2]) + h*h*params[1])
                bits = struct.unpack("I", struct.pack("f", boundary))[0]
                for delta in (-1, 0, 1):
                    s = struct.unpack("f", struct.pack("I", bits + delta))[0]
                    for sign in (-1, 1):
                        core.reset(.1)
                        code, c = core.evaluate(sign*s, 0., h)
                        self.assertEqual(code, 0)
                        p, a, nxt = reference(1, tuple(map(f32, params)), c[0], f32(.1), f32(h))
                        self.assertAlmostEqual(c[1], p, delta=3e-8)
                        self.assertAlmostEqual(c[2], a, delta=3e-7)
    def test_invalid_dt_and_measurement_preserve_state(self):
        for mode in (0, 1):
            core = self.core(mode, BASE); core.reset(.1)
            for v, h in ((.01, 0.), (.01, -.01), (.01, math.nan), (math.inf, .01), (math.nan, .01)):
                self.assertNotEqual(core.evaluate(v, 0., h)[0], 0)
                self.assertEqual(core.state(), f32(.1))
    def test_evaluation_no_commit_and_duplicate_commit_rejected(self):
        for mode in (0, 1):
            core = self.core(mode, BASE); core.reset(.1)
            code, c = core.evaluate(.001, 0., .01)
            self.assertEqual(code, 0); self.assertEqual(core.state(), f32(.1))
            self.assertEqual(core.commit(c[4]), 0)
            self.assertNotEqual(core.commit(c[4]), 0)
    def test_waveform_derivative_and_zero_endpoints(self):
        for t in (0., 4., 8., 13., 25., 32.):
            numerical = (target(t+1e-5)[0] - target(t-1e-5)[0]) / 2e-5
            self.assertAlmostEqual(target(t)[1], numerical, delta=1e-9)
        self.assertAlmostEqual(target(0.)[0], 0.)
        self.assertAlmostEqual(target(32.)[0], 0.)

if __name__ == "__main__":
    unittest.main()
