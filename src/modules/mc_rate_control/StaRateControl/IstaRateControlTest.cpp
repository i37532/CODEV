// SPDX-License-Identifier: BSD-3-Clause
#include "IstaRateControl.hpp"
#include "../RateControl/ControllerSelection.hpp"
#include <gtest/gtest.h>
#include <algorithm>
#include <cmath>
#include <limits>

namespace
{
using C = IstaRateControl;
constexpr float huge = std::numeric_limits<float>::max();
constexpr float tiny = std::numeric_limits<float>::min();
constexpr float nan_value = std::numeric_limits<float>::quiet_NaN();
constexpr float inf = std::numeric_limits<float>::infinity();

void rejected(const C::Result &r, C::Status status)
{
	EXPECT_FALSE(r.valid()); EXPECT_EQ(r.status, status); EXPECT_EQ(r.branch, C::Branch::Invalid);
	for (float x : {r.s, r.a, r.c_raw, r.nu_next, r.virtual_s, r.xi}) { EXPECT_TRUE(std::isnan(x)); }
}

void equations(const C::Result &r, float old, const C::Parameters &p, float dt)
{
	ASSERT_TRUE(r.valid());
	const double h = static_cast<double>(dt), a = static_cast<double>(r.a), s = static_cast<double>(r.s);
	const double nu = static_cast<double>(old), xi = static_cast<double>(r.xi);
	const double next = static_cast<double>(r.nu_next), v = static_cast<double>(r.virtual_s);
	const double l1 = static_cast<double>(p.lambda1), l2 = static_cast<double>(p.lambda2);
	const double scale = std::max({1e-30, std::fabs(s), std::fabs(h * a), std::fabs(v)});
	EXPECT_NEAR(v, s + h * a, 4e-7 * scale);
	EXPECT_NEAR(v, s + h * static_cast<double>(p.g) * static_cast<double>(r.c_raw), 5e-7 * scale);
	EXPECT_NEAR(next, nu - h * l2 * xi, 4e-7 * std::max({1e-30, std::fabs(nu), std::fabs(h * l2)}));
	EXPECT_NEAR(a, -l1 * std::sqrt(std::fabs(v)) * xi + next,
		    4e-7 * std::max({1e-30, std::fabs(a), std::fabs(next), l1 * std::sqrt(std::fabs(v))}));
	EXPECT_LE(std::fabs(r.xi), 1.f);
	if (r.branch != C::Branch::Sliding) { EXPECT_GT(r.virtual_s * r.xi, 0.f); }
}
}

TEST(IstaRateControlTest, UnconfiguredAndInvalidAxis)
{
	C c;
	rejected(c.update(0, 0.f, 0.f, .01f), C::Status::Unconfigured);
	for (size_t axis : {size_t{3}, std::numeric_limits<size_t>::max()}) {
		rejected(c.update(axis, 0.f, 0.f, .01f), C::Status::InvalidAxis);
		EXPECT_FALSE(c.setParameters(axis, {2.f, 1.f, 1.f})); EXPECT_FALSE(c.reset(axis));
	}
}

TEST(IstaRateControlTest, ExactBoundariesAndBothFloatNeighbours)
{
	const C::Parameters p{2.f, 4.f, 3.f};
	// h=1/8, q=1/16, nu=0: all exact binary values.
	for (float boundary : {-0.0625f, 0.0625f}) {
		for (float s : {std::nextafter(boundary, -inf), boundary, std::nextafter(boundary, inf)}) {
			C c; ASSERT_TRUE(c.setParameters(0, p));
			const auto r = c.update(0, s, 0.f, .125f);
			equations(r, 0.f, p, .125f);
			EXPECT_EQ(r.branch, std::fabs(s) <= .0625f ? C::Branch::Sliding :
				  (s > 0.f ? C::Branch::Positive : C::Branch::Negative));
			if (r.branch == C::Branch::Sliding) { EXPECT_FLOAT_EQ(r.virtual_s, 0.f); }
		}
	}
}

