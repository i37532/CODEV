// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>

#include "RegularizedIstaVelocityControl.hpp"
#include "VelocityControlSelector.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <new>
#include <type_traits>

namespace
{
using Kernel = RegularizedIstaVelocityControl;
using Status = Kernel::Status;
using Branch = Kernel::Branch;
constexpr float NaN = std::numeric_limits<float>::quiet_NaN();
constexpr float Inf = std::numeric_limits<float>::infinity();
constexpr float Min = std::numeric_limits<float>::min();
constexpr float Tiny = std::numeric_limits<float>::denorm_min();
constexpr float Max = std::numeric_limits<float>::max();

static_assert(!std::is_copy_constructible<Kernel>::value, "Candidate ownership forbids copying a controller");
static_assert(!std::is_copy_assignable<Kernel>::value, "Candidate ownership forbids copy assignment");
static_assert(!std::is_move_constructible<Kernel>::value, "Candidate ownership forbids moving a controller");
static_assert(!std::is_move_assignable<Kernel>::value, "Candidate ownership forbids move assignment");

struct Reference {
	double p;
	double rho;
	double psi;
	double next;
	double output;
};

double rho(double p, double epsilon)
{
	return std::max(-1., std::min(1., p / epsilon));
}

double psi(double p, double epsilon)
{
	return std::sqrt(std::max(std::fabs(p), epsilon)) * rho(p, epsilon);
}

// Independently solve the monotonic implicit equation by bracketing/bisection.
// No inner/outer analytical solution or implementation root helper is reused.
Reference reference(const Kernel::Parameters &parameters, double s, double nu, float h_float)
{
	const double h = static_cast<double>(h_float);
	const double epsilon = static_cast<double>(parameters.epsilon);
	const double lambda1 = static_cast<double>(parameters.lambda1);
	const double lambda2 = static_cast<double>(parameters.lambda2);
	const double sign = s < 0. ? -1. : 1.;
	double low = 0.;
	double high = std::fabs(s);

	for (int iteration = 0; iteration < 160; ++iteration) {
		const double middle = low + (high - low) * .5;
		const double residual = middle + h * lambda1 * psi(middle, epsilon)
					+ h * h * lambda2 * rho(middle, epsilon) - std::fabs(s);

		if (residual > 0.) {
			high = middle;

		} else {
			low = middle;
		}
	}

	const double predicted = sign * (low + (high - low) * .5);
	const double predicted_rho = rho(predicted, epsilon);
	const double predicted_psi = psi(predicted, epsilon);
	const double next = nu - h * lambda2 * predicted_rho;
	return {predicted, predicted_rho, predicted_psi, next, -lambda1 *predicted_psi + next};
}

void nearReference(float actual, double expected, double tolerance = 3.e-6)
{
	EXPECT_NEAR(static_cast<double>(actual), expected, tolerance * std::max(1., std::fabs(expected)));
}

void nearShapeReference(float actual, double expected)
{
	// p/Psi/rho have no cancellation with old state; require relative accuracy
	// for the small signals as well, rather than allowing them to disappear
	// within the output/state comparison's absolute tolerance.
	if (std::fabs(expected) <= 0.) {
		EXPECT_FLOAT_EQ(actual, 0.f);

	} else {
		EXPECT_NE(actual, 0.f);
		EXPECT_NEAR(static_cast<double>(actual), expected, 5.e-6 * std::fabs(expected));
	}
}

void checkImplicitResiduals(const Kernel::Candidate &candidate, const Kernel::Parameters &parameters)
{
	const double h = candidate.dt;
	const double epsilon = parameters.epsilon;
	const double lambda1 = parameters.lambda1;
	const double lambda2 = parameters.lambda2;
	const double predicted = candidate.p;
	const double shape_rho = rho(predicted, epsilon);
	const double shape_psi = psi(predicted, epsilon);
	const double scale = std::max(1., std::max(std::fabs(static_cast<double>(candidate.s)),
				      std::max(std::fabs(h * static_cast<double>(candidate.a_sta)),
					       std::fabs(h * static_cast<double>(candidate.nu_before)))));
	// All three frozen relations, plus the scalar root equation, are checked.
	EXPECT_NEAR(predicted - static_cast<double>(candidate.s)
		    - h * (static_cast<double>(candidate.a_sta) - static_cast<double>(candidate.nu_before)),
		    0., 4.e-6 * scale);
	nearReference(candidate.nu_next, static_cast<double>(candidate.nu_before) - h * lambda2 * shape_rho, 4.e-6);
	nearReference(candidate.a_sta, -lambda1 * shape_psi + static_cast<double>(candidate.nu_next), 4.e-6);
	EXPECT_NEAR(predicted + h * lambda1 * shape_psi + h * h * lambda2 * shape_rho - static_cast<double>(candidate.s),
		    0., 4.e-6 * std::max(1., std::fabs(static_cast<double>(candidate.s))));
}

void expectUnchanged(const Kernel &kernel, const std::array<float, 3> &before)
{
	for (size_t axis = 0; axis < before.size(); ++axis) {
		EXPECT_FLOAT_EQ(kernel.state()[axis], before[axis]);
	}
}
}

TEST(RegularizedIstaVelocityControl, ParameterDomainIncludesClosedEpsilonEndpoints)
{
	EXPECT_TRUE(Kernel::validParameters({.5f, .1f, .001f}));
	EXPECT_TRUE(Kernel::validParameters({2.f, 1.f, 1.f}));
	EXPECT_TRUE(Kernel::validParameters({Min, Max, .01f}));

	for (const float value : {0.f, -1.f, Tiny, NaN, Inf, -Inf}) {
		EXPECT_FALSE(Kernel::validParameters({value, .1f, .01f}));
		EXPECT_FALSE(Kernel::validParameters({.5f, value, .01f}));
	}

	for (const float epsilon : {
		     0.f, -1.f, Tiny, Min, .0001f,
		     std::nextafter(.001f, 0.f), std::nextafter(1.f, Inf), NaN, Inf
	     }) {
		EXPECT_FALSE(Kernel::validEpsilon(epsilon));
		EXPECT_FALSE(Kernel::validParameters({.5f, .1f, epsilon}));
	}
}

