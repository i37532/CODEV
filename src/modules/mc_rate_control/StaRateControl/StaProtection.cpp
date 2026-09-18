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
	if (a.mode != b.mode || a.axes != b.axes || !sameFloat(a.c_limit, b.c_limit)
	    || !TakeoffNuManager::sameConfig(a.takeoff, b.takeoff)) { return false; }

	for (size_t i = 0; i < 3; ++i) {
		if (!sameFloat(a.gains[i].lambda1, b.gains[i].lambda1) || !sameFloat(a.gains[i].lambda2, b.gains[i].lambda2)
		    || !sameFloat(a.gains[i].g, b.gains[i].g) || !sameFloat(a.nu_limit[i], b.nu_limit[i])) { return false; }
	}

	return true;
}

bool StaProtection::validConfig(const Config &c)
{
	if (c.mode < 0 || c.mode > 3 || c.axes < 0 || c.axes > 7 || !std::isfinite(c.c_limit)
	    || c.c_limit <= 0.f || c.c_limit > 1.f || (c.mode != 0 && c.axes == 0)
	    || (c.mode == 3 && c.axes != 1 && c.axes != 3)
	    || !TakeoffNuManager::validConfig(c.takeoff)) { return false; }

	for (size_t i = 0; i < 3; ++i) {
		if ((c.axes & (1 << i)) && (!StaRateControl::validParameters(c.gains[i])
					    || !std::isfinite(c.nu_limit[i]) || c.nu_limit[i] <= 0.f)) { return false; }
	}

	return true;
}

