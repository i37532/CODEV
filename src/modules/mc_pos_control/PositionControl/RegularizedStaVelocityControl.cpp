// SPDX-License-Identifier: BSD-3-Clause
#include "RegularizedStaVelocityControl.hpp"

#include <cmath>
#include <cstring>

namespace
{
bool positiveNormal(float value)
{
	return std::isfinite(value) && value >= std::numeric_limits<float>::min();
}
}

bool RegularizedStaVelocityControl::validEpsilon(float epsilon)
{
	return std::isfinite(epsilon) && epsilon >= .001f && epsilon <= 1.f;
}

bool RegularizedStaVelocityControl::validParameters(const Parameters &parameters)
{
	return positiveNormal(parameters.lambda1) && positiveNormal(parameters.lambda2)
	       && validEpsilon(parameters.epsilon);
}

RegularizedStaVelocityControl::Nonlinearity RegularizedStaVelocityControl::nonlinear(float s, float epsilon)
{
	Nonlinearity result{};

	if (!validEpsilon(epsilon)) {
		return result;
	}

	if (!std::isfinite(s)) {
		result.status = Status::InvalidInput;
		return result;
	}

	if (std::fabs(s) <= epsilon) {
		result.psi = s / std::sqrt(epsilon);
		result.rho = s / epsilon;

	} else {
		result.rho = s > 0.f ? 1.f : -1.f;
		result.psi = std::sqrt(std::fabs(s)) * result.rho;
	}

	// Do not silently accept a nonzero response that is flushed/subnormal.
	// Exact zero is valid and retains any nonzero old integral state.
	if (!std::isfinite(result.psi) || !std::isfinite(result.rho)
	    || (std::fabs(s) > 0.f && (!positiveNormal(std::fabs(result.psi)) || !positiveNormal(std::fabs(result.rho))))) {
		result.status = Status::NumericalError;
		return result;
	}

	result.status = Status::Ok;
	return result;
}

bool RegularizedStaVelocityControl::setParameters(size_t axis, const Parameters &parameters)
{
	if (axis >= _nu.size() || !validParameters(parameters)) {
		return false;
	}

	_parameters[axis] = parameters;
	_configured[axis] = true;
	++_revision[axis];
	return true;
}

RegularizedStaVelocityControl::Candidate RegularizedStaVelocityControl::evaluate(size_t axis, float velocity,
		float velocity_sp, float dt) const
{
	Candidate candidate{};
	candidate.axis = axis;

	if (axis >= _nu.size()) {
		candidate.status = Status::InvalidAxis;
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

	const float s = velocity - velocity_sp;

	if (!std::isfinite(s)) {
		candidate.status = Status::NumericalError;
		return candidate;
	}

	const Nonlinearity shape = nonlinear(s, _parameters[axis].epsilon);

	if (!shape.valid()) {
		candidate.status = shape.status;
		return candidate;
	}

	const float correction = _parameters[axis].lambda1 * shape.psi;
	// Zero error has exactly zero increment, even when the unused h*lambda2
	// would overflow. For nonzero error require all evaluated products normal.
	const bool nonzero_error = std::fabs(s) > 0.f;
	const float step = nonzero_error ? dt * _parameters[axis].lambda2 : 0.f;
	const float delta = step * shape.rho;
	const float nu_before = _nu[axis];
	const float a_sta = -correction + nu_before;
	const float nu_next = nu_before - delta;
	const bool nonzero_underflow = nonzero_error && (!positiveNormal(std::fabs(correction))
				      || !positiveNormal(step) || !positiveNormal(std::fabs(delta)));

	if (!std::isfinite(correction) || !std::isfinite(step) || !std::isfinite(delta) || nonzero_underflow
	    || !std::isfinite(nu_before) || !std::isfinite(a_sta) || !std::isfinite(nu_next)) {
		candidate.status = Status::NumericalError;
		return candidate;
	}

	// A normal delta may round away when added to a much larger nu. This is
	// ordinary float addition rounding, not a subnormal product/underflow.
	candidate.status = Status::Ok;
	candidate.s = s;
	candidate.a_sta = a_sta;
	candidate.nu_before = nu_before;
	candidate.nu_next = nu_next;
	candidate.revision = _revision[axis];
	candidate.owner = this;
	candidate.sealed_axis = axis;
	candidate.sealed_revision = candidate.revision;
	candidate.sealed = {{s, a_sta, nu_before, nu_next}};
	return candidate;
}

bool RegularizedStaVelocityControl::current(const Candidate &candidate) const
{
	const std::array<float, 4> payload{{candidate.s, candidate.a_sta, candidate.nu_before, candidate.nu_next}};
	return candidate.valid() && candidate.owner == this && candidate.axis < _nu.size()
	       && candidate.axis == candidate.sealed_axis && candidate.revision == candidate.sealed_revision
	       && _configured[candidate.axis] && candidate.revision == _revision[candidate.axis]
	       && std::memcmp(payload.data(), candidate.sealed.data(), sizeof(float) * payload.size()) == 0;
}

RegularizedStaVelocityControl::Status RegularizedStaVelocityControl::commit(const Candidate &candidate)
{
	return commitProtected(candidate, candidate.nu_next);
}

RegularizedStaVelocityControl::Status RegularizedStaVelocityControl::commitProtected(const Candidate &candidate,
		float applied_nu)
{
	if (!candidate.valid() || candidate.axis >= _nu.size()) {
		return candidate.status == Status::Ok ? Status::InvalidAxis : candidate.status;
	}

	if (!current(candidate) || !std::isfinite(applied_nu)) {
		return Status::StaleCandidate;
	}

	_nu[candidate.axis] = applied_nu;
	++_revision[candidate.axis];
	return Status::Ok;
}

bool RegularizedStaVelocityControl::reset(size_t axis, float nu)
{
	if (axis >= _nu.size() || !std::isfinite(nu)) {
		return false;
	}

	_nu[axis] = nu;
	++_revision[axis];
	return true;
}

void RegularizedStaVelocityControl::reset()
{
	for (size_t axis = 0; axis < _nu.size(); ++axis) {
		_nu[axis] = 0.f;
		++_revision[axis];
	}
}
