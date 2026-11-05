/****************************************************************************
 *
 *   Copyright (C) 2019 PX4 Development Team. All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 *
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in
 *    the documentation and/or other materials provided with the
 *    distribution.
 * 3. Neither the name PX4 nor the names of its contributors may be
 *    used to endorse or promote products derived from this software
 *    without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
 * FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
 * COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
 * INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
 * BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS
 * OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED
 * AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
 * LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
 * ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 *
 ****************************************************************************/

#include <gtest/gtest.h>
#include <Takeoff.hpp>
#include <drivers/drv_hrt.h>
#include <lib/ecl/geo/geo.h>

TEST(TakeoffTest, Initialization)
{
	Takeoff takeoff;
	EXPECT_EQ(takeoff.getTakeoffState(), TakeoffState::disarmed);
}

TEST(TakeoffTest, RegularTakeoffRamp)
{
	Takeoff takeoff;
	takeoff.setSpoolupTime(1.f);
	takeoff.setTakeoffRampTime(2.0);
	takeoff.generateInitialRampValue(CONSTANTS_ONE_G / 0.5f);

	// disarmed, landed, don't want takeoff
	takeoff.updateTakeoffState(false, true, false, 1.f, false, 0);
	EXPECT_EQ(takeoff.getTakeoffState(), TakeoffState::disarmed);

	// armed, not landed anymore, don't want takeoff
	takeoff.updateTakeoffState(true, false, false, 1.f, false, 500_ms);
	EXPECT_EQ(takeoff.getTakeoffState(), TakeoffState::spoolup);

	// armed, not landed, don't want takeoff yet, spoolup time passed
	takeoff.updateTakeoffState(true, false, false, 1.f, false, 2_s);
	EXPECT_EQ(takeoff.getTakeoffState(), TakeoffState::ready_for_takeoff);

	// armed, not landed, want takeoff
	takeoff.updateTakeoffState(true, false, true, 1.f, false, 3_s);
	EXPECT_EQ(takeoff.getTakeoffState(), TakeoffState::rampup);

	// armed, not landed, want takeoff, ramping up
	takeoff.updateTakeoffState(true, false, true, 1.f, false, 4_s);
	// CODEV 317ee4c9cca deliberately overrides the calculated initial value
	// with zero. Preserve that production behavior (V00 scope approval).
	EXPECT_FLOAT_EQ(takeoff.updateRamp(.5f, 1.5f), .375f);
	EXPECT_FLOAT_EQ(takeoff.updateRamp(.5f, 1.5f), .75f);
	EXPECT_FLOAT_EQ(takeoff.updateRamp(.5f, 1.5f), 1.125f);
	EXPECT_FLOAT_EQ(takeoff.updateRamp(.5f, 1.5f), 1.5f);
	EXPECT_FLOAT_EQ(takeoff.updateRamp(.5f, 1.5f), 1.5f);

	// armed, not landed, want takeoff, rampup time passed
	takeoff.updateTakeoffState(true, false, true, 1.f, false, 6500_ms);
	EXPECT_EQ(takeoff.getTakeoffState(), TakeoffState::flight);
}

TEST(TakeoffTest, CodevZeroInitialValueIndependentOfGain)
{
	for (const float gain : {-1.f, 0.f, .005f, 1.f, 4.f, 20.f}) {
		Takeoff takeoff;
		takeoff.generateInitialRampValue(gain);
		EXPECT_FLOAT_EQ(takeoff.updateRamp(.1f, 1.5f), 0.f);
		takeoff.setSpoolupTime(0.f);
		takeoff.setTakeoffRampTime(2.f);
		takeoff.updateTakeoffState(true, false, true, 1.5f, false, 1_s);
		ASSERT_EQ(takeoff.getTakeoffState(), TakeoffState::rampup);
		EXPECT_FLOAT_EQ(takeoff.updateRamp(.5f, 1.5f), .375f);
	}
}

TEST(TakeoffTest, SpoolupCancellationRestartsDelay)
{
	Takeoff takeoff;
	takeoff.setSpoolupTime(1.f);
	takeoff.generateInitialRampValue(4.f);
	takeoff.updateTakeoffState(true, true, false, 1.f, false, 100_ms);
	takeoff.updateTakeoffState(false, true, false, 1.f, false, 500_ms);
	EXPECT_EQ(takeoff.getTakeoffState(), TakeoffState::disarmed);
	takeoff.updateTakeoffState(true, true, false, 1.f, false, 600_ms);
	takeoff.updateTakeoffState(true, true, false, 1.f, false, 1500_ms);
	EXPECT_EQ(takeoff.getTakeoffState(), TakeoffState::spoolup);
	EXPECT_FLOAT_EQ(takeoff.updateRamp(.1f, 1.f), 0.f);
	takeoff.updateTakeoffState(true, true, false, 1.f, false, 1600_ms);
	EXPECT_EQ(takeoff.getTakeoffState(), TakeoffState::ready_for_takeoff);
}

