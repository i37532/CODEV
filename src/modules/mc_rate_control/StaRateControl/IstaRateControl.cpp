// SPDX-License-Identifier: BSD-3-Clause
#include "IstaRateControl.hpp"

#include <algorithm>
#include <cmath>

namespace
{
bool positiveNormal(float x)
{
	return std::isfinite(x) && x >= std::numeric_limits<float>::min();
}

// Check BEFORE narrowing: overflowing float casts must never be used as guards.
bool representable(double x)
{
	const double magnitude = std::fabs(x);
	return std::isfinite(x) && magnitude <= static_cast<double>(std::numeric_limits<float>::max())
	       && (std::fpclassify(x) == FP_ZERO || magnitude >= static_cast<double>(std::numeric_limits<float>::min()));
}

// Extreme finite inputs can lose low-order terms even in double arithmetic.
// Check rounded public outputs against each equation before state is committed.
bool consistent(double lhs, double first, double second)
{
	const double scale = std::max({std::fabs(lhs), std::fabs(first), std::fabs(second)});
	return std::fabs(lhs - (first + second)) <= 8.0 * static_cast<double>(std::numeric_limits<float>::epsilon()) * scale;
}
}

bool IstaRateControl::validParameters(const Parameters &p)
{
	return positiveNormal(p.lambda1) && positiveNormal(p.lambda2) && positiveNormal(p.g);
}

bool IstaRateControl::setParameters(size_t axis, const Parameters &p)
{
	if (axis >= _nu.size() || !validParameters(p)) { return false; }

	_parameters[axis] = p;
	_configured[axis] = true;
	return true;
}

bool IstaRateControl::reset(size_t axis, float nu)
{
	if (axis >= _nu.size() || !std::isfinite(nu)) { return false; }

	_nu[axis] = nu;
	return true;
}

void IstaRateControl::reset()
{
	_nu.fill(0.f);
}

IstaRateControl::Result IstaRateControl::update(size_t axis, float rate, float rate_sp, float dt)
{
	Result out;

	if (axis >= _nu.size()) { out.status = Status::InvalidAxis; return out; }

	if (!_configured[axis]) { return out; }

	if (!std::isfinite(rate) || !std::isfinite(rate_sp)) { out.status = Status::InvalidInput; return out; }

	if (!positiveNormal(dt)) { out.status = Status::InvalidDt; return out; }

	out.status = Status::NumericalError;
	// Preserve the shared float error interface, with checked subtraction.
	const double difference = static_cast<double>(rate) - static_cast<double>(rate_sp);

	if (!representable(difference)) { return out; }

	const float s = static_cast<float>(difference);
	const auto &p = _parameters[axis];
	const double h = static_cast<double>(dt);
	const double l1 = static_cast<double>(p.lambda1);
	const double l2 = static_cast<double>(p.lambda2);
	const double nu = static_cast<double>(_nu[axis]);
	const double alpha = h * l1;
	const double q = h * h * l2;
	const double b = -static_cast<double>(s) - h * nu;
	double xi, next, acceleration, virtual_s;
	Branch branch;

	// For finite normal float gains/h, q > 0 and alpha^2 + 4*delta
	// fit in binary64 (even when those expressions under/overflow binary32).
	if (!std::isfinite(q) || q <= 0.0 || !std::isfinite(b) || !std::isfinite(alpha)) { return out; }

	if (b >= -q && b <= q) {
		branch = Branch::Sliding; // BOTH equalities belong to the sliding branch
		xi = -b / q;
		virtual_s = 0.0;
		next = -static_cast<double>(s) / h;
		acceleration = next;

	} else {
		xi = b < -q ? 1.0 : -1.0;
		branch = xi > 0.0 ? Branch::Positive : Branch::Negative;
		const double delta = std::fabs(b) - q;
		const double discriminant = alpha * alpha + 4.0 * delta;

		if (!std::isfinite(discriminant) || discriminant <= 0.0) { return out; }

		// Rationalization avoids subtracting nearly equal sqrt(D) and alpha.
		const double root = (2.0 * delta) / (std::sqrt(discriminant) + alpha);
		virtual_s = xi * root * root;
		next = nu - h * l2 * xi;
		acceleration = -l1 * root * xi + next;
	}

	const double command = acceleration / static_cast<double>(p.g);

	if (!representable(next) || !representable(acceleration) || !representable(command)
	    || !representable(virtual_s) || !representable(xi) || std::fabs(xi) > 1.0) { return out; }

	const double rounded_a = static_cast<double>(static_cast<float>(acceleration));
	const double rounded_c = static_cast<double>(static_cast<float>(command));
	const double rounded_next = static_cast<double>(static_cast<float>(next));
	const double rounded_v = static_cast<double>(static_cast<float>(virtual_s));
	const double rounded_xi = static_cast<double>(static_cast<float>(xi));

	if (!consistent(rounded_v, static_cast<double>(s), h * rounded_a)
	    || !consistent(rounded_v, static_cast<double>(s), h * static_cast<double>(p.g) * rounded_c)
	    || !consistent(rounded_next, nu, -h * l2 * rounded_xi)
	    || !consistent(rounded_a, -l1 * std::sqrt(std::fabs(rounded_v)) * rounded_xi, rounded_next)) { return out; }

	out.s = s;
	out.a = static_cast<float>(acceleration);
	out.c_raw = static_cast<float>(command);
	out.nu_next = static_cast<float>(next);
	out.virtual_s = static_cast<float>(virtual_s);
	out.xi = static_cast<float>(xi);
	out.branch = branch;
	out.status = Status::Ok;
	_nu[axis] = out.nu_next; // commit exactly once, after validation of the ENTIRE result
	return out;
}
