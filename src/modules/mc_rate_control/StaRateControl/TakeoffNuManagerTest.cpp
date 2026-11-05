// SPDX-License-Identifier: BSD-3-Clause
#include "TakeoffNuManager.hpp"
#include "StaProtection.hpp"
#include <gtest/gtest.h>

namespace
{
using M = TakeoffNuManager;

M::Input input(uint64_t t, bool armed, bool landed, bool maybe_landed, float z = 0.f, float vz = 0.f)
{
	M::Input in;
	in.sample = t; in.selected = true; in.armed = armed; in.rate_enabled = true;
	in.landed = landed; in.maybe_landed = maybe_landed;
	in.estimate_valid = true; in.z_m = z; in.vz_m_s = vz;
	return in;
}

M configured()
{
	M manager;
	M::Config config; config.enabled = true;
	EXPECT_TRUE(manager.setConfig(config));
	return manager;
}

StaProtection::Config guardConfig(bool enabled)
{
	StaProtection::Config c;
	c.mode = 1; c.axes = 1; c.c_limit = 1.f;
	c.gains[0] = {1.f, 1.f, 1.f}; c.nu_limit[0] = 10.f;
	c.takeoff.enabled = enabled;
	return c;
}
}

TEST(TakeoffNuManagerTest, DefaultDisabledIsTransparent)
{
	M manager;
	const auto out = manager.update(input(1000, true, true, true));
	EXPECT_EQ(out.state, M::State::Disabled);
	EXPECT_FALSE(out.freeze); EXPECT_FALSE(out.reset); EXPECT_FALSE(out.abort);
}

TEST(TakeoffNuManagerTest, RejectsInvalidThresholds)
{
	M::Config config; config.enabled = true; config.landing_height_m = config.release_height_m;
	EXPECT_FALSE(M::validConfig(config));
	config = {}; config.enabled = true; config.wait_timeout_us = config.takeoff_confirm_us;
	EXPECT_FALSE(M::validConfig(config));
}

TEST(TakeoffNuManagerTest, ArmTakeoffAndHystereticRelease)
{
	auto manager = configured();
	auto out = manager.update(input(1000, true, true, true));
	EXPECT_EQ(out.state, M::State::Waiting); EXPECT_TRUE(out.freeze); EXPECT_TRUE(out.reset);
	out = manager.update(input(2000, true, false, false, -0.13f, -0.1f));
	EXPECT_EQ(out.state, M::State::ConfirmingTakeoff); EXPECT_TRUE(out.freeze);
	out = manager.update(input(201000, true, false, false, -0.13f, 0.f));
	EXPECT_EQ(out.state, M::State::ConfirmingTakeoff);
	out = manager.update(input(202000, true, false, false, -0.13f, 0.f));
	EXPECT_EQ(out.state, M::State::Released); EXPECT_FALSE(out.freeze);
}

TEST(TakeoffNuManagerTest, FalseTakeoffAndCancellationDoNotRelease)
{
	auto manager = configured();
	manager.update(input(1000, true, true, true));
	EXPECT_EQ(manager.update(input(2000, true, false, false, -0.13f, 0.f)).state, M::State::ConfirmingTakeoff);
	auto out = manager.update(input(100000, true, true, true, -0.13f, 0.f));
	EXPECT_EQ(out.state, M::State::Waiting); EXPECT_EQ(out.event, M::Event::TakeoffCancelled); EXPECT_TRUE(out.freeze);
}

TEST(TakeoffNuManagerTest, EstimatorJumpAbortsUntilDisarmThenRearm)
{
	auto manager = configured();
	manager.update(input(1000, true, true, true));
	auto out = manager.update(input(2000, true, true, true, -0.8f, 0.f));
	EXPECT_EQ(out.state, M::State::Fault); EXPECT_TRUE(out.abort); EXPECT_TRUE(out.freeze);
	out = manager.update(input(3000, false, true, true));
	EXPECT_EQ(out.state, M::State::Idle); EXPECT_FALSE(out.abort);
	out = manager.update(input(4000, true, true, true));
	EXPECT_EQ(out.state, M::State::Waiting); EXPECT_TRUE(out.reset);
}

TEST(TakeoffNuManagerTest, TimeoutAbortsRatherThanPermanentlyWaiting)
{
	auto manager = configured();
	manager.update(input(1000, true, true, true));
	auto out = manager.update(input(10001001, true, true, true));
	EXPECT_EQ(out.state, M::State::Fault); EXPECT_EQ(out.event, M::Event::Timeout); EXPECT_TRUE(out.abort);
}

