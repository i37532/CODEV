/****************************************************************************
 * AX02 opt-in Iris SITL trajectory adapter. No controller law is changed.
 * H delegates to the qualified mode 6; V adds an analytic NED-Z displacement.
 ****************************************************************************/
#pragma once
#include "VelocityResearchTask.hpp"

class VelocityAxisAblationTask
{
public:
	struct Vertical { float p{0.f}; float v{0.f}; float a{0.f}; };
	static Vertical vertical(float t)
	{
		Vertical o;
		if (!std::isfinite(t) || t <= 0.f || t >= 64.f) { return o; }
		constexpr float pi = 3.14159265358979323846f;
		constexpr float b = pi / 64.f;
		constexpr float w = 2.f * pi / 32.f;
		const float q = sinf(b * t), c = cosf(b * t);
		const float e = q * q * q * q;
		const float ed = 4.f * b * q * q * q * c;
		const float edd = 4.f * b * b * (3.f * q * q * c * c - q * q * q * q);
		const float s = sinf(w * t), co = cosf(w * t);
		o.p = .1f * e * s;
		o.v = .1f * (ed * s + e * w * co);
		o.a = .1f * (edd * s + 2.f * ed * w * co - e * w * w * s);
		return o;
	}

	// Called ONLY for MPC_VCT_TEST=8 in the existing guarded, SITL-only path.
	// Input is a fresh per-frame copy of the single upstream trajectory target.
	template<typename Setpoint>
	static void apply(Setpoint &sp, float t)
	{
		VelocityResearchTask::apply(sp, VelocityResearchTask::evaluate(6, t));
		const Vertical z = vertical(t);
		sp.z += z.p;
		sp.vz = (std::isfinite(sp.vz) ? sp.vz : 0.f) + z.v;
		sp.acceleration[2] = (std::isfinite(sp.acceleration[2]) ? sp.acceleration[2] : 0.f) + z.a;
	}
};
