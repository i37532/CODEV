// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>
#include "PositionControl.hpp"
#include <cmath>
#include <limits>

// No production translation unit defines or calls this friend.
class RegularizedVelocityTestAccess
{
public:
	static void admit(PositionControl &p) { p._regularized_test_admission = true; }
};

namespace
{
using Guard = StaVelocityProtection;
using matrix::Vector3f;

Guard::Config config(uint8_t axes = 7, uint8_t variant = 3)
{
	Guard::Config c{};
	c.axes = axes; c.variant = variant;
	c.gains[0] = {.5f, .1f}; c.gains[1] = {.5f, .1f}; c.gains[2] = {2.f, 1.f};
	c.nu_limit = {{.4f, .4f, 4.f}}; c.acceleration_limit = {{.8f, .8f, 6.f}};
	return c;
}

void setup(PositionControl &p, uint8_t axes = 7, uint8_t variant = 3, bool admit = true)
{
	p.setPositionGains(Vector3f(.95f, .95f, 1.f));
	p.setVelocityGains(Vector3f(2.16f, 2.16f, 4.f), Vector3f(.48f, .48f, 2.f), Vector3f(.24f, .24f, 0.f));
	p.setVelocityLimits(12.f, 3.f, .55f); p.setThrustLimits(.12f, 1.f); p.setTiltLimit(.7f); p.setHoverThrust(.5f);
	if (admit) { RegularizedVelocityTestAccess::admit(p); }
	if (axes) { p.configureVelocityEsta(config(axes, variant), false); p.configureVelocityControl(variant, axes, false); }
}

Guard::Frame frame()
{
	Guard::Frame f{}; f.sample = 1000000; f.armed = f.enabled = f.flying = true; f.landed = f.contact = false;
	return f;
}

vehicle_local_position_setpoint_s target(float x = 0.f, float y = 0.f, float z = 0.f)
{
	vehicle_local_position_setpoint_s s{}; s.x = s.y = s.z = NAN; s.vx = x; s.vy = y; s.vz = z;
	for (float &a : s.acceleration) { a = NAN; }
	return s;
}

bool step(PositionControl &p, Guard::Frame &f, const vehicle_local_position_setpoint_s &s,
	  Vector3f velocity = Vector3f(), float legacy_dt = .01f)
{
	p.setVelocityFrame(f); p.setState({Vector3f(), velocity, Vector3f(), 0.f}); p.setInputSetpoint(s);
	return p.update(legacy_dt);
}

void equalState(const Guard::Vec &a, const Guard::Vec &b)
{
	for (size_t i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(a[i], b[i]); }
}
}

TEST(RegularizedVelocityIntegration, ProductionAdmissionRemainsClosedForAllNewMasks)
{
	for (const uint8_t axes : {1, 3, 4, 7}) {
		PositionControl p; setup(p, 0, 3, false);
		p.configureVelocityEsta(config(axes), false); p.configureVelocityControl(3, axes, false);
		EXPECT_NE(p.velocitySelection().reject(), 0); EXPECT_EQ(p.velocitySelection().effectiveMode(), 0);
		p.configureVelocityEsta(config(axes, 1), false); p.configureVelocityControl(1, axes, false);
		ASSERT_EQ(p.velocitySelection().effectiveMode(), 1);
		p.configureVelocityEsta(config(axes), false); p.configureVelocityControl(3, axes, false);
		EXPECT_NE(p.velocitySelection().reject(), 0); EXPECT_EQ(p.velocitySelection().effectiveMode(), 1);
		EXPECT_EQ(p.effectiveVelocityEsta().variant, 1);
	}
}

TEST(RegularizedVelocityIntegration, FixtureAdmissionRequiresConsistentVariantAndSupportedAxes)
{
	for (const uint8_t axes : {1, 3, 4, 7}) {
		PositionControl p; setup(p, axes);
		ASSERT_EQ(p.velocitySelection().reject(), 0); EXPECT_EQ(p.velocitySelection().effectiveMode(), 3);
		p.configureVelocityEsta(config(axes, 1), false); p.configureVelocityControl(3, axes, false);
		EXPECT_NE(p.velocitySelection().reject(), 0); EXPECT_EQ(p.effectiveVelocityEsta().variant, 3);
		p.configureVelocityEsta(config(axes, 3), false); p.configureVelocityControl(1, axes, false);
		EXPECT_NE(p.velocitySelection().reject(), 0); EXPECT_EQ(p.effectiveVelocityEsta().variant, 3);
	}
	for (const int axes : {-1, 0, 2, 5, 6, 8, 257}) {
		PositionControl p; setup(p, 0); p.configureVelocityEsta(config(7), false);
		p.configureVelocityControl(3, axes, false); EXPECT_NE(p.velocitySelection().reject(), 0);
		EXPECT_EQ(p.velocitySelection().effectiveMode(), 0);
	}
	PositionControl p; setup(p, 7); p.configureVelocityControl(2, 7, false);
	EXPECT_NE(p.velocitySelection().reject(), 0); EXPECT_EQ(p.velocitySelection().effectiveMode(), 3);
}

