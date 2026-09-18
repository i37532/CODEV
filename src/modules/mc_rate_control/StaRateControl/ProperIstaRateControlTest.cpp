// SPDX-License-Identifier: BSD-3-Clause
#include "ProperIstaRateControl.hpp"
#include "../RateControl/ControllerSelection.hpp"
#include <gtest/gtest.h>
#include <algorithm>
#include <cmath>

namespace
{
using C = ProperIstaRateControl;
constexpr float huge = std::numeric_limits<float>::max();
constexpr float tiny = std::numeric_limits<float>::min();
constexpr float subnormal = std::numeric_limits<float>::denorm_min();
constexpr float infinity = std::numeric_limits<float>::infinity();
constexpr float nan_value = std::numeric_limits<float>::quiet_NaN();

void rejected(const C::Result &r, C::Status status)
{
	EXPECT_FALSE(r.valid()); EXPECT_EQ(r.status, status); EXPECT_EQ(r.branch, C::Branch::Invalid);
	for (float x : {r.s, r.a, r.c_raw, r.nu_next, r.virtual_s, r.xi}) { EXPECT_TRUE(std::isnan(x)); }
}

void nearEquation(double lhs, double x, double y, double z = 0.0)
{
	EXPECT_NEAR(lhs, x + y + z, 8.0 * static_cast<double>(std::numeric_limits<float>::epsilon()) *
		    std::max({std::fabs(lhs), std::fabs(x), std::fabs(y), std::fabs(z)}));
}

void equations(const C::Result &r, float old, const C::Parameters &p, float dt)
{
	ASSERT_TRUE(r.valid());
	const double s = r.s, a = r.a, n = r.nu_next, h = dt, z = r.virtual_s, xi = r.xi;
	nearEquation(z, s, h * a, -h * n);
	nearEquation(z, s, h * static_cast<double>(p.g) * static_cast<double>(r.c_raw), -h * n);
	nearEquation(n, static_cast<double>(old), -h * static_cast<double>(p.lambda2) * xi);
	nearEquation(a, -static_cast<double>(p.lambda1) * std::sqrt(std::fabs(z)) * xi, 2.0 * n, -static_cast<double>(old));
	EXPECT_LE(std::fabs(xi), 1.0);
	if (r.branch != C::Branch::Sliding) { EXPECT_GT(z * xi, 0.0); }
}
}

TEST(ProperIstaRateControlTest, UnconfiguredAndInvalidAxis)
{
	C c;
	rejected(c.update(0, 0.f, 0.f, .004f), C::Status::Unconfigured);
	for (size_t axis : {size_t{3}, std::numeric_limits<size_t>::max()}) {
		rejected(c.update(axis, 0.f, 0.f, .004f), C::Status::InvalidAxis);
		EXPECT_FALSE(c.setParameters(axis, {2.f, 1.f, 1.f})); EXPECT_FALSE(c.reset(axis));
	}
	C::Candidate empty; EXPECT_FALSE(c.commit(empty));
}

TEST(ProperIstaRateControlTest, ExactBoundariesAndBothNeighboursIndependentOfNu)
{
	const C::Parameters p{2.f, 4.f, 3.f}; // q=1/16 at h=1/8
	for (float nu : {-2.f, 0.f, 2.f}) {
		for (float boundary : {-.0625f, .0625f}) {
			for (float s : {std::nextafter(boundary, -infinity), boundary, std::nextafter(boundary, infinity)}) {
				C c; ASSERT_TRUE(c.setParameters(0, p)); ASSERT_TRUE(c.reset(0, nu));
				const auto r = c.update(0, s, 0.f, .125f); equations(r, nu, p, .125f);
				EXPECT_EQ(r.branch, std::fabs(s) <= .0625f ? C::Branch::Sliding :
					  (s > 0.f ? C::Branch::Positive : C::Branch::Negative));
			}
		}
	}
}

