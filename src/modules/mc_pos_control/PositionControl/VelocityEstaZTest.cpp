// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>
#include <PositionControl.hpp>
#include "../../../../research/sta-velocity-control/z_velocity/StaVelocityZPrototype.hpp"

namespace {
using Z = StaVelocityZPrototype;
Z::Frame flying()
{
	Z::Frame f{}; f.sample = 1000000; f.armed = f.flying = true;
	f.landed = f.contact = false; return f;
}
float actualMap(float acceleration, float hover)
{
	PositionControl p;
	p.setPositionGains(matrix::Vector3f(1.f, 1.f, 1.f));
	p.setVelocityGains(matrix::Vector3f(1.f, 1.f, 1.f), matrix::Vector3f(), matrix::Vector3f());
	p.setVelocityLimits(12.f, 3.f, 1.f); p.setThrustLimits(.12f, 1.f);
	p.setTiltLimit(.7f); p.setHoverThrust(hover);
	p.setState({matrix::Vector3f(), matrix::Vector3f(), matrix::Vector3f(), 0.f});
	vehicle_local_position_setpoint_s sp{};
	sp.x = sp.y = sp.z = sp.vx = sp.vy = sp.vz = NAN;
	sp.acceleration[2] = acceleration;
	p.setInputSetpoint(sp); EXPECT_TRUE(p.update(.008f));
	p.getLocalPositionSetpoint(sp); return sp.thrust[2];
}
}

TEST(VelocityEstaZ, ProductionAdmissionStillRejectsZAndXyz)
{
	VelocityControlSelector selector;
	for (int axes : {4, 7}) {
		selector.configure(1, axes, false, true);
		EXPECT_EQ(selector.effectiveMode(), 0);
		EXPECT_NE(selector.reject(), 0);
	}
}

TEST(VelocityEstaZ, DirectionHoverAndRealPositionControlMapping)
{
	for (float target : {-.25f, 0.f, .25f}) {
		Z z; ASSERT_TRUE(z.configure({})); auto f = flying(); ASSERT_TRUE(z.enter(f, 0.f));
		f.sample += 8000; f.target = target; const auto o = z.evaluate(f); ASSERT_TRUE(o.valid);
		EXPECT_NEAR(o.a_ideal, std::copysign(std::sqrt(std::abs(target)), target), 1e-6f);
		EXPECT_NEAR(o.thrust_applied, actualMap(o.a_applied_request, z.hover()), 1e-6f);
		if (target < 0) { EXPECT_LT(o.thrust_applied, -.5f); }
		if (target > 0) { EXPECT_GT(o.thrust_applied, -.5f); }
		if (std::abs(target) <= 0.f) { EXPECT_FLOAT_EQ(o.thrust_applied, -.5f); }
	}
}

TEST(VelocityEstaZ, PidHandoverUsesOldNuAndFeedforwardOnce)
{
	Z z; ASSERT_TRUE(z.configure({})); auto f = flying(); f.velocity = .04f; f.ff = .15f;
	ASSERT_TRUE(z.enter(f, -.3f)); const float before = z.state()[2];
	f.sample += 12000; auto o = z.evaluate(f); ASSERT_TRUE(o.valid);
	EXPECT_NEAR(o.a_ideal, -.3f, 1e-6f); EXPECT_FLOAT_EQ(z.state()[2], before);
	EXPECT_NEAR(o.nu_ideal, before - .012f * .2f, 1e-7f);
	EXPECT_FALSE(z.commit(f.sample + 1)); EXPECT_FLOAT_EQ(z.state()[2], before);
	ASSERT_TRUE(z.commit(f.sample)); EXPECT_FALSE(z.commit(f.sample));
	EXPECT_FLOAT_EQ(z.state()[2], o.nu_applied);
	EXPECT_FLOAT_EQ(z.state()[0], 0.f); EXPECT_FLOAT_EQ(z.state()[1], 0.f);
}

