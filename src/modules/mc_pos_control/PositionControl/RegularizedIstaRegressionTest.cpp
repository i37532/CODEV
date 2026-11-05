// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>
#include "PositionControl.hpp"
#include "RI01PositionControl.hpp"

#include <cmath>
#include <cstring>
#include <tuple>

namespace
{
using matrix::Vector3f;

template<typename Config> Config gains(int mode, int axes)
{
	Config c{};
	c.axes = static_cast<uint8_t>(axes ? axes : 1);
	c.variant = static_cast<uint8_t>(mode == 3 ? 3 : 1);
	c.epsilon = {{.01f, .01f, .02f}};

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
	p.configureVelocityDivisor(1, false);
}

void sameFloat(float actual, float expected)
{
	// NaN denotes disabled components, not a numerical result. Compare that
	// validity meaning; every other value including signed zero is bitwise.
	if (std::isnan(actual) && std::isnan(expected)) { return; }

	uint32_t a{}, b{};
	std::memcpy(&a, &actual, sizeof(a));
	std::memcpy(&b, &expected, sizeof(b));
	EXPECT_EQ(a, b) << actual << " vs " << expected;
}

template<typename ConfigA, typename ConfigB> void sameConfig(const ConfigA &a, const ConfigB &b)
{
	EXPECT_EQ(a.axes, b.axes);
	EXPECT_EQ(a.variant, b.variant);

	for (int axis = 0; axis < 3; ++axis) {
		sameFloat(a.gains[axis].lambda1, b.gains[axis].lambda1);
		sameFloat(a.gains[axis].lambda2, b.gains[axis].lambda2);
		sameFloat(a.epsilon[axis], b.epsilon[axis]);
		sameFloat(a.nu_limit[axis], b.nu_limit[axis]);
		sameFloat(a.acceleration_limit[axis], b.acceleration_limit[axis]);
	}
}

void sameState(const PositionControl &p, const RI01PositionControl &q)
{
	const auto &a = p.diagnostic();
	const auto &b = q.diagnostic();
	const float *left[] = {a.p_sp, a.v_ff, a.v_sp, a.v, a.v_dot, a.a_ff, a.s, a.nu_before,
			       a.nu_ideal, a.nu_applied, a.a_sta, a.a_req, a.a_proxy, a.thrust
			      };
	const float *right[] = {b.p_sp, b.v_ff, b.v_sp, b.v, b.v_dot, b.a_ff, b.s, b.nu_before,
				b.nu_ideal, b.nu_applied, b.a_sta, b.a_req, b.a_proxy, b.thrust
			       };

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
	sameFloat(a.tilt_limit, b.tilt_limit);
	sameFloat(a.thrust_min, b.thrust_min);
	sameFloat(a.thrust_max, b.thrust_max);
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
	EXPECT_EQ(p.inputValidity(), q.inputValidity());
	EXPECT_EQ(p.failureReason(), q.failureReason());
	EXPECT_EQ(p.velocityOutputPublishable(), q.velocityOutputPublishable());
	EXPECT_EQ(p.velocityEstaPending(), q.velocityEstaPending());
	EXPECT_EQ(p.velocityEstaRejected(), q.velocityEstaRejected());
	EXPECT_EQ(p.velocityEstaGeneration(), q.velocityEstaGeneration());
	sameConfig(p.requestedVelocityEsta(), q.requestedVelocityEsta());
	sameConfig(p.effectiveVelocityEsta(), q.effectiveVelocityEsta());
	EXPECT_EQ(p.velocitySelection().requestedMode(), q.velocitySelection().requestedMode());
	EXPECT_EQ(p.velocitySelection().requestedAxes(), q.velocitySelection().requestedAxes());
	EXPECT_EQ(p.velocitySelection().effectiveMode(), q.velocitySelection().effectiveMode());
	EXPECT_EQ(p.velocitySelection().effectiveAxes(), q.velocitySelection().effectiveAxes());
	EXPECT_EQ(p.velocitySelection().pending(), q.velocitySelection().pending());
	EXPECT_EQ(p.velocitySelection().reject(), q.velocitySelection().reject());
	const auto &d = p.velocityDecimation();
	const auto &e = q.velocityDecimation();
	EXPECT_EQ(d.sequence, e.sequence);
	EXPECT_EQ(d.updated, e.updated);
	EXPECT_EQ(d.held, e.held);
	EXPECT_EQ(d.divisor, e.divisor);
	EXPECT_EQ(d.fault, e.fault);
	sameFloat(d.h, e.h);
	sameFloat(d.raw_dt, e.raw_dt);
	vehicle_attitude_setpoint_s aa{}, bb{};
	p.getAttitudeSetpoint(aa); q.getAttitudeSetpoint(bb);

	for (int i = 0; i < 4; ++i) { sameFloat(aa.q_d[i], bb.q_d[i]); }

	for (int i = 0; i < 3; ++i) { sameFloat(aa.thrust_body[i], bb.thrust_body[i]); }

	sameFloat(aa.yaw_sp_move_rate, bb.yaw_sp_move_rate);
	vehicle_local_position_setpoint_s sa{}, sb{};
	p.getLocalPositionSetpoint(sa); q.getLocalPositionSetpoint(sb);
	sameFloat(sa.x, sb.x); sameFloat(sa.y, sb.y); sameFloat(sa.z, sb.z);
	sameFloat(sa.vx, sb.vx); sameFloat(sa.vy, sb.vy); sameFloat(sa.vz, sb.vz);
	sameFloat(sa.yaw, sb.yaw); sameFloat(sa.yawspeed, sb.yawspeed);

	for (int i = 0; i < 3; ++i) {
		sameFloat(sa.acceleration[i], sb.acceleration[i]);
		sameFloat(sa.thrust[i], sb.thrust[i]);
	}
}

using Configuration = std::tuple<int, int>;
using Case = std::tuple<Configuration, int>;
class RegularizedIstaLegacySequence : public ::testing::TestWithParam<Case> {};
INSTANTIATE_TEST_SUITE_P(AllFrozenModesAndMasks, RegularizedIstaLegacySequence,
			 ::testing::Combine(::testing::Values(Configuration(0, 0),
					 Configuration(3, 1), Configuration(3, 3), Configuration(3, 4), Configuration(3, 7),
					 Configuration(1, 1), Configuration(1, 2), Configuration(1, 3), Configuration(1, 4),
					 Configuration(1, 5), Configuration(1, 6), Configuration(1, 7)), ::testing::Values(0, 1)));
}

