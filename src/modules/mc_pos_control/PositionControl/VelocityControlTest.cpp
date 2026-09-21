// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>
#include <PositionControl.hpp>
#include <Takeoff.hpp>
#include "test/v00/V00PositionControl.hpp"
#include "test/v00/V00Takeoff.hpp"
#include <climits>
#include <cstring>

using matrix::Vector3f;

static void sameFloat(float a, float b)
{
	if (std::isnan(a) || std::isnan(b)) {
		EXPECT_TRUE(std::isnan(a) && std::isnan(b));
	} else {
		uint32_t x, y;
		memcpy(&x, &a, sizeof(x)); memcpy(&y, &b, sizeof(y));
		EXPECT_EQ(x, y) << a << " vs " << b;
	}
}

class VelocityControlTestAccess
{
public:
	static Vector3f integral(const PositionControl &c) { return c._vel_int; }
	static void compare(const PositionControl &a, const V00PositionControl &b)
	{
		const Vector3f av[] = {a._vel_int, a._pos, a._vel, a._vel_dot, a._pos_sp, a._vel_sp, a._acc_sp, a._thr_sp,
			a._gain_pos_p, a._gain_vel_p, a._gain_vel_i, a._gain_vel_d};
		const Vector3f bv[] = {b._vel_int, b._pos, b._vel, b._vel_dot, b._pos_sp, b._vel_sp, b._acc_sp, b._thr_sp,
			b._gain_pos_p, b._gain_vel_p, b._gain_vel_i, b._gain_vel_d};
		for (unsigned k = 0; k < sizeof(av) / sizeof(av[0]); ++k) {
			for (int i = 0; i < 3; ++i) { sameFloat(av[k](i), bv[k](i)); }
		}
		const float af[] = {a._yaw, a._yaw_sp, a._yawspeed_sp, a._hover_thrust, a._lim_vel_horizontal,
			a._lim_vel_up, a._lim_vel_down, a._lim_thr_min, a._lim_thr_max, a._lim_tilt};
		const float bf[] = {b._yaw, b._yaw_sp, b._yawspeed_sp, b._hover_thrust, b._lim_vel_horizontal,
			b._lim_vel_up, b._lim_vel_down, b._lim_thr_min, b._lim_thr_max, b._lim_tilt};
		for (unsigned k = 0; k < sizeof(af) / sizeof(af[0]); ++k) { sameFloat(af[k], bf[k]); }
	}
};

static vehicle_local_position_setpoint_s emptySp()
{
	vehicle_local_position_setpoint_s s{};
	s.x = s.y = s.z = s.vx = s.vy = s.vz = s.yaw = s.yawspeed = NAN;
	Vector3f(NAN, NAN, NAN).copyTo(s.acceleration);
	return s;
}

static void compareOutputs(const PositionControl &a, const V00PositionControl &b)
{
	VelocityControlTestAccess::compare(a, b);
	vehicle_local_position_setpoint_s p{}, q{};
	a.getLocalPositionSetpoint(p); b.getLocalPositionSetpoint(q);
	const float pf[] = {p.x,p.y,p.z,p.vx,p.vy,p.vz,p.yaw,p.yawspeed};
	const float qf[] = {q.x,q.y,q.z,q.vx,q.vy,q.vz,q.yaw,q.yawspeed};
	for (unsigned i = 0; i < 8; ++i) { sameFloat(pf[i], qf[i]); }
	for (int i = 0; i < 3; ++i) { sameFloat(p.acceleration[i], q.acceleration[i]); sameFloat(p.thrust[i], q.thrust[i]); }
	vehicle_attitude_setpoint_s r{}, t{};
	a.getAttitudeSetpoint(r); b.getAttitudeSetpoint(t);
	sameFloat(r.roll_body,t.roll_body); sameFloat(r.pitch_body,t.pitch_body); sameFloat(r.yaw_body,t.yaw_body);
	sameFloat(r.yaw_sp_move_rate,t.yaw_sp_move_rate);
	for (int i = 0; i < 4; ++i) { sameFloat(r.q_d[i],t.q_d[i]); }
	for (int i = 0; i < 3; ++i) { sameFloat(r.thrust_body[i],t.thrust_body[i]); }
}

template<typename C> static void gains(C &c, int variant, int k)
{
	const float scale = 1.f + .1f * variant + .05f * ((k / 128) % 3);
	c.setPositionGains(Vector3f(.95f,.95f,1.f) * scale);
	c.setVelocityGains(Vector3f(1.8f,1.8f,4.f) * scale, Vector3f(.4f,.4f,2.f), Vector3f(.2f,.2f,.03f));
}

