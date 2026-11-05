// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>
#include "PositionControl.hpp"
#include "AX00PositionControl.hpp"
#include <cmath>
#include <cstring>
#include <climits>

namespace {
using G = StaVelocityProtection;
using matrix::Vector3f;
template<typename C> C gains(int axes) {
	C c{}; c.axes=axes;
	for(int i=0;i<3;++i) {
		c.gains[i]={i==2?2.f:.5f,i==2?1.f:.1f};
		c.nu_limit[i]=i==2?4.f:.4f; c.acceleration_limit[i]=i==2?6.f:.8f;
	}
	return c;
}
template<typename P> void setup(P &p) {
	p.setPositionGains(Vector3f(.95f,.95f,1.f));
	p.setVelocityGains(Vector3f(2.16f,2.16f,4.f),Vector3f(.48f,.48f,2.f),Vector3f(.24f,.24f,0.f));
	p.setVelocityLimits(12.f,3.f,.55f); p.setThrustLimits(.12f,1.f); p.setTiltLimit(.7f); p.setHoverThrust(.5f);
}
void select(PositionControl &p,int axes,bool armed=false) {
	p.configureVelocityEsta(gains<G::Config>(axes),armed); p.configureVelocityControl(axes?1:0,axes,armed);
}
G::Frame frame() {
	G::Frame f{}; f.sample=1000000; f.armed=f.enabled=f.flying=true; f.landed=f.contact=false; return f;
}
vehicle_local_position_setpoint_s target() {
	vehicle_local_position_setpoint_s s{}; s.x=s.y=s.z=NAN; return s;
}
bool step(PositionControl &p,G::Frame &f,vehicle_local_position_setpoint_s s=target(),Vector3f v=Vector3f()) {
	p.setVelocityFrame(f); p.setState({Vector3f(),v,Vector3f(),0.f}); p.setInputSetpoint(s); return p.update(.01f);
}
void bits(float a,float b) {
	if(std::isnan(a) && std::isnan(b)) { return; }
	uint32_t x,y; memcpy(&x,&a,4); memcpy(&y,&b,4); EXPECT_EQ(x,y) << a << " vs " << b;
}
class VelocityAxes : public ::testing::TestWithParam<int> {};
INSTANTIATE_TEST_SUITE_P(AllMasks,VelocityAxes,::testing::Values(0,1,2,3,4,5,6,7));
}

TEST_P(VelocityAxes, SignedAdmissionAndExclusiveAxesWithOneFeedforward) {
	const int axes=GetParam(); PositionControl p; setup(p); select(p,axes);
	ASSERT_EQ(p.velocitySelection().effectiveAxes(),axes); ASSERT_EQ(p.velocitySelection().reject(),0);
	auto f=frame(); ASSERT_TRUE(step(p,f)); f.sample+=10000;
	auto s=target(); s.vx=.02f; s.vy=-.03f; s.vz=.01f;
	s.acceleration[0]=.02f; s.acceleration[1]=-.03f; s.acceleration[2]=.04f;
	ASSERT_TRUE(step(p,f,s)); const auto d=p.diagnostic();
	EXPECT_EQ(d.committed_axes,axes); EXPECT_EQ(d.active_axes,axes); EXPECT_EQ(d.pid_axes,7^axes);
	const float error[]={.02f,-.03f,.01f};
	for(int i=0;i<3;++i) {
		if(axes&(1<<i)) {
			EXPECT_NEAR(d.a_sta[i],(i==2?2.f:.5f)*sqrtf(fabsf(error[i]))*(error[i]>0?1.f:-1.f),1e-6f);
			EXPECT_NEAR(d.a_req[i],d.a_sta[i]+s.acceleration[i],1e-6f);
			EXPECT_FLOAT_EQ(p.velocityIntegral()(i),0.f);
		} else {
			EXPECT_NEAR(d.a_req[i],error[i]*(i==2?4.f:2.16f)+s.acceleration[i],1e-6f);
			EXPECT_TRUE(std::isnan(d.nu_applied[i])); EXPECT_NE(p.velocityIntegral()(i),0.f);
		}
	}
}

