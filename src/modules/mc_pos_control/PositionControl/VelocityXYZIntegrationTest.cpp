// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>
#include "PositionControl.hpp"
#include "VelocityXYZDiagnosticExcitation.hpp"
#include <cmath>

namespace {
using G = StaVelocityProtection;
using matrix::Vector3f;
G::Config config() {
	G::Config c{}; c.axes=7;
	c.gains[0]={1.f,.2f}; c.gains[1]={1.5f,.3f}; c.gains[2]={2.f,1.f};
	c.nu_limit={{.4f,.4f,4.f}}; c.acceleration_limit={{.8f,.8f,6.f}}; return c;
}
void setup(PositionControl &p,bool esta=true) {
	p.setPositionGains(Vector3f(.95f,.95f,1.f));
	p.setVelocityGains(Vector3f(1.8f,1.8f,4.f),Vector3f(.4f,.4f,2.f),Vector3f(.2f,.2f,0.f));
	p.setVelocityLimits(12.f,3.f,.55f); p.setThrustLimits(.12f,1.f); p.setTiltLimit(.7f); p.setHoverThrust(.5f);
	if(esta) { p.configureVelocityEsta(config(),false); p.configureVelocityControl(1,7,false); }
}
G::Frame frame() { G::Frame f{}; f.sample=1000000; f.armed=f.enabled=f.flying=true; f.landed=f.contact=false; return f; }
vehicle_local_position_setpoint_s target(float x=0.f,float y=0.f,float z=0.f) {
	vehicle_local_position_setpoint_s s{}; s.x=s.y=s.z=NAN; s.vx=x; s.vy=y; s.vz=z;
	for(auto &a:s.acceleration) { a=NAN; } return s;
}
bool step(PositionControl &p,G::Frame &f,vehicle_local_position_setpoint_s s,Vector3f v=Vector3f()) {
	p.setVelocityFrame(f); p.setState({Vector3f(),v,Vector3f(),0.f}); p.setInputSetpoint(s); return p.update(.01f);
}
}

TEST(VelocityXYZIntegration, GroundPidAndAtomicContinuousThreeAxisHandover) {
	PositionControl p,q; setup(p); setup(q,false); auto f=frame(); f.flying=false;
	auto s=target(.01f,-.02f,-.1f); s.acceleration[0]=.02f; s.acceleration[1]=-.01f; s.acceleration[2]=-.03f;
	for(int k=0;k<20;++k) {
		ASSERT_TRUE(step(p,f,s)); ASSERT_TRUE(step(q,f,s));
		for(int i=0;i<3;++i) { EXPECT_FLOAT_EQ(p.diagnostic().thrust[i],q.diagnostic().thrust[i]); }
		EXPECT_EQ(p.diagnostic().z_phase,1); EXPECT_EQ(p.diagnostic().committed_axes,0); f.sample+=10000;
	}
	f.flying=true; ASSERT_TRUE(step(p,f,s)) << "fault=" << p.diagnostic().sta_fault << " a=" << p.diagnostic().a_req[0] << "," << p.diagnostic().a_req[1] << "," << p.diagnostic().a_req[2] << " thrust=" << p.diagnostic().thrust[0] << "," << p.diagnostic().thrust[1] << "," << p.diagnostic().thrust[2]; ASSERT_TRUE(step(q,f,s)); auto before=p.diagnostic();
	EXPECT_EQ(before.z_phase,2); EXPECT_EQ(before.pid_axes,7); EXPECT_EQ(before.committed_axes,0);
	for(int i=0;i<3;++i) { EXPECT_FLOAT_EQ(before.a_req[i],q.diagnostic().a_req[i]); }
	f.sample+=10000; ASSERT_TRUE(step(p,f,s)); const auto d=p.diagnostic();
	EXPECT_EQ(d.pid_axes,0); EXPECT_EQ(d.active_axes,7); EXPECT_EQ(d.committed_axes,7);
	for(int i=0;i<3;++i) { EXPECT_NEAR(d.a_req[i],before.a_req[i],1e-6f); EXPECT_FLOAT_EQ(d.nu_before[i],before.nu_applied[i]); }
}