TEST(VelocityEstaZ, NoGroundRampContactOrLandedOutputAndFreshReentry)
{
	for (int state = 0; state < 4; ++state) {
		Z z; ASSERT_TRUE(z.configure({})); auto f = flying(); auto ground = f;
		if (state == 0) { ground.armed = false; }
		if (state == 1) { ground.flying = false; }
		if (state == 2) { ground.contact = true; }
		if (state == 3) { ground.landed = true; }
		EXPECT_FALSE(z.enter(ground, 0.f)); ASSERT_TRUE(z.enter(f, .2f));
		f.sample += 8000; ASSERT_TRUE(z.evaluate(f).valid);
		EXPECT_FALSE(z.evaluate(ground).valid); EXPECT_FALSE(z.commit(f.sample));
		EXPECT_FLOAT_EQ(z.state()[2], 0.f); EXPECT_FALSE(z.active());
		f.sample += 8000; ASSERT_TRUE(z.enter(f, -.1f)); f.sample += 8000;
		EXPECT_NEAR(z.evaluate(f).a_ideal, -.1f, 1e-6f);
	}
}

TEST(VelocityEstaZ, TimestampBoundariesDuplicatesAndLatch)
{
	for (int delta : {-8000, 0, 1, 1999, 2000, 8000, 12000, 40000, 40001, 1000000}) {
		Z z; ASSERT_TRUE(z.configure({})); auto f = flying(); ASSERT_TRUE(z.enter(f, 0.f));
		f.sample += delta; auto o = z.evaluate(f);
		const bool valid = delta >= 2000 && delta <= 40000;
		EXPECT_EQ(o.valid, valid); EXPECT_EQ(z.fault(), !valid);
		if (valid) { ASSERT_TRUE(z.commit(f.sample)); EXPECT_FALSE(z.evaluate(f).valid); }
		f.sample += 8000; EXPECT_FALSE(z.evaluate(f).valid);
		z.reset(); EXPECT_FALSE(z.fault()); EXPECT_TRUE(z.enter(f, 0.f));
	}
}

TEST(VelocityEstaZ, PendingCandidateCannotBeOverwrittenOrRetuned)
{
	Z z; ASSERT_TRUE(z.configure({})); auto f = flying(); ASSERT_TRUE(z.enter(f, 0.f));
	EXPECT_FALSE(z.configure({})); f.sample += 8000; ASSERT_TRUE(z.evaluate(f).valid);
	EXPECT_FALSE(z.rebaseHover(.55f, 0.f, 0.f, 0.f));
	f.sample += 8000; EXPECT_FALSE(z.evaluate(f).valid); EXPECT_TRUE(z.fault());
	EXPECT_FALSE(z.commit(f.sample - 8000)); EXPECT_FLOAT_EQ(z.state()[2], 0.f);
}

TEST(VelocityEstaZ, InvalidConfigurationAndEntryAreNonMutating)
{
	for (int field = 0; field < 8; ++field) {
		Z z; Z::Config c{};
		if (field == 0) { c.gains.lambda1 = 0.f; }
		if (field == 1) { c.gains.lambda2 = INFINITY; }
		if (field == 2) { c.nu_limit = NAN; }
		if (field == 3) { c.acceleration_limit = -1.f; }
		if (field == 4) { c.hover = .05f; }
		if (field == 5) { c.thrust_min = c.hover; }
		if (field == 6) { c.thrust_max = 2.f; }
		if (field == 7) { c.gains.lambda1 = std::numeric_limits<float>::denorm_min(); }
		EXPECT_FALSE(z.configure(c)); EXPECT_FALSE(z.enter(flying(), 0.f));
	}
	Z z; ASSERT_TRUE(z.configure({})); auto f = flying();
	for (float bad : {NAN, INFINITY, -INFINITY, 10.f}) { EXPECT_FALSE(z.enter(f, bad)); }
	f.ff = 100.f; EXPECT_FALSE(z.enter(f, 0.f));
	EXPECT_FALSE(z.active()); EXPECT_FLOAT_EQ(z.state()[2], 0.f);
}

