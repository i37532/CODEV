// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>
#include "PositionControl.hpp"
#include "VelocityDiagnosticExcitation.hpp"
#include <ecl/geo/geo.h>

namespace
{
using Guard = StaVelocityProtection;
using matrix::Vector3f;
Guard::Config candidate()
{
	Guard::Config c{}; c.axes = 1; c.gains[0] = {1.f, .2f};
	c.nu_limit[0] = .4f; c.acceleration_limit[0] = .8f; return c;
}
Guard::Frame airborne(uint64_t sample = 1000000)
{
	Guard::Frame f{}; f.sample = sample; f.armed = f.enabled = f.flying = true;
	f.landed = f.contact = false; return f;
}
vehicle_local_position_setpoint_s target(float x = .1f)
{
	vehicle_local_position_setpoint_s s{}; s.x = s.y = s.z = NAN;
	s.vx = x; s.vy = .02f; s.vz = -.01f; s.yaw = 0.f;
	for (float &v : s.acceleration) { v = NAN; }
	return s;
}
void setup(PositionControl &p)
{
	p.setPositionGains(Vector3f(.95f, .95f, 1.f));
	p.setVelocityGains(Vector3f(1.8f,1.8f,4.f),Vector3f(.4f,.4f,2.f),Vector3f(.2f,.2f,0.f));
	p.setVelocityLimits(12.f,3.f,1.f); p.setThrustLimits(.12f,1.f);
	p.setTiltLimit(.7f); p.setHoverThrust(.5f);
	p.configureVelocityEsta(candidate(),false); p.configureVelocityControl(1,1,false);
}
bool step(PositionControl &p, Guard::Frame f, const vehicle_local_position_setpoint_s &sp, Vector3f v = Vector3f())
{
	p.setVelocityFrame(f); p.setState({Vector3f(),v,Vector3f(),sp.yaw}); p.setInputSetpoint(sp); return p.update(.01f);
}
}

TEST(VelocityEsta, AdmissionRequiresConfiguredGainsAndOnlyNorth)
{
	PositionControl p;
	p.configureVelocityControl(1,1,false); EXPECT_EQ(p.velocitySelection().effectiveMode(),0);
	setup(p); ASSERT_EQ(p.velocitySelection().effectiveMode(),1);
	for (int axes : {0,2,3,4,5,6,7,256}) {
		p.configureVelocityControl(1,axes,false); EXPECT_NE(p.velocitySelection().reject(),0);
		EXPECT_EQ(p.velocitySelection().effectiveAxes(),1);
	}
	p.configureVelocityControl(2,1,false); EXPECT_NE(p.velocitySelection().reject(),0);
}

TEST(VelocityEsta, SignedCorrectionOldNuFeedforwardAndWorldDirection)
{
	for (float sign : {-1.f,1.f}) {
		for (float yaw : {0.f,1.5707963268f}) {
			PositionControl p; setup(p); auto f=airborne(); auto sp=target(.1f*sign);
			sp.yaw=yaw; sp.acceleration[0]=.02f; sp.acceleration[1]=0.f;
			ASSERT_TRUE(step(p,f,sp)); f.sample+=10000; ASSERT_TRUE(step(p,f,sp));
			const auto &d=p.diagnostic();
			EXPECT_NEAR(d.a_sta[0],sign*sqrtf(.1f),1e-6f);
			EXPECT_NEAR(d.a_req[0],d.a_sta[0]+.02f,1e-6f);
			EXPECT_FLOAT_EQ(d.nu_before[0],0.f); EXPECT_NEAR(d.nu_applied[0],sign*.002f,1e-7f);
			EXPECT_EQ(d.committed_axes,1); EXPECT_EQ(d.pid_axes,6);
			EXPECT_GT(sign*d.thrust[0],0.f); EXPECT_TRUE(std::isnan(d.nu_applied[1]));
			vehicle_attitude_setpoint_s a{}; p.getAttitudeSetpoint(a);
			const Vector3f actual=matrix::Dcmf(matrix::Quatf(a.q_d))*Vector3f(a.thrust_body);
			for (int i=0;i<3;++i) { EXPECT_NEAR(actual(i),d.thrust[i],1e-6f); }
		}
	}
}