TEST(RegularizedIstaVelocityControl, InvalidConfigurationPreservesStateAndCandidate)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {.5f, .1f, .01f}));
	ASSERT_TRUE(kernel.reset(0, .25f));
	const auto candidate = kernel.evaluate(0, .1f, 0.f, .012f);
	ASSERT_TRUE(candidate.valid());
	EXPECT_FALSE(kernel.setParameters(0, {.5f, .1f, 0.f}));
	EXPECT_FALSE(kernel.setParameters(3, {.5f, .1f, .01f}));
	EXPECT_TRUE(kernel.current(candidate));
	EXPECT_FLOAT_EQ(kernel.state()[0], .25f);
	EXPECT_EQ(kernel.commit(candidate), Status::Ok);
}

TEST(RegularizedIstaVelocityControl, CurrentIdealOutputUsesCandidateNuWithoutFeedForward)
{
	Kernel kernel;
	const Kernel::Parameters parameters{1.f, 1.f, .25f};
	ASSERT_TRUE(kernel.setParameters(0, parameters));
	ASSERT_TRUE(kernel.reset(0, .25f));
	const auto candidate = kernel.evaluate(0, .875f, .5f, .5f);
	ASSERT_TRUE(candidate.valid());
	EXPECT_FLOAT_EQ(candidate.s, .375f);
	EXPECT_EQ(candidate.branch, Branch::Inner);
	EXPECT_FLOAT_EQ(candidate.p, .125f);
	EXPECT_FLOAT_EQ(candidate.rho, .5f);
	EXPECT_FLOAT_EQ(candidate.psi, .25f);
	EXPECT_FLOAT_EQ(candidate.nu_before, .25f);
	EXPECT_FLOAT_EQ(candidate.nu_next, 0.f);
	EXPECT_FLOAT_EQ(candidate.a_sta, -.25f);
	EXPECT_NE(candidate.a_sta, -candidate.psi + candidate.nu_before);
	EXPECT_FLOAT_EQ(kernel.state()[0], .25f);
	const float original_ff = .3f;
	EXPECT_FLOAT_EQ(candidate.a_sta + original_ff, -.25f + original_ff);
	checkImplicitResiduals(candidate, parameters);
	EXPECT_EQ(kernel.commit(candidate), Status::Ok);
	EXPECT_FLOAT_EQ(kernel.state()[0], 0.f);
}

TEST(RegularizedIstaVelocityControl, ZeroErrorRetainsNonzeroNuWithoutUnusedIntermediateOverflow)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {Max, Max, .01f}));
	ASSERT_TRUE(kernel.reset(0, -.25f));

	for (const float zero : {0.f, -0.f}) {
		const auto candidate = kernel.evaluate(0, zero, 0.f, Max);
		ASSERT_TRUE(candidate.valid());
		EXPECT_EQ(candidate.branch, Branch::Inner);
		EXPECT_FLOAT_EQ(candidate.p, 0.f);
		EXPECT_FLOAT_EQ(candidate.psi, 0.f);
		EXPECT_FLOAT_EQ(candidate.rho, 0.f);
		EXPECT_FLOAT_EQ(candidate.a_sta, -.25f);
		EXPECT_FLOAT_EQ(candidate.nu_next, -.25f);
		EXPECT_EQ(kernel.commit(candidate), Status::Ok);
	}
}

TEST(RegularizedIstaVelocityControl, PositiveNegativeSymmetryIncludesNonzeroNu)
{
	Kernel positive;
	Kernel negative;
	ASSERT_TRUE(positive.setParameters(0, {.5f, .1f, .01f}));
	ASSERT_TRUE(negative.setParameters(0, {.5f, .1f, .01f}));

	for (const float s : {.0001f, .005f, .01f, .1f, 10.f}) {
		ASSERT_TRUE(positive.reset(0, .17f));
		ASSERT_TRUE(negative.reset(0, -.17f));
		const auto p = positive.evaluate(0, s, 0.f, .012f);
		const auto n = negative.evaluate(0, -s, 0.f, .012f);
		ASSERT_TRUE(p.valid());
		ASSERT_TRUE(n.valid());
		EXPECT_FLOAT_EQ(n.p, -p.p);
		EXPECT_FLOAT_EQ(n.psi, -p.psi);
		EXPECT_FLOAT_EQ(n.rho, -p.rho);
		EXPECT_FLOAT_EQ(n.a_sta, -p.a_sta);
		EXPECT_FLOAT_EQ(n.nu_next, -p.nu_next);
	}
}

TEST(RegularizedIstaVelocityControl, ExactSignedBranchBoundariesAndNextafterNeighbors)
{
	const Kernel::Parameters parameters{1.f, 1.f, .25f};
	const float h = .5f;
	const float boundary = .75f; // All terms of eps+h*l1*sqrt(eps)+h*h*l2 are exact.
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, parameters));
	ASSERT_TRUE(kernel.reset(0, .125f));

	for (const float sign : {-1.f, 1.f}) {
		for (const float magnitude : {
			     std::nextafter(boundary, 0.f), boundary,
			     std::nextafter(boundary, Inf)
		     }) {
			const auto candidate = kernel.evaluate(0, sign * magnitude, 0.f, h);
			ASSERT_TRUE(candidate.valid());
			EXPECT_EQ(candidate.branch, magnitude <= boundary ? Branch::Inner : Branch::Outer);
			const auto expected = reference(parameters, sign * magnitude, .125f, h);
			nearReference(candidate.p, expected.p);
			nearReference(candidate.a_sta, expected.output);
			nearReference(candidate.nu_next, expected.next);
			EXPECT_LE(std::fabs(candidate.rho), 1.f);
			checkImplicitResiduals(candidate, parameters);

			if (std::fabs(magnitude - boundary) <= 0.f) {
				EXPECT_FLOAT_EQ(candidate.p, sign * parameters.epsilon);
				EXPECT_FLOAT_EQ(candidate.rho, sign);
			}
		}
	}
}

