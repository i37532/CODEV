// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>

#include "RegularizedStaVelocityControl.hpp"
#include "VelocityControlSelector.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>

namespace
{
using Kernel = RegularizedStaVelocityControl;
using Status = Kernel::Status;
constexpr float NaN = std::numeric_limits<float>::quiet_NaN();
constexpr float Inf = std::numeric_limits<float>::infinity();
constexpr float Min = std::numeric_limits<float>::min();
constexpr float Tiny = std::numeric_limits<float>::denorm_min();
constexpr float Max = std::numeric_limits<float>::max();

struct Reference {
	double output;
	double next;
};

// Independent evaluation of the original product/saturation definition in
// double, not the implementation's piecewise Psi. Inputs are promoted *after*
// float representation to distinguish conversion error from arithmetic error.
Reference reference(const Kernel::Parameters &p, float s, double nu, float h)
{
	const double error = static_cast<double>(s);
	const double epsilon = static_cast<double>(p.epsilon);
	const double rho = std::max(-1., std::min(1., error / epsilon));
	const double psi = std::sqrt(std::max(std::fabs(error), epsilon)) * rho;
	return {-static_cast<double>(p.lambda1) * psi + nu,
		nu - static_cast<double>(h) * static_cast<double>(p.lambda2) * rho};
}

void nearReference(float actual, double expected, double tolerance = 3.e-6)
{
	EXPECT_NEAR(static_cast<double>(actual), expected, tolerance * std::max(1., std::fabs(expected)));
}

void expectUnchanged(const Kernel &kernel, const std::array<float, 3> &before)
{
	for (size_t axis = 0; axis < before.size(); ++axis) {
		EXPECT_FLOAT_EQ(kernel.state()[axis], before[axis]);
	}
}
}

TEST(RegularizedStaVelocityControl, ParameterDomainIncludesBothClosedEpsilonEndpoints)
{
	EXPECT_TRUE(Kernel::validParameters({.5f, .1f, .001f}));
	EXPECT_TRUE(Kernel::validParameters({2.f, 1.f, 1.f}));
	EXPECT_TRUE(Kernel::validParameters({Min, Max, .01f}));

	for (const float value : {0.f, -1.f, Tiny, NaN, Inf, -Inf}) {
		EXPECT_FALSE(Kernel::validParameters({value, .1f, .01f}));
		EXPECT_FALSE(Kernel::validParameters({.5f, value, .01f}));
	}

	for (const float epsilon : {0.f, -1.f, Tiny, Min, .0001f,
			std::nextafter(.001f, 0.f), std::nextafter(1.f, Inf), NaN, Inf}) {
		EXPECT_FALSE(Kernel::validEpsilon(epsilon));
		EXPECT_FALSE(Kernel::validParameters({.5f, .1f, epsilon}));
		EXPECT_EQ(Kernel::nonlinear(.1f, epsilon).status, Status::InvalidParameters);
	}
}

TEST(RegularizedStaVelocityControl, InvalidConfigurationPreservesStateAndCurrentCandidate)
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

TEST(RegularizedStaVelocityControl, LayerOutputUsesOldNuAndContainsNoFeedForward)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {2.f, 1.f, .25f}));
	ASSERT_TRUE(kernel.reset(0, .7f));
	const auto candidate = kernel.evaluate(0, .625f, .5f, .125f);
	ASSERT_TRUE(candidate.valid());
	EXPECT_FLOAT_EQ(candidate.s, .125f);
	EXPECT_FLOAT_EQ(candidate.nu_before, .7f);
	EXPECT_FLOAT_EQ(candidate.a_sta, -.5f + .7f);
	EXPECT_FLOAT_EQ(candidate.nu_next, .7f - .0625f);
	EXPECT_FLOAT_EQ(kernel.state()[0], .7f);
	const float acceleration_ff = .3f;
	EXPECT_FLOAT_EQ(candidate.a_sta + acceleration_ff, -.5f + .7f + acceleration_ff);
	EXPECT_EQ(kernel.commit(candidate), Status::Ok);
	EXPECT_FLOAT_EQ(kernel.state()[0], candidate.nu_next);
}

TEST(RegularizedStaVelocityControl, ZeroErrorRetainsNonzeroNuAndSkipsUnusedHugeStep)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {Max, Max, .01f}));
	ASSERT_TRUE(kernel.reset(0, -.25f));

	for (const float zero : {0.f, -0.f}) {
		// h*lambda2 would overflow, but rho=0 means the exact increment is 0.
		const auto candidate = kernel.evaluate(0, zero, 0.f, Max);
		ASSERT_TRUE(candidate.valid());
		EXPECT_FLOAT_EQ(candidate.a_sta, -.25f);
		EXPECT_FLOAT_EQ(candidate.nu_next, -.25f);
		EXPECT_EQ(kernel.commit(candidate), Status::Ok);
	}
}