TEST(IstaRateControlTest, SlidingXiIntervalAndNonzeroNu)
{
	const C::Parameters p{3.f, 4.f, 2.f};
	for (int k = -64; k <= 64; ++k) {
		C c; ASSERT_TRUE(c.setParameters(0, p)); ASSERT_TRUE(c.reset(0, .25f));
		const float s = static_cast<float>(k) / 1024.f - .03125f;
		const auto r = c.update(0, s, 0.f, .125f);
		equations(r, .25f, p, .125f);
		EXPECT_EQ(r.branch, C::Branch::Sliding);
		EXPECT_FLOAT_EQ(r.xi, static_cast<float>(k) / 64.f);
		EXPECT_FLOAT_EQ(r.nu_next, -s / .125f);
	}
}

TEST(IstaRateControlTest, ThreeEquationsNonUnitGainAndSymmetry)
{
	for (float g : {.5f, 1.f, 7.f, 130.575283f}) {
		const C::Parameters p{2.2f, .05f, g};
		C pos, neg; ASSERT_TRUE(pos.setParameters(0, p)); ASSERT_TRUE(neg.setParameters(0, p));
		ASSERT_TRUE(pos.reset(0, .375f)); ASSERT_TRUE(neg.reset(0, -.375f));
		for (int k = 0; k < 256; ++k) {
			const float rate = static_cast<float>(k) / 256.f;
			const float old = pos.state()[0];
			const auto a = pos.update(0, rate, .5f, .004f);
			const auto b = neg.update(0, -rate, -.5f, .004f);
			equations(a, old, p, .004f); ASSERT_TRUE(b.valid());
			EXPECT_FLOAT_EQ(a.a, -b.a); EXPECT_FLOAT_EQ(a.nu_next, -b.nu_next);
			EXPECT_FLOAT_EQ(a.virtual_s, -b.virtual_s); EXPECT_FLOAT_EQ(a.xi, -b.xi);
		}
	}
}

TEST(IstaRateControlTest, ZeroStateAndZeroErrorWithNonzeroMemory)
{
	C c; ASSERT_TRUE(c.setParameters(0, {2.f, 4.f, 2.f}));
	const auto zero = c.update(0, 1.f, 1.f, .125f);
	ASSERT_TRUE(zero.valid()); EXPECT_FLOAT_EQ(zero.a, 0.f); EXPECT_FLOAT_EQ(zero.xi, 0.f);
	ASSERT_TRUE(c.reset(0, .25f));
	const auto r = c.update(0, 0.f, 0.f, .125f);
	ASSERT_TRUE(r.valid()); EXPECT_FLOAT_EQ(r.a, 0.f); EXPECT_FLOAT_EQ(r.nu_next, 0.f);
	EXPECT_FLOAT_EQ(r.xi, .5f); // NOT ESTA's sign(0)=0 / retained old nu behavior.
}

TEST(IstaRateControlTest, IndependentAxesResetAndInstances)
{
	C c, other;
	for (size_t i = 0; i < 3; ++i) {
		ASSERT_TRUE(c.setParameters(i, {2.f, static_cast<float>(i + 1), 3.f}));
		ASSERT_TRUE(c.reset(i, static_cast<float>(i + 1)));
	}
	ASSERT_TRUE(c.update(1, 2.f, 0.f, .125f).valid());
	EXPECT_FLOAT_EQ(c.state()[0], 1.f); EXPECT_FLOAT_EQ(c.state()[2], 3.f);
	EXPECT_FLOAT_EQ(c.state()[1], 1.75f);
	ASSERT_TRUE(c.reset(1)); EXPECT_FLOAT_EQ(c.state()[1], 0.f); EXPECT_FLOAT_EQ(c.state()[2], 3.f);
	for (float bad : {nan_value, inf, -inf}) { EXPECT_FALSE(c.reset(2, bad)); EXPECT_FLOAT_EQ(c.state()[2], 3.f); }
	for (float x : other.state()) { EXPECT_FLOAT_EQ(x, 0.f); }
	c.reset();
	for (size_t i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(c.state()[i], 0.f); ASSERT_TRUE(c.update(i, 0.f, 0.f, .1f).valid()); }
}

