// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>
#include "StaVelocityProtection.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>

namespace
{
using Guard = StaVelocityProtection;
using Core = RegularizedIstaVelocityControl;

Guard::Config config(uint8_t axes = 7)
{
	Guard::Config c{};
	c.axes = axes;
	c.variant = 4;
	c.gains[0] = {.5f, .1f}; c.gains[1] = {.5f, .1f}; c.gains[2] = {2.f, 1.f};
	c.epsilon = {{.01f, .01f, .02f}};
	c.nu_limit = {{.4f, .4f, 4.f}};
	c.acceleration_limit = {{.8f, .8f, 6.f}};
	return c;
}

Guard::Frame flying(uint64_t sample = 1000000)
{
	Guard::Frame f{};
	f.sample = sample;
	f.armed = f.enabled = f.flying = true;
	f.landed = f.contact = false;
	f.velocity = {{.05f, -.04f, .03f}};
	f.target = {{0.f, 0.f, 0.f}};
	f.ff = {{.02f, -.03f, .04f}};
	return f;
}

void prime(Guard &g, Guard::Frame &f, uint32_t step = 8000)
{
	EXPECT_TRUE(g.begin(f).flags & Guard::Priming);
	f.sample += step;
}

void sameState(const Guard::Vec &actual, const Guard::Vec &expected)
{
	EXPECT_EQ(memcmp(actual.data(), expected.data(), sizeof(actual)), 0);
}

double rho(double p, double epsilon)
{
	return std::max(-1., std::min(1., p / epsilon));
}

double psi(double p, double epsilon)
{
	return std::sqrt(std::max(std::fabs(p), epsilon)) * rho(p, epsilon);
}

double root(double s, double h, double l1, double l2, double epsilon)
{
	// Independent monotone residual bisection, NOT the production piecewise
	// formula or rationalized square root. The zero function is exactly known.
	if (std::fabs(s) <= 0.) { return 0.; }

	double low = -std::fabs(s), high = std::fabs(s);

	for (int i = 0; i < 180; ++i) {
		const double middle = low + (high - low) * .5;
		const double residual = middle + h * l1 * psi(middle, epsilon) + h * h * l2 * rho(middle, epsilon) - s;

		if (residual < 0.) { low = middle; } else { high = middle; }
	}

	return low + (high - low) * .5;
}

void checkIdeal(const Guard::Result &r, const Guard::Config &c)
{
	for (size_t i = 0; i < 3; ++i) {
		if (!(r.candidate_axes & (1u << i))) { continue; }

		const double h = static_cast<double>(r.kernel_dt);
		const double l1 = static_cast<double>(c.gains[i].lambda1);
		const double l2 = static_cast<double>(c.gains[i].lambda2);
		const double eps = static_cast<double>(c.epsilon[i]);
		const double p = root(static_cast<double>(r.s[i]), h, l1, l2, eps);
		const double nu = static_cast<double>(r.nu_before[i]) - h * l2 * rho(p, eps);
		const double output = -l1 * psi(p, eps) + nu;
		EXPECT_NEAR(static_cast<double>(r.p[i]), p, 2e-7);
		EXPECT_NEAR(static_cast<double>(r.nu_ideal[i]), nu, 2e-7);
		EXPECT_NEAR(static_cast<double>(r.a_sta[i]), output, 2e-6);
		const double residual = static_cast<double>(r.p[i])
					+ h * l1 * psi(static_cast<double>(r.p[i]), eps)
					+ h * h * l2 * rho(static_cast<double>(r.p[i]), eps) - static_cast<double>(r.s[i]);
		EXPECT_NEAR(residual, 0., 2e-7);
	}
}
}

