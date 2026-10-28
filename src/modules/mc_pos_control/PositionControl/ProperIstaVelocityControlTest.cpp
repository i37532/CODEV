// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>
#include "ProperIstaVelocityControl.hpp"

#include <algorithm>
#include <cfenv>
#include <cmath>
#include <cstring>
#include <new>
#include <type_traits>
#if defined(__SSE__)
#include <xmmintrin.h>
#endif

namespace
{
using Kernel = ProperIstaVelocityControl;
using Status = Kernel::Status;
using Branch = Kernel::Branch;
constexpr float Nan = std::numeric_limits<float>::quiet_NaN();
constexpr float Inf = std::numeric_limits<float>::infinity();
constexpr float Tiny = std::numeric_limits<float>::denorm_min();
constexpr float Min = std::numeric_limits<float>::min();
constexpr float Max = std::numeric_limits<float>::max();
static_assert(!std::is_copy_constructible<Kernel>::value, "owner is stable");
static_assert(!std::is_copy_assignable<Kernel>::value, "owner is stable");
static_assert(!std::is_move_constructible<Kernel>::value, "owner is stable");
static_assert(!std::is_move_assignable<Kernel>::value, "owner is stable");

float fromBits(uint32_t bits)
{
	float value;
	std::memcpy(&value, &bits, sizeof(value));
	return value;
}

struct Reference { double z, xi, nu, output; };

// Independent monotonic implicit solve in z. No rationalized closed form.
Reference solve(double s, double old, double h, double l1, double l2)
{
	const double sign = s < 0.0 ? -1.0 : 1.0;
	double lo = 0.0, hi = std::fabs(s);

	for (unsigned iteration = 0; iteration < 1100; ++iteration) {
		const double mid = lo + (hi - lo) * .5;
		if (mid == lo || mid == hi) { break; }
		// Group the constant residual before bisection. Adding q to a tiny
		// root term and then subtracting s destroys boundary-neighbour bits.
		const double equation = mid + h * l1 * std::sqrt(mid) - (std::fabs(s) - h * h * l2);
		if (equation > 0.0) { hi = mid; } else { lo = mid; }
	}

	const double magnitude = lo + (hi - lo) * .5;
	const bool sliding = h * h * l2 >= std::fabs(s);
	const double z = sliding ? 0.0 : sign * magnitude;
	const double xi = sliding ? s / (h * h * l2) : sign;
	const double next = old - h * l2 * xi;
	return {z, xi, next, -l1 * std::sqrt(std::fabs(z)) * xi + 2.0 * next - old};
}

void checkReference(const Kernel::Candidate &c, const Kernel::Parameters &parameters)
{
	ASSERT_TRUE(c.valid());
	const auto reference = solve(c.s, c.nu_before, c.dt, parameters.lambda1, parameters.lambda2);
	const double scale = std::max({std::fabs(reference.output), std::fabs(reference.nu),
				      std::fabs(static_cast<double>(c.nu_before)), 1.e-300});
	const double tolerance = 8.0 * std::numeric_limits<float>::epsilon() * scale + 2.0 * Tiny;
	EXPECT_NEAR(c.a_sta, reference.output, tolerance);
	EXPECT_NEAR(c.nu_next, reference.nu, tolerance);
	EXPECT_NEAR(c.virtual_s, reference.z, 2.e-12 * std::max(std::fabs(reference.z), 1.e-300));
	EXPECT_NEAR(c.xi, reference.xi, 2.e-14);
}

class ProperVelocityTest : public ::testing::Test
{
protected:
	void SetUp() override
	{
		ASSERT_TRUE(Kernel::floatingPointEnvironmentSupported());
		for (size_t axis = 0; axis < 3; ++axis) { ASSERT_TRUE(core.setParameters(axis, parameters)); }
	}
	Kernel core;
	const Kernel::Parameters parameters{2.f, 1.f};
};
}

TEST_F(ProperVelocityTest, ThreeBranchesAndIndependentImplicitReference)
{
	for (float s : {-1.f, -.00001f, 0.f, .00001f, 1.f}) {
		const auto c = core.evaluate(0, s, 0.f, .01f);
		checkReference(c, parameters);
		EXPECT_EQ(c.branch, s < -.0001f ? Branch::Negative : s > .0001f ? Branch::Positive : Branch::Sliding);
	}
}

