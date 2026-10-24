// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>
#include "PositionControl.hpp"
#include <ecl/geo/geo.h>
#include <algorithm>
#include <cmath>
#include <cstring>
#include "../../../../research/sta-velocity-control/regularized_ista/ri04_hte_fix/recorded_hte_fixture.hpp"

// Defined only in an offline test translation unit. No production caller.
class RegularizedIstaVelocityTestAccess
{
public:
	static void admit(PositionControl &p) { p._regularized_ista_admission = true; }
	static void staleHteCache(PositionControl &p, bool generation)
	{
		if (generation) { ++p._rista_cache_generation; } else { ++p._rista_cache_sample; }
	}
};

namespace
{
using Guard = StaVelocityProtection;
using matrix::Vector3f;

Guard::Config config(uint8_t axes)
{
	Guard::Config c{};
	c.axes = axes; c.variant = 4;
	c.gains[0] = {.5f, .1f}; c.gains[1] = {.5f, .1f}; c.gains[2] = {2.f, 1.f};
	c.epsilon = {{.01f, .01f, .02f}};
	c.nu_limit = {{.4f, .4f, 4.f}}; c.acceleration_limit = {{.8f, .8f, 6.f}};
	return c;
}

void setup(PositionControl &p, uint8_t axes, bool admit = true)
{
	p.setPositionGains(Vector3f(.95f, .95f, 1.f));
	p.setVelocityGains(Vector3f(2.16f, 2.16f, 4.f), Vector3f(.48f, .48f, 2.f), Vector3f(.24f, .24f, 0.f));
	p.setVelocityLimits(12.f, 3.f, .55f);
	p.setThrustLimits(.12f, 1.f); p.setTiltLimit(.7f); p.setHoverThrust(.5f);
	p.configureVelocityDivisor(1, false);

	if (admit) { RegularizedIstaVelocityTestAccess::admit(p); }

	if (axes) {
		p.configureVelocityEsta(config(axes), false); p.configureVelocityControl(4, axes, false);
	}
}

Guard::Frame frame()
{
	Guard::Frame f{};
	f.sample = 1000000; f.armed = f.enabled = true;
	f.flying = false; f.landed = f.contact = true;
	return f;
}

vehicle_local_position_setpoint_s target()
{
	vehicle_local_position_setpoint_s sp{};
	sp.x = sp.y = sp.z = NAN;
	sp.vx = .005f; sp.vy = -.005f; sp.vz = -.005f;
	sp.acceleration[0] = .02f; sp.acceleration[1] = -.01f; sp.acceleration[2] = .03f;
	sp.yaw = .02f; sp.yawspeed = .01f;
	return sp;
}

bool step(PositionControl &p, const Guard::Frame &f, const vehicle_local_position_setpoint_s &sp,
	  float legacy_dt = .01f, Vector3f velocity = Vector3f(.01f, -.01f, .01f))
{
	p.setVelocityFrame(f);
	p.setState({Vector3f(), velocity, Vector3f(.001f, -.001f, .002f), .01f});
	p.setInputSetpoint(sp);
	return p.update(legacy_dt);
}

void engage(PositionControl &p, Guard::Frame &f, const vehicle_local_position_setpoint_s &sp = target())
{
	ASSERT_TRUE(step(p, f, sp));
	f.sample += 8000; f.flying = true; f.landed = f.contact = false;
	ASSERT_TRUE(step(p, f, sp));
	f.sample += 12000;
	ASSERT_TRUE(step(p, f, sp));
	ASSERT_TRUE(p.regularizedIstaDiagnostic().valid);
}

void sameVec(const Vector3f &a, const Vector3f &b)
{
	for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(a(i), b(i)); }
}

double rho(double p, double eps) { return std::max(-1., std::min(1., p / eps)); }
double psi(double p, double eps) { return std::sqrt(std::max(std::fabs(p), eps)) * rho(p, eps); }

double inverse(double s, double h, double l1, double l2, double eps)
{
	double lo = -std::fabs(s), hi = std::fabs(s);

	for (int k = 0; k < 180; ++k) {
		const double mid = lo + (hi - lo) * .5;
		const double residual = mid + h * l1 * psi(mid, eps) + h * h * l2 * rho(mid, eps) - s;

		if (residual < 0.) { lo = mid; } else { hi = mid; }
	}

	const double p = lo + (hi - lo) * .5;
	return l1 * psi(p, eps) + h * l2 * rho(p, eps);
}

// Reach the real production bound by normal updates, never by editing nu or
// relaxing gains/limits. Stop on the FIRST clipped commit, not a steady bound.
void reachStateLimit(PositionControl &p, Guard::Frame &f, vehicle_local_position_setpoint_s &sp, float error_sign)
{
	sp.vz = 0.f;
	const Vector3f velocity(.01f, -.01f, error_sign * .1f);
	ASSERT_TRUE(step(p, f, sp, .01f, velocity));
	f.sample += 8000; f.flying = true; f.landed = f.contact = false;
	ASSERT_TRUE(step(p, f, sp, .008f, velocity));
	for (unsigned k = 0; k < 800; ++k) {
		const unsigned us = k % 2 ? 12000 : 8000; f.sample += us;
		ASSERT_TRUE(step(p, f, sp, static_cast<float>(us) * 1e-6f, velocity));
		if (p.diagnostic().sta_flags & Guard::StateLimit) {
			ASSERT_EQ(p.diagnostic().sta_flags, Guard::StateLimit);
			ASSERT_EQ(p.diagnostic().constraint_bits, 0);
			ASSERT_EQ(p.regularizedIstaDiagnostic().commit_axes, 4);
			ASSERT_EQ(p.regularizedIstaDiagnostic().strict_axes, 0);
			ASSERT_FLOAT_EQ(p.diagnostic().nu_applied[2], -error_sign * 4.f);
			return;
		}
	}
	FAIL() << "Natural integration did not reach the frozen state limit";
}
}