TEST(TakeoffTest, DisarmAndRearmRestartsRamp)
{
	Takeoff takeoff;
	takeoff.setSpoolupTime(0.f);
	takeoff.setTakeoffRampTime(2.f);
	takeoff.generateInitialRampValue(4.f);
	takeoff.updateTakeoffState(true, false, true, 2.f, false, 1_s);
	EXPECT_FLOAT_EQ(takeoff.updateRamp(1.f, 2.f), 1.f);
	takeoff.updateTakeoffState(false, true, false, 2.f, false, 2_s);
	EXPECT_EQ(takeoff.getTakeoffState(), TakeoffState::disarmed);
	EXPECT_FLOAT_EQ(takeoff.updateRamp(.5f, 2.f), 0.f);
	takeoff.updateTakeoffState(true, false, true, 2.f, false, 3_s);
	EXPECT_FLOAT_EQ(takeoff.updateRamp(.5f, 2.f), .5f);
}

TEST(TakeoffTest, LandingReturnsToReadyThenNewRamp)
{
	Takeoff takeoff;
	takeoff.setSpoolupTime(0.f);
	takeoff.setTakeoffRampTime(1.f);
	takeoff.generateInitialRampValue(4.f);
	takeoff.updateTakeoffState(true, false, true, 1.f, false, 1_s);
	EXPECT_FLOAT_EQ(takeoff.updateRamp(1.f, 1.f), 1.f);
	takeoff.updateTakeoffState(true, false, false, 1.f, false, 2_s);
	EXPECT_EQ(takeoff.getTakeoffState(), TakeoffState::flight);
	takeoff.updateTakeoffState(true, true, false, 1.f, false, 3_s);
	EXPECT_EQ(takeoff.getTakeoffState(), TakeoffState::ready_for_takeoff);
	EXPECT_FLOAT_EQ(takeoff.updateRamp(.1f, 1.f), 0.f);
	takeoff.updateTakeoffState(true, false, true, 1.f, false, 4_s);
	EXPECT_FLOAT_EQ(takeoff.updateRamp(.25f, 1.f), .25f);
}

TEST(TakeoffTest, ShortRampAndSkipTakeoff)
{
	for (const float ramp_time : {0.f, .01f, .1f}) {
		Takeoff takeoff;
		takeoff.setSpoolupTime(0.f);
		takeoff.setTakeoffRampTime(ramp_time);
		takeoff.generateInitialRampValue(4.f);
		takeoff.updateTakeoffState(true, false, true, 1.f, false, 1_s);
		EXPECT_FLOAT_EQ(takeoff.updateRamp(.1f, 1.f), 1.f);
	}
	Takeoff skipped;
	skipped.updateTakeoffState(true, false, false, 1.f, true, 1_s);
	EXPECT_EQ(skipped.getTakeoffState(), TakeoffState::flight);
	EXPECT_FLOAT_EQ(skipped.updateRamp(.1f, 2.f), 2.f);
	skipped.updateTakeoffState(false, true, false, 1.f, true, 2_s);
	EXPECT_EQ(skipped.getTakeoffState(), TakeoffState::disarmed);
}

TEST(TakeoffTest, NonuniformStepsAndChangedTarget)
{
	Takeoff takeoff;
	takeoff.setSpoolupTime(0.f);
	takeoff.setTakeoffRampTime(2.f);
	takeoff.generateInitialRampValue(4.f);
	takeoff.updateTakeoffState(true, false, true, 2.f, false, 1_s);
	EXPECT_FLOAT_EQ(takeoff.updateRamp(.25f, 2.f), .25f);
	EXPECT_FLOAT_EQ(takeoff.updateRamp(.75f, 1.f), .5f);
	EXPECT_FLOAT_EQ(takeoff.updateRamp(.5f, 2.f), 1.5f);
	EXPECT_FLOAT_EQ(takeoff.updateRamp(.75f, 2.f), 2.f);
}