TEST_F(ProperVelocityTest, ExactBothBoundariesAndNextafterNeighbours)
{
	ASSERT_TRUE(core.setParameters(0, {3.f, 2.f}));
	constexpr float h = .125f, boundary = .03125f;
	for (float sign : {-1.f, 1.f}) {
		const float s = sign * boundary;
		const auto boundary_candidate = core.evaluate(0, s, 0.f, h);
		ASSERT_TRUE(boundary_candidate.valid());
		EXPECT_EQ(boundary_candidate.branch, Branch::Sliding);
		EXPECT_DOUBLE_EQ(boundary_candidate.xi, sign);
		EXPECT_DOUBLE_EQ(boundary_candidate.virtual_s, 0.0);
		const auto inner = core.evaluate(0, std::nextafter(s, 0.f), 0.f, h);
		const auto outer = core.evaluate(0, std::nextafter(s, sign * Inf), 0.f, h);
		ASSERT_TRUE(inner.valid()); ASSERT_TRUE(outer.valid());
		EXPECT_EQ(inner.branch, Branch::Sliding);
		EXPECT_EQ(outer.branch, sign > 0.f ? Branch::Positive : Branch::Negative);
		checkReference(outer, {3.f, 2.f});
	}
}

TEST_F(ProperVelocityTest, RepresentativeEightTwelveMillisecondBoundaries)
{
	for (float h : {.008f, .012f}) {
		const float q = static_cast<float>(static_cast<double>(h) * h);
		for (float s : {std::nextafter(q, 0.f), q, std::nextafter(q, Inf)}) {
			for (float sign : {-1.f, 1.f}) {
				const auto c = core.evaluate(0, sign * s, 0.f, h);
				ASSERT_TRUE(c.valid());
				EXPECT_EQ(c.branch == Branch::Sliding, static_cast<double>(s) <= static_cast<double>(h) * h);
				checkReference(c, parameters);
			}
		}
	}
}

TEST_F(ProperVelocityTest, SymmetricPositiveNegativeInputAndState)
{
	for (float s : {Tiny, 1.e-20f, .00003f, .3f, 30.f}) {
		ASSERT_TRUE(core.reset(0, .4f)); ASSERT_TRUE(core.reset(1, -.4f));
		const auto positive = core.evaluate(0, s, 0.f, .01f);
		const auto negative = core.evaluate(1, -s, 0.f, .01f);
		ASSERT_TRUE(positive.valid()); ASSERT_TRUE(negative.valid());
		EXPECT_FLOAT_EQ(positive.a_sta, -negative.a_sta);
		EXPECT_FLOAT_EQ(positive.nu_next, -negative.nu_next);
		EXPECT_DOUBLE_EQ(positive.virtual_s, -negative.virtual_s);
		EXPECT_DOUBLE_EQ(positive.xi, -negative.xi);
	}
}

TEST_F(ProperVelocityTest, ZeroErrorRetainsNonzeroStateAndOutput)
{
	ASSERT_TRUE(core.reset(0, .7f));
	const auto c = core.evaluate(0, 2.f, 2.f, .012f);
	ASSERT_TRUE(c.valid());
	EXPECT_FLOAT_EQ(c.nu_next, .7f); EXPECT_FLOAT_EQ(c.a_sta, .7f);
	EXPECT_DOUBLE_EQ(c.virtual_s, 0.0); EXPECT_DOUBLE_EQ(c.xi, 0.0);
	EXPECT_EQ(core.commit(c), Status::Ok); EXPECT_FLOAT_EQ(core.state()[0], .7f);
}

TEST_F(ProperVelocityTest, IdealOutputUsesCandidateTwiceNotOldStaRule)
{
	ASSERT_TRUE(core.reset(0, .25f));
	const auto c = core.evaluate(0, .003f, 0.f, .125f);
	ASSERT_TRUE(c.valid());
	EXPECT_EQ(c.branch, Branch::Sliding);
	EXPECT_NEAR(c.nu_next, .25 - .003f / .125, 1.e-8);
	EXPECT_NEAR(c.a_sta, .25 - 2.0 * .003f / .125, 1.e-8);
	EXPECT_NE(c.a_sta, c.nu_next);
}