TEST(RegularizedIstaProtection, AllAdmissibleMasksUseCandidateNuAndSingleFeedforward)
{
	for (const uint8_t axes : {1, 3, 4, 7}) {
		for (const uint32_t step : {8000, 12000}) {
			Guard g;
			const auto c = config(axes);
			ASSERT_TRUE(g.configure(c, false));
			auto f = flying(); prime(g, f, step);

			for (int repetition = 0; repetition < 3; ++repetition) {
				const auto before = g.state();
				const auto candidate = g.begin(f);
				ASSERT_EQ(candidate.fault, 0);
				ASSERT_EQ(candidate.candidate_axes, axes);
				checkIdeal(candidate, c);
				sameState(g.state(), before);

				for (size_t i = 0; i < 3; ++i) {
					if (!(axes & (1u << i))) { continue; }

					EXPECT_FLOAT_EQ(candidate.a_req[i], candidate.a_sta[i] + f.ff[i]);
					EXPECT_GT(fabsf(candidate.nu_ideal[i] - candidate.nu_before[i]), 1e-6f);
				}

				const auto applied = g.finish(candidate.a_req, 0, true);
				ASSERT_EQ(applied.committed_axes, axes);
				EXPECT_EQ(applied.strict_axes, axes);
				sameState(g.state(), applied.nu_ideal);
				f.sample += step == 8000 ? 12000 : 8000;
			}
		}
	}
}

TEST(RegularizedIstaProtection, PositiveNegativeSaturationFreezesOutwardThenAllowsInwardAndRelease)
{
	for (const float direction : {-1.f, 1.f}) {
		Guard g;
		ASSERT_TRUE(g.configure(config(1), false));
		auto f = flying(); f.velocity[0] *= direction; prime(g, f);
		auto candidate = g.begin(f);
		auto proxy = candidate.a_req; proxy[0] += direction;
		auto applied = g.finish(proxy, 1, true);
		EXPECT_TRUE(applied.flags & Guard::OutwardFreeze);
		EXPECT_FLOAT_EQ(g.state()[0], 0.f);
		EXPECT_EQ(applied.strict_axes, 0);
		EXPECT_FLOAT_EQ(applied.a_sta[0], candidate.a_sta[0]);
		EXPECT_FLOAT_EQ(applied.a_req[0], candidate.a_req[0]);
		f.sample += 12000; candidate = g.begin(f);
		proxy = candidate.a_req; proxy[0] -= direction;
		applied = g.finish(proxy, 1, true);
		EXPECT_FALSE(applied.flags & Guard::OutwardFreeze);
		EXPECT_LT(g.state()[0] * direction, 0.f);
		EXPECT_EQ(applied.strict_axes, 0); // Real downstream limit remains.
		f.sample += 8000; candidate = g.begin(f);
		applied = g.finish(candidate.a_req, 0, true);
		EXPECT_EQ(applied.strict_axes, 1);
		EXPECT_EQ(applied.committed_axes, 1);
	}
}

TEST(RegularizedIstaProtection, StateAndCorrectionLimitsNeverReconstructCurrentIdealOutput)
{
	for (const bool limit_state : {false, true}) {
		Guard g;
		auto c = config(1);

		if (limit_state) { c.nu_limit[0] = .00001f; } else { c.acceleration_limit[0] = .001f; }

		ASSERT_TRUE(g.configure(c, false));
		auto f = flying(); prime(g, f);
		const auto candidate = g.begin(f);
		const auto applied = g.finish(candidate.a_req, 0, true);
		EXPECT_EQ(applied.committed_axes, 1);
		EXPECT_EQ(applied.strict_axes, 0);
		EXPECT_FLOAT_EQ(applied.a_sta[0], candidate.a_sta[0]);
		EXPECT_FLOAT_EQ(applied.a_req[0], candidate.a_req[0]);
		EXPECT_GT(fabsf(applied.nu_applied[0] - applied.nu_ideal[0]), 1e-6f);

		if (limit_state) {
			EXPECT_TRUE(applied.flags & Guard::StateLimit);
			EXPECT_FLOAT_EQ(applied.nu_applied[0], -c.nu_limit[0]);

		} else {
			EXPECT_TRUE(applied.flags & Guard::CorrectionLimit);
			EXPECT_TRUE(applied.flags & Guard::OutwardFreeze);
			EXPECT_FLOAT_EQ(applied.correction_applied[0], -.001f);
			EXPECT_FLOAT_EQ(applied.a_req[0], -.001f + f.ff[0]);
		}
	}
}

