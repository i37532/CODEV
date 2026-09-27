// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>
#include "PositionControl.hpp"
#include <cmath>
namespace {
using G = StaVelocityProtection;
using matrix::Vector3f;
G::Config config() {
	G::Config c{}; c.axes=4; c.gains[2]={1.f,.2f}; c.nu_limit[2]=2.f; c.acceleration_limit[2]=3.f; return c;
}
void setup(PositionControl &p, bool esta=true) {
	p.setPositionGains(Vector3f(.95f,.95f,1.f));
	p.setVelocityGains(Vector3f(1.8f,1.8f,4.f),Vector3f(.4f,.4f,2.f),Vector3f(.2f,.2f,0.f));
	p.setVelocityLimits(5.f,3.f,.55f); p.setThrustLimits(.12f,1.f); p.setTiltLimit(.7f); p.setHoverThrust(.5f);
	if(esta) { p.configureVelocityEsta(config(),false); p.configureVelocityControl(1,4,false); }
}
G::Frame frame() {
	G::Frame f{}; f.sample=1000000; f.armed=f.enabled=f.flying=true; f.landed=f.contact=false; return f;
}
vehicle_local_position_setpoint_s target(float z=0.f) {
	vehicle_local_position_setpoint_s s{}; s.x=s.y=s.z=NAN; s.vz=z;
	s.acceleration[0]=s.acceleration[1]=s.acceleration[2]=NAN; return s;
}
bool step(PositionControl &p,G::Frame &f,vehicle_local_position_setpoint_s s,Vector3f v=Vector3f()) {
	p.setState({Vector3f(),v,Vector3f(),0.f}); p.setInputSetpoint(s); p.setVelocityFrame(f);
	return p.update(.01f);
}
}

TEST(VelocityZIntegration, IndependentAdmissionAndArmedStaging) {
	PositionControl p; p.configureVelocityControl(1,4,false); EXPECT_EQ(p.velocitySelection().effectiveMode(),0);
	setup(p); EXPECT_EQ(p.velocitySelection().effectiveAxes(),4);
	for(int mask:{1,2,3,5,6,7}) { p.configureVelocityControl(1,mask,false); EXPECT_NE(p.velocitySelection().reject(),0); }
	p.configureVelocityControl(0,0,true); EXPECT_TRUE(p.velocitySelection().pending()); EXPECT_EQ(p.velocitySelection().effectiveAxes(),4);
	p.configureVelocityControl(1,4,true); EXPECT_FALSE(p.velocitySelection().pending());
	auto c=config(); c.gains[2].lambda1=2.f; p.configureVelocityEsta(c,true);
	auto f=frame(); auto s=target(); ASSERT_TRUE(step(p,f,s)); EXPECT_TRUE(p.diagnostic().config_pending);
	p.configureVelocityEsta(config(),true); f.sample+=10000; ASSERT_TRUE(step(p,f,s)); EXPECT_FALSE(p.diagnostic().config_pending);
	p.configureVelocityControl(0,0,false); EXPECT_EQ(p.velocitySelection().effectiveMode(),0);
}

TEST(VelocityZIntegration, UnconfiguredInactiveEstaIsNotPendingDuringPid)
{
	PositionControl p; setup(p,false); G::Config unused{}; unused.axes=1;
	p.configureVelocityEsta(unused,false); p.configureVelocityControl(0,0,false);
	auto f=frame(); p.configureVelocityEsta(unused,true); p.configureVelocityControl(0,0,true);
	ASSERT_TRUE(step(p,f,target())); EXPECT_FALSE(p.diagnostic().config_pending); EXPECT_EQ(p.diagnostic().pid_axes,7);
	// Invalid active ESTA changes remain pending/rejected, never silently applied.
	PositionControl z; setup(z); ASSERT_TRUE(step(z,f,target()));
	auto bad=config(); bad.gains[2].lambda1=0.f; z.configureVelocityEsta(bad,true); z.configureVelocityControl(1,4,true);
	f.sample+=10000; ASSERT_TRUE(step(z,f,target())); EXPECT_TRUE(z.diagnostic().config_pending);
	EXPECT_NE(z.velocitySelection().reject(),0); EXPECT_EQ(z.velocitySelection().effectiveAxes(),4);
}

TEST(VelocityZIntegration, VerticalDiagnosticDoesNotChangeXYOrBypassLimits) {
	PositionControl p; setup(p,false); auto f=frame(); auto s=target(.5f);
	p.setDiagnosticExcitation(.1f,true); ASSERT_TRUE(step(p,f,s));
	EXPECT_FLOAT_EQ(p.diagnostic().v_sp[2],.55f); EXPECT_FLOAT_EQ(p.diagnostic().v_sp[0],0.f);
	f.sample+=10000; p.setDiagnosticExcitation(-.1f,true); s.vz=0.f; ASSERT_TRUE(step(p,f,s));
	EXPECT_FLOAT_EQ(p.diagnostic().v_sp[2],-.1f); EXPECT_EQ(p.diagnostic().pid_axes,7);
	p.setDiagnosticExcitation(0.f); f.sample+=10000; ASSERT_TRUE(step(p,f,s)); EXPECT_FLOAT_EQ(p.diagnostic().v_sp[2],0.f);
}

