// SPDX-License-Identifier: BSD-3-Clause
#include "StaRateControl.hpp"
#include "test/ReferenceSamples.hpp"

#include <gtest/gtest.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <limits>

using Controller = StaRateControl;
using Status = Controller::Status;

namespace
{
constexpr float nan_value = std::numeric_limits<float>::quiet_NaN();
constexpr float inf_value = std::numeric_limits<float>::infinity();
constexpr float huge = std::numeric_limits<float>::max();

void expectRejected(const Controller::Result &out, Status reason)
{
	EXPECT_FALSE(out.valid());
	EXPECT_EQ(out.status, reason);
	EXPECT_TRUE(std::isnan(out.s));
	EXPECT_TRUE(std::isnan(out.a));
	EXPECT_TRUE(std::isnan(out.c_raw));
	EXPECT_TRUE(std::isnan(out.nu_next));
}
}

TEST(StaRateControlTest, StartsUnconfiguredAndRejectsInvalidAxis)
{
	Controller controller;
	expectRejected(controller.update(0, 1.f, 0.f, 0.01f), Status::Unconfigured);

	for (size_t axis : {size_t{3}, std::numeric_limits<size_t>::max()}) {
		expectRejected(controller.update(axis, 1.f, 0.f, 0.01f), Status::InvalidAxis);
		EXPECT_FALSE(controller.setParameters(axis, {2.f, 1.f, 1.f}));
		EXPECT_FALSE(controller.reset(axis, 1.f));
	}

	for (float nu : controller.state()) { EXPECT_FLOAT_EQ(nu, 0.f); }
}

TEST(StaRateControlTest, UsesOldNuAndAdvancesOnce)
{
	Controller controller;
	ASSERT_TRUE(controller.setParameters(0, {2.f, 4.f, 2.f}));
	ASSERT_TRUE(controller.reset(0, 0.5f));
	const auto first = controller.update(0, 5.f, 1.f, 0.125f);
	ASSERT_TRUE(first.valid());
	EXPECT_FLOAT_EQ(first.s, 4.f);
	EXPECT_FLOAT_EQ(first.a, -3.5f);
	EXPECT_FLOAT_EQ(first.c_raw, -1.75f); // deliberately not clipped to [-1, 1]
	EXPECT_FLOAT_EQ(first.nu_next, 0.f);
	const auto second = controller.update(0, 5.f, 1.f, 0.125f);
	ASSERT_TRUE(second.valid());
	EXPECT_FLOAT_EQ(second.a, -4.f);
	EXPECT_FLOAT_EQ(second.nu_next, -0.5f);
	EXPECT_FLOAT_EQ(controller.state()[0], -0.5f);
}

TEST(StaRateControlTest, PositiveNegativeSymmetry)
{
	Controller positive, negative;
	ASSERT_TRUE(positive.setParameters(0, {2.75f, 1.75f, 2.5f}));
	ASSERT_TRUE(negative.setParameters(0, {2.75f, 1.75f, 2.5f}));
	ASSERT_TRUE(positive.reset(0, 0.375f));
	ASSERT_TRUE(negative.reset(0, -0.375f));

	for (int k = 1; k <= 128; ++k) {
		const float rate = static_cast<float>(k) / 16.f;
		const auto p = positive.update(0, rate, 0.125f, 1.f / 256.f);
		const auto n = negative.update(0, -rate, -0.125f, 1.f / 256.f);
		ASSERT_TRUE(p.valid());
		ASSERT_TRUE(n.valid());
		EXPECT_FLOAT_EQ(p.a, -n.a);
		EXPECT_FLOAT_EQ(p.c_raw, -n.c_raw);
		EXPECT_FLOAT_EQ(p.nu_next, -n.nu_next);
	}
}