TEST(VelocityEstaZ, InvalidMeasurementAndOverflowDoNotCommit)
{
	for (int field = 0; field < 5; ++field) {
		Z z; ASSERT_TRUE(z.configure({})); auto f = flying(); ASSERT_TRUE(z.enter(f, 0.f));
		f.sample += 8000;
		if (field == 0) { f.velocity = NAN; }
		if (field == 1) { f.target = INFINITY; }
		if (field == 2) { f.ff = NAN; }
		if (field == 3) { f.velocity = std::numeric_limits<float>::max(); f.target = -f.velocity; }
		if (field == 4) { f.sample = 0; }
		EXPECT_FALSE(z.evaluate(f).valid); EXPECT_TRUE(z.fault());
		EXPECT_FALSE(z.commit(f.sample)); EXPECT_FLOAT_EQ(z.state()[2], 0.f);
	}
}

TEST(VelocityEstaZ, KernelUnderflowAndOverflowArePropagated)
{
	for (bool underflow : {false, true}) {
		Z z; Z::Config c{};
		if (underflow) { c.gains.lambda2 = std::numeric_limits<float>::min(); }
		else { c.gains.lambda1 = std::numeric_limits<float>::max(); }
		ASSERT_TRUE(z.configure(c)); auto f = flying(); ASSERT_TRUE(z.enter(f, 0.f));
		f.sample += 8000; f.target = 4.f;
		EXPECT_FALSE(z.evaluate(f).valid); EXPECT_TRUE(z.fault());
		EXPECT_FALSE(z.commit(f.sample)); EXPECT_FLOAT_EQ(z.state()[2], 0.f);
	}
}

TEST(VelocityEstaZ, CorrectionLimitsFreezeOnlyDeeperIncrement)
{
	for (float sign : {-1.f, 1.f}) {
		Z z; Z::Config c{}; c.acceleration_limit = .2f; ASSERT_TRUE(z.configure(c));
		auto f = flying(); ASSERT_TRUE(z.enter(f, 0.f)); f.sample += 8000; f.target = sign;
		auto o = z.evaluate(f); ASSERT_TRUE(o.valid); EXPECT_TRUE(o.limited);
		EXPECT_NEAR(o.a_applied_request, sign * .2f, 1e-6f);
		EXPECT_FLOAT_EQ(o.nu_applied, 0.f); EXPECT_NE(o.nu_ideal, 0.f);
		ASSERT_TRUE(z.commit(f.sample));
	}
}

TEST(VelocityEstaZ, BothThrustLimitsAndRecoveryDirection)
{
	for (float sign : {-1.f, 1.f}) {
		for (bool deepen : {false, true}) {
			Z z; ASSERT_TRUE(z.configure({})); auto f = flying(); ASSERT_TRUE(z.enter(f, 0.f));
			f.sample += 8000; f.ff = sign * 30.f; f.target = (deepen ? sign : -sign) * .04f;
			const auto o = z.evaluate(f); ASSERT_TRUE(o.valid); EXPECT_TRUE(o.limited);
			EXPECT_NEAR(o.thrust_applied, sign > 0.f ? -.12f : -1.f, 1e-6f);
			EXPECT_NEAR(o.thrust_applied, actualMap(o.a_applied_request, .5f), 1e-6f);
			if (deepen) { EXPECT_FLOAT_EQ(o.nu_applied, 0.f); }
			else { EXPECT_FLOAT_EQ(o.nu_applied, o.nu_ideal); }
			EXPECT_NE(o.a_ideal, o.acceleration_proxy);
		}
	}
}

TEST(VelocityEstaZ, NuLimitAndCrossObjectIsolation)
{
	Z a, b; Z::Config c{}; c.nu_limit = .001f;
	ASSERT_TRUE(a.configure(c)); ASSERT_TRUE(b.configure(c)); auto f = flying();
	ASSERT_TRUE(a.enter(f, 0.f)); ASSERT_TRUE(b.enter(f, 0.f));
	f.sample += 8000; f.target = .04f; const auto o = a.evaluate(f); ASSERT_TRUE(o.valid);
	EXPECT_FLOAT_EQ(o.nu_applied, .001f); EXPECT_FALSE(b.commit(f.sample));
	ASSERT_TRUE(a.commit(f.sample)); EXPECT_FLOAT_EQ(b.state()[2], 0.f);
	a.reset(); EXPECT_FALSE(a.commit(f.sample)); EXPECT_FLOAT_EQ(a.state()[2], 0.f);
}