TEST(RegularizedVelocityIntegration, RegularizedDivisorIsOneIncludingReconfigurationOrder)
{
	for (const int divisor : {2, 4}) {
		PositionControl p; setup(p, 0); p.configureVelocityDivisor(divisor, false);
		ASSERT_EQ(p.velocityDecimation().divisor, divisor);
		p.configureVelocityEsta(config(1), false); p.configureVelocityControl(3, 1, false);
		EXPECT_NE(p.velocitySelection().reject(), 0); EXPECT_EQ(p.velocitySelection().effectiveMode(), 0);
		p.configureVelocityDivisor(1, false); p.configureVelocityControl(3, 1, false);
		ASSERT_EQ(p.velocitySelection().effectiveMode(), 3);
		p.configureVelocityDivisor(divisor, false);
		EXPECT_TRUE(p.velocityDecimation().rejected); EXPECT_EQ(p.velocityDecimation().divisor, 1);
		Guard g; ASSERT_TRUE(g.configure(config(1), false)); auto f = frame(); f.divisor = divisor;
		EXPECT_TRUE(g.begin(f).fault & Guard::Time);
	}
}

TEST(RegularizedVelocityIntegration, ConfigDomainAndLegacyUnusedEpsilonRemainDistinct)
{
	for (const uint8_t variant : {0, 2, 4, 255}) { EXPECT_FALSE(Guard::validConfig(config(1, variant))); }
	for (const uint8_t axes : {2, 5, 6}) { EXPECT_FALSE(Guard::validConfig(config(axes))); EXPECT_TRUE(Guard::validConfig(config(axes, 1))); }
	for (const float bad : {0.f, .0001f, 1.1f, NAN, INFINITY}) {
		auto c = config(1); c.epsilon[0] = bad; EXPECT_FALSE(Guard::validConfig(c));
		c.variant = 1; EXPECT_TRUE(Guard::validConfig(c));
	}
	Guard old; auto c = config(1, 1); ASSERT_TRUE(old.configure(c, false)); const auto generation = old.generation();
	c.epsilon = {{NAN, INFINITY, 0.f}};
	ASSERT_TRUE(old.configure(c, true)); EXPECT_FALSE(old.pending());
	ASSERT_TRUE(old.configure(c, false)); EXPECT_EQ(old.generation(), generation);
	auto new_x = config(1); new_x.epsilon[1] = NAN; EXPECT_TRUE(Guard::validConfig(new_x));
}

TEST(RegularizedVelocityIntegration, SelectedEpsilonPendingCancelAndDisarmedCommit)
{
	for (const uint8_t axes : {1, 3, 4, 7}) {
		for (unsigned axis = 0; axis < 3; ++axis) {
			if (!(axes & (1u << axis))) { continue; }
			PositionControl p; setup(p, axes); auto original = config(axes); auto changed = original;
			changed.epsilon[axis] *= 2.f;
			const auto generation = p.velocityEstaGeneration();
			p.configureVelocityEsta(changed, true); p.configureVelocityControl(3, axes, true);
			EXPECT_TRUE(p.velocityEstaPending()); EXPECT_FALSE(p.velocityEstaRejected());
			EXPECT_EQ(p.velocityEstaGeneration(), generation);
			EXPECT_FLOAT_EQ(p.effectiveVelocityEsta().epsilon[axis], original.epsilon[axis]);
			p.configureVelocityEsta(original, true); p.configureVelocityControl(3, axes, true);
			EXPECT_FALSE(p.velocityEstaPending()); EXPECT_EQ(p.velocityEstaGeneration(), generation);
			p.configureVelocityEsta(changed, false); p.configureVelocityControl(3, axes, false);
			EXPECT_FALSE(p.velocityEstaPending()); EXPECT_GT(p.velocityEstaGeneration(), generation);
			EXPECT_FLOAT_EQ(p.effectiveVelocityEsta().epsilon[axis], changed.epsilon[axis]);
			changed.epsilon[axis] = 0.f; const auto accepted = p.velocityEstaGeneration();
			p.configureVelocityEsta(changed, true); p.configureVelocityControl(3, axes, true);
			EXPECT_TRUE(p.velocityEstaPending()); EXPECT_TRUE(p.velocityEstaRejected());
			p.configureVelocityEsta(changed, false); p.configureVelocityControl(3, axes, false);
			EXPECT_NE(p.velocitySelection().reject(), 0); EXPECT_EQ(p.velocityEstaGeneration(), accepted);
		}
	}
}