TEST_F(ProperVelocityTest, EvaluateDoesNotChangeAnyAxis)
{
	ASSERT_TRUE(core.reset(0, .5f));
	const auto before = core.state();
	for (size_t axis = 0; axis < 3; ++axis) { ASSERT_TRUE(core.evaluate(axis, .1f, 0.f, .01f).valid()); }
	EXPECT_EQ(core.state(), before);
}

TEST_F(ProperVelocityTest, CommitOneAxisLeavesOthersAndCandidatesCurrent)
{
	const auto x = core.evaluate(0, .2f, 0.f, .01f);
	const auto y = core.evaluate(1, -.2f, 0.f, .01f);
	const auto z = core.evaluate(2, .3f, 0.f, .01f);
	ASSERT_EQ(core.commit(x), Status::Ok);
	EXPECT_FLOAT_EQ(core.state()[1], 0.f); EXPECT_FLOAT_EQ(core.state()[2], 0.f);
	EXPECT_TRUE(core.current(y)); EXPECT_TRUE(core.current(z));
	ASSERT_EQ(core.commit(y), Status::Ok); ASSERT_EQ(core.commit(z), Status::Ok);
	EXPECT_FLOAT_EQ(core.state()[1], y.nu_next); EXPECT_FLOAT_EQ(core.state()[2], z.nu_next);
}

TEST_F(ProperVelocityTest, DistinctParametersAndStatesPerAxis)
{
	for (size_t axis = 0; axis < 3; ++axis) {
		const Kernel::Parameters p{static_cast<float>(axis + 2), static_cast<float>(axis + 1)};
		ASSERT_TRUE(core.setParameters(axis, p)); ASSERT_TRUE(core.reset(axis, .1f * axis));
		const auto c = core.evaluate(axis, .2f, 0.f, .01f);
		checkReference(c, p);
		ASSERT_EQ(core.commit(c), Status::Ok);
	}
	EXPECT_NE(core.state()[0], core.state()[1]); EXPECT_NE(core.state()[1], core.state()[2]);
}

TEST_F(ProperVelocityTest, RepeatedCommitRejected)
{
	const auto c = core.evaluate(0, .2f, 0.f, .01f);
	ASSERT_EQ(core.commit(c), Status::Ok);
	const auto state = core.state();
	EXPECT_EQ(core.commit(c), Status::StaleCandidate); EXPECT_EQ(core.state(), state);
}

TEST_F(ProperVelocityTest, OlderSiblingCandidateRejectedAfterCommit)
{
	const auto first = core.evaluate(0, .2f, 0.f, .01f);
	const auto sibling = core.evaluate(0, .3f, 0.f, .01f);
	ASSERT_EQ(core.commit(first), Status::Ok);
	EXPECT_EQ(core.commit(sibling), Status::StaleCandidate);
}

TEST_F(ProperVelocityTest, CrossObjectCandidateRejected)
{
	Kernel other;
	ASSERT_TRUE(other.setParameters(0, parameters));
	EXPECT_EQ(other.commit(core.evaluate(0, .2f, 0.f, .01f)), Status::StaleCandidate);
	EXPECT_FLOAT_EQ(other.state()[0], 0.f);
}

TEST_F(ProperVelocityTest, AddressReuseCannotReviveCandidate)
{
	alignas(Kernel) unsigned char storage[sizeof(Kernel)];
	auto *first = new (storage) Kernel;
	ASSERT_TRUE(first->setParameters(0, parameters));
	const auto old = first->evaluate(0, .2f, 0.f, .01f);
	first->~Kernel();
	auto *second = new (storage) Kernel;
	ASSERT_TRUE(second->setParameters(0, parameters));
	EXPECT_EQ(second->commit(old), Status::StaleCandidate);
	second->~Kernel();
}

TEST_F(ProperVelocityTest, AxisTamperingRejected)
{
	auto c = core.evaluate(0, .2f, 0.f, .01f);
	c.axis = 1;
	EXPECT_EQ(core.commit(c), Status::StaleCandidate);
	c.axis = 3;
	EXPECT_EQ(core.commit(c), Status::InvalidAxis);
}

