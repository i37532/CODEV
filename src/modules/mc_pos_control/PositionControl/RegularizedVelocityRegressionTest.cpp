// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>
#include "PositionControl.hpp"
#include "R01PositionControl.hpp"

#include <cmath>
#include <cstring>
#include <tuple>

namespace
{
using matrix::Vector3f;

template<typename Config> Config gains(int axes)
{
	Config c{};
	c.axes = static_cast<uint8_t>(axes ? axes : 1);
	for (int i = 0; i < 3; ++i) {
		c.gains[i] = {i == 2 ? 2.f : .5f, i == 2 ? 1.f : .1f};
		c.nu_limit[i] = i == 2 ? 4.f : .4f;
		c.acceleration_limit[i] = i == 2 ? 6.f : .8f;
	}

	return c;
}

template<typename Controller> void setup(Controller &p)
{
	p.setPositionGains(Vector3f(.95f, .95f, 1.f));
	p.setVelocityGains(Vector3f(2.16f, 2.16f, 4.f), Vector3f(.48f, .48f, 2.f), Vector3f(.24f, .24f, 0.f));
	p.setVelocityLimits(12.f, 3.f, .55f);
	p.setThrustLimits(.12f, 1.f);
	p.setTiltLimit(.7f);
	p.setHoverThrust(.5f);
}

void sameFloat(float actual, float expected)
{
	// NaN is an explicit inactive component, not a value to interpolate. Its
	// payload is unspecified; every finite value (including signed zero) is exact.
	if (std::isnan(actual) && std::isnan(expected)) { return; }
	uint32_t a{}, b{};
	std::memcpy(&a, &actual, sizeof(a));
	std::memcpy(&b, &expected, sizeof(b));
	EXPECT_EQ(a, b) << actual << " vs " << expected;
}

void sameState(const PositionControl &p, const R01PositionControl &q)
{
	const auto &a = p.diagnostic();
	const auto &b = q.diagnostic();
	const float *left[] = {a.p_sp, a.v_ff, a.v_sp, a.v, a.v_dot, a.a_ff, a.s, a.nu_before,
			      a.nu_ideal, a.nu_applied, a.a_sta, a.a_req, a.a_proxy, a.thrust};
	const float *right[] = {b.p_sp, b.v_ff, b.v_sp, b.v, b.v_dot, b.a_ff, b.s, b.nu_before,
			       b.nu_ideal, b.nu_applied, b.a_sta, b.a_req, b.a_proxy, b.thrust};

	for (size_t field = 0; field < sizeof(left) / sizeof(left[0]); ++field) {
		for (int axis = 0; axis < 3; ++axis) { sameFloat(left[field][axis], right[field][axis]); }
	}

	for (int axis = 0; axis < 3; ++axis) {
		sameFloat(p.velocityIntegral()(axis), q.velocityIntegral()(axis));
		sameFloat(p.velocityCorrection()(axis), q.velocityCorrection()(axis));
	}

	sameFloat(a.z_hte_shift, b.z_hte_shift);
	sameFloat(a.raw_dt, b.raw_dt);
	sameFloat(a.hover_thrust, b.hover_thrust);
	EXPECT_EQ(a.config_generation, b.config_generation);
	EXPECT_EQ(a.config_pending, b.config_pending);
	EXPECT_EQ(a.pid_axes, b.pid_axes);
	EXPECT_EQ(a.active_axes, b.active_axes);
	EXPECT_EQ(a.committed_axes, b.committed_axes);
	EXPECT_EQ(a.z_phase, b.z_phase);
	EXPECT_EQ(a.sta_fault, b.sta_fault);
	EXPECT_EQ(a.sta_flags, b.sta_flags);
	EXPECT_EQ(a.constraint_bits, b.constraint_bits);
	EXPECT_EQ(a.valid, b.valid);
	EXPECT_EQ(a.fault, b.fault);
	EXPECT_EQ(p.velocityOutputPublishable(), q.velocityOutputPublishable());
	EXPECT_EQ(p.velocitySelection().requestedMode(), q.velocitySelection().requestedMode());
	EXPECT_EQ(p.velocitySelection().effectiveMode(), q.velocitySelection().effectiveMode());
	EXPECT_EQ(p.velocitySelection().effectiveAxes(), q.velocitySelection().effectiveAxes());
	EXPECT_EQ(p.velocitySelection().pending(), q.velocitySelection().pending());
	EXPECT_EQ(p.velocitySelection().reject(), q.velocitySelection().reject());
	vehicle_attitude_setpoint_s aa{}, bb{};
	p.getAttitudeSetpoint(aa); q.getAttitudeSetpoint(bb);
	for (int i = 0; i < 4; ++i) { sameFloat(aa.q_d[i], bb.q_d[i]); }
}

class RegularizedLegacySequence : public ::testing::TestWithParam<std::tuple<int, int>> {};
INSTANTIATE_TEST_SUITE_P(AllLegacyMasks, RegularizedLegacySequence,
	::testing::Combine(::testing::Range(0, 8), ::testing::Values(0, 1)));
}