TEST(RegularizedStaVelocityControl, PositiveNegativeSymmetryIncludesNonzeroState)
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
		EXPECT_FLOAT_EQ(n.a_sta, -p.a_sta);
		EXPECT_FLOAT_EQ(n.nu_next, -p.nu_next);
	}
}

TEST(RegularizedStaVelocityControl, ExactBoundaryAndNextafterNeighborsMatchIndependentProduct)
{
	for (const float epsilon : {.001f, .01f, .02f, .25f, 1.f}) {
		const Kernel::Parameters parameters{.5f, .1f, epsilon};
		Kernel kernel;
		ASSERT_TRUE(kernel.setParameters(0, parameters));
		ASSERT_TRUE(kernel.reset(0, .12f));

		for (const float magnitude : {std::nextafter(epsilon, 0.f), epsilon, std::nextafter(epsilon, Inf)}) {
			for (const float sign : {-1.f, 1.f}) {
				const float s = sign * magnitude;
				const auto candidate = kernel.evaluate(0, s, 0.f, .008f);
				ASSERT_TRUE(candidate.valid());
				const auto expected = reference(parameters, s, .12f, .008f);
				nearReference(candidate.a_sta, expected.output);
				nearReference(candidate.nu_next, expected.next);
				const auto shape = Kernel::nonlinear(s, epsilon);
				ASSERT_TRUE(shape.valid());
				EXPECT_LE(std::fabs(shape.rho), 1.f);
			}
		}
	}
}

TEST(RegularizedStaVelocityControl, ShapeIsContinuousOddAndMonotonic)
{
	for (const float epsilon : {.001f, .01f, .02f, 1.f}) {
		const auto left = Kernel::nonlinear(std::nextafter(epsilon, 0.f), epsilon);
		const auto right = Kernel::nonlinear(std::nextafter(epsilon, Inf), epsilon);
		ASSERT_TRUE(left.valid());
		ASSERT_TRUE(right.valid());
		EXPECT_LE(std::fabs(right.psi - left.psi), 8.f * std::numeric_limits<float>::epsilon());
		float previous = -Inf;

		for (int i = -200; i <= 200; ++i) {
			const float s = static_cast<float>(i) * epsilon / 100.f;
			const auto positive = Kernel::nonlinear(s, epsilon);
			const auto negative = Kernel::nonlinear(-s, epsilon);
			ASSERT_TRUE(positive.valid());
			ASSERT_TRUE(negative.valid());
			EXPECT_GE(positive.psi, previous);
			EXPECT_FLOAT_EQ(negative.psi, -positive.psi);
			EXPECT_FLOAT_EQ(negative.rho, -positive.rho);
			previous = positive.psi;
		}
	}
}

TEST(RegularizedStaVelocityControl, OuterLayerDoesNotEvaluateOverflowingErrorOverEpsilon)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {.5f, .1f, .001f}));

	for (const float s : {-Max, Max}) {
		const auto shape = Kernel::nonlinear(s, .001f);
		ASSERT_TRUE(shape.valid());
		EXPECT_EQ(std::fabs(shape.rho), 1.f);
		const auto candidate = kernel.evaluate(0, s, 0.f, .008f);
		ASSERT_TRUE(candidate.valid());
		EXPECT_TRUE(std::isfinite(candidate.a_sta));
		EXPECT_EQ(std::signbit(candidate.a_sta), !std::signbit(s));
	}
}

TEST(RegularizedStaVelocityControl, InvalidInputsAndErrorSubtractionOverflowAreAtomic)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {.5f, .1f, .01f}));
	ASSERT_TRUE(kernel.reset(0, .2f));
	const auto before = kernel.state();

	for (const float value : {NaN, Inf, -Inf}) {
		EXPECT_EQ(kernel.evaluate(0, value, 0.f, .01f).status, Status::InvalidInput);
		EXPECT_EQ(kernel.evaluate(0, 0.f, value, .01f).status, Status::InvalidInput);
		EXPECT_EQ(Kernel::nonlinear(value, .01f).status, Status::InvalidInput);
		EXPECT_FALSE(kernel.reset(0, value));
	}

	EXPECT_EQ(kernel.evaluate(0, Max, -Max, .01f).status, Status::NumericalError);
	expectUnchanged(kernel, before);
}

