// Copyright (c) 2026 PX4 Development Team. All rights reserved.
// SPDX-License-Identifier: BSD-3-Clause

#include <gtest/gtest.h>
#include <RateControlDispatcher.hpp>
#include "test/M00RateControl.hpp"
#include <cstring>

using matrix::Vector3f;

static uint32_t bits(float value)
{
	uint32_t result;
	static_assert(sizeof(result) == sizeof(value), "float must be 32 bit");
	std::memcpy(&result, &value, sizeof(result));
	return result;
}

static void expectExact(const Vector3f &actual, const Vector3f &expected)
{
	for (int axis = 0; axis < 3; ++axis) {
		EXPECT_EQ(bits(actual(axis)), bits(expected(axis))) << "axis=" << axis;
	}
}

template<typename Controller>
static void gains(Controller &controller, int revision)
{
	const Vector3f k = revision ? Vector3f(0.8f, 1.2f, 0.9f) : Vector3f(1.f, 1.f, 1.f);
	controller.setGains(k.emult(Vector3f(0.15f, 0.16f, 0.20f)),
			    k.emult(Vector3f(0.2f, 0.17f, 0.1f)), k.emult(Vector3f(0.003f, 0.004f, 0.001f)));
	controller.setFeedForwardGain(revision ? Vector3f(0.04f, 0.02f, 0.03f) : Vector3f(0.02f, 0.03f, 0.01f));
	controller.setIntegratorLimit(revision ? Vector3f(0.04f, 0.03f, 0.02f) : Vector3f(0.03f, 0.02f, 0.01f));
}

static void fixedSequence(bool exercise_selection)
{
	RateControlDispatcher actual;
	M00RateControl reference;
	gains(actual, 0);
	gains(reference, 0);
	bool saw_nonzero_integral = false;
	bool saw_output_above_one = false;
	unsigned active_steps = 0;
	const float timesteps[] = {0.000125f, 0.002f, 0.004f, 0.01f, 0.02f};

	for (int step = 0; step < 2048; ++step) {
		SCOPED_TRACE(::testing::Message() << "step=" << step);
		// Replay the original module's reset/update order, including periods when
		// rate control is disabled. The new selector must never reset PID state.
		const bool armed = (step % 256) >= 24;
		const bool rotary_wing = (step % 311) != 0;
		const bool rates_enabled = (step % 173) >= 5;
		const bool landed = (step % 256) < 34;
		const bool maybe_landed = (step % 256) >= 245;

		if (step == 101 || step == 601 || step == 1401) {
			// These revisions occur armed too, preserving live PID gain updates.
			gains(actual, (step / 100) % 2);
			gains(reference, (step / 100) % 2);
		}

		const int modes[] = {0, 1, 2, -1, 256, 0};
		const int mode = exercise_selection ? modes[(step / 41) % 6] : 0;
		const int axes = exercise_selection ? ((step / 19) % 10) - 1 : 0;
		actual.select(mode, axes, armed);
		EXPECT_EQ(actual.selectionStatus().effective_mode, ControllerSelection::PID);
		EXPECT_EQ(actual.selectionStatus().effective_axes, 0);

		if (rates_enabled) {
			++active_steps;

			if (!armed || !rotary_wing) {
				actual.resetIntegral();
				reference.resetIntegral();
			}

			// Feedback sometimes does not update: retain the preceding saturation.
			if ((step % 7) != 0) {
				MultirotorMixer::saturation_status saturation{};
				saturation.flags.valid = true;
				saturation.flags.roll_pos = (step % 37) < 7;
				saturation.flags.roll_neg = (step % 41) < 9;
				saturation.flags.pitch_pos = (step % 31) < 8;
				saturation.flags.pitch_neg = (step % 43) < 7;
				saturation.flags.yaw_pos = (step % 47) < 6;
				saturation.flags.yaw_neg = (step % 29) < 5;
				actual.setSaturationStatus(saturation);
				reference.setSaturationStatus(saturation);
			}

			const Vector3f rates(((step % 47) - 23) * 0.071f, ((step % 53) - 26) * 0.052f,
					     ((step % 31) - 15) * 0.047f);
			const Vector3f sp((step % 2) ? 8.f : -8.f, 1.4f, -0.7f);
			const Vector3f accel(((step % 19) - 9) * 0.7f, ((step % 13) - 6) * 0.6f, ((step % 17) - 8) * 0.5f);
			const float dt = timesteps[step % 5];
			const Vector3f output = actual.update(rates, sp, accel, dt, landed || maybe_landed);
			expectExact(output, reference.update(rates, sp, accel, dt, landed || maybe_landed));
			saw_output_above_one |= fabsf(output(0)) > 1.f;
		}

		rate_ctrl_status_s a{}, b{};
		actual.getRateControlStatus(a);
		reference.getRateControlStatus(b);
		expectExact(Vector3f(a.rollspeed_integ, a.pitchspeed_integ, a.yawspeed_integ),
			    Vector3f(b.rollspeed_integ, b.pitchspeed_integ, b.yawspeed_integ));
		saw_nonzero_integral |= fabsf(a.pitchspeed_integ) > 0.f;
	}

	EXPECT_GT(active_steps, 1900u);
	EXPECT_TRUE(saw_nonzero_integral);
	EXPECT_TRUE(saw_output_above_one); // Detect accidental new output limiting.
}