TEST(VelocityXYZIntegration, IndependentOldNuSignedOutputsAndSingleFeedforward) {
	for(float direction:{-1.f,1.f}) {
		PositionControl p; setup(p); auto f=frame(); ASSERT_TRUE(step(p,f,target())); f.sample+=10000;
		auto s=target(direction*.1f,-direction*.04f,direction*.01f);
		s.acceleration[0]=.02f; s.acceleration[1]=-.03f; s.acceleration[2]=.04f;
		ASSERT_TRUE(step(p,f,s)); const auto d=p.diagnostic();
		const float expected[]={direction*sqrtf(.1f),-direction*.3f,direction*.2f};
		const float nu[]={direction*.002f,-direction*.003f,direction*.01f};
		for(int i=0;i<3;++i) {
			EXPECT_NEAR(d.a_sta[i],expected[i],1e-6f); EXPECT_NEAR(d.a_req[i],expected[i]+s.acceleration[i],1e-6f);
			EXPECT_NEAR(d.nu_applied[i],nu[i],1e-7f);
		}
		EXPECT_EQ(d.pid_axes,0);
	}
}

TEST(VelocityXYZIntegration, InvalidThirdAxisOrRetryNeverPartiallyCommits) {
	for(int fault=0;fault<8;++fault) {
		SCOPED_TRACE(fault);
		PositionControl p; setup(p); auto f=frame(); ASSERT_TRUE(step(p,f,target())); f.sample+=10000;
		ASSERT_TRUE(step(p,f,target(.01f,-.01f,.01f))); const auto old=p.diagnostic();
		if(fault!=0) { f.sample+=10000; } auto s=target(); Vector3f v;
		if(fault==1) { v(2)=NAN; } if(fault==2) { s.acceleration[2]=INFINITY; }
		if(fault==3) { f.sample-=20000; } if(fault==4) { f.sample+=100000; }
		if(fault==5) { f.inner_valid=false; } if(fault==6) { f.unmatched_reset_axes=4; }
		if(fault==7) { f.unmatched_reset_axes=2; }
		EXPECT_FALSE(step(p,f,s,v)); EXPECT_EQ(p.diagnostic().committed_axes,0); EXPECT_FALSE(p.velocityOutputPublishable());
		for(int i=0;i<3;++i) { EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[i],old.nu_applied[i]); }
		f.sample+=10000; EXPECT_FALSE(step(p,f,target()));
		f.armed=false; f.sample+=10000; ASSERT_TRUE(step(p,f,target()));
		const auto next_sample=f.sample+10000; f=frame(); f.sample=next_sample; ASSERT_TRUE(step(p,f,target())); EXPECT_EQ(p.diagnostic().z_phase,2);
	}
}

TEST(VelocityXYZIntegration, SeedAndProxyInvalidLastAxisAreAtomic) {
	for(int fault=0;fault<2;++fault) {
		G g; ASSERT_TRUE(g.configure(config(),false)); auto f=frame(); g.begin(f);
		if(fault==0) { EXPECT_FALSE(g.seedXYZ({{.1f,.1f,5.f}})); }
		else { ASSERT_TRUE(g.seedXYZ({{0.f,0.f,0.f}})); f.sample+=10000; f.target={{.1f,-.1f,.1f}}; g.begin(f); g.finish({{0.f,0.f,NAN}},7,true); }
		for(float value:g.state()) { EXPECT_FLOAT_EQ(value,0.f); }
	}
}

TEST(VelocityXYZIntegration, HteChangesOnlyZAtNonzeroTilt) {
	PositionControl p; setup(p); auto f=frame(); auto s=target(); s.acceleration[0]=.3f; s.acceleration[1]=-.2f;
	ASSERT_TRUE(step(p,f,s)); f.sample+=10000; ASSERT_TRUE(step(p,f,s)); const auto old=p.diagnostic();
	p.updateHoverThrust(.55f); f.sample+=10000; ASSERT_TRUE(step(p,f,s)); const auto d=p.diagnostic();
	for(int i=0;i<3;++i) { EXPECT_NEAR(d.thrust[i],old.thrust[i],2e-6f); }
	for(int i=0;i<2;++i) { EXPECT_FLOAT_EQ(d.nu_before[i],old.nu_applied[i]); }
	EXPECT_NEAR(d.z_hte_shift,(1.f-.5f/.55f)*9.80665f,2e-6f); EXPECT_EQ(d.pid_axes,0);
}

