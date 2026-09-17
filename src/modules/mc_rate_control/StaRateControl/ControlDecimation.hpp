// SPDX-License-Identifier: BSD-3-Clause
#pragma once
#include "StaProtection.hpp"

/** Safety stays callback-clocked. Cache is ALWAYS unscaled. Saturation directions
 * are ORed across the interval; any invalid/stale observation invalidates it.
 * N=1 retains legacy PID mixer-validity handling exactly.
 */
class ControlDecimation
{
public:
	bool configure(int32_t requested, bool armed)
	{
		_requested = requested; _valid = requested == 1 || requested == 2 || requested == 4;
		_pending = armed && requested != _div;
		if (!armed && _valid && requested != _div) { _div = requested; _cached = false; return true; }
		return false;
	}
	void reset() { _cached = false; _last_update = 0; _count = 0; clearFeedback(); }
	void lifecycle(const StaProtection::Frame &frame, bool reset_state, bool fault)
	{
		if (!frame.rate_enabled || fault) {
			reset(); // no active integration epoch across disabled/faulted control
		} else if (reset_state || frame.armed != _previous.armed || frame.landed != _previous.landed
			   || frame.maybe_landed != _previous.maybe_landed) {
			// Invalidate torque, NOT the real update timestamp or interval feedback.
			_cached = false;
		}
		_previous = frame;
	}
	void observe(const StaProtection::Feedback &feedback)
	{
		_bits |= feedback.bits; _feedback_valid = _feedback_valid && feedback.valid(); ++_observations;
	}
	bool due(uint64_t sample, float initial_dt)
	{
		++_count;
		if (!_cached || _div == 1 || _count >= _div) {
			// Only the first update of a newly enabled epoch bootstraps callback dt.
			_dt = _last_update ? static_cast<float>((sample - _last_update) * 1e-6f) : initial_dt;
			return true;
		}
		return false;
	}
	void commit(uint64_t sample, const std::array<float, 3> &command)
	{
		_command = command; _cached = true; _last_update = sample; _count = 0; clearFeedback();
	}
	std::array<float, 4> output(float thrust, float scale) const
	{
		return {{_command[0] * scale, _command[1] * scale, _command[2] * scale, thrust * scale}};
	}
	const std::array<float, 3> &command() const { return _command; }
	uint16_t bits() const { return _feedback_valid ? _bits : (_bits & ~1u); }
	bool feedbackValid() const { return _feedback_valid && _observations > 0; }
	uint32_t observations() const { return _observations; }
	float dt() const { return _dt; }
	int32_t requested() const { return _requested; }
	uint8_t divisor() const { return _div; }
	bool valid() const { return _valid; }
	bool pending() const { return _pending; }
	bool cached() const { return _cached; }
private:
	void clearFeedback() { _bits = 0; _feedback_valid = true; _observations = 0; }
	std::array<float, 3> _command{};
	StaProtection::Frame _previous{};
	uint64_t _last_update{0};
	uint32_t _observations{0};
	int32_t _requested{1};
	uint16_t _bits{0};
	uint8_t _div{1}, _count{0};
	float _dt{0.f};
	bool _valid{true}, _pending{false}, _cached{false}, _feedback_valid{true};
};