TEST_P(VelocityAxes, ArmedPendingCancellationDisarmAndFreshState) {
	const int axes=GetParam(); PositionControl p; setup(p); select(p,axes,true);
	EXPECT_EQ(p.velocitySelection().effectiveAxes(),0); EXPECT_EQ(p.velocitySelection().pending(),axes!=0);
	select(p,0,true); EXPECT_FALSE(p.velocitySelection().pending()); select(p,axes,false);
	auto f=frame(); ASSERT_TRUE(step(p,f)); f.sample+=10000; auto s=target(); s.vx=.01f; s.vy=-.01f; s.vz=.01f;
	ASSERT_TRUE(step(p,f,s));
	if(axes) {
		const int selected=axes&1?0:(axes&2?1:2);
		auto c=gains<G::Config>(axes); c.gains[selected].lambda1=9.f;
		p.configureVelocityEsta(c,true); p.configureVelocityControl(1,axes,true);
		f.sample+=10000; ASSERT_TRUE(step(p,f,s));
		EXPECT_TRUE(p.diagnostic().config_pending);
		select(p,axes,true); f.sample+=10000; ASSERT_TRUE(step(p,f,s)); EXPECT_FALSE(p.diagnostic().config_pending);
	}
	f.armed=false; f.sample+=10000; ASSERT_TRUE(step(p,f));
	for(int i=0;i<3;++i) { if(axes&(1<<i)) { EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[i],0.f); } }
	select(p,0); EXPECT_EQ(p.velocitySelection().effectiveMode(),0);
	PositionControl restarted; setup(restarted); select(restarted,axes); EXPECT_EQ(restarted.velocitySelection().effectiveAxes(),axes);
}

TEST(VelocityAxesBoundary, InvalidRequestCannotContaminateEffectiveGains) {
	for(int invalid:{INT_MIN,-1,8,256,INT_MAX}) {
		PositionControl p; setup(p); select(p,7); auto f=frame(); ASSERT_TRUE(step(p,f));
		auto bad=gains<G::Config>(1); bad.gains[0].lambda1=9.f;
		p.configureVelocityEsta(bad,false); p.configureVelocityControl(1,invalid,false);
		EXPECT_NE(p.velocitySelection().reject(),0); EXPECT_EQ(p.velocitySelection().effectiveAxes(),7);
		f.sample+=10000; auto s=target(); s.vx=.01f; ASSERT_TRUE(step(p,f,s)); EXPECT_NEAR(p.diagnostic().a_sta[0],.05f,1e-7f);
	}
	PositionControl p; setup(p); select(p,6); p.configureVelocityControl(2,6,false);
	EXPECT_NE(p.velocitySelection().reject(),0); EXPECT_EQ(p.velocitySelection().effectiveAxes(),6);
}

TEST(VelocityAxesBoundary, NewMasksNeverAdmitDivisorsTwoOrFour) {
	for(int axes:{2,5,6}) { for(int div:{2,4}) {
		PositionControl p; setup(p); select(p,axes); p.configureVelocityDivisor(div,false);
		EXPECT_TRUE(p.velocityDecimation().rejected); EXPECT_EQ(p.velocityDecimation().divisor,1);
		PositionControl q; setup(q); q.configureVelocityDivisor(div,false); select(q,axes);
		EXPECT_NE(q.velocitySelection().reject(),0); EXPECT_EQ(q.velocitySelection().effectiveMode(),0);
	} }
}