TEST(VelocityEsta, YZPidSemanticsAndHoverThrustRemainIndependent)
{
	PositionControl p, pid; setup(p); setup(pid); pid.configureVelocityControl(0,0,false);
	// Match X demand exactly: different X demand legitimately couples into the
	// common thrust map and Y tracking ARW. Do not assert independent trajectories.
	auto f=airborne(); auto sp=target(0.f); sp.acceleration[0]=0.f; sp.acceleration[1]=-.02f;
	for (int k=0;k<200;++k) {
		if (k==100) { p.updateHoverThrust(.55f); pid.updateHoverThrust(.55f); }
		ASSERT_TRUE(step(p,f,sp)); ASSERT_TRUE(step(pid,f,sp));
		for (int i=1;i<3;++i) { EXPECT_FLOAT_EQ(p.diagnostic().a_req[i],pid.diagnostic().a_req[i]); }
		f.sample+=10000;
	}
}

TEST(VelocityEsta, SameSampleRetryNeverCommitsAndFaultNeedsDisarm)
{
	PositionControl p; setup(p); auto f=airborne(); auto sp=target();
	ASSERT_TRUE(step(p,f,sp)); f.sample+=10000; ASSERT_TRUE(step(p,f,sp));
	const float nu=p.diagnostic().nu_applied[0];
	EXPECT_FALSE(step(p,f,sp)); EXPECT_EQ(p.diagnostic().committed_axes,0);
	EXPECT_FALSE(p.velocityOutputPublishable());
	EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[0],nu);
	f.sample+=10000; EXPECT_FALSE(step(p,f,sp));
	f.armed=false; f.sample+=10000; EXPECT_TRUE(step(p,f,sp));
	f.armed=true; f.sample+=10000; ASSERT_TRUE(step(p,f,sp));
	EXPECT_EQ(p.diagnostic().committed_axes,0); EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[0],0.f);
}

TEST(VelocityEsta, GroundRampExitContactAndFreshTakeoffReset)
{
	PositionControl p; setup(p); auto f=airborne(); auto sp=target();
	for (int cycle=0;cycle<4;++cycle) {
		ASSERT_TRUE(step(p,f,sp)); f.sample+=10000; ASSERT_TRUE(step(p,f,sp));
		EXPECT_NEAR(p.diagnostic().nu_applied[0],.002f,1e-7f);
		f.sample+=10000;
		if (cycle==0) { f.contact=true; }
		if (cycle==1) { f.flying=false; }
		if (cycle==2) { f.enabled=false; }
		if (cycle==3) { f.landed=true; }
		ASSERT_TRUE(step(p,f,sp)); EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[0],0.f);
		f=airborne(f.sample+10000);
	}
}

TEST(VelocityEsta, InvalidPairsMeasurementTimeInnerAndEkfLatch)
{
	for (int fault=0;fault<6;++fault) {
		PositionControl p; setup(p); auto f=airborne(); auto sp=target(); ASSERT_TRUE(step(p,f,sp));
		f.sample+=10000; Vector3f v;
		if (fault==0) { sp.vy=NAN; }
		if (fault==1) { v(0)=NAN; }
		if (fault==2) { f.sample+=100000; }
		if (fault==3) { f.inner_valid=false; }
		if (fault==4) { f.unmatched_reset_axes=1; }
		if (fault==5) { sp.acceleration[0]=INFINITY; sp.acceleration[1]=INFINITY; }
		EXPECT_FALSE(step(p,f,sp,v)); EXPECT_EQ(p.diagnostic().committed_axes,0);
		EXPECT_FALSE(p.velocityOutputPublishable());
		f=airborne(f.sample+10000); EXPECT_FALSE(step(p,f,target()));
	}
}