TEST(IstaRateControlTest, InvalidParametersAtomicAndValidUpdatePreservesState)
{
	C c; const C::Parameters good{2.f, 4.f, 2.f};
	ASSERT_TRUE(c.setParameters(0, good)); ASSERT_TRUE(c.reset(0, .25f));
	for (float bad : {0.f, -1.f, nan_value, inf, -inf, std::numeric_limits<float>::denorm_min()}) {
		for (int field = 0; field < 3; ++field) {
			auto p = good;
			if (field == 0) { p.lambda1 = bad; }
			if (field == 1) { p.lambda2 = bad; }
			if (field == 2) { p.g = bad; }
			EXPECT_FALSE(C::validParameters(p)); EXPECT_FALSE(c.setParameters(0, p));
			EXPECT_FLOAT_EQ(c.state()[0], .25f);
		}
	}
	ASSERT_TRUE(c.setParameters(0, {3.f, 8.f, 7.f})); EXPECT_FLOAT_EQ(c.state()[0], .25f);
	const auto r = c.update(0, 1.f, 0.f, .125f); ASSERT_TRUE(r.valid()); EXPECT_FLOAT_EQ(r.nu_next, -.75f);
}

TEST(IstaRateControlTest, InvalidInputsAndTimeAreAtomic)
{
	C c; ASSERT_TRUE(c.setParameters(0, {2.f, 1.f, 1.f})); ASSERT_TRUE(c.reset(0, .25f));
	for (float bad : {0.f, -1.f, nan_value, inf, -inf, std::numeric_limits<float>::denorm_min()}) {
		rejected(c.update(0, 1.f, 0.f, bad), C::Status::InvalidDt);
	}
	for (float bad : {nan_value, inf, -inf}) {
		rejected(c.update(0, bad, 0.f, .1f), C::Status::InvalidInput);
		rejected(c.update(0, 0.f, bad, .1f), C::Status::InvalidInput);
	}
	EXPECT_FLOAT_EQ(c.state()[0], .25f);
}

TEST(IstaRateControlTest, RationalizedRootRetainsBoundaryNeighbour)
{
	C c; ASSERT_TRUE(c.setParameters(0, {16.f, 1.f, 1.f}));
	const float s = std::nextafter(1.f, inf);
	const float naive = (std::sqrt(256.f + 4.f * (s - 1.f)) - 16.f) * .5f;
	EXPECT_FLOAT_EQ(naive, 0.f);
	const auto r = c.update(0, s, 0.f, 1.f);
	ASSERT_TRUE(r.valid()); EXPECT_GT(r.virtual_s, 0.f);
	const double delta = static_cast<double>(s) - 1.0;
	// Bound without using the production quadratic formula: r <= delta/alpha.
	EXPECT_NEAR(static_cast<double>(r.virtual_s), (delta / 16.0) * (delta / 16.0), 1e-23);
	equations(r, 0.f, {16.f, 1.f, 1.f}, 1.f);
}

TEST(IstaRateControlTest, DoubleProductsAvoidFloatQUnderflowAndDiscriminantOverflow)
{
	C c; ASSERT_TRUE(c.setParameters(0, {tiny, tiny, 1.f}));
	EXPECT_FLOAT_EQ(tiny * tiny, 0.f);
	const auto zero = c.update(0, 0.f, 0.f, tiny);
	ASSERT_TRUE(zero.valid()); EXPECT_EQ(zero.branch, C::Branch::Sliding); EXPECT_FLOAT_EQ(zero.xi, 0.f);
	ASSERT_TRUE(c.setParameters(0, {1.f, 1e-20f, 1.f}));
	const auto small_q = c.update(0, .25f, 0.f, 1e-15f);
	equations(small_q, 0.f, {1.f, 1e-20f, 1.f}, 1e-15f);
	EXPECT_LT(small_q.nu_next, 0.f);
	c.reset();
	ASSERT_TRUE(c.setParameters(0, {1e20f, 1.f, 1.f}));
	const auto wide = c.update(0, 1e20f, 0.f, 1.f);
	ASSERT_TRUE(wide.valid()); EXPECT_EQ(wide.branch, C::Branch::Positive);
	EXPECT_NEAR(static_cast<double>(wide.virtual_s), 1.0, 2e-6);
	equations(wide, 0.f, {1e20f, 1.f, 1.f}, 1.f);
}