TEST(RegularizedVelocityIntegration, ProtectionVariantAndEpsilonChangesInvalidateOpenTransactions)
{
	Guard g; auto c = config(3); ASSERT_TRUE(g.configure(c, false)); auto f = frame(); g.begin(f);
	f.sample += 10000; f.target = {{.005f, -.005f, 0.f}}; g.begin(f); const auto before = g.state();
	auto next = c; next.epsilon[0] = .02f;
	ASSERT_TRUE(g.configure(next, true)); EXPECT_TRUE(g.pending()); equalState(g.state(), before);
	ASSERT_TRUE(g.configure(c, true)); EXPECT_FALSE(g.pending());
	ASSERT_TRUE(g.configure(next, false)); EXPECT_EQ(g.finish({{0.f, 0.f, 0.f}}, 0, true).committed_axes, 0);
	equalState(g.state(), {{0.f, 0.f, 0.f}});
	f.sample += 10000; g.begin(f); f.sample += 10000; g.begin(f);
	const auto generation = g.generation(); next.variant = 1; ASSERT_TRUE(g.configure(next, false));
	EXPECT_GT(g.generation(), generation); EXPECT_EQ(g.finish({{0.f, 0.f, 0.f}}, 0, true).committed_axes, 0);
	equalState(g.state(), {{0.f, 0.f, 0.f}});
}

TEST(RegularizedVelocityIntegration, MasksUseIndependentNuSingleFeedForwardAndOnlyRemainingPid)
{
	for (const uint8_t axes : {1, 3, 4, 7}) {
		PositionControl p; setup(p, axes); auto f = frame(); ASSERT_TRUE(step(p, f, target()));
		f.sample += 12000; auto s = target(.005f, -.003f, .004f);
		s.acceleration[0] = .02f; s.acceleration[1] = -.03f; s.acceleration[2] = .04f;
		ASSERT_TRUE(step(p, f, s)); const auto d = p.diagnostic(); const auto c = config(axes);
		const float demand[3] = {s.vx, s.vy, s.vz};
		EXPECT_EQ(d.active_axes, axes); EXPECT_EQ(d.committed_axes, axes); EXPECT_EQ(d.pid_axes, 7 ^ axes);
		for (unsigned i = 0; i < 3; ++i) {
			if (axes & (1u << i)) {
				const float expected = c.gains[i].lambda1 * demand[i] / sqrtf(c.epsilon[i]);
				EXPECT_NEAR(d.a_sta[i], expected, 2.e-6f);
				EXPECT_NEAR(d.a_req[i], expected + s.acceleration[i], 2.e-6f);
				EXPECT_NEAR(d.nu_ideal[i], .012f * c.gains[i].lambda2 * demand[i] / c.epsilon[i], 2.e-7f);
				EXPECT_FLOAT_EQ(d.nu_before[i], 0.f); EXPECT_FLOAT_EQ(d.nu_applied[i], d.nu_ideal[i]);
			} else { EXPECT_TRUE(std::isnan(d.a_sta[i])); }
		}
	}
}