TEST(ProperIstaRateControlTest, SlidingXiAndNonzeroMemory)
{
	const C::Parameters p{3.f, 4.f, 2.f};
	for (int k = -64; k <= 64; ++k) {
		C c; ASSERT_TRUE(c.setParameters(0, p)); ASSERT_TRUE(c.reset(0, .25f));
		const float s = static_cast<float>(k) / 1024.f;
		const auto r = c.update(0, s, 0.f, .125f); equations(r, .25f, p, .125f);
		EXPECT_EQ(r.branch, C::Branch::Sliding); EXPECT_FLOAT_EQ(r.xi, static_cast<float>(k) / 64.f);
		EXPECT_FLOAT_EQ(r.nu_next, .25f - s / .125f); EXPECT_FLOAT_EQ(r.a, .25f - 2.f * s / .125f);
	}
}

TEST(ProperIstaRateControlTest, ZeroErrorRetainsDisturbanceCompensation)
{
	C c; ASSERT_TRUE(c.setParameters(0, {2.f, 4.f, 2.f}));
	const auto zero = c.update(0, 1.f, 1.f, .125f);
	ASSERT_TRUE(zero.valid()); EXPECT_FLOAT_EQ(zero.a, 0.f);
	ASSERT_TRUE(c.reset(0, .25f));
	const auto r = c.update(0, 1.f, 1.f, .125f);
	ASSERT_TRUE(r.valid()); EXPECT_FLOAT_EQ(r.a, .25f); EXPECT_FLOAT_EQ(r.nu_next, .25f);
	EXPECT_FLOAT_EQ(r.xi, 0.f); EXPECT_FLOAT_EQ(r.c_raw, .125f);
}

TEST(ProperIstaRateControlTest, SymmetryNonUnitMappingAndRateDifference)
{
	for (float g : {.5f, 1.f, 7.f, 112.763533f}) {
		const C::Parameters p{2.4f, .08f, g}; C pos, neg;
		ASSERT_TRUE(pos.setParameters(0, p)); ASSERT_TRUE(neg.setParameters(0, p));
		ASSERT_TRUE(pos.reset(0, .375f)); ASSERT_TRUE(neg.reset(0, -.375f));
		for (int k = 0; k < 256; ++k) {
			const float rate = static_cast<float>(k) / 256.f, old = pos.state()[0];
			const auto a = pos.update(0, rate, .5f, .004f), b = neg.update(0, -rate, -.5f, .004f);
			equations(a, old, p, .004f); ASSERT_TRUE(b.valid());
			EXPECT_FLOAT_EQ(a.s, rate - .5f); EXPECT_FLOAT_EQ(a.a, -b.a);
			EXPECT_FLOAT_EQ(a.c_raw, -b.c_raw); EXPECT_FLOAT_EQ(a.nu_next, -b.nu_next);
			EXPECT_FLOAT_EQ(a.virtual_s, -b.virtual_s); EXPECT_FLOAT_EQ(a.xi, -b.xi);
		}
	}
}

TEST(ProperIstaRateControlTest, CandidateIsReadOnlyAndCommittedExactlyOnce)
{
	C c, other; ASSERT_TRUE(c.setParameters(0, {2.f, 4.f, 1.f}));
	const auto a = c.evaluate(0, 1.f, 0.f, .125f), b = c.evaluate(0, -1.f, 0.f, .125f);
	ASSERT_TRUE(a.result().valid()); EXPECT_FLOAT_EQ(c.state()[0], 0.f);
	EXPECT_FALSE(other.commit(a)); ASSERT_TRUE(c.commit(a));
	EXPECT_FLOAT_EQ(c.state()[0], -.5f); EXPECT_FALSE(c.commit(a)); EXPECT_FALSE(c.commit(b));
	EXPECT_FLOAT_EQ(c.state()[0], -.5f);
}

TEST(ProperIstaRateControlTest, ResetAndParametersInvalidateCandidatesAtomically)
{
	C c; const C::Parameters p{2.f, 4.f, 1.f}; ASSERT_TRUE(c.setParameters(0, p));
	const auto a = c.evaluate(0, 1.f, 0.f, .125f); ASSERT_TRUE(c.reset(0)); EXPECT_FALSE(c.commit(a));
	const auto b = c.evaluate(0, 1.f, 0.f, .125f); ASSERT_TRUE(c.setParameters(0, p)); EXPECT_FALSE(c.commit(b));
	const auto valid = c.evaluate(0, 1.f, 0.f, .125f);
	EXPECT_FALSE(c.setParameters(0, {0.f, 1.f, 1.f})); EXPECT_FALSE(c.reset(0, nan_value));
	ASSERT_TRUE(c.commit(valid)); // rejected operations did not invalidate the valid state
	const auto pending = c.evaluate(0, 1.f, 0.f, .125f); c.reset(); EXPECT_FALSE(c.commit(pending));
}

