// SPDX-License-Identifier: BSD-3-Clause
#include "StaAxesApplication.hpp"
#include "../RateControl/ControllerSelection.hpp"
#include "../../mc_att_control/AttitudeControl/ResearchPulse.hpp"
#include <gtest/gtest.h>
#include <cstring>

namespace {
using G = StaProtection;
G::Config config()
{
	G::Config c; c.mode = 1; c.axes = 3; c.c_limit = .15f;
	c.gains[0] = {2.5f, .05f, 130.575283f}; c.gains[1] = {2.5f, .05f, 112.763533f};
	c.nu_limit = {3.f, 3.f, 0.f}; return c;
}
G::Frame frame(uint64_t sample, bool armed)
{
	G::Frame f; f.sample = sample; f.armed = armed; f.rate_enabled = true;
	f.landed = !armed; f.maybe_landed = !armed; f.experiment_active = true; return f;
}
G::Feedback fb(uint16_t bits = 1) { return {1000, 2000, bits}; }
}

TEST(StaAxesApplication, CalibratedGateRejectsPitchAndYawMisconfiguration)
{
	auto c = config(); EXPECT_TRUE(StaAxesApplication::ready(true, c));
	EXPECT_FALSE(StaAxesApplication::ready(false, c));
	for (float bad : {0.f, -1.f, 130.575283f, NAN, INFINITY}) {
		c.gains[1].g = bad; EXPECT_FALSE(StaAxesApplication::ready(true, c));
	}
	c = config(); c.gains[1].lambda1 = 0.f; EXPECT_FALSE(StaAxesApplication::ready(true, c));
	for (int axes : {0, 2, 4, 7, 259, -1}) {
		c = config(); c.axes = axes; EXPECT_FALSE(StaAxesApplication::ready(true, c));
	}
	c = config(); c.axes = 1; c.gains[1] = {}; EXPECT_TRUE(StaAxesApplication::ready(true, c));
}

TEST(StaAxesApplication, ProperIstaGateIsRollOnlyAndUsesEstablishedLifecycle)
{
	auto c = config(); c.mode = 3; c.axes = 1; c.gains[1] = {}; c.nu_limit[1] = 0.f;
	EXPECT_TRUE(StaAxesApplication::ready(true, c));
	for (int axes : {3, 7}) {
		c.axes = axes;
		EXPECT_FALSE(StaAxesApplication::ready(true, c));
	}
	c.axes = 1; c.takeoff.enabled = true;
	EXPECT_FALSE(StaAxesApplication::ready(true, c));
	c.takeoff.enabled = false; c.gains[0].g = 112.763533f;
	EXPECT_FALSE(StaAxesApplication::ready(true, c));
}

TEST(StaAxesApplication, ArmedMasksPreserveEffectiveAxesAndDisarmApplies)
{
	ControllerSelection s;
	s.select(1, 1, false, true);
	s.select(1, 3, true, true); EXPECT_EQ(s.status().effective_axes, 1); EXPECT_TRUE(s.status().pending);
	s.select(1, 1, true, true); EXPECT_FALSE(s.status().pending);
	s.select(1, 3, false, true); EXPECT_EQ(s.status().effective_axes, 3);
	s.select(1, 1, true, true); EXPECT_EQ(s.status().effective_axes, 3);
	s.select(1, 7, false, true); EXPECT_EQ(s.status().effective_axes, 7);
	EXPECT_EQ(s.status().request_status, ControllerSelection::Accepted);
	s.select(0, 0, false); EXPECT_EQ(s.status().effective_axes, 0);
}

TEST(StaAxesApplication, PitchSignsAtomicApplicationAndYawBitIdentity)
{
	for (float sign : {-1.f, 1.f}) {
		G g; auto c = config(); g.begin(c, frame(1000000, false)); g.begin(c, frame(1004000, true));
		const auto out = g.step({-.1f * sign, .1f * sign, 5.f}, {}, fb(), true);
		ASSERT_TRUE(out.valid); EXPECT_LT(out.c_raw[1] * sign, 0.f); EXPECT_GT(out.c_raw[0] * sign, 0.f);
		std::array<float, 3> pid{.02f, -.03f, -.0f}, mixed{};
		ASSERT_TRUE(StaAxesApplication::apply(3, true, out, pid, mixed));
		EXPECT_EQ(std::memcmp(&pid[2], &mixed[2], sizeof(float)), 0);
		EXPECT_FLOAT_EQ(g.state()[2], 0.f);
		auto bad = out; bad.c_applied[1] = NAN;
		EXPECT_FALSE(StaAxesApplication::apply(3, true, bad, pid, mixed));
		EXPECT_EQ(std::memcmp(pid.data(), mixed.data(), sizeof(pid)), 0);
		EXPECT_TRUE(StaAxesApplication::apply(3, false, {}, pid, mixed));
		EXPECT_EQ(mixed[0], 0.f); EXPECT_EQ(mixed[1], 0.f);
	}
}

