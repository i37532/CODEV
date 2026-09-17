// SPDX-License-Identifier: BSD-3-Clause
#include "StaProtection.hpp"
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

bool StaProtection::same(const Config &a, const Config &b)
{
	if (a.mode != b.mode || a.axes != b.axes || !sameFloat(a.c_limit, b.c_limit)) { return false; }

	for (size_t i = 0; i < 3; ++i) {
		if (!sameFloat(a.gains[i].lambda1, b.gains[i].lambda1) || !sameFloat(a.gains[i].lambda2, b.gains[i].lambda2)
		    || !sameFloat(a.gains[i].g, b.gains[i].g) || !sameFloat(a.nu_limit[i], b.nu_limit[i])) { return false; }
	}

	return true;
}

bool StaProtection::validConfig(const Config &c)
{
	if (c.mode < 0 || c.mode > 2 || c.axes < 0 || c.axes > 7 || !std::isfinite(c.c_limit)
	    || c.c_limit <= 0.f || c.c_limit > 1.f || (c.mode != 0 && c.axes == 0)) { return false; }

	for (size_t i = 0; i < 3; ++i) {
		if ((c.axes & (1 << i)) && (!StaRateControl::validParameters(c.gains[i])
					    || !std::isfinite(c.nu_limit[i]) || c.nu_limit[i] <= 0.f)) { return false; }
	}

	return true;
}

void StaProtection::begin(const Config &requested, const Frame &frame)
{
	_reset = 0;
	_used = false;
	_frame = frame;
	_request_valid = validConfig(requested);
	_pending = frame.armed && !same(requested, _config);

	if (!_started) { clear(Startup); }

	if (!frame.armed && _request_valid && (!_started || !same(requested, _config))) {
		_config = requested;

		for (size_t i = 0; i < 3; ++i) {
			if (requested.axes & (1 << i)) {
				_kernel.setParameters(i, requested.gains[i]);
				_ista.setParameters(i, requested.gains[i]);
			}
		}

		++_config_seq;
		clear(ConfigChanged);
	}

	if (_previous.armed && !frame.armed) { clear(Disarm); }

	if ((_previous.rate_enabled && !frame.rate_enabled) || (_previous.experiment_active && !frame.experiment_active)) { clear(Exit); }

	if (frame.landed && (!_started || !_previous.landed)) { clear(Landed); }

	_raw_dt = _last_sample ? static_cast<float>((static_cast<double>(frame.sample) - static_cast<double>
			(_last_sample)) * 1e-6)
		  : std::numeric_limits<float>::quiet_NaN();
	_timing = None;

	if (!_last_sample || !frame.sample) { _timing = FirstSample; }

	else if (frame.sample == _last_sample) { _timing = DuplicateTime; }

	else if (frame.sample < _last_sample) { _timing = BackwardTime; }

	else if (frame.sample - _last_sample > 20000) { _timing = LongGap; }

	else if (frame.sample - _last_sample < 125) { _timing = ShortDt; }

	_last_sample = frame.sample;
	_allowed = frame.experiment_active && frame.armed && frame.rate_enabled && !frame.landed && !frame.maybe_landed;

	if (frame.experiment_active && frame.armed && frame.rate_enabled) {
		if ((_config.mode != 1 && _config.mode != 2) || !validConfig(_config) || (!_previous.armed && !_request_valid)) { latch(Configuration); }

		else if (!frame.measurement_valid) { latch(Measurement); }

		else if (_timing != None) { latch(_timing); }
	}

	_previous = frame;
	_started = true;
}

bool StaProtection::acknowledge()
{
	if (_frame.armed) { return false; }

	_fault = None;
	clear(Acknowledge);
	return true;
}

