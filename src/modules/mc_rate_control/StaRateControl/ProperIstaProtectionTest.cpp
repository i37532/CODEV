// SPDX-License-Identifier: BSD-3-Clause
#include "ProperIstaProtection.hpp"
#include <gtest/gtest.h>
#include <cmath>
#include <limits>
#include <utility>

namespace
{
using P = ProperIstaProtection;

P::Config config(int axes = 1)
{
	P::Config c; c.enabled = true; c.axes = axes; c.c_limit = 1.f;
	for (size_t i = 0; i < 3; ++i) { c.gains[i] = {1.f, 1.f, 2.f}; c.nu_limit[i] = 10.f; }
	return c;
}

P::Frame frame(uint64_t sample, bool armed, bool allowed = true)
{
	P::Frame f; f.sample = sample; f.armed = armed; f.rate_enabled = armed; f.update_allowed = allowed;
	return f;
}

StaProtection::Feedback feedback(uint16_t extra = 0, bool valid = true)
{
	StaProtection::Feedback f; f.timestamp = 100; f.now = 110; f.bits = static_cast<uint16_t>(extra | (valid ? 1 : 0));
	return f;
}

void start(P &guard, const P::Config &c, bool allowed = true)
{
	guard.begin(c, frame(1000, false));
	guard.begin(c, frame(5000, true, allowed));
}
}

TEST(ProperIstaProtectionTest, IdealCandidateRemainsStrictAndCommits)
{
	P guard; const auto c = config(); start(guard, c);
	auto out = guard.step({0.01f, 0.f, 0.f}, {}, feedback(), 0.004f);
	ASSERT_TRUE(out.valid); EXPECT_TRUE(out.updated); EXPECT_TRUE(out.strict_implicit[0]);
	EXPECT_FLOAT_EQ(out.ideal_c[0], out.preclip_c[0]);
	EXPECT_FLOAT_EQ(out.ideal_c[0], out.applied_c[0]);
	EXPECT_FLOAT_EQ(out.ideal_nu[0], out.applied_nu[0]);
	EXPECT_FLOAT_EQ(out.applied_nu[0], guard.state()[0]);
}

TEST(ProperIstaProtectionTest, InvalidFeedbackFreezesStateAndUsesTwoDeltaMapping)
{
	P guard; const auto c = config(); start(guard, c);
	auto out = guard.step({0.01f, 0.f, 0.f}, {}, feedback(0, false), 0.004f);
	ASSERT_TRUE(out.valid); EXPECT_EQ(out.limits[0] & StaProtection::FeedbackInvalid, StaProtection::FeedbackInvalid);
	EXPECT_FLOAT_EQ(out.applied_nu[0], 0.f);
	EXPECT_FLOAT_EQ(out.state_mapped_a[0], out.ideal_a[0] + 2.f * (out.applied_nu[0] - out.ideal_nu[0]));
	EXPECT_FALSE(out.strict_implicit[0]);
}

TEST(ProperIstaProtectionTest, MixerDirectionsFreezeOnlyMatchingAxisAndSign)
{
	P negative_delta; auto c = config(3); start(negative_delta, c);
	auto out = negative_delta.step({0.01f, 0.01f, 0.f}, {}, feedback(1 << 4), 0.004f);
	ASSERT_TRUE(out.valid); // roll negative-direction saturation
	EXPECT_NE(out.limits[0] & StaProtection::MixerFreeze, 0);
	EXPECT_EQ(out.limits[1] & StaProtection::MixerFreeze, 0);

	P positive_delta; start(positive_delta, c);
	out = positive_delta.step({-0.01f, -0.01f, 0.f}, {}, feedback(1 << 5), 0.004f);
	ASSERT_TRUE(out.valid); // pitch positive-direction saturation
	EXPECT_EQ(out.limits[0] & StaProtection::MixerFreeze, 0);
	EXPECT_NE(out.limits[1] & StaProtection::MixerFreeze, 0);
}

TEST(ProperIstaProtectionTest, NuAndOutputLimitsAreSeparateFromIdealCandidate)
{
	P nu_guard; auto c = config(); c.nu_limit[0] = 0.001f; start(nu_guard, c);
	auto out = nu_guard.step({0.01f, 0.f, 0.f}, {}, feedback(), 0.004f);
	ASSERT_TRUE(out.valid);
	EXPECT_NE(out.limits[0] & StaProtection::NuLimit, 0);
	EXPECT_FALSE(out.strict_implicit[0]);

	P output_guard; c = config(); c.c_limit = 0.02f; start(output_guard, c);
	out = output_guard.step({0.2f, 0.f, 0.f}, {}, feedback(), 0.004f);
	ASSERT_TRUE(out.valid);
	EXPECT_NE(out.limits[0] & StaProtection::OutputLimit, 0);
	EXPECT_LE(std::fabs(out.applied_c[0]), c.c_limit);
	EXPECT_FALSE(out.strict_implicit[0]);
}

