// SPDX-License-Identifier: BSD-3-Clause
#include "RegularizedIstaVelocityControl.hpp"
#include <atomic>
#include <cmath>
#include <cstring>

namespace
{
bool positiveNormal(float x)
{
	return std::isfinite(x) && x >= std::numeric_limits<float>::min();
}
bool normalOrZero(float x)
{
	return std::isfinite(x) && (std::fabs(x) <= 0.f || positiveNormal(std::fabs(x)));
}
uint64_t nextInstance()
{
	// Distinguish destruction/reconstruction at the same address. Saturate,
	// never wrap to an identity that could still be held by a candidate.
	static std::atomic<uint64_t> counter{0};
	uint64_t value = counter.load(std::memory_order_relaxed);

	while (value < std::numeric_limits<uint64_t>::max()) {
		if (counter.compare_exchange_weak(value, value + 1, std::memory_order_relaxed)) {
			return value + 1;
		}
	}

	return 0; // Exhausted identity space: instance can never configure.
}
}

RegularizedIstaVelocityControl::RegularizedIstaVelocityControl() : _instance_id(nextInstance()) {}
bool RegularizedIstaVelocityControl::incrementable(uint64_t generation)
{
	return generation != std::numeric_limits<uint64_t>::max();
}
bool RegularizedIstaVelocityControl::validEpsilon(float epsilon)
{
	return std::isfinite(epsilon) && epsilon >= .001f && epsilon <= 1.f;
}
bool RegularizedIstaVelocityControl::validParameters(const Parameters &parameters)
{
	return positiveNormal(parameters.lambda1) && positiveNormal(parameters.lambda2)
	       && validEpsilon(parameters.epsilon);
}
bool RegularizedIstaVelocityControl::setParameters(size_t axis, const Parameters &parameters)
{
	if (!_instance_id || _exhausted || axis >= _nu.size() || !validParameters(parameters)
	    || !incrementable(_config_generation[axis])) {
		return false;
	}

	_parameters[axis] = parameters;
	_configured[axis] = true;
	++_config_generation[axis];
	return true;
}
RegularizedIstaVelocityControl::Candidate RegularizedIstaVelocityControl::evaluate(
	size_t axis, float velocity, float velocity_sp, float dt) const
{
	Candidate c{};
	c.axis = axis;

	if (axis >= _nu.size()) {
		c.status = Status::InvalidAxis;
		return c;
	}

	if (!_configured[axis]) {
		return c;
	}

	if (!std::isfinite(velocity) || !std::isfinite(velocity_sp)) {
		c.status = Status::InvalidInput;
		return c;
	}

	if (!positiveNormal(dt)) {
		c.status = Status::InvalidDt;
		return c;
	}

	c.status = Status::NumericalError;
	const float s = velocity - velocity_sp;

	if (!normalOrZero(s) || !normalOrZero(_nu[axis])) {
		return c;
	}

	const Parameters &parameters = _parameters[axis];
	float p = 0.f;
	float psi = 0.f;
	float rho = 0.f;
	float correction = 0.f;
	float delta = 0.f;

	if (std::fabs(s) > 0.f) {
		// Exact zero bypasses unused h*gain products. Nonzero disappearing
		// or subnormal products are errors, never silently flushed to zero.
		const float A = dt * parameters.lambda1;
		const float step = dt * parameters.lambda2;
		const float B = dt * step;
		const float sqrt_epsilon = std::sqrt(parameters.epsilon);
		const float boundary_term = A * sqrt_epsilon;
		const float boundary = parameters.epsilon + boundary_term + B;

		if (!positiveNormal(A) || !positiveNormal(step) || !positiveNormal(B)
		    || !positiveNormal(boundary_term) || !positiveNormal(boundary)) {
			return c;
		}

		if (std::fabs(s) <= boundary) {
			const float first = A / sqrt_epsilon;
			const float second = B / parameters.epsilon;
			const float denominator = 1.f + first + second;

			if (!positiveNormal(first) || !positiveNormal(second) || !positiveNormal(denominator)) {
				return c;
			}

			p = s / denominator;

		} else {
			c.branch = Branch::Outer;
			const float C = std::fabs(s) - B;
			const float half_A = A * .5f;
			// Rationalized AND scaled: no A*A, 4*C, 2*C, or sqrt(...)-A.
			const float denominator = std::hypot(half_A, std::sqrt(C)) + half_A;

			if (!positiveNormal(C) || !positiveNormal(half_A) || !positiveNormal(denominator)) {
				return c;
			}

			const float r = C / denominator;

			if (!positiveNormal(r)) {
				return c;
			}

			p = std::copysign(r * r, s);
		}

		// b and the root round independently. At a float branch boundary p
		// can cross epsilon by one ulp; always apply the actual saturated
		// nonlinearity to the computed p, never allow |rho| > 1.
		if (!positiveNormal(std::fabs(p))) {
			return c;
		}

		if (std::fabs(p) <= parameters.epsilon) {
			rho = p / parameters.epsilon;
			psi = p / sqrt_epsilon;

		} else {
			rho = std::copysign(1.f, p);
			psi = std::copysign(std::sqrt(std::fabs(p)), p);
		}

		correction = parameters.lambda1 * psi;
		delta = step * rho;

		if (!positiveNormal(std::fabs(p)) || !positiveNormal(std::fabs(rho))
		    || !positiveNormal(std::fabs(psi)) || !positiveNormal(std::fabs(correction))
		    || !positiveNormal(std::fabs(delta))) {
			return c;
		}
	}

	const float next_nu = _nu[axis] - delta;
	const float a_sta = -correction + next_nu; // Candidate, NOT old nu.

	if (!normalOrZero(next_nu) || !normalOrZero(a_sta)) {
		return c;
	}

	c.status = Status::Ok;
	c.s = s;
	c.p = p;
	c.psi = psi;
	c.rho = rho;
	c.a_sta = a_sta;
	c.nu_before = _nu[axis];
	c.nu_next = next_nu;
	c.dt = dt;
	c.config_generation = _config_generation[axis];
	c.reset_generation = _reset_generation[axis];
	c.state_generation = _state_generation[axis];
	c.owner = this;
	c.instance_id = _instance_id;
	c.sealed_axis = axis;
	c.sealed_branch = c.branch;
	c.generations = {{c.config_generation, c.reset_generation, c.state_generation}};
	c.payload = {{s, p, psi, rho, a_sta, c.nu_before, next_nu, dt}};
	return c;
}
bool RegularizedIstaVelocityControl::current(const Candidate &c) const
{
	const std::array<float, 8> payload{{c.s, c.p, c.psi, c.rho, c.a_sta, c.nu_before, c.nu_next, c.dt}};
	const std::array<uint64_t, 3> generations{{c.config_generation, c.reset_generation, c.state_generation}};
	return c.valid() && !_exhausted && c.owner == this && c.instance_id == _instance_id && _instance_id
	       && c.axis < _nu.size() && c.axis == c.sealed_axis && c.branch == c.sealed_branch
	       && _configured[c.axis] && generations == c.generations
	       && c.config_generation == _config_generation[c.axis]
	       && c.reset_generation == _reset_generation[c.axis]
	       && c.state_generation == _state_generation[c.axis]
	       && std::memcmp(payload.data(), c.payload.data(), sizeof(float) * payload.size()) == 0;
}
RegularizedIstaVelocityControl::Status RegularizedIstaVelocityControl::commit(const Candidate &candidate)
{
	return commitProtected(candidate, candidate.nu_next);
}
RegularizedIstaVelocityControl::Status RegularizedIstaVelocityControl::commitProtected(
	const Candidate &candidate, float applied_nu)
{
	if (!candidate.valid()) {
		return candidate.status;
	}

	if (candidate.axis >= _nu.size()) {
		return Status::InvalidAxis;
	}

	if (!current(candidate)) {
		return Status::StaleCandidate;
	}

	if (!normalOrZero(applied_nu) || !incrementable(_state_generation[candidate.axis])) {
		return Status::NumericalError;
	}

	_nu[candidate.axis] = applied_nu;
	++_state_generation[candidate.axis];
	return Status::Ok;
}
RegularizedIstaVelocityControl::Status RegularizedIstaVelocityControl::commitBatch(
	const std::array<Candidate, 3> &candidates, uint8_t mask, const std::array<float, 3> &applied_nu)
{
	if (!mask || (mask & ~7u)) {
		return Status::InvalidAxis;
	}

	for (size_t axis = 0; axis < _nu.size(); ++axis) {
		if (mask & (1u << axis)) {
			if (candidates[axis].axis != axis || !current(candidates[axis])) {
				return Status::StaleCandidate;
			}

			if (!normalOrZero(applied_nu[axis]) || !incrementable(_state_generation[axis])) {
				return Status::NumericalError;
			}
		}
	}

	for (size_t axis = 0; axis < _nu.size(); ++axis) {
		if (mask & (1u << axis)) {
			_nu[axis] = applied_nu[axis];
			++_state_generation[axis];
		}
	}

	return Status::Ok;
}
bool RegularizedIstaVelocityControl::reset(size_t axis, float nu)
{
	if (_exhausted || axis >= _nu.size() || !normalOrZero(nu) || !incrementable(_reset_generation[axis])) {
		return false;
	}

	_nu[axis] = nu;
	++_reset_generation[axis];
	return true;
}
void RegularizedIstaVelocityControl::reset()
{
	if (_exhausted) {
		return;
	}

	for (size_t axis = 0; axis < _nu.size(); ++axis) {
		if (!incrementable(_reset_generation[axis])) {
			_exhausted = true;
			_configured.fill(false); // Fail closed on exhaustion; never wrap.
			return;
		}
	}

	for (size_t axis = 0; axis < _nu.size(); ++axis) {
		_nu[axis] = 0.f;
		++_reset_generation[axis];
	}
}

bool RegularizedIstaVelocityControl::resetBatch(uint8_t mask, const std::array<float, 3> &nu)
{
	if (_exhausted || !mask || (mask & ~7u)) { return false; }
	for (size_t axis = 0; axis < _nu.size(); ++axis) {
		if ((mask & (1u << axis)) && (!normalOrZero(nu[axis]) || !incrementable(_reset_generation[axis]))) { return false; }
	}
	for (size_t axis = 0; axis < _nu.size(); ++axis) {
		if (mask & (1u << axis)) { _nu[axis] = nu[axis]; ++_reset_generation[axis]; }
	}
	return true;
}