TEST(RegularizedIstaPosition, RI04ProductionAdmitsOnlyXOrZAndUnknownMasksNeverAliasThem)
{
	for (const int axes : {-1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 257}) {
		PositionControl p; setup(p, 0, false);
		p.configureVelocityEsta(config(axes > 0 && axes < 8 ? static_cast<uint8_t>(axes) : 7), false);
		p.configureVelocityControl(4, axes, false);
		const bool admitted = axes == 1 || axes == 4;
		EXPECT_EQ(p.velocitySelection().reject() == 0, admitted);
		EXPECT_EQ(p.velocitySelection().requestedMode(), 4);
		EXPECT_EQ(p.velocitySelection().requestedAxes(), axes);
		EXPECT_EQ(p.velocitySelection().effectiveMode(), admitted ? 4 : 0);
		EXPECT_EQ(p.velocitySelection().effectiveAxes(), admitted ? axes : 0);
	}

	for (const int axes : {-1, 0, 2, 5, 6, 8, 257}) {
		PositionControl p; setup(p, 0);
		p.configureVelocityEsta(config(axes > 0 && axes < 8 ? static_cast<uint8_t>(axes) : 7), false);
		p.configureVelocityControl(4, axes, false);
		EXPECT_NE(p.velocitySelection().reject(), 0);
		EXPECT_EQ(p.velocitySelection().effectiveMode(), 0);
	}
}

TEST(RegularizedIstaPosition, RI03ProductionXPreservesActualYzPidArithmeticAndHoverThrustShift)
{
	PositionControl p; setup(p, 1, false); ASSERT_EQ(p.velocitySelection().effectiveMode(), 4);
	auto f = frame(); const auto sp = target(); engage(p, f, sp);
	for (unsigned k = 0; k < 256; ++k) {
		if (k == 128) {
			const auto before = p.velocityIntegral(); const float hover = p.diagnostic().hover_thrust;
			const float nu = p.diagnostic().nu_applied[0];
			p.updateHoverThrust(.505f);
			EXPECT_FLOAT_EQ(p.velocityIntegral()(0), before(0)); EXPECT_FLOAT_EQ(p.velocityIntegral()(1), before(1));
			EXPECT_FLOAT_EQ(p.velocityIntegral()(2), before(2) + (.505f - hover) * (CONSTANTS_ONE_G / .505f));
			EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[0], nu);
		}
		const auto integral = p.velocityIntegral();
		const uint64_t us = k % 2 ? 12000 : 8000; f.sample += us;
		ASSERT_TRUE(step(p, f, sp, static_cast<float>(us) * 1e-6f));
		ASSERT_TRUE(p.regularizedIstaDiagnostic().valid); EXPECT_EQ(p.regularizedIstaDiagnostic().commit_axes, 1);
		EXPECT_EQ(p.diagnostic().pid_axes, 6); EXPECT_FLOAT_EQ(p.velocityIntegral()(0), 0.f);
		const float expected_y = (sp.vy - -.01f) * 2.16f + integral(1) - -.001f * .24f;
		const float expected_z = (sp.vz - .01f) * 4.f + integral(2) - .002f * 0.f;
		EXPECT_FLOAT_EQ(p.velocityCorrection()(1), expected_y); EXPECT_FLOAT_EQ(p.velocityCorrection()(2), expected_z);
		vehicle_local_position_setpoint_s output{}; p.getLocalPositionSetpoint(output);
		EXPECT_FLOAT_EQ(output.acceleration[1], expected_y + sp.acceleration[1]);
		EXPECT_FLOAT_EQ(output.acceleration[2], expected_z + sp.acceleration[2]);
		EXPECT_TRUE(std::isnan(p.diagnostic().nu_applied[1])); EXPECT_TRUE(std::isnan(p.diagnostic().nu_applied[2]));
	}
}