TEST(RegularizedIstaVelocityControl, RootIsMonotonicOddContinuousAndBoundedByInput)
{
	Kernel kernel;
	const Kernel::Parameters parameters{.5f, .1f, .01f};
	ASSERT_TRUE(kernel.setParameters(0, parameters));
	float previous = -Inf;

	for (int i = -1000; i <= 1000; ++i) {
		const float s = static_cast<float>(i) * .0001f;
		const auto candidate = kernel.evaluate(0, s, 0.f, .012f);
		const auto negative = kernel.evaluate(0, -s, 0.f, .012f);
		ASSERT_TRUE(candidate.valid());
		ASSERT_TRUE(negative.valid());
		EXPECT_GE(candidate.p, previous);
		EXPECT_LE(std::fabs(candidate.p), std::fabs(s));
		EXPECT_FLOAT_EQ(candidate.p, -negative.p);
		EXPECT_LE(std::fabs(candidate.rho), 1.f);
		previous = candidate.p;
	}
}

TEST(RegularizedIstaVelocityControl, RoundedEngineeringBoundariesRespectSaturationDefinition)
{
	for (const float epsilon : {.001f, .01f, .02f}) {
		for (const Kernel::Parameters &parameters : {
		Kernel::Parameters{.1f, .01f, epsilon},
	{.5f, .1f, epsilon}, {2.f, 1.f, epsilon}, {3.f, 1.f, epsilon}, {20.f, 40.f, epsilon}
	     }) {
			Kernel kernel;
			ASSERT_TRUE(kernel.setParameters(0, parameters));

			for (const float h : {.002f, .008f, .012f, .04f}) {
				// Unlike the exact .75 test, this is a rounded float estimate
				// of the mathematical boundary: do not assume branch identity.
				const float boundary = epsilon + h * parameters.lambda1 * std::sqrt(epsilon)
						       + h * (h * parameters.lambda2);

				for (const float magnitude : {
					     std::nextafter(boundary, 0.f), boundary,
					     std::nextafter(boundary, Inf)
				     }) {
					for (const float sign : {-1.f, 1.f}) {
						const auto candidate = kernel.evaluate(0, sign * magnitude, 0.f, h);
						ASSERT_TRUE(candidate.valid());
						EXPECT_LE(std::fabs(candidate.rho), 1.f);
						const auto expected = reference(parameters, sign * magnitude, 0., h);
						nearShapeReference(candidate.p, expected.p);
						nearShapeReference(candidate.rho, rho(candidate.p, epsilon));
						nearShapeReference(candidate.psi, psi(candidate.p, epsilon));
						checkImplicitResiduals(candidate, parameters);
					}
				}
			}
		}
	}
}

TEST(RegularizedIstaVelocityControl, CompensatedRootDoesNotDependOnOldNu)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {.5f, .1f, .01f}));
	const auto zero = kernel.evaluate(0, 1.e-8f, 0.f, .012f);
	ASSERT_TRUE(zero.valid());
	ASSERT_TRUE(kernel.reset(0, 1.e20f));
	const auto large = kernel.evaluate(0, 1.e-8f, 0.f, .012f);
	ASSERT_TRUE(large.valid());
	EXPECT_FLOAT_EQ(large.p, zero.p);
	EXPECT_FLOAT_EQ(large.psi, zero.psi);
	EXPECT_FLOAT_EQ(large.rho, zero.rho);
	EXPECT_GT(large.p, 0.f);
	// Literal input compensation would erase the small error in float.
	EXPECT_EQ((1.e-8f + .012f * 1.e20f) - .012f * 1.e20f, 0.f);
}

TEST(RegularizedIstaVelocityControl, RationalizedRootAvoidsFloatSubtractionCancellation)
{
	Kernel kernel;
	const Kernel::Parameters parameters{1.e14f, .1f, .001f};
	const float h = .01f;
	const float s = 1.e12f;
	ASSERT_TRUE(kernel.setParameters(0, parameters));
	const float a = h * parameters.lambda1;
	const float c = s - h * h * parameters.lambda2;
	const float naive = (std::sqrt(a * a + 4.f * c) - a) * .5f;
	ASSERT_EQ(naive, 0.f);
	const auto candidate = kernel.evaluate(0, s, 0.f, h);
	ASSERT_TRUE(candidate.valid());
	EXPECT_EQ(candidate.branch, Branch::Outer);
	EXPECT_GT(candidate.p, 0.f);
	const auto expected = reference(parameters, s, 0., h);
	nearReference(candidate.p, expected.p);
	nearReference(candidate.a_sta, expected.output);
	checkImplicitResiduals(candidate, parameters);
}

TEST(RegularizedIstaVelocityControl, ScaledOuterRootAvoidsIntermediateSquaresAndMultiplesOverflow)
{
	Kernel kernel;
	const Kernel::Parameters parameters{1.e18f, .1f, .001f};
	// This is purely an arithmetic-domain test, not an admissible flight dt.
	const float h = 100.f;
	const float s = 1.e38f;
	ASSERT_TRUE(kernel.setParameters(0, parameters));
	const float a = h * parameters.lambda1;
	EXPECT_FALSE(std::isfinite(a * a));
	EXPECT_FALSE(std::isfinite(4.f * s));
	const auto candidate = kernel.evaluate(0, s, 0.f, h);
	ASSERT_TRUE(candidate.valid());
	EXPECT_EQ(candidate.branch, Branch::Outer);
	EXPECT_TRUE(std::isfinite(candidate.p));
	EXPECT_TRUE(std::isfinite(candidate.a_sta));
	const auto expected = reference(parameters, s, 0., h);
	nearReference(candidate.p, expected.p, 5.e-6);
	nearReference(candidate.a_sta, expected.output, 5.e-6);
	checkImplicitResiduals(candidate, parameters);
}

