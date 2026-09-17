// SPDX-License-Identifier: BSD-3-Clause
#include "StaProtection.hpp"
#include <gtest/gtest.h>
#include <cmath>
#include <cstring>
#include "StaRollApplication.hpp"
#include "../RateControl/ControllerSelection.hpp"
#include "../../mc_att_control/AttitudeControl/ResearchPulse.hpp"
#include "../../sensors/vehicle_angular_velocity/GyroPublicationGuard.hpp"

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
	c = config(); c.mode = 3; EXPECT_FALSE(Guard::validConfig(c));
	c = config(); c.axes = 0; EXPECT_FALSE(Guard::validConfig(c));

	for (float bad : {0.f, -1.f, NAN, INFINITY}) {
		c = config(); c.nu_limit[1] = bad; EXPECT_FALSE(Guard::validConfig(c));
		c = config(); c.c_limit = bad; EXPECT_FALSE(Guard::validConfig(c));
	}
}

TEST(M04, RollDirectionAndNonselectedPidBitIdentity)
{
	for (float sign : {-1.f, 1.f}) {
		Guard g; auto c = config(); c.axes = 1; initialize(g, c);
		const auto result = g.step({sign, 0.f, 0.f}, {}, feedback(), true);
		ASSERT_TRUE(result.valid); EXPECT_LT(result.c_raw[0] * sign, 0.f);
		std::array<float, 3> mixed{}, pid{.125f, -.234567f, .345678f};
		ASSERT_TRUE(StaRollApplication::apply(true, true, result, pid, mixed));
		EXPECT_FLOAT_EQ(mixed[0], result.c_applied[0]);
		EXPECT_EQ(std::memcmp(&mixed[1], &pid[1], 2 * sizeof(float)), 0);
		ASSERT_TRUE(StaRollApplication::apply(false, true, {}, pid, mixed));
		EXPECT_EQ(std::memcmp(mixed.data(), pid.data(), 3 * sizeof(float)), 0);
	}
}

TEST(M04, FaultSuppressesActuationRatherThanPidTakeover)
{
	std::array<float, 3> mixed{}, pid{.1f, .2f, .3f};
	EXPECT_FALSE(StaRollApplication::apply(true, true, {}, pid, mixed));
	Guard g; auto c = config(); c.axes = 1; initialize(g, c);
	g.begin(c, airborne(1004000));
	EXPECT_TRUE(g.abortRequested());
	EXPECT_FALSE(StaRollApplication::apply(true, true, g.step({}, {}, feedback(), true), pid, mixed));
	EXPECT_TRUE(StaRollApplication::apply(true, false, {}, pid, mixed));
	EXPECT_FLOAT_EQ(mixed[0], 0.f); // only disarmed, never fault fallback
}

TEST(M04, GroundCorrectionWithoutNuIntegration)
{
	Guard g; auto c = config(); c.axes = 1; initialize(g, c);
	auto f = airborne(1008000); f.landed = true; f.maybe_landed = true;
	g.begin(c, f);
	const auto result = g.step({.1f, 0.f, 0.f}, {}, feedback(), true);
	ASSERT_TRUE(result.valid); EXPECT_FALSE(result.updated);
	EXPECT_LT(result.c_applied[0], 0.f); EXPECT_FLOAT_EQ(g.state()[0], 0.f);
	EXPECT_FALSE(g.step({}, {}, feedback(), true).valid);
	EXPECT_FALSE(g.canUpdate());
}

TEST(M04, CapabilityRollOnlyAndArmedSwitchIsStaged)
{
	ControllerSelection s;
	s.select(1, 1, false, false); EXPECT_EQ(s.status().effective_mode, 0);
	s.select(1, 1, false, true); EXPECT_EQ(s.status().effective_mode, 1);
	s.select(0, 0, true, true); EXPECT_EQ(s.status().effective_mode, 1); EXPECT_TRUE(s.status().pending);
	s.select(1, 1, true, true); EXPECT_FALSE(s.status().pending);
	s.select(2, 1, false, true); EXPECT_EQ(s.status().request_status, ControllerSelection::Unsupported);
	s.select(1, 7, false, false); EXPECT_EQ(s.status().effective_axes, 1); // uncalibrated capability still rejected
	EXPECT_EQ(s.status().request_status, ControllerSelection::Unsupported);
	s.select(0, 0, false); EXPECT_EQ(s.status().effective_mode, 0);
}

