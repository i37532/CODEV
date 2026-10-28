// SPDX-License-Identifier: BSD-3-Clause
#include "ProperIstaVelocityControl.hpp"

#include <atomic>
#include <cfenv>
#include <cmath>
#include <cstring>
#if defined(__SSE__) && (defined(__i386__) || defined(__x86_64__))
#include <xmmintrin.h>
#endif

namespace
{
bool positiveNormal(float value)
{
	return std::isfinite(value) && value >= std::numeric_limits<float>::min();
}

bool narrowable(double value)
{
	// No lower cutoff: gradual rounding, including correct IEEE underflow to
	// zero below half a float subnormal ulp, is not an algorithmic deadzone.
	return std::isfinite(value) && std::fabs(value) <= static_cast<double>(std::numeric_limits<float>::max());
}

double narrowingBound(double value)
{
	// Round-to-nearest binary32: |fl(x)-x| <= u32*|x| + eta32/2.
	// eta32 is denorm_min, NOT FLT_MIN and not an engineering tolerance.
	return .5 * static_cast<double>(std::numeric_limits<float>::epsilon()) * std::fabs(value)
	       + .5 * static_cast<double>(std::numeric_limits<float>::denorm_min());
}

bool residual(double lhs, double first, double second, double third, double narrowing)
{
	// Binary64 arithmetic/solve budget, independent of a fixed absolute epsilon.
	const double scale = std::fabs(lhs) + std::fabs(first) + std::fabs(second) + std::fabs(third);
	constexpr double unit_roundoff = .5 * std::numeric_limits<double>::epsilon();
	constexpr double gamma = (64.0 * unit_roundoff) / (1.0 - 64.0 * unit_roundoff);
	const double budget = gamma * scale + narrowing;
	return std::isfinite(lhs) && std::isfinite(scale)
	       && std::fabs(lhs - (first + second + third)) <= budget;
}

uint64_t nextInstance()
{
	static std::atomic<uint64_t> counter{0};
	uint64_t value = counter.load(std::memory_order_relaxed);

	while (value < std::numeric_limits<uint64_t>::max()) {
		if (counter.compare_exchange_weak(value, value + 1, std::memory_order_relaxed)) {
			return value + 1;
		}
	}

	return 0; // Exhaustion must never wrap to a previously issued identity.
}
}

ProperIstaVelocityControl::ProperIstaVelocityControl() : _instance_id(nextInstance()) {}

bool ProperIstaVelocityControl::floatingPointEnvironmentSupported()
{
#if defined(__FAST_MATH__) || (defined(__FINITE_MATH_ONLY__) && __FINITE_MATH_ONLY__ > 0) \
	|| !defined(__SSE__) || (!defined(__i386__) && !defined(__x86_64__))
	return false;
#else
	if (!std::numeric_limits<float>::is_iec559 || !std::numeric_limits<double>::is_iec559
	    || std::numeric_limits<float>::digits != 24 || std::numeric_limits<double>::digits != 53
	    || std::fegetround() != FE_TONEAREST) {
		return false;
	}

	// fegetround may observe only x87. Also inspect SSE rounding (0x6000),
	// FTZ (0x8000) and DAZ (0x0040) directly. No test arithmetic is performed
	// under an unsupported mode, so even sticky exception flags are preserved.
	return (_mm_getcsr() & 0xe040u) == 0u;
#endif
}

bool ProperIstaVelocityControl::incrementable(uint64_t generation)
{
	return generation != std::numeric_limits<uint64_t>::max();
}

bool ProperIstaVelocityControl::validParameters(const Parameters &parameters)
{
	return positiveNormal(parameters.lambda1) && positiveNormal(parameters.lambda2);
}

bool ProperIstaVelocityControl::setParameters(size_t axis, const Parameters &parameters)
{
	if (!_instance_id || axis >= _nu.size() || !floatingPointEnvironmentSupported()
	    || !validParameters(parameters) || !incrementable(_config_generation[axis])) {
		return false;
	}

	_parameters[axis] = parameters;
	_configured[axis] = true;
	++_config_generation[axis];
	return true;
}