TEST(RegularizedStaVelocityControl, InvalidDtIsRejectedWithoutClamping)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {.5f, .1f, .01f}));
	const auto before = kernel.state();

	for (const float h : {0.f, -0.f, -.01f, Tiny, NaN, Inf, -Inf}) {
		const auto candidate = kernel.evaluate(0, .1f, 0.f, h);
		EXPECT_EQ(candidate.status, Status::InvalidDt);
		EXPECT_EQ(kernel.commit(candidate), Status::InvalidDt);
	}

	// The pure kernel is not the later adapter's 2..40ms timing guard.
	ASSERT_TRUE(kernel.evaluate(0, .1f, 0.f, .05f).valid());
	expectUnchanged(kernel, before);
}

TEST(RegularizedStaVelocityControl, CorrectionProductOverflowIsRejected)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {Max, .1f, .01f}));
	const auto candidate = kernel.evaluate(0, 4.f, 0.f, .01f);
	EXPECT_EQ(candidate.status, Status::NumericalError);
	EXPECT_EQ(kernel.commit(candidate), Status::NumericalError);
	EXPECT_FLOAT_EQ(kernel.state()[0], 0.f);
}

TEST(RegularizedStaVelocityControl, OutputAndNextStateOverflowAreRejected)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {Max, Max, .01f}));
	ASSERT_TRUE(kernel.reset(0, -Max));
	EXPECT_EQ(kernel.evaluate(0, 1.f, 0.f, .5f).status, Status::NumericalError);
	ASSERT_TRUE(kernel.setParameters(0, {.5f, Max, .01f}));
	EXPECT_EQ(kernel.evaluate(0, 1.f, 0.f, 1.f).status, Status::NumericalError);
	EXPECT_FLOAT_EQ(kernel.state()[0], -Max);
}

TEST(RegularizedStaVelocityControl, NonzeroIntermediateStepOverflowIsExplicitlyRejected)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {.5f, Max, .01f}));
	// Deliberately outside the documented float intermediate domain. Even if
	// small rho could recover a finite real result, overflow is not a hold.
	EXPECT_EQ(kernel.evaluate(0, 1.e-5f, 0.f, 2.f).status, Status::NumericalError);
	EXPECT_FLOAT_EQ(kernel.state()[0], 0.f);
}

TEST(RegularizedStaVelocityControl, TrueSubnormalProductsRejectWithoutChangingState)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {Min, .1f, .01f}));
	EXPECT_EQ(kernel.evaluate(0, .005f, 0.f, .01f).status, Status::NumericalError);
	ASSERT_TRUE(kernel.setParameters(0, {.5f, Min, .01f}));
	EXPECT_EQ(kernel.evaluate(0, .01f, 0.f, .01f).status, Status::NumericalError);
	ASSERT_TRUE(kernel.setParameters(0, {.5f, Min, 1.f}));
	EXPECT_EQ(kernel.evaluate(0, .5f, 0.f, 1.f).status, Status::NumericalError);
	EXPECT_EQ(Kernel::nonlinear(Tiny, 1.f).status, Status::NumericalError);
	EXPECT_FLOAT_EQ(kernel.state()[0], 0.f);
}

TEST(RegularizedStaVelocityControl, OrdinaryAdditionRoundingIsNotProductUnderflow)
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

TEST(RegularizedStaVelocityControl, AxisStateAndCandidateGenerationsAreIndependent)
{
	Kernel kernel;
	std::array<Kernel::Candidate, 3> candidates{};

	for (size_t axis = 0; axis < 3; ++axis) {
		ASSERT_TRUE(kernel.setParameters(axis, {.5f, .1f, .01f}));
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

TEST(RegularizedStaVelocityControl, ResetToSameValueAndGlobalResetInvalidateCandidates)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {.5f, .1f, .01f}));
	ASSERT_TRUE(kernel.reset(0, .2f));
	const auto before = kernel.evaluate(0, .1f, 0.f, .01f);
	ASSERT_TRUE(kernel.reset(0, .2f));
	EXPECT_EQ(kernel.commit(before), Status::StaleCandidate);
	const auto next = kernel.evaluate(0, .1f, 0.f, .01f);
	kernel.reset();
	EXPECT_EQ(kernel.commit(next), Status::StaleCandidate);
	EXPECT_FLOAT_EQ(kernel.state()[0], 0.f);
	EXPECT_TRUE(kernel.evaluate(0, .1f, 0.f, .01f).valid());
}

