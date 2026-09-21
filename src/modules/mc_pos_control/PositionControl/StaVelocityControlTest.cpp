// SPDX-License-Identifier: BSD-3-Clause
#include "StaVelocityControl.hpp"
#include "VelocityControlSelector.hpp"

#include <gtest/gtest.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>

namespace
{
using Controller = StaVelocityControl;
using Status = Controller::Status;

constexpr float kNan = std::numeric_limits<float>::quiet_NaN();
constexpr float kInf = std::numeric_limits<float>::infinity();
constexpr float kHuge = std::numeric_limits<float>::max();

struct DoubleStep {
	double s;
	double a;
	double nu_next;
};

// Deliberately binary64 and separate from the production candidate lifecycle.
DoubleStep doubleEsta(double velocity, double velocity_sp, double nu, double lambda1, double lambda2, double dt)
{
	const double s = velocity - velocity_sp;
	const double sign = s > 0. ? 1. : (s < 0. ? -1. : 0.);
	return {s, -lambda1 * std::sqrt(std::fabs(s)) * sign + nu, nu - dt * lambda2 * sign};
}

void expectRejected(const Controller::Candidate &candidate, Status expected)
{
	EXPECT_FALSE(candidate.valid());
	EXPECT_EQ(candidate.status, expected);
	EXPECT_TRUE(std::isnan(candidate.s));
	EXPECT_TRUE(std::isnan(candidate.a_sta));
	EXPECT_TRUE(std::isnan(candidate.nu_before));
	EXPECT_TRUE(std::isnan(candidate.nu_next));
}

float addFeedForwardOnce(float a_sta, float a_ff)
{
	return a_sta + a_ff;
}
}

TEST(StaVelocityControlTest, EvaluateUsesOldNuAndAdapterAddsFeedForwardOnce)
{
	Controller controller;
	ASSERT_TRUE(controller.setParameters(0, {2.f, 4.f}));
	ASSERT_TRUE(controller.reset(0, .5f));
	const auto candidate = controller.evaluate(0, 5.f, 1.f, .125f);
	ASSERT_TRUE(candidate.valid());
	EXPECT_FLOAT_EQ(candidate.s, 4.f);
	EXPECT_FLOAT_EQ(candidate.nu_before, .5f);
	EXPECT_FLOAT_EQ(candidate.a_sta, -3.5f);
	EXPECT_FLOAT_EQ(candidate.nu_next, 0.f);
	// V02 has no production adapter: this local test models the one permitted
	// future composition a_req=a_sta+a_ff, not a second feed-forward injection.
	EXPECT_FLOAT_EQ(addFeedForwardOnce(candidate.a_sta, .75f), -2.75f);
	EXPECT_EQ(controller.commit(candidate), Status::Ok);
	EXPECT_FLOAT_EQ(controller.state()[0], 0.f);
	const auto next = controller.evaluate(0, 5.f, 1.f, .125f);
	ASSERT_TRUE(next.valid());
	EXPECT_FLOAT_EQ(next.a_sta, -4.f);
	EXPECT_FLOAT_EQ(next.nu_next, -.5f);
}

TEST(StaVelocityControlTest, PositiveNegativeAndZeroError)
{
	Controller positive, negative;
	ASSERT_TRUE(positive.setParameters(0, {2.75f, 1.75f}));
	ASSERT_TRUE(negative.setParameters(0, {2.75f, 1.75f}));
	ASSERT_TRUE(positive.reset(0, .375f));
	ASSERT_TRUE(negative.reset(0, -.375f));

	for (int k = 1; k <= 128; ++k) {
		const float value = static_cast<float>(k) / 16.f;
		const auto p = positive.evaluate(0, value, .125f, .008f);
		const auto n = negative.evaluate(0, -value, -.125f, .008f);
		ASSERT_TRUE(p.valid()); ASSERT_TRUE(n.valid());
		EXPECT_FLOAT_EQ(p.a_sta, -n.a_sta);
		EXPECT_FLOAT_EQ(p.nu_next, -n.nu_next);
		ASSERT_EQ(positive.commit(p), Status::Ok);
		ASSERT_EQ(negative.commit(n), Status::Ok);
	}

	Controller zero;
	ASSERT_TRUE(zero.setParameters(0, {2.f, 4.f}));
	ASSERT_TRUE(zero.reset(0, -.75f));
	const auto result = zero.evaluate(0, 1.25f, 1.25f, .012f);
	ASSERT_TRUE(result.valid());
	EXPECT_FLOAT_EQ(result.a_sta, -.75f);
	EXPECT_FLOAT_EQ(result.nu_next, -.75f);
}