TEST(RegularizedIstaVelocityControl, LargestFiniteErrorIsFiniteOrExplicitlyRejectedWithoutStateChange)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {.5f, .1f, .001f}));
	const auto before = kernel.state();

	for (const float s : {-Max, Max}) {
		const auto candidate = kernel.evaluate(0, s, 0.f, .008f);

		if (candidate.valid()) {
			EXPECT_TRUE(std::isfinite(candidate.p));
			EXPECT_TRUE(std::isfinite(candidate.a_sta));
			EXPECT_TRUE(std::isfinite(candidate.nu_next));
			EXPECT_EQ(std::signbit(candidate.a_sta), !std::signbit(s));

		} else {
			EXPECT_EQ(candidate.status, Status::NumericalError);
			EXPECT_EQ(kernel.commit(candidate), Status::NumericalError);
		}

		expectUnchanged(kernel, before);
	}
}

TEST(RegularizedIstaVelocityControl, InvalidInputsAndSubtractionOverflowAreAtomic)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {.5f, .1f, .01f}));
	ASSERT_TRUE(kernel.reset(0, .2f));
	const auto before = kernel.state();

	for (const float value : {NaN, Inf, -Inf}) {
		EXPECT_EQ(kernel.evaluate(0, value, 0.f, .01f).status, Status::InvalidInput);
		EXPECT_EQ(kernel.evaluate(0, 0.f, value, .01f).status, Status::InvalidInput);
		EXPECT_FALSE(kernel.reset(0, value));
	}

	EXPECT_EQ(kernel.evaluate(0, Max, -Max, .01f).status, Status::NumericalError);
	expectUnchanged(kernel, before);
}

TEST(RegularizedIstaVelocityControl, InvalidDtIsRejectedWithoutClamping)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {.5f, .1f, .01f}));
	const auto before = kernel.state();

	for (const float h : {0.f, -0.f, -.01f, Tiny, NaN, Inf, -Inf}) {
		const auto candidate = kernel.evaluate(0, .1f, 0.f, h);
		EXPECT_EQ(candidate.status, Status::InvalidDt);
		EXPECT_EQ(kernel.commit(candidate), Status::InvalidDt);
	}

	ASSERT_TRUE(kernel.evaluate(0, .1f, 0.f, .05f).valid());
	expectUnchanged(kernel, before);
}

TEST(RegularizedIstaVelocityControl, NonzeroIntermediateOverflowIsRejected)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {Max, .1f, .01f}));
	EXPECT_EQ(kernel.evaluate(0, 1.f, 0.f, 2.f).status, Status::NumericalError);
	ASSERT_TRUE(kernel.setParameters(0, {.5f, Max, .01f}));
	EXPECT_EQ(kernel.evaluate(0, 1.f, 0.f, 2.f).status, Status::NumericalError);
	EXPECT_FLOAT_EQ(kernel.state()[0], 0.f);
}

TEST(RegularizedIstaVelocityControl, NonzeroIntermediateUnderflowIsNotSilentlyZeroed)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {Min, .1f, .01f}));
	EXPECT_EQ(kernel.evaluate(0, .005f, 0.f, .01f).status, Status::NumericalError);
	ASSERT_TRUE(kernel.setParameters(0, {.5f, Min, .01f}));
	EXPECT_EQ(kernel.evaluate(0, .01f, 0.f, .01f).status, Status::NumericalError);
	ASSERT_TRUE(kernel.setParameters(0, {.5f, .1f, 1.f}));
	EXPECT_EQ(kernel.evaluate(0, Tiny, 0.f, .01f).status, Status::NumericalError);
	ASSERT_TRUE(kernel.setParameters(0, {Max, 1.f, 1.f}));
	EXPECT_EQ(kernel.evaluate(0, Min, 0.f, 1.f).status, Status::NumericalError);
	EXPECT_FLOAT_EQ(kernel.state()[0], 0.f);
}

TEST(RegularizedIstaVelocityControl, NormalIncrementAdditionRoundingIsNotProductUnderflow)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {.5f, .1f, .01f}));
	ASSERT_TRUE(kernel.reset(0, 1.f));
	const auto candidate = kernel.evaluate(0, 1.e-10f, 0.f, .01f);
	ASSERT_TRUE(candidate.valid());
	EXPECT_FLOAT_EQ(candidate.nu_next, candidate.nu_before);
	EXPECT_EQ(kernel.commit(candidate), Status::Ok);
	EXPECT_FALSE(kernel.current(candidate));
}

TEST(RegularizedIstaVelocityControl, FinalOutputAndStateOverflowAreRejectedAtomically)
{
	Kernel kernel;
	const Kernel::Parameters parameters{1.e22f, .1f, .001f};
	ASSERT_TRUE(kernel.setParameters(0, parameters));
	ASSERT_TRUE(kernel.reset(0, -Max));
	const auto before = kernel.state();
	EXPECT_EQ(kernel.evaluate(0, 1.e38f, 0.f, .01f).status, Status::NumericalError);
	expectUnchanged(kernel, before);
	// Inner-layer delta is normal and finite, but subtracting it from -Max
	// overflows even though the root and lambda1*Psi are representable.
	ASSERT_TRUE(kernel.setParameters(0, {1.f, Max, 1.f}));
	EXPECT_EQ(kernel.evaluate(0, Max, 0.f, 1.f).status, Status::NumericalError);
	expectUnchanged(kernel, before);
}