TEST(RateControlDispatcher, DefaultPidBitwiseMatchesFrozenM00)
{
	fixedSequence(false);
}

TEST(RateControlDispatcher, RejectedAndPendingSelectionsPreservePidBitwise)
{
	fixedSequence(true);
}

TEST(RateControlDispatcher, UsesOldIntegralAndLandedFreezesWithoutClearing)
{
	RateControlDispatcher controller;
	controller.setGains(Vector3f(), Vector3f(1.f, 1.f, 1.f), Vector3f());
	controller.setIntegratorLimit(Vector3f(1.f, 1.f, 1.f));
	const Vector3f zero;
	const Vector3f error(0.1f, -0.2f, 0.3f);
	expectExact(controller.update(zero, error, zero, 0.01f, false), zero);
	rate_ctrl_status_s status{};
	controller.getRateControlStatus(status);
	const Vector3f integral(status.rollspeed_integ, status.pitchspeed_integ, status.yawspeed_integ);
	EXPECT_NE(integral(0), 0.f);
	controller.select(1, 1, true);
	expectExact(controller.update(zero, error, zero, 0.01f, true), integral);
	controller.select(2, 7, false); // A rejected request alone does not reset PID.
	expectExact(controller.update(zero, error, zero, 0.01f, true), integral);
	controller.resetIntegral();
	expectExact(controller.update(zero, error, zero, 0.01f, true), zero);
}

TEST(RateControlDispatcher, AllAxesSkipsPidAndDisarmedReturnStartsResetState)
{
	RateControlDispatcher c; gains(c, 0);
	const Vector3f zero, sp(.1f, -.2f, .3f);
	c.update(zero, sp, zero, .004f, false);
	rate_ctrl_status_s before{}, after{}; c.getRateControlStatus(before);
	c.select(1, 7, false, true); EXPECT_FALSE(c.pidRequired());
	const auto seq = c.pidUpdateSequence();
	for (int i = 0; i < 100; ++i) {
		c.select(0, 0, true); // airborne request cannot resume PID, including after an ESTA fault
		const auto ignored = c.update(zero, sp, zero, .004f, false);
		for (int axis = 0; axis < 3; ++axis) { EXPECT_TRUE(std::isnan(ignored(axis))); }
	}
	EXPECT_EQ(c.pidUpdateSequence(), seq); c.getRateControlStatus(after);
	EXPECT_EQ(bits(before.rollspeed_integ), bits(after.rollspeed_integ));
	EXPECT_EQ(bits(before.pitchspeed_integ), bits(after.pitchspeed_integ));
	EXPECT_EQ(bits(before.yawspeed_integ), bits(after.yawspeed_integ));
	c.select(0, 0, false); c.resetIntegral(); // actual module order on disarm
	RateControlDispatcher fresh; gains(fresh, 0);
	expectExact(c.update(zero, sp, zero, .004f, true), fresh.update(zero, sp, zero, .004f, true));
	EXPECT_EQ(c.pidUpdateSequence(), seq + 1);
	for (int mask : {1, 3, 7, 1, 0}) {
		c.select(mask ? 1 : 0, mask, false, true); c.resetIntegral();
		EXPECT_EQ(c.pidRequired(), mask != 7);
	}
}
