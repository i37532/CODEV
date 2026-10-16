#!/usr/bin/env python3
"""Independent R00 algebra/ideal-object audit; no PX4/flight dependencies."""
import cmath
import math
import unittest


def psi(s, epsilon):
    if not math.isfinite(epsilon) or epsilon <= 0:
        raise ValueError("epsilon must be finite and positive")
    return s / math.sqrt(epsilon) if abs(s) <= epsilon else math.copysign(math.sqrt(abs(s)), s)


def rho(s, epsilon):
    if not math.isfinite(epsilon) or epsilon <= 0:
        raise ValueError("epsilon must be finite and positive")
    return s / epsilon if abs(s) < epsilon else math.copysign(1., s)


def ideal_step(s, nu, h, l1, l2, epsilon, disturbance=0.):
    """Old nu produces acceleration; plant is an independent exact ZOH integrator."""
    acceleration = -l1 * psi(s, epsilon) + nu
    next_s = s + h * (acceleration + disturbance)
    next_nu = nu - h * l2 * rho(s, epsilon)
    return next_s, next_nu


def local_matrix(l1, l2, epsilon, h):
    alpha, beta = l1 / math.sqrt(epsilon), l2 / epsilon
    return ((1 - h * alpha, h), (-h * beta, 1.))


def eigenvalues(l1, l2, epsilon, h):
    a = local_matrix(l1, l2, epsilon, h)
    return matrix_eigenvalues(a)


def matrix_eigenvalues(a):
    trace, determinant = a[0][0] + a[1][1], a[0][0] * a[1][1] - a[0][1] * a[1][0]
    root = cmath.sqrt(trace * trace - 4 * determinant)
    return ((trace + root) / 2, (trace - root) / 2)


def product(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(2)) for j in range(2)) for i in range(2))


def jury(l1, l2, epsilon, h):
    alpha, beta = l1 / math.sqrt(epsilon), l2 / epsilon
    terms = (h * h * beta, 4 - 2 * h * alpha + h * h * beta, h * alpha - h * h * beta)
    return all(x > 0 for x in terms), terms


def first_stability_boundary(l1, l2, epsilon):
    alpha, beta = l1 / math.sqrt(epsilon), l2 / epsilon
    det_boundary = alpha / beta
    # Factor epsilon out first to preserve the known l1^2=4*l2 equality.
    discriminant = (l1 * l1 - 4 * l2) / epsilon
    if discriminant < -1e-12 * max(alpha * alpha, 4 * beta):
        return det_boundary
    minus_one_boundary = 4 / (alpha + math.sqrt(max(0., discriminant)))
    return min(det_boundary, minus_one_boundary)


def audit_summary():
    sets = [("source_high_z", 20., 12., .01), ("ax05_xy_candidate", .5, .1, .01),
            ("ax05_z_candidate", 2., 1., .02)]
    records = []
    for name, l1, l2, epsilon in sets:
        records.append(dict(name=name, lambda1=l1, lambda2=l2, epsilon=epsilon,
                            first_boundary_s=first_stability_boundary(l1, l2, epsilon),
                            periods=[dict(h_s=h, schur=jury(l1, l2, epsilon, h)[0],
                                          spectral_radius=max(abs(e) for e in eigenvalues(l1, l2, epsilon, h)),
                                          eigenvalues=[[e.real, e.imag] for e in eigenvalues(l1, l2, epsilon, h)])
                                     for h in [.002, .005, .01, .012, .016, .04]]))
    grid = []
    for name, l1, l2 in [("ax05_xy", .5, .1), ("ax05_z", 2., 1.)]:
        for epsilon in [.0025, .005, .01, .02, .04, .08]:
            grid.append(dict(name=name, epsilon=epsilon,
                             first_boundary_s=first_stability_boundary(l1, l2, epsilon),
                             maximum_h_s=.04, schur_at_max_h=jury(l1, l2, epsilon, .04)[0]))
    alternating = product(local_matrix(20., 12., .01, .012), local_matrix(20., 12., .01, .008))
    return dict(local_models=records, epsilon_grid=grid, epsilon_grid_size=12,
                source_high_z_alternating_8_12ms=dict(matrix=alternating,
                    two_step_spectral_radius=max(abs(e) for e in matrix_eigenvalues(alternating)),
                    note="Ideal in-layer two-step stability is not a lagged/limited aircraft guarantee"),
                proposed_numeric_domain_m_s=[.001, 1.], proposed_first_candidate_m_s=[.01, .01, .02],
                status="offline screening only; R01 must validate lag/noise/constraints/variable time")


