// SPDX-License-Identifier: BSD-3-Clause
#include "StaVelocityProtection.hpp"
#include <cmath>
#include <algorithm>
#include <cstring>

bool StaVelocityProtection::validConfig(const Config &c)
{
	if (c.axes > 7 || (c.variant != 1 && c.variant != 3 && c.variant != 4)) { return false; }
	if ((c.variant == 3 || c.variant == 4) && c.axes != 0 && c.axes != 1 && c.axes != 3 && c.axes != 4 && c.axes != 7) { return false; }

	for (size_t i = 0; i < 3; ++i) {
		if ((c.axes & (1 << i)) && (!StaVelocityControl::validParameters(c.gains[i])
		    || ((c.variant == 3 || c.variant == 4) && !RegularizedStaVelocityControl::validEpsilon(c.epsilon[i]))
		    || !std::isnormal(c.nu_limit[i]) || c.nu_limit[i] <= 0.f
		    || !std::isnormal(c.acceleration_limit[i]) || c.acceleration_limit[i] <= 0.f)) { return false; }
	}

	return true;
}

bool StaVelocityProtection::seedZ(float nu)
{
	if (_config.axes != 4 || !_active || _open || _fault || !(_result.flags & Priming)
	    || !std::isfinite(nu) || fabsf(nu) > _config.nu_limit[2]) { latch(Numerical); return false; }
	if (_config.variant == 4 && !_implicit_kernel.reset(2, nu)) { latch(Numerical); return false; }
	if (_config.variant != 4) { resetAxis(2, nu); }
	_result.nu_before[2] = _result.nu_ideal[2] = _result.nu_applied[2] = nu;
	return true;
}

bool StaVelocityProtection::shiftZ(float shift, float correction)
{
	const float nu = state()[2] + shift;
	if (!(_config.axes & 4) || !_active || _open || _fault || !std::isfinite(shift)
	    || !std::isfinite(nu) || fabsf(nu) > _config.nu_limit[2]
	    || !std::isfinite(correction) || fabsf(correction) > _config.acceleration_limit[2]
	    || !std::isfinite(correction + shift) || fabsf(correction + shift) > _config.acceleration_limit[2]) {
		latch(Numerical); return false;
	}
	if (_config.variant == 4 && !_implicit_kernel.reset(2, nu)) { latch(Numerical); return false; }
	if (_config.variant != 4) { resetAxis(2, nu); }
	return true;
}

bool StaVelocityProtection::seedXYZ(const Vec &nu)
{
	if (_config.axes != 7) { latch(Numerical); return false; }
	return seedCoupled(nu);
}

bool StaVelocityProtection::seedCoupled(const Vec &nu)
{
	if ((_config.axes != 5 && _config.axes != 6 && _config.axes != 7)
	    || !_active || _open || _fault || !(_result.flags & Priming)) {
		latch(Numerical); return false;
	}
	for (size_t i = 0; i < 3; ++i) {
		if ((_result.active_axes & (1u << i)) && (!std::isfinite(nu[i]) || fabsf(nu[i]) > _config.nu_limit[i])) {
			latch(Numerical); return false;
		}
	}
	if (_config.variant == 4 && !_implicit_kernel.resetBatch(_result.active_axes, nu)) { latch(Numerical); return false; }
	for (size_t i = 0; i < 3; ++i) {
		const float value = (_result.active_axes & (1u << i)) ? nu[i] : 0.f;
		if (_config.variant != 4) { resetAxis(i, value); }
		_result.nu_before[i] = _result.nu_ideal[i] = _result.nu_applied[i] = value;
	}
	return true;
}

bool StaVelocityProtection::same(const Config &a, const Config &b)
{
	if (a.axes != b.axes || a.variant != b.variant) { return false; }

	for (size_t i = 0; i < 3; ++i) {
		if (a.axes & (1 << i)) {
			if (memcmp(&a.gains[i].lambda1, &b.gains[i].lambda1, sizeof(float))
			    || memcmp(&a.gains[i].lambda2, &b.gains[i].lambda2, sizeof(float))
			    || ((a.variant == 3 || a.variant == 4) && memcmp(&a.epsilon[i], &b.epsilon[i], sizeof(float)))
			    || memcmp(&a.nu_limit[i], &b.nu_limit[i], sizeof(float))
			    || memcmp(&a.acceleration_limit[i], &b.acceleration_limit[i], sizeof(float))) { return false; }
		}
	}

	return true;
}