TEST(StaAxesApplication, IndependentStatesSaturationAndAtomicFailure)
{
	auto c = config(); c.gains[1].lambda1 = 3.f; c.gains[1].lambda2 = .13f;
	G together, roll, pitch; auto r = c; r.axes = 1; auto p = c; p.axes = 2;
	together.begin(c, frame(1000000, false)); roll.begin(r, frame(1000000, false)); pitch.begin(p, frame(1000000, false));
	for (int k = 1; k <= 512; ++k) {
		const auto f = frame(1000000 + k * 4000, true);
		together.begin(c, f); roll.begin(r, f); pitch.begin(p, f);
		std::array<float, 3> rate{.07f * sinf(k * .11f), .03f * cosf(k * .07f), 4.f};
		const auto feedback = fb(k % 3 == 0 ? 1 | (1 << 6) : 1); // pitch negative saturation only
		const auto both = together.step(rate, {}, feedback);
		const auto ro = roll.step(rate, {}, feedback); const auto pi = pitch.step(rate, {}, feedback);
		ASSERT_TRUE(both.valid && ro.valid && pi.valid);
		EXPECT_FLOAT_EQ(both.nu[0], ro.nu[0]); EXPECT_FLOAT_EQ(both.nu[1], pi.nu[1]);
		EXPECT_FLOAT_EQ(both.c_raw[0], ro.c_raw[0]); EXPECT_FLOAT_EQ(both.c_raw[1], pi.c_raw[1]);
		EXPECT_EQ(both.limits[0], ro.limits[0]); EXPECT_EQ(both.limits[1], pi.limits[1]);
		EXPECT_FLOAT_EQ(both.nu[2], 0.f);
	}
	const auto old = together.state(); together.begin(c, frame(3052000, true));
	EXPECT_FALSE(together.step({.1f, NAN, 0.f}, {}, fb()).valid);
	EXPECT_EQ(together.fault(), G::Numerical); EXPECT_EQ(together.state(), old);
}

TEST(StaAxesApplication, PitchGainStagingAndResetBothAxes)
{
	auto c = config(); G g; g.begin(c, frame(1000000, false)); g.begin(c, frame(1004000, true));
	ASSERT_TRUE(g.step({.1f, -.1f, 0.f}, {}, fb()).valid);
	const auto old = g.state(); auto changed = c; changed.gains[1].lambda2 = .12f;
	g.begin(changed, frame(1008000, true)); EXPECT_TRUE(g.pending()); EXPECT_EQ(g.state(), old);
	EXPECT_FLOAT_EQ(g.config().gains[1].lambda2, .05f);
	g.begin(changed, frame(1012000, false)); EXPECT_FALSE(g.pending());
	EXPECT_FLOAT_EQ(g.config().gains[1].lambda2, .12f);
	for (float nu : g.state()) { EXPECT_EQ(nu, 0.f); }
}

TEST(StaAxesApplication, CombinedPulsePhasesHaveBothSignsAndZeroIntegral)
{
	for (unsigned axis = 0; axis < 3; ++axis) {
		for (int phase = 0; phase < 3; ++phase) {
			double integral = 0.; float lo = 0.f, hi = 0.f;
			for (int k = 0; k < 3000; ++k) {
				const float v = ResearchPulse::combined(12.f * phase + .004f * k, axis);
				integral += .004 * static_cast<double>(v); lo = std::min(lo, v); hi = std::max(hi, v);
			}
			EXPECT_NEAR(integral, 0., 1e-6);
			if (axis < 2 && (phase == 2 || phase == static_cast<int>(axis))) {
				EXPECT_LT(lo, -.119f); EXPECT_GT(hi, .119f);
			} else { EXPECT_EQ(lo, 0.f); EXPECT_EQ(hi, 0.f); }
		}
	}
}