TEST(RegularizedIstaPosition, ZAndXyzSeedMatchPidBoundaryAndImplicitInverseAtTrueSampleH)
{
	for (const uint8_t axes : {4, 7}) {
		for (const uint32_t us : {8000, 12000}) {
			PositionControl p, pid; setup(p, axes, axes != 4); setup(pid, 0);
			auto f = frame(); auto sp = target();
			ASSERT_TRUE(step(p, f, sp)); ASSERT_TRUE(step(pid, f, sp));
			f.sample += us; f.flying = true; f.landed = f.contact = false;
			ASSERT_TRUE(step(p, f, sp, .02f)); ASSERT_TRUE(step(pid, f, sp, .02f));
			ASSERT_EQ(p.diagnostic().z_phase, 2);
			EXPECT_FALSE(p.regularizedIstaDiagnostic().valid);
			EXPECT_EQ(p.regularizedIstaDiagnostic().commit_axes, 0);
			const float seed_h = p.regularizedIstaDiagnostic().seed_h;
			EXPECT_NEAR(seed_h, static_cast<float>(us) * 1e-6f, 1e-8f);
			const auto boundary = p.velocityCorrection();
			const auto c = config(axes);

			for (int i = 0; i < 3; ++i) {
				EXPECT_FLOAT_EQ(p.diagnostic().thrust[i], pid.diagnostic().thrust[i]);
				EXPECT_FLOAT_EQ(p.diagnostic().a_req[i], pid.diagnostic().a_req[i]);

				if (!(axes & (1u << i))) { continue; }

				const double correction = static_cast<double>(boundary(i));
				const double expected = correction + inverse(static_cast<double>(p.diagnostic().s[i]),
							static_cast<double>(seed_h), static_cast<double>(c.gains[i].lambda1),
							static_cast<double>(c.gains[i].lambda2), static_cast<double>(c.epsilon[i]));
				EXPECT_NEAR(static_cast<double>(p.diagnostic().nu_applied[i]), expected, 3e-7);
			}

			f.sample += us;
			ASSERT_TRUE(step(p, f, sp, .02f));
			EXPECT_FLOAT_EQ(p.regularizedIstaDiagnostic().h, seed_h);
			EXPECT_EQ(p.regularizedIstaDiagnostic().commit_axes, axes);

			for (int i = 0; i < 3; ++i) {
				if (axes & (1u << i)) { EXPECT_NEAR(p.regularizedIstaDiagnostic().a_ideal[i], boundary(i), 3e-7f); }
			}

			f.sample += us == 8000 ? 12000 : 8000;
			ASSERT_TRUE(step(p, f, sp, .02f));
			const auto &r = p.regularizedIstaDiagnostic();
			EXPECT_NEAR(r.h, us == 8000 ? .012f : .008f, 1e-8f);

			for (int i = 0; i < 3; ++i) {
				if (!(axes & (1u << i))) { continue; }

				const double expected = static_cast<double>(p.diagnostic().nu_before[i])
							- inverse(static_cast<double>(p.diagnostic().s[i]), static_cast<double>(r.h),
								  static_cast<double>(c.gains[i].lambda1), static_cast<double>(c.gains[i].lambda2),
								  static_cast<double>(c.epsilon[i]));
				EXPECT_NEAR(static_cast<double>(r.a_ideal[i]), expected, 4e-7);
			}
		}
	}
}

TEST(RegularizedIstaPosition, MissingGroundHistoryCannotInventSeedTiming)
{
	for (const uint8_t axes : {4, 7}) {
		PositionControl p; setup(p, axes, axes != 4);
		auto f = frame(); f.flying = true; f.landed = f.contact = false;
		EXPECT_FALSE(step(p, f, target()));
		EXPECT_FALSE(p.velocityOutputPublishable());
		EXPECT_EQ(p.regularizedIstaDiagnostic().commit_axes, 0);
		EXPECT_TRUE(p.diagnostic().fault);
	}
}

TEST(RegularizedIstaPosition, HteUsesClosedAppliedCacheDoesNotEvaluateAndPreservesFrozenMap)
{
	for (const uint8_t axes : {4, 7}) {
		PositionControl p; setup(p, axes, axes != 4); auto f = frame(); engage(p, f);
		ASSERT_TRUE(p.regularizedIstaDiagnostic().cache_valid);
		const auto before = p.regularizedIstaDiagnostic();
		const float nu = p.diagnostic().nu_applied[2];
		const float correction = p.velocityCorrection()(2);
		const float ff = p.diagnostic().a_ff[2];
		const float hover = p.diagnostic().hover_thrust;
		const uint32_t sequence = p.velocityDecimation().sequence;
		const float next_hover = .505f;
		const float shift = (hover / next_hover - 1.f) * (correction + ff - CONSTANTS_ONE_G);
		p.updateHoverThrust(next_hover);
		EXPECT_EQ(p.velocityDecimation().sequence, sequence);
		EXPECT_FLOAT_EQ(p.regularizedIstaDiagnostic().a_ideal[2], before.a_ideal[2]);
		EXPECT_FLOAT_EQ(p.regularizedIstaDiagnostic().nu_candidate[2], before.nu_candidate[2]);
		EXPECT_FLOAT_EQ(p.velocityCorrection()(2), correction + shift);
		const float old_map = (correction + ff - CONSTANTS_ONE_G) * hover;
		const float new_map = (p.velocityCorrection()(2) + ff - CONSTANTS_ONE_G) * next_hover;
		EXPECT_NEAR(old_map, new_map, 1e-6f);
		f.sample += 8000; ASSERT_TRUE(step(p, f, target()));
		EXPECT_FLOAT_EQ(p.diagnostic().nu_before[2], nu + shift);
		EXPECT_FLOAT_EQ(p.diagnostic().hover_thrust, next_hover);
		EXPECT_FLOAT_EQ(p.diagnostic().z_hte_shift, shift);
	}
}

TEST(RegularizedIstaPosition, HteWithoutCacheOrWithProtectedOutputFailsWithoutHoverCorruption)
{
	for (const bool protected_output : {false, true}) {
		PositionControl p; setup(p, 7); auto f = frame(); engage(p, f);

		if (protected_output) {
			p.setThrustLimits(.12f, .51f);
			auto sp = target(); sp.acceleration[2] = -20.f;
			f.sample += 8000; ASSERT_TRUE(step(p, f, sp));
			ASSERT_NE(p.diagnostic().constraint_bits, 0);
			ASSERT_FALSE(p.regularizedIstaDiagnostic().cache_valid);

		} else { p.resetIntegral(); }

		const float hover = p.diagnostic().hover_thrust;
		const Vector3f integral = p.velocityIntegral();
		const auto before = p.regularizedIstaDiagnostic().nu_applied;
		p.updateHoverThrust(.505f);
		f.sample += 12000; EXPECT_FALSE(step(p, f, target()));
		EXPECT_FALSE(p.velocityOutputPublishable());
		EXPECT_FLOAT_EQ(p.diagnostic().hover_thrust, hover);
		sameVec(p.velocityIntegral(), integral);

		for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(p.regularizedIstaDiagnostic().nu_applied[i], before[i]); }
	}
}