StaProtection::Output StaProtection::step(const std::array<float, 3> &rate, const std::array<float, 3> &sp,
		const Feedback &feedback, bool allow_frozen)
{
	Output out{};
	const float nan = std::numeric_limits<float>::quiet_NaN();
	out.a.fill(nan); out.c_raw.fill(nan); out.c_applied.fill(nan);
	out.nu = state();

	// Land/maybe_landed freeze nu, not the proportional correction needed for
	// takeoff. The staged SITL application explicitly requests this evaluation.
	const bool frozen_evaluation = allow_frozen && _frame.experiment_active && _frame.armed
				       && _frame.rate_enabled && !_used && _fault == None;

	if (!canUpdate() && !frozen_evaluation) { return out; }

	_used = true;
	StaRateControl proposal = _kernel; // all selected axes commit together, or none do
	IstaRateControl implicit_proposal = _ista;
	const auto failure = [this]() { Output invalid; invalid.nu = state(); return invalid; };

	for (size_t i = 0; i < 3; ++i) {
		if (!(_config.axes & (1 << i))) { continue; }

		StaRateControl::Result candidate;

		if (_config.mode == 2) {
			const auto implicit = implicit_proposal.update(i, rate[i], sp[i], _raw_dt);
			candidate = implicit;
			out.xi[i] = implicit.xi; out.virtual_s[i] = implicit.virtual_s;
			out.branch[i] = static_cast<uint8_t>(implicit.branch);

		} else {
			candidate = proposal.update(i, rate[i], sp[i], _raw_dt);
		}

		if (!candidate.valid()) { latch(Numerical); return failure(); }

		float nu = candidate.nu_next;
		const float delta_c = (nu - state()[i]) / _config.gains[i].g;

		if (!std::isfinite(delta_c)) { latch(Numerical); return failure(); }

		if (!feedback.valid()) {
			nu = state()[i]; out.limits[i] |= FeedbackInvalid;

		} else if ((delta_c > 0.f && (feedback.bits & (1 << (3 + 2 * i))))
			   || (delta_c < 0.f && (feedback.bits & (1 << (4 + 2 * i))))) {
			nu = state()[i]; out.limits[i] |= MixerFreeze;
		}

		// Also prevent further windup in the direction of our own command limit.
		if ((candidate.c_raw > _config.c_limit && delta_c > 0.f)
		    || (candidate.c_raw < -_config.c_limit && delta_c < 0.f)) {
			nu = state()[i]; out.limits[i] |= OutputLimit;
		}

		const float bounded = std::max(-_config.nu_limit[i], std::min(_config.nu_limit[i], nu));

		if (bounded < nu || bounded > nu) { out.limits[i] |= NuLimit; }

		const float applied_nu = _allowed ? bounded : state()[i];
		float protected_a = candidate.a;
		float protected_c = candidate.c_raw;

		if (_config.mode == 2) {
			implicit_proposal.reset(i, applied_nu);
			// Keep the ideal root/xi for diagnostics, replace ONLY its additive
			// nu_next by protected nu. This constrained law is NOT a new implicit
			// solution; do not relabel its applied output as the ideal prediction.
			if (!sameFloat(applied_nu, candidate.nu_next)) {
				protected_a = candidate.a + (applied_nu - candidate.nu_next);
				protected_c = protected_a / _config.gains[i].g;
			}

		} else {
			proposal.reset(i, applied_nu); // preserve ESTA old-nu output EXACTLY
		}

		if (!std::isfinite(protected_a) || !std::isfinite(protected_c)) { latch(Numerical); return failure(); }

		out.nu_candidate[i] = candidate.nu_next; out.a_protected[i] = protected_a;
		out.a[i] = candidate.a; out.c_raw[i] = candidate.c_raw;
		out.c_applied[i] = std::max(-_config.c_limit, std::min(_config.c_limit, protected_c));

		if (protected_c < -_config.c_limit || protected_c > _config.c_limit) { out.limits[i] |= OutputLimit; }
	}

	_kernel = proposal;
	_ista = implicit_proposal;
	out.nu = state(); out.valid = true; out.updated = _allowed;
	return out;
}