TEST(ProperIstaProtectionTest, LifecycleFreezeDoesNotCommitIdealNu)
{
	P guard; const auto c = config(); start(guard, c, false);
	auto out = guard.step({0.01f, 0.f, 0.f}, {}, feedback(), 0.004f);
	ASSERT_TRUE(out.valid); EXPECT_FALSE(out.updated);
	EXPECT_FLOAT_EQ(out.applied_nu[0], 0.f); EXPECT_FLOAT_EQ(guard.state()[0], 0.f);
	EXPECT_FALSE(out.strict_implicit[0]);
}

TEST(ProperIstaProtectionTest, FeedbackAgeBoundaryAndFutureAreChecked)
{
	P boundary; auto c = config(); start(boundary, c);
	StaProtection::Feedback f; f.bits = 1; f.timestamp = 100; f.now = 20100;
	auto out = boundary.step({0.01f, 0.f, 0.f}, {}, f, 0.004f);
	ASSERT_TRUE(out.valid); EXPECT_EQ(out.limits[0] & StaProtection::FeedbackInvalid, 0);

	P stale; start(stale, c); f.now = 20101;
	out = stale.step({0.01f, 0.f, 0.f}, {}, f, 0.004f);
	ASSERT_TRUE(out.valid); EXPECT_NE(out.limits[0] & StaProtection::FeedbackInvalid, 0);

	P future; start(future, c); f.timestamp = 200; f.now = 100;
	out = future.step({0.01f, 0.f, 0.f}, {}, f, 0.004f);
	ASSERT_TRUE(out.valid); EXPECT_NE(out.limits[0] & StaProtection::FeedbackInvalid, 0);
}

TEST(ProperIstaProtectionTest, NumericalFailureCannotPartiallyCommitAxes)
{
	P guard; auto c = config(3); start(guard, c);
	const float nan = std::numeric_limits<float>::quiet_NaN();
	auto out = guard.step({0.01f, nan, 0.f}, {}, feedback(), 0.004f);
	EXPECT_FALSE(out.valid); EXPECT_EQ(guard.fault(), P::Fault::Numerical);
	EXPECT_FLOAT_EQ(guard.state()[0], 0.f); EXPECT_FLOAT_EQ(guard.state()[1], 0.f);
}

TEST(ProperIstaProtectionTest, DuplicateTimeLatchesAndNeedsDisarmedAcknowledge)
{
	P guard; auto c = config(); start(guard, c);
	guard.begin(c, frame(5000, true));
	EXPECT_EQ(guard.fault(), P::Fault::DuplicateTime); EXPECT_TRUE(guard.abortRequested());
	EXPECT_FALSE(guard.acknowledge());
	guard.begin(c, frame(9000, false));
	EXPECT_TRUE(guard.acknowledge()); EXPECT_EQ(guard.fault(), P::Fault::None);
}

TEST(ProperIstaProtectionTest, TimeAndMeasurementFaultClassesAreDistinct)
{
	for (const auto &sample_fault : {std::pair<uint64_t, P::Fault>{4000, P::Fault::BackwardTime},
					     {30000, P::Fault::LongGap}, {5100, P::Fault::ShortDt}}) {
		P guard; auto c = config(); start(guard, c);
		guard.begin(c, frame(sample_fault.first, true));
		EXPECT_EQ(guard.fault(), sample_fault.second);
	}
	P measurement; auto c = config(); measurement.begin(c, frame(1000, false));
	auto bad = frame(5000, true); bad.measurement_valid = false; measurement.begin(c, bad);
	EXPECT_EQ(measurement.fault(), P::Fault::Measurement);
}

TEST(ProperIstaProtectionTest, ArmedConfigChangeIsPendingUntilDisarm)
{
	P guard; auto c = config(); start(guard, c);
	auto changed = c; changed.nu_limit[0] = 2.f;
	guard.begin(changed, frame(9000, true));
	EXPECT_TRUE(guard.pending());
	guard.begin(changed, frame(13000, false));
	EXPECT_FALSE(guard.pending());
}

TEST(ProperIstaProtectionTest, ProtectedCommitRejectsWrongOwnerAndStaleCandidate)
{
	ProperIstaRateControl a, b; ProperIstaRateControl::Parameters p{1.f, 1.f, 1.f};
	ASSERT_TRUE(a.setParameters(0, p)); ASSERT_TRUE(b.setParameters(0, p));
	auto candidate = a.evaluate(0, 0.01f, 0.f, 0.004f); ASSERT_TRUE(candidate.result().valid());
	EXPECT_FALSE(b.commitProtected(candidate, 0.f));
	EXPECT_TRUE(a.commitProtected(candidate, 0.f));
	EXPECT_FALSE(a.commitProtected(candidate, 0.f));
}