TEST(VelocityAxesBoundary, NewMasksFaultTimeMeasurementResetAndSameSample) {
	for(int axes:{2,5,6}) { for(int fault=0;fault<8;++fault) {
		SCOPED_TRACE(axes*10+fault); PositionControl p; setup(p); select(p,axes); auto f=frame(); ASSERT_TRUE(step(p,f));
		f.sample+=10000; auto s=target(); s.vx=.01f; s.vy=-.01f; s.vz=.01f; ASSERT_TRUE(step(p,f,s)); const auto old=p.diagnostic();
		if(fault!=0) { f.sample+=10000; } Vector3f v;
		if(fault==1) { f.sample-=20000; } if(fault==2) { f.sample+=40001; }
		if(fault==3) { f.inner_valid=false; } if(fault==4) { f.unmatched_reset_axes=axes; }
		if(fault==5) { v(axes&4?2:1)=NAN; } if(fault==6) { s.acceleration[axes&4?2:1]=INFINITY; }
		if(fault==7) { s.vy=NAN; }
		EXPECT_FALSE(step(p,f,s,v)); EXPECT_FALSE(p.velocityOutputPublishable()); EXPECT_EQ(p.diagnostic().committed_axes,0);
		for(int i=0;i<3;++i) { if(axes&(1<<i)) { EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[i],old.nu_applied[i]); } }
		// Same sensor sample, changed failsafe target cannot commit or clear latch.
		EXPECT_FALSE(step(p,f)); EXPECT_EQ(p.diagnostic().committed_axes,0);
		f=frame(); f.sample=2000000; f.armed=false; ASSERT_TRUE(step(p,f));
		f.armed=true; f.sample+=10000; ASSERT_TRUE(step(p,f)); EXPECT_EQ(p.diagnostic().committed_axes,0);
	} }
}

TEST(VelocityAxesBoundary, CoupledGroundHandoverHteContactAndRemainingPid) {
	for(int axes:{5,6}) {
		PositionControl p,q; setup(p); setup(q); select(p,axes); auto f=frame(); f.flying=false;
		auto s=target(); s.vx=.005f; s.vy=-.005f; s.vz=-.01f; s.acceleration[0]=.1f; s.acceleration[1]=-.1f;
		for(int k=0;k<10;++k) {
			ASSERT_TRUE(step(p,f,s)); ASSERT_TRUE(step(q,f,s));
			for(int i=0;i<3;++i) { bits(p.diagnostic().thrust[i],q.diagnostic().thrust[i]); }
			EXPECT_EQ(p.diagnostic().z_phase,1); f.sample+=10000;
		}
		f.flying=true; ASSERT_TRUE(step(p,f,s)); ASSERT_TRUE(step(q,f,s)); auto boundary=p.diagnostic();
		EXPECT_EQ(boundary.z_phase,2); EXPECT_EQ(boundary.pid_axes,7); EXPECT_EQ(boundary.committed_axes,0);
		for(int i=0;i<3;++i) { bits(boundary.a_req[i],q.diagnostic().a_req[i]); }
		f.sample+=10000; ASSERT_TRUE(step(p,f,s)); auto before=p.diagnostic();
		EXPECT_EQ(before.pid_axes,7^axes); EXPECT_EQ(before.committed_axes,axes);
		for(int i=0;i<3;++i) { if(axes&(1<<i)) { EXPECT_NEAR(before.a_req[i],boundary.a_req[i],1e-6f); } }
		p.updateHoverThrust(.505f); f.sample+=10000; ASSERT_TRUE(step(p,f,s));
		EXPECT_NE(p.diagnostic().z_hte_shift,0.f); EXPECT_EQ(p.diagnostic().pid_axes,7^axes);
		for(int i=0;i<2;++i) { if(axes&(1<<i)) { EXPECT_FLOAT_EQ(p.diagnostic().nu_before[i],before.nu_applied[i]); } }
		f.contact=true; f.sample+=10000; ASSERT_TRUE(step(p,f)); EXPECT_EQ(p.diagnostic().z_phase,1); EXPECT_EQ(p.diagnostic().committed_axes,0);
		f.contact=false; f.sample+=10000; ASSERT_TRUE(step(p,f)); EXPECT_EQ(p.diagnostic().z_phase,2);
	}
}

TEST(VelocityAxesBoundary, CoupledInactiveComponentsReprimeWithoutStaleNu) {
	for(int axes:{5,6}) {
		PositionControl p; setup(p); select(p,axes); auto f=frame(); ASSERT_TRUE(step(p,f));
		for(int active:{axes&3,axes,4,axes,0,axes}) {
			auto s=target(); if(!(active&3)) { s.vx=s.vy=NAN; } if(!(active&4)) { s.vz=NAN; }
			f.sample+=10000; ASSERT_TRUE(step(p,f,s)); EXPECT_EQ(p.diagnostic().committed_axes,0);
			f.sample+=10000; ASSERT_TRUE(step(p,f,s)); EXPECT_EQ(p.diagnostic().committed_axes,active);
			EXPECT_EQ(p.diagnostic().pid_axes,(active&3)?(7^axes):0);
		}
	}
}