TEST(TakeoffNuManagerTest, AirborneLandFlagAndBounceDoNotResetState)
{
	auto manager = configured();
	manager.update(input(1000, true, true, true));
	manager.update(input(2000, true, false, false, -0.13f, 0.f));
	manager.update(input(202000, true, false, false, -0.13f, 0.f));
	manager.update(input(250000, true, false, false, -0.5f, 0.f));
	manager.update(input(275000, true, false, false, -0.9f, 0.f));
	auto out = manager.update(input(300000, true, true, true, -1.f, 0.f));
	EXPECT_EQ(out.state, M::State::Released); EXPECT_FALSE(out.reset); // false in-air land flag
	manager.update(input(325000, true, false, false, -0.6f, 0.f));
	manager.update(input(350000, true, false, false, -0.2f, 0.f));
	out = manager.update(input(400000, true, true, true, -0.02f, 0.f));
	EXPECT_EQ(out.state, M::State::ConfirmingLanding); EXPECT_TRUE(out.freeze); EXPECT_FALSE(out.reset);
	out = manager.update(input(450000, true, false, false, -0.03f, -0.1f));
	EXPECT_EQ(out.state, M::State::Released); EXPECT_EQ(out.event, M::Event::LandingCancelled);
}

TEST(TakeoffNuManagerTest, ConfirmedLandingResetsAndSecondTakeoffCanRelease)
{
	auto manager = configured();
	manager.update(input(1000, true, true, true));
	manager.update(input(2000, true, false, false, -0.13f, 0.f));
	manager.update(input(202000, true, false, false, -0.13f, 0.f));
	manager.update(input(300000, true, true, true, 0.f, 0.f));
	auto out = manager.update(input(800000, true, true, true, 0.f, 0.f));
	EXPECT_EQ(out.state, M::State::LandedHold); EXPECT_TRUE(out.reset);
	out = manager.update(input(900000, true, false, false, -0.01f, 0.f));
	EXPECT_EQ(out.state, M::State::Waiting);
	manager.update(input(901000, true, false, false, -0.14f, 0.f));
	out = manager.update(input(1101000, true, false, false, -0.14f, 0.f));
	EXPECT_EQ(out.state, M::State::Released); EXPECT_FALSE(out.freeze);
}

TEST(TakeoffNuManagerTest, ArmedConfigurationIsStagedUntilDisarm)
{
	StaProtection guard;
	auto disabled = guardConfig(false);
	StaProtection::Frame frame; frame.sample = 1000;
	guard.begin(disabled, frame);
	EXPECT_FALSE(guard.config().takeoff.enabled);

	frame.sample = 5000; frame.armed = true; frame.rate_enabled = true; frame.experiment_active = true;
	frame.landed = false; frame.maybe_landed = false;
	auto enabled = guardConfig(true);
	guard.begin(enabled, frame);
	EXPECT_TRUE(guard.pending()); EXPECT_FALSE(guard.config().takeoff.enabled);

	frame.sample = 9000; frame.armed = false; frame.rate_enabled = false; frame.experiment_active = false;
	frame.landed = true; frame.maybe_landed = true;
	guard.begin(enabled, frame);
	EXPECT_TRUE(guard.config().takeoff.enabled);
	frame.sample = 13000; frame.armed = true; frame.rate_enabled = true; frame.experiment_active = true;
	guard.begin(enabled, frame);
	EXPECT_EQ(guard.takeoffState(), M::State::Waiting);
	EXPECT_NE(guard.resetReason() & StaProtection::TakeoffManaged, 0);
}

TEST(TakeoffNuManagerTest, CommonFaultNeedsDisarmedAcknowledgeBeforeRearm)
{
	StaProtection guard; auto c = guardConfig(true);
	StaProtection::Frame f; f.sample = 1000; f.local_position_valid = true; f.local_z = 0.f; f.local_vz = 0.f;
	guard.begin(c, f);
	f.sample = 5000; f.armed = true; f.rate_enabled = true; f.experiment_active = true;
	guard.begin(c, f);
	f.sample = 9000; f.local_z = -0.8f;
	guard.begin(c, f);
	EXPECT_EQ(guard.fault(), StaProtection::TakeoffManagement); EXPECT_TRUE(guard.abortRequested());
	EXPECT_FALSE(guard.acknowledge());
	f.sample = 13000; f.armed = false; f.rate_enabled = false; f.experiment_active = false;
	guard.begin(c, f);
	EXPECT_TRUE(guard.acknowledge()); EXPECT_EQ(guard.fault(), StaProtection::None);
	f.sample = 17000; f.armed = true; f.rate_enabled = true; f.experiment_active = true; f.local_z = 0.f;
	guard.begin(c, f);
	EXPECT_EQ(guard.takeoffState(), M::State::Waiting); EXPECT_FALSE(guard.abortRequested());
}