TEST(StaVelocityControlTest, StatesAreThreeAxisIndependentAndCandidatesAreOneShot)
{
	Controller controller, other;
	for (size_t axis = 0; axis < 3; ++axis) {
		ASSERT_TRUE(controller.setParameters(axis, {2.f, static_cast<float>(axis + 1)}));
		ASSERT_TRUE(controller.reset(axis, static_cast<float>(axis + 1)));
	}

	const auto y = controller.evaluate(1, 1.f, 0.f, .012f);
	ASSERT_TRUE(y.valid());
	EXPECT_EQ(controller.commit(y), Status::Ok);
	EXPECT_FLOAT_EQ(controller.state()[0], 1.f);
	EXPECT_FLOAT_EQ(controller.state()[1], 1.976f);
	EXPECT_FLOAT_EQ(controller.state()[2], 3.f);
	EXPECT_EQ(controller.commit(y), Status::StaleCandidate);
	EXPECT_FLOAT_EQ(controller.state()[1], 1.976f);

	const auto stale_after_reset = controller.evaluate(2, 1.f, 0.f, .008f);
	ASSERT_TRUE(controller.reset(2));
	EXPECT_EQ(controller.commit(stale_after_reset), Status::StaleCandidate);
	EXPECT_FLOAT_EQ(controller.state()[2], 0.f);
	const auto stale_after_configuration = controller.evaluate(0, 1.f, 0.f, .008f);
	ASSERT_TRUE(controller.setParameters(0, {3.f, 2.f}));
	EXPECT_EQ(controller.commit(stale_after_configuration), Status::StaleCandidate);
	EXPECT_FLOAT_EQ(controller.state()[0], 1.f);
	for (float nu : other.state()) { EXPECT_FLOAT_EQ(nu, 0.f); }

	controller.reset();
	for (float nu : controller.state()) { EXPECT_FLOAT_EQ(nu, 0.f); }
}

TEST(StaVelocityControlTest, InvalidInputsAndNumericsAreAtomic)
{
	Controller controller;
	ASSERT_TRUE(controller.setParameters(0, {2.f, 4.f}));
	ASSERT_TRUE(controller.reset(0, .75f));
	for (float bad : {0.f, -1.f, kNan, kInf, -kInf, std::numeric_limits<float>::denorm_min()}) {
		expectRejected(controller.evaluate(0, 1.f, 0.f, bad), Status::InvalidDt);
		EXPECT_FLOAT_EQ(controller.state()[0], .75f);
	}
	for (float bad : {kNan, kInf, -kInf}) {
		expectRejected(controller.evaluate(0, bad, 0.f, .008f), Status::InvalidInput);
		expectRejected(controller.evaluate(0, 0.f, bad, .008f), Status::InvalidInput);
	}
	EXPECT_FALSE(controller.setParameters(3, {2.f, 4.f}));
	expectRejected(controller.evaluate(3, 0.f, 0.f, .008f), Status::InvalidAxis);

	const std::array<Controller::Parameters, 5> invalid_parameters{{
		{0.f, 1.f}, {-1.f, 1.f}, {kNan, 1.f}, {1.f, kInf}, {std::numeric_limits<float>::denorm_min(), 1.f}
	}};
	for (const Controller::Parameters &bad : invalid_parameters) {
		EXPECT_FALSE(Controller::validParameters(bad));
		EXPECT_FALSE(controller.setParameters(0, bad));
	}

	Controller overflow;
	ASSERT_TRUE(overflow.setParameters(0, {kHuge, 1.f}));
	ASSERT_TRUE(overflow.reset(0, kHuge));
	expectRejected(overflow.evaluate(0, -1.f, 0.f, .008f), Status::NumericalError);
	EXPECT_FLOAT_EQ(overflow.state()[0], kHuge);
	ASSERT_TRUE(overflow.setParameters(1, {1.f, kHuge}));
	expectRejected(overflow.evaluate(1, 0.f, 0.f, 2.f), Status::NumericalError);
	Controller underflow;
	ASSERT_TRUE(underflow.setParameters(0, {1.f, std::numeric_limits<float>::min()}));
	ASSERT_TRUE(underflow.reset(0, .25f));
	expectRejected(underflow.evaluate(0, 1.f, 0.f, .008f), Status::NumericalError);
	EXPECT_FLOAT_EQ(underflow.state()[0], .25f);
}

