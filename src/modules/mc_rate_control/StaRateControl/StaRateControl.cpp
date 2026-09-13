// SPDX-License-Identifier: BSD-3-Clause
#include "StaRateControl.hpp"

#include <cmath>

namespace
{
bool positiveNormal(float value)
{
	return std::isfinite(value) && value >= std::numeric_limits<float>::min();
}
}

bool StaRateControl::validParameters(const Parameters &parameters)
{
	return positiveNormal(parameters.lambda1) && positiveNormal(parameters.lambda2) && positiveNormal(parameters.g);
}

bool StaRateControl::setParameters(size_t axis, const Parameters &parameters)
{
	if (axis >= _nu.size() || !validParameters(parameters)) {
		return false;
	}

	_parameters[axis] = parameters;
	_configured[axis] = true;
	return true;
}

bool StaRateControl::reset(size_t axis, float nu)
{
	if (axis >= _nu.size() || !std::isfinite(nu)) {
		return false;
	}

	_nu[axis] = nu;
	return true;
}

void StaRateControl::reset()
{
	_nu.fill(0.f);
}

StaRateControl::Result StaRateControl::update(size_t axis, float rate, float rate_sp, float dt)
{
	Result result{};

	if (axis >= _nu.size()) {
		result.status = Status::InvalidAxis;
		return result;
	}

	if (!_configured[axis]) {
		return result;
	}

	if (!std::isfinite(rate) || !std::isfinite(rate_sp)) {
		result.status = Status::InvalidInput;
		return result;
	}

	if (!positiveNormal(dt)) {
		result.status = Status::InvalidDt;
		return result;
	}

	const Parameters &p = _parameters[axis];
	const float s = rate - rate_sp;
	const float sigma = (s > 0.f) ? 1.f : ((s < 0.f) ? -1.f : 0.f);
	const float correction = p.lambda1 * std::sqrt(std::fabs(s));
	const float delta = dt * p.lambda2;
	// Explicit ESTA: output uses nu_k, never nu_{k+1}.
	const float a = -correction * sigma + _nu[axis];
	const float c_raw = a / p.g;
	const float nu_next = _nu[axis] - delta * sigma;

	// Validate the entire proposal before committing state, including intermediate overflow.
	if (!std::isfinite(s) || !std::isfinite(correction) || !std::isfinite(delta)
	    || !std::isfinite(a) || !std::isfinite(c_raw) || !std::isfinite(nu_next)) {
		result.status = Status::NumericalError;
		return result;
	}

	result.status = Status::Ok;
	result.s = s;
	result.a = a;
	result.c_raw = c_raw;
	result.nu_next = nu_next;
	_nu[axis] = nu_next;
	return result;
}