TEST(RegularizedVelocityIntegration, NonuniformSampleDtNotLegacyDtDrivesNewNu)
{
	Guard g; ASSERT_TRUE(g.configure(config(1), false)); auto f = frame(); g.begin(f);
	float expected = 0.f;
	for (const uint64_t interval : {8000, 12000, 8000, 12000}) {
		f.sample += interval; f.target[0] = .005f; const auto r = g.begin(f);
		const float h = static_cast<float>(interval) * 1.e-6f;
		expected += h * .1f * .5f; EXPECT_FLOAT_EQ(r.raw_dt, h);
		EXPECT_NEAR(r.nu_ideal[0], expected, 2.e-9f);
		EXPECT_EQ(g.finish(r.a_req, 0, true).committed_axes, 1);
	}
	PositionControl p; setup(p, 1); f = frame(); ASSERT_TRUE(step(p, f, target(), Vector3f(), .02f));
	f.sample += 8000; ASSERT_TRUE(step(p, f, target(.005f), Vector3f(), .03f));
	EXPECT_NEAR(p.diagnostic().nu_applied[0], .0004f, 2.e-9f);
}

TEST(RegularizedVelocityIntegration, GroundRampAndBoundedZOrXyzHandoverRetainPidOutput)
{
	for (const uint8_t axes : {4, 7}) {
		PositionControl p, pid; setup(p, axes); setup(pid, 0); auto f = frame(); f.flying = false;
		auto s = target(.003f, -.002f, -.004f); s.acceleration[0] = .02f; s.acceleration[1] = -.01f; s.acceleration[2] = -.03f;
		for (int k = 0; k < 15; ++k) {
			ASSERT_TRUE(step(p, f, s)); ASSERT_TRUE(step(pid, f, s));
			EXPECT_EQ(p.diagnostic().z_phase, 1); EXPECT_EQ(p.diagnostic().committed_axes, 0);
			for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(p.diagnostic().thrust[i], pid.diagnostic().thrust[i]); }
			f.sample += 10000;
		}
		f.flying = true; ASSERT_TRUE(step(p, f, s)); ASSERT_TRUE(step(pid, f, s)); const auto boundary = p.diagnostic();
		EXPECT_EQ(boundary.z_phase, 2); EXPECT_EQ(boundary.pid_axes, 7); EXPECT_EQ(boundary.committed_axes, 0);
		for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(boundary.a_req[i], pid.diagnostic().a_req[i]); }
		f.sample += 10000; ASSERT_TRUE(step(p, f, s));
		for (unsigned i = 0; i < 3; ++i) {
			if (axes & (1u << i)) { EXPECT_NEAR(p.diagnostic().a_req[i], boundary.a_req[i], 2.e-6f); }
		}
		EXPECT_EQ(p.diagnostic().pid_axes, 7 ^ axes);
	}
}

TEST(RegularizedVelocityIntegration, HteUsesRegularizedShapeAtNonzeroErrorNuFfAndTilt)
{
	for (const uint8_t axes : {4, 7}) {
		PositionControl p, unchanged; setup(p, axes); setup(unchanged, axes); auto f = frame();
		auto s = target(.003f, -.002f, .004f); s.acceleration[0] = .2f; s.acceleration[1] = -.1f; s.acceleration[2] = .03f;
		for (int k = 0; k < 3; ++k) { ASSERT_TRUE(step(p, f, s)); ASSERT_TRUE(step(unchanged, f, s)); f.sample += 10000; }
		const auto old = p.diagnostic();
		const float correction = 2.f * s.vz / sqrtf(.02f) + old.nu_applied[2];
		const float expected_shift = (.5f / .55f - 1.f) * (correction + s.acceleration[2] - 9.80665f);
		p.updateHoverThrust(.55f); ASSERT_TRUE(step(p, f, s)); ASSERT_TRUE(step(unchanged, f, s));
		EXPECT_NEAR(p.diagnostic().z_hte_shift, expected_shift, 2.e-6f);
		EXPECT_NEAR(p.diagnostic().nu_before[2], old.nu_applied[2] + expected_shift, 2.e-6f);
		for (int i = 0; i < 3; ++i) { EXPECT_NEAR(p.diagnostic().thrust[i], unchanged.diagnostic().thrust[i], 3.e-6f); }
		for (int i = 0; i < 2; ++i) {
			if (axes & (1u << i)) { EXPECT_FLOAT_EQ(p.diagnostic().nu_before[i], old.nu_applied[i]); }
		}
	}
}

TEST(RegularizedVelocityIntegration, InvalidHteOrOutOfRangeSeedFailsClosed)
{
	for (const int reason : {0, 1, 2}) {
		PositionControl p; setup(p, 7); auto f = frame();
		if (reason == 0) { EXPECT_FALSE(step(p, f, target(.5f))); }
		else {
			ASSERT_TRUE(step(p, f, target())); p.updateHoverThrust(reason == 1 ? NAN : .9f);
			f.sample += 10000; EXPECT_FALSE(step(p, f, target()));
		}
		EXPECT_FALSE(p.velocityOutputPublishable()); EXPECT_EQ(p.diagnostic().committed_axes, 0);
	}
}