TEST_F(ProperVelocityTest, EveryPublicPayloadFieldSealed)
{
	const auto original = core.evaluate(0, .2f, 0.f, .01f);
	ASSERT_TRUE(original.valid());
	for (int field = 0; field < 12; ++field) {
		auto c = original;
		switch (field) {
		case 0: c.s = std::nextafter(c.s, Inf); break;
		case 1: c.a_sta = std::nextafter(c.a_sta, Inf); break;
		case 2: c.nu_before = Tiny; break;
		case 3: c.nu_next = std::nextafter(c.nu_next, Inf); break;
		case 4: c.dt = std::nextafter(c.dt, Inf); break;
		case 5: c.virtual_s = std::nextafter(c.virtual_s, static_cast<double>(Inf)); break;
		case 6: c.xi = std::nextafter(c.xi, 0.0); break;
		case 7: ++c.config_generation; break;
		case 8: ++c.reset_generation; break;
		case 9: ++c.state_generation; break;
		case 10: c.branch = Branch::Sliding; break;
		case 11: c.status = Status::NumericalError; break;
		}
		EXPECT_FALSE(core.current(c)) << field;
		EXPECT_NE(core.commit(c), Status::Ok) << field;
	}
	EXPECT_TRUE(core.current(original)); EXPECT_FLOAT_EQ(core.state()[0], 0.f);
}

TEST_F(ProperVelocityTest, SignedZeroPayloadTamperingDetected)
{
	auto c = core.evaluate(0, 0.f, 0.f, .01f);
	ASSERT_TRUE(c.valid());
	c.nu_before = -0.f;
	EXPECT_FALSE(core.current(c)); EXPECT_EQ(core.commit(c), Status::StaleCandidate);
}

TEST_F(ProperVelocityTest, DefaultOrForgedCandidateRejected)
{
	Kernel::Candidate c;
	EXPECT_EQ(core.commit(c), Status::Unconfigured);
	c.status = Status::Ok;
	EXPECT_EQ(core.commit(c), Status::StaleCandidate);
}

TEST_F(ProperVelocityTest, ConfigChangeInvalidatesOnlyOwnAxis)
{
	const auto x = core.evaluate(0, .2f, 0.f, .01f);
	const auto y = core.evaluate(1, .2f, 0.f, .01f);
	ASSERT_TRUE(core.setParameters(0, parameters));
	EXPECT_EQ(core.commit(x), Status::StaleCandidate); EXPECT_TRUE(core.current(y));
}

TEST_F(ProperVelocityTest, ResetInvalidatesWithoutDiscardingConfiguration)
{
	const auto c = core.evaluate(0, .2f, 0.f, .01f);
	ASSERT_TRUE(core.reset(0, -.4f));
	EXPECT_EQ(core.commit(c), Status::StaleCandidate);
	ASSERT_TRUE(core.evaluate(0, .2f, 0.f, .01f).valid());
	EXPECT_FLOAT_EQ(core.state()[0], -.4f);
}

TEST_F(ProperVelocityTest, AllAxisResetIsCompleteAndInvalidates)
{
	std::array<Kernel::Candidate, 3> candidates;
	for (size_t axis = 0; axis < 3; ++axis) {
		ASSERT_TRUE(core.reset(axis, .1f + axis));
		candidates[axis] = core.evaluate(axis, .2f, 0.f, .01f);
	}
	ASSERT_TRUE(core.reset());
	for (size_t axis = 0; axis < 3; ++axis) {
		EXPECT_FLOAT_EQ(core.state()[axis], 0.f);
		EXPECT_EQ(core.commit(candidates[axis]), Status::StaleCandidate);
		EXPECT_TRUE(core.evaluate(axis, .2f, 0.f, .01f).valid());
	}
}

TEST_F(ProperVelocityTest, InvalidParametersAreTransactional)
{
	const auto c = core.evaluate(0, .2f, 0.f, .01f);
	for (float invalid : {0.f, -1.f, Tiny, Nan, Inf}) {
		EXPECT_FALSE(core.setParameters(0, {invalid, 1.f}));
		EXPECT_FALSE(core.setParameters(0, {1.f, invalid}));
	}
	EXPECT_TRUE(core.current(c));
}

