"""Offline numerical tests only; no simulator, old-analyzer mutation, or flight."""
import copy
from fractions import Fraction
import math
import unittest

import numpy as np

import checker as c


def values(**changes):
    args = dict(s=c.binary32(.005658068228513002), h=c.binary32(.012),
                lambda2=c.binary32(1), epsilon=c.binary32(.02),
                nu_before=c.binary32(-4), nu_ideal=c.binary32(-4.003394603729248),
                declared_lambda2=1, declared_epsilon=.02)
    args.update(changes)
    return args


def candidate(args):
    """Test fixture only. Fraction oracle inside checker remains independent."""
    s, h, l2, eps, nu = [np.float32(args[key]) for key in ('s', 'h', 'lambda2', 'epsilon', 'nu_before')]
    rho = np.float32(s / eps) if abs(s) <= eps else np.float32(1 if s > 0 else -1)
    step = np.float32(h * l2) if s != 0 else np.float32(0)
    with np.errstate(over='ignore', under='ignore', invalid='ignore'):
        return float(np.float32(nu - np.float32(step * rho)))


def valid(**changes):
    args = values(**changes)
    args['nu_ideal'] = candidate(args)
    return args


class ExactRounding(unittest.TestCase):
    def test_exact_float_bit_roundtrip_including_signed_zero(self):
        for bits in (0, 0x80000000, 1, 0x80000001, 0x7fffff, 0x800000,
                     0x3f800000, 0xbf800000, 0x7f7fffff, 0xff7fffff):
            with self.subTest(bits=hex(bits)):
                self.assertEqual(c._round_binary32(c._fraction(bits), negative_zero=bool(bits >> 31)), bits)

    def test_positive_ties_even_both_parities(self):
        self.assertEqual(c._round_binary32(Fraction(1) + Fraction(1, 1 << 24)), 0x3f800000)
        self.assertEqual(c._round_binary32(Fraction(1) + Fraction(3, 1 << 24)), 0x3f800002)

    def test_negative_ties_even_both_parities(self):
        self.assertEqual(c._round_binary32(-Fraction(1) - Fraction(1, 1 << 24)), 0xbf800000)
        self.assertEqual(c._round_binary32(-Fraction(1) - Fraction(3, 1 << 24)), 0xbf800002)

    def test_tie_neighbors_not_always_round_up(self):
        tie = Fraction(1) + Fraction(1, 1 << 24)
        self.assertEqual(c._round_binary32(tie - Fraction(1, 1 << 60)), 0x3f800000)
        self.assertEqual(c._round_binary32(tie + Fraction(1, 1 << 60)), 0x3f800001)

    def test_subnormal_midpoint_and_minimum_normal_carry(self):
        self.assertEqual(c._round_binary32(Fraction(1, 1 << 150)), 0)
        self.assertEqual(c._round_binary32(Fraction(3, 1 << 150)), 2)
        self.assertEqual(c._round_binary32(c._pow2(-126) - c._pow2(-150)), 0x800000)

    def test_overflow_boundary_and_neighbor(self):
        tie = c._fraction(0x7f7fffff) + c._pow2(103)
        self.assertEqual(c._round_binary32(tie - 1), 0x7f7fffff)
        self.assertEqual(c._round_binary32(tie), 0x7f800000)
        self.assertEqual(c._round_binary32(-tie), 0xff800000)

    def test_zero_sign_operations_and_exact_cancellation(self):
        self.assertEqual(c._exact_operation('divide', 0x80000000, 0x3f800000)[0], 0x80000000)
        self.assertEqual(c._exact_operation('multiply', 0, 0xbf800000)[0], 0x80000000)
        self.assertEqual(c._exact_operation('subtract', 0x80000000, 0)[0], 0x80000000)
        self.assertEqual(c._exact_operation('subtract', 0x80000000, 0x80000000)[0], 0)
        self.assertEqual(c._exact_operation('subtract', 0xbf800000, 0xbf800000)[0], 0)

    def test_nonfinite_bits_have_no_rational_value(self):
        for bits in (0x7f800000, 0xff800000, 0x7fc00000):
            with self.subTest(bits=bits), self.assertRaises(c.CandidateAuditError):
                c._fraction(bits)


