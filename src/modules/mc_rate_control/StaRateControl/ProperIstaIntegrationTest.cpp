// SPDX-License-Identifier: BSD-3-Clause
#include "StaAxesApplication.hpp"
#include "../RateControl/RateControlDispatcher.hpp"

#include <gtest/gtest.h>
#include <cmath>

namespace
{
using G = StaProtection;

G::Config config()
{
	G::Config c;
	c.mode = 3;
	c.axes = 1;
	c.c_limit = .15f;
	c.gains[0] = {2.2f, .05f, 130.575283f};
	c.gains[1] = {2.4f, .08f, 112.763533f};
	c.gains[2] = {1.5f, .02f, 34.582326f};
	c.nu_limit[0] = 3.f;
	c.nu_limit[1] = 3.f;
	c.nu_limit[2] = 3.f;
	return c;
}

G::Frame frame(uint64_t sample, bool armed = true)
{
	G::Frame f;
	f.sample = sample;
	f.armed = armed;
	f.rate_enabled = true;
	f.experiment_active = true;
	f.landed = !armed;
	f.maybe_landed = !armed;
	return f;
}

G::Feedback feedback(uint16_t bits = 1) { return {1000000, 1004000, bits}; }

void start(G &guard, const G::Config &c = config())
{
	guard.begin(c, frame(1000000, false));
	guard.begin(c, frame(1004000));
}
}

TEST(ProperIstaIntegration, DedicatedModeAndThreeAxisCapability)
{
	for (int axes : {1, 3, 7}) {
		auto c = config(); c.axes = axes;
		const bool ready = StaAxesApplication::ready(true, c);
		EXPECT_TRUE(ready);
		ControllerSelection selector;
		selector.select(3, axes, false, false, false, ready);
		EXPECT_EQ(selector.status().request_status,
			  ControllerSelection::Accepted);
		EXPECT_EQ(selector.status().effective_mode, 3);
		EXPECT_EQ(selector.status().effective_axes, axes);
	}
	auto managed = config(); managed.takeoff.enabled = true;
	EXPECT_FALSE(StaAxesApplication::ready(true, managed));
}

TEST(ProperIstaIntegration, DirectionIdealCandidateAndSingleCommit)
{
	for (float sign : {-1.f, 1.f}) {
		G guard; start(guard);
		const auto before = guard.state();
		const auto out = guard.step({sign * .1f, 0.f, 0.f}, {}, feedback());
		ASSERT_TRUE(out.valid); EXPECT_TRUE(out.updated);
		EXPECT_LT(out.c_raw[0] * sign, 0.f);
		EXPECT_FLOAT_EQ(out.a[0] / config().gains[0].g, out.c_raw[0]);
		EXPECT_FLOAT_EQ(out.nu[0], out.nu_candidate[0]);
		EXPECT_NE(out.nu[0], before[0]);
		EXPECT_TRUE(std::isfinite(out.xi[0]));
		EXPECT_TRUE(std::isfinite(out.virtual_s[0]));
		EXPECT_NE(out.branch[0], 255);
		EXPECT_TRUE(std::isnan(out.c_raw[1]));
		EXPECT_FLOAT_EQ(out.nu[1], 0.f);
		EXPECT_FALSE(guard.step({}, {}, feedback()).valid);
	}
}

TEST(ProperIstaIntegration, ProtectedStateUsesTwoDeltaMapping)
{
	for (float sign : {-1.f, 1.f}) {
		G guard; start(guard);
		const uint16_t worsening = 1 << (sign > 0.f ? 4 : 3);
		const auto out = guard.step({sign * .2f, 0.f, 0.f}, {}, feedback(1 | worsening));
		ASSERT_TRUE(out.valid);
		EXPECT_NE(out.limits[0] & G::MixerFreeze, 0);
		EXPECT_FLOAT_EQ(out.nu[0], 0.f);
		EXPECT_NE(out.nu_candidate[0], 0.f);
		EXPECT_FLOAT_EQ(out.a_protected[0], out.a[0] + 2.f * (out.nu[0] - out.nu_candidate[0]));
		EXPECT_FLOAT_EQ(out.c_applied[0], out.a_protected[0] / config().gains[0].g);
	}
}

TEST(ProperIstaIntegration, PitchYawStayPidBitExact)
{
	G guard; start(guard);
	const auto out = guard.step({.1f, -.2f, .3f}, {}, feedback());
	ASSERT_TRUE(out.valid);
	const std::array<float, 3> pid{{.012345f, -.234567f, .345678f}};
	std::array<float, 3> mixed{};
	ASSERT_TRUE(StaAxesApplication::apply(1, true, out, pid, mixed));
	EXPECT_FLOAT_EQ(mixed[0], out.c_applied[0]);
	EXPECT_FLOAT_EQ(mixed[1], pid[1]);
	EXPECT_FLOAT_EQ(mixed[2], pid[2]);
}

