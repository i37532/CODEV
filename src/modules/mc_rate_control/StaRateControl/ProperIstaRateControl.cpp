// SPDX-License-Identifier: BSD-3-Clause
#include "ProperIstaRateControl.hpp"

#include <algorithm>
#include <cmath>

namespace
{
bool positiveNormal(float x)
{
	return std::isfinite(x) && x >= std::numeric_limits<float>::min();
}

bool representable(double x)
{
	const double magnitude = std::fabs(x);
	return std::isfinite(x) && magnitude <= static_cast<double>(std::numeric_limits<float>::max())
	       && (std::fpclassify(x) == FP_ZERO || magnitude >= static_cast<double>(std::numeric_limits<float>::min()));
}

bool consistent(double lhs, double t1, double t2, double t3 = 0.0)
{
	const double scale = std::max({std::fabs(lhs), std::fabs(t1), std::fabs(t2), std::fabs(t3)});
	return std::fabs(lhs - (t1 + t2 + t3)) <= 8.0 * static_cast<double>(std::numeric_limits<float>::epsilon()) * scale;
}
}

bool ProperIstaRateControl::validParameters(const Parameters &p)
{
	return positiveNormal(p.lambda1) && positiveNormal(p.lambda2) && positiveNormal(p.g);
}

bool ProperIstaRateControl::setParameters(size_t axis, const Parameters &p)
{
	if (axis >= _nu.size() || !validParameters(p)) { return false; }
	_parameters[axis] = p;
	_configured[axis] = true;
	++_generation[axis];
	return true;
}

bool ProperIstaRateControl::reset(size_t axis, float nu)
{
	if (axis >= _nu.size() || !representable(static_cast<double>(nu))) { return false; }
	_nu[axis] = nu;
	++_generation[axis];
	return true;
}

void ProperIstaRateControl::reset()
{
	for (size_t axis = 0; axis < _nu.size(); ++axis) { reset(axis); }
}

ProperIstaRateControl::Candidate ProperIstaRateControl::evaluate(size_t axis, float rate, float rate_sp, float dt) const
{
	Candidate candidate;
	auto &out = candidate._result;
	if (axis >= _nu.size()) { out.status = Status::InvalidAxis; return candidate; }
	if (!_configured[axis]) { return candidate; }
	if (!std::isfinite(rate) || !std::isfinite(rate_sp)) { out.status = Status::InvalidInput; return candidate; }
	if (!positiveNormal(dt)) { out.status = Status::InvalidDt; return candidate; }
	out.status = Status::NumericalError;
	const double difference = static_cast<double>(rate) - static_cast<double>(rate_sp);
	if (!representable(difference)) { return candidate; }
	const float error = static_cast<float>(difference); // same float error interface as original ISTA
	const double s = static_cast<double>(error), h = static_cast<double>(dt);
	const auto &p = _parameters[axis];
	const double l1 = static_cast<double>(p.lambda1), l2 = static_cast<double>(p.lambda2);
	const double nu = static_cast<double>(_nu[axis]), g = static_cast<double>(p.g);
	const double alpha = h * l1, q = h * h * l2;
	double xi, next, a, z;
	Branch branch;
	if (!std::isfinite(q) || q <= 0.0 || !std::isfinite(alpha)) { return candidate; }

	// Eliminate a and nu_next: z + h*l1*sqrt(|z|)*xi + h^2*l2*xi = s.
	// Unlike original ISTA, the branch threshold does NOT depend on old nu.
	if (std::fabs(s) <= q) {
		branch = Branch::Sliding; // both equalities included
		xi = s / q;
		z = 0.0;
		const double correction = s / h;
		next = nu - correction;
		a = nu - 2.0 * correction;
	} else {
		xi = s > 0.0 ? 1.0 : -1.0;
		branch = s > 0.0 ? Branch::Positive : Branch::Negative;
		const double delta = std::fabs(s) - q;
		const double discriminant = alpha * alpha + 4.0 * delta;
		if (!std::isfinite(discriminant) || discriminant <= 0.0) { return candidate; }
		// r^2 + alpha*r = delta; rationalization preserves boundary neighbours.
		// Normal float inputs fit these products in double even if float q=0/D=Inf.
		const double root = 2.0 * delta / (std::sqrt(discriminant) + alpha);
		z = xi * root * root;
		const double correction = h * l2 * xi;
		next = nu - correction;
		a = nu - 2.0 * correction - l1 * root * xi;
	}
	const double command = a / g;
	if (!representable(next) || !representable(a) || !representable(command)
	    || !representable(z) || !representable(xi) || std::fabs(xi) > 1.0) { return candidate; }
	const double rn = static_cast<double>(static_cast<float>(next));
	const double ra = static_cast<double>(static_cast<float>(a));
	const double rc = static_cast<double>(static_cast<float>(command));
	const double rz = static_cast<double>(static_cast<float>(z));
	const double rx = static_cast<double>(static_cast<float>(xi));
	// Check the rounded interface, not just the double candidate. Keep original
	// terms separate in the tolerance scale when large nu terms cancel.
	if (!consistent(rz, s, h * ra, -h * rn)
	    || !consistent(rz, s, h * g * rc, -h * rn)
	    || !consistent(rn, nu, -h * l2 * rx)
	    || !consistent(ra, -l1 * std::sqrt(std::fabs(rz)) * rx, 2.0 * rn, -nu)
	    || !consistent(ra, g * rc, 0.0)) { return candidate; }
	out.s = error;
	out.a = static_cast<float>(a);
	out.c_raw = static_cast<float>(command);
	out.nu_next = static_cast<float>(next);
	out.virtual_s = static_cast<float>(z);
	out.xi = static_cast<float>(xi);
	out.branch = branch;
	out.status = Status::Ok;
	candidate._owner = this;
	candidate._axis = axis;
	candidate._generation = _generation[axis];
	return candidate;
}

bool ProperIstaRateControl::commit(const Candidate &candidate)
{
	return commitProtected(candidate, candidate._result.nu_next);
}

bool ProperIstaRateControl::commitProtected(const Candidate &candidate, float applied_nu)
{
	if (candidate._owner != this || candidate._axis >= _nu.size() || !candidate._result.valid()
	    || candidate._generation != _generation[candidate._axis] || !representable(static_cast<double>(applied_nu))) { return false; }
	_nu[candidate._axis] = applied_nu;
	++_generation[candidate._axis];
	return true;
}

ProperIstaRateControl::Result ProperIstaRateControl::update(size_t axis, float rate, float rate_sp, float dt)
{
	const auto candidate = evaluate(axis, rate, rate_sp, dt);
	if (!candidate.result().valid()) { return candidate.result(); }
	if (!commit(candidate)) { Result error; error.status = Status::NumericalError; return error; }
	return candidate.result();
}