TEST(RegularizedIstaPosition, RepeatedSampleFailsafeDoesNotIntegrateRemainingPidOrNuTwice)
{
	for (const uint8_t axes : {1, 3, 4, 7}) {
		PositionControl p; setup(p, axes, axes != 1 && axes != 4); auto f = frame(); engage(p, f);
		const Vector3f integral = p.velocityIntegral();
		const auto nu = p.regularizedIstaDiagnostic().nu_applied;
		const uint32_t sequence = p.velocityDecimation().sequence;
		auto retry = target(); retry.vx = retry.vy = retry.vz = 0.f;
		EXPECT_FALSE(step(p, f, retry));
		EXPECT_FALSE(p.velocityOutputPublishable());
		EXPECT_EQ(p.velocityDecimation().sequence, sequence);
		EXPECT_FALSE(p.velocityDecimation().updated);
		sameVec(p.velocityIntegral(), integral);

		for (int i = 0; i < 3; ++i) {
			if (axes & (1u << i)) { EXPECT_FLOAT_EQ(p.regularizedIstaDiagnostic().nu_applied[i], nu[i]); }
		}

		EXPECT_EQ(p.regularizedIstaDiagnostic().commit_axes, 0);
		EXPECT_EQ(p.regularizedIstaDiagnostic().strict_axes, 0);
		f.sample += 8000; EXPECT_FALSE(step(p, f, target()));
		f.armed = false; f.sample += 12000; ASSERT_TRUE(step(p, f, target()));
		f.armed = true; f.sample += 8000; ASSERT_TRUE(step(p, f, target()));
		f.sample += 12000; ASSERT_TRUE(step(p, f, target()));
		EXPECT_TRUE(p.regularizedIstaDiagnostic().valid);
	}
}

TEST(RegularizedIstaPosition, XyzNormalAlgorithmDoesNotCalculateUnusedPid)
{
	PositionControl p; setup(p, 7); auto f = frame(); engage(p, f);
	p.setVelocityGains(Vector3f(NAN, NAN, NAN), Vector3f(NAN, NAN, NAN), Vector3f(NAN, NAN, NAN));
	f.sample += 8000;
	ASSERT_TRUE(step(p, f, target()));
	EXPECT_EQ(p.diagnostic().pid_axes, 0);
	EXPECT_EQ(p.regularizedIstaDiagnostic().commit_axes, 7);
	for (int axis = 0; axis < 3; ++axis) { EXPECT_TRUE(std::isfinite(p.velocityIntegral()(axis))); }
	EXPECT_FLOAT_EQ(p.velocityIntegral().norm(), 0.f);
}

TEST(RegularizedIstaPosition, HorizontalVectorAndVerticalPriorityLimitsFreezeThenRecover)
{
	for (const uint8_t axes : {3, 7}) {
		PositionControl p; setup(p, axes); auto f = frame(); engage(p, f);
		p.setTiltLimit(.001f);
		auto sp = target(); sp.vx = .1f; sp.vy = -.1f;
		f.sample += 8000; ASSERT_TRUE(step(p, f, sp));
		EXPECT_NE(p.diagnostic().constraint_bits & 1, 0);
		EXPECT_EQ(p.regularizedIstaDiagnostic().strict_axes & 3, 0);
		p.setTiltLimit(.7f); p.setThrustLimits(.12f, .51f);
		sp.acceleration[2] = -20.f;
		f.sample += 12000; ASSERT_TRUE(step(p, f, sp));
		EXPECT_NE(p.diagnostic().constraint_bits & 4, 0);
		EXPECT_FLOAT_EQ(p.diagnostic().thrust[0], 0.f);
		EXPECT_FLOAT_EQ(p.diagnostic().thrust[1], 0.f);
		EXPECT_EQ(p.regularizedIstaDiagnostic().strict_axes, 0);
		p.setThrustLimits(.12f, 1.f);
		f.sample += 8000; ASSERT_TRUE(step(p, f, target()));
		EXPECT_EQ(p.diagnostic().constraint_bits, 0);
		EXPECT_EQ(p.regularizedIstaDiagnostic().strict_axes, axes);
	}
}

TEST(RegularizedIstaPosition, DisarmedAlgorithmChangeInvalidatesCacheAndStateAcrossTakeoffs)
{
	PositionControl p; setup(p, 7); auto f = frame(); engage(p, f);
	const auto old_generation = p.velocityEstaGeneration();
	p.configureVelocityControl(0, 0, true);
	EXPECT_TRUE(p.velocitySelection().pending());
	EXPECT_EQ(p.velocitySelection().effectiveMode(), 4);
	p.configureVelocityControl(4, 7, true);
	EXPECT_FALSE(p.velocitySelection().pending());
	f.armed = false; f.sample += 8000; ASSERT_TRUE(step(p, f, target()));
	EXPECT_FALSE(p.regularizedIstaDiagnostic().cache_valid);
	p.configureVelocityControl(0, 0, false);
	EXPECT_EQ(p.velocitySelection().effectiveMode(), 0);
	EXPECT_GT(p.velocityEstaGeneration(), old_generation);
	p.configureVelocityEsta(config(4), false); p.configureVelocityControl(4, 4, false);
	EXPECT_FALSE(p.regularizedIstaDiagnostic().cache_valid);
	f.sample += 12000; f.flying = false; f.landed = f.contact = true;
	ASSERT_TRUE(step(p, f, target()));
	f.armed = true; f.sample += 8000; ASSERT_TRUE(step(p, f, target()));
	f.sample += 12000; f.flying = true; f.landed = f.contact = false;
	ASSERT_TRUE(step(p, f, target()));
	EXPECT_EQ(p.diagnostic().z_phase, 2);
	EXPECT_EQ(p.regularizedIstaDiagnostic().commit_axes, 0);
	f.sample += 8000; ASSERT_TRUE(step(p, f, target()));
	EXPECT_EQ(p.regularizedIstaDiagnostic().commit_axes, 4);
	EXPECT_EQ(p.diagnostic().pid_axes, 3);
}

