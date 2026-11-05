// SPDX-License-Identifier: BSD-3-Clause
#pragma once
#include <cmath>

/** Default-off E01-XYZ SITL task on the existing guarded sample clock.
 * Z 0..16s, XY 16..32s, XYZ 32..64s. Smooth, zero-area windows.
 * Horizontal norm <= .2m/s; Down amplitude <= .1m/s. No new publisher.
 */
class VelocityXYZDiagnosticExcitation
{
public:
	static void waveform(float t, float &x, float &y, float &z)
	{
		x = y = z = 0.f;
		if (!std::isfinite(t) || t <= 0.f || t >= 64.f) { return; }
		const float u = t < 16.f ? t : (t < 32.f ? t - 16.f : t - 32.f);
		const float duration = t < 32.f ? 16.f : 32.f;
		const float envelope = sinf(3.14159265358979323846f * u / duration);
		const float wave = sinf(2.f * 3.14159265358979323846f * u / 8.f) * envelope * envelope;
		if (t >= 16.f) { x = .1414213562373095f * wave; y = -x; }
		if (t < 16.f || t >= 32.f) { z = .1f * wave; }
	}
};
