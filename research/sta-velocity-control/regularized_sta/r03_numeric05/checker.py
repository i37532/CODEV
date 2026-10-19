"""Offline audit of ONE regularized-STA ideal nu candidate, not acceptance.

Declared arithmetic: IEEE-754 binary32, round-to-nearest/ties-to-even after
division, multiplication and subtraction; no FMA, reassociation, reciprocal
approximation or flush-to-zero. Recorded inputs must already be binary32.
The frozen decimal configuration is separately quantized once to binary32.

Two routes must agree: NumPy binary32 operations and an independent exact
rational rounder. The latter rounds using integer quotient/remainder and IEEE
exponent/significand encoding, not NumPy, struct's float conversion, or the
C++ kernel. Its unrounded real equation also explains accumulated rounding.

This does NOT verify s=v-v_sp, timestamp provenance, that nu_before is the
correct lifecycle state, HTE, Psi/raw output, protected/applied nu, saturation,
full-kernel validity, flight safety or authorization. Those remain separate
checks. It neither imports nor overrides any frozen analyzer/runner, changes
no prior result or tolerance, and grants no permission to fly.
"""
from fractions import Fraction
import math
import struct

import numpy as np


class CandidateAuditError(ValueError):
    """Input, declared arithmetic, or recorded ideal candidate is inconsistent."""


def _from_bits(bits):
    return struct.unpack('>f', struct.pack('>I', bits))[0]


def _bits(value):
    return struct.unpack('>I', struct.pack('>f', float(value)))[0]


def binary32(value):
    """Convert frozen JSON-number semantics, never arbitrary decimal precision.

    Accept Python float/int and NumPy float32/float64, with integers restricted
    to the exact binary64 integer range. Fraction/Decimal/longdouble are not a
    configuration format here: casting them through float could double-round.
    Exact Fraction arithmetic is used only by the independent internal oracle.
    """
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.float32, np.float64)):
        raise CandidateAuditError('A supported nonboolean JSON/binary32/binary64 number is required')
    if isinstance(value, int) and abs(value) > 1 << 53:
        raise CandidateAuditError('JSON integer outside the supported exact binary64 range')
    try:
        rounded = _from_bits(_bits(value))
    except (OverflowError, ValueError, struct.error) as exc:
        raise CandidateAuditError('Value cannot be represented as finite binary32') from exc
    if not math.isfinite(rounded):
        raise CandidateAuditError('Nonfinite binary32 input')
    return rounded


def _recorded(value, name):
    rounded = binary32(value)
    # Do not first narrow the original value: that would hide precision loss.
    if value != rounded:
        raise CandidateAuditError(name + ' is not an exact recorded binary32 value')
    return _bits(rounded)


def _pow2(exponent):
    return Fraction(1 << exponent, 1) if exponent >= 0 else Fraction(1, 1 << -exponent)


def _fraction(bits):
    sign = -1 if bits >> 31 else 1
    exponent, mantissa = (bits >> 23) & 255, bits & 0x7fffff
    if exponent == 255:
        raise CandidateAuditError('Exact rational cannot represent NaN/infinity')
    if exponent == 0:
        return sign * mantissa * _pow2(-149)
    return sign * ((1 << 23) + mantissa) * _pow2(exponent - 150)


def _nearest_even_integer(value):
    quotient, remainder = divmod(value.numerator, value.denominator)
    twice = remainder * 2
    return quotient + int(twice > value.denominator or
                          (twice == value.denominator and quotient & 1))


def _round_binary32(value, negative_zero=False):
    """Exact rational -> IEEE bits, including ties, subnormals and overflow."""
    value = Fraction(value)
    sign = 0x80000000 if value < 0 or (not value and negative_zero) else 0
    value = abs(value)
    if not value:
        return sign
    if value < _pow2(-126):
        # A carry to 2**23 is precisely the smallest normal encoding.
        return sign | _nearest_even_integer(value / _pow2(-149))
    exponent = value.numerator.bit_length() - value.denominator.bit_length()
    if value < _pow2(exponent):
        exponent -= 1
    if exponent > 127:
        return sign | 0x7f800000
    significand = _nearest_even_integer(value / _pow2(exponent - 23))
    if significand == 1 << 24:
        exponent += 1
        significand >>= 1
    if exponent > 127:
        return sign | 0x7f800000
    return sign | ((exponent + 127) << 23) | (significand - (1 << 23))


def _exact_operation(operation, left, right):
    a, b = _fraction(left), _fraction(right)
    if operation == 'divide':
        value = a / b
        negative_zero = bool((left ^ right) >> 31)
    elif operation == 'multiply':
        value = a * b
        negative_zero = bool((left ^ right) >> 31)
    elif operation == 'subtract':
        value = a - b
        # RN cancellation of nonzero equal numbers is +0. Only -0-(+0)
        # produces -0 when subtracting two zero inputs.
        negative_zero = not a and not b and bool(left >> 31) and not (right >> 31)
    else:
        raise CandidateAuditError('Unknown exact operation')
    return _round_binary32(value, negative_zero=negative_zero), value


def _finite_bits(bits):
    return ((bits >> 23) & 255) != 255


def _normal_bits(bits):
    return 0 < ((bits >> 23) & 255) < 255


def _rational(value):
    return dict(numerator=str(value.numerator), denominator=str(value.denominator),
                value=float(value))