TEST(RegularizedIstaProtection, HorizontalAndZPriorityFeedbackIsAtomicAndNotBodyMixerSigns)
{
	Guard g; ASSERT_TRUE(g.configure(config(), false));
	auto f = flying(); prime(g, f);
	const auto candidate = g.begin(f);
	auto proxy = candidate.a_req;
	proxy[0] += .1f; proxy[1] -= .1f; proxy[2] += .1f;
	const auto applied = g.finish(proxy, 7, true);
	EXPECT_EQ(applied.committed_axes, 7);
	EXPECT_EQ(applied.strict_axes, 0);
	EXPECT_TRUE(applied.flags & Guard::OutwardFreeze);
	sameState(g.state(), {{0.f, 0.f, 0.f}});
	// Component mismatch without real constraint bits is not an instruction to
	// freeze. A thrust-map proxy is neither measured acceleration nor mixer bits.
	f.sample += 12000;
	const auto next = g.begin(f);
	const auto free = g.finish(proxy, 0, true);
	EXPECT_EQ(free.strict_axes, 7);
	sameState(g.state(), next.nu_ideal);
}

TEST(RegularizedIstaProtection, LastAxisBadFeedbackCannotPartiallyCommitOrClaimStrict)
{
	for (const bool valid : {false, true}) {
		Guard g; ASSERT_TRUE(g.configure(config(), false));
		auto f = flying(); prime(g, f);
		const auto before = g.state();
		const auto candidate = g.begin(f);
		auto proxy = candidate.a_req;

		if (valid) { proxy[2] = NAN; }

		const auto failed = g.finish(proxy, 0, valid);
		EXPECT_TRUE(failed.fault & Guard::Feedback);
		EXPECT_EQ(failed.committed_axes, 0);
		EXPECT_EQ(failed.strict_axes, 0);
		sameState(g.state(), before);
		f.sample += 12000;
		EXPECT_TRUE(g.begin(f).flags & Guard::Latched);
		f.armed = false; f.sample += 8000;
		EXPECT_EQ(g.begin(f).fault, 0);
		f.armed = true; f.sample += 12000;
		EXPECT_TRUE(g.begin(f).flags & Guard::Priming);
	}
}

TEST(RegularizedIstaProtection, LastAxisNumericalFailurePreservesAllPreviousStates)
{
	Guard g; ASSERT_TRUE(g.configure(config(), false));
	auto f = flying(); prime(g, f);
	const auto accepted = g.begin(f); g.finish(accepted.a_req, 0, true);
	const auto before = g.state();
	f.sample += 12000;
	f.velocity[2] = std::numeric_limits<float>::max();
	f.target[2] = -std::numeric_limits<float>::max();
	const auto failed = g.begin(f);
	EXPECT_TRUE(failed.fault & Guard::Numerical);
	EXPECT_EQ(failed.committed_axes, 0);
	EXPECT_EQ(failed.strict_axes, 0);
	sameState(g.state(), before);
	EXPECT_EQ(g.finish({{0.f, 0.f, 0.f}}, 0, true).committed_axes, 0);
	sameState(g.state(), before);
}

TEST(RegularizedIstaProtection, SubnormalNumericsLatchWithoutSilentZeroOrAutomaticRecovery)
{
	Guard g; ASSERT_TRUE(g.configure(config(1), false));
	auto f = flying(); prime(g, f);
	const auto accepted = g.begin(f); g.finish(accepted.a_req, 0, true);
	const auto before = g.state();
	f.sample += 12000;
	f.velocity[0] = std::numeric_limits<float>::denorm_min();
	EXPECT_TRUE(g.begin(f).fault & Guard::Numerical);
	sameState(g.state(), before);
	f.sample += 8000; f.velocity[0] = .05f;
	EXPECT_TRUE(g.begin(f).flags & Guard::Latched);
	sameState(g.state(), before);
	f.armed = false; f.sample += 12000;
	EXPECT_EQ(g.begin(f).fault, 0);
	sameState(g.state(), {{0.f, 0.f, 0.f}});
	f.armed = true; f.sample += 8000;
	EXPECT_TRUE(g.begin(f).flags & Guard::Priming);
}