TEST(VelocityEsta, ArmedGainsPendingCancelDisarmAndModeReset)
{
	PositionControl p; setup(p); auto f=airborne(); auto sp=target(); ASSERT_TRUE(step(p,f,sp));
	auto c=candidate(); c.gains[0].lambda1=2.f; p.configureVelocityEsta(c,true);
	f.sample+=10000; ASSERT_TRUE(step(p,f,sp)); EXPECT_TRUE(p.diagnostic().config_pending);
	EXPECT_NEAR(p.diagnostic().a_sta[0],sqrtf(.1f),1e-6f);
	p.configureVelocityEsta(candidate(),true); f.sample+=10000; ASSERT_TRUE(step(p,f,sp));
	EXPECT_FALSE(p.diagnostic().config_pending);
	p.configureVelocityControl(0,0,true); EXPECT_TRUE(p.velocitySelection().pending());
	EXPECT_EQ(p.velocitySelection().effectiveMode(),1);
	f.armed=false; f.sample+=10000; step(p,f,sp);
	p.configureVelocityEsta(c,false); p.configureVelocityControl(0,0,false);
	EXPECT_EQ(p.velocitySelection().effectiveMode(),0);
	p.configureVelocityControl(1,1,false); f=airborne(f.sample+10000); ASSERT_TRUE(step(p,f,sp));
	f.sample+=10000; ASSERT_TRUE(step(p,f,sp)); EXPECT_NEAR(p.diagnostic().a_sta[0],2.f*sqrtf(.1f),1e-6f);
}

TEST(VelocityEsta, RealThrustSaturationFreezesOnlyOutwardNu)
{
	PositionControl p; setup(p); auto f=airborne(); auto sp=target(.2f);
	sp.acceleration[0]=sp.acceleration[1]=0.f; sp.acceleration[2]=-30.f;
	ASSERT_TRUE(step(p,f,sp)); f.sample+=10000; ASSERT_TRUE(step(p,f,sp));
	EXPECT_TRUE(p.diagnostic().constraint_bits & 4); EXPECT_FLOAT_EQ(p.diagnostic().thrust[0],0.f);
	EXPECT_TRUE(p.diagnostic().sta_flags & Guard::OutwardFreeze);
	EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[0],0.f);
}

TEST(VelocityEsta, IndependentObjectWithAttitudeMotorLagAndMassMismatch)
{
	// Separate physical states; exact scalar ZOH lag integration, no simulator truth input.
	for (double gain : {.8,1.,1.2}) {
		for (double lag : {.04,.08}) {
			PositionControl p; setup(p); auto f=airborne();
			double velocity=0.,attitude_accel=0.,motor_accel=0.,t=0.,sum=0.,duration=0.;
			for (int k=0;k<4000;++k) {
				const double h=k%2?.012:.008;
				auto sp=target(VelocityDiagnosticExcitation::waveform(static_cast<float>(t)));
				sp.vy=sp.vz=0.f;
				ASSERT_TRUE(step(p,f,sp,Vector3f(static_cast<float>(velocity),0.f,0.f)));
				const auto &d=p.diagnostic();
				const double demanded=static_cast<double>(d.thrust[0])*9.80665/.5;
				const double next_att=demanded+(attitude_accel-demanded)*exp(-h/lag);
				const double next_motor=next_att+(motor_accel-next_att)*exp(-h/.03);
				velocity+=gain*(next_att*h+(motor_accel-next_att)*.03*(1.-exp(-h/.03)))+.02*h;
				attitude_accel=next_att; motor_accel=next_motor;
				if (t<32.) { const double error=static_cast<double>(d.s[0]); sum+=error*error*h; duration+=h; }
				EXPECT_LT(fabs(velocity),1.); EXPECT_LE(fabs(d.nu_applied[0]),.400001f);
				f.sample+=k%2?12000:8000; t+=h;
			}
			EXPECT_LT(sqrt(sum/duration),.08); // Development screen, not a proof of vehicle stability.
		}
	}
}
