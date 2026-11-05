// SPDX-License-Identifier: BSD-3-Clause
#include "TakeoffNuManager.hpp"

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

bool TakeoffNuManager::validConfig(const Config &c)
{
	return std::isfinite(c.release_height_m) && c.release_height_m > 0.f
	       && std::isfinite(c.max_takeoff_vz_m_s) && c.max_takeoff_vz_m_s >= 0.f
	       && std::isfinite(c.max_estimator_step_m) && c.max_estimator_step_m > c.release_height_m
	       && std::isfinite(c.landing_height_m) && c.landing_height_m >= 0.f
	       && c.landing_height_m < c.release_height_m
	       && std::isfinite(c.max_landing_speed_m_s) && c.max_landing_speed_m_s >= 0.f
	       && c.takeoff_confirm_us > 0 && c.landing_confirm_us > 0
	       && c.wait_timeout_us > c.takeoff_confirm_us;
}

bool TakeoffNuManager::sameConfig(const Config &a, const Config &b)
{
	return a.enabled == b.enabled && sameFloat(a.release_height_m, b.release_height_m)
	       && sameFloat(a.max_takeoff_vz_m_s, b.max_takeoff_vz_m_s)
	       && sameFloat(a.max_estimator_step_m, b.max_estimator_step_m)
	       && sameFloat(a.landing_height_m, b.landing_height_m)
	       && sameFloat(a.max_landing_speed_m_s, b.max_landing_speed_m_s)
	       && a.takeoff_confirm_us == b.takeoff_confirm_us && a.landing_confirm_us == b.landing_confirm_us
	       && a.wait_timeout_us == b.wait_timeout_us;
}

bool TakeoffNuManager::setConfig(const Config &config)
{
	if (!validConfig(config)) { return false; }
	const bool changed = !sameConfig(config, _config);
	if (changed) { reset(); }
	_config = config;
	if (changed) { _state = config.enabled ? State::Idle : State::Disabled; }
	return true;
}

void TakeoffNuManager::reset()
{
	_state = _config.enabled ? State::Idle : State::Disabled;
	_wait_start = 0;
	_confirm_start = 0;
	_last_sample = 0;
	_arm_z = 0.f;
	_last_z = 0.f;
	_baseline_valid = false;
}

bool TakeoffNuManager::estimateValid(const Input &input) const
{
	return input.estimate_valid && std::isfinite(input.z_m) && std::isfinite(input.vz_m_s);
}

bool TakeoffNuManager::takeoffEvidence(const Input &input) const
{
	return _baseline_valid && estimateValid(input) && !input.landed && !input.maybe_landed
	       && (_arm_z - input.z_m) >= _config.release_height_m
	       && input.vz_m_s <= _config.max_takeoff_vz_m_s;
}

bool TakeoffNuManager::landingEvidence(const Input &input) const
{
	return _baseline_valid && estimateValid(input) && (input.landed || input.maybe_landed)
	       && std::fabs(input.z_m - _arm_z) <= _config.landing_height_m
	       && std::fabs(input.vz_m_s) <= _config.max_landing_speed_m_s;
}

TakeoffNuManager::Decision TakeoffNuManager::decision(Event event, bool reset_state) const
{
	Decision out;
	out.state = _state;
	out.event = event;
	out.freeze = _state != State::Released && _state != State::Disabled && _state != State::Idle;
	out.reset = reset_state;
	out.abort = _state == State::Fault;
	return out;
}

void TakeoffNuManager::enterWaiting(const Input &input)
{
	_state = State::Waiting;
	_wait_start = input.sample;
	_confirm_start = 0;
	_baseline_valid = estimateValid(input);
	if (_baseline_valid) { _arm_z = _last_z = input.z_m; }
}

TakeoffNuManager::Decision TakeoffNuManager::update(const Input &input)
{
	if (!_config.enabled) {
		_state = State::Disabled;
		return decision();
	}

	if (!input.armed) {
		const bool transitioned = _state != State::Idle;
		reset();
		_state = State::Idle;
		return decision(transitioned ? Event::Disarm : Event::None);
	}

	if (!input.selected || !input.rate_enabled) {
		_state = State::Idle;
		_wait_start = _confirm_start = _last_sample = 0;
		_baseline_valid = false;
		return decision();
	}

	if (_state == State::Idle || _state == State::Disabled) {
		enterWaiting(input);
		_last_sample = input.sample;
		return decision(Event::Arm, true);
	}

	// Common protection owns duplicate/backward/long-gap timing.  Here only a
	// monotonic sample is consumed so timeout/confirm arithmetic cannot wrap.
	if (!input.sample || (_last_sample && input.sample <= _last_sample)) {
		return decision();
	}

	const bool estimate_valid = estimateValid(input);
	if (estimate_valid) {
		if (!_baseline_valid) {
			_baseline_valid = true;
			_arm_z = _last_z = input.z_m;
		} else if (std::fabs(input.z_m - _last_z) > _config.max_estimator_step_m) {
			_state = State::Fault;
			_last_sample = input.sample;
			return decision(Event::EstimatorJump);
		} else {
			_last_z = input.z_m;
		}
	}
	_last_sample = input.sample;

	if (_state == State::Fault) { return decision(); }

	if ((_state == State::Waiting || _state == State::ConfirmingTakeoff)
	    && input.sample - _wait_start >= _config.wait_timeout_us) {
		_state = State::Fault;
		return decision(Event::Timeout);
	}

	switch (_state) {
	case State::Waiting:
		if (takeoffEvidence(input)) {
			_state = State::ConfirmingTakeoff;
			_confirm_start = input.sample;
			return decision(Event::TakeoffCandidate);
		}
		break;

	case State::ConfirmingTakeoff:
		if (!takeoffEvidence(input)) {
			_state = State::Waiting;
			_confirm_start = 0;
			return decision(Event::TakeoffCancelled);
		}
		if (input.sample - _confirm_start >= _config.takeoff_confirm_us) {
			_state = State::Released;
			return decision(Event::Released);
		}
		break;

	case State::Released:
		if (landingEvidence(input)) {
			_state = State::ConfirmingLanding;
			_confirm_start = input.sample;
			return decision(Event::LandingCandidate);
		}
		break;

	case State::ConfirmingLanding:
		if (!landingEvidence(input)) {
			_state = State::Released;
			_confirm_start = 0;
			return decision(Event::LandingCancelled);
		}
		if (input.sample - _confirm_start >= _config.landing_confirm_us) {
			_state = State::LandedHold;
			return decision(Event::Landed, true);
		}
		break;

	case State::LandedHold:
		if (!input.landed && !input.maybe_landed) {
			enterWaiting(input); // an armed second takeoff can release again
			return decision(Event::TakeoffCandidate);
		}
		break;

	default:
		break;
	}

	return decision();
}