TEST_F(ProperVelocityTest, InvalidAxisAndUnconfiguredAreExplicit)
{
	Kernel empty;
	EXPECT_EQ(empty.evaluate(0, 0.f, 0.f, .01f).status, Status::Unconfigured);
	EXPECT_EQ(core.evaluate(3, 0.f, 0.f, .01f).status, Status::InvalidAxis);
	EXPECT_FALSE(core.setParameters(3, parameters)); EXPECT_FALSE(core.reset(3));
}

TEST_F(ProperVelocityTest, InvalidInputsNeverChangeState)
{
	const auto state = core.state();
	for (float invalid : {Nan, Inf, -Inf}) {
		EXPECT_EQ(core.evaluate(0, invalid, 0.f, .01f).status, Status::InvalidInput);
		EXPECT_EQ(core.evaluate(0, 0.f, invalid, .01f).status, Status::InvalidInput);
		EXPECT_FALSE(core.reset(0, invalid));
	}
	EXPECT_EQ(core.state(), state);
}

TEST_F(ProperVelocityTest, InvalidTimeNeverClamped)
{
	for (float invalid : {0.f, -0.01f, Tiny, Nan, Inf}) {
		EXPECT_EQ(core.evaluate(0, .1f, 0.f, invalid).status, Status::InvalidDt);
	}
}

TEST_F(ProperVelocityTest, TrueInputDifferenceOverflowRejected)
{
	EXPECT_EQ(core.evaluate(0, Max, -Max, .01f).status, Status::NumericalError);
}

TEST_F(ProperVelocityTest, TrueOutputOverflowRejectedNotClipped)
{
	ASSERT_TRUE(core.setParameters(0, {Max, 1.f}));
	EXPECT_EQ(core.evaluate(0, Max, 0.f, Min).status, Status::NumericalError);
	EXPECT_FLOAT_EQ(core.state()[0], 0.f);
}

TEST_F(ProperVelocityTest, Binary64PreventsFloatIntermediateOverflow)
{
	ASSERT_TRUE(core.setParameters(0, {1.e20f, 1.f}));
	const auto c = core.evaluate(0, .2f, 0.f, 1.f);
	ASSERT_TRUE(c.valid()); // q=1: sliding, despite float alpha^2 overflow.
	checkReference(c, {1.e20f, 1.f});
	const auto outer = core.evaluate(0, 2.f, 0.f, 1.f);
	ASSERT_TRUE(outer.valid()); EXPECT_GT(outer.virtual_s, 0.0);
	EXPECT_NEAR(outer.a_sta, -3.f, 1.e-6f);
}

TEST_F(ProperVelocityTest, RationalizedRootRetainsCancellationLostRoot)
{
	ASSERT_TRUE(core.setParameters(0, {1.e20f, 1.f}));
	const auto c = core.evaluate(0, .01f, 0.f, .01f);
	ASSERT_TRUE(c.valid()); EXPECT_GT(c.virtual_s, 0.0);
	const double alpha = static_cast<double>(.01f) * 1.e20f;
	const double delta = static_cast<double>(.01f) - static_cast<double>(.01f) * .01f;
	EXPECT_DOUBLE_EQ((std::sqrt(alpha * alpha + 4.0 * delta) - alpha) * .5, 0.0);
	checkReference(c, {1.e20f, 1.f});
}

TEST_F(ProperVelocityTest, DoubleDiagnosticsPreserveSubfloatVirtualError)
{
	ASSERT_TRUE(core.setParameters(0, {Max, Min}));
	const auto c = core.evaluate(0, Tiny, 0.f, .0001f);
	ASSERT_TRUE(c.valid()); EXPECT_EQ(c.branch, Branch::Positive);
	EXPECT_GT(c.virtual_s, 0.0); EXPECT_LT(c.virtual_s, static_cast<double>(Tiny));
	EXPECT_NE(c.a_sta, 0.f);
}