void StaVelocityProtection::resetState()
{
	_kernel.reset();
	_regularized_kernel.reset();
	_implicit_kernel.reset();
	_active = false;
	_open = false;
	_xyz_active_axes = 0;
}

void StaVelocityProtection::resetAxis(size_t axis, float nu)
{
	if (_config.variant == 4) { _implicit_kernel.reset(axis, nu); }
	else if (_config.variant == 3) { _regularized_kernel.reset(axis, nu); }
	else { _kernel.reset(axis, nu); }
}

bool StaVelocityProtection::configure(const Config &c, bool armed)
{
	_rejected = !validConfig(c);
	_pending = armed && (!_configured || !same(c, _config));

	if (armed || _rejected) { return !_rejected; }

	if (!_configured || !same(c, _config)) {
		_config = c;
		for (size_t i = 0; i < 3; ++i) {
			if (c.axes & (1 << i)) {
				if (c.variant == 4) {
					if (!_implicit_kernel.setParameters(i, {c.gains[i].lambda1, c.gains[i].lambda2, c.epsilon[i]})) { latch(Numerical); return false; }
				} else if (c.variant == 3) {
					_regularized_kernel.setParameters(i, {c.gains[i].lambda1, c.gains[i].lambda2, c.epsilon[i]});
				} else { _kernel.setParameters(i, c.gains[i]); }
			}
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
	if (_config.variant == 4) { _result.strict_axes = 0; }
	_result.fault = _fault;
	_result.flags |= Latched;
	_open = false;
}

const StaVelocityProtection::Result &StaVelocityProtection::begin(const Frame &f)
{
	_open = false;
	_result = {};
	_result.nu_before = _result.nu_ideal = _result.nu_applied = state();
	const uint64_t previous = _last_sample;

	// Disarm clears a latch; no automatic PID takeover is claimed.
	if (!f.armed) {
		_fault = 0; resetState(); _result.flags |= Reset; _result.nu_applied = state();
	}
	_result.fault = _fault;

	_last_sample = f.sample;
	_result.raw_dt = previous ? (_config.variant == 4
		? static_cast<float>((f.sample >= previous ? static_cast<double>(f.sample - previous)
			: -static_cast<double>(previous - f.sample)) * 1e-6)
		: static_cast<float>((static_cast<int64_t>(f.sample) - static_cast<int64_t>(previous)) * 1e-6)) : 0.f;
	const bool run = _configured && _config.axes && f.armed && f.enabled
			 && f.flying && !f.landed && !f.contact;

	if (!run) {
		if (_active) { _result.flags |= Reset; }
		resetState();
		_result.nu_applied = state();
		_result.flags |= Inactive;
		return _result;
	}

	if (previous && f.sample == previous) {
		_result.flags |= Duplicate;
		if (_config.variant == 4) { latch(Time); }
		return _result;
	}

	if (_fault) { _result.flags |= Latched; return _result; }
	if (!f.inner_valid) { latch(Feedback); return _result; }
	if ((_config.variant == 3 || _config.variant == 4) && f.divisor != 1) { latch(Time); return _result; }

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
		resetState(); _result.nu_applied = state(); _result.flags |= Inactive | Reset; return _result;
	}

	// XZ/YZ/XYZ mix velocity and acceleration-only targets. Any active-mask change
	// requires a fresh, explicit handover; never reuse an inactive axis's nu.
	if ((_config.axes == 5 || _config.axes == 6 || _config.axes == 7) && _result.active_axes != _xyz_active_axes) {
		resetState();
		_xyz_active_axes = _result.active_axes;
		_result.nu_before = _result.nu_ideal = _result.nu_applied = state();
	}

	if (!_active || !previous) {
		_kernel.reset(); _regularized_kernel.reset(); _implicit_kernel.reset(); _active = true; _result.nu_applied = state();
		_result.flags |= Priming | Reset; return _result;
	}
	if (!f.evaluate) {
		_result.flags |= Held;
		for (size_t i = 0; i < 3; ++i) {
			_result.a_sta[i] = _result.nu_ideal[i] = NAN; // no ideal candidate was evaluated
		}
		return _result;
	}
	if (_config.variant == 4 && (!std::isfinite(f.integration_dt) || f.integration_dt < 0.f
	    || (f.integration_dt > 0.f && fabsf(f.integration_dt - _result.raw_dt) > 0.f))) { latch(Time); return _result; }
	const float h = f.integration_dt > 0.f ? f.integration_dt : _result.raw_dt;
	if ((f.divisor != 1 && f.divisor != 2 && f.divisor != 4) || !std::isfinite(h)
	    || h < .002f || h > .04f * f.divisor) { latch(Time); return _result; }
	_result.kernel_dt = h;

	for (size_t i = 0; i < 3; ++i) {
		if (_result.active_axes & (1 << i)) {
			const auto store = [&](const auto &c) {
				if (!c.valid()) { return false; }
				_result.s[i] = c.s;
				_result.a_sta[i] = c.a_sta;
				_result.nu_before[i] = c.nu_before;
				_result.nu_ideal[i] = c.nu_next;
				return true;
			};
			bool valid = false;
			if (_config.variant == 4) {
				_implicit_candidates[i] = _implicit_kernel.evaluate(i, f.velocity[i], f.target[i], h);
				const auto &c = _implicit_candidates[i];
				valid = store(c);
				if (valid) { _result.p[i] = c.p; _result.psi[i] = c.psi; _result.rho[i] = c.rho; }
			} else if (_config.variant == 3) {
				_regularized_candidates[i] = _regularized_kernel.evaluate(i, f.velocity[i], f.target[i], h);
				valid = store(_regularized_candidates[i]);
			} else {
				_candidates[i] = _kernel.evaluate(i, f.velocity[i], f.target[i], h);
				valid = store(_candidates[i]);
			}
			if (!valid) { latch(Numerical); return _result; }
			const float limited = std::max(-_config.acceleration_limit[i], std::min(_result.a_sta[i], _config.acceleration_limit[i]));
			_result.correction_applied[i] = limited;
			if (fabsf(limited - _result.a_sta[i]) > 0.f) { _result.flags |= CorrectionLimit; }
			_result.a_req[i] = limited + (std::isfinite(f.ff[i]) ? f.ff[i] : 0.f);
			if (!std::isfinite(_result.a_req[i])) { latch(Numerical); return _result; }
		}
	}

	_result.candidate_axes = _result.active_axes;
	_open = true;
	return _result;
}

const StaVelocityProtection::Result &StaVelocityProtection::finish(const Vec &proxy, uint8_t constrained_axes,
		bool feedback_valid, uint8_t interval_positive, uint8_t interval_negative)
{
	if (!_open) { _result.committed_axes = 0; if (_config.variant == 4) { _result.strict_axes = 0; } return _result; }
	_open = false;
	_result.a_proxy = proxy;
	if (!feedback_valid) { latch(Feedback); return _result; }
	Vec applied = state();

	for (size_t i = 0; i < 3; ++i) {
		if (_result.active_axes & (1 << i)) {
			const bool current = _config.variant == 4 ? _implicit_kernel.current(_implicit_candidates[i])
				: (_config.variant == 3 ? _regularized_kernel.current(_regularized_candidates[i]) : _kernel.current(_candidates[i]));
			if (!std::isfinite(proxy[i]) || !current) { latch(Feedback); return _result; }
			// Derive the applied state from the immutable, sealed kernel proposal,
			// not from the separate diagnostic Result that copies those values.
			const float ideal = _config.variant == 4 ? _implicit_candidates[i].nu_next : (_config.variant == 3 ? _regularized_candidates[i].nu_next : _candidates[i].nu_next);
			const float before = _config.variant == 4 ? _implicit_candidates[i].nu_before : (_config.variant == 3 ? _regularized_candidates[i].nu_before : _candidates[i].nu_before);
			const float raw = _config.variant == 4 ? _implicit_candidates[i].a_sta : (_config.variant == 3 ? _regularized_candidates[i].a_sta : _candidates[i].a_sta);
			float next = std::max(-_config.nu_limit[i], std::min(ideal, _config.nu_limit[i]));
			if (fabsf(next - ideal) > 0.f) { _result.flags |= StateLimit; }
			const float increment = next - before;
			const float correction_residual = raw - std::max(-_config.acceleration_limit[i],
					std::min(raw, _config.acceleration_limit[i]));
			// Freeze only increments deepening a real constraint; unconstrained
			// thrust-map mismatch (including Z scaling) alone must not freeze nu.
			if ((increment > 0.f && (interval_positive & (1 << i)))
			    || (increment < 0.f && (interval_negative & (1 << i)))
			    || increment * correction_residual > 0.f || ((constrained_axes & (1 << i))
			    && increment * (_result.a_req[i] - proxy[i]) > 0.f)) {
				next = before; _result.flags |= OutwardFreeze;
			}
			applied[i] = next;
			if (_config.variant == 4 && !memcmp(&next, &ideal, sizeof(float)) && fabsf(correction_residual) <= 0.f
			    && !(constrained_axes & (1u << i))) { _result.strict_axes |= 1u << i; }
		}
	}
	if (_config.variant == 4) {
		if (_implicit_kernel.commitBatch(_implicit_candidates, _result.active_axes, applied) != RegularizedIstaVelocityControl::Status::Ok) {
			_result.strict_axes = 0; latch(Numerical); return _result;
		}
		_result.committed_axes = _result.active_axes;
		_result.nu_applied = state();
		return _result; // Frozen/clipped nu never rewrites this step's ideal a.
	}

	for (size_t i = 0; i < 3; ++i) {
		if (_result.active_axes & (1 << i)) {
			// All selected candidates prevalidated; no intervening state mutation.
			if (_config.variant == 3) { _regularized_kernel.commitProtected(_regularized_candidates[i], applied[i]); }
			else { _kernel.commitProtected(_candidates[i], applied[i]); }
			_result.committed_axes |= 1 << i;
		}
	}
	_result.nu_applied = state();
	return _result;
}

bool StaVelocityProtection::implicitSeed(size_t axis, float s, float correction, float &nu)
{
	if (_config.variant != 4 || axis >= 3 || !(_result.active_axes & (1u << axis)) || _open || _fault
	    || !(_result.flags & Priming) || _result.raw_dt < .002f || _result.raw_dt > .04f
	    || !std::isfinite(correction) || fabsf(correction) > _config.acceleration_limit[axis]) { latch(Numerical); return false; }
	RegularizedIstaVelocityControl probe;
	if (!probe.setParameters(axis, {_config.gains[axis].lambda1, _config.gains[axis].lambda2, _config.epsilon[axis]})) { latch(Numerical); return false; }
	const auto candidate = probe.evaluate(axis, s, 0.f, _result.raw_dt);
	if (!candidate.valid()) { latch(Numerical); return false; }
	nu = correction - candidate.a_sta; // F_h(s), not explicit lambda1*Psi(s).
	if (!std::isfinite(nu) || (fabsf(nu) > 0.f && !std::isnormal(nu)) || fabsf(nu) > _config.nu_limit[axis]) { latch(Numerical); return false; }
	_result.p[axis] = candidate.p; _result.psi[axis] = candidate.psi; _result.rho[axis] = candidate.rho;
	_result.seed_dt = _result.raw_dt;
	return true;
}

void StaVelocityProtection::abortImplicit(uint16_t reason, uint16_t flags)
{
	if (_config.variant != 4) { return; }
	_result = {};
	_result.nu_before = _result.nu_ideal = _result.nu_applied = state();
	_result.flags = flags;
	latch(reason);
}