TEST(VelocityAxesBoundary, CoupledInvalidLastSeedAndFeedbackAreAtomic) {
	for(int axes:{5,6}) { for(int kind=0;kind<2;++kind) {
		G g; ASSERT_TRUE(g.configure(gains<G::Config>(axes),false)); auto f=frame(); g.begin(f);
		if(!kind) { EXPECT_FALSE(g.seedCoupled({{.1f,.1f,5.f}})); }
		else { ASSERT_TRUE(g.seedCoupled({{0.f,0.f,0.f}})); f.sample+=10000; f.target={{.01f,-.01f,.01f}}; g.begin(f); g.finish({{0.f,0.f,NAN}},axes,true); }
		for(float value:g.state()) { EXPECT_FLOAT_EQ(value,0.f); }
	} }
}

TEST(VelocityAxesBoundary, HandoverCannotClipAndHteFailureCannotTakeover) {
	for(int axes:{5,6}) { for(int kind=0;kind<3;++kind) {
		PositionControl p; setup(p); select(p,axes); auto f=frame(); auto s=target();
		if(!kind) { s.vx=s.vy=.5f; EXPECT_FALSE(step(p,f,s)); }
		else { ASSERT_TRUE(step(p,f)); p.updateHoverThrust(kind==1?NAN:.9f); f.sample+=10000; EXPECT_FALSE(step(p,f)); }
		EXPECT_EQ(p.diagnostic().committed_axes,0); EXPECT_FALSE(p.velocityOutputPublishable());
	} }
}

TEST(VelocityAxesBoundary, ConstraintsFreezeSelectedStatesAndKeepOtherPid) {
	for(int axes:{2,5,6}) { for(int kind=0;kind<2;++kind) {
		PositionControl p; setup(p); select(p,axes); auto f=frame(); ASSERT_TRUE(step(p,f));
		if(kind) { p.setTiltLimit(.001f); }
		f.sample+=10000; auto s=target(); s.vx=.2f; s.vy=-.1f; s.vz=-.1f; if(!kind) { s.acceleration[2]=-30.f; }
		ASSERT_TRUE(step(p,f,s)); auto d=p.diagnostic(); EXPECT_NE(d.constraint_bits,0); EXPECT_TRUE(d.sta_flags&G::OutwardFreeze);
		EXPECT_EQ(d.committed_axes,axes); EXPECT_EQ(d.pid_axes,7^axes);
		for(int i=0;i<2;++i) { if(axes&(1<<i)) { EXPECT_FLOAT_EQ(d.nu_applied[i],0.f); } }
	} }
}