TEST(RegularizedStaVelocityControl, EpsilonOnlyGainOnlyAndEqualConfigurationInvalidate)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {.5f, .1f, .01f}));

	for (const Kernel::Parameters &p : {Kernel::Parameters{.5f, .1f, .02f}, {.6f, .1f, .02f},
			{.6f, .2f, .02f}, {.6f, .2f, .02f}}) {
		const auto previous = kernel.evaluate(0, .1f, 0.f, .01f);
		ASSERT_TRUE(previous.valid());
		ASSERT_TRUE(kernel.setParameters(0, p));
		EXPECT_EQ(kernel.commit(previous), Status::StaleCandidate);
	}
}

TEST(RegularizedStaVelocityControl, CandidateCanOnlyCommitOnceIncludingSameNu)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {.5f, .1f, .01f}));
	const auto zero = kernel.evaluate(0, 0.f, 0.f, .01f);
	ASSERT_TRUE(zero.valid());
	EXPECT_EQ(kernel.commit(zero), Status::Ok);
	EXPECT_EQ(kernel.commit(zero), Status::StaleCandidate);
	const auto positive = kernel.evaluate(0, .1f, 0.f, .01f);
	EXPECT_EQ(kernel.commitProtected(positive, 0.f), Status::Ok);
	EXPECT_EQ(kernel.commit(positive), Status::StaleCandidate);
}

TEST(RegularizedStaVelocityControl, OwnerAxisRevisionAndAllPublicPayloadFieldsAreSealed)
{
	Kernel first;
	Kernel second;
	ASSERT_TRUE(first.setParameters(0, {.5f, .1f, .01f}));
	ASSERT_TRUE(first.setParameters(1, {.5f, .1f, .01f}));
	ASSERT_TRUE(second.setParameters(0, {.5f, .1f, .01f}));
	const auto original = first.evaluate(0, .1f, 0.f, .01f);
	ASSERT_TRUE(original.valid());
	EXPECT_EQ(second.commit(original), Status::StaleCandidate);

	for (int mutation = 0; mutation < 7; ++mutation) {
		auto changed = original;

		switch (mutation) {
		case 0: changed.axis = 1; break;
		case 1: ++changed.revision; break;
		case 2: changed.s = 0.f; break;
		case 3: changed.a_sta = 0.f; break;
		case 4: changed.nu_before = -0.f; break; // Bitwise seal distinguishes signed zero.
		case 5: changed.nu_next = 0.f; break;
		default: changed.status = Status::NumericalError; break;
		}

		EXPECT_FALSE(first.current(changed));
		EXPECT_NE(first.commit(changed), Status::Ok);
		EXPECT_TRUE(first.current(original));
	}

	Kernel::Candidate forged{};
	forged.status = Status::Ok;
	forged.axis = 0;
	EXPECT_EQ(first.commit(forged), Status::StaleCandidate);
	EXPECT_EQ(first.commit(original), Status::Ok);
}

TEST(RegularizedStaVelocityControl, ProtectedCommitKeepsIdealOutputAndSealedCandidate)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {.5f, .1f, .01f}));
	ASSERT_TRUE(kernel.reset(0, .2f));
	const auto candidate = kernel.evaluate(0, .1f, 0.f, .012f);
	ASSERT_TRUE(candidate.valid());
	const float original_output = candidate.a_sta;
	const float ideal_next = candidate.nu_next;
	EXPECT_EQ(kernel.commitProtected(candidate, -.05f), Status::Ok);
	EXPECT_FLOAT_EQ(kernel.state()[0], -.05f);
	EXPECT_FLOAT_EQ(candidate.a_sta, original_output);
	EXPECT_FLOAT_EQ(candidate.nu_next, ideal_next);
	EXPECT_NE(kernel.state()[0], candidate.nu_next);
	EXPECT_EQ(kernel.commit(candidate), Status::StaleCandidate);
}

TEST(RegularizedStaVelocityControl, InvalidProtectedStateDoesNotConsumeCandidate)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {.5f, .1f, .01f}));
	const auto candidate = kernel.evaluate(0, .1f, 0.f, .01f);

	for (const float applied : {NaN, Inf, -Inf}) {
		EXPECT_EQ(kernel.commitProtected(candidate, applied), Status::StaleCandidate);
		EXPECT_TRUE(kernel.current(candidate));
		EXPECT_FLOAT_EQ(kernel.state()[0], 0.f);
	}

	EXPECT_EQ(kernel.commit(candidate), Status::Ok);
}

TEST(RegularizedStaVelocityControl, UnconfiguredInvalidAxisAndResetValidation)
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