TEST(ProperIstaRateControlTest, ThreeAxesAndInstancesDoNotShareState)
{
	C c, other;
	for (size_t i = 0; i < 3; ++i) { ASSERT_TRUE(c.setParameters(i, {2.f, static_cast<float>(i + 1), 3.f})); }
	const auto roll = c.evaluate(0, 1.f, 0.f, .125f);
	ASSERT_TRUE(c.reset(1, 2.f)); ASSERT_TRUE(c.update(1, 2.f, 0.f, .125f).valid());
	ASSERT_TRUE(c.commit(roll)); // other-axis change does not invalidate roll
	EXPECT_FLOAT_EQ(c.state()[0], -.125f); EXPECT_FLOAT_EQ(c.state()[1], 1.75f); EXPECT_FLOAT_EQ(c.state()[2], 0.f);
	for (float x : other.state()) { EXPECT_FLOAT_EQ(x, 0.f); }
	for (int k = 0; k < 3; ++k) {
		c.reset();
		for (size_t i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(c.state()[i], 0.f); ASSERT_TRUE(c.update(i, 0.f, 0.f, .004f).valid()); }
	}
}

TEST(ProperIstaRateControlTest, InvalidParametersAndResetLeaveStateIntact)
{
	C c; const C::Parameters good{2.f, 4.f, 2.f}; ASSERT_TRUE(c.setParameters(0, good)); ASSERT_TRUE(c.reset(0, .25f));
	for (float bad : {0.f, -1.f, nan_value, infinity, -infinity, subnormal}) {
		for (int field = 0; field < 3; ++field) {
			auto p = good;
			if (field == 0) { p.lambda1 = bad; } if (field == 1) { p.lambda2 = bad; } if (field == 2) { p.g = bad; }
			EXPECT_FALSE(C::validParameters(p)); EXPECT_FALSE(c.setParameters(0, p)); EXPECT_FLOAT_EQ(c.state()[0], .25f);
		}
	}
	for (float bad : {nan_value, infinity, -infinity, subnormal}) { EXPECT_FALSE(c.reset(0, bad)); }
	ASSERT_TRUE(c.setParameters(0, {3.f, 8.f, 7.f})); EXPECT_FLOAT_EQ(c.state()[0], .25f);
}

TEST(ProperIstaRateControlTest, InvalidInputAndDtCannotCommit)
{
	C c; ASSERT_TRUE(c.setParameters(0, {2.f, 1.f, 1.f})); ASSERT_TRUE(c.reset(0, .25f));
	for (float bad : {0.f, -1.f, nan_value, infinity, -infinity, subnormal}) {
		const auto candidate = c.evaluate(0, 1.f, 0.f, bad);
		rejected(candidate.result(), C::Status::InvalidDt); EXPECT_FALSE(c.commit(candidate));
	}
	for (float bad : {nan_value, infinity, -infinity}) {
		rejected(c.update(0, bad, 0.f, .1f), C::Status::InvalidInput);
		rejected(c.update(0, 0.f, bad, .1f), C::Status::InvalidInput);
	}
	EXPECT_FLOAT_EQ(c.state()[0], .25f);
}

TEST(ProperIstaRateControlTest, RationalizedRootPreservesSmallBoundaryNeighbour)
{
	C c; ASSERT_TRUE(c.setParameters(0, {16.f, 1.f, 1.f}));
	const float s = std::nextafter(1.f, infinity);
	EXPECT_FLOAT_EQ((std::sqrt(256.f + 4.f * (s - 1.f)) - 16.f) * .5f, 0.f);
	const auto r = c.update(0, s, 0.f, 1.f); equations(r, 0.f, {16.f, 1.f, 1.f}, 1.f);
	EXPECT_GT(r.virtual_s, 0.f);
	const double upper = (static_cast<double>(s) - 1.0) / 16.0;
	EXPECT_NEAR(static_cast<double>(r.virtual_s), upper * upper, 1e-23);
}