TEST(StaAxesApplication, ThreeAxesCalibratedGateAndNoPidFallbackOnFault)
{
	auto c = config(); c.axes = 7; c.gains[2] = {.65f, .02f, 34.582326f}; c.nu_limit[2] = 3.f;
	ASSERT_TRUE(StaAxesApplication::ready(true, c));
	auto bad = c; bad.gains[2].g = c.gains[0].g; EXPECT_FALSE(StaAxesApplication::ready(true, bad));
	G together, isolated[3]; together.begin(c, frame(1000000, false));
	for (int i = 0; i < 3; ++i) { auto one = c; one.axes = 1 << i; isolated[i].begin(one, frame(1000000, false)); }
	for (int k = 1; k <= 512; ++k) {
		const auto f = frame(1000000 + k * 4000, true);
		const std::array<float, 3> rate{.07f * sinf(k*.11f), .03f * cosf(k*.07f), .04f * sinf(k*.09f)};
		// Alternate both yaw saturation directions, without freezing R/P.
		const auto feedback = fb(1 | (1 << (k % 2 ? 7 : 8)));
		together.begin(c, f); auto out = together.step(rate, {}, feedback); ASSERT_TRUE(out.valid);
		std::array<float, 3> command{};
		ASSERT_TRUE(StaAxesApplication::apply(7, true, out, {NAN, NAN, NAN}, command));
		for (int i = 0; i < 3; ++i) {
			auto one = c; one.axes = 1 << i; isolated[i].begin(one, f);
			auto single = isolated[i].step(rate, {}, feedback);
			EXPECT_FLOAT_EQ(out.nu[i], single.nu[i]); EXPECT_FLOAT_EQ(command[i], single.c_applied[i]);
			EXPECT_EQ(out.limits[i], single.limits[i]);
		}
	}
	together.begin(c, frame(3052000, true));
	auto fault = together.step({0.f, 0.f, NAN}, {}, fb());
	EXPECT_FALSE(fault.valid); EXPECT_TRUE(together.abortRequested());
	std::array<float, 3> command{};
	EXPECT_FALSE(StaAxesApplication::apply(7, true, fault, {NAN, NAN, NAN}, command));
	for (float v : command) { EXPECT_TRUE(std::isnan(v)); }
	together.begin(c, frame(3056000, false));
	for (float nu : together.state()) { EXPECT_EQ(nu, 0.f); }
}

TEST(StaAxesApplication, YawSaturationFreezesOnlyWorseningDirection)
{
	for (bool positive : {false, true}) {
		G g; auto c = config(); c.axes = 7; c.gains[2] = {1.5f, .02f, 34.582326f}; c.nu_limit[2] = 3.f;
		g.begin(c, frame(1000000, false)); g.begin(c, frame(1004000, true));
		const std::array<float, 3> rate{.1f, -.1f, positive ? -.1f : .1f};
		const auto blocked = g.step(rate, {}, fb(1 | (1 << (positive ? 7 : 8))));
		ASSERT_TRUE(blocked.valid); EXPECT_FLOAT_EQ(blocked.nu[2], 0.f);
		EXPECT_EQ(blocked.limits[2], G::MixerFreeze);
		EXPECT_LT(blocked.nu[0], 0.f); EXPECT_GT(blocked.nu[1], 0.f);
		g.begin(c, frame(1008000, true));
		const auto unwind = g.step(rate, {}, fb(1 | (1 << (positive ? 8 : 7))));
		ASSERT_TRUE(unwind.valid); EXPECT_EQ(unwind.limits[2], 0);
		EXPECT_NEAR(unwind.nu[2], positive ? .00008f : -.00008f, 1e-10f);
	}
}

TEST(StaAxesApplication, WorldYawTransformationAndThreeAxisScene)
{
	for (float heading : {-2.f, 0.f, 1.5f}) {
		matrix::Quatf q(matrix::Eulerf(.15f, -.1f, heading));
		const auto body = ResearchPulse::yawBody(q, .12f);
		const matrix::Vector3f world = matrix::Dcmf(q) * body;
		EXPECT_NEAR(world(0), 0.f, 1e-7); EXPECT_NEAR(world(1), 0.f, 1e-7); EXPECT_NEAR(world(2), .12f, 1e-7);
		EXPECT_GT(fabsf(body(0)), .005f); EXPECT_GT(fabsf(body(1)), .005f);
	}
	for (bool yaw_only : {false, true}) {
		for (unsigned axis = 0; axis < 3; ++axis) {
			for (int phase = 0; phase < 3; ++phase) {
				double integral = 0.; float peak = 0.f;
				for (int k = 0; k < 3000; ++k) {
					const float v = ResearchPulse::threeAxis(12.f * phase + .004f * k, axis, yaw_only);
					integral += .004 * static_cast<double>(v); peak = std::max(peak, fabsf(v));
				}
				EXPECT_NEAR(integral, 0., 1e-6);
				if (axis == 2 || (!yaw_only && phase > 0)) { EXPECT_GT(peak, .119f); }
				else { EXPECT_EQ(peak, 0.f); }
			}
		}
	}
}