TEST(RegularizedIstaProtection, DuplicateAndRepeatedFinishCannotClaimAnotherCommit)
{
	Guard g; ASSERT_TRUE(g.configure(config(), false));
	auto f = flying(); prime(g, f);
	const auto candidate = g.begin(f);
	ASSERT_EQ(g.finish(candidate.a_req, 0, true).committed_axes, 7);
	const auto before = g.state();
	const auto repeated = g.finish(candidate.a_req, 0, true);
	EXPECT_EQ(repeated.committed_axes, 0);
	EXPECT_EQ(repeated.strict_axes, 0);
	sameState(g.state(), before);
	f.target = {{.02f, .02f, -.02f}};
	EXPECT_TRUE(g.begin(f).flags & Guard::Duplicate);
	EXPECT_EQ(g.finish(candidate.a_req, 0, true).committed_axes, 0);
	sameState(g.state(), before);
	f.contact = true;
	EXPECT_TRUE(g.begin(f).flags & Guard::Inactive);
	sameState(g.state(), {{0.f, 0.f, 0.f}});
}

TEST(RegularizedIstaProtection, TimeDomainIsUnclampedAndModeFourRequiresDivisorOne)
{
	for (const int64_t step : {-8000, 1000, 41000, 2000000}) {
		Guard g; ASSERT_TRUE(g.configure(config(), false));
		auto f = flying(); g.begin(f);
		f.sample = static_cast<uint64_t>(static_cast<int64_t>(f.sample) + step);
		EXPECT_TRUE(g.begin(f).fault & Guard::Time);
		sameState(g.state(), {{0.f, 0.f, 0.f}});
	}

	for (const uint8_t divisor : {2, 4}) {
		Guard g; ASSERT_TRUE(g.configure(config(), false));
		auto f = flying(); f.divisor = divisor;
		EXPECT_TRUE(g.begin(f).fault & Guard::Time);
	}

	for (const float h : {.001f, .041f, .012f, -.008f, NAN, INFINITY}) {
		Guard g; ASSERT_TRUE(g.configure(config(), false));
		auto f = flying(); prime(g, f); f.integration_dt = h;
		EXPECT_TRUE(g.begin(f).fault & Guard::Time);
	}

	for (const uint32_t us : {2000, 8000, 12000, 40000}) {
		Guard g; ASSERT_TRUE(g.configure(config(), false));
		auto f = flying(); prime(g, f, us);
		const auto candidate = g.begin(f);
		EXPECT_EQ(candidate.fault, 0);
		EXPECT_FLOAT_EQ(candidate.kernel_dt, candidate.raw_dt);
		EXPECT_EQ(g.finish(candidate.a_req, 0, true).committed_axes, 7);
	}
}

TEST(RegularizedIstaProtection, NaNPairsPureAccelerationExitAndReentryResetBeforeReuse)
{
	Guard g; ASSERT_TRUE(g.configure(config(), false));
	auto f = flying(); prime(g, f);
	auto candidate = g.begin(f); g.finish(candidate.a_req, 0, true);
	f.sample += 12000; f.target = {{NAN, NAN, NAN}};
	auto r = g.begin(f);
	EXPECT_TRUE(r.flags & Guard::Inactive);
	EXPECT_EQ(r.candidate_axes, 0);
	sameState(g.state(), {{0.f, 0.f, 0.f}});
	f.sample += 8000; f.target = {{0.f, 0.f, 0.f}};
	EXPECT_TRUE(g.begin(f).flags & Guard::Priming);
	f.sample += 12000; f.target[1] = NAN;
	EXPECT_TRUE(g.begin(f).fault & Guard::Measurement);
	f.sample += 8000; f.target[1] = 0.f;
	EXPECT_TRUE(g.begin(f).flags & Guard::Latched);
}

