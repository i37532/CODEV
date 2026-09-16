// SPDX-License-Identifier: BSD-3-Clause
#pragma once
#include <cmath>
#include <cstdint>
#include <matrix/matrix/math.hpp>

/** Frozen M04 zero-integral sine pulses, one existing rates-setpoint publisher. */
class ResearchPulse
{
public:
	float update(bool request, bool permitted, uint64_t now)
	{
		if (!request || !permitted) { _start = 0; _elapsed = -1.f; _previous = request; return 0.f; }

		if (!_previous) { _start = now; }

		_previous = request;

		if (!_start || now < _start) { _elapsed = -1.f; return 0.f; }

		_elapsed = static_cast<float>(now - _start) * 1e-6f;
		return value(_elapsed);
	}
	float elapsed() const { return _elapsed; }
	// M06: first Y only [0,12), then synchronous R/P/Y [12,36).
	// World-z yaw feedforward uses the original attitude controller's mapping.
	static matrix::Vector3f yawBody(const matrix::Quatf &q, float yaw_rate)
	{
		return q.inversed().dcm_z() * yaw_rate;
	}
	static float threeAxis(float t, unsigned axis, bool yaw_only)
	{
		if (!std::isfinite(t) || t < 0.f || t >= 36.f || axis > 2) { return 0.f; }
		if (axis < 2 && (yaw_only || t < 12.f)) { return 0.f; }
		const float local = t - 12.f * static_cast<int>(t / 12.f);
		const int cycle = static_cast<int>(local / 4.f);
		return .04f * (cycle + 1) * sinf(1.5707963267948966f * (local - 4.f * cycle));
	}
	// M05: R only [0,12), P only [12,24), synchronous R/P [24,36).
	// Each 4 s cycle has zero integral; amplitudes grow .04, .08, .12.
	static float combined(float t, unsigned axis)
	{
		if (!std::isfinite(t) || t < 0.f || t >= 36.f || axis > 1) { return 0.f; }
		const int phase = static_cast<int>(t / 12.f);
		if (phase < 2 && axis != static_cast<unsigned>(phase)) { return 0.f; }
		const float local = t - 12.f * phase;
		const int cycle = static_cast<int>(local / 4.f);
		return .04f * (cycle + 1) * sinf(1.5707963267948966f * (local - 4.f * cycle));
	}
	static float value(float t)
	{
		if (t < 0.f || t >= 20.f) { return 0.f; }

		const int part = static_cast<int>(t / 8.f);
		const float local = t - part * 8.f;
		return local < 4.f ? .04f * (part + 1) * sinf(1.5707963267948966f * local) : 0.f;
	}
private:
	uint64_t _start{0};
	bool _previous{false};
	float _elapsed{-1.f};
};