TEST(RegularizedVelocityIntegration, LastAxisEvaluationOrFeedbackFailureCommitsNoAxis)
{
	for (const int reason : {0, 1, 2, 3}) {
		Guard g; ASSERT_TRUE(g.configure(config(), false)); auto f = frame(); g.begin(f);
		ASSERT_TRUE(g.seedXYZ({{.01f, -.01f, .02f}})); const auto before = g.state(); f.sample += 10000;
		f.target = {{.005f, -.005f, .004f}};
		if (reason == 0) { f.velocity[2] = NAN; }
		if (reason == 1) { f.ff[2] = INFINITY; }
		const auto candidate = g.begin(f);
		auto proxy = candidate.a_req; if (reason == 2) { proxy[2] = NAN; }
		const auto result = g.finish(proxy, 0, reason != 3);
		EXPECT_NE(result.fault, 0); EXPECT_EQ(result.committed_axes, 0); equalState(g.state(), before);
	}
}

TEST(RegularizedVelocityIntegration, CorrectionAndStateLimitsKeepIdealSeparateAndFfOnce)
{
	Guard g; auto c = config(3); c.acceleration_limit[0] = .01f; c.nu_limit[1] = .0001f;
	ASSERT_TRUE(g.configure(c, false)); auto f = frame(); g.begin(f); f.sample += 10000;
	f.target = {{.005f, -.005f, 0.f}}; f.ff = {{.3f, -.2f, 0.f}};
	const auto ideal = g.begin(f); EXPECT_NEAR(ideal.a_sta[0], .025f, 2.e-8f);
	EXPECT_NEAR(ideal.a_req[0], .31f, 2.e-8f); EXPECT_GT(ideal.nu_ideal[0], 0.f);
	const auto applied = g.finish(ideal.a_req, 0, true);
	EXPECT_TRUE(applied.flags & Guard::CorrectionLimit); EXPECT_TRUE(applied.flags & Guard::StateLimit);
	EXPECT_TRUE(applied.flags & Guard::OutwardFreeze); EXPECT_FLOAT_EQ(applied.nu_applied[0], 0.f);
	EXPECT_FLOAT_EQ(applied.nu_applied[1], -.0001f); EXPECT_FLOAT_EQ(applied.a_sta[0], ideal.a_sta[0]);
	EXPECT_FLOAT_EQ(applied.nu_ideal[0], ideal.nu_ideal[0]); EXPECT_EQ(applied.committed_axes, 3);
}

TEST(RegularizedVelocityIntegration, SaturationDirectionAllowsRecoveryAndRequiresValidFeedback)
{
	for (const bool outward : {false, true}) {
		Guard g; ASSERT_TRUE(g.configure(config(1), false)); auto f = frame(); g.begin(f); f.sample += 10000;
		f.target[0] = outward ? .005f : -.005f; const auto candidate = g.begin(f);
		const auto result = g.finish(candidate.a_req, 0, true, 1, 0);
		EXPECT_EQ(bool(result.flags & Guard::OutwardFreeze), outward);
		if (outward) { EXPECT_FLOAT_EQ(result.nu_applied[0], 0.f); }
		else { EXPECT_LT(result.nu_applied[0], 0.f); }
	}
}

TEST(RegularizedVelocityIntegration, VectorTiltAndVerticalPriorityFreezeAffectedDirections)
{
	for (const int constraint : {0, 1}) {
		PositionControl p; setup(p, 7); auto f = frame(); ASSERT_TRUE(step(p, f, target()));
		if (constraint == 1) { p.setTiltLimit(.005f); }
		f.sample += 10000; auto s = target(.2f, -.1f, -.1f); if (constraint == 0) { s.acceleration[2] = -30.f; }
		ASSERT_TRUE(step(p, f, s)); const auto d = p.diagnostic();
		EXPECT_NE(d.constraint_bits, 0); EXPECT_EQ(d.committed_axes, 7); EXPECT_TRUE(d.sta_flags & Guard::OutwardFreeze);
		EXPECT_FLOAT_EQ(d.nu_applied[0], 0.f); EXPECT_FLOAT_EQ(d.nu_applied[1], 0.f);
		if (constraint == 0) { EXPECT_FLOAT_EQ(d.nu_applied[2], 0.f); EXPECT_FLOAT_EQ(d.thrust[2], -1.f); }
		else { EXPECT_LT(d.nu_applied[2], 0.f); }
	}
}