class CandidatePositive(unittest.TestCase):
    def test_actual_run015_bad_frame_without_rejudging_run(self):
        result = c.check_candidate(**values())
        self.assertTrue(result['candidate_consistent'])
        self.assertFalse(result['flight_accepted'])
        self.assertFalse(result['execution_authority_granted'])
        # Independent exact equation using the consumed float epsilon.
        residual = Fraction(result['exact_residual']['numerator']) / int(result['exact_residual']['denominator'])
        self.assertGreater(abs(residual), Fraction(2, 10_000_000))
        self.assertLess(abs(residual), Fraction(1, 1 << 22))
        self.assertEqual(result['trace']['candidate']['bits'], 'c0801bcf')

    def test_actual_bad_frame_positive_mirror(self):
        original = values()
        mirror = values(**{key: -original[key] for key in ('s', 'nu_before', 'nu_ideal')})
        a, b = c.check_candidate(**original), c.check_candidate(**mirror)
        self.assertEqual(a['exact_residual']['value'], -b['exact_residual']['value'])

    def test_zero_error_preserves_nonzero_old_nu(self):
        for zero in (0., -0.):
            args = valid(s=zero, nu_before=c.binary32(2.3))
            result = c.check_candidate(**args)
            self.assertEqual(result['trace']['step']['value'], 0)
            self.assertEqual(result['trace']['candidate']['value'], args['nu_before'])

    def test_zero_old_nu_signed_zero_defined_by_ieee_operations(self):
        for s in (0., -0.):
            for nu in (0., -0.):
                with self.subTest(s=s, nu=nu):
                    c.check_candidate(**valid(s=s, nu_before=nu))

    def test_epsilon_boundary_and_exact_adjacent_values_both_signs(self):
        eps = np.float32(.02)
        for magnitude, branch in ((np.nextafter(eps, np.float32(0)), 'inside_or_boundary'),
                                  (eps, 'inside_or_boundary'),
                                  (np.nextafter(eps, np.float32(1)), 'outside')):
            for sign in (-1, 1):
                with self.subTest(magnitude=float(magnitude), sign=sign):
                    result = c.check_candidate(**valid(s=float(sign * magnitude)))
                    self.assertEqual(result['branch'], branch)

    def test_nonzero_nu_and_unequal_lambda2(self):
        args = valid(nu_before=c.binary32(.83), lambda2=c.binary32(.17), declared_lambda2=.17)
        result = c.check_candidate(**args)
        self.assertNotEqual(result['trace']['candidate']['value'], args['nu_before'])

    def test_state_bound_four_adjacent_before_values(self):
        for sign in (-1, 1):
            for n in (np.nextafter(np.float32(4), np.float32(0)), np.float32(4)):
                args = valid(s=c.binary32(-sign * .01), nu_before=float(sign * n))
                result = c.check_candidate(**args)
                self.assertGreater(abs(result['trace']['candidate']['value']), 4)

    def test_ideal_can_cross_state_bound_without_being_applied(self):
        args = values()
        result = c.check_candidate(**args)
        self.assertLess(result['trace']['candidate']['value'], -4)
        self.assertNotIn('applied', result)
        self.assertIn('raw/applied checks not performed', result['scope'])

    def test_min_max_existing_h_and_epsilon_domain(self):
        for h in (.002, .04):
            for epsilon in (.001, 1):
                with self.subTest(h=h, epsilon=epsilon):
                    c.check_candidate(**valid(h=c.binary32(h), epsilon=c.binary32(epsilon), declared_epsilon=epsilon))

    def test_frozen_decimal_is_quantized_once_but_record_is_not_repaired(self):
        args = values()
        self.assertNotEqual(args['epsilon'], args['declared_epsilon'])
        c.check_candidate(**args)
        with self.assertRaisesRegex(c.CandidateAuditError, 'exact recorded binary32'):
            c.check_candidate(**values(epsilon=.02))

    def test_deterministic_257_sample_arithmetic_grid(self):
        # Test inputs, not simulation seeds or a new experiment manifest.
        for i in range(257):
            sign = 1 if i % 2 else -1
            eps = (.001, .01, .02, 1)[i % 4]
            l2 = (.1, 1, .37)[i % 3]
            args = valid(s=c.binary32(sign * eps * (i + 1) / 127), h=c.binary32((.008, .012)[i % 2]),
                         nu_before=c.binary32(sign * (i - 128) / 32),
                         epsilon=c.binary32(eps), declared_epsilon=eps,
                         lambda2=c.binary32(l2), declared_lambda2=l2)
            with self.subTest(i=i):
                result = c.check_candidate(**args)
                self.assertLessEqual(abs(result['exact_residual']['value']), result['absolute_error_bound']['value'])


