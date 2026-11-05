// SPDX-License-Identifier: BSD-3-Clause
#include "StaVelocityControl.hpp"

#include <cmath>
#include <cstring>

namespace
{
bool positiveNormal(float value)
{
	return std::isfinite(value) && value >= std::numeric_limits<float>::min();
}

float signSelection(float value)
{
	return value > 0.f ? 1.f : (value < 0.f ? -1.f : 0.f);
}
}

bool StaVelocityControl::validParameters(const Parameters &parameters)
{
	return positiveNormal(parameters.lambda1) && positiveNormal(parameters.lambda2);
}

bool StaVelocityControl::setParameters(size_t axis, const Parameters &parameters)
{
	if (axis >= _nu.size() || !validParameters(parameters)) {
		return false;
	}

	_parameters[axis] = parameters;
	_configured[axis] = true;
	++_revision[axis];
	return true;
}

StaVelocityControl::Candidate StaVelocityControl::evaluate(size_t axis, float velocity, float velocity_sp, float dt) const
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
	const float sigma = signSelection(s);
	const float correction = _parameters[axis].lambda1 * std::sqrt(std::fabs(s));
	const float delta = dt * _parameters[axis].lambda2;
	const float nu_before = _nu[axis];
	const float a_sta = -correction * sigma + nu_before;
	const float nu_next = nu_before - delta * sigma;

	// A subnormal/zero nonzero-error correction or nu increment silently loses
	// the intended explicit update. Reject it atomically instead of treating a
	// floating-point underflow as a valid held controller state.
	const bool correction_underflow = std::fabs(s) > 0.f && !positiveNormal(correction);
	const bool delta_underflow = !positiveNormal(delta);

	if (!std::isfinite(s) || !std::isfinite(correction) || !std::isfinite(delta)
	    || correction_underflow || delta_underflow
	    || !std::isfinite(nu_before) || !std::isfinite(a_sta) || !std::isfinite(nu_next)) {
		candidate.status = Status::NumericalError;
		return candidate;
	}

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

bool StaVelocityControl::current(const Candidate &candidate) const
{
	const std::array<float, 4> payload{{candidate.s, candidate.a_sta, candidate.nu_before, candidate.nu_next}};
	return candidate.valid() && candidate.owner == this && candidate.axis < _nu.size()
	       && candidate.axis == candidate.sealed_axis && candidate.revision == candidate.sealed_revision
	       && _configured[candidate.axis] && candidate.revision == _revision[candidate.axis]
	       && std::memcmp(payload.data(), candidate.sealed.data(), sizeof(float) * payload.size()) == 0;
}

StaVelocityControl::Status StaVelocityControl::commit(const Candidate &candidate)
{
	return commitProtected(candidate, candidate.nu_next);
}

StaVelocityControl::Status StaVelocityControl::commitProtected(const Candidate &candidate, float applied_nu)
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

bool StaVelocityControl::reset(size_t axis, float nu)
{
	if (axis >= _nu.size() || !std::isfinite(nu)) {
		return false;
	}

	_nu[axis] = nu;
	++_revision[axis];
	return true;
}

void StaVelocityControl::reset()
{
	for (size_t axis = 0; axis < _nu.size(); ++axis) {
		_nu[axis] = 0.f;
		++_revision[axis];
	}
}