TEST(StaRateControlTest, ZeroErrorRetainsNonzeroNu)
{
	Controller controller;
	ASSERT_TRUE(controller.setParameters(0, {2.f, 4.f, 2.f}));

	for (float nu : {0.f, 0.75f, -0.75f}) {
		ASSERT_TRUE(controller.reset(0, nu));

		for (float rate : {0.f, -0.f, 1.25f, -1.25f}) {
			const auto out = controller.update(0, rate, rate, 0.125f);
			ASSERT_TRUE(out.valid());
			EXPECT_FLOAT_EQ(out.a, nu);
			EXPECT_FLOAT_EQ(out.c_raw, nu / 2.f);
			EXPECT_FLOAT_EQ(out.nu_next, nu);
		}
	}
}

TEST(StaRateControlTest, IndependentAxesInstancesAndReset)
{
	Controller controller, other;

	for (size_t axis = 0; axis < 3; ++axis) {
		ASSERT_TRUE(controller.setParameters(axis, {2.f, static_cast<float>(axis + 1), 1.f}));
		ASSERT_TRUE(controller.reset(axis, static_cast<float>(axis + 1)));
	}

	ASSERT_TRUE(controller.update(1, 1.f, 0.f, 0.125f).valid());
	EXPECT_FLOAT_EQ(controller.state()[0], 1.f);
	EXPECT_FLOAT_EQ(controller.state()[1], 1.75f);
	EXPECT_FLOAT_EQ(controller.state()[2], 3.f);

	for (float nu : other.state()) { EXPECT_FLOAT_EQ(nu, 0.f); }

	ASSERT_TRUE(controller.reset(1));
	EXPECT_FLOAT_EQ(controller.state()[1], 0.f);
	EXPECT_FLOAT_EQ(controller.state()[0], 1.f);
	EXPECT_FLOAT_EQ(controller.state()[2], 3.f);

	for (float bad : {nan_value, inf_value, -inf_value}) {
		EXPECT_FALSE(controller.reset(2, bad));
		EXPECT_FLOAT_EQ(controller.state()[2], 3.f);
	}
	controller.reset();

	for (size_t axis = 0; axis < 3; ++axis) {
		EXPECT_FLOAT_EQ(controller.state()[axis], 0.f);
		ASSERT_TRUE(controller.update(axis, 0.f, 0.f, 0.01f).valid());
	}
}

TEST(StaRateControlTest, ParameterValidationIsAtomicAndDoesNotReset)
{
	Controller controller;
	const Controller::Parameters good{2.f, 4.f, 2.f};
	ASSERT_TRUE(controller.setParameters(0, good));
	ASSERT_TRUE(controller.reset(0, 0.75f));

	for (float bad : {0.f, -1.f, nan_value, inf_value, -inf_value, std::numeric_limits<float>::denorm_min()}) {
		for (int field = 0; field < 3; ++field) {
			auto p = good;

			if (field == 0) { p.lambda1 = bad; }

			if (field == 1) { p.lambda2 = bad; }

			if (field == 2) { p.g = bad; }

			EXPECT_FALSE(Controller::validParameters(p));
			EXPECT_FALSE(controller.setParameters(0, p));
			const auto out = controller.update(0, 0.f, 0.f, 0.01f);
			ASSERT_TRUE(out.valid());
			EXPECT_FLOAT_EQ(out.a, 0.75f);
			EXPECT_FLOAT_EQ(out.c_raw, 0.375f);
		}
	}
	ASSERT_TRUE(controller.setParameters(0, {3.f, 5.f, 3.f}));
	EXPECT_FLOAT_EQ(controller.state()[0], 0.75f);
	const auto out = controller.update(0, 4.f, 0.f, 0.125f);
	ASSERT_TRUE(out.valid());
	EXPECT_FLOAT_EQ(out.a, -5.25f);
	EXPECT_FLOAT_EQ(out.nu_next, 0.125f);
}