TEST(RegularizedIstaVelocityControl, NonzeroSubnormalStateCannotEnterThroughResetOrProtectedCommit)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {.5f, .1f, .01f}));
	EXPECT_FALSE(kernel.reset(0, Tiny));
	EXPECT_FALSE(kernel.reset(0, -Tiny));
	const auto candidate = kernel.evaluate(0, .1f, 0.f, .01f);
	ASSERT_TRUE(candidate.valid());
	EXPECT_NE(kernel.commitProtected(candidate, Tiny), Status::Ok);
	EXPECT_NE(kernel.commitProtected(candidate, -Tiny), Status::Ok);
	EXPECT_TRUE(kernel.current(candidate));
	EXPECT_FLOAT_EQ(kernel.state()[0], 0.f);
	EXPECT_EQ(kernel.commit(candidate), Status::Ok);
}

TEST(RegularizedIstaVelocityControl, FinalSubnormalOutputOrNextStateIsRejected)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {Min, Min, 1.f}));
	// A, B, rho, Psi, lambda1*Psi and delta are normal; only subtracting
	// near-equal normal quantities creates the forbidden final subnormal.
	const float output_case_state = 2.f * Min + 2.f * Tiny;
	ASSERT_EQ(std::fpclassify((output_case_state - Min) - Min), FP_SUBNORMAL);
	ASSERT_TRUE(kernel.reset(0, output_case_state));
	const auto before_output_case = kernel.state();
	EXPECT_EQ(kernel.evaluate(0, 1.f, 0.f, 1.f).status, Status::NumericalError);
	expectUnchanged(kernel, before_output_case);
	const float state_case_state = Min + Tiny;
	ASSERT_EQ(std::fpclassify(state_case_state - Min), FP_SUBNORMAL);
	ASSERT_TRUE(kernel.reset(0, state_case_state));
	const auto before_state_case = kernel.state();
	EXPECT_EQ(kernel.evaluate(0, 1.f, 0.f, 1.f).status, Status::NumericalError);
	expectUnchanged(kernel, before_state_case);
}

TEST(RegularizedIstaVelocityControl, StateAndCandidateGenerationsAreIndependentAcrossAxes)
{
	Kernel kernel;
	std::array<Kernel::Candidate, 3> candidates{};

	for (size_t axis = 0; axis < 3; ++axis) {
		ASSERT_TRUE(kernel.setParameters(axis, {.5f + static_cast<float>(axis), .1f, .01f}));
		ASSERT_TRUE(kernel.reset(axis, static_cast<float>(axis) * .1f));
		candidates[axis] = kernel.evaluate(axis, .1f, 0.f, .01f);
		ASSERT_TRUE(candidates[axis].valid());
	}

	EXPECT_EQ(kernel.commit(candidates[0]), Status::Ok);
	EXPECT_TRUE(kernel.current(candidates[1]));
	EXPECT_TRUE(kernel.current(candidates[2]));
	ASSERT_TRUE(kernel.setParameters(1, {.6f, .2f, .02f}));
	EXPECT_FALSE(kernel.current(candidates[1]));
	EXPECT_TRUE(kernel.current(candidates[2]));
	EXPECT_EQ(kernel.commit(candidates[2]), Status::Ok);
	EXPECT_FLOAT_EQ(kernel.state()[1], .1f);
}

TEST(RegularizedIstaVelocityControl, ResetToSameValueAndGlobalResetInvalidateCandidates)
{
	Kernel kernel;
	std::array<Kernel::Candidate, 3> before{};

	for (size_t axis = 0; axis < 3; ++axis) {
		ASSERT_TRUE(kernel.setParameters(axis, {.5f, .1f, .01f}));
		ASSERT_TRUE(kernel.reset(axis, .2f));
		before[axis] = kernel.evaluate(axis, .1f, 0.f, .01f);
	}

	ASSERT_TRUE(kernel.reset(0, .2f));
	EXPECT_EQ(kernel.commit(before[0]), Status::StaleCandidate);
	EXPECT_TRUE(kernel.current(before[1]));
	EXPECT_TRUE(kernel.current(before[2]));
	const auto next = kernel.evaluate(0, .1f, 0.f, .01f);
	EXPECT_GT(next.reset_generation, before[0].reset_generation);
	kernel.reset();
	EXPECT_EQ(kernel.commit(next), Status::StaleCandidate);

	for (size_t axis = 0; axis < 3; ++axis) {
		EXPECT_EQ(kernel.commit(before[axis]), Status::StaleCandidate);
		EXPECT_FLOAT_EQ(kernel.state()[axis], 0.f);
		EXPECT_TRUE(kernel.evaluate(axis, .1f, 0.f, .01f).valid());
	}
}

TEST(RegularizedIstaVelocityControl, EpsilonGainAndEqualConfigurationUpdatesInvalidate)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {.5f, .1f, .01f}));

	for (const Kernel::Parameters &parameters : {
	Kernel::Parameters{.5f, .1f, .02f}, {.6f, .1f, .02f},
{.6f, .2f, .02f}, {.6f, .2f, .02f}
     }) {
		const auto previous = kernel.evaluate(0, .1f, 0.f, .01f);
		ASSERT_TRUE(previous.valid());
		ASSERT_TRUE(kernel.setParameters(0, parameters));
		EXPECT_EQ(kernel.commit(previous), Status::StaleCandidate);
		const auto next = kernel.evaluate(0, .1f, 0.f, .01f);
		EXPECT_GT(next.config_generation, previous.config_generation);
	}
}

TEST(RegularizedIstaVelocityControl, CandidatesCommitOnlyOnceIncludingSameNu)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {.5f, .1f, .01f}));
	const auto zero = kernel.evaluate(0, 0.f, 0.f, .01f);
	ASSERT_TRUE(zero.valid());
	EXPECT_EQ(kernel.commit(zero), Status::Ok);
	EXPECT_EQ(kernel.commit(zero), Status::StaleCandidate);
	const auto next = kernel.evaluate(0, 0.f, 0.f, .01f);
	EXPECT_GT(next.state_generation, zero.state_generation);
	const auto other_candidate_same_state = kernel.evaluate(0, .1f, 0.f, .01f);
	EXPECT_EQ(kernel.commitProtected(next, 0.f), Status::Ok);
	EXPECT_EQ(kernel.commit(other_candidate_same_state), Status::StaleCandidate);
}