TEST_P(RegularizedLegacySequence, Two2048SampleSequencesPreserveR01OutputAndStateExactly)
{
	const int axes = std::get<0>(GetParam());
	const int sequence = std::get<1>(GetParam());
	PositionControl p;
	R01PositionControl q;
	setup(p); setup(q);
	auto c = gains<StaVelocityProtection::Config>(axes);
	auto old_c = gains<R01StaVelocityProtection::Config>(axes);
	p.configureVelocityEsta(c, false); q.configureVelocityEsta(old_c, false);
	p.configureVelocityControl(axes ? 1 : 0, axes, false);
	q.configureVelocityControl(axes ? 1 : 0, axes, false);
	ASSERT_EQ(p.velocitySelection().reject(), 0);
	ASSERT_EQ(q.velocitySelection().reject(), 0);
	uint64_t sample = 1000000;
	unsigned successful = 0, repeat_calls = 0, constrained = 0;

	for (int k = 0; k < 2048; ++k) {
		SCOPED_TRACE(k);
		const float h = sequence ? (k % 2 ? .008f : .012f) : .01f;
		sample += sequence ? (k % 2 ? 8000 : 12000) : 10000;
		StaVelocityProtection::Frame f{};
		f.sample = sample;
		f.armed = k % 256 != 0;
		f.enabled = k % 461 != 0;
		f.flying = k > 8 && k % 503 > 2;
		f.landed = k % 503 == 0;
		f.contact = k % 503 < 2;
		f.inner_valid = k != 1830;
		f.unmatched_reset_axes = k == 1800 ? static_cast<uint8_t>(axes) : 0;
		R01StaVelocityProtection::Frame old{};
		old.sample = f.sample; old.armed = f.armed; old.enabled = f.enabled;
		old.flying = f.flying; old.landed = f.landed; old.contact = f.contact;
		old.inner_valid = f.inner_valid; old.unmatched_reset_axes = f.unmatched_reset_axes;

		// Equal requests, an armed changed request and its cancellation exercise
		// the original configuration timing without ever selecting the new mode.
		if (k == 100 || k == 101 || !f.armed) {
			c = gains<StaVelocityProtection::Config>(axes);
			old_c = gains<R01StaVelocityProtection::Config>(axes);
			if (k == 100) { c.gains[0].lambda1 += .1f; old_c.gains[0].lambda1 += .1f; }
			p.configureVelocityEsta(c, f.armed); q.configureVelocityEsta(old_c, f.armed);
			p.configureVelocityControl(axes ? 1 : 0, axes, f.armed);
			q.configureVelocityControl(axes ? 1 : 0, axes, f.armed);
		}

		if (k % 257 == 0) {
			const float hover = k % 514 ? .505f : .5f;
			p.updateHoverThrust(hover); q.updateHoverThrust(hover);
		}

		if (k == 700 || k == 900) {
			const float gain = k == 700 ? 2.2f : 2.16f;
			p.setVelocityGains(Vector3f(gain, gain, 4.f), Vector3f(.48f, .48f, 2.f), Vector3f(.24f, .24f, 0.f));
			q.setVelocityGains(Vector3f(gain, gain, 4.f), Vector3f(.48f, .48f, 2.f), Vector3f(.24f, .24f, 0.f));
		}

		const float tilt = k > 250 && k < 300 ? .001f : .7f;
		p.setTiltLimit(tilt); q.setTiltLimit(tilt);
		p.setVelocityFrame(f); q.setVelocityFrame(old);
		const float t = static_cast<float>(k) * .01f;
		Vector3f velocity(.003f * sinf(t), -.002f * cosf(t), .001f);
		if (sequence && k == 650) { velocity(2) = NAN; }
		const Vector3f derivative(.004f, .003f, .002f);
		p.setState({Vector3f(), velocity, derivative, 0.f});
		q.setState({Vector3f(), velocity, derivative, 0.f});
		vehicle_local_position_setpoint_s sp{};
		sp.x = sp.y = sp.z = NAN;
		sp.vx = .01f * sinf(t); sp.vy = .01f * cosf(t); sp.vz = .005f * sinf(t);
		sp.acceleration[0] = .02f * cosf(t); sp.acceleration[1] = -.02f * sinf(t); sp.acceleration[2] = .01f;
		if (sequence && k % 307 == 0) { sp.vx = sp.vy = NAN; }
		if (k > 850 && k < 865) { sp.acceleration[2] = -25.f; }
		if (k > 1200 && k < 1220) { sp.x = .005f; sp.y = -.005f; sp.z = -.005f; }
		p.setInputSetpoint(sp); q.setInputSetpoint(sp);
		const bool a = p.update(h), b = q.update(h);
		ASSERT_EQ(a, b);
		successful += static_cast<unsigned>(a);
		constrained += static_cast<unsigned>(p.diagnostic().constraint_bits != 0);
		sameState(p, q);

		if (k % 256 >= 254) {
			// Same sample, changed failsafe-like target: never hide a second
			// invocation by skipping comparison or advancing the sensor clock.
			sp.vx = sp.vy = sp.vz = 0.f;
			p.setInputSetpoint(sp); q.setInputSetpoint(sp);
			ASSERT_EQ(p.update(h), q.update(h));
			sameState(p, q);
			++repeat_calls;
		}
	}

	EXPECT_GT(successful, 500u);
	EXPECT_GT(constrained, 0u);
	EXPECT_EQ(repeat_calls, 16u);
}