TEST_P(RegularizedIstaLegacySequence, Two2048SamplesPreserveFrozenRI01OutputAndStateBitwise)
{
	const int mode = std::get<0>(std::get<0>(GetParam()));
	const int axes = std::get<1>(std::get<0>(GetParam()));
	const int sequence = std::get<1>(GetParam());
	const int changed_axis = !axes || (axes & 1) ? 0 : ((axes & 2) ? 1 : 2);
	PositionControl p;
	RI01PositionControl q;
	setup(p); setup(q);
	auto c = gains<StaVelocityProtection::Config>(mode, axes);
	auto old_c = gains<RI01StaVelocityProtection::Config>(mode, axes);
	p.configureVelocityEsta(c, false); q.configureVelocityEsta(old_c, false);
	p.configureVelocityControl(mode, axes, false); q.configureVelocityControl(mode, axes, false);
	ASSERT_EQ(p.velocitySelection().reject(), 0);
	ASSERT_EQ(q.velocitySelection().reject(), 0);
	uint64_t sample = 1000000;
	unsigned successful = 0, repeat_calls = 0, constrained = 0, committed = 0, handovers = 0;
	unsigned ground = 0, hte_shifts = 0, pending = 0, position_ff = 0, pure_acceleration = 0;

	for (int k = 0; k < 2048; ++k) {
		SCOPED_TRACE(k);
		const int phase = k % 256;
		const float h = sequence ? (k % 2 ? .008f : .012f) : .01f;
		sample += sequence ? (k % 2 ? 8000 : 12000) : 10000;
		StaVelocityProtection::Frame f{};
		f.sample = sample;
		f.armed = phase > 0 && phase < 241;
		f.enabled = phase != 222;
		f.flying = phase >= 9 && phase < 241 && phase != 232;
		f.landed = phase <= 3 || phase >= 241;
		f.contact = phase <= 4 || phase == 231 || phase == 232 || phase >= 241;
		f.inner_valid = !(sequence && phase == 210);
		f.unmatched_reset_axes = sequence && phase == 211 ? static_cast<uint8_t>(axes) : 0;
		RI01StaVelocityProtection::Frame old{};
		old.sample = f.sample; old.armed = f.armed; old.enabled = f.enabled;
		old.flying = f.flying; old.landed = f.landed; old.contact = f.contact;
		old.inner_valid = f.inner_valid; old.unmatched_reset_axes = f.unmatched_reset_axes;

		if (phase == 0 || phase == 30 || phase == 31 || phase == 242) {
			c = gains<StaVelocityProtection::Config>(mode, axes);
			old_c = gains<RI01StaVelocityProtection::Config>(mode, axes);

			if (phase == 30 || phase == 242) {
				c.gains[changed_axis].lambda1 += .1f; old_c.gains[changed_axis].lambda1 += .1f;
				c.epsilon[changed_axis] *= 2.f; old_c.epsilon[changed_axis] *= 2.f;
			}

			p.configureVelocityEsta(c, f.armed); q.configureVelocityEsta(old_c, f.armed);
			p.configureVelocityControl(mode, axes, f.armed); q.configureVelocityControl(mode, axes, f.armed);
			pending += static_cast<unsigned>(p.velocityEstaPending());
		}

		if (phase == 64 || phase == 68) {
			const float hover = phase == 64 ? .505f : .5f;
			p.updateHoverThrust(hover); q.updateHoverThrust(hover);
		}

		if (phase == 50 || phase == 55) {
			const float gain = phase == 50 ? 2.2f : 2.16f;
			p.setVelocityGains(Vector3f(gain, gain, 4.f), Vector3f(.48f, .48f, 2.f), Vector3f(.24f, .24f, 0.f));
			q.setVelocityGains(Vector3f(gain, gain, 4.f), Vector3f(.48f, .48f, 2.f), Vector3f(.24f, .24f, 0.f));
		}

		if (phase == 40) { p.resetIntegral(); q.resetIntegral(); }

		const float tilt = phase >= 70 && phase < 78 ? .001f : .7f;
		p.setTiltLimit(tilt); q.setTiltLimit(tilt);
		// Module-equivalent ramp input; the actual Takeoff class has its own
		// separately executed tests. Keep ground/ramp PID semantics unchanged.
		const float up = phase < 9 ? .1f + .02f * static_cast<float>(phase) : 3.f;
		p.setVelocityLimits(12.f, up, .55f); q.setVelocityLimits(12.f, up, .55f);
		p.setVelocityFrame(f); q.setVelocityFrame(old);
		const float t = static_cast<float>(k) * .01f;
		Vector3f velocity(.003f * sinf(t), -.002f * cosf(t), .001f);
		const Vector3f derivative(.004f, .003f, .002f);
		Vector3f position(0.f, 0.f, 0.f);
		vehicle_local_position_setpoint_s sp{};
		sp.x = sp.y = sp.z = NAN;
		sp.vx = .01f * sinf(t); sp.vy = .01f * cosf(t); sp.vz = .005f * sinf(t);
		sp.acceleration[0] = .02f * cosf(t); sp.acceleration[1] = -.02f * sinf(t); sp.acceleration[2] = .01f;
		sp.yaw = .1f * sinf(t); sp.yawspeed = .03f * cosf(t);

		if (phase >= 1 && phase < 9) { sp.vz = -.3f; }

		if (phase >= 79 && phase < 82) { sp.acceleration[2] = -25.f; }

		if (phase >= 90 && phase < 95) {
			sp.vx = sp.vy = sp.vz = NAN;
			++pure_acceleration;
		}

		if (phase >= 110 && phase < 125) {
			position = Vector3f(10.f, -12.f, -2.5f);
			sp.x = 10.005f; sp.y = -12.005f; sp.z = -2.505f;
			++position_ff;
		}

		if (sequence && phase == 180) { velocity(2) = NAN; }

		if (sequence && phase == 190) { sp.vx = NAN; }

		p.setState({position, velocity, derivative, .03f});
		q.setState({position, velocity, derivative, .03f});
		p.setInputSetpoint(sp); q.setInputSetpoint(sp);
		const bool a = p.update(h), b = q.update(h);
		ASSERT_EQ(a, b);
		successful += static_cast<unsigned>(a);
		constrained += static_cast<unsigned>(p.diagnostic().constraint_bits != 0);
		committed += static_cast<unsigned>(p.diagnostic().committed_axes != 0);
		handovers += static_cast<unsigned>(p.diagnostic().z_phase == 2);
		ground += static_cast<unsigned>(p.diagnostic().z_phase == 1);
		hte_shifts += static_cast<unsigned>(fabsf(p.diagnostic().z_hte_shift) > 0.f);
		sameState(p, q);

		if (phase == 238 || phase == 239) {
			// Do not advance the sensor clock or re-prime between a first result
			// and the same-sample failsafe-like target. Compare failures as well.
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
	EXPECT_EQ(position_ff, 120u);
	EXPECT_EQ(pure_acceleration, 40u);

	if (mode) {
		EXPECT_GT(committed, 100u);
		EXPECT_GE(pending, 8u);
	}

	if (mode && (axes & 4)) {
		EXPECT_GT(handovers, 0u);
		EXPECT_GT(ground, 0u);
		EXPECT_GT(hte_shifts, 0u);
	}

	RecordProperty("mode", mode);
	RecordProperty("axes", axes);
	RecordProperty("sequence", sequence);
	RecordProperty("compared_samples", 2048);
	RecordProperty("same_sample_recomputations", static_cast<int>(repeat_calls));
	RecordProperty("successful_updates", static_cast<int>(successful));
	RecordProperty("constrained_updates", static_cast<int>(constrained));
	RecordProperty("state_commits", static_cast<int>(committed));
	RecordProperty("z_seed_handovers", static_cast<int>(handovers));
	RecordProperty("ground_ramp_updates", static_cast<int>(ground));
	RecordProperty("hte_shifts", static_cast<int>(hte_shifts));
	RecordProperty("armed_pending_requests", static_cast<int>(pending));
}