TEST(RegularizedIstaProtection, ActiveSubsetChangeReseedsAllAndNeverRetainsInactiveZ)
{
	Guard g; ASSERT_TRUE(g.configure(config(), false));
	auto f = flying(); prime(g, f);
	auto candidate = g.begin(f); g.finish(candidate.a_req, 0, true);
	f.sample += 12000; f.target[2] = NAN;
	const auto xy = g.begin(f);
	EXPECT_TRUE(xy.flags & Guard::Priming);
	EXPECT_EQ(xy.active_axes, 3);
	sameState(g.state(), {{0.f, 0.f, 0.f}});
	ASSERT_TRUE(g.seedXYZ({{.1f, -.1f, NAN}}));
	EXPECT_FLOAT_EQ(g.state()[2], 0.f);
	f.sample += 8000; f.target[2] = 0.f;
	EXPECT_TRUE(g.begin(f).flags & Guard::Priming);
	sameState(g.state(), {{0.f, 0.f, 0.f}});
}

TEST(RegularizedIstaProtection, NonfiniteMeasurementOrFeedforwardAndInnerFeedbackLatch)
{
	for (int kind = 0; kind < 5; ++kind) {
		Guard g; ASSERT_TRUE(g.configure(config(), false));
		auto f = flying(); prime(g, f);

		if (kind == 0) { f.velocity[2] = NAN; }

		if (kind == 1) { f.target[2] = INFINITY; }

		if (kind == 2) { f.ff[2] = INFINITY; }

		if (kind == 3) { f.velocity[2] = INFINITY; }

		if (kind == 4) { f.inner_valid = false; }

		EXPECT_NE(g.begin(f).fault, 0);
		sameState(g.state(), {{0.f, 0.f, 0.f}});
	}
}

TEST(RegularizedIstaProtection, GroundRampFalseTakeoffCancelBounceTimeoutAndDisarm)
{
	for (int kind = 0; kind < 5; ++kind) {
		Guard g; ASSERT_TRUE(g.configure(config(), false));
		auto f = flying(); prime(g, f);
		const auto candidate = g.begin(f); g.finish(candidate.a_req, 0, true);
		f.sample += 12000;

		if (kind == 0) { f.landed = true; }

		if (kind == 1) { f.contact = true; }

		if (kind == 2) { f.flying = false; }

		if (kind == 3) { f.enabled = false; }

		if (kind == 4) { f.armed = false; }

		for (int dwell = 0; dwell < 500; ++dwell) {
			EXPECT_TRUE(g.begin(f).flags & Guard::Inactive);
			sameState(g.state(), {{0.f, 0.f, 0.f}});
			f.sample += 8000;
		}

		f.armed = f.enabled = f.flying = true; f.landed = f.contact = false;
		EXPECT_TRUE(g.begin(f).flags & Guard::Priming);
		f.sample += 12000;
		const auto next = g.begin(f);
		EXPECT_EQ(g.finish(next.a_req, 0, true).committed_axes, 7);
	}
}

TEST(RegularizedIstaProtection, CovariantVelocityResetPreservesNuUnmatchedResetLatches)
{
	Guard g; ASSERT_TRUE(g.configure(config(1), false));
	auto f = flying(); prime(g, f);
	const auto first = g.begin(f); g.finish(first.a_req, 0, true);
	const auto before = g.state();
	f.sample += 12000; f.velocity[0] += 4.f; f.target[0] += 4.f;
	const auto shifted = g.begin(f);
	EXPECT_FLOAT_EQ(shifted.nu_before[0], before[0]);
	EXPECT_NEAR(shifted.s[0], .05f, 3e-7f);
	g.finish(shifted.a_req, 0, true);
	f.sample += 8000; f.unmatched_reset_axes = 4;
	EXPECT_EQ(g.begin(f).fault, 0);
	f.sample += 12000; f.unmatched_reset_axes = 1;
	EXPECT_TRUE(g.begin(f).fault & Guard::ResetMismatch);
}