TEST(VelocityEstaZ, HoverRebaseMaintainsThrustAtNonzeroErrorAndFeedforward)
{
	for (float h : {.45f, .55f}) {
		Z z; ASSERT_TRUE(z.configure({})); auto f = flying(); f.velocity = .04f; f.ff = .1f;
		ASSERT_TRUE(z.enter(f, -.2f)); const float before = actualMap(-.2f, .5f);
		ASSERT_TRUE(z.rebaseHover(h, f.velocity, f.target, f.ff));
		f.sample += 8000; const auto o = z.evaluate(f); ASSERT_TRUE(o.valid);
		EXPECT_NEAR(o.thrust_applied, before, 1e-6f);
		EXPECT_NEAR(actualMap(o.a_applied_request, h), before, 1e-6f);
	}
}

TEST(VelocityEstaZ, HoverRebaseRejectsClippingAndInvalidValues)
{
	Z z; Z::Config c{}; c.nu_limit = .1f; ASSERT_TRUE(z.configure(c));
	auto f = flying(); ASSERT_TRUE(z.enter(f, 0.f));
	for (float h : {NAN, 0.f, .9f}) {
		EXPECT_FALSE(z.rebaseHover(h, 0.f, 0.f, 0.f)); EXPECT_FLOAT_EQ(z.hover(), .5f);
		EXPECT_FLOAT_EQ(z.state()[2], 0.f);
	}
	EXPECT_FALSE(z.rebaseHover(.5f, 0.f, 0.f, 30.f));
}

TEST(VelocityEstaZ, IndependentDoubleSequenceAtMeasuredPeriods)
{
	for (int period : {8000, 12000}) {
		Z z; ASSERT_TRUE(z.configure({})); auto f = flying(); ASSERT_TRUE(z.enter(f, .15f));
		double nu = .15f;
		for (int k = 1; k <= 2048; ++k) {
			f.sample += period; f.velocity = float(.1 * std::sin(k * .02));
			f.target = float(.05 * std::cos(k * .03)); f.ff = .12f;
			const double s = double(f.velocity) - double(f.target);
			const double a = -std::copysign(std::sqrt(std::abs(s)), s) + nu + double(f.ff);
			const auto o = z.evaluate(f); ASSERT_TRUE(o.valid); ASSERT_FALSE(o.limited);
			EXPECT_NEAR(o.a_ideal, a, 2e-6);
			nu -= period * 1e-6 * double(.2f) * ((s > 0.) - (s < 0.));
			ASSERT_TRUE(z.commit(f.sample)); EXPECT_NEAR(z.state()[2], nu, 2e-6);
		}
	}
}

TEST(VelocityEstaZ, IndependentVerticalObjectConstantRampAndLag)
{
	for (int period : {8000, 12000}) {
		for (bool lagged : {false, true}) {
			for (double disturbance_sign : {-1., 0., 1.}) {
			Z z; ASSERT_TRUE(z.configure({})); auto f = flying(); ASSERT_TRUE(z.enter(f, 0.f));
			double v = 0., applied = 0.; const double dt = period * 1e-6;
			double squared = 0.; int count = 0;
			for (int k = 1; k <= 2500; ++k) {
				f.sample += period; f.velocity = float(v);
				f.target = float(.1 * std::sin(k * dt)); f.ff = float(.1 * std::cos(k * dt));
				const auto o = z.evaluate(f); ASSERT_TRUE(o.valid); ASSERT_TRUE(z.commit(f.sample));
				// Separate ZOH object: vertical thrust force + gravity, fixed H=.5.
				const double demanded = 9.80665 * (double(o.thrust_applied) / .5 + 1.);
				applied = lagged ? demanded + (applied - demanded) * std::exp(-dt / .06) : demanded;
				const double disturbance = disturbance_sign * (.08 + .001 * std::max(0, k - 1000) * dt);
				v += dt * (applied + disturbance);
				ASSERT_TRUE(std::isfinite(v)); ASSERT_LT(std::abs(v), .5);
				if (k > 1500) { squared += std::pow(v - .1 * std::sin((k + 1) * dt), 2); ++count; }
			}
			EXPECT_LT(std::sqrt(squared / count), lagged ? .02 : .005);
			}
		}
	}
}