ProperIstaVelocityControl::Candidate ProperIstaVelocityControl::evaluate(
	size_t axis, float velocity, float velocity_sp, float dt) const
{
	Candidate candidate;
	candidate.axis = axis;

	if (axis >= _nu.size()) {
		candidate.status = Status::InvalidAxis;
		return candidate;
	}

	if (!floatingPointEnvironmentSupported()) {
		candidate.status = Status::UnsupportedEnvironment;
		return candidate;
	}

	if (!_configured[axis]) {
		return candidate;
	}

	if (!std::isfinite(velocity) || !std::isfinite(velocity_sp)) {
		candidate.status = Status::InvalidInput;
		return candidate;
	}

	if (!positiveNormal(dt)) {
		candidate.status = Status::InvalidDt;
		return candidate;
	}

	candidate.status = Status::NumericalError;
	const double difference = static_cast<double>(velocity) - static_cast<double>(velocity_sp);

	if (!narrowable(difference)) { return candidate; }

	const float error = static_cast<float>(difference);
	const double s = error, h = dt, nu = _nu[axis];
	const double l1 = _parameters[axis].lambda1, l2 = _parameters[axis].lambda2;
	const double alpha = h * l1, q = h * h * l2;
	double xi, next, output, z;

	if (!std::isfinite(q) || q <= 0.0 || !std::isfinite(alpha)) { return candidate; }

	if (std::fabs(s) <= q) {
		candidate.branch = Branch::Sliding; // Includes both exact boundaries.
		z = 0.0;
		xi = s / q;
		const double correction = s / h;
		next = nu - correction;
		output = nu - 2.0 * correction;

	} else {
		xi = s > 0.0 ? 1.0 : -1.0;
		candidate.branch = s > 0.0 ? Branch::Positive : Branch::Negative;
		const double delta = std::fabs(s) - q;
		const double discriminant = alpha * alpha + 4.0 * delta;

		if (!std::isfinite(discriminant) || discriminant <= 0.0) { return candidate; }

		// Solve r^2+alpha*r=delta by rationalization, never subtract roots.
		// Products of finite binary32 inputs fit binary64 even when the
		// equivalent float intermediate would underflow or overflow.
		const double root = 2.0 * delta / (std::sqrt(discriminant) + alpha);
		z = xi * root * root;
		const double correction = h * l2 * xi;
		next = nu - correction;
		output = nu - 2.0 * correction - l1 * root * xi;
	}

	if (!narrowable(next) || !narrowable(output) || !std::isfinite(z) || !std::isfinite(xi)
	    || std::fabs(xi) > 1.0) { return candidate; }

	const float next_float = static_cast<float>(next), output_float = static_cast<float>(output);
	const double rn = next_float, ra = output_float;
	const double bn = narrowingBound(next), ba = narrowingBound(output);

	// Check the rounded public interface against the original three equations.
	// z/xi stay binary64: narrowing a tiny z would distort sqrt(abs(z)).
	if (!residual(z, s, h * ra, -h * rn, h * (ba + bn))
	    || !residual(rn, nu, -h * l2 * xi, 0.0, bn)
	    || !residual(ra, -l1 * std::sqrt(std::fabs(z)) * xi, 2.0 * rn, -nu, ba + 2.0 * bn)
	    || !residual(s, z, h * l1 * std::sqrt(std::fabs(z)) * xi, q * xi, 0.0)) {
		return candidate;
	}

	candidate.status = Status::Ok;
	candidate.s = error;
	candidate.virtual_s = z;
	candidate.xi = xi;
	candidate.a_sta = output_float;
	candidate.nu_before = _nu[axis];
	candidate.nu_next = next_float;
	candidate.dt = dt;
	candidate.config_generation = _config_generation[axis];
	candidate.reset_generation = _reset_generation[axis];
	candidate.state_generation = _state_generation[axis];
	candidate.owner = this;
	candidate.instance_id = _instance_id;
	candidate.sealed_axis = axis;
	candidate.sealed_branch = candidate.branch;
	candidate.generations = {{candidate.config_generation, candidate.reset_generation, candidate.state_generation}};
	candidate.payload = {{error, output_float, candidate.nu_before, next_float, dt}};
	candidate.wide_payload = {{z, xi}};
	return candidate;
}

bool ProperIstaVelocityControl::current(const Candidate &candidate) const
{
	const std::array<float, 5> payload{{candidate.s, candidate.a_sta, candidate.nu_before,
			candidate.nu_next, candidate.dt}};
	const std::array<double, 2> wide_payload{{candidate.virtual_s, candidate.xi}};
	const std::array<uint64_t, 3> generations{{candidate.config_generation,
			candidate.reset_generation, candidate.state_generation}};
	return candidate.valid() && candidate.owner == this && _instance_id && candidate.instance_id == _instance_id
	       && candidate.axis < _nu.size() && candidate.axis == candidate.sealed_axis
	       && candidate.branch == candidate.sealed_branch && _configured[candidate.axis]
	       && generations == candidate.generations
	       && candidate.config_generation == _config_generation[candidate.axis]
	       && candidate.reset_generation == _reset_generation[candidate.axis]
	       && candidate.state_generation == _state_generation[candidate.axis]
	       && std::memcmp(payload.data(), candidate.payload.data(), sizeof(float) * payload.size()) == 0
	       && std::memcmp(wide_payload.data(), candidate.wide_payload.data(), sizeof(double) * wide_payload.size()) == 0;
}

ProperIstaVelocityControl::Status ProperIstaVelocityControl::commit(const Candidate &candidate)
{
	if (!floatingPointEnvironmentSupported()) { return Status::UnsupportedEnvironment; }
	if (!candidate.valid()) { return candidate.status; }
	if (candidate.axis >= _nu.size()) { return Status::InvalidAxis; }
	if (!current(candidate)) { return Status::StaleCandidate; }
	if (!std::isfinite(candidate.nu_next) || !incrementable(_state_generation[candidate.axis])) {
		return Status::NumericalError;
	}

	_nu[candidate.axis] = candidate.nu_next;
	++_state_generation[candidate.axis];
	return Status::Ok;
}

bool ProperIstaVelocityControl::reset(size_t axis, float nu)
{
	if (!_instance_id || axis >= _nu.size() || !floatingPointEnvironmentSupported()
	    || !std::isfinite(nu) || !incrementable(_reset_generation[axis])) {
		return false;
	}

	_nu[axis] = nu;
	++_reset_generation[axis];
	return true;
}

bool ProperIstaVelocityControl::reset()
{
	if (!_instance_id || !floatingPointEnvironmentSupported()) { return false; }

	for (size_t axis = 0; axis < _nu.size(); ++axis) {
		if (!incrementable(_reset_generation[axis])) { return false; }
	}

	for (size_t axis = 0; axis < _nu.size(); ++axis) {
		_nu[axis] = 0.f;
		++_reset_generation[axis];
	}

	return true;
}