TEST(RegularizedVelocityIntegration, SameSampleFailsafeCannotCommitAgain)
{
	for (const uint8_t axes : {1, 3, 4, 7}) {
		PositionControl p; setup(p, axes); auto f = frame(); ASSERT_TRUE(step(p, f, target())); f.sample += 10000;
		ASSERT_TRUE(step(p, f, target(.005f, -.005f, .004f))); const auto old = p.diagnostic();
		EXPECT_FALSE(step(p, f, target())); EXPECT_EQ(p.diagnostic().committed_axes, 0); EXPECT_FALSE(p.velocityOutputPublishable());
		for (unsigned i = 0; i < 3; ++i) { if (axes & (1u << i)) { EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[i], old.nu_applied[i]); } }
	}
}

TEST(RegularizedVelocityIntegration, TimeMeasurementResetAndInnerFaultsLatchUntilDisarm)
{
	for (const int reason : {0, 1, 2, 3, 4, 5, 6, 7, 8}) {
		PositionControl p; setup(p, 7); auto f = frame(); ASSERT_TRUE(step(p, f, target())); f.sample += 10000;
		ASSERT_TRUE(step(p, f, target(.005f, -.003f, .004f))); const auto old = p.diagnostic(); f.sample += 10000;
		Vector3f velocity;
		if (reason == 0) { f.sample -= 20000; } if (reason == 1) { f.sample += 100000; }
		if (reason == 2) { f.sample -= 9999; } if (reason == 3) { velocity(2) = NAN; }
		if (reason == 4) { f.inner_valid = false; } if (reason == 5) { f.unmatched_reset_axes = 2; }
		if (reason == 6) { f.unmatched_reset_axes = 4; }
		if (reason == 7) { f.unmatched_reset_axes = 1; } if (reason == 8) { f.unmatched_reset_axes = 7; }
		EXPECT_FALSE(step(p, f, target(), velocity)); EXPECT_EQ(p.diagnostic().committed_axes, 0);
		for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[i], old.nu_applied[i]); }
		f.sample += 10000; f.inner_valid = true; f.unmatched_reset_axes = 0;
		EXPECT_FALSE(step(p, f, target())); f.armed = false; f.sample += 10000; ASSERT_TRUE(step(p, f, target()));
		f.armed = true; f.sample += 10000; ASSERT_TRUE(step(p, f, target())); EXPECT_EQ(p.diagnostic().z_phase, 2);
	}
}

TEST(RegularizedVelocityIntegration, OriginalHalfNanPairCannotResetOrReseedSubset)
{
	for (const uint8_t axes : {1, 3, 4, 7}) {
		PositionControl p; setup(p, axes); auto f = frame(); ASSERT_TRUE(step(p, f, target())); f.sample += 10000;
		ASSERT_TRUE(step(p, f, target(.005f, -.003f, .004f))); const auto old = p.diagnostic();
		ASSERT_TRUE(p.velocityDecimation().updated); const auto sequence = p.velocityDecimation().sequence;
		f.sample += 10000; auto invalid = target(); invalid.vx = NAN;
		EXPECT_FALSE(step(p, f, invalid)); EXPECT_EQ(p.diagnostic().committed_axes, 0);
		EXPECT_FALSE(p.velocityDecimation().updated); EXPECT_FALSE(p.velocityDecimation().held);
		EXPECT_EQ(p.velocityDecimation().sequence, sequence);
		for (unsigned i = 0; i < 3; ++i) { if (axes & (1u << i)) { EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[i], old.nu_applied[i]); } }
		EXPECT_FALSE(step(p, f, target())); EXPECT_EQ(p.diagnostic().committed_axes, 0);
	}
}

