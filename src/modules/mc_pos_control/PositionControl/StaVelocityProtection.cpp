// SPDX-License-Identifier: BSD-3-Clause
#include "StaVelocityProtection.hpp"
#include <cmath>
#include <algorithm>
#include <cstring>

bool StaVelocityProtection::validConfig(const Config &c)
{
	if (c.axes != 0 && c.axes != 1 && c.axes != 3 && c.axes != 4) { return false; }

	for (size_t i = 0; i < 3; ++i) {
		if ((c.axes & (1 << i)) && (!StaVelocityControl::validParameters(c.gains[i])
		    || !std::isnormal(c.nu_limit[i]) || c.nu_limit[i] <= 0.f
		    || !std::isnormal(c.acceleration_limit[i]) || c.acceleration_limit[i] <= 0.f)) { return false; }
	}

	return true;
}

bool StaVelocityProtection::seedZ(float nu)
{
	if (_config.axes != 4 || !_active || _open || _fault || !(_result.flags & Priming)
	    || !std::isfinite(nu) || fabsf(nu) > _config.nu_limit[2]) { latch(Numerical); return false; }
	_kernel.reset(2, nu);
	_result.nu_before[2] = _result.nu_ideal[2] = _result.nu_applied[2] = nu;
	return true;
}

bool StaVelocityProtection::shiftZ(float shift, float correction)
{
	const float nu = _kernel.state()[2] + shift;
	if (_config.axes != 4 || !_active || _open || _fault || !std::isfinite(shift)
	    || !std::isfinite(nu) || fabsf(nu) > _config.nu_limit[2]
	    || !std::isfinite(correction) || fabsf(correction) > _config.acceleration_limit[2]
	    || !std::isfinite(correction + shift) || fabsf(correction + shift) > _config.acceleration_limit[2]) {
		latch(Numerical); return false;
	}
	_kernel.reset(2, nu);
	return true;
}

bool StaVelocityProtection::same(const Config &a, const Config &b)
{
	if (a.axes != b.axes) { return false; }

	for (size_t i = 0; i < 3; ++i) {
		if (a.axes & (1 << i)) {
			if (memcmp(&a.gains[i].lambda1, &b.gains[i].lambda1, sizeof(float))
			    || memcmp(&a.gains[i].lambda2, &b.gains[i].lambda2, sizeof(float))
			    || memcmp(&a.nu_limit[i], &b.nu_limit[i], sizeof(float))
			    || memcmp(&a.acceleration_limit[i], &b.acceleration_limit[i], sizeof(float))) { return false; }
		}
	}

	return true;
}

void StaVelocityProtection::resetState()
{
	_kernel.reset();
	_active = false;
	_open = false;
}

bool StaVelocityProtection::configure(const Config &c, bool armed)
{
	_rejected = !validConfig(c);
	_pending = armed && (!_configured || !same(c, _config));

	if (armed || _rejected) { return !_rejected; }

	if (!_configured || !same(c, _config)) {
		_config = c;
		for (size_t i = 0; i < 3; ++i) {
			if (c.axes & (1 << i)) { _kernel.setParameters(i, c.gains[i]); }
		}
		resetState();
		++_generation;
		_configured = true;
	}

	_pending = false;
	return true;
}

void StaVelocityProtection::latch(uint16_t reason)
{
	_fault |= reason;
	_result.fault = _fault;
	_result.flags |= Latched;
	_open = false;
}