TEST(RegularizedIstaPosition, HalfNaNAndResetMismatchNeverPartiallyUpdateOrReuseCache)
{
	for (int kind = 0; kind < 3; ++kind) {
		PositionControl p; setup(p, 7); auto f = frame(); engage(p, f);
		const auto before = p.regularizedIstaDiagnostic().nu_applied;
		const auto integral = p.velocityIntegral();
		auto sp = target();

		if (kind == 0) { sp.vx = NAN; }

		if (kind == 1) { sp.acceleration[1] = NAN; }

		if (kind == 2) { f.unmatched_reset_axes = 4; }

		f.sample += 8000;
		EXPECT_FALSE(step(p, f, sp));
		EXPECT_FALSE(p.regularizedIstaDiagnostic().cache_valid);
		EXPECT_EQ(p.regularizedIstaDiagnostic().commit_axes, 0);
		EXPECT_EQ(p.regularizedIstaDiagnostic().strict_axes, 0);
		sameVec(p.velocityIntegral(), integral);

		for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(p.regularizedIstaDiagnostic().nu_applied[i], before[i]); }
	}
}

TEST(RegularizedIstaPosition, FirstGuardTimeOrLastAxisFailureDoesNotClaimARealUpdate)
{
	for (int kind = 0; kind < 3; ++kind) {
		PositionControl p; setup(p, 7); auto f = frame(); engage(p, f);
		const auto before = p.regularizedIstaDiagnostic().nu_applied;
		const auto integral = p.velocityIntegral();
		const uint32_t sequence = p.velocityDecimation().sequence;
		f.sample += kind == 0 ? 41000 : 8000;
		p.setVelocityFrame(f);
		Vector3f velocity(.01f, -.01f, .01f);
		Vector3f derivative(.001f, -.001f, .002f);

		if (kind == 1) { velocity(2) = NAN; }

		// XYZ's kernel can evaluate all candidates before the downstream final
		// validity check rejects the last measured derivative. No partial commit.
		if (kind == 2) { derivative(2) = INFINITY; }

		p.setState({Vector3f(), velocity, derivative, .01f});
		p.setInputSetpoint(target());
		EXPECT_FALSE(p.update(.01f));
		EXPECT_EQ(p.velocityDecimation().sequence, sequence);
		EXPECT_FALSE(p.velocityDecimation().updated);
		EXPECT_FALSE(p.velocityDecimation().held);
		EXPECT_FALSE(p.velocityOutputPublishable());
		EXPECT_FALSE(p.regularizedIstaDiagnostic().cache_valid);
		EXPECT_EQ(p.regularizedIstaDiagnostic().commit_axes, 0);
		EXPECT_EQ(p.regularizedIstaDiagnostic().strict_axes, 0);
		sameVec(p.velocityIntegral(), integral);

		for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(p.regularizedIstaDiagnostic().nu_applied[i], before[i]); }
	}
}

TEST(RegularizedIstaPosition, RI04ProductionZPreservesXyPidArithmeticAndNeverIntegratesIdleZPid)
{
	PositionControl p; setup(p, 4, false); ASSERT_EQ(p.velocitySelection().effectiveAxes(), 4);
	auto f = frame(); const auto sp = target(); engage(p, f, sp);
	const float idle_z_integral = p.velocityIntegral()(2);
	// Poison only the unused Z PID gains after handover. XY still uses actual PID.
	p.setVelocityGains(Vector3f(2.16f, 2.16f, NAN), Vector3f(.48f, .48f, NAN), Vector3f(.24f, .24f, NAN));
	for (unsigned k = 0; k < 256; ++k) {
		const auto integral = p.velocityIntegral();
		const uint64_t us = k % 2 ? 12000 : 8000; f.sample += us;
		ASSERT_TRUE(step(p, f, sp, static_cast<float>(us) * 1e-6f));
		ASSERT_TRUE(p.regularizedIstaDiagnostic().valid);
		EXPECT_EQ(p.regularizedIstaDiagnostic().commit_axes, 4); EXPECT_EQ(p.diagnostic().pid_axes, 3);
		EXPECT_FLOAT_EQ(p.velocityIntegral()(2), idle_z_integral);
		vehicle_local_position_setpoint_s output{}; p.getLocalPositionSetpoint(output);
		for (int i = 0; i < 2; ++i) {
			const float error = i == 0 ? sp.vx - .01f : sp.vy - -.01f;
			const float derivative = i == 0 ? .001f : -.001f;
			const float expected = error * 2.16f + integral(i) - derivative * .24f;
			EXPECT_FLOAT_EQ(p.velocityCorrection()(i), expected);
			EXPECT_FLOAT_EQ(output.acceleration[i], expected + sp.acceleration[i]);
			EXPECT_TRUE(std::isnan(p.diagnostic().nu_applied[i]));
			EXPECT_TRUE(std::isnan(p.regularizedIstaDiagnostic().nu_candidate[i]));
		}
	}
}

