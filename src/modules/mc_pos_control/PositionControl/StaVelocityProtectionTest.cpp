// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>
#include "StaVelocityProtection.hpp"
#include "PositionControl.hpp"
#include <cmath>
#include <ecl/geo/geo.h>
#include "VelocityDiagnosticExcitation.hpp"

namespace
{
using Guard = StaVelocityProtection;
Guard::Config config()
{
	Guard::Config c{}; c.axes = 3;
	for (size_t i = 0; i < 3; ++i) { c.gains[i] = {2.f, 1.f}; c.nu_limit[i] = 1.f; c.acceleration_limit[i] = 3.f; }
	return c;
}
Guard::Frame flying(uint64_t sample = 1000000)
{
	Guard::Frame f{};
	f.sample = sample; f.armed = f.enabled = f.flying = true; f.landed = f.contact = false;
	f.velocity = {{-.25f, .25f, 0.f}}; f.target = {{0.f, 0.f, 0.f}}; f.ff = {{.2f, -.1f, NAN}};
	return f;
}
void prime(Guard &g, Guard::Frame &f)
{
	ASSERT_TRUE(g.configure(config(), false));
	EXPECT_TRUE(g.begin(f).flags & Guard::Priming); f.sample += 10000;
}
}

TEST(StaVelocityProtection, IndependentAxesOldNuAndSingleFeedforward)
{
	Guard g; auto f = flying(); prime(g, f);
	const auto r = g.begin(f);
	EXPECT_FLOAT_EQ(r.a_sta[0], 1.f); EXPECT_FLOAT_EQ(r.a_req[0], 1.2f);
	EXPECT_FLOAT_EQ(r.a_req[1], -1.1f); EXPECT_FLOAT_EQ(r.nu_before[0], 0.f);
	const auto out = g.finish(r.a_req, 0, true);
	EXPECT_EQ(out.committed_axes, 3); EXPECT_NEAR(g.state()[0], .01f, 1e-7f);
	EXPECT_NEAR(g.state()[1], -.01f, 1e-7f); EXPECT_FLOAT_EQ(g.state()[2], 0.f);
}

TEST(StaVelocityProtection, SameSampleFailsafeAndRepeatedFinishCannotIntegrateTwice)
{
	Guard g; auto f = flying(); prime(g, f); auto r = g.begin(f); g.finish(r.a_req, 0, true);
	const auto before = g.state(); EXPECT_EQ(g.finish(r.a_req, 0, true).committed_axes, 0);
	f.target = {{.5f, .5f, .5f}};
	EXPECT_TRUE(g.begin(f).flags & Guard::Duplicate); g.finish(r.a_req, 0, true);
	EXPECT_EQ(g.state(), before);
	f.contact = true; EXPECT_TRUE(g.begin(f).flags & Guard::Inactive);
	EXPECT_FLOAT_EQ(g.state()[0], 0.f); // Safety lifecycle still applies on a retry sample.
}

TEST(StaVelocityProtection, SignedConstraintDirectionNotBodyMixerBits)
{
	for (float direction : {-1.f, 1.f}) {
		Guard g; auto f = flying(); f.velocity = {{-.25f * direction, .25f * direction, 0.f}};
		prime(g, f); auto r = g.begin(f); auto proxy = r.a_req;
		proxy[0] -= .5f * direction; proxy[1] += .5f * direction;
		auto out = g.finish(proxy, 3, true);
		EXPECT_TRUE(out.flags & Guard::OutwardFreeze); EXPECT_FLOAT_EQ(g.state()[0], 0.f);
		EXPECT_FLOAT_EQ(g.state()[1], 0.f);
		f.sample += 10000; r = g.begin(f); proxy = r.a_req;
		proxy[0] += .5f * direction; proxy[1] -= .5f * direction;
		out = g.finish(proxy, 3, true);
		EXPECT_FALSE(out.flags & Guard::OutwardFreeze);
		EXPECT_NEAR(g.state()[0], .01f * direction, 1e-7f);
	}
}

TEST(StaVelocityProtection, CorrectionStateLimitsAndUnconstrainedMappingMismatch)
{
	Guard g; auto c = config(); c.nu_limit[0] = .005f; c.acceleration_limit[1] = .5f;
	ASSERT_TRUE(g.configure(c, false)); auto f = flying(); g.begin(f); f.sample += 10000;
	const auto r = g.begin(f); auto proxy = r.a_req; proxy[0] = 0.f;
	const auto out = g.finish(proxy, 0, true); // No real X constraint: proxy mismatch alone is not ARW.
	EXPECT_TRUE(out.flags & Guard::StateLimit); EXPECT_TRUE(out.flags & Guard::CorrectionLimit);
	EXPECT_NEAR(g.state()[0], .005f, 1e-7f); EXPECT_FLOAT_EQ(g.state()[1], 0.f);
	EXPECT_FLOAT_EQ(out.a_sta[1], -1.f); EXPECT_FLOAT_EQ(out.a_req[1], -.6f);
}