TEST(RegularizedVelocityIntegration, ContactCancelDisarmAndDisabledExitClearStateAndReprime)
{
	for (const int reason : {0, 1, 2, 3, 4}) {
		PositionControl p; setup(p, 7); auto f = frame(); ASSERT_TRUE(step(p, f, target())); f.sample += 10000;
		ASSERT_TRUE(step(p, f, target(.005f, -.003f, .004f)));
		if (reason == 0) { f.contact = true; } if (reason == 1) { f.landed = true; } if (reason == 2) { f.flying = false; }
		if (reason == 3) { f.armed = false; } if (reason == 4) { f.enabled = false; }
		f.sample += 10000; ASSERT_TRUE(step(p, f, target())); EXPECT_EQ(p.diagnostic().committed_axes, 0);
		for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[i], 0.f); }
		auto next = frame(); next.sample = f.sample + 10000; ASSERT_TRUE(step(p, next, target())); EXPECT_EQ(p.diagnostic().z_phase, 2);
	}
}

TEST(RegularizedVelocityIntegration, AccelerationOnlyAndChangingActiveMasksNeverReuseNu)
{
	PositionControl p; setup(p, 7); auto f = frame(); ASSERT_TRUE(step(p, f, target())); f.sample += 10000;
	ASSERT_TRUE(step(p, f, target(.005f, -.003f, .004f)));
	for (const int active : {3, 7, 4, 7, 0, 7}) {
		auto s = target(); if (!(active & 3)) { s.vx = s.vy = NAN; s.acceleration[0] = s.acceleration[1] = 0.f; }
		if (!(active & 4)) { s.vz = NAN; s.acceleration[2] = .02f; }
		f.sample += 10000; ASSERT_TRUE(step(p, f, s)); EXPECT_EQ(p.diagnostic().committed_axes, 0);
		for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[i], 0.f); }
		f.sample += 10000; ASSERT_TRUE(step(p, f, s)); EXPECT_EQ(p.diagnostic().committed_axes, active); EXPECT_EQ(p.diagnostic().pid_axes, 0);
	}
}

TEST(RegularizedVelocityIntegration, AlgorithmAndMaskSwitchesCannotInheritOldStates)
{
	PositionControl p; setup(p, 7); auto f = frame(); ASSERT_TRUE(step(p, f, target())); f.sample += 10000;
	ASSERT_TRUE(step(p, f, target(.005f, -.003f, .004f)));
	for (const uint8_t variant : {1, 3}) {
		for (const uint8_t axes : {1, 3, 4, 7}) {
			p.configureVelocityEsta(config(axes, variant), false); p.configureVelocityControl(variant, axes, false);
			ASSERT_EQ(p.velocitySelection().reject(), 0); f.armed = false; f.sample += 10000;
			ASSERT_TRUE(step(p, f, target())); f.armed = true; f.sample += 10000; ASSERT_TRUE(step(p, f, target()));
			EXPECT_EQ(p.diagnostic().committed_axes, 0);
			for (unsigned i = 0; i < 3; ++i) { if (axes & (1u << i)) { EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[i], 0.f); } }
		}
	}
	p.configureVelocityControl(0, 0, true); EXPECT_TRUE(p.velocitySelection().pending());
	p.configureVelocityControl(3, 7, true); EXPECT_FALSE(p.velocitySelection().pending());
	p.configureVelocityControl(0, 0, false); EXPECT_EQ(p.velocitySelection().effectiveMode(), 0);
}

TEST(RegularizedVelocityIntegration, NormalXyzDoesNotCalculateUnusedPid)
{
	PositionControl p; setup(p, 7); auto f = frame(); ASSERT_TRUE(step(p, f, target()));
	p.setVelocityGains(Vector3f(NAN, NAN, NAN), Vector3f(NAN, NAN, NAN), Vector3f(NAN, NAN, NAN));
	f.sample += 10000; ASSERT_TRUE(step(p, f, target(.005f, -.003f, .004f)));
	EXPECT_EQ(p.diagnostic().pid_axes, 0); EXPECT_EQ(p.diagnostic().committed_axes, 7);
	for (int i = 0; i < 3; ++i) { EXPECT_TRUE(std::isfinite(p.diagnostic().thrust[i])); EXPECT_FLOAT_EQ(p.velocityIntegral()(i), 0.f); }
}