TEST(StaVelocityControlTest, FrozenEightTwelveMillisecondSequenceMatchesIndependentDoubleReference)
{
	Controller controller;
	const std::array<Controller::Parameters, 3> gains{{{2.4f, 1.2f}, {1.7f, .8f}, {3.1f, 2.3f}}};
	std::array<double, 3> nu{{.25, -.5, .75}};
	for (size_t axis = 0; axis < 3; ++axis) {
		ASSERT_TRUE(controller.setParameters(axis, gains[axis]));
		ASSERT_TRUE(controller.reset(axis, static_cast<float>(nu[axis])));
	}

	for (unsigned k = 0; k < 384; ++k) {
		const size_t axis = k % 3;
		const float dt = (k & 1U) ? .012f : .008f; // V00 recorded 8/12 ms, mean 10 ms.
		const float velocity = .6f * std::sin(.073f * static_cast<float>(k + axis)) + .1f * static_cast<float>(axis);
		const float sp = .25f * std::cos(.051f * static_cast<float>(k + 2 * axis));
		const auto reference = doubleEsta(velocity, sp, nu[axis], gains[axis].lambda1, gains[axis].lambda2, dt);
		const auto candidate = controller.evaluate(axis, velocity, sp, dt);
		ASSERT_TRUE(candidate.valid());
		EXPECT_NEAR(candidate.s, reference.s, 1e-6);
		EXPECT_NEAR(candidate.a_sta, reference.a, 2e-6 * std::max(1., std::fabs(reference.a)));
		EXPECT_NEAR(candidate.nu_next, reference.nu_next, 2e-6 * std::max(1., std::fabs(reference.nu_next)));
		ASSERT_EQ(controller.commit(candidate), Status::Ok);
		nu[axis] = reference.nu_next;
	}
}

TEST(StaVelocityControlTest, ZohObjectsSeparateIdealAndLaggedConstrainedConclusions)
{
	// These synthetic plants use acceleration units and V00's 8/12 ms cadence.
	// They are not Iris calibration and do not license a flight gain.
	for (int model = 0; model < 2; ++model) {
		Controller controller;
		ASSERT_TRUE(controller.setParameters(0, {4.f, 2.f}));
		double velocity = 1., nu = 0., applied_lag = 0., tail_squares = 0.;
		double t = 0.;
		unsigned saturated = 0, tail_count = 0;

		for (unsigned k = 0; k < 800; ++k) {
			const double dt = (k & 1U) ? .012 : .008;
			const double velocity_sp = .15 * std::sin(.5 * t);
			const double acceleration_ff = .075 * std::cos(.5 * t); // d(v_sp)/dt
			const double disturbance = model == 0 ? .18 : .18 + .04 * t; // constant / ramp
			const auto reference = doubleEsta(velocity, velocity_sp, nu, 4., 2., dt);
			const auto candidate = controller.evaluate(0, static_cast<float>(velocity), static_cast<float>(velocity_sp), static_cast<float>(dt));
			ASSERT_TRUE(candidate.valid());
			// The object retains binary64 velocity while the real-time kernel gets
			// its documented float interface, so this checks float-vs-double rather
			// than demanding an impossible bitwise identity.
			EXPECT_NEAR(candidate.a_sta, reference.a, 1e-5 * std::max(1., std::fabs(reference.a)));
			const double raw_request = addFeedForwardOnce(candidate.a_sta, static_cast<float>(acceleration_ff));
			double applied = raw_request;
			if (model == 1) {
				const double clipped = std::max(-.55, std::min(.55, raw_request));
				saturated += std::fabs(clipped - raw_request) > 0.;
				applied_lag += .35 * (clipped - applied_lag); // explicit actuator/attitude lag proxy
				applied = applied_lag;
			}
			velocity += dt * (applied + disturbance); // ZOH object, not a kernel prediction
			ASSERT_TRUE(std::isfinite(velocity));
			ASSERT_EQ(controller.commit(candidate), Status::Ok);
			nu = reference.nu_next;
			if (k >= 600) { tail_squares += std::pow(velocity - velocity_sp, 2); ++tail_count; }
			t += dt;
		}

		ASSERT_GT(tail_count, 0U);
		const double tail_rmse = std::sqrt(tail_squares / tail_count);
		EXPECT_TRUE(std::isfinite(tail_rmse));
		if (model == 0) {
			EXPECT_LT(tail_rmse, .08);

		} else {
			EXPECT_GT(saturated, 0U);
			// Constrained/lagged output is deliberately not claimed to solve the
			// ideal STA object; it is only a finite robustness exercise.
			EXPECT_GT(tail_rmse, 0.);
		}
	}
}

TEST(StaVelocityControlTest, ModeOneRemainsRejectedAndKernelHasNoDispatcherPath)
{
	VelocityControlSelector selector;
	selector.configure(1, 1, false);
	EXPECT_EQ(selector.effectiveMode(), 0);
	EXPECT_EQ(selector.effectiveAxes(), 0);
	EXPECT_EQ(selector.reject(), VelocityControlSelector::ModeUnimplemented | VelocityControlSelector::AxesUnavailable);
}