TEST(RegularizedIstaVelocityControl, OwnerAxisBranchGenerationsAndEveryPayloadFieldAreSealed)
{
	Kernel first;
	Kernel second;
	ASSERT_TRUE(first.setParameters(0, {.5f, .1f, .01f}));
	ASSERT_TRUE(first.setParameters(1, {.5f, .1f, .01f}));
	ASSERT_TRUE(second.setParameters(0, {.5f, .1f, .01f}));
	const auto original = first.evaluate(0, .1f, 0.f, .01f);
	ASSERT_TRUE(original.valid());
	EXPECT_EQ(second.commit(original), Status::StaleCandidate);

	for (int mutation = 0; mutation < 14; ++mutation) {
		auto changed = original;

		switch (mutation) {
		case 0: changed.axis = 1; break;

		case 1: ++changed.config_generation; break;

		case 2: ++changed.reset_generation; break;

		case 3: ++changed.state_generation; break;

		case 4: changed.s = 0.f; break;

		case 5: changed.p = 0.f; break;

		case 6: changed.psi = 0.f; break;

		case 7: changed.rho = 0.f; break;

		case 8: changed.a_sta = 0.f; break;

		case 9: changed.nu_before = -0.f; break; // A bitwise seal detects signed zero.

		case 10: changed.nu_next = 0.f; break;

		case 11: changed.dt = .012f; break;

		case 12: changed.branch = original.branch == Branch::Inner ? Branch::Outer : Branch::Inner; break;

		default: changed.status = Status::NumericalError; break;
		}

		EXPECT_FALSE(first.current(changed));
		EXPECT_NE(first.commit(changed), Status::Ok);
		EXPECT_TRUE(first.current(original));
		EXPECT_FLOAT_EQ(first.state()[0], 0.f);
	}

	Kernel::Candidate forged{};
	forged.status = Status::Ok;
	forged.axis = 0;
	EXPECT_EQ(first.commit(forged), Status::StaleCandidate);
	EXPECT_EQ(first.commit(original), Status::Ok);
}

TEST(RegularizedIstaVelocityControl, ProtectedCommitPreservesIdealOutputWithoutImplicitClaim)
{
	Kernel kernel;
	const Kernel::Parameters parameters{.5f, .1f, .01f};
	ASSERT_TRUE(kernel.setParameters(0, parameters));
	ASSERT_TRUE(kernel.reset(0, .2f));
	const auto candidate = kernel.evaluate(0, .1f, 0.f, .012f);
	ASSERT_TRUE(candidate.valid());
	checkImplicitResiduals(candidate, parameters);
	const float original_output = candidate.a_sta;
	const float ideal_next = candidate.nu_next;
	const float applied = -.05f;
	EXPECT_EQ(kernel.commitProtected(candidate, applied), Status::Ok);
	EXPECT_FLOAT_EQ(kernel.state()[0], applied);
	EXPECT_FLOAT_EQ(candidate.a_sta, original_output);
	EXPECT_FLOAT_EQ(candidate.nu_next, ideal_next);
	EXPECT_NE(kernel.state()[0], candidate.nu_next);
	EXPECT_EQ(kernel.commit(candidate), Status::StaleCandidate);
	// Applying a different state cannot be labelled the original implicit pair.
	const double protected_state_residual = applied - candidate.nu_before
						+ candidate.dt * parameters.lambda2 * candidate.rho;
	EXPECT_GT(std::fabs(protected_state_residual), .1);
	// Replacing a by a+delta_nu at unchanged p breaks the prediction equation.
	const double changed_output = static_cast<double>(candidate.a_sta) + static_cast<double>(applied)
				      - static_cast<double>(candidate.nu_next);
	const double prediction_residual = static_cast<double>(candidate.p - candidate.s)
					   - static_cast<double>(candidate.dt) * (changed_output - static_cast<double>(candidate.nu_before));
	EXPECT_NEAR(prediction_residual, -candidate.dt * (applied - candidate.nu_next), 1.e-6);
}

TEST(RegularizedIstaVelocityControl, ReconstructedControllerAtSameAddressRejectsDestroyedOwnersCandidate)
{
	alignas(Kernel) unsigned char storage[sizeof(Kernel)];
	auto *first = new (storage) Kernel;
	ASSERT_TRUE(first->setParameters(0, {.5f, .1f, .01f}));
	ASSERT_TRUE(first->reset(0, .2f));
	const auto old_candidate = first->evaluate(0, .1f, 0.f, .012f);
	ASSERT_TRUE(old_candidate.valid());
	first->~Kernel();
	auto *replacement = new (storage) Kernel;
	ASSERT_TRUE(replacement->setParameters(0, {.5f, .1f, .01f}));
	ASSERT_TRUE(replacement->reset(0, .2f));
	const auto new_candidate = replacement->evaluate(0, .1f, 0.f, .012f);
	ASSERT_TRUE(new_candidate.valid());
	EXPECT_EQ(new_candidate.config_generation, old_candidate.config_generation);
	EXPECT_EQ(new_candidate.reset_generation, old_candidate.reset_generation);
	EXPECT_EQ(new_candidate.state_generation, old_candidate.state_generation);
	EXPECT_FLOAT_EQ(new_candidate.nu_before, old_candidate.nu_before);
	EXPECT_FALSE(replacement->current(old_candidate));
	EXPECT_EQ(replacement->commit(old_candidate), Status::StaleCandidate);
	EXPECT_TRUE(replacement->current(new_candidate));
	EXPECT_EQ(replacement->commit(new_candidate), Status::Ok);
	replacement->~Kernel();
}