TEST(VelocityZIntegration, GroundRampBitwisePidAndContinuousHandover) {
	PositionControl p,q; setup(p); setup(q,false); auto f=frame(); auto s=target(-.1f); f.flying=false;
	for(int k=0;k<100;++k) {
		ASSERT_TRUE(step(p,f,s)); ASSERT_TRUE(step(q,f,s));
		for(int i=0;i<3;++i) { EXPECT_FLOAT_EQ(p.diagnostic().a_req[i],q.diagnostic().a_req[i]); EXPECT_FLOAT_EQ(p.diagnostic().thrust[i],q.diagnostic().thrust[i]); }
		EXPECT_EQ(p.diagnostic().z_phase,1); EXPECT_EQ(p.diagnostic().active_axes,0); f.sample+=10000;
	}
	f.flying=true; ASSERT_TRUE(step(p,f,s)); ASSERT_TRUE(step(q,f,s));
	EXPECT_EQ(p.diagnostic().z_phase,2); EXPECT_EQ(p.diagnostic().pid_axes,7);
	EXPECT_FLOAT_EQ(p.diagnostic().thrust[2],q.diagnostic().thrust[2]); const auto old=p.diagnostic();
	f.sample+=10000; ASSERT_TRUE(step(p,f,s)); EXPECT_EQ(p.diagnostic().z_phase,3);
	EXPECT_EQ(p.diagnostic().pid_axes,3); EXPECT_EQ(p.diagnostic().committed_axes,4);
	EXPECT_NEAR(p.diagnostic().a_req[2],old.a_req[2],2e-7f);
	EXPECT_NEAR(p.diagnostic().nu_applied[2],old.nu_applied[2]-.002f,1e-7f);
}

TEST(VelocityZIntegration, SignedOutputOldNuAndFeedforwardExactlyOnce) {
	for(float sign:{-1.f,1.f}) {
		PositionControl p; setup(p); auto f=frame(); auto s=target(); ASSERT_TRUE(step(p,f,s));
		f.sample+=10000; s.vz=sign*.1f; s.acceleration[2]=.07f; ASSERT_TRUE(step(p,f,s)); const auto d=p.diagnostic();
		EXPECT_NEAR(d.a_sta[2],sign*sqrtf(.1f),1e-6f); EXPECT_NEAR(d.a_req[2],d.a_sta[2]+.07f,1e-6f);
		EXPECT_NEAR(d.nu_applied[2],sign*.002f,1e-7f); EXPECT_TRUE(std::isnan(d.nu_applied[0]));
		EXPECT_NEAR(d.thrust[2],(d.a_req[2]/9.80665f-1.f)*.5f,1e-7f);
	}
}

TEST(VelocityZIntegration, HoverRebasePreservesTiltedThrustAndNuNotPidArw) {
	PositionControl p; setup(p); auto f=frame(); auto s=target(); s.vx=.2f; s.vy=-.1f;
	ASSERT_TRUE(step(p,f,s)); f.sample+=10000; ASSERT_TRUE(step(p,f,s)); const auto old=p.diagnostic();
	p.updateHoverThrust(.55f); f.sample+=10000; ASSERT_TRUE(step(p,f,s)); const auto d=p.diagnostic();
	EXPECT_NEAR(d.thrust[2],old.thrust[2],2e-7f); EXPECT_NEAR(d.nu_before[2],(1.f-.5f/.55f)*9.80665f,2e-6f);
	EXPECT_NEAR(d.z_hte_shift,d.nu_before[2],2e-6f); EXPECT_EQ(d.pid_axes,3);
}

TEST(VelocityZIntegration, HteInvalidOrUnrepresentableRebaseLatches) {
	for(float h:{NAN,0.f,.99f,.9f}) {
		PositionControl p; setup(p); auto f=frame(); auto s=target(); ASSERT_TRUE(step(p,f,s));
		p.updateHoverThrust(h); f.sample+=10000; EXPECT_FALSE(step(p,f,s)); EXPECT_FALSE(p.velocityOutputPublishable());
	}
}