static void sequence(int variant)
{
	PositionControl a;
	V00PositionControl b;
	Takeoff takeoff;
	V00Takeoff ref_takeoff;
	a.setHoverThrust(.5f); b.setHoverThrust(.5f);
	takeoff.setSpoolupTime(.02f); ref_takeoff.setSpoolupTime(.02f);
	takeoff.setTakeoffRampTime(.2f); ref_takeoff.setTakeoffRampTime(.2f);
	takeoff.generateInitialRampValue(4.f); ref_takeoff.generateInitialRampValue(4.f);
	uint64_t timestamp = 1000000;
	int retries=0, resets=0, hte=0, limited=0, accepted=0;
	for (int k = 0; k < 2048; ++k) {
		SCOPED_TRACE(::testing::Message() << "sequence=" << variant << " sample=" << k);
		const float dt = variant ? (k % 2 ? .012f : .008f) : .01f;
		timestamp += static_cast<uint64_t>(dt * 1e6f);
		const int phase = k % 256;
		const bool armed = phase >= 8 && phase < 248;
		const bool landed = phase < 48 || phase >= 244;
		takeoff.updateTakeoffState(armed, landed, phase >= 12, 1.5f, false, timestamp);
		ref_takeoff.updateTakeoffState(armed, landed, phase >= 12, 1.5f, false, timestamp);
		EXPECT_EQ(static_cast<int>(takeoff.getTakeoffState()), static_cast<int>(ref_takeoff.getTakeoffState()));
		const float ramp = takeoff.updateRamp(dt, 1.5f);
		sameFloat(ramp, ref_takeoff.updateRamp(dt,1.5f));
		gains(a,variant,k); gains(b,variant,k); // Includes updates while armed and with pending requests.
		if (k % 43 == 0) {
			const float hover = .45f + .015f * ((k/43)%7);
			a.updateHoverThrust(hover); b.updateHoverThrust(hover); ++hte;
			compareOutputs(a,b);
		}
		const bool ground_reset = takeoff.getTakeoffState() < TakeoffState::rampup || (phase >= 244);
		if (ground_reset || k % 89 == 0) { a.resetIntegral(); b.resetIntegral(); ++resets; }
		const int mode = variant && k % 17 < 8 ? 1 : 0;
		const int axes = variant && k % 23 < 8 ? 3 : 0;
		a.configureVelocityControl(mode, axes, armed);
		EXPECT_EQ(a.velocitySelection().effectiveMode(), 0);
		EXPECT_EQ(a.velocitySelection().effectiveAxes(), 0);
		compareOutputs(a,b); // Selector must not reset or otherwise mutate the PID state.
		const float tilt = k % 128 < 64 ? .2f : .7f;
		const float thrust_max = k % 160 < 80 ? .6f : .9f;
		a.setTiltLimit(tilt); b.setTiltLimit(tilt);
		a.setThrustLimits(ground_reset ? 0.f : .12f,thrust_max);
		b.setThrustLimits(ground_reset ? 0.f : .12f,thrust_max);
		// Parameter-linked XY/Z limits plus the actual frozen takeoff ramp.
		const float xy_all = .5f + .1f * ((k / 64) % 4);
		const float z_all = 1.f + .25f * ((k / 128) % 3);
		a.setVelocityLimits(xy_all, math::min(ramp,z_all), .75f*z_all);
		b.setVelocityLimits(xy_all, math::min(ramp,z_all), .75f*z_all);
		const float v = .15f*sinf(.031f*k + variant);
		PositionControlStates state{Vector3f(.2f,-.1f,-1.8f), Vector3f(v,-v,.1f), Vector3f(.2f,-.3f,.1f), .4f};
		auto sp = emptySp();
		sp.vx=.7f; sp.vy=-.4f; sp.vz=-.5f;
		sp.yaw=.3f; sp.yawspeed=.12f;
		Vector3f(.3f,-.2f,.1f).copyTo(sp.acceleration);
		switch ((k / 16) % 8) {
		case 0: sp.x=1.f; sp.y=-1.f; sp.z=-2.5f; break;
		case 1: sp.yaw=sp.yawspeed=NAN; break; // velocity only, default yaw semantics
		case 2: sp.vx=sp.vy=sp.vz=NAN; break; // pure acceleration
		case 3: sp.vx=sp.vy=NAN; state.velocity(2)=.7f*.18f+.3f*.1f; break; // pre-blended Z measurement
		case 4: sp.vx=8.f; sp.vy=-9.f; sp.vz=-8.f; Vector3f(30.f,-25.f,-15.f).copyTo(sp.acceleration); break;
		case 5: sp.x=1.f; sp.y=NAN; break; // invalid paired XY, same-frame failsafe retry
		case 6: state.velocity(0)=NAN; state.acceleration(0)=NAN; break;
		case 7: sp.x=state.position(0)+.3f; sp.y=state.position(1)-.2f; sp.z=state.position(2)-.1f;
			state.position += Vector3f(2.f,-3.f,.4f); sp.x+=2.f; sp.y-=3.f; sp.z+=.4f; break; // EKF delta translation
		}
		if (ground_reset) { sp=emptySp(); Vector3f(0.f,0.f,100.f).copyTo(sp.acceleration); }
		a.setState(state);
		b.setState({state.position,state.velocity,state.acceleration,state.yaw});
		a.setInputSetpoint(sp); b.setInputSetpoint(sp);
		const bool ok=a.update(dt);
		ASSERT_EQ(ok,b.update(dt));
		compareOutputs(a,b);
		if (!ok) {
			++retries;
			auto fallback=emptySp(); Vector3f(0.f,0.f,.2f).copyTo(fallback.acceleration);
			a.setInputSetpoint(fallback); b.setInputSetpoint(fallback);
			a.setVelocityLimits(2.f,1.5f,1.f); b.setVelocityLimits(2.f,1.5f,1.f);
			const bool retry_ok=a.update(dt); ASSERT_EQ(retry_ok,b.update(dt));
			EXPECT_TRUE(retry_ok);
			compareOutputs(a,b);
		} else { ++accepted; }
		vehicle_local_position_setpoint_s out{}; a.getLocalPositionSetpoint(out);
		if (fabsf(Vector3f(out.thrust).norm()-thrust_max)<1e-5f) { ++limited; }
	}
	EXPECT_GT(retries,100); EXPECT_GT(resets,100); EXPECT_GT(hte,40); EXPECT_GT(limited,20); EXPECT_GT(accepted,1000);
}