class CandidateNegative(unittest.TestCase):
    def test_one_ulp_candidate_mutation_rejected_both_directions(self):
        base = values()
        for toward in (-math.inf, math.inf):
            changed = float(np.nextafter(np.float32(base['nu_ideal']), np.float32(toward)))
            with self.subTest(toward=toward), self.assertRaisesRegex(c.CandidateAuditError, 'exact binary32 candidate'):
                c.check_candidate(**values(nu_ideal=changed))

    def test_applied_clipped_nu_cannot_replace_ideal(self):
        with self.assertRaisesRegex(c.CandidateAuditError, 'exact binary32 candidate'):
            c.check_candidate(**values(nu_ideal=-4.))

    def test_omitted_h(self):
        args = values()
        args['nu_ideal'] = c.binary32(args['nu_before'] - args['lambda2'] * args['s'] / args['epsilon'])
        with self.assertRaisesRegex(c.CandidateAuditError, 'exact binary32 candidate'):
            c.check_candidate(**args)

    def test_double_h(self):
        args = values()
        args['nu_ideal'] = c.binary32(args['nu_before'] - args['h']**2 * args['lambda2'] * args['s'] / args['epsilon'])
        with self.assertRaisesRegex(c.CandidateAuditError, 'exact binary32 candidate'):
            c.check_candidate(**args)

    def test_wrong_sign(self):
        args = values()
        args['nu_ideal'] = c.binary32(args['nu_before'] + args['h'] * args['lambda2'] * args['s'] / args['epsilon'])
        with self.assertRaisesRegex(c.CandidateAuditError, 'exact binary32 candidate'):
            c.check_candidate(**args)

    def test_wrong_old_nu(self):
        with self.assertRaisesRegex(c.CandidateAuditError, 'exact binary32 candidate'):
            c.check_candidate(**values(nu_before=c.binary32(-3.99)))

    def test_changed_parameter_and_declared_configuration(self):
        for changes in (dict(epsilon=c.binary32(.01)), dict(lambda2=c.binary32(.5)),
                        dict(declared_epsilon=.03), dict(declared_lambda2=.9)):
            with self.subTest(changes=changes), self.assertRaisesRegex(c.CandidateAuditError, 'frozen binary32'):
                c.check_candidate(**values(**changes))

    def test_all_record_fields_reject_nan_inf(self):
        for key in ('s', 'h', 'lambda2', 'epsilon', 'nu_before', 'nu_ideal'):
            for bad in (math.nan, math.inf, -math.inf):
                with self.subTest(key=key, bad=bad), self.assertRaises(c.CandidateAuditError):
                    c.check_candidate(**values(**{key: bad}))

    def test_frozen_parameter_rejects_nan_inf(self):
        for key in ('declared_lambda2', 'declared_epsilon'):
            for bad in (math.nan, math.inf, -math.inf):
                with self.subTest(key=key, bad=bad), self.assertRaises(c.CandidateAuditError):
                    c.check_candidate(**values(**{key: bad}))

    def test_nonbinary32_record_is_not_silently_rounded(self):
        for key, bad in (('s', .0056580683), ('h', .012), ('nu_before', -.123456789)):
            with self.subTest(key=key), self.assertRaisesRegex(c.CandidateAuditError, 'exact recorded binary32'):
                c.check_candidate(**values(**{key: bad}))

    def test_higher_precision_or_large_integer_is_not_narrowed_silently(self):
        for bad in (Fraction(1) + Fraction(1, 1 << 100),
                    np.nextafter(np.longdouble(1), np.longdouble(2)), (1 << 60) + 1):
            with self.subTest(type=type(bad).__name__), self.assertRaises(c.CandidateAuditError):
                c.check_candidate(**values(nu_before=bad))

    def test_declared_configuration_is_json_number_semantics_not_arbitrary_precision(self):
        for bad in (Fraction(1) + Fraction(1, 1 << 100),
                    np.nextafter(np.longdouble(1), np.longdouble(2)), (1 << 60) + 1):
            with self.subTest(type=type(bad).__name__), self.assertRaises(c.CandidateAuditError):
                c.check_candidate(**values(declared_lambda2=bad))

    def test_boolean_string_and_complex_payloads(self):
        for bad in (True, False, '0.02', complex(.02), None):
            with self.subTest(bad=bad), self.assertRaises(c.CandidateAuditError):
                c.check_candidate(**values(epsilon=bad))

    def test_h_outside_domain_and_exact_neighbors(self):
        for bad in (0., -.008, .001, .041,
                    np.nextafter(np.float32(.002), np.float32(0)),
                    np.nextafter(np.float32(.04), np.float32(1))):
            with self.subTest(bad=bad), self.assertRaisesRegex(c.CandidateAuditError, 'h outside'):
                c.check_candidate(**values(h=c.binary32(bad)))

    def test_epsilon_outside_domain(self):
        for bad in (0., -.01, .0001, 1.1,
                    np.nextafter(np.float32(.001), np.float32(0))):
            with self.subTest(bad=bad), self.assertRaisesRegex(c.CandidateAuditError, 'epsilon outside'):
                c.check_candidate(**values(epsilon=c.binary32(bad), declared_epsilon=float(bad)))

    def test_lambda_nonpositive_or_subnormal(self):
        for bad in (0., -.1, c._from_bits(1)):
            with self.subTest(bad=bad), self.assertRaisesRegex(c.CandidateAuditError, 'lambda2 must'):
                c.check_candidate(**values(lambda2=c.binary32(bad), declared_lambda2=bad))

    def test_subnormal_rho(self):
        with self.assertRaisesRegex(c.CandidateAuditError, 'underflow'):
            c.check_candidate(**values(s=c._from_bits(1), epsilon=1., declared_epsilon=1.))

    def test_underflow_in_h_lambda2_product(self):
        tiny = c._from_bits(0x800000)
        with self.assertRaisesRegex(c.CandidateAuditError, 'underflow'):
            c.check_candidate(**values(lambda2=tiny, declared_lambda2=tiny))

    def test_underflow_in_step_rho_product(self):
        with self.assertRaisesRegex(c.CandidateAuditError, 'underflow'):
            c.check_candidate(**values(s=c._from_bits(0x800000), epsilon=1., declared_epsilon=1.))

    def test_candidate_subtraction_overflow(self):
        maximum = c._from_bits(0x7f7fffff)
        with self.assertRaisesRegex(c.CandidateAuditError, 'Nonfinite evaluated'):
            c.check_candidate(**values(s=-1., lambda2=maximum, declared_lambda2=maximum,
                                      nu_before=maximum, nu_ideal=maximum))

    def test_input_outside_binary32_range(self):
        with self.assertRaises(c.CandidateAuditError):
            c.check_candidate(**values(nu_before=1e300))

    def test_does_not_modify_input_or_take_applied_argument(self):
        args = values(); original = copy.deepcopy(args)
        c.check_candidate(**args)
        self.assertEqual(args, original)
        with self.assertRaises(TypeError):
            c.check_candidate(**args, nu_applied=-4.)


if __name__ == '__main__':
    unittest.main(verbosity=2)
