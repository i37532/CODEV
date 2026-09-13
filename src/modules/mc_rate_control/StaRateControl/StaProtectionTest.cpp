// SPDX-License-Identifier: BSD-3-Clause
#include "StaProtection.hpp"
#include <gtest/gtest.h>
#include <cmath>

using Guard = StaProtection;
namespace
{
Guard::Config config()
{
	Guard::Config c;
	c.mode = 1; c.axes = 7;

	for (size_t i = 0; i < 3; ++i) { c.gains[i] = {1.f, 2.f, 10.f}; c.nu_limit[i] = 2.f; }

	return c;
}
Guard::Frame airborne(uint64_t sample)
{
	Guard::Frame f;
	f.sample = sample; f.armed = true; f.rate_enabled = true;
	f.landed = false; f.maybe_landed = false; f.experiment_active = true;
	return f;
}
Guard::Feedback feedback(uint16_t bits = 1) { return {1000000, 1004000, bits}; }
void initialize(Guard &g, const Guard::Config &c = config())
{
	Guard::Frame f; f.sample = 1000000;
	g.begin(c, f);
	g.begin(c, airborne(1004000));
}
}

TEST(StaProtectionTest, StartupLandFreezeAndOneUpdatePerFrame)
{
	Guard g; auto c = config();
	Guard::Frame f; f.sample = 1000000;
	g.begin(c, f);
	EXPECT_NE(g.resetReason() & Guard::Startup, 0);
	EXPECT_NE(g.resetReason() & Guard::Landed, 0);
	EXPECT_FALSE(g.canUpdate());
	f.sample += 4000; g.begin(c, f);
	EXPECT_EQ(g.resetReason(), 0);
	EXPECT_FALSE(g.step({1.f, 0.f, 0.f}, {}, feedback()).valid);
	g.begin(c, airborne(1008000));
	ASSERT_TRUE(g.step({1.f, 0.f, 0.f}, {}, feedback()).valid);
	EXPECT_LT(g.state()[0], 0.f);
	EXPECT_FALSE(g.step({1.f, 0.f, 0.f}, {}, feedback()).valid);
	f = airborne(1012000); f.maybe_landed = true;
	const float old = g.state()[0]; g.begin(c, f);
	EXPECT_FALSE(g.canUpdate()); EXPECT_FLOAT_EQ(g.state()[0], old);
	f.sample += 4000; f.landed = true; g.begin(c, f);
	EXPECT_NE(g.resetReason() & Guard::Landed, 0); EXPECT_FLOAT_EQ(g.state()[0], 0.f);
	f.sample += 4000; g.begin(c, f); EXPECT_EQ(g.resetReason(), 0);
}

TEST(StaProtectionTest, ArmedConfigurationStagingCancelRejectAndDisarmApply)
{
	Guard g; auto c = config(); initialize(g, c);
	ASSERT_TRUE(g.step({1.f, 0.f, 0.f}, {}, feedback()).valid);
	const float nu = g.state()[0]; const auto seq = g.configSequence();
	auto changed = c; changed.gains[0].g = 20.f; changed.axes = 1;
	g.begin(changed, airborne(1008000));
	EXPECT_TRUE(g.pending()); EXPECT_EQ(g.configSequence(), seq);
	EXPECT_FLOAT_EQ(g.state()[0], nu); EXPECT_FLOAT_EQ(g.config().gains[0].g, 10.f);
	g.begin(c, airborne(1012000)); EXPECT_FALSE(g.pending());
	Guard::Frame f; f.sample = 1016000;
	g.begin(changed, f); EXPECT_FALSE(g.pending()); EXPECT_EQ(g.configSequence(), seq + 1);
	EXPECT_FLOAT_EQ(g.config().gains[0].g, 20.f); EXPECT_FLOAT_EQ(g.state()[0], 0.f);
	EXPECT_NE(g.resetReason() & Guard::Disarm, 0);
	changed.gains[0].g = NAN; f.sample += 4000; g.begin(changed, f);
	EXPECT_FALSE(g.configValid()); EXPECT_EQ(g.configSequence(), seq + 1); EXPECT_EQ(g.resetReason(), 0);
}

TEST(StaProtectionTest, ModeExitRateDisableAndReentry)
{
	for (bool exit_mode : {false, true}) {
		Guard g; initialize(g);
		ASSERT_TRUE(g.step({1.f, 1.f, 1.f}, {}, feedback()).valid);
		auto f = airborne(1008000);

		if (exit_mode) { f.experiment_active = false; } else { f.rate_enabled = false; }

		g.begin(config(), f); EXPECT_NE(g.resetReason() & Guard::Exit, 0);

		for (float nu : g.state()) { EXPECT_FLOAT_EQ(nu, 0.f); }

		EXPECT_FALSE(g.canUpdate());
		g.begin(config(), airborne(1012000)); EXPECT_TRUE(g.canUpdate());
	}
}

TEST(StaProtectionTest, RawTimeErrorsLatchAndCannotBeHiddenByClamping)
{
	const uint64_t samples[] = {1004000, 1003000, 1040000, 1004001};
	const Guard::Fault reasons[] = {Guard::DuplicateTime, Guard::BackwardTime, Guard::LongGap, Guard::ShortDt};

	for (size_t i = 0; i < 4; ++i) {
		Guard g; initialize(g); g.begin(config(), airborne(samples[i]));
		EXPECT_EQ(g.fault(), reasons[i]); EXPECT_TRUE(g.abortRequested()); EXPECT_FALSE(g.canUpdate());

		if (i == 1) { EXPECT_LT(g.rawDt(), 0.f); }

		if (i == 2) { EXPECT_GT(g.rawDt(), 0.02f); }

		EXPECT_FALSE(g.acknowledge());
		g.begin(config(), airborne(samples[i] + 4000)); EXPECT_TRUE(g.abortRequested());
		Guard::Frame f; f.sample = samples[i] + 8000; g.begin(config(), f);
		EXPECT_TRUE(g.abortRequested()); ASSERT_TRUE(g.acknowledge()); EXPECT_FALSE(g.abortRequested());
		EXPECT_NE(g.resetReason() & Guard::Acknowledge, 0);
	}
}