TEST(StaRateControlTest, InvalidInputsAndDtPreserveAllState)
{
	Controller controller;
	ASSERT_TRUE(controller.setParameters(0, {2.f, 4.f, 2.f}));
	ASSERT_TRUE(controller.reset(0, 0.75f));

	for (float bad : {0.f, -1.f, nan_value, inf_value, -inf_value, std::numeric_limits<float>::denorm_min()}) {
		expectRejected(controller.update(0, 1.f, 0.f, bad), Status::InvalidDt);
		EXPECT_FLOAT_EQ(controller.state()[0], 0.75f);
	}

	for (float bad : {nan_value, inf_value, -inf_value}) {
		expectRejected(controller.update(0, bad, 0.f, 0.01f), Status::InvalidInput);
		expectRejected(controller.update(0, 0.f, bad, 0.01f), Status::InvalidInput);
		EXPECT_FLOAT_EQ(controller.state()[0], 0.75f);
	}
	EXPECT_FLOAT_EQ(controller.state()[1], 0.f);
	EXPECT_FLOAT_EQ(controller.state()[2], 0.f);
}

TEST(StaRateControlTest, FiniteInputIntermediateOverflowIsAtomic)
{
	struct Case { Controller::Parameters p; float rate, sp, dt, nu; };
	const Case cases[] = {
		{{1.f, 1.f, 1.f}, huge, -huge, 0.01f, 0.f}, // s overflow
		{{huge, 1.f, 1.f}, 4.f, 0.f, 0.01f, 0.f}, // sqrt term overflow
		{{1.f, huge, 1.f}, 0.f, 0.f, 2.f, 0.5f}, // h*lambda2 even with sign(0)
		{{huge, 1.f, 1.f}, -1.f, 0.f, 0.01f, huge}, // a addition
		{{1.f, 1.f, std::numeric_limits<float>::min()}, 100.f, 0.f, 0.01f, 0.f}, // a/g
		{{1.f, huge, 1.f}, -1.f, 0.f, 1.f, huge}, // nu_next addition
	};

	for (const auto &test : cases) {
		Controller controller;
		ASSERT_TRUE(controller.setParameters(0, test.p));
		ASSERT_TRUE(controller.reset(0, test.nu));
		ASSERT_TRUE(controller.reset(1, 2.f));
		expectRejected(controller.update(0, test.rate, test.sp, test.dt), Status::NumericalError);
		EXPECT_FLOAT_EQ(controller.state()[0], test.nu);
		EXPECT_FLOAT_EQ(controller.state()[1], 2.f);
	}
}

TEST(StaRateControlTest, InputGainMapsOutputNotInternalState)
{
	for (float g : {0.5f, 1.f, 2.5f, 7.f}) {
		Controller controller;
		ASSERT_TRUE(controller.setParameters(0, {2.f, 4.f, g}));

		for (int k = 0; k < 64; ++k) {
			const auto out = controller.update(0, 1.f, 0.f, 0.125f);
			ASSERT_TRUE(out.valid());
			EXPECT_FLOAT_EQ(out.a, -2.f - static_cast<float>(k) * 0.5f);
			EXPECT_FLOAT_EQ(out.nu_next, -static_cast<float>(k + 1) * 0.5f);
			EXPECT_NEAR(static_cast<double>(out.c_raw) * static_cast<double>(g), static_cast<double>(out.a), 4e-6);
		}
	}
}

TEST(StaRateControlTest, FrozenIndependentDoubleSequence)
{
	Controller controller;
	ASSERT_TRUE(controller.reset(0, 0.375f));
	ASSERT_TRUE(controller.reset(1, -0.625f));
	ASSERT_TRUE(controller.reset(2, 1.25f));
	unsigned count = 0;

	for (const auto &row : reference_samples) {
		SCOPED_TRACE(count);
		ASSERT_TRUE(controller.setParameters(row.axis, {row.lambda1, row.lambda2, row.g}));
		EXPECT_DOUBLE_EQ(static_cast<double>(controller.state()[row.axis]), row.nu_old);
		const auto out = controller.update(row.axis, row.rate, row.sp, row.dt);
		ASSERT_TRUE(out.valid());
		EXPECT_DOUBLE_EQ(static_cast<double>(out.s), row.s);
		EXPECT_NEAR(static_cast<double>(out.a), row.a, 2e-6 * std::max(1.0, std::fabs(row.a)));
		EXPECT_NEAR(static_cast<double>(out.c_raw), row.c, 2e-6 * std::max(1.0, std::fabs(row.c)));
		EXPECT_DOUBLE_EQ(static_cast<double>(out.nu_next), row.nu_next);
		++count;
	}

	EXPECT_EQ(count, 96u);
}