const StaVelocityProtection::Result &StaVelocityProtection::begin(const Frame &f)
{
	_open = false;
	_result = {};
	_result.nu_before = _result.nu_ideal = _result.nu_applied = _kernel.state();
	const uint64_t previous = _last_sample;

	// Disarm clears a latch; no automatic PID takeover is claimed.
	if (!f.armed) {
		_fault = 0; resetState(); _result.flags |= Reset; _result.nu_applied = _kernel.state();
	}
	_result.fault = _fault;

	_last_sample = f.sample;
	_result.raw_dt = previous ? static_cast<float>((static_cast<int64_t>(f.sample)
			 - static_cast<int64_t>(previous)) * 1e-6) : 0.f;
	const bool run = _configured && _config.axes && f.armed && f.enabled
			 && f.flying && !f.landed && !f.contact;

	if (!run) {
		if (_active) { _result.flags |= Reset; }
		resetState();
		_result.nu_applied = _kernel.state();
		_result.flags |= Inactive;
		return _result;
	}

	if (previous && f.sample == previous) {
		_result.flags |= Duplicate;
		return _result;
	}

	if (_fault) { _result.flags |= Latched; return _result; }
	if (!f.inner_valid) { latch(Feedback); return _result; }

	if (!f.sample || (previous && (_result.raw_dt < .002f || _result.raw_dt > .04f))) {
		latch(Time); return _result;
	}

	if (f.unmatched_reset_axes & _config.axes) { latch(ResetMismatch); return _result; }

	// XY target pair can be NaN (acceleration-only), but cannot be half-enabled.
	if (std::isfinite(f.target[0]) != std::isfinite(f.target[1])) { latch(Measurement); return _result; }

	for (size_t i = 0; i < 3; ++i) {
		if ((_config.axes & (1 << i)) && std::isinf(f.target[i])) { latch(Measurement); return _result; }
		if ((_config.axes & (1 << i)) && std::isfinite(f.target[i])) {
			if (!std::isfinite(f.velocity[i]) || std::isinf(f.ff[i])) { latch(Measurement); return _result; }
			_result.active_axes |= 1 << i;
		}
	}

	if (!_result.active_axes) {
		resetState(); _result.nu_applied = _kernel.state(); _result.flags |= Inactive | Reset; return _result;
	}

	if (!_active || !previous) {
		_kernel.reset(); _active = true; _result.nu_applied = _kernel.state();
		_result.flags |= Priming | Reset; return _result;
	}

	for (size_t i = 0; i < 3; ++i) {
		if (_result.active_axes & (1 << i)) {
			auto &c = _candidates[i];
			c = _kernel.evaluate(i, f.velocity[i], f.target[i], _result.raw_dt);
			if (!c.valid()) { latch(Numerical); return _result; }
			_result.s[i] = c.s;
			_result.a_sta[i] = c.a_sta;
			_result.nu_before[i] = c.nu_before;
			_result.nu_ideal[i] = c.nu_next;
			const float limited = std::max(-_config.acceleration_limit[i], std::min(c.a_sta, _config.acceleration_limit[i]));
			if (fabsf(limited - c.a_sta) > 0.f) { _result.flags |= CorrectionLimit; }
			_result.a_req[i] = limited + (std::isfinite(f.ff[i]) ? f.ff[i] : 0.f);
			if (!std::isfinite(_result.a_req[i])) { latch(Numerical); return _result; }
		}
	}

	_open = true;
	return _result;
}

const StaVelocityProtection::Result &StaVelocityProtection::finish(const Vec &proxy, uint8_t constrained_axes,
		bool feedback_valid)
{
	if (!_open) { _result.committed_axes = 0; return _result; }
	_open = false;
	_result.a_proxy = proxy;
	if (!feedback_valid) { latch(Feedback); return _result; }
	Vec applied = _kernel.state();

	for (size_t i = 0; i < 3; ++i) {
		if (_result.active_axes & (1 << i)) {
			const auto &c = _candidates[i];
			if (!std::isfinite(proxy[i]) || !_kernel.current(c)) { latch(Feedback); return _result; }
			float next = std::max(-_config.nu_limit[i], std::min(c.nu_next, _config.nu_limit[i]));
			if (fabsf(next - c.nu_next) > 0.f) { _result.flags |= StateLimit; }
			const float increment = next - c.nu_before;
			const float correction_residual = c.a_sta - std::max(-_config.acceleration_limit[i],
					std::min(c.a_sta, _config.acceleration_limit[i]));
			// Freeze only increments deepening a real constraint; unconstrained
			// thrust-map mismatch (including Z scaling) alone must not freeze nu.
			if (increment * correction_residual > 0.f || ((constrained_axes & (1 << i))
			    && increment * (_result.a_req[i] - proxy[i]) > 0.f)) {
				next = c.nu_before; _result.flags |= OutwardFreeze;
			}
			applied[i] = next;
		}
	}

	for (size_t i = 0; i < 3; ++i) {
		if (_result.active_axes & (1 << i)) {
			_kernel.commitProtected(_candidates[i], applied[i]); // All axes prevalidated; no intervening mutation.
			_result.committed_axes |= 1 << i;
		}
	}
	_result.nu_applied = _kernel.state();
	return _result;
}