TEST(RegularizedIstaPosition, RI04ProductionZHasVerticalPriorityOverMixedXyPidAndRecovers)
{
	PositionControl p; setup(p, 4, false); auto f = frame(); engage(p, f);
	p.setThrustLimits(.12f, .51f);
	auto sp = target(); sp.vx = .1f; sp.vy = -.1f; sp.acceleration[2] = -20.f;
	f.sample += 8000; ASSERT_TRUE(step(p, f, sp));
	EXPECT_EQ(p.diagnostic().pid_axes, 3); EXPECT_EQ(p.regularizedIstaDiagnostic().commit_axes, 4);
	EXPECT_NE(p.diagnostic().constraint_bits & 4, 0); EXPECT_EQ(p.regularizedIstaDiagnostic().strict_axes, 0);
	EXPECT_FLOAT_EQ(p.diagnostic().thrust[2], -.51f);
	EXPECT_FLOAT_EQ(p.diagnostic().thrust[0], 0.f); EXPECT_FLOAT_EQ(p.diagnostic().thrust[1], 0.f);
	EXPECT_FALSE(p.regularizedIstaDiagnostic().cache_valid);
	p.setThrustLimits(.12f, 1.f); f.sample += 12000; ASSERT_TRUE(step(p, f, target()));
	EXPECT_EQ(p.diagnostic().constraint_bits, 0); EXPECT_EQ(p.regularizedIstaDiagnostic().strict_axes, 4);
	EXPECT_TRUE(p.regularizedIstaDiagnostic().cache_valid);
}

TEST(RegularizedIstaPosition, RI04ProductionZHteRejectsInvalidOrUnclosedCacheWithoutCorruptingState)
{
	for (int kind = 0; kind < 4; ++kind) {
		PositionControl p; setup(p, 4, false); auto f = frame(); engage(p, f);
		if (kind == 0) { p.resetIntegral(); }
		if (kind == 1) {
			p.setThrustLimits(.12f, .51f); auto sp = target(); sp.acceleration[2] = -20.f;
			f.sample += 8000; ASSERT_TRUE(step(p, f, sp)); ASSERT_FALSE(p.regularizedIstaDiagnostic().cache_valid);
		}
		const float hover = p.diagnostic().hover_thrust, nu = p.diagnostic().nu_applied[2];
		const auto integral = p.velocityIntegral();
		p.updateHoverThrust(kind == 2 ? NAN : (kind == 3 ? 1.f : .505f));
		f.sample += 12000; EXPECT_FALSE(step(p, f, target()));
		EXPECT_FALSE(p.velocityOutputPublishable()); EXPECT_FALSE(p.regularizedIstaDiagnostic().cache_valid);
		EXPECT_FLOAT_EQ(p.diagnostic().hover_thrust, hover); EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[2], nu);
		sameVec(p.velocityIntegral(), integral); EXPECT_EQ(p.regularizedIstaDiagnostic().commit_axes, 0);
	}
}

TEST(RegularizedIstaPosition, RI04HteStateLimitUsesAppliedOutputAndBoundedStateWithoutReevaluating)
{
	for (const float direction : {1.f, -1.f}) {
		PositionControl p; setup(p, 4, false); auto f = frame(); auto sp = target();
		reachStateLimit(p, f, sp, direction);
		const auto old = p.regularizedIstaDiagnostic();
		const auto diag = p.diagnostic();
		const auto correction = p.velocityCorrection(), integral = p.velocityIntegral();
		const uint32_t sequence = p.velocityDecimation().sequence;
		EXPECT_TRUE(old.cache_valid); // Old code continues below to reproduce the actual HTE fault.
		EXPECT_NE(old.nu_candidate[2], old.nu_applied[2]);
		EXPECT_FLOAT_EQ(old.a_applied[2], old.a_ideal[2]);
		EXPECT_LT(std::fabs(diag.nu_before[2]), 4.f);
		// Re-evaluating from clipped nu would lose this first-clipping history.
		const double wrong_recomputed = static_cast<double>(old.nu_applied[2]) - inverse(diag.s[2], old.h, 2., 1., .02);
		EXPECT_GT(std::fabs(wrong_recomputed - static_cast<double>(correction(2))), .001);
		vehicle_local_position_setpoint_s published{}; p.getLocalPositionSetpoint(published);
		// Freeze the actual post-limitTilt geometry. Reconstructing it from
		// acceleration omits limitTilt's float acos/sin rounding at small tilt.
		const Vector3f body = -Vector3f(published.thrust).normalized();
		ASSERT_LT(body(2), 1.f); // Nonzero XY demand/tilt and FF.
		const float hover_new = direction > 0.f ? .7190654277801514f : .4f;
		const float delta = (diag.hover_thrust / hover_new - 1.f)
			* (correction(2) + sp.acceleration[2] - CONSTANTS_ONE_G);
		p.updateHoverThrust(hover_new);
		EXPECT_EQ(p.velocityDecimation().sequence, sequence);
		sameVec(p.velocityIntegral(), integral);
		EXPECT_FLOAT_EQ(p.regularizedIstaDiagnostic().p[2], old.p[2]);
		EXPECT_FLOAT_EQ(p.regularizedIstaDiagnostic().a_ideal[2], old.a_ideal[2]);
		EXPECT_FLOAT_EQ(p.regularizedIstaDiagnostic().nu_candidate[2], old.nu_candidate[2]);
		EXPECT_EQ(p.regularizedIstaDiagnostic().strict_axes, 0);
		EXPECT_FLOAT_EQ(p.velocityCorrection()(2), correction(2) + delta);
		EXPECT_FLOAT_EQ(p.velocityCorrection()(0), correction(0));
		EXPECT_FLOAT_EQ(p.velocityCorrection()(1), correction(1));
		const Vector3f frozen_map = body * ((p.velocityCorrection()(2) + sp.acceleration[2] - CONSTANTS_ONE_G)
			* hover_new / (CONSTANTS_ONE_G * body(2)));
		for (int i = 0; i < 3; ++i) { EXPECT_NEAR(frozen_map(i), published.thrust[i], 2e-7f); }
		vehicle_local_position_setpoint_s unchanged{}; p.getLocalPositionSetpoint(unchanged);
		for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(unchanged.thrust[i], published.thrust[i]); }
		// Different next s/h/FF: verify the new update, not a false unchanged-output guarantee.
		f.sample += 12000; sp.acceleration[2] = -.04f;
		ASSERT_TRUE(step(p, f, sp, .012f, Vector3f(.01f, -.01f, direction * .02f)));
		EXPECT_FLOAT_EQ(p.diagnostic().nu_before[2], old.nu_applied[2] + delta);
		EXPECT_FLOAT_EQ(p.diagnostic().hover_thrust, hover_new);
		EXPECT_FLOAT_EQ(p.diagnostic().z_hte_shift, delta);
		EXPECT_EQ(p.velocityDecimation().sequence, sequence + 1);
		const double next = static_cast<double>(old.nu_applied[2] + delta)
			- inverse(p.diagnostic().s[2], p.regularizedIstaDiagnostic().h, 2., 1., .02);
		EXPECT_NEAR(p.regularizedIstaDiagnostic().a_ideal[2], next, 8e-7);
		EXPECT_FLOAT_EQ(p.diagnostic().a_req[2], p.velocityCorrection()(2) + sp.acceleration[2]);
	}
}