TEST(RegularizedStaVelocityControl, FloatOneStepGridMatchesOriginalDoubleDefinition)
{
	for (const float epsilon : {.001f, .01f, .02f, 1.f}) {
		for (const float lambda1 : {.1f, .5f, 2.f}) {
			for (const float lambda2 : {.01f, .1f, 1.f}) {
				const Kernel::Parameters p{lambda1, lambda2, epsilon};
				Kernel kernel;
				ASSERT_TRUE(kernel.setParameters(0, p));

				for (const float error_scale : {-10.f, -1.f, -.5f, -.001f, 0.f, .001f, .5f, 1.f, 10.f}) {
					const float s = error_scale * epsilon;

					for (const float nu : {-.2f, 0.f, .8f}) {
						for (const float h : {.008f, .012f, .04f}) {
							ASSERT_TRUE(kernel.reset(0, nu));
							const auto candidate = kernel.evaluate(0, s, 0.f, h);
							ASSERT_TRUE(candidate.valid());
							const auto expected = reference(p, s, static_cast<double>(nu), h);
							nearReference(candidate.a_sta, expected.output);
							nearReference(candidate.nu_next, expected.next);
						}
					}
				}
			}
		}
	}
}

TEST(RegularizedStaVelocityControl, EightTwelveMillisecondSequencesTrackIndependentDoubleState)
{
	for (const Kernel::Parameters &p : {Kernel::Parameters{.5f, .1f, .01f}, {2.f, 1.f, .02f}}) {
		Kernel kernel;
		ASSERT_TRUE(kernel.setParameters(0, p));
		ASSERT_TRUE(kernel.reset(0, .2f));
		double reference_nu = static_cast<double>(.2f);

		for (int k = 0; k < 2048; ++k) {
			const float velocity = .2f * std::sin(static_cast<float>(k) * .03f);
			const float setpoint = .1f * std::cos(static_cast<float>(k) * .017f);
			const float h = k % 2 == 0 ? .008f : .012f;
			const auto candidate = kernel.evaluate(0, velocity, setpoint, h);
			ASSERT_TRUE(candidate.valid());
			const auto expected = reference(p, velocity - setpoint, reference_nu, h);
			nearReference(candidate.a_sta, expected.output, 2.e-5);
			nearReference(candidate.nu_next, expected.next, 2.e-5);
			ASSERT_EQ(kernel.commit(candidate), Status::Ok);
			reference_nu = expected.next;
		}
	}
}

TEST(RegularizedStaVelocityControl, InnerLayerMatchesIndependentLinearStateTransition)
{
	const Kernel::Parameters p{.5f, .1f, .01f};
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, p));
	const double epsilon = static_cast<double>(p.epsilon);
	const double alpha = static_cast<double>(p.lambda1) / std::sqrt(epsilon);
	const double beta = static_cast<double>(p.lambda2) / epsilon;

	for (const float s : {-.005f, -.0001f, 0.f, .0001f, .005f}) {
		const float nu = .02f;
		const float h = .012f;
		ASSERT_TRUE(kernel.reset(0, nu));
		const auto candidate = kernel.evaluate(0, s, 0.f, h);
		ASSERT_TRUE(candidate.valid());
		const double error_next = (1. - static_cast<double>(h) * alpha) * static_cast<double>(s)
					 + static_cast<double>(h) * static_cast<double>(nu);
		const double state_next = static_cast<double>(nu) - static_cast<double>(h) * beta * static_cast<double>(s);
		nearReference(s + h * candidate.a_sta, error_next);
		nearReference(candidate.nu_next, state_next);
	}
}

TEST(RegularizedStaVelocityControl, NewModeCannotDisplacePidOrLegacyEsta)
{
	VelocityControlSelector selector;
	selector.configure(3, 1, false, true, 1);
	EXPECT_NE(selector.reject(), VelocityControlSelector::None);
	EXPECT_EQ(selector.requestedMode(), 3);
	EXPECT_EQ(selector.effectiveMode(), 0);
	EXPECT_EQ(selector.effectiveAxes(), 0);
	selector.configure(1, 7, false, true, 7);
	ASSERT_EQ(selector.reject(), VelocityControlSelector::None);
	ASSERT_EQ(selector.effectiveMode(), 1);
	ASSERT_EQ(selector.effectiveAxes(), 7);

	for (const bool armed : {true, false}) {
		selector.configure(3, 7, armed, true, 7);
		EXPECT_NE(selector.reject(), VelocityControlSelector::None);
		EXPECT_EQ(selector.effectiveMode(), 1);
		EXPECT_EQ(selector.effectiveAxes(), 7);
		EXPECT_EQ(selector.pending(), armed);
	}

	selector.configure(2, 0, false);
	EXPECT_NE(selector.reject(), VelocityControlSelector::None);
	EXPECT_EQ(selector.effectiveMode(), 1);
}