TEST(VelocityAxesRegression, ExistingMasksTwoSequencesEach2048Bitwise) {
	for(int axes:{0,1,3,4,7}) { for(int variant=0;variant<2;++variant) {
		PositionControl p; AX00PositionControl q; setup(p); setup(q); select(p,axes);
		q.configureVelocityEsta(gains<AX00StaVelocityProtection::Config>(axes?axes:1),false);
		q.configureVelocityControl(axes?1:0,axes,false);
		auto f=frame(); AX00StaVelocityProtection::Frame old{};
		for(int k=0;k<2048;++k) {
			SCOPED_TRACE(axes*100000+variant*10000+k);
			const float h=variant?(k%2?.008f:.012f):.01f;
			f.sample+=static_cast<uint64_t>(h*1e6f); f.armed=(k%503!=0); f.flying=k>8; f.contact=(k%509==0);
			f.unmatched_reset_axes=k==1800?axes:0;
			old.sample=f.sample; old.armed=f.armed; old.enabled=f.enabled; old.flying=f.flying;
			old.landed=f.landed; old.contact=f.contact; old.inner_valid=true; old.unmatched_reset_axes=f.unmatched_reset_axes;
			auto s=target(); const float t=k*.01f; s.vx=.01f*sinf(t); s.vy=.01f*cosf(t); s.vz=.005f*sinf(t);
			s.acceleration[0]=.02f*cosf(t); s.acceleration[1]=-.02f*sinf(t); s.acceleration[2]=.01f;
			if(variant && k%307==0) { s.vx=s.vy=NAN; }
			if(k%257==0) { const float hover=k%514?.505f:.5f; p.updateHoverThrust(hover); q.updateHoverThrust(hover); }
			const float tilt=(k>250 && k<300)?.001f:.7f; p.setTiltLimit(tilt); q.setTiltLimit(tilt);
			p.setVelocityFrame(f); q.setVelocityFrame(old);
			const Vector3f v(.003f*sinf(t),-.002f*cosf(t),.001f),vd(.004f,.003f,.002f);
			p.setState({Vector3f(),v,vd,0.f}); q.setState({Vector3f(),v,vd,0.f});
			p.setInputSetpoint(s); q.setInputSetpoint(s); ASSERT_EQ(p.update(h),q.update(h));
			const auto a=p.diagnostic(),b=q.diagnostic();
			EXPECT_EQ(a.pid_axes,b.pid_axes); EXPECT_EQ(a.active_axes,b.active_axes); EXPECT_EQ(a.committed_axes,b.committed_axes);
			EXPECT_EQ(a.z_phase,b.z_phase); EXPECT_EQ(a.sta_fault,b.sta_fault); EXPECT_EQ(a.sta_flags,b.sta_flags);
			for(int i=0;i<3;++i) {
				bits(a.a_req[i],b.a_req[i]); bits(a.thrust[i],b.thrust[i]); bits(a.v_sp[i],b.v_sp[i]);
				bits(a.nu_applied[i],b.nu_applied[i]); bits(a.a_sta[i],b.a_sta[i]); bits(p.velocityIntegral()(i),q.velocityIntegral()(i));
			}
		}
	} }
}

TEST(VelocityAxesModel, IndependentDoublePlantWithAttitudeMotorLagAndCoupling) {
	// No model truth enters production control; this is an independent offline
	// plant consuming normalized thrust with two first-order actuator lags.
	for(int axes=0;axes<=7;++axes) { for(int constrained=0;constrained<2;++constrained) {
		SCOPED_TRACE(axes*10+constrained); PositionControl p; setup(p); select(p,axes); auto f=frame();
		ASSERT_TRUE(step(p,f)); double v[3]{}, attitude[3]{}, actuator[3]{}, square[3]{}; unsigned n=0;
		for(int k=0;k<3000;++k) {
			const double h=k%2?.008:.012,t=k*.01; f.sample+=static_cast<uint64_t>(h*1e6);
			auto s=target(); s.vx=.03*sin(.5*t); s.vy=.02*sin(.4*t); s.vz=.01*sin(.3*t);
			s.acceleration[0]=.015*cos(.5*t); s.acceleration[1]=.008*cos(.4*t); s.acceleration[2]=.003*cos(.3*t);
			if(constrained) { p.setTiltLimit(.008f); }
			ASSERT_TRUE(step(p,f,s,Vector3f(v[0],v[1],v[2])));
			const auto d=p.diagnostic();
			for(int i=0;i<3;++i) {
				const double mapped=double(d.thrust[i])*9.80665/.5+(i==2?9.80665:0.);
				attitude[i]+=(1.-exp(-h/.04))*(mapped-attitude[i]);
				actuator[i]+=(1.-exp(-h/.03))*(attitude[i]-actuator[i]);
				const double disturbance=(i==1?-.004:.003)+.0001*t;
				v[i]+=h*(actuator[i]+disturbance); ASSERT_TRUE(std::isfinite(v[i])); ASSERT_LT(fabs(v[i]),.5);
				if(k>1000) { const double e=v[i]-double(d.v_sp[i]); square[i]+=e*e; }
			}
			if(k>1000) { ++n; }
		}
		for(int i=0;i<3;++i) { EXPECT_LT(sqrt(square[i]/n),.1); }
	} }
}