TEST(ProperIstaIntegration, RollPitchStatesAreIndependentAndYawStaysPid)
{
	auto c = config(); c.axes = 3;
	G guard; start(guard, c);
	const auto roll = guard.step({.1f, 0.f, .3f}, {}, feedback());
	ASSERT_TRUE(roll.valid); EXPECT_NE(roll.nu[0], 0.f); EXPECT_FLOAT_EQ(roll.nu[1], 0.f);
	guard.begin(c, frame(1008000));
	const auto pitch = guard.step({0.f, -.1f, .3f}, {}, feedback());
	ASSERT_TRUE(pitch.valid); EXPECT_NE(pitch.nu[1], 0.f); EXPECT_GT(pitch.c_applied[1], 0.f);
	EXPECT_TRUE(std::isnan(pitch.c_raw[2])); EXPECT_FLOAT_EQ(pitch.nu[2], 0.f);
	const std::array<float, 3> pid{{.1f, .2f, .345678f}};
	std::array<float, 3> mixed{};
	ASSERT_TRUE(StaAxesApplication::apply(3, true, pitch, pid, mixed));
	EXPECT_FLOAT_EQ(mixed[0], pitch.c_applied[0]);
	EXPECT_FLOAT_EQ(mixed[1], pitch.c_applied[1]);
	EXPECT_FLOAT_EQ(mixed[2], pid[2]);
}

TEST(ProperIstaIntegration, ArmedChangesStageAndDisarmSwitchClearsState)
{
	G guard; auto c = config(); start(guard, c);
	ASSERT_TRUE(guard.step({.2f, 0.f, 0.f}, {}, feedback()).valid);
	const auto old = guard.state();
	auto changed = c; changed.gains[0].lambda1 = 2.4f;
	guard.begin(changed, frame(1008000));
	EXPECT_TRUE(guard.pending()); EXPECT_EQ(guard.state(), old);
	EXPECT_FLOAT_EQ(guard.config().gains[0].lambda1, c.gains[0].lambda1);
	guard.begin(c, frame(1012000)); EXPECT_FALSE(guard.pending()); EXPECT_EQ(guard.state(), old);
	guard.begin(changed, frame(1016000, false));
	EXPECT_FALSE(guard.pending()); EXPECT_FLOAT_EQ(guard.state()[0], 0.f);
	EXPECT_FLOAT_EQ(guard.config().gains[0].lambda1, changed.gains[0].lambda1);

	auto esta = changed; esta.mode = 1;
	guard.begin(esta, frame(1020000, false)); EXPECT_FLOAT_EQ(guard.state()[0], 0.f);
	guard.begin(changed, frame(1024000, false)); EXPECT_FLOAT_EQ(guard.state()[0], 0.f);
}

TEST(ProperIstaIntegration, FaultLatchesNoPidTakeoverAndDisarmedAckResets)
{
	G guard; auto c = config(); start(guard, c);
	ASSERT_TRUE(guard.step({.1f, 0.f, 0.f}, {}, feedback()).valid);
	const auto old = guard.state();
	guard.begin(c, frame(1004000));
	EXPECT_EQ(guard.fault(), G::DuplicateTime); EXPECT_TRUE(guard.abortRequested());
	EXPECT_EQ(guard.state(), old); EXPECT_FALSE(guard.acknowledge());
	std::array<float, 3> command{};
	EXPECT_FALSE(StaAxesApplication::apply(1, true, guard.step({}, {}, feedback()), {.1f, .2f, .3f}, command));
	guard.begin(c, frame(1012000, false));
	EXPECT_TRUE(guard.acknowledge()); EXPECT_FALSE(guard.abortRequested());
	EXPECT_FLOAT_EQ(guard.state()[0], 0.f);
}

TEST(ProperIstaIntegration, LandedFreezeComputesCorrectionWithoutStateAdvance)
{
	G guard; auto c = config(); start(guard, c);
	auto landed = frame(1008000); landed.landed = true; landed.maybe_landed = true;
	guard.begin(c, landed);
	const auto out = guard.step({.1f, 0.f, 0.f}, {}, feedback(), true);
	ASSERT_TRUE(out.valid); EXPECT_FALSE(out.updated);
	EXPECT_FLOAT_EQ(guard.state()[0], 0.f);
	EXPECT_FLOAT_EQ(out.nu[0], 0.f);
	EXPECT_LT(out.c_applied[0], 0.f);
}