TEST(RegularizedVelocityIntegration, DiagnosticStateReplicaCannotReplaceSealedKernelProposal)
{
	for (const uint8_t variant : {1, 3}) {
		Guard g; ASSERT_TRUE(g.configure(config(3, variant), false)); auto f = frame(); g.begin(f); f.sample += 10000;
		f.target = {{.005f, -.005f, 0.f}};
		const auto &candidate_observation = g.begin(f);
		const auto ideal = candidate_observation;
		// Deliberate fault injection into observation storage. Ordinary clients
		// receive only const Result; this does not mutate the sealed candidates.
		auto &open_observation = const_cast<Guard::Result &>(candidate_observation);
		open_observation.nu_before = {{.2f, .2f, .2f}};
		open_observation.nu_ideal = {{.3f, .3f, .3f}};
		open_observation.a_sta = {{100.f, 100.f, 100.f}};
		const auto applied = g.finish(ideal.a_req, 0, true);
		EXPECT_EQ(applied.committed_axes, 3);
		EXPECT_FLOAT_EQ(applied.nu_applied[0], ideal.nu_ideal[0]);
		EXPECT_FLOAT_EQ(applied.nu_applied[1], ideal.nu_ideal[1]);
	}
}

TEST(RegularizedVelocityIntegration, RawTimeExactBoundsAndNeighborsPreserveOriginalGuard)
{
	for (const uint64_t interval : {1999, 2000, 40000, 40001}) {
		Guard g; ASSERT_TRUE(g.configure(config(1), false)); auto f = frame(); g.begin(f);
		f.sample += interval; f.target[0] = .005f; const auto result = g.begin(f);
		if (interval == 2000 || interval == 40000) {
			EXPECT_EQ(result.fault, 0); EXPECT_EQ(g.finish(result.a_req, 0, true).committed_axes, 1);
		} else {
			EXPECT_TRUE(result.fault & Guard::Time); EXPECT_EQ(g.finish(result.a_req, 0, true).committed_axes, 0);
			EXPECT_FLOAT_EQ(g.state()[0], 0.f);
		}
	}
}

TEST(RegularizedVelocityIntegration, InvalidOriginalPairCannotApplyHteAfterFault)
{
	PositionControl p; setup(p, 7); auto f = frame(); ASSERT_TRUE(step(p, f, target())); f.sample += 10000;
	ASSERT_TRUE(step(p, f, target(.005f, -.003f, .004f))); const auto old = p.diagnostic();
	f.sample += 10000; auto invalid = target(); invalid.vx = NAN;
	EXPECT_FALSE(step(p, f, invalid)); const auto integral = p.velocityIntegral();
	p.updateHoverThrust(NAN); p.updateHoverThrust(.55f); f.sample += 10000; EXPECT_FALSE(step(p, f, target()));
	EXPECT_FALSE(p.velocityOutputPublishable()); EXPECT_EQ(p.diagnostic().committed_axes, 0);
	EXPECT_FLOAT_EQ(p.diagnostic().z_hte_shift, 0.f);
	EXPECT_FLOAT_EQ(p.diagnostic().hover_thrust, old.hover_thrust);
	for (int i = 0; i < 3; ++i) {
		EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[i], old.nu_applied[i]);
		EXPECT_FLOAT_EQ(p.velocityIntegral()(i), integral(i));
	}
}

TEST(RegularizedVelocityIntegration, RepeatedContactBounceAndLongRampRequireFreshBoundedHandover)
{
	PositionControl p; setup(p, 7); auto f = frame(); f.flying = false;
	// No elapsed-time release in this adapter: long ramp stays PID with zero nu.
	// Long ground wait, external timeout cancellation and termination are
	// exercised at module level; Takeoff has no independent timeout timer.
	for (int k = 0; k < 2000; ++k) {
		ASSERT_TRUE(step(p, f, target())); EXPECT_EQ(p.diagnostic().z_phase, 1);
		EXPECT_EQ(p.diagnostic().committed_axes, 0); f.sample += 10000;
	}
	f.flying = true; ASSERT_TRUE(step(p, f, target())); EXPECT_EQ(p.diagnostic().z_phase, 2);
	for (int bounce = 0; bounce < 3; ++bounce) {
		f.sample += 10000; ASSERT_TRUE(step(p, f, target(.005f, -.003f, .004f)));
		f.contact = true; f.sample += 10000; ASSERT_TRUE(step(p, f, target()));
		EXPECT_EQ(p.diagnostic().z_phase, 1); EXPECT_EQ(p.diagnostic().committed_axes, 0);
		f.contact = false; f.sample += 10000; ASSERT_TRUE(step(p, f, target()));
		EXPECT_EQ(p.diagnostic().z_phase, 2); EXPECT_EQ(p.diagnostic().committed_axes, 0);
		for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[i], 0.f); }
	}
}