TEST(StaRateControlTest, IndependentExactZohPlantAcrossGainsDisturbancesAndDt)
{
	// Synthetic, unsaturated scalar plant; these gains are NOT Iris/DP1000 calibration.
	// Before running: require entire final 2 s |rate-sp| < .02 rad/s,
	// float vs double tail RMSE difference < .003; no claim of exact ESTA sliding.
	for (float dt : {0.001f, 0.004f, 0.01f}) {
		for (float g : {0.5f, 2.5f, 7.f}) {
			for (int disturbance = 0; disturbance < 3; ++disturbance) {
				Controller controller;
				ASSERT_TRUE(controller.setParameters(0, {4.f, 2.f, g}));
				double rate = 1.0, reference_rate = 1.0, reference_nu = 0.0;
				double maximum = 0.0, reference_maximum = 0.0, squares = 0.0, reference_squares = 0.0;
				unsigned tail_count = 0;
				const double h = static_cast<double>(dt);
				const int steps = static_cast<int>(std::ceil(8.0 / h));

				for (int k = 0; k < steps; ++k) {
					const double t = static_cast<double>(k) * h;
					const double sp = disturbance == 2 ? 0.15 * std::sin(0.5 * t) : 0.0;
					const auto out = controller.update(0, static_cast<float>(rate), static_cast<float>(sp), dt);
					ASSERT_TRUE(out.valid());
					// Independent binary64 controller and independently evolved state.
					const double error = reference_rate - sp;
					const double sign = error > 0.0 ? 1.0 : (error < 0.0 ? -1.0 : 0.0);
					const double reference_a = reference_nu - 4.0 * sign * std::sqrt(std::fabs(error));
					reference_nu -= 2.0 * h * sign;
					// Exact integral of dot(rate)=g*c_ZOH+phi(t), not controller virtual prediction.
					const double impulse = disturbance == 0 ? 0.0 : (disturbance == 1 ? 0.4 * h :
							       0.4 / 0.7 * (std::cos(0.7 * t) - std::cos(0.7 * (t + h))));
					rate += h * static_cast<double>(g) * static_cast<double>(out.c_raw) + impulse;
					reference_rate += h * reference_a + impulse;
					ASSERT_TRUE(std::isfinite(rate));

					if (t >= 6.0) {
						const double next_sp = disturbance == 2 ? 0.15 * std::sin(0.5 * (t + h)) : 0.0;
						const double e = rate - next_sp;
						const double re = reference_rate - next_sp;
						maximum = std::max(maximum, std::fabs(e));
						reference_maximum = std::max(reference_maximum, std::fabs(re));
						squares += e * e;
						reference_squares += re * re;
						++tail_count;
					}
				}

				ASSERT_GT(tail_count, 0u);
				const double rmse = std::sqrt(squares / tail_count);
				const double reference_rmse = std::sqrt(reference_squares / tail_count);
				std::printf("plant dt=%.9g g=%.9g disturbance=%d samples=%d tail=%u max=%.9g double_max=%.9g rmse=%.9g double_rmse=%.9g\n",
					    h, static_cast<double>(g), disturbance, steps, tail_count, maximum, reference_maximum, rmse, reference_rmse);
				EXPECT_LT(maximum, 0.02);
				EXPECT_LT(reference_maximum, 0.02);
				EXPECT_NEAR(rmse, reference_rmse, 0.003);
			}
		}
	}
}