TEST(RegularizedIstaProtection, ArmedConfigurationPendingCancelAndDisarmInvalidatesCandidates)
{
	Guard g; auto original = config(); ASSERT_TRUE(g.configure(original, false));
	auto f = flying(); prime(g, f);
	const auto candidate = g.begin(f);
	const auto generation = g.generation();
	auto changed = original; changed.epsilon[2] *= 2.f;
	ASSERT_TRUE(g.configure(changed, true));
	EXPECT_TRUE(g.pending()); EXPECT_EQ(g.generation(), generation);
	ASSERT_TRUE(g.configure(original, true)); EXPECT_FALSE(g.pending());
	ASSERT_TRUE(g.configure(changed, false)); EXPECT_GT(g.generation(), generation);
	EXPECT_EQ(g.finish(candidate.a_req, 0, true).committed_axes, 0);
	sameState(g.state(), {{0.f, 0.f, 0.f}});
	f.sample += 12000; EXPECT_TRUE(g.begin(f).flags & Guard::Priming);
	changed.epsilon[2] = NAN;
	EXPECT_FALSE(g.configure(changed, true)); EXPECT_TRUE(g.rejected());
	EXPECT_TRUE(g.pending());
}

TEST(RegularizedIstaProtection, SeedInvertsImplicitOutputAtActualEightAndTwelveMilliseconds)
{
	for (const uint8_t axes : {4, 7}) {
		for (const uint32_t step : {8000, 12000}) {
			Guard g; const auto c = config(axes); ASSERT_TRUE(g.configure(c, false));
			auto f = flying(); f.flying = false; g.begin(f);
			f.sample += step; f.flying = true;
			ASSERT_TRUE(g.begin(f).flags & Guard::Priming);
			const float h = g.result().raw_dt;
			Guard::Vec seeds{};
			const Guard::Vec desired{{.06f, -.05f, .12f}};

			for (size_t i = 0; i < 3; ++i) {
				if (!(axes & (1u << i))) { continue; }

				const float s = f.velocity[i] - f.target[i];
				ASSERT_TRUE(g.implicitSeed(i, s, desired[i], seeds[i]));
				const double l1 = static_cast<double>(c.gains[i].lambda1);
				const double l2 = static_cast<double>(c.gains[i].lambda2);
				const double epsilon = static_cast<double>(c.epsilon[i]);
				const double hd = static_cast<double>(h);
				const double p = root(static_cast<double>(s), hd, l1, l2, epsilon);
				const double expected = static_cast<double>(desired[i]) + l1 * psi(p, epsilon) + hd * l2 * rho(p, epsilon);
				EXPECT_NEAR(static_cast<double>(seeds[i]), expected, 2e-7);
				const double explicit_seed = static_cast<double>(desired[i]) + l1 * psi(static_cast<double>(s), epsilon);
				EXPECT_GT(std::fabs(static_cast<double>(seeds[i]) - explicit_seed), 1e-6);
			}

			ASSERT_TRUE(axes == 4 ? g.seedZ(seeds[2]) : g.seedXYZ(seeds));
			sameState(g.state(), seeds);
			EXPECT_FLOAT_EQ(g.result().seed_dt, h);
			f.sample += step;
			const auto candidate = g.begin(f);
			checkIdeal(candidate, c);

			for (size_t i = 0; i < 3; ++i) {
				if (axes & (1u << i)) { EXPECT_NEAR(candidate.a_sta[i], desired[i], 3e-7f); }
			}

			g.finish(candidate.a_req, 0, true);
			f.sample += step == 8000 ? 12000 : 8000;
			checkIdeal(g.begin(f), c); // New h is not assumed to preserve prior output.
		}
	}
}

TEST(RegularizedIstaProtection, SeedRejectsMissingRealIntervalAndInvalidLastAxisAtomically)
{
	Guard no_history; ASSERT_TRUE(no_history.configure(config(4), false));
	auto f = flying(); ASSERT_TRUE(no_history.begin(f).flags & Guard::Priming);
	float nu{};
	EXPECT_FALSE(no_history.implicitSeed(2, .03f, .12f, nu));
	EXPECT_TRUE(no_history.result().fault & Guard::Numerical);

	for (const float invalid : {NAN, INFINITY, 5.f, std::numeric_limits<float>::denorm_min()}) {
		Guard g; ASSERT_TRUE(g.configure(config(), false));
		f = flying(); f.flying = false; g.begin(f);
		f.flying = true; f.sample += 8000;
		ASSERT_TRUE(g.begin(f).flags & Guard::Priming);
		const auto before = g.state();
		EXPECT_FALSE(g.seedXYZ({{.1f, -.1f, invalid}}));
		sameState(g.state(), before);
		EXPECT_TRUE(g.result().fault & Guard::Numerical);
	}
}