TEST(VelocityZIntegration, PureAccelerationExitAndReentryNeverReuseNu) {
	PositionControl p; setup(p); auto f=frame(); auto s=target(); ASSERT_TRUE(step(p,f,s));
	f.sample+=10000; s.vz=.1f; ASSERT_TRUE(step(p,f,s)); EXPECT_NE(p.diagnostic().nu_applied[2],0.f);
	f.sample+=10000; s.vz=NAN; s.acceleration[2]=.2f; ASSERT_TRUE(step(p,f,s));
	EXPECT_EQ(p.diagnostic().z_phase,4); EXPECT_EQ(p.diagnostic().active_axes,0); EXPECT_FLOAT_EQ(p.diagnostic().a_req[2],.2f);
	f.sample+=10000; s=target(); ASSERT_TRUE(step(p,f,s)); EXPECT_EQ(p.diagnostic().z_phase,2);
	EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[2],0.f);
}

TEST(VelocityZIntegration, ContactCancelBounceDisarmAndNewTakeoff) {
	for(int reason=0;reason<5;++reason) {
		PositionControl p; setup(p); auto f=frame(); auto s=target(); ASSERT_TRUE(step(p,f,s));
		f.sample+=10000; s.vz=.1f; ASSERT_TRUE(step(p,f,s));
		f.sample+=10000;
		if(reason==0) { f.contact=true; }
		if(reason==1) { f.landed=true; }
		if(reason==2) { f.flying=false; }
		if(reason==3) { f.armed=false; }
		if(reason==4) { f.enabled=false; }
		ASSERT_TRUE(step(p,f,s)); EXPECT_EQ(p.diagnostic().z_phase,1); EXPECT_EQ(p.diagnostic().committed_axes,0);
		const uint64_t next=f.sample+10000; f=frame(); f.sample=next;
		ASSERT_TRUE(step(p,f,target())); EXPECT_EQ(p.diagnostic().z_phase,2);
	}
}

TEST(VelocityZIntegration, InvalidMeasurementTimingFeedbackResetAndDuplicateNeverFallback) {
	for(int fault=0;fault<8;++fault) {
		PositionControl p; setup(p); auto f=frame(); auto s=target(); ASSERT_TRUE(step(p,f,s));
		if(fault!=0) { f.sample+=10000; }
		Vector3f v;
		if(fault==1) { f.sample-=20000; }
		if(fault==2) { f.sample+=100000; }
		if(fault==3) { v(2)=NAN; }
		if(fault==4) { f.unmatched_reset_axes=4; }
		if(fault==5) { f.inner_valid=false; }
		if(fault==6) { s.acceleration[2]=INFINITY; }
		if(fault==7) { s.vy=NAN; }
		EXPECT_FALSE(step(p,f,s,v)); EXPECT_EQ(p.diagnostic().committed_axes,0); EXPECT_FALSE(p.velocityOutputPublishable());
		f.sample+=10000; EXPECT_FALSE(step(p,f,target()));
		f.armed=false; f.sample+=10000; ASSERT_TRUE(step(p,f,target()));
		const uint64_t next=f.sample+10000; f=frame(); f.sample=next;
		ASSERT_TRUE(step(p,f,target())); EXPECT_EQ(p.diagnostic().z_phase,2);
	}
}

TEST(VelocityZIntegration, ThrustAndCorrectionLimitsFreezeOnlyOutwardIncrement) {
	for(float sign:{-1.f,1.f}) {
		PositionControl p; setup(p); auto f=frame(); ASSERT_TRUE(step(p,f,target()));
		f.sample+=10000; auto s=target(sign*.1f); s.acceleration[2]=sign*30.f; ASSERT_TRUE(step(p,f,s));
		EXPECT_TRUE(p.diagnostic().constraint_bits & 6); EXPECT_TRUE(p.diagnostic().sta_flags & G::OutwardFreeze);
		EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[2],0.f);
		f.sample+=10000; s.vz=-sign*.1f; ASSERT_TRUE(step(p,f,s)); EXPECT_NE(p.diagnostic().nu_applied[2],0.f);
	}
}

TEST(VelocityZIntegration, IndependentZohMotorLagConstantAndRampDisturbance) {
	for(double h:{.008,.012}) {
		PositionControl p; setup(p); auto f=frame(); double v=0.,a=0.,sum=0.;
		for(int k=0;k<4000;++k) {
			const double t=k*h, demand=.1*std::sin(t*.8); auto s=target(static_cast<float>(demand));
			ASSERT_TRUE(step(p,f,s,Vector3f(0.f,0.f,static_cast<float>(v))));
			const double request=static_cast<double>(p.diagnostic().thrust[2])*9.80665/.5+9.80665;
			const double decay=std::exp(-h/.06), disturbance=.03+(t>10? .001*(t-10):0.);
			v+=request*h+(a-request)*.06*(1.-decay)+disturbance*h; a=request+(a-request)*decay;
			const double error=v-demand; if(k>500)sum+=error*error;
			EXPECT_LT(std::abs(v),.3); f.sample+=static_cast<uint64_t>(std::llround(h*1e6));
		}
		EXPECT_LT(std::sqrt(sum/3499.),.04); // screening only, not aircraft proof
	}
}