TEST(M04, RejectInvalidConfigurationOnArmingButNotMidflight)
{
	Guard g; auto c = config(); c.axes = 1; initialize(g, c);
	auto bad = c; bad.c_limit = 0.f;
	g.begin(bad, airborne(1008000)); EXPECT_TRUE(g.pending()); EXPECT_FALSE(g.abortRequested());
	Guard::Frame ground; ground.sample = 1012000; g.begin(bad, ground);
	g.begin(bad, airborne(1016000)); EXPECT_EQ(g.fault(), Guard::Configuration);
}

TEST(M04, PulseZeroIntegralBoundedAndSingleTrigger)
{
	double sum = 0.;

	for (int k = 0; k <= 6000; ++k) {
		const float v = ResearchPulse::value(k * .004f);
		EXPECT_LE(fabsf(v), .120001f); sum += static_cast<double>(v) * .004;
	}

	EXPECT_NEAR(sum, 0., 1e-6);
	ResearchPulse p;
	EXPECT_FLOAT_EQ(p.update(true, false, 1000000), 0.f);
	EXPECT_FLOAT_EQ(p.update(true, true, 2000000), 0.f); // no automatic trigger after forbidden request
	p.update(false, true, 3000000); p.update(true, true, 4000000);
	EXPECT_NEAR(p.update(true, true, 5000000), .04f, 1e-6f);
	EXPECT_FLOAT_EQ(p.update(true, true, 30000000), 0.f);
}

static void checkLaggedRollObject(float lambda1, float lambda2)
{
	for (double mismatch : {.8, 1., 1.2}) {
		Guard g; auto c = config(); c.axes = 1; c.c_limit = .15f;
		c.gains[0] = {lambda1, lambda2, 130.575283f}; c.nu_limit[0] = 3.f;
		Guard::Frame ground; ground.sample = 1000000; g.begin(c, ground);
		double angle = 0., rate = 0., acceleration = 0., max_angle = 0.;

		for (int k = 1; k <= 15000; ++k) {
			g.begin(c, airborne(1000000 + 4000 * k));
			const float sp = static_cast<float>(-6.5 * angle) + ResearchPulse::value(k * .004f - 15.f);
			const auto out = g.step({static_cast<float>(rate), 0.f, 0.f}, {sp, 0.f, 0.f}, feedback(), true);
			ASSERT_TRUE(out.valid);
			// Independent rigid-body integrator with 25 ms actuator lag;
			// uncertainty sweep is engineering sensitivity, not flight validation.
			acceleration += (130.575283 * mismatch * static_cast<double>(out.c_applied[0]) - acceleration) * (1. - exp(
						-.004 / .025));
			rate += .004 * acceleration; angle += .004 * rate;
			max_angle = std::max(max_angle, fabs(angle));
			ASSERT_TRUE(std::isfinite(rate)); EXPECT_LT(fabs(rate), 1.);
		}

		EXPECT_LT(max_angle, .261799); EXPECT_LT(fabs(angle), .01);
	}
}

TEST(M04, PulsesOnIndependentLaggedRollObject)
{
	checkLaggedRollObject(3.f, 6.f);
	checkLaggedRollObject(3.f, .5f);
	checkLaggedRollObject(1.5f, .5f);
	checkLaggedRollObject(1.5f, .05f);
	checkLaggedRollObject(2.5f, .05f);
}

TEST(M04, UpstreamDuplicateDoesNotAdvanceNuAndRealGapStillLatches)
{
	GyroPublicationGuard source;
	Guard g; auto c = config(); c.axes = 1;
	Guard::Frame ground; ground.sample = 1000000;
	ASSERT_TRUE(source.consider(ground.sample, 1, true).publish); g.begin(c, ground);
	ASSERT_TRUE(source.consider(1004000, 1, true).publish); g.begin(c, airborne(1004000));
	ASSERT_TRUE(g.step({.1f, 0.f, 0.f}, {}, feedback(), true).valid);
	const float nu = g.state()[0];
	EXPECT_FALSE(source.consider(1004000, 2, true).publish);
	EXPECT_FLOAT_EQ(g.state()[0], nu); // no new downstream begin/update
	ASSERT_TRUE(source.consider(1008000, 2, true).publish); g.begin(c, airborne(1008000));
	EXPECT_EQ(g.timing(), Guard::None); EXPECT_FALSE(g.abortRequested());
	ASSERT_TRUE(source.consider(1108000, 2, true).publish); g.begin(c, airborne(1108000));
	EXPECT_EQ(g.fault(), Guard::LongGap); EXPECT_TRUE(g.abortRequested());
	EXPECT_FALSE(g.step({}, {}, feedback(), true).valid);
}