TEST(RegularizedIstaProtection, HteShiftChangesStateWithoutReevaluatingOrReconstructingIdeal)
{
	Guard g; ASSERT_TRUE(g.configure(config(4), false));
	auto f = flying(); prime(g, f);
	const auto candidate = g.begin(f);
	const auto applied = g.finish(candidate.a_req, 0, true);
	const auto before = g.state();
	ASSERT_TRUE(g.shiftZ(.03f, applied.correction_applied[2]));
	EXPECT_FLOAT_EQ(g.state()[2], before[2] + .03f);
	EXPECT_FLOAT_EQ(g.result().a_sta[2], candidate.a_sta[2]);
	EXPECT_FLOAT_EQ(g.result().nu_ideal[2], candidate.nu_ideal[2]);
	EXPECT_EQ(g.finish(candidate.a_req, 0, true).committed_axes, 0);
	f.sample += 12000;
	const auto shifted = g.begin(f);
	EXPECT_FLOAT_EQ(shifted.nu_before[2], before[2] + .03f);
	checkIdeal(shifted, config(4));
}

TEST(RegularizedIstaProtection, HteShiftWhileOpenOrBeyondLimitPreservesStateAndLatches)
{
	for (const bool open : {false, true}) {
		Guard g; ASSERT_TRUE(g.configure(config(4), false));
		auto f = flying(); prime(g, f);
		const auto candidate = g.begin(f);

		if (!open) { g.finish(candidate.a_req, 0, true); }

		const auto before = g.state();
		EXPECT_FALSE(g.shiftZ(open ? .01f : 10.f, candidate.correction_applied[2]));
		sameState(g.state(), before);
		EXPECT_TRUE(g.result().fault & Guard::Numerical);
	}
}

TEST(RegularizedIstaProtection, CoreResetBatchRejectsLastAxisWithoutInvalidatingOtherCandidates)
{
	Core kernel;

	for (size_t i = 0; i < 3; ++i) { ASSERT_TRUE(kernel.setParameters(i, {.5f, .1f, .01f})); }

	ASSERT_TRUE(kernel.resetBatch(7, {{.1f, -.1f, .2f}}));
	const auto a = kernel.evaluate(0, .05f, 0.f, .008f);
	const auto b = kernel.evaluate(1, -.04f, 0.f, .012f);
	const auto c = kernel.evaluate(2, .03f, 0.f, .008f);
	ASSERT_TRUE(a.valid() && b.valid() && c.valid());
	const auto before = kernel.state();

	for (const float invalid : {NAN, INFINITY, std::numeric_limits<float>::denorm_min()}) {
		EXPECT_FALSE(kernel.resetBatch(7, {{.2f, -.2f, invalid}}));
		sameState(kernel.state(), before);
		EXPECT_TRUE(kernel.current(a) && kernel.current(b) && kernel.current(c));
	}

	EXPECT_FALSE(kernel.resetBatch(0, {{0.f, 0.f, 0.f}}));
	EXPECT_FALSE(kernel.resetBatch(8, {{0.f, 0.f, 0.f}}));
	ASSERT_TRUE(kernel.resetBatch(3, {{.2f, -.2f, NAN}}));
	EXPECT_FALSE(kernel.current(a)); EXPECT_FALSE(kernel.current(b)); EXPECT_TRUE(kernel.current(c));
	EXPECT_FLOAT_EQ(kernel.state()[2], before[2]);
}

TEST(RegularizedIstaProtection, ExplicitAbortClosesCandidateAndLatchesWithoutPartialState)
{
	Guard g; ASSERT_TRUE(g.configure(config(), false));
	auto f = flying(); prime(g, f);
	const auto candidate = g.begin(f);
	const auto before = g.state();
	g.abortImplicit(Guard::Feedback, Guard::Duplicate);
	EXPECT_TRUE(g.result().flags & Guard::Duplicate);
	EXPECT_TRUE(g.result().flags & Guard::Latched);
	EXPECT_EQ(g.finish(candidate.a_req, 0, true).committed_axes, 0);
	sameState(g.state(), before);
}