TEST_F(ProperVelocityTest, DoubleDiagnosticsPreserveSubfloatXi)
{
	ASSERT_TRUE(core.setParameters(0, {1.f, Max}));
	const auto c = core.evaluate(0, Tiny, 0.f, 1.f);
	ASSERT_TRUE(c.valid()); EXPECT_EQ(c.branch, Branch::Sliding);
	EXPECT_GT(c.xi, 0.0); EXPECT_LT(c.xi, static_cast<double>(Tiny));
	EXPECT_FLOAT_EQ(c.nu_next, -Tiny); EXPECT_FLOAT_EQ(c.a_sta, -2.f * Tiny);
}

TEST_F(ProperVelocityTest, FloatIntermediateUnderflowIsNotInputUnderflow)
{
	ASSERT_TRUE(core.setParameters(0, {Min, Min}));
	const auto c = core.evaluate(0, Tiny, 0.f, Min);
	ASSERT_TRUE(c.valid()); EXPECT_GT(c.virtual_s, 0.0);
	EXPECT_GT(c.xi, 0.0);
	EXPECT_EQ(core.commit(c), Status::Ok);
}

TEST_F(ProperVelocityTest, SubnormalResetCommitAndSubsequentEvaluate)
{
	ASSERT_TRUE(core.reset(0, Tiny));
	const auto c = core.evaluate(0, 0.f, 0.f, .01f);
	ASSERT_TRUE(c.valid()); EXPECT_FLOAT_EQ(c.a_sta, Tiny); EXPECT_FLOAT_EQ(c.nu_next, Tiny);
	ASSERT_EQ(core.commit(c), Status::Ok);
	const auto next = core.evaluate(0, Tiny, 0.f, .01f);
	ASSERT_TRUE(next.valid()); ASSERT_EQ(core.commit(next), Status::Ok);
	EXPECT_TRUE(core.reset(0, -Tiny));
}

TEST_F(ProperVelocityTest, UnderflowTiesRoundToEvenWithoutArtificialDeadzone)
{
	const auto half = core.evaluate(0, Tiny, 0.f, 2.f);
	ASSERT_TRUE(half.valid());
	EXPECT_EQ(std::fpclassify(half.nu_next), FP_ZERO);
	EXPECT_TRUE(std::signbit(half.nu_next)); // native IEEE -eta/2 -> -0
	EXPECT_FLOAT_EQ(half.a_sta, -Tiny);
	ASSERT_EQ(core.commit(half), Status::Ok);
	ASSERT_TRUE(core.reset(0));
	const auto one_and_half = core.evaluate(0, 3.f * Tiny, 0.f, 2.f);
	ASSERT_TRUE(one_and_half.valid());
	EXPECT_FLOAT_EQ(one_and_half.nu_next, -2.f * Tiny); // -1.5 eta -> -2 eta
	EXPECT_FLOAT_EQ(one_and_half.a_sta, -3.f * Tiny);
	ASSERT_EQ(core.commit(one_and_half), Status::Ok);
	EXPECT_FLOAT_EQ(core.state()[0], -2.f * Tiny);
}

TEST_F(ProperVelocityTest, ExactFourPV00StopsCompleteLifecycle)
{
	const uint32_t data[4][3] = {
		{0x024f9587u, 0x05cab325u, 0x3c03126fu},
		{0x8517f57bu, 0x886d6f93u, 0x3c23d70au},
		{0x862c062du, 0x895ffd56u, 0x3c449ba6u},
		{0x0072f289u, 0x0395abccu, 0x3c03126fu}
	};
	for (size_t row = 0; row < 4; ++row) {
		const float h = fromBits(data[row][2]);
		double physical_error = fromBits(data[row][0]);
		ASSERT_TRUE(core.reset(0, fromBits(data[row][1])));
		for (size_t step = 0; step < 128; ++step) {
			const auto c = core.evaluate(0, static_cast<float>(physical_error), 0.f, h);
			ASSERT_TRUE(c.valid()) << row << " step " << step;
			checkReference(c, parameters);
			ASSERT_EQ(core.commit(c), Status::Ok);
			physical_error += static_cast<double>(h) * c.a_sta; // independent physical integral
		}
		ASSERT_TRUE(core.reset(0, Tiny));
		ASSERT_TRUE(core.evaluate(0, Tiny, 0.f, h).valid());
	}
}