TEST(StaProtectionTest, InactivePidObserverDoesNotLatchOrAlterPidPolicy)
{
	Guard g; Guard::Config c;
	Guard::Frame f = airborne(1000); f.experiment_active = false;
	g.begin(c, f); f.sample = 999; f.measurement_valid = false; g.begin(c, f);
	EXPECT_EQ(g.timing(), Guard::BackwardTime); EXPECT_FALSE(g.abortRequested()); EXPECT_FALSE(g.canUpdate());
	EXPECT_FALSE(g.step({}, {}, feedback()).valid);
}

TEST(StaProtectionTest, MeasurementConfigurationAndNumericFaultNoPartialAxisCommit)
{
	Guard g; initialize(g); auto f = airborne(1008000); f.measurement_valid = false;
	g.begin(config(), f); EXPECT_EQ(g.fault(), Guard::Measurement);
	Guard bad; Guard::Frame init; init.sample = 1000000;
	bad.begin({}, init); bad.begin({}, airborne(1004000)); EXPECT_EQ(bad.fault(), Guard::Configuration);
	Guard numeric; initialize(numeric);
	const auto out = numeric.step({1.f, NAN, 1.f}, {}, feedback());
	EXPECT_FALSE(out.valid); EXPECT_EQ(numeric.fault(), Guard::Numerical);

	for (float nu : numeric.state()) { EXPECT_FLOAT_EQ(nu, 0.f); }

	for (float c : out.c_applied) { EXPECT_TRUE(std::isnan(c)); }
}

TEST(StaProtectionTest, MixerDirectionEachAxisAndUnwind)
{
	for (size_t axis = 0; axis < 3; ++axis) {
		for (float sign : {-1.f, 1.f}) {
			std::array<float, 3> rate{}; rate[axis] = sign;
			// s positive => delta_nu/g negative; negative saturation freezes it.
			const uint16_t opposing = sign > 0.f ? (1 << (4 + 2 * axis)) : (1 << (3 + 2 * axis));
			Guard g; initialize(g);
			const auto frozen = g.step(rate, {}, feedback(1 | opposing));
			ASSERT_TRUE(frozen.valid); EXPECT_EQ(frozen.limits[axis] & Guard::MixerFreeze, Guard::MixerFreeze);
			EXPECT_FLOAT_EQ(g.state()[axis], 0.f);
			Guard unwind; initialize(unwind);
			const uint16_t helping = sign > 0.f ? (1 << (3 + 2 * axis)) : (1 << (4 + 2 * axis));
			const auto out = unwind.step(rate, {}, feedback(1 | helping));
			ASSERT_TRUE(out.valid); EXPECT_LT(unwind.state()[axis] * sign, 0.f);
		}
	}
}

TEST(StaProtectionTest, InvalidStaleFutureAndBoundaryFeedback)
{
	const Guard::Feedback invalid[] = {{0, 1, 1}, {1000, 1004, 0}, {1000, 21001, 1}, {1005, 1004, 1}};

	for (const auto &fb : invalid) {
		Guard g; initialize(g); EXPECT_FALSE(fb.valid());
		const auto out = g.step({1.f, 0.f, 0.f}, {}, fb);
		ASSERT_TRUE(out.valid); EXPECT_NE(out.limits[0] & Guard::FeedbackInvalid, 0); EXPECT_FLOAT_EQ(g.state()[0], 0.f);
	}

	const Guard::Feedback boundary{1000, 21000, 1}; EXPECT_TRUE(boundary.valid());
}

TEST(StaProtectionTest, NuAndOutputLimitsRemainVisible)
{
	auto c = config(); c.nu_limit[0] = 0.001f;
	Guard g; initialize(g, c); const auto bounded = g.step({1.f, 0.f, 0.f}, {}, feedback());
	ASSERT_TRUE(bounded.valid); EXPECT_NE(bounded.limits[0] & Guard::NuLimit, 0);
	EXPECT_FLOAT_EQ(g.state()[0], -0.001f); EXPECT_FLOAT_EQ(bounded.nu[0], g.state()[0]);
	Guard clipped; initialize(clipped); const auto out = clipped.step({400.f, 0.f, 0.f}, {}, feedback());
	ASSERT_TRUE(out.valid); EXPECT_LT(out.c_raw[0], -1.f); EXPECT_FLOAT_EQ(out.c_applied[0], -1.f);
	EXPECT_NE(out.limits[0] & Guard::OutputLimit, 0); EXPECT_FLOAT_EQ(clipped.state()[0], 0.f);
}

TEST(StaProtectionTest, InvalidConfigurationDomain)
{
	auto c = config();

	for (int bad : {-1, 8, 256}) { c.axes = bad; EXPECT_FALSE(Guard::validConfig(c)); }
	c = config(); c.mode = 2; EXPECT_FALSE(Guard::validConfig(c));
	c = config(); c.axes = 0; EXPECT_FALSE(Guard::validConfig(c));

	for (float bad : {0.f, -1.f, NAN, INFINITY}) {
		c = config(); c.nu_limit[1] = bad; EXPECT_FALSE(Guard::validConfig(c));
		c = config(); c.c_limit = bad; EXPECT_FALSE(Guard::validConfig(c));
	}
}