TEST(StaAxesApplication, YawParameterStagedWhileArmedAndReloadResetsAllStates)
{
	G g; auto c = config(); c.axes = 7; c.gains[2] = {.65f, .02f, 34.582326f}; c.nu_limit[2] = 3.f;
	g.begin(c, frame(1000000, false)); g.begin(c, frame(1004000, true));
	ASSERT_TRUE(g.step({.1f, -.1f, .07f}, {}, fb()).valid);
	const auto old = g.state();
	auto changed = c; changed.gains[2].lambda1 = .8f; changed.gains[2].lambda2 = .03f;
	g.begin(changed, frame(1008000, true)); EXPECT_TRUE(g.pending()); EXPECT_EQ(g.state(), old);
	EXPECT_FLOAT_EQ(g.config().gains[2].lambda1, .65f);
	g.begin(c, frame(1012000, true)); EXPECT_FALSE(g.pending()); EXPECT_EQ(g.state(), old);
	g.begin(changed, frame(1016000, false)); EXPECT_FALSE(g.pending());
	EXPECT_FLOAT_EQ(g.config().gains[2].lambda1, .8f);
	for (float value : g.state()) { EXPECT_EQ(value, 0.f); }
	G fresh; fresh.begin(changed, frame(1016000, false));
	g.begin(changed, frame(1020000, true)); fresh.begin(changed, frame(1020000, true));
	const auto a = g.step({.1f, -.1f, .07f}, {}, fb()), b = fresh.step({.1f, -.1f, .07f}, {}, fb());
	EXPECT_EQ(a.nu, b.nu); EXPECT_EQ(a.c_raw, b.c_raw);
}

TEST(StaAxesApplication, ThreeAxisLaggedCoupledObjectWithUncertainGain)
{
	for (double mismatch : {.8, 1., 1.2}) {
		G g; auto c = config(); c.axes = 7; c.gains[2] = {1.5f, .02f, 34.582326f}; c.nu_limit[2] = 3.f;
		c.gains[0].lambda1 = 2.2f; c.gains[1].lambda1 = 2.4f; c.gains[1].lambda2 = .08f;
		g.begin(c, frame(1000000, false));
		double angle[3]{}, rate[3]{}, acceleration[3]{};
		for (int k = 1; k <= 15000; ++k) {
			std::array<float, 3> measured{}, sp{};
			for (int i = 0; i < 3; ++i) {
				measured[i] = static_cast<float>(rate[i]);
				sp[i] = static_cast<float>(-(i == 2 ? 2.8 : 6.5) * angle[i]) + ResearchPulse::threeAxis(.004f*k - 15.f, i, false);
			}
			g.begin(c, frame(1000000 + k*4000, true)); const auto out = g.step(measured, sp, fb());
			ASSERT_TRUE(out.valid);
			const double command[3]{out.c_applied[0], out.c_applied[1], out.c_applied[2]};
			const double target[3]{130.575283*command[0] + 19.039183*command[2],
					       112.763533*command[1] - .484, -.067051*command[0] + 34.582326*command[2]};
			for (int i = 0; i < 3; ++i) {
				acceleration[i] += (mismatch*target[i] - acceleration[i]) * (1. - exp(-.004/.025));
				rate[i] += .004*acceleration[i]; angle[i] += .004*rate[i];
				ASSERT_TRUE(std::isfinite(rate[i])); ASSERT_LT(fabs(rate[i]), 1.); ASSERT_LT(fabs(angle[i]), .261799);
			}
		}
		for (double value : angle) { EXPECT_LT(fabs(value), .01); }
	}
}

TEST(StaAxesApplication, CombinedIndependentLaggedObjectWithGainUncertainty)
{
	for (double mismatch : {.8, 1., 1.2}) {
		G g; auto c = config(); g.begin(c, frame(1000000, false));
		double angle[2]{}, rate[2]{}, accel[2]{};
		for (int k = 1; k <= 15000; ++k) {
			std::array<float, 3> measured{}, sp{};
			for (int i = 0; i < 2; ++i) {
				measured[i] = static_cast<float>(rate[i]);
				sp[i] = static_cast<float>(-6.5 * angle[i]) + ResearchPulse::combined(.004f * k - 15.f, i);
			}
			g.begin(c, frame(1000000 + k * 4000, true)); const auto out = g.step(measured, sp, fb());
			ASSERT_TRUE(out.valid);
			for (int i = 0; i < 2; ++i) {
				accel[i] += (static_cast<double>(c.gains[i].g) * mismatch * static_cast<double>(out.c_applied[i]) - accel[i]) * (1. - exp(-.004 / .025));
				rate[i] += .004 * accel[i]; angle[i] += .004 * rate[i];
				ASSERT_TRUE(std::isfinite(rate[i])); ASSERT_LT(fabs(rate[i]), 1.); ASSERT_LT(fabs(angle[i]), .261799);
			}
		}
		for (double v : angle) { EXPECT_LT(fabs(v), .01); }
	}
}