TEST(VelocityControl, FrozenPid2048Uniform) { sequence(0); }
TEST(VelocityControl, FrozenPid2048NonuniformAndRejectedRequests) { sequence(1); }

TEST(VelocityControl, DefaultAndSignedRangeRejection)
{
	VelocityControlSelector s;
	EXPECT_EQ(s.effectiveMode(),0); EXPECT_EQ(s.effectiveAxes(),0); EXPECT_FALSE(s.pending()); EXPECT_EQ(s.reject(),0);
	for (int32_t mode : {INT32_MIN,-1,1,2,3,256,INT32_MAX}) {
		s.configure(mode,0,false);
		EXPECT_EQ(s.requestedMode(),mode); EXPECT_EQ(s.effectiveMode(),0); EXPECT_NE(s.reject(),0); EXPECT_FALSE(s.pending());
	}
}

TEST(VelocityControl, EveryNonzeroAxesRejected)
{
	VelocityControlSelector s;
	for (int32_t axes : {INT32_MIN,-1,1,2,3,4,5,6,7,8,256,INT32_MAX}) {
		s.configure(0,axes,false);
		EXPECT_EQ(s.requestedAxes(),axes); EXPECT_EQ(s.effectiveAxes(),0); EXPECT_EQ(s.reject(),VelocityControlSelector::AxesUnavailable);
	}
}

TEST(VelocityControl, ArmedPendingCancelAndDisarm)
{
	VelocityControlSelector s;
	s.configure(1,3,true);
	EXPECT_TRUE(s.pending()); EXPECT_EQ(s.reject(),6); EXPECT_EQ(s.effectiveMode(),0);
	s.configure(0,0,true);
	EXPECT_FALSE(s.pending()); EXPECT_EQ(s.reject(),0);
	s.configure(2,7,true); EXPECT_TRUE(s.pending());
	s.configure(2,7,false); EXPECT_FALSE(s.pending()); EXPECT_EQ(s.reject(),6); EXPECT_EQ(s.effectiveMode(),0);
	s.configure(0,0,false); EXPECT_EQ(s.reject(),0); EXPECT_EQ(s.effectiveAxes(),0);
}

TEST(VelocityControl, RestartRevalidatesPersistedRequest)
{
	const int32_t stored_mode=2, stored_axes=7;
	VelocityControlSelector restarted;
	restarted.configure(stored_mode,stored_axes,false);
	EXPECT_EQ(restarted.requestedMode(),2); EXPECT_EQ(restarted.reject(),6);
	EXPECT_EQ(restarted.effectiveMode(),0); EXPECT_FALSE(restarted.pending());
}