TEST(VelocityXYZIntegration, InvalidHteAndUnrepresentableHandoverFailClosed) {
	for(int fault=0;fault<3;++fault) {
		PositionControl p; setup(p); auto f=frame();
		if(fault==0) { EXPECT_FALSE(step(p,f,target(.5f,0.f,0.f))); }
		else { ASSERT_TRUE(step(p,f,target())); p.updateHoverThrust(fault==1?NAN:.9f); f.sample+=10000; EXPECT_FALSE(step(p,f,target())); }
		EXPECT_EQ(p.diagnostic().committed_axes,0); EXPECT_FALSE(p.velocityOutputPublishable());
	}
}

TEST(VelocityXYZIntegration, VerticalPriorityAndTiltFreezeOnlyOutwardNu) {
	for(int constraint=0;constraint<2;++constraint) {
		PositionControl p; setup(p); auto f=frame(); ASSERT_TRUE(step(p,f,target()));
		if(constraint==1) { p.setTiltLimit(.005f); }
		f.sample+=10000; auto s=target(.2f,-.1f,-.1f); if(constraint==0) { s.acceleration[2]=-30.f; }
		ASSERT_TRUE(step(p,f,s)); const auto d=p.diagnostic(); EXPECT_NE(d.constraint_bits,0); EXPECT_EQ(d.committed_axes,7);
		EXPECT_TRUE(d.sta_flags&G::OutwardFreeze); EXPECT_FLOAT_EQ(d.nu_applied[0],0.f); EXPECT_FLOAT_EQ(d.nu_applied[1],0.f);
		if(constraint==0) { EXPECT_FLOAT_EQ(d.nu_applied[2],0.f); EXPECT_FLOAT_EQ(d.thrust[2],-1.f); }
		else { EXPECT_LT(d.nu_applied[2],0.f); }
	}
}

TEST(VelocityXYZIntegration, MixedAccelerationExitReentryAndNoStaleState) {
	PositionControl p; setup(p); auto f=frame(); ASSERT_TRUE(step(p,f,target())); f.sample+=10000;
	ASSERT_TRUE(step(p,f,target(.01f,-.01f,.01f)));
	for(int active:{3,7,4,7,0,7}) {
		auto s=target(); if(!(active&3)) { s.vx=s.vy=NAN; s.acceleration[0]=s.acceleration[1]=0.f; }
		if(!(active&4)) { s.vz=NAN; s.acceleration[2]=.02f; }
		f.sample+=10000; ASSERT_TRUE(step(p,f,s)); EXPECT_EQ(p.diagnostic().committed_axes,0);
		for(int i=0;i<3;++i) { EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[i],0.f); }
		f.sample+=10000; ASSERT_TRUE(step(p,f,s)); EXPECT_EQ(p.diagnostic().committed_axes,active); EXPECT_EQ(p.diagnostic().pid_axes,0);
	}
}

TEST(VelocityXYZIntegration, ArmedXYZChangesAndMaskSwitchReset) {
	PositionControl p; setup(p); auto f=frame(); ASSERT_TRUE(step(p,f,target()));
	for(int axis=0;axis<3;++axis) {
		auto c=config(); c.gains[axis].lambda1+=.1f; p.configureVelocityEsta(c,true);
		f.sample+=10000; ASSERT_TRUE(step(p,f,target())); EXPECT_TRUE(p.diagnostic().config_pending);
		p.configureVelocityEsta(config(),true); f.sample+=10000; ASSERT_TRUE(step(p,f,target())); EXPECT_FALSE(p.diagnostic().config_pending);
	}
	for(int mask:{1,3,4,7,0,7}) {
		auto c=config(); c.axes=mask?mask:7; p.configureVelocityEsta(c,false); p.configureVelocityControl(mask?1:0,mask,false);
		EXPECT_EQ(p.velocitySelection().effectiveAxes(),mask); EXPECT_EQ(p.velocitySelection().reject(),0);
		f.armed=false; f.sample+=10000; ASSERT_TRUE(step(p,f,target()));
		f.armed=true; f.sample+=10000; ASSERT_TRUE(step(p,f,target())); EXPECT_EQ(p.diagnostic().committed_axes,0);
	}
	p.configureVelocityControl(0,0,true); EXPECT_TRUE(p.velocitySelection().pending()); EXPECT_EQ(p.velocitySelection().effectiveAxes(),7);
	p.configureVelocityControl(1,7,true); EXPECT_FALSE(p.velocitySelection().pending());
	for(int mask:{2,5,6,-1,256}) { p.configureVelocityControl(1,mask,false); EXPECT_NE(p.velocitySelection().reject(),0); }
	p.configureVelocityControl(2,7,false); EXPECT_NE(p.velocitySelection().reject(),0);
}