TEST(RegularizedIstaPosition, RI04HteStateLimitRepeatedRebasesComposeWithoutIntegration)
{
	PositionControl p; setup(p, 4, false); auto f = frame(); auto sp = target();
	reachStateLimit(p, f, sp, 1.f);
	const auto initial = p.velocityCorrection(); const float nu = p.diagnostic().nu_applied[2];
	const auto old = p.regularizedIstaDiagnostic(); const auto integral = p.velocityIntegral();
	const uint32_t sequence = p.velocityDecimation().sequence;
	float hover = .5f, total = 0.f;
	for (const float next : {.6f, .7f, .65f}) {
		const float delta = (hover / next - 1.f) * (p.velocityCorrection()(2) + sp.acceleration[2] - CONSTANTS_ONE_G);
		p.updateHoverThrust(next); total += delta;
		EXPECT_NEAR((p.velocityCorrection()(2) + sp.acceleration[2] - CONSTANTS_ONE_G) * next,
			(initial(2) + sp.acceleration[2] - CONSTANTS_ONE_G) * .5f, 2e-6f);
		EXPECT_EQ(p.velocityDecimation().sequence, sequence);
		EXPECT_FLOAT_EQ(p.regularizedIstaDiagnostic().nu_candidate[2], old.nu_candidate[2]);
		sameVec(p.velocityIntegral(), integral); hover = next;
	}
	f.sample += 8000; ASSERT_TRUE(step(p, f, sp));
	EXPECT_NEAR(p.diagnostic().nu_before[2], nu + total, 1e-6f);
	EXPECT_FLOAT_EQ(p.diagnostic().z_hte_shift, total);
	EXPECT_FLOAT_EQ(p.diagnostic().hover_thrust, hover);
}

TEST(RegularizedIstaPosition, RI04HteStateLimitRejectsOutwardStateAndCorrectionOverflowAtomically)
{
	for (const int kind : {0, 1, 2, 3, 4}) {
		PositionControl p; setup(p, 4, false); auto f = frame(); auto sp = target();
		reachStateLimit(p, f, sp, kind == 1 ? -1.f : 1.f);
		ASSERT_EQ(p.diagnostic().sta_flags, Guard::StateLimit);
		const auto old = p.regularizedIstaDiagnostic(); const auto correction = p.velocityCorrection();
		const auto integral = p.velocityIntegral(); const uint32_t sequence = p.velocityDecimation().sequence;
		// 0/1: outward nu, 2: both nu/correction overflow, 3/4: invalid hover.
		const float next = kind == 0 ? .49f : kind == 1 ? .51f : kind == 2 ? .1f : kind == 3 ? NAN : .91f;
		p.updateHoverThrust(next);
		sameVec(p.velocityCorrection(), correction); sameVec(p.velocityIntegral(), integral);
		EXPECT_EQ(p.velocityDecimation().sequence, sequence);
		f.sample += 8000; EXPECT_FALSE(step(p, f, sp));
		EXPECT_FALSE(p.velocityOutputPublishable()); // Publication eligibility is refreshed by update().
		EXPECT_FLOAT_EQ(p.diagnostic().hover_thrust, .5f);
		EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[2], old.nu_applied[2]);
		EXPECT_EQ(p.regularizedIstaDiagnostic().commit_axes, 0);
		EXPECT_NE(p.diagnostic().sta_fault & Guard::Numerical, 0);
	}
}

TEST(RegularizedIstaPosition, RI04HteStateLimitCannotReuseStaleOrResetCache)
{
	for (const int kind : {0, 1, 2}) {
		PositionControl p; setup(p, 4, false); auto f = frame(); auto sp = target();
		reachStateLimit(p, f, sp, 1.f);
		if (kind < 2) { RegularizedIstaVelocityTestAccess::staleHteCache(p, kind == 1); }
		else { p.resetIntegral(); }
		const auto correction = p.velocityCorrection();
		p.updateHoverThrust(.7190654277801514f);
		sameVec(p.velocityCorrection(), correction);
		f.sample += 12000; EXPECT_FALSE(step(p, f, sp));
		EXPECT_FALSE(p.velocityOutputPublishable());
		EXPECT_FLOAT_EQ(p.diagnostic().hover_thrust, .5f);
		EXPECT_FALSE(p.regularizedIstaDiagnostic().cache_valid);
	}
}