TEST(ProperIstaRateControlTest, DoubleProductsAvoidFloatUnderflowAndOverflow)
{
	C c; ASSERT_TRUE(c.setParameters(0, {tiny, tiny, 1.f}));
	EXPECT_FLOAT_EQ(tiny * tiny, 0.f); ASSERT_TRUE(c.update(0, 0.f, 0.f, tiny).valid());
	ASSERT_TRUE(c.setParameters(0, {1.f, 1e-20f, 1.f}));
	equations(c.update(0, .25f, 0.f, 1e-15f), 0.f, {1.f, 1e-20f, 1.f}, 1e-15f);
	c.reset(); ASSERT_TRUE(c.setParameters(0, {1e20f, 1.f, 1.f}));
	const auto r = c.update(0, 1e20f, 0.f, 1.f); equations(r, 0.f, {1e20f, 1.f, 1.f}, 1.f);
	EXPECT_NEAR(static_cast<double>(r.virtual_s), 1.0, 2e-6);
}

TEST(ProperIstaRateControlTest, UnrepresentableResultsRejectWithoutPartialState)
{
	struct Case { C::Parameters p; float s, sp, h, nu; };
	const Case cases[] = {
		{{2.f, 1.f, 1.f}, huge, -huge, .1f, .25f},
		{{2.f, 1.f, tiny}, 100.f, 0.f, .1f, .25f},
		{{tiny, tiny, huge}, 1.f, 0.f, 1.f, 0.f},
		{{huge, 1.f, 1.f}, 2.f, 0.f, 1.f, 0.f},
		{{1.f, 1.f, 1.f}, subnormal, 0.f, tiny, 0.f},
		{{1.f, huge, 1.f}, -huge, 0.f, .5f, huge},
		{{huge, 1.f, huge}, -huge, 0.f, 1e-20f, 0.f},
	};
	for (const auto &v : cases) {
		C c; ASSERT_TRUE(c.setParameters(0, v.p)); ASSERT_TRUE(c.reset(0, v.nu));
		rejected(c.update(0, v.s, v.sp, v.h), C::Status::NumericalError); EXPECT_FLOAT_EQ(c.state()[0], v.nu);
	}
}

TEST(ProperIstaRateControlTest, ConstantDisturbanceHasZeroErrorEquilibrium)
{
	for (float h : {.004f, .008f, .016f}) {
		for (float d : {-.5f, 0.f, .5f}) {
			C c; ASSERT_TRUE(c.setParameters(0, {2.4f, .08f, 2.f})); ASSERT_TRUE(c.reset(0, -d));
			for (int k = 0; k < 32; ++k) {
				const auto r = c.update(0, 0.f, 0.f, h); ASSERT_TRUE(r.valid());
				EXPECT_FLOAT_EQ(r.a, -d); EXPECT_FLOAT_EQ(r.nu_next, -d);
				EXPECT_FLOAT_EQ(h * (2.f * r.c_raw + d), 0.f);
			}
		}
	}
}

TEST(ProperIstaRateControlTest, VariableDtIsNumericallyValidNotATheorem)
{
	C c; const C::Parameters p{2.4f, .08f, 112.763533f}; ASSERT_TRUE(c.setParameters(0, p));
	for (float h : {.004f, .009f, .002f, .016f, .001f, .125f}) {
		const float old = c.state()[0]; equations(c.update(0, .1f, .2f, h), old, p, h);
	}
}

TEST(ProperIstaRateControlTest, RuntimeHasNoNewModeEvenWithBothOldCapabilities)
{
	for (int mode : {0, 1, 2}) {
		for (int axes : {1, 3, 7}) {
			ControllerSelection selector;
			selector.select(mode, axes, false, true, true);
			ASSERT_EQ(selector.status().effective_mode, mode);
			for (bool armed : {false, true}) {
				for (int unsupported : {3, 4, 255, 256}) {
					selector.select(unsupported, axes, armed, true, true);
					EXPECT_EQ(selector.status().request_status, ControllerSelection::InvalidMode);
					EXPECT_EQ(selector.status().effective_mode, mode);
				}
			}
		}
	}
}