TEST(RegularizedIstaVelocityControl, BatchCommitPreflightsAllAxesBeforeAnyMutation)
{
	Kernel kernel;
	std::array<Kernel::Candidate, 3> candidates{};
	std::array<float, 3> applied{};

	for (size_t axis = 0; axis < 3; ++axis) {
		ASSERT_TRUE(kernel.setParameters(axis, {.5f + static_cast<float>(axis), .1f, .01f}));
		ASSERT_TRUE(kernel.reset(axis, .1f * static_cast<float>(axis)));
		candidates[axis] = kernel.evaluate(axis, .1f, 0.f, .012f);
		ASSERT_TRUE(candidates[axis].valid());
		applied[axis] = candidates[axis].nu_next;
	}

	const auto before = kernel.state();
	auto changed = candidates;
	changed[2].nu_next = 0.f;
	EXPECT_NE(kernel.commitBatch(changed, 7, applied), Status::Ok);
	expectUnchanged(kernel, before);

	for (const auto &candidate : candidates) {
		EXPECT_TRUE(kernel.current(candidate));
	}

	auto invalid_applied = applied;
	invalid_applied[2] = NaN;
	EXPECT_NE(kernel.commitBatch(candidates, 7, invalid_applied), Status::Ok);
	expectUnchanged(kernel, before);
	invalid_applied[2] = Tiny;
	EXPECT_NE(kernel.commitBatch(candidates, 7, invalid_applied), Status::Ok);
	expectUnchanged(kernel, before);
	EXPECT_EQ(kernel.commitBatch(candidates, 7, applied), Status::Ok);

	for (size_t axis = 0; axis < 3; ++axis) {
		EXPECT_FLOAT_EQ(kernel.state()[axis], applied[axis]);
		EXPECT_FALSE(kernel.current(candidates[axis]));
	}

	EXPECT_NE(kernel.commitBatch(candidates, 7, applied), Status::Ok);
}

TEST(RegularizedIstaVelocityControl, BatchMaskAndIndexIdentityAreExplicitAndUnselectedAxesRemainCurrent)
{
	Kernel kernel;
	std::array<Kernel::Candidate, 3> candidates{};
	std::array<float, 3> applied{};

	for (size_t axis = 0; axis < 3; ++axis) {
		ASSERT_TRUE(kernel.setParameters(axis, {.5f, .1f, .01f}));
		candidates[axis] = kernel.evaluate(axis, .1f, 0.f, .012f);
		ASSERT_TRUE(candidates[axis].valid());
		applied[axis] = candidates[axis].nu_next;
	}

	const auto before = kernel.state();

	for (const uint8_t mask : {uint8_t{0}, uint8_t{8}, uint8_t{255}}) {
		EXPECT_NE(kernel.commitBatch(candidates, mask, applied), Status::Ok);
		expectUnchanged(kernel, before);
	}

	auto swapped = candidates;
	std::swap(swapped[0], swapped[1]);
	EXPECT_NE(kernel.commitBatch(swapped, 3, applied), Status::Ok);
	expectUnchanged(kernel, before);
	// Invalid values on an unselected axis are not consumed by this batch.
	auto unused_invalid = applied;
	unused_invalid[1] = NaN;
	EXPECT_EQ(kernel.commitBatch(candidates, 5, unused_invalid), Status::Ok);
	EXPECT_FLOAT_EQ(kernel.state()[0], applied[0]);
	EXPECT_FLOAT_EQ(kernel.state()[1], before[1]);
	EXPECT_FLOAT_EQ(kernel.state()[2], applied[2]);
	EXPECT_TRUE(kernel.current(candidates[1]));
	EXPECT_FALSE(kernel.current(candidates[0]));
	EXPECT_FALSE(kernel.current(candidates[2]));
}

TEST(RegularizedIstaVelocityControl, AllNonemptyBatchMasksCommitOnlySelectedIndependentStates)
{
	for (uint8_t mask = 1; mask <= 7; ++mask) {
		Kernel kernel;
		std::array<Kernel::Candidate, 3> candidates{};
		std::array<float, 3> applied{};

		for (size_t axis = 0; axis < 3; ++axis) {
			ASSERT_TRUE(kernel.setParameters(axis, {.5f, .1f + static_cast<float>(axis), .01f}));
			candidates[axis] = kernel.evaluate(axis, .1f, 0.f, .012f);
			ASSERT_TRUE(candidates[axis].valid());
			applied[axis] = candidates[axis].nu_next;
		}

		ASSERT_EQ(kernel.commitBatch(candidates, mask, applied), Status::Ok);

		for (size_t axis = 0; axis < 3; ++axis) {
			const bool selected = (mask & (1u << axis)) != 0;
			EXPECT_FLOAT_EQ(kernel.state()[axis], selected ? applied[axis] : 0.f);
			EXPECT_EQ(kernel.current(candidates[axis]), !selected);
		}
	}
}

TEST(RegularizedIstaVelocityControl, InvalidProtectedStateDoesNotConsumeCandidate)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {.5f, .1f, .01f}));
	const auto candidate = kernel.evaluate(0, .1f, 0.f, .01f);
	ASSERT_TRUE(candidate.valid());

	for (const float applied : {NaN, Inf, -Inf}) {
		EXPECT_NE(kernel.commitProtected(candidate, applied), Status::Ok);
		EXPECT_TRUE(kernel.current(candidate));
		EXPECT_FLOAT_EQ(kernel.state()[0], 0.f);
	}

	EXPECT_EQ(kernel.commit(candidate), Status::Ok);
}

TEST(RegularizedIstaVelocityControl, UnconfiguredInvalidAxisAndResetValidation)
{
	Kernel kernel;
	EXPECT_EQ(kernel.evaluate(0, 0.f, 0.f, .01f).status, Status::Unconfigured);
	EXPECT_EQ(kernel.evaluate(3, 0.f, 0.f, .01f).status, Status::InvalidAxis);
	EXPECT_FALSE(kernel.reset(3, 0.f));
	EXPECT_FALSE(kernel.reset(0, NaN));
	Kernel::Candidate invalid{};
	invalid.status = Status::Ok;
	invalid.axis = 3;
	EXPECT_EQ(kernel.commit(invalid), Status::InvalidAxis);
	EXPECT_FALSE(kernel.current(invalid));
}