TEST(IstaRateControlTest, UnrepresentableOutputsRejectWithoutPartialCommit)
{
	struct Case { C::Parameters p; float rate, sp, dt, nu; };
	const Case cases[] = {
		{{2.f, 1.f, 1.f}, huge, -huge, .1f, .25f}, // s overflow
		{{2.f, 1.f, tiny}, 100.f, 0.f, .1f, .25f}, // command overflow
		{{tiny, tiny, huge}, 1.f, 0.f, 1.f, 0.f}, // command underflow
		{{huge, 1.f, 1.f}, 2.f, 0.f, 1.f, 0.f}, // virtual_s underflow
		{{1.f, 1.f, 1.f}, std::numeric_limits<float>::denorm_min(), 0.f, tiny, 0.f}, // subnormal s
		{{1.f, huge, 1.f}, -huge, 0.f, .5f, huge}, // nu_next overflow
		{{huge, 1.f, huge}, -huge, 0.f, 1e-20f, 0.f}, // acceleration overflow
		{{tiny, tiny, 1.f}, huge, 0.f, 2.f, huge}, // virtual state overflow
		{{1e30f, 1.f, 1.f}, 2.f, 0.f, 1.f, 1e30f}, // even double loses equation consistency
	};
	for (const auto &t : cases) {
		C c; ASSERT_TRUE(c.setParameters(0, t.p)); ASSERT_TRUE(c.reset(0, t.nu)); ASSERT_TRUE(c.reset(1, 2.f));
		rejected(c.update(0, t.rate, t.sp, t.dt), C::Status::NumericalError);
		EXPECT_FLOAT_EQ(c.state()[0], t.nu); EXPECT_FLOAT_EQ(c.state()[1], 2.f);
	}
}

TEST(IstaRateControlTest, ConstraintsInvalidateIdealPredictionNotKernelEquations)
{
	C c; const C::Parameters p{10.f, 6.f, 2.f}; ASSERT_TRUE(c.setParameters(0, p));
	const auto r = c.update(0, 5.f, 0.f, .01f); equations(r, 0.f, p, .01f);
	const float applied = std::max(-.1f, std::min(.1f, r.c_raw));
	const float actual_next = 5.f + .01f * p.g * applied;
	EXPECT_GT(std::fabs(actual_next - r.virtual_s), .1f);
	// No saturation/nu freeze is secretly applied by this ideal kernel.
	EXPECT_LT(r.c_raw, -.1f); EXPECT_FLOAT_EQ(c.state()[0], r.nu_next);
}

TEST(IstaRateControlTest, ModeTwoStillRejectedFromPidAndEstaAllMasks)
{
	for (int axes : {0, 1, 3, 7}) {
		for (bool armed : {false, true}) {
			ControllerSelection pid, esta;
			esta.select(1, 7, false, true);
			pid.select(2, axes, armed, true); esta.select(2, axes, armed, true);
			EXPECT_EQ(pid.status().request_status, ControllerSelection::Unsupported);
			EXPECT_EQ(esta.status().request_status, ControllerSelection::Unsupported);
			EXPECT_EQ(pid.status().effective_mode, ControllerSelection::PID);
			EXPECT_EQ(esta.status().effective_mode, ControllerSelection::ESTA);
			EXPECT_EQ(esta.status().effective_axes, 7);
		}
	}
}