def check_candidate(*, s, h, lambda2, epsilon, nu_before, nu_ideal,
                    declared_lambda2, declared_epsilon):
    """Check exact ideal-candidate bits and report independent rational error.

    lambda2/epsilon are actual consumed binary32 parameters, while declared_*
    are the separately frozen configuration values. No applied state is an
    input: a bounded applied value cannot replace the pre-limit ideal value.
    Raises CandidateAuditError on any mismatch. A return is not flight or
    full-controller acceptance, nor permission to reinterpret historical data.
    """
    recorded = {name: _recorded(value, name) for name, value in dict(
        s=s, h=h, lambda2=lambda2, epsilon=epsilon,
        nu_before=nu_before, nu_ideal=nu_ideal).items()}
    if recorded['lambda2'] != _bits(binary32(declared_lambda2)):
        raise CandidateAuditError('Actual lambda2 differs from frozen binary32 configuration')
    if recorded['epsilon'] != _bits(binary32(declared_epsilon)):
        raise CandidateAuditError('Actual epsilon differs from frozen binary32 configuration')
    if not binary32(.002) <= h <= binary32(.04):
        raise CandidateAuditError('h outside existing DIV1 [2,40] ms domain')
    if not binary32(.001) <= epsilon <= 1:
        raise CandidateAuditError('epsilon outside existing [.001,1] domain')
    if lambda2 <= 0 or not _normal_bits(recorded['lambda2']):
        raise CandidateAuditError('lambda2 must be finite positive normal')

    # Independent route A: explicitly rounded NumPy scalar operations.
    ss, hh, ll, ee, nn = (np.float32(value) for value in (s, h, lambda2, epsilon, nu_before))
    nonzero = bool(ss != np.float32(0))
    inside = bool(abs(ss) <= ee)
    with np.errstate(over='ignore', under='ignore', invalid='ignore', divide='ignore'):
        rho = np.divide(ss, ee, dtype=np.float32) if inside else np.float32(1 if ss > 0 else -1)
        step = np.multiply(hh, ll, dtype=np.float32) if nonzero else np.float32(0)
        delta = np.multiply(step, rho, dtype=np.float32)
        candidate = np.subtract(nn, delta, dtype=np.float32)
    floating = dict(rho=_bits(rho), step=_bits(step), delta=_bits(delta), candidate=_bits(candidate))
    if not all(_finite_bits(bits) for bits in floating.values()):
        raise CandidateAuditError('Nonfinite evaluated candidate arithmetic')
    if nonzero and any(not _normal_bits(floating[name]) for name in ('rho', 'step', 'delta')):
        raise CandidateAuditError('Nonzero candidate product/response underflow or flush-to-zero')

    # Independent route B: fractions from exact encoded inputs, then an
    # integer-only nearest-even quantizer at each specified rounding point.
    if inside:
        rho_bits, rho_unrounded = _exact_operation('divide', recorded['s'], recorded['epsilon'])
    else:
        rho_bits = 0x3f800000 if s > 0 else 0xbf800000
        rho_unrounded = Fraction(1 if s > 0 else -1)
    if nonzero:
        step_bits, step_unrounded = _exact_operation('multiply', recorded['h'], recorded['lambda2'])
    else:
        step_bits, step_unrounded = 0, Fraction(0)
    delta_bits, delta_unrounded = _exact_operation('multiply', step_bits, rho_bits)
    candidate_bits, candidate_unrounded = _exact_operation('subtract', recorded['nu_before'], delta_bits)
    exact = dict(rho=rho_bits, step=step_bits, delta=delta_bits, candidate=candidate_bits)
    for name in floating:
        if floating[name] != exact[name]:
            raise CandidateAuditError('Host operation does not implement declared binary32 semantics: ' + name)
    if recorded['nu_ideal'] != candidate_bits:
        raise CandidateAuditError('Recorded ideal nu is not the exact binary32 candidate')

    # The unrounded mathematical equation uses the actual binary32 parameters,
    # not an independently rounded/decimal epsilon. This equation has no
    # staged arithmetic; its residual is explained by exact operation errors.
    mathematical = _fraction(recorded['nu_before']) - step_unrounded * rho_unrounded
    residual = _fraction(candidate_bits) - mathematical
    rounding = dict(rho=_fraction(rho_bits) - rho_unrounded,
                    step=_fraction(step_bits) - step_unrounded,
                    delta=_fraction(delta_bits) - delta_unrounded,
                    candidate=_fraction(candidate_bits) - candidate_unrounded)
    bound = (abs(_fraction(step_bits)) * abs(rounding['rho']) +
             abs(rho_unrounded) * abs(rounding['step']) +
             abs(rounding['delta']) + abs(rounding['candidate']))
    if abs(residual) > bound:
        raise CandidateAuditError('Independent rounding-error decomposition is inconsistent')
    return dict(candidate_consistent=True, diagnostic_only=True,
                flight_accepted=False, execution_authority_granted=False,
                scope='Ideal nu candidate only; lifecycle/raw/applied checks not performed',
                arithmetic='binary32 RN-even at each operation; no contraction/reassociation/FTZ',
                branch='inside_or_boundary' if inside else 'outside',
                records={name: dict(value=_from_bits(bits), bits=f'{bits:08x}')
                         for name, bits in recorded.items()},
                trace={name: dict(value=_from_bits(bits), bits=f'{bits:08x}')
                       for name, bits in exact.items()},
                ideal_real_equation=_rational(mathematical),
                exact_residual=_rational(residual),
                rounding_errors={name: _rational(value) for name, value in rounding.items()},
                absolute_error_bound=_rational(bound))