TEST_F(ProperVelocityTest, NormalDomainGridIndependentReference)
{
	for (const auto &p : {Kernel::Parameters{2.f, 1.f}, Kernel::Parameters{.3f, .08f}, Kernel::Parameters{5.f, 4.f}}) {
		ASSERT_TRUE(core.setParameters(0, p));
		for (float h : {.004f, .008f, .012f, .016f}) {
			for (float nu : {-.7f, 0.f, .3f}) {
				ASSERT_TRUE(core.reset(0, nu));
				for (float s : {-20.f, -.02f, -.00003f, 0.f, .00003f, .02f, 20.f}) {
					checkReference(core.evaluate(0, s, 0.f, h), p);
				}
			}
		}
	}
}

TEST_F(ProperVelocityTest, VariableTargetIsDifferenceNotHiddenFeedforward)
{
	const auto a = core.evaluate(0, 2.f, 1.5f, .012f);
	const auto b = core.evaluate(0, .5f, 0.f, .012f);
	ASSERT_TRUE(a.valid()); ASSERT_TRUE(b.valid());
	EXPECT_FLOAT_EQ(a.a_sta, b.a_sta); EXPECT_FLOAT_EQ(a.nu_next, b.nu_next);
	EXPECT_DOUBLE_EQ(a.virtual_s, b.virtual_s);
}

TEST_F(ProperVelocityTest, NonNearestRoundingRejectedWithoutMutation)
{
	const auto c = core.evaluate(0, .2f, 0.f, .01f);
	const int saved = std::fegetround();
	ASSERT_EQ(std::fesetround(FE_DOWNWARD), 0);
	EXPECT_FALSE(Kernel::floatingPointEnvironmentSupported());
	EXPECT_EQ(core.evaluate(0, .2f, 0.f, .01f).status, Status::UnsupportedEnvironment);
	EXPECT_EQ(core.commit(c), Status::UnsupportedEnvironment);
	EXPECT_FALSE(core.reset(0, Tiny)); EXPECT_FALSE(core.setParameters(0, parameters));
	EXPECT_EQ(std::fegetround(), FE_DOWNWARD);
	ASSERT_EQ(std::fesetround(saved), 0);
	EXPECT_TRUE(core.current(c));
}

#if defined(__SSE__)
TEST_F(ProperVelocityTest, FtzAndDazRejectedWithoutChangingHostFlags)
{
	const auto c = core.evaluate(0, .2f, 0.f, .01f);
	const unsigned saved = _mm_getcsr();
	for (unsigned bits : {0x8000u, 0x0040u, 0x8040u}) {
		_mm_setcsr(saved | bits);
		const unsigned before = _mm_getcsr();
		EXPECT_FALSE(Kernel::floatingPointEnvironmentSupported());
		EXPECT_EQ(core.evaluate(0, Tiny, 0.f, .01f).status, Status::UnsupportedEnvironment);
		EXPECT_EQ(core.commit(c), Status::UnsupportedEnvironment);
		EXPECT_FALSE(core.reset(0, Tiny));
		EXPECT_EQ(_mm_getcsr(), before);
		_mm_setcsr(saved);
	}
	EXPECT_TRUE(core.current(c));
}

TEST_F(ProperVelocityTest, SseOnlyRoundingRejectedEvenIfX87Nearest)
{
	const auto c = core.evaluate(0, .2f, 0.f, .01f);
	const unsigned saved = _mm_getcsr();
	for (unsigned rounding : {0x2000u, 0x4000u, 0x6000u}) {
		_mm_setcsr((saved & ~0x6000u) | rounding);
		const unsigned before = _mm_getcsr();
		EXPECT_FALSE(Kernel::floatingPointEnvironmentSupported());
		EXPECT_EQ(core.evaluate(0, Tiny, 0.f, .01f).status, Status::UnsupportedEnvironment);
		EXPECT_EQ(core.commit(c), Status::UnsupportedEnvironment);
		EXPECT_FALSE(core.reset(0, Tiny)); EXPECT_FALSE(core.setParameters(0, parameters));
		EXPECT_EQ(_mm_getcsr(), before);
		_mm_setcsr(saved);
	}
	EXPECT_TRUE(core.current(c));
}
#endif