StaProtection::StateDecision StaProtection::protectState(float old_nu, float candidate_nu, float candidate_c, float g,
		float nu_limit, float c_limit, const Feedback &feedback)
{
	StateDecision out;
	if (!std::isfinite(old_nu) || !std::isfinite(candidate_nu) || !std::isfinite(candidate_c)
	    || !std::isfinite(g) || g <= 0.f || !std::isfinite(nu_limit) || nu_limit <= 0.f
	    || !std::isfinite(c_limit) || c_limit <= 0.f) { return out; }

	float nu = candidate_nu;
	const float delta_c = (candidate_nu - old_nu) / g;
	if (!std::isfinite(delta_c)) { return out; }

	if (!feedback.valid()) {
		nu = old_nu;
		out.limits |= FeedbackInvalid;
	} else {
		// Mixer bits: 3/4 roll +/-, 5/6 pitch +/-, 7/8 yaw +/-.
		// The caller supplies one-axis feedback by shifting the relevant pair
		// into the roll positions before using this common scalar policy.
		if ((delta_c > 0.f && (feedback.bits & (1 << 3)))
		    || (delta_c < 0.f && (feedback.bits & (1 << 4)))) {
			nu = old_nu;
			out.limits |= MixerFreeze;
		}
	}

	if ((candidate_c > c_limit && delta_c > 0.f) || (candidate_c < -c_limit && delta_c < 0.f)) {
		nu = old_nu;
		out.limits |= OutputLimit;
	}

	if (nu > nu_limit) { nu = nu_limit; out.limits |= NuLimit; }
	if (nu < -nu_limit) { nu = -nu_limit; out.limits |= NuLimit; }
	out.nu = nu;
	out.valid = std::isfinite(nu);
	return out;
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
				_proper.setParameters(i, requested.gains[i]);
			}
		}

		++_config_seq;
		clear(ConfigChanged);
	}
	_takeoff.setConfig(_config.takeoff);

	if (_previous.armed && !frame.armed) { clear(Disarm); }

	if ((_previous.rate_enabled && !frame.rate_enabled) || (_previous.experiment_active && !frame.experiment_active)) { clear(Exit); }

	TakeoffNuManager::Input takeoff_input;
	takeoff_input.sample = frame.sample;
	takeoff_input.selected = frame.experiment_active;
	takeoff_input.armed = frame.armed;
	takeoff_input.rate_enabled = frame.rate_enabled;
	takeoff_input.landed = frame.landed;
	takeoff_input.maybe_landed = frame.maybe_landed;
	takeoff_input.estimate_valid = frame.local_position_valid;
	takeoff_input.z_m = frame.local_z;
	takeoff_input.vz_m_s = frame.local_vz;
	_takeoff_decision = _takeoff.update(takeoff_input);

	if (!_config.takeoff.enabled) {
		if (frame.landed && (!_started || !_previous.landed)) { clear(Landed); }
	} else {
		if (_takeoff_decision.reset) { clear(TakeoffManaged); }
	}

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
	_allowed = frame.experiment_active && frame.armed && frame.rate_enabled && !frame.landed && !frame.maybe_landed
		   && (!_config.takeoff.enabled || !_takeoff_decision.freeze);

	if ((frame.experiment_active || frame.decimated) && frame.armed && frame.rate_enabled) {
		if (frame.experiment_active && ((_config.mode != 1 && _config.mode != 2 && _config.mode != 3)
					      || !validConfig(_config)
					      || (!_previous.armed && !_request_valid))) { latch(Configuration); }

		else if (!frame.measurement_valid) { latch(Measurement); }

		else if (_timing != None) { latch(_timing); }
	}

	// Preserve the existing measurement/timing fault precedence. The manager's
	// own estimator-jump/timeout latch is considered only after common checks.
	if (_config.takeoff.enabled && _takeoff_decision.abort) { latch(TakeoffManagement); }

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
		const Feedback &feedback, bool allow_frozen, float update_dt)
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
	// Zero selects legacy callback dt. M09 h spans up to four valid callbacks.
	const float h = sameFloat(update_dt, 0.f) ? _raw_dt : update_dt;
	if (!std::isfinite(h) || h < 0.000125f || h > 0.08f) { latch(Numerical); return out; }
	StaRateControl proposal = _kernel; // all selected axes commit together, or none do
	IstaRateControl implicit_proposal = _ista;
	std::array<ProperIstaRateControl::Candidate, 3> proper_candidates{};
	std::array<float, 3> proper_applied_nu{};
	const auto failure = [this]() { Output invalid; invalid.nu = state(); return invalid; };

	for (size_t i = 0; i < 3; ++i) {
		if (!(_config.axes & (1 << i))) { continue; }

		StaRateControl::Result candidate;

		if (_config.mode == 3) {
			proper_candidates[i] = _proper.evaluate(i, rate[i], sp[i], h);
			const auto &proper = proper_candidates[i].result();
			candidate = proper;
			out.xi[i] = proper.xi; out.virtual_s[i] = proper.virtual_s;
			out.branch[i] = static_cast<uint8_t>(proper.branch);

		} else if (_config.mode == 2) {
			const auto implicit = implicit_proposal.update(i, rate[i], sp[i], h);
			candidate = implicit;
			out.xi[i] = implicit.xi; out.virtual_s[i] = implicit.virtual_s;
			out.branch[i] = static_cast<uint8_t>(implicit.branch);

		} else {
			candidate = proposal.update(i, rate[i], sp[i], h);
		}

		if (!candidate.valid()) { latch(Numerical); return failure(); }

		Feedback scalar_feedback = feedback;
		scalar_feedback.bits = static_cast<uint16_t>((feedback.bits & 1)
				       | ((feedback.bits >> (2 * i)) & ((1 << 3) | (1 << 4))));
		const auto protected_state = protectState(state()[i], candidate.nu_next, candidate.c_raw,
					     _config.gains[i].g, _config.nu_limit[i], _config.c_limit, scalar_feedback);
		if (!protected_state.valid) { latch(Numerical); return failure(); }
		out.limits[i] = protected_state.limits;
		const float applied_nu = _allowed ? protected_state.nu : state()[i];
		proper_applied_nu[i] = applied_nu;
		float protected_a = candidate.a;
		float protected_c = candidate.c_raw;

		if (_config.mode == 3) {
			// Proper PDF (11a) contains 2*nu_next. If protection freezes or
			// clamps the state, map that state change with coefficient two.
			// The constrained tuple is diagnostic/applied output, not a new
			// strict solution of the ideal implicit equations.
			if (!sameFloat(applied_nu, candidate.nu_next)) {
				protected_a = candidate.a + 2.f * (applied_nu - candidate.nu_next);
				protected_c = protected_a / _config.gains[i].g;
			}

		} else if (_config.mode == 2) {
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

	if (_config.mode == 3) {
		for (size_t i = 0; i < 3; ++i) {
			if ((_config.axes & (1 << i)) && !_proper.commitProtected(proper_candidates[i], proper_applied_nu[i])) {
				latch(Numerical);
				return failure();
			}
		}
	}

	_kernel = proposal;
	_ista = implicit_proposal;
	out.nu = state(); out.valid = true; out.updated = _allowed;
	return out;
}