class MathProbe(unittest.TestCase):
    def test_01_piecewise_product_equivalence(self):
        for epsilon in [.001, .01, .02, .1, 1.]:
            for s in [-10., -epsilon, -epsilon / 2, 0., epsilon / 2, epsilon, 10.]:
                product = math.sqrt(max(abs(s), epsilon)) * max(-1., min(s / epsilon, 1.))
                self.assertAlmostEqual(psi(s, epsilon), product, places=14)

    def test_02_sign_mapping_nonzero_nu(self):
        for s in [-.2, -.01, 0., .01, .2]:
            for nu in [-.3, 0., .3]:
                self.assertAlmostEqual(-2 * psi(s, .02) + nu, 2 * psi(-s, .02) + nu)
                self.assertAlmostEqual(nu - .01 * rho(s, .02), nu + .01 * rho(-s, .02))

    def test_03_exact_boundary_and_neighbors(self):
        for epsilon in [.001, .01, .02, 1.]:
            for sign in [-1., 1.]:
                center = sign * epsilon
                self.assertAlmostEqual(psi(center, epsilon), sign * math.sqrt(epsilon), places=14)
                for toward in [-math.inf, math.inf, 0.]:
                    self.assertAlmostEqual(psi(math.nextafter(center, toward), epsilon), psi(center, epsilon), places=14)

    def test_04_explicit_old_nu(self):
        s, nu, h, l1, l2, epsilon = .01, .2, .01, 2., 1., .02
        next_s, next_nu = ideal_step(s, nu, h, l1, l2, epsilon)
        self.assertAlmostEqual(next_s, s + h * (-l1 * psi(s, epsilon) + nu))
        self.assertNotAlmostEqual(next_s, s + h * (-l1 * psi(s, epsilon) + next_nu), places=12)

    def test_05_jury_vs_direct_eigenvalues(self):
        for l1, l2 in [(.5, .1), (2., 1.), (20., 12.), (.1, 10.)]:
            for epsilon in [.001, .01, .02, .1]:
                for h in [.002, .005, .01, .012, .016, .04, .15, .3]:
                    radius = max(abs(e) for e in eigenvalues(l1, l2, epsilon, h))
                    if abs(radius - 1) > 1e-10:
                        self.assertEqual(jury(l1, l2, epsilon, h)[0], radius < 1)

    def test_06_high_z_stability_boundary(self):
        boundary = first_stability_boundary(20., 12., .01)
        self.assertAlmostEqual(boundary, .01031947467255235, places=15)
        self.assertTrue(jury(20., 12., .01, boundary * (1 - 1e-6))[0])
        self.assertFalse(jury(20., 12., .01, boundary * (1 + 1e-6))[0])
        self.assertFalse(jury(20., 12., .01, .012)[0])

    def test_07_ax05_epsilon_domain(self):
        for l1, l2, minimum in [(.5, .1, 6.4e-5), (2., 1., .0004)]:
            self.assertFalse(jury(l1, l2, minimum * .99, .04)[0])
            self.assertTrue(jury(l1, l2, minimum * 1.01, .04)[0])
        self.assertTrue(all(r["schur_at_max_h"] for r in audit_summary()["epsilon_grid"]))

    def test_08_independent_zoh_matches_local_matrix(self):
        for l1, l2, epsilon in [(.5, .1, .01), (2., 1., .02), (20., 12., .01)]:
            for h in [.002, .005, .01, .04]:
                s, nu = epsilon / 20, -.003
                matrix = local_matrix(l1, l2, epsilon, h)
                actual = ideal_step(s, nu, h, l1, l2, epsilon)
                expected = (matrix[0][0] * s + matrix[0][1] * nu,
                            matrix[1][0] * s + matrix[1][1] * nu)
                self.assertAlmostEqual(actual[0], expected[0], places=15)
                self.assertAlmostEqual(actual[1], expected[1], places=15)

    def test_09_constant_disturbance_exact_equilibrium(self):
        for d in [-.2, 0., .2]:
            for h in [.002, .01, .04]:
                self.assertEqual(ideal_step(0., -d, h, 2., 1., .02, d), (0., -d))

    def test_10_ramp_disturbance_particular_solution(self):
        # In-layer ramp d[k+1]=d[k]+r*h has s*=r/beta, not generic exact zero.
        for rate in [-.05, 0., .05]:
            h, epsilon, l1, l2 = .01, .02, 2., 1.
            alpha, beta = l1 / math.sqrt(epsilon), l2 / epsilon
            s, disturbance = rate / beta, .1
            nu = alpha * s - disturbance
            next_s, next_nu = ideal_step(s, nu, h, l1, l2, epsilon, disturbance)
            self.assertAlmostEqual(next_s, s, places=14)
            self.assertAlmostEqual(next_nu, alpha * s - (disturbance + rate * h), places=14)

    def test_11_convergence_ideal_fixed_period(self):
        for h in [.005, .01, .04]:
            s, nu, d = .001, .003, .1
            for _ in range(math.ceil(12 / h)):
                s, nu = ideal_step(s, nu, h, 2., 1., .02, d)
            self.assertLess(abs(s), 1e-10)
            self.assertLess(abs(nu + d), 1e-9)

    def test_12_invalid_epsilon_rejected(self):
        for epsilon in [0., -1., math.inf, math.nan]:
            with self.assertRaises(ValueError):
                psi(0., epsilon)
            with self.assertRaises(ValueError):
                rho(0., epsilon)

    def test_13_tiny_error_piecewise_no_ratio_overflow(self):
        # Huge finite s/epsilon would overflow in the product form; piecewise avoids it.
        self.assertTrue(math.isfinite(psi(1e308, .001)))
        self.assertEqual(rho(1e308, .001), 1.)
        self.assertEqual(psi(0., .001), 0.)

    def test_14_zero_gain_not_asymptotically_stable(self):
        self.assertFalse(jury(0., 1., .02, .01)[0])
        self.assertFalse(jury(2., 0., .02, .01)[0])

    def test_15_alternating_time_not_fixed_time(self):
        l1, l2, epsilon = 20., 12., .01
        self.assertFalse(jury(l1, l2, epsilon, .012)[0])
        matrix = product(local_matrix(l1, l2, epsilon, .012), local_matrix(l1, l2, epsilon, .008))
        self.assertLess(max(abs(e) for e in matrix_eigenvalues(matrix)), 1.)
        # Independently advance actual ZOH-object states, keeping the trajectory
        # inside the boundary layer, and compare to a two-step matrix product.
        s, nu = .00001, -.00003
        expected = (matrix[0][0] * s + matrix[0][1] * nu, matrix[1][0] * s + matrix[1][1] * nu)
        for h in [.008, .012]:
            s, nu = ideal_step(s, nu, h, l1, l2, epsilon)
        self.assertAlmostEqual(s, expected[0], places=15)
        self.assertAlmostEqual(nu, expected[1], places=15)


if __name__ == "__main__":
    unittest.main(verbosity=2)