TEST(RegularizedIstaVelocityControl, FloatGridMatchesIndependentDoubleMonotonicRoot)
{
	size_t checked = 0;

	for (const float epsilon : {.001f, .01f, .02f, 1.f}) {
		for (const float lambda1 : {.1f, .5f, 2.f}) {
			for (const float lambda2 : {.01f, .1f, 1.f}) {
				const Kernel::Parameters parameters{lambda1, lambda2, epsilon};
				Kernel kernel;
				ASSERT_TRUE(kernel.setParameters(0, parameters));

				for (const float error_scale : {-10.f, -1.f, -.5f, -.001f, 0.f, .001f, .5f, 1.f, 10.f}) {
					const float s = error_scale * epsilon;

					for (const float nu : {-.2f, 0.f, .8f}) {
						for (const float h : {.002f, .008f, .012f, .04f}) {
							ASSERT_TRUE(kernel.reset(0, nu));
							const auto candidate = kernel.evaluate(0, s, 0.f, h);
							ASSERT_TRUE(candidate.valid());
							const auto expected = reference(parameters, s, static_cast<double>(nu), h);
							nearShapeReference(candidate.p, expected.p);
							nearShapeReference(candidate.psi, expected.psi);
							nearShapeReference(candidate.rho, expected.rho);
							nearReference(candidate.a_sta, expected.output);
							nearReference(candidate.nu_next, expected.next);
							checkImplicitResiduals(candidate, parameters);
							++checked;
						}
					}
				}
			}
		}
	}

	EXPECT_EQ(checked, 3888u);
}

TEST(RegularizedIstaVelocityControl, VariableSampleDrivenSequencesMatchIndependentDoubleState)
{
	for (const Kernel::Parameters &parameters : {Kernel::Parameters{.5f, .1f, .01f}, {2.f, 1.f, .02f}}) {
		Kernel kernel;
		ASSERT_TRUE(kernel.setParameters(0, parameters));
		ASSERT_TRUE(kernel.reset(0, .2f));
		double reference_nu = static_cast<double>(.2f);

		for (int k = 0; k < 2048; ++k) {
			const float velocity = .2f * std::sin(static_cast<float>(k) * .03f);
			const float setpoint = .1f * std::cos(static_cast<float>(k) * .017f);
			// A deliberately non-uniform offline cadence; full measured replay
			// belongs to the separately archived independent object experiment.
			const float h = k % 2 == 0 ? .008f : .012f;
			const auto candidate = kernel.evaluate(0, velocity, setpoint, h);
			ASSERT_TRUE(candidate.valid());
			const auto expected = reference(parameters, velocity - setpoint, reference_nu, h);
			nearReference(candidate.p, expected.p, 2.e-5);
			nearReference(candidate.a_sta, expected.output, 2.e-5);
			nearReference(candidate.nu_next, expected.next, 2.e-5);
			ASSERT_EQ(kernel.commit(candidate), Status::Ok);
			reference_nu = expected.next;
		}
	}
}

TEST(RegularizedIstaVelocityControl, FixedPeriodInnerLayerMatchesIndependentStateMatrix)
{
	const Kernel::Parameters parameters{.5f, .1f, .01f};
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, parameters));
	const double epsilon = parameters.epsilon;
	const double alpha = static_cast<double>(parameters.lambda1) / std::sqrt(epsilon);
	const double beta = static_cast<double>(parameters.lambda2) / epsilon;

	for (const float h_float : {.008f, .012f}) {
		const double h = h_float;
		const double denominator = 1. + h * alpha + h * h * beta;
		const double trace = 1. + 1. / denominator;
		const double determinant = (1. + h * h * beta) / denominator;
		EXPECT_GT(1. - trace + determinant, 0.);
		EXPECT_GT(1. - determinant, 0.);
		EXPECT_GT(1. + trace + determinant, 0.);

		for (const float s : {-.005f, -.0001f, 0.f, .0001f, .005f}) {
			const float nu = .02f;
			ASSERT_TRUE(kernel.reset(0, nu));
			const auto candidate = kernel.evaluate(0, s, 0.f, h_float);
			ASSERT_TRUE(candidate.valid());
			ASSERT_EQ(candidate.branch, Branch::Inner);
			const double expected_error = static_cast<double>(s) / denominator + h * static_cast<double>(nu);
			const double expected_state = static_cast<double>(nu) - h * beta * static_cast<double>(s) / denominator;
			nearReference(s + h_float * candidate.a_sta, expected_error);
			nearReference(candidate.nu_next, expected_state);
		}
	}
}

TEST(RegularizedIstaVelocityControl, SelectorWithoutCallerAdmissionCannotDisplaceExistingAlgorithms)
{
	VelocityControlSelector selector;

	for (const int mode : {0, 1, 3}) {
		// Admission flag is explicit for the already qualified R-STA path.
		selector.configure(mode, mode == 0 ? 0 : 1, false, true, 1, true);
		ASSERT_EQ(selector.effectiveMode(), mode);
		const int previous_axes = selector.effectiveAxes();

		for (const bool armed : {false, true}) {
			for (int mask = 0; mask <= 7; ++mask) {
				selector.configure(4, mask, armed, true, mask, true);
				EXPECT_EQ(selector.requestedMode(), 4);
				EXPECT_EQ(selector.requestedAxes(), mask);
				// The selector requires explicit admission from its caller even in RI03.
				EXPECT_NE(selector.reject() & VelocityControlSelector::ModeUnimplemented, 0);
				EXPECT_EQ(selector.effectiveMode(), mode);
				EXPECT_EQ(selector.effectiveAxes(), previous_axes);
				EXPECT_EQ(selector.pending(), armed);
			}
		}

		selector.configure(mode, mode == 0 ? 0 : 1, false, true, 1, true);
	}
}
