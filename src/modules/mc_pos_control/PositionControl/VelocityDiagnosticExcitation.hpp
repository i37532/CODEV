// SPDX-License-Identifier: BSD-3-Clause
#pragma once
#include <cmath>
#include <cstdint>

/** SITL protocol waveform: single shot, 12 s airborne settle, 32 s window.
 * Smooth 0.2 sin(2pi t/8) sin²(pi t/32), zero integral over the whole window.
 * Starts only with explicit enable. Inhibit after a safety/clock/gate break;
 * never restarts in the same arming. No publisher or yaw/Z command is added.
 */
class VelocityDiagnosticExcitation
{
public:
	enum Fault : uint8_t { Clock = 1, Gate = 2, Controller = 4 };
	// Same-frame failure notification: does not advance the sample clock.
	void abort() { _fault |= Controller; }
	uint8_t fault() const { return _fault; }
	float update(uint64_t sample, bool armed, bool gate)
	{
		if (!armed) { _start = _last = 0; _fault = 0; _time = -1.f; return 0.f; }
		if (_last && (sample <= _last || sample - _last > 40000)) { _fault |= Clock; }
		_last = sample;
		if (!gate) { if (_start) { _fault |= Gate; } return 0.f; }
		if (_fault) { return 0.f; }
		if (!_start) { _start = sample; }
		_time = static_cast<float>((sample - _start) * 1e-6) - 12.f;
		return waveform(_time);
	}
	float time() const { return _time; }
	static float waveform(float t)
	{
		if (!std::isfinite(t) || t <= 0.f || t >= 32.f) { return 0.f; }
		const float envelope = sinf(3.14159265358979323846f * t / 32.f);
		return .2f * sinf(2.f * 3.14159265358979323846f * t / 8.f) * envelope * envelope;
	}
private:
	uint64_t _start{0}, _last{0};
	float _time{-1.f};
	uint8_t _fault{0};
};
