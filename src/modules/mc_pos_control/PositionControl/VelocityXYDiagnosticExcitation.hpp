// SPDX-License-Identifier: BSD-3-Clause
#pragma once
#include "VelocityDiagnosticExcitation.hpp"

/** V05 default-off SITL stimulus, driven by the existing guarded sample clock.
 * X: 0..32 s (unchanged V04 regression); Y: 32..48 s; XY: 48..64 s.
 * Each window has zero integral and smooth zero endpoints. The combined
 * horizontal norm never exceeds the previous 0.2 m/s command bound.
 */
class VelocityXYDiagnosticExcitation
{
public:
	static void waveform(float t, float &x, float &y)
	{
		x = y = 0.f;
		if (!std::isfinite(t) || t <= 0.f || t >= 64.f) { return; }
		if (t < 32.f) { x = VelocityDiagnosticExcitation::waveform(t); return; }
		const float u = t < 48.f ? t - 32.f : t - 48.f;
		const float envelope = sinf(3.14159265358979323846f * u / 16.f);
		const float wave = .2f * sinf(2.f * 3.14159265358979323846f * u / 8.f) * envelope * envelope;
		if (t < 48.f) { y = wave; }
		else { x = wave * .7071067811865475f; y = -x; }
	}
};
