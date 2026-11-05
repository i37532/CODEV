// SPDX-License-Identifier: BSD-3-Clause
#pragma once
#include <cmath>
#include <cstdint>

/** Default-off SITL trajectory addition, in local NED, before position P.
 * No publisher, measurement, integrator, mass/g mapping or feedback law here.
 * The caller supplies the existing guarded sample clock (12 s settling).
 * 5=hover, 6=figure8, 7=same translation with smooth heading variation.
 * 64 s: two 32 s loops, sin^4 endpoint envelope (p/v/a continuous).
 */
class VelocityResearchTask
{
public:
	struct Output { float p[2]{}, v[2]{}, a[2]{}, yaw{}, yaw_rate{}; };
	static bool valid(int mode) { return mode >= 5 && mode <= 7; }
	static Output evaluate(int mode, float t)
	{
		Output o{};
		if (!valid(mode) || mode == 5 || !std::isfinite(t) || t <= 0.f || t >= 64.f) { return o; }
		constexpr float pi = 3.14159265358979323846f;
		const float b = pi / 64.f, w = 2.f * pi / 32.f;
		const float q = sinf(b * t), c = cosf(b * t);
		const float e = q*q*q*q, ed = 4.f*b*q*q*q*c;
		const float edd = 4.f*b*b*(3.f*q*q*c*c-q*q*q*q);
		for (int i = 0; i < 2; ++i) {
			const float k = (i+1)*w, amp = i == 0 ? .5f : .25f;
			const float s = sinf(k*t), co = cosf(k*t);
			o.p[i] = amp * e * s;
			o.v[i] = amp * (ed*s+e*k*co);
			o.a[i] = amp * (edd*s+2.f*ed*k*co-e*k*k*s);
		}
		if (mode == 7) {
			const float amp = pi / 6.f;
			o.yaw = amp*e*sinf(w*t);
			o.yaw_rate = amp*(ed*sinf(w*t)+e*w*cosf(w*t));
		}
		return o;
	}
	template<typename Setpoint>
	static void apply(Setpoint &sp, const Output &o)
	{
		sp.x += o.p[0]; sp.y += o.p[1];
		sp.vx = (std::isfinite(sp.vx) ? sp.vx : 0.f) + o.v[0];
		sp.vy = (std::isfinite(sp.vy) ? sp.vy : 0.f) + o.v[1];
		for (int i = 0; i < 2; ++i) { sp.acceleration[i] = (std::isfinite(sp.acceleration[i]) ? sp.acceleration[i] : 0.f) + o.a[i]; }
		sp.yaw = atan2f(sinf(sp.yaw+o.yaw),cosf(sp.yaw+o.yaw));
		sp.yawspeed = (std::isfinite(sp.yawspeed) ? sp.yawspeed : 0.f) + o.yaw_rate;
	}
};