TEST(StaVelocityProtection, FeedbackValidityAtomicAcrossAxesAndLatchedUntilDisarm)
{
	for (bool valid : {false, true}) {
		Guard g; auto f = flying(); prime(g, f); auto r = g.begin(f); auto p = r.a_req;
		if (valid) { p[1] = NAN; }
		EXPECT_TRUE(g.finish(p, 3, valid).fault & Guard::Feedback);
		EXPECT_FLOAT_EQ(g.state()[0], 0.f); EXPECT_FLOAT_EQ(g.state()[1], 0.f);
		f.sample += 10000; EXPECT_TRUE(g.begin(f).flags & Guard::Latched);
		f.armed = false; f.sample += 10000; EXPECT_EQ(g.begin(f).fault, 0);
		f.armed = true; f.sample += 10000; EXPECT_TRUE(g.begin(f).flags & Guard::Priming);
	}
}

TEST(StaVelocityProtection, RawTimeNeverClampedAndNonuniformUpdates)
{
	for (int64_t step : {-8000, 1000, 41000, 2000000}) {
		Guard g; auto f = flying(); prime(g, f); f.sample = 1000000 + step;
		EXPECT_TRUE(g.begin(f).fault & Guard::Time); EXPECT_FLOAT_EQ(g.state()[0], 0.f);
	}
	Guard g; auto f = flying(); prime(g, f);
	for (uint64_t step : {8000, 12000, 8000, 12000}) {
		f.sample += step; auto r = g.begin(f); g.finish(r.a_req, 0, true); EXPECT_EQ(r.fault, 0);
	}
	EXPECT_NEAR(g.state()[0], .05f, 1e-6f); // 18 + 12 + 8 + 12 ms from priming sample.
}

TEST(StaVelocityProtection, NaNPairsAccelerationOnlyAndInvalidRecovery)
{
	Guard g; auto f = flying(); prime(g, f); f.target = {{NAN, NAN, 0.f}};
	EXPECT_EQ(g.begin(f).active_axes, 0); EXPECT_FLOAT_EQ(g.state()[0], 0.f);
	f.sample += 10000; f.target = {{0.f, 0.f, 0.f}}; EXPECT_TRUE(g.begin(f).flags & Guard::Priming);
	f.sample += 10000; f.target[1] = NAN; EXPECT_TRUE(g.begin(f).fault & Guard::Measurement);
	f.sample += 10000; f.target[1] = 0.f; EXPECT_TRUE(g.begin(f).flags & Guard::Latched);
	Guard bad; f = flying(); prime(bad, f); f.velocity[0] = NAN;
	EXPECT_TRUE(bad.begin(f).fault & Guard::Measurement);
	Guard infinite; f = flying(); prime(infinite, f); f.target = {{INFINITY, INFINITY, 0.f}};
	EXPECT_TRUE(infinite.begin(f).fault & Guard::Measurement);
}

TEST(StaVelocityProtection, GroundRampContactBounceCancellationTimeoutExitReentry)
{
	Guard g; auto f = flying(); prime(g, f); auto r = g.begin(f); g.finish(r.a_req, 0, true);
	for (int state = 0; state < 5; ++state) {
		f = flying(f.sample + 10000);
		if (state == 0) { f.landed = true; } // cancellation / false airborne indication
		if (state == 1) { f.contact = true; } // contact or landing bounce
		if (state == 2) { f.flying = false; } // takeoff ramp, including timeout
		if (state == 3) { f.enabled = false; }
		if (state == 4) { f.armed = false; }
		EXPECT_TRUE(g.begin(f).flags & Guard::Inactive); EXPECT_FLOAT_EQ(g.state()[0], 0.f);
		for (int j = 0; j < 100; ++j) { f.sample += 10000; g.begin(f); }
		f.armed = f.enabled = f.flying = true; f.landed = f.contact = false; f.sample += 10000;
		EXPECT_TRUE(g.begin(f).flags & Guard::Priming);
		f.sample += 10000; r = g.begin(f); EXPECT_EQ(g.finish(r.a_req, 0, true).committed_axes, 3);
	}
}

TEST(StaVelocityProtection, CovariantEkfResetsAndHeadingDoNotEraseNu)
{
	Guard g; auto f = flying(); prime(g, f); auto r = g.begin(f); g.finish(r.a_req, 0, true);
	f.sample += 10000; f.velocity[0] += 5.f; f.target[0] += 5.f;
	r = g.begin(f); EXPECT_NEAR(r.nu_before[0], .01f, 1e-7f); EXPECT_FLOAT_EQ(r.s[0], -.25f);
	g.finish(r.a_req, 0, true);
	f.sample += 10000; f.unmatched_reset_axes = 4; EXPECT_EQ(g.begin(f).fault, 0); // Z not selected
	f.sample += 10000; f.unmatched_reset_axes = 1; EXPECT_TRUE(g.begin(f).fault & Guard::ResetMismatch);
	// Position/heading resets do not rotate world NED axes. Module must first
	// adjust legacy targets; no position or heading signal enters this guard.
}