TEST(VelocityXYZIntegration, ContactBounceCancelAndRestartRequireFreshHandover) {
	for(int reason=0;reason<5;++reason) {
		PositionControl p; setup(p); auto f=frame(); ASSERT_TRUE(step(p,f,target())); f.sample+=10000;
		ASSERT_TRUE(step(p,f,target(.01f,-.01f,.01f)));
		if(reason==0) { f.contact=true; } if(reason==1) { f.landed=true; } if(reason==2) { f.flying=false; }
		if(reason==3) { f.armed=false; } if(reason==4) { f.enabled=false; }
		f.sample+=10000; ASSERT_TRUE(step(p,f,target())); EXPECT_EQ(p.diagnostic().committed_axes,0);
		for(int i=0;i<3;++i) { EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[i],0.f); }
		auto next=frame(); next.sample=f.sample+10000; ASSERT_TRUE(step(p,next,target())); EXPECT_EQ(p.diagnostic().z_phase,2);
	}
}

TEST(VelocityXYZIntegration, SmoothBoundedZeroAreaStimulusAndLimitWiring) {
	double integrals[3][3]{};
	for(int k=0;k<=64000;++k) {
		float x,y,z; VelocityXYZDiagnosticExcitation::waveform(k*.001f,x,y,z);
		EXPECT_LE(std::hypot(x,y),.200001f); EXPECT_LE(fabsf(z),.100001f);
		const int window=k<16000?0:(k<32000?1:2); integrals[window][0]+=static_cast<double>(x)*.001; integrals[window][1]+=static_cast<double>(y)*.001; integrals[window][2]+=static_cast<double>(z)*.001;
	}
	for(auto &window:integrals) { for(double value:window) { EXPECT_NEAR(value,0.,2e-6); } }
	PositionControl p; setup(p,false); auto f=frame(); p.setDiagnosticExcitationXYZ(.1f,-.1f,.1f);
	ASSERT_TRUE(step(p,f,target(0.f,0.f,.5f))); EXPECT_FLOAT_EQ(p.diagnostic().v_sp[2],.55f); EXPECT_FLOAT_EQ(p.diagnostic().v_sp[1],-.1f);
	p.setDiagnosticExcitation(0.f); f.sample+=10000; ASSERT_TRUE(step(p,f,target()));
	for(int i=0;i<3;++i) { EXPECT_FLOAT_EQ(p.diagnostic().v_sp[i],0.f); }
}

TEST(VelocityXYZIntegration, IndependentThreeAxisLaggedPlantAndThrustCoupling) {
	for(double gain:{.8,1.,1.2}) {
		PositionControl p; setup(p); auto c=config(); c.gains[1]=c.gains[0]; p.configureVelocityEsta(c,false); p.configureVelocityControl(1,7,false);
		auto f=frame(); double v[3]{},a[3]{},square[3]{};
		for(int k=0;k<6400;++k) {
			const double h=k%2?.012:.008; float x,y,z; VelocityXYZDiagnosticExcitation::waveform(k*.01f,x,y,z);
			ASSERT_TRUE(step(p,f,target(x,y,z),Vector3f(v[0],v[1],v[2])));
			const auto d=p.diagnostic(); double req[3]; for(int i=0;i<3;++i) { req[i]=static_cast<double>(d.thrust[i])*9.80665/.5+(i==2?9.80665:0.); }
			const double targets[]={x,y,z};
			for(int i=0;i<3;++i) {
				const double demand=gain*req[i]+.03*req[(i+1)%3], lag=i==2?.06:.1, decay=std::exp(-h/lag);
				v[i]+=demand*h+(a[i]-demand)*lag*(1.-decay)+(.02+.0001*k*.01)*h;
				a[i]=demand+(a[i]-demand)*decay;
				EXPECT_LT(std::abs(v[i]),.4); square[i]+=(v[i]-targets[i])*(v[i]-targets[i]);
			}
			f.sample+=k%2?12000:8000;
		}
		for(double sum:square) { EXPECT_LT(std::sqrt(sum/6400.),.06); }
	}
}
