// SPDX-License-Identifier: BSD-3-Clause
#include "ProperIstaProtection.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>

namespace
{
bool sameFloat(float a, float b)
{
	uint32_t x, y;
	std::memcpy(&x, &a, sizeof(x));
	std::memcpy(&y, &b, sizeof(y));
	return x == y;
}
}

ProperIstaProtection::Output::Output()
{
	const float nan = std::numeric_limits<float>::quiet_NaN();
	ideal_a.fill(nan); ideal_c.fill(nan); ideal_nu.fill(nan); virtual_s.fill(nan); xi.fill(nan);
	state_mapped_a.fill(nan); preclip_c.fill(nan); applied_c.fill(nan); applied_nu.fill(nan);
	branch.fill(255); limits.fill(0); strict_implicit.fill(false);
}

bool ProperIstaProtection::same(const Config &a, const Config &b)
{
	if (a.enabled != b.enabled || a.axes != b.axes || !sameFloat(a.c_limit, b.c_limit)) { return false; }
	for (size_t i = 0; i < 3; ++i) {
		if (!sameFloat(a.gains[i].lambda1, b.gains[i].lambda1)
		    || !sameFloat(a.gains[i].lambda2, b.gains[i].lambda2)
		    || !sameFloat(a.gains[i].g, b.gains[i].g)
		    || !sameFloat(a.nu_limit[i], b.nu_limit[i])) { return false; }
	}
	return true;
}

bool ProperIstaProtection::validConfig(const Config &c)
{
	if (c.axes < 0 || c.axes > 7 || !std::isfinite(c.c_limit) || c.c_limit <= 0.f || c.c_limit > 1.f
	    || (c.enabled && c.axes == 0)) { return false; }
	for (size_t i = 0; i < 3; ++i) {
		if ((c.axes & (1 << i)) && (!ProperIstaRateControl::validParameters(c.gains[i])
					    || !std::isfinite(c.nu_limit[i]) || c.nu_limit[i] <= 0.f)) { return false; }
	}
	return true;
}

void ProperIstaProtection::reset()
{
	for (auto &kernel : _kernel) { kernel.reset(); }
}

void ProperIstaProtection::begin(const Config &requested, const Frame &frame)
{
	_used = false;
	_frame = frame;
	const bool request_valid = validConfig(requested);
	_pending = frame.armed && !same(requested, _config);

	if (!frame.armed && request_valid && (!_started || !same(requested, _config))) {
		_config = requested;
		for (size_t axis = 0; axis < 3; ++axis) {
			if (_config.axes & (1 << axis)) { _kernel[axis].setParameters(axis, _config.gains[axis]); }
		}
		reset();
	}
	if (_previous.armed && !frame.armed) { reset(); }

	Fault timing = Fault::None;
	if (!_last_sample || !frame.sample) { timing = Fault::FirstSample; }
	else if (frame.sample == _last_sample) { timing = Fault::DuplicateTime; }
	else if (frame.sample < _last_sample) { timing = Fault::BackwardTime; }
	else if (frame.sample - _last_sample > 20000) { timing = Fault::LongGap; }
	else if (frame.sample - _last_sample < 125) { timing = Fault::ShortDt; }
	_last_sample = frame.sample;

	if (frame.armed && frame.rate_enabled && (_config.enabled || requested.enabled)) {
		// Armed edits remain pending. Only the effective disarmed-applied
		// configuration can control or invalidate this frame.
		if (!_config.enabled || !validConfig(_config)) { latch(Fault::Configuration); }
		else if (!frame.measurement_valid) { latch(Fault::Measurement); }
		else if (timing != Fault::None) { latch(timing); }
	}
	_previous = frame;
	_started = true;
}

bool ProperIstaProtection::acknowledge()
{
	if (_frame.armed) { return false; }
	_fault = Fault::None;
	reset();
	return true;
}

const std::array<float, 3> ProperIstaProtection::state() const
{
	std::array<float, 3> out{};
	for (size_t axis = 0; axis < 3; ++axis) { out[axis] = _kernel[axis].state()[axis]; }
	return out;
}

ProperIstaProtection::Output ProperIstaProtection::step(const std::array<float, 3> &rate,
		const std::array<float, 3> &sp, const StaProtection::Feedback &feedback, float dt)
{
	Output out;
	if (_used || !_config.enabled || !_frame.armed || !_frame.rate_enabled || _fault != Fault::None) { return out; }
	_used = true;
	if (!std::isfinite(dt) || dt < 0.000125f || dt > 0.08f) { latch(Fault::Numerical); return out; }

	std::array<ProperIstaRateControl::Candidate, 3> candidates{};
	std::array<float, 3> protected_nu{};
	for (size_t axis = 0; axis < 3; ++axis) {
		if (!(_config.axes & (1 << axis))) { continue; }
		candidates[axis] = _kernel[axis].evaluate(axis, rate[axis], sp[axis], dt);
		const auto &ideal = candidates[axis].result();
		if (!ideal.valid()) { latch(Fault::Numerical); return Output{}; }
		StaProtection::Feedback scalar_feedback = feedback;
		scalar_feedback.bits = static_cast<uint16_t>((feedback.bits & 1)
					       | ((feedback.bits >> (2 * axis)) & ((1 << 3) | (1 << 4))));
		const auto protected_state = StaProtection::protectState(_kernel[axis].state()[axis], ideal.nu_next,
						ideal.c_raw, _config.gains[axis].g, _config.nu_limit[axis],
						_config.c_limit, scalar_feedback);
		if (!protected_state.valid) { latch(Fault::Numerical); return Output{}; }
		protected_nu[axis] = _frame.update_allowed ? protected_state.nu : _kernel[axis].state()[axis];
		const float delta = protected_nu[axis] - ideal.nu_next;
		const float mapped_a = ideal.a + 2.f * delta; // PDF (11a): a contains 2*nu_next
		const float preclip_c = mapped_a / _config.gains[axis].g;
		if (!std::isfinite(mapped_a) || !std::isfinite(preclip_c)) { latch(Fault::Numerical); return Output{}; }

		out.ideal_a[axis] = ideal.a; out.ideal_c[axis] = ideal.c_raw; out.ideal_nu[axis] = ideal.nu_next;
		out.virtual_s[axis] = ideal.virtual_s; out.xi[axis] = ideal.xi;
		out.branch[axis] = static_cast<uint8_t>(ideal.branch); out.limits[axis] = protected_state.limits;
		out.state_mapped_a[axis] = mapped_a; out.preclip_c[axis] = preclip_c;
		out.applied_c[axis] = std::max(-_config.c_limit, std::min(_config.c_limit, preclip_c));
		out.applied_nu[axis] = protected_nu[axis];
		if (!sameFloat(out.applied_c[axis], preclip_c)) { out.limits[axis] |= StaProtection::OutputLimit; }
		out.strict_implicit[axis] = sameFloat(protected_nu[axis], ideal.nu_next)
					    && sameFloat(out.applied_c[axis], ideal.c_raw);
	}

	// All candidates and constrained values are validated before any state is
	// committed. In this single-threaded object their generations cannot change.
	for (size_t axis = 0; axis < 3; ++axis) {
		if ((_config.axes & (1 << axis)) && !_kernel[axis].commitProtected(candidates[axis], protected_nu[axis])) {
			latch(Fault::Numerical);
			return Output{};
		}
	}
	out.valid = true;
	out.updated = _frame.update_allowed;
	return out;
}