TEST(StaVelocityProtection, ArmedConfigurationPendingCancelAndDisarmReset)
{
	Guard g; auto f = flying(); prime(g, f); const auto generation = g.generation(); auto c = config();
	c.gains[0].lambda2 = 2.f; EXPECT_TRUE(g.configure(c, true)); EXPECT_TRUE(g.pending());
	EXPECT_EQ(g.generation(), generation); EXPECT_TRUE(g.configure(config(), true)); EXPECT_FALSE(g.pending());
	EXPECT_TRUE(g.configure(c, false)); EXPECT_EQ(g.generation(), generation + 1);
	EXPECT_TRUE(g.begin(f).flags & Guard::Priming);
	c.axes = 7; EXPECT_TRUE(g.configure(c, false)); EXPECT_FALSE(g.rejected()); // E01-XYZ admission
	c.axes = 5; EXPECT_FALSE(g.configure(c, false)); EXPECT_TRUE(g.rejected());
	c = config(); c.gains[0].lambda1 = NAN; EXPECT_FALSE(g.configure(c, false));
}

TEST(StaVelocityProtection, ActualPidThrustMapShowsZPriorityTiltAndHteProxy)
{
	for (float hover : {.35f, .65f}) {
		PositionControl p;
		p.setPositionGains(matrix::Vector3f(1.f, 1.f, 1.f));
		p.setVelocityGains(matrix::Vector3f(1.f, 1.f, 1.f), matrix::Vector3f(), matrix::Vector3f());
		p.setVelocityLimits(2.f, 2.f, 2.f); p.setThrustLimits(.1f, .7f); p.setTiltLimit(.2f); p.setHoverThrust(hover);
		PositionControlStates state{}; p.setState(state);
		vehicle_local_position_setpoint_s sp{};
		sp.x = sp.y = sp.z = sp.vx = sp.vy = sp.vz = NAN;
		sp.acceleration[0] = 6.f; sp.acceleration[1] = -6.f; sp.acceleration[2] = -20.f;
		p.setInputSetpoint(sp); ASSERT_TRUE(p.update(.01f)); p.getLocalPositionSetpoint(sp);
		EXPECT_FLOAT_EQ(sp.thrust[2], -.7f); EXPECT_FLOAT_EQ(sp.thrust[0], 0.f); EXPECT_FLOAT_EQ(sp.thrust[1], 0.f);
		Guard g; auto f = flying(); f.velocity[1] = .25f; prime(g, f); g.begin(f);
		Guard::Vec proxy{{sp.thrust[0] * CONSTANTS_ONE_G / hover, sp.thrust[1] * CONSTANTS_ONE_G / hover,
			sp.thrust[2] * CONSTANTS_ONE_G / hover + CONSTANTS_ONE_G}};
		EXPECT_TRUE(g.finish(proxy, 3, true).flags & Guard::OutwardFreeze);
		EXPECT_FLOAT_EQ(g.state()[0], 0.f); EXPECT_FLOAT_EQ(g.state()[1], 0.f);
	}
}

TEST(StaVelocityProtection, ExcitationSmoothZeroIntegralAndClockGateSingleShot)
{
	double integral = 0., displacement = 0., max_displacement = 0.;
	for (int i = 0; i <= 32000; ++i) {
		const float v = VelocityDiagnosticExcitation::waveform(i * .001f);
		EXPECT_LE(fabsf(v), .200001f); integral += static_cast<double>(v) * .001;
		displacement += static_cast<double>(v) * .001; max_displacement = fmax(max_displacement, fabs(displacement));
	}
	EXPECT_NEAR(integral, 0., 1e-6); EXPECT_LT(max_displacement, .55);
	VelocityDiagnosticExcitation x;
	uint64_t sample = 1000000;
	EXPECT_FLOAT_EQ(x.update(sample, false, false), 0.f);
	for (int i = 0; i < 1400; ++i) { sample += 10000; x.update(sample, true, true); }
	EXPECT_GT(fabsf(x.update(sample + 10000, true, true)), .005f);
	sample += 20000; EXPECT_FLOAT_EQ(x.update(sample, true, false), 0.f);
	EXPECT_FLOAT_EQ(x.update(sample + 10000, true, true), 0.f);
	x.update(sample + 20000, false, false); EXPECT_FLOAT_EQ(x.update(sample + 30000, true, true), 0.f);
	EXPECT_FLOAT_EQ(x.update(sample + 1000000, true, true), 0.f); // pause inhibits until next disarm
}