TEST(RegularizedIstaPosition, RI04HteStateLimitPlusOutputOrDownstreamProtectionStillRefuses)
{
	for (const int kind : {0, 1, 2}) {
		PositionControl p; setup(p, 4, false); auto f = frame(); auto sp = target();
		reachStateLimit(p, f, sp, 1.f);
		if (kind == 2) {
			// Return just inside the bound so the next clipped increment is outward.
			f.sample += 8000; ASSERT_TRUE(step(p, f, sp, .008f, Vector3f(.01f, -.01f, -.01f)));
			ASSERT_GT(p.diagnostic().nu_applied[2], -4.f);
		}
		if (kind > 0) { sp.acceleration[2] = -20.f; }
		f.sample += 12000;
		ASSERT_TRUE(step(p, f, sp, .012f, Vector3f(.01f, -.01f, kind == 0 ? 2.f : .1f)));
		EXPECT_NE(p.diagnostic().sta_flags & Guard::StateLimit, 0);
		if (kind == 0) { EXPECT_NE(p.diagnostic().sta_flags & Guard::CorrectionLimit, 0); }
		if (kind > 0) { EXPECT_NE(p.diagnostic().constraint_bits, 0); }
		if (kind == 2) { EXPECT_NE(p.diagnostic().sta_flags & Guard::OutwardFreeze, 0); }
		EXPECT_FALSE(p.regularizedIstaDiagnostic().cache_valid);
		const auto correction = p.velocityCorrection(); const float nu = p.diagnostic().nu_applied[2];
		p.updateHoverThrust(.7190654277801514f);
		sameVec(p.velocityCorrection(), correction);
		f.sample += 8000; EXPECT_FALSE(step(p, f, target()));
		EXPECT_FALSE(p.velocityOutputPublishable());
		EXPECT_FLOAT_EQ(p.diagnostic().hover_thrust, .5f); EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[2], nu);
	}
}

TEST(RegularizedIstaPosition, RI04HteRecordedLastBoundaryNoLongerLatchesOnFirstValidEstimate)
{
	namespace recorded = ri04_hte_fixture;
	PositionControl p; setup(p, 4, false); auto f = frame(); auto sp = target();
	reachStateLimit(p, f, sp, 1.f);
	sp.acceleration[2] = recorded::LastFf;
	f.sample += 8000;
	ASSERT_TRUE(step(p, f, sp, recorded::LastStep, Vector3f(.01f, -.01f, recorded::LastError)));
	ASSERT_FLOAT_EQ(p.diagnostic().nu_applied[2], recorded::LastNu);
	ASSERT_FLOAT_EQ(p.regularizedIstaDiagnostic().h, recorded::LastStep);
	ASSERT_FLOAT_EQ(p.regularizedIstaDiagnostic().nu_candidate[2], recorded::LastNuCandidate);
	ASSERT_FLOAT_EQ(p.velocityCorrection()(2), recorded::LastCorrection);
	ASSERT_EQ(p.diagnostic().sta_flags, Guard::StateLimit);
	const double desired_correction = static_cast<double>(CONSTANTS_ONE_G) - static_cast<double>(recorded::LastFf)
		+ (static_cast<double>(recorded::LastCorrection) + static_cast<double>(recorded::LastFf) - static_cast<double>(CONSTANTS_ONE_G))
		* static_cast<double>(recorded::OldHover) / static_cast<double>(recorded::NewHover);
	const double expected_nu = static_cast<double>(recorded::LastNu) + desired_correction - static_cast<double>(recorded::LastCorrection);
	p.updateHoverThrust(recorded::NewHover);
	EXPECT_TRUE(p.velocityOutputPublishable());
	EXPECT_NEAR(p.velocityCorrection()(2), desired_correction, 8e-7);
	f.sample += 12000;
	ASSERT_TRUE(step(p, f, sp, .012f, Vector3f(.01f, -.01f, recorded::LastError)));
	EXPECT_NEAR(p.diagnostic().nu_before[2], expected_nu, 8e-7);
	EXPECT_FLOAT_EQ(p.diagnostic().hover_thrust, recorded::NewHover);
	EXPECT_FALSE(p.diagnostic().fault); EXPECT_EQ(p.regularizedIstaDiagnostic().commit_axes, 4);
	// This reconstructs the last valid boundary, not a new accepted flight or
	// the complete recorded plant trajectory after this counterfactual change.
}

TEST(RegularizedIstaPosition, RI04HteCorrectionOverflowRefusesEvenWhenShiftedNuWouldBeFeasible)
{
	PositionControl p; setup(p, 4, false); auto f = frame(); auto sp = target(); engage(p, f, sp);
	sp.vz = 0.f; f.sample += 8000;
	ASSERT_TRUE(step(p, f, sp, .008f, Vector3f(.01f, -.01f, 8.f)));
	ASSERT_TRUE(p.regularizedIstaDiagnostic().cache_valid);
	ASSERT_EQ(p.diagnostic().constraint_bits, 0);
	const float correction = p.velocityCorrection()(2), nu = p.diagnostic().nu_applied[2];
	const float delta = (.5f / .45f - 1.f) * (correction + sp.acceleration[2] - CONSTANTS_ONE_G);
	ASSERT_LT(std::fabs(nu + delta), 4.f);
	ASSERT_GT(std::fabs(correction + delta), 6.f);
	p.updateHoverThrust(.45f);
	EXPECT_FLOAT_EQ(p.velocityCorrection()(2), correction);
	f.sample += 12000; EXPECT_FALSE(step(p, f, sp));
	EXPECT_FALSE(p.velocityOutputPublishable());
	EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[2], nu);
	EXPECT_FLOAT_EQ(p.diagnostic().hover_thrust, .5f);
}
