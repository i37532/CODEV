// SPDX-License-Identifier: BSD-3-Clause
#pragma once

#include <StaVelocityControl.hpp>
#include <algorithm>
#include <cmath>
#include <limits>

// Z01 OFFLINE ONLY. Not a flight safety adapter: no XY/tilt allocation,
// estimator reset compensation or takeoff-state estimator is implemented here.
// An invalid output is NOT a zero-thrust command or a safe PID handover.
class StaVelocityZPrototype
{
public:
	static constexpr float gravity() { return 9.80665f; }
	struct Config {
		StaVelocityControl::Parameters gains{1.f, .2f};
		float nu_limit{2.f}, acceleration_limit{3.f};
		float hover{.5f}, thrust_min{.12f}, thrust_max{1.f};
	};
	struct Frame {
		uint64_t sample{0};
		float velocity{0.f}, target{0.f}, ff{0.f};
		bool armed{false}, flying{false}, landed{true}, contact{true};
	};
	struct Output {
		bool valid{false}, limited{false};
		uint64_t sample{0};
		float a_ideal{NAN}, a_applied_request{NAN};
		float thrust_raw{NAN}, thrust_applied{NAN}, acceleration_proxy{NAN};
		float nu_ideal{NAN}, nu_applied{NAN};
	};
	bool configure(const Config &c)
	{
		if (_active || _open || !StaVelocityControl::validParameters(c.gains)
		    || !positive(c.nu_limit) || !positive(c.acceleration_limit)
		    || !std::isfinite(c.hover) || c.hover < .1f || c.hover > .9f
		    || !positive(c.thrust_min) || !std::isfinite(c.thrust_max)
		    || c.thrust_max > 1.f || c.thrust_min >= c.thrust_max
		    || c.hover <= c.thrust_min || c.hover >= c.thrust_max) { return false; }
		_config = c;
		_configured = _kernel.setParameters(2, c.gains);
		return _configured;
	}
	// Offline handover: match the previous PID acceleration request at this
	// error and FF. The real module must qualify flight state before calling.
	bool enter(const Frame &f, float pid_acceleration)
	{
		if (!_configured || _active || _fault || !f.sample || !eligible(f) || !finite(f)
		    || !std::isfinite(pid_acceleration)) { return false; }
		const double s = double(f.velocity) - double(f.target);
		const double seed = double(pid_acceleration) - double(f.ff)
			+ double(_config.gains.lambda1) * std::copysign(std::sqrt(std::abs(s)), s);
		const double correction = double(pid_acceleration) - double(f.ff);
		const double thrust = (double(pid_acceleration) / double(gravity()) - 1.) * double(_config.hover);
		if (!std::isfinite(seed) || std::abs(seed) > double(_config.nu_limit)
		    || std::abs(correction) > double(_config.acceleration_limit)
		    || thrust < -double(_config.thrust_max) || thrust > -double(_config.thrust_min)) { return false; }
		_kernel.reset(2, float(seed));
		_last_sample = f.sample;
		_active = true;
		return true;
	}
	Output evaluate(const Frame &f)
	{
		if (!eligible(f)) { deactivate(); return {}; }
		if (!_active || _fault) { return {}; }
		if (_open || !finite(f) || f.sample <= _last_sample) { return fail(); }
		const uint64_t elapsed = f.sample - _last_sample;
		if (elapsed < 2000 || elapsed > 40000) { return fail(); }
		_candidate = _kernel.evaluate(2, f.velocity, f.target, float(elapsed) * 1e-6f);
		if (!_candidate.valid()) { return fail(); }
		Output o{}; o.sample = f.sample;
		o.a_ideal = _candidate.a_sta + f.ff;
		o.a_applied_request = clamp(_candidate.a_sta, _config.acceleration_limit) + f.ff;
		o.thrust_raw = (o.a_applied_request / gravity() - 1.f) * _config.hover;
		o.thrust_applied = std::max(-_config.thrust_max, std::min(-_config.thrust_min, o.thrust_raw));
		o.acceleration_proxy = gravity() * (o.thrust_applied / _config.hover + 1.f);
		o.nu_ideal = _candidate.nu_next;
		o.nu_applied = clamp(o.nu_ideal, _config.nu_limit);
		if (!std::isfinite(o.a_ideal) || !std::isfinite(o.a_applied_request)
		    || !std::isfinite(o.thrust_raw) || !std::isfinite(o.acceleration_proxy)) { return fail(); }
		const float increment = o.nu_applied - _candidate.nu_before;
		// Acceleration-domain direction, NOT body mixer bits or PID 2/Kp ARW.
		const bool correction_deepens = (_candidate.a_sta > _config.acceleration_limit && increment > 0.f)
			|| (_candidate.a_sta < -_config.acceleration_limit && increment < 0.f);
		const bool thrust_deepens = (o.thrust_raw > -_config.thrust_min && increment > 0.f)
			|| (o.thrust_raw < -_config.thrust_max && increment < 0.f);
		if (correction_deepens || thrust_deepens) { o.nu_applied = _candidate.nu_before; }
		o.limited = std::abs(_candidate.a_sta) > _config.acceleration_limit
			|| o.thrust_raw < -_config.thrust_max || o.thrust_raw > -_config.thrust_min
			|| std::abs(o.nu_applied - o.nu_ideal) > 0.f;
		o.valid = true; _pending = o; _open = true;
		return o;
	}
	bool commit(uint64_t sample)
	{
		if (!_open || sample != _pending.sample || _fault) { return false; }
		if (_kernel.commitProtected(_candidate, _pending.nu_applied) != StaVelocityControl::Status::Ok) {
			fail(); return false;
		}
		_last_sample = sample; _open = false;
		return true;
	}
	// Fixed error and FF, unconstrained vertical map only. Reject rather than
	// clipping nu and falsely claiming continuity. No open candidate allowed.
	bool rebaseHover(float hover, float velocity, float target, float ff)
	{
		if (!_active || _fault || _open || !std::isfinite(hover) || hover < .1f || hover > .9f
		    || hover <= _config.thrust_min || hover >= _config.thrust_max
		    || !std::isfinite(velocity) || !std::isfinite(target) || !std::isfinite(ff)) { return false; }
		const auto c = _kernel.evaluate(2, velocity, target, .008f);
		if (!c.valid()) { return false; }
		const double a = double(c.a_sta) + double(ff);
		const double old_thrust = (a / double(gravity()) - 1.) * double(_config.hover);
		const double shift = (double(_config.hover) / double(hover) - 1.) * (a - double(gravity()));
		const double nu = double(c.nu_before) + shift;
		if (std::abs(c.a_sta) > _config.acceleration_limit || old_thrust < -double(_config.thrust_max)
		    || old_thrust > -double(_config.thrust_min) || !std::isfinite(nu) || std::abs(nu) > double(_config.nu_limit)
		    || std::abs(double(c.a_sta) + shift) > double(_config.acceleration_limit)) { return false; }
		_kernel.reset(2, float(nu)); _config.hover = hover;
		return true;
	}
	void reset() { deactivate(); _fault = false; }
	bool fault() const { return _fault; }
	bool active() const { return _active; }
	float hover() const { return _config.hover; }
	const std::array<float, 3> &state() const { return _kernel.state(); }

private:
	static bool positive(float v) { return std::isnormal(v) && v > 0.f; }
	static float clamp(float v, float limit) { return std::max(-limit, std::min(limit, v)); }
	static bool finite(const Frame &f) { return std::isfinite(f.velocity) && std::isfinite(f.target) && std::isfinite(f.ff); }
	static bool eligible(const Frame &f) { return f.armed && f.flying && !f.landed && !f.contact; }
	void deactivate() { _kernel.reset(); _active = _open = false; _last_sample = 0; }
	Output fail() { _fault = true; _open = false; return {}; }
	Config _config{};
	StaVelocityControl _kernel{};
	StaVelocityControl::Candidate _candidate{};
	Output _pending{};
	uint64_t _last_sample{0};
	bool _configured{false}, _active{false}, _open{false}, _fault{false};
};
