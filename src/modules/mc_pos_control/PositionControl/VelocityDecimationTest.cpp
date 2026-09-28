// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>
#include "PositionControl.hpp"
#include <cmath>

namespace {
using matrix::Vector3f;
using Guard = StaVelocityProtection;
vehicle_local_position_setpoint_s target(float x=.1f, float y=-.04f)
{
	vehicle_local_position_setpoint_s s{}; s.x=s.y=s.z=NAN; s.vx=x; s.vy=y;
	for (float &a : s.acceleration) { a=NAN; } return s;
}
Guard::Frame frame(uint64_t sample=1000000)
{
	Guard::Frame f{}; f.sample=sample; f.armed=f.enabled=f.flying=true; f.landed=f.contact=false; return f;
}
void setup(PositionControl &p, int divisor, bool esta=false)
{
	p.setPositionGains(Vector3f(.95f,.95f,1.f));
	p.setVelocityGains(Vector3f(1.8f,1.8f,4.f),Vector3f(.4f,.4f,2.f),Vector3f(.2f,.2f,0.f));
	p.setVelocityLimits(12.f,3.f,1.f); p.setThrustLimits(.12f,1.f); p.setTiltLimit(.7f); p.setHoverThrust(.5f);
	Guard::Config c{}; c.axes=3;
	for (int i=0;i<2;++i) { c.gains[i]={1.f,.2f}; c.nu_limit[i]=.4f; c.acceleration_limit[i]=.8f; }
	p.configureVelocityEsta(c,false); p.configureVelocityControl(esta?1:0,esta?3:0,false);
	p.configureVelocityDivisor(divisor,false);
}
bool step(PositionControl &p, Guard::Frame f, const vehicle_local_position_setpoint_s &s,
	Vector3f v=Vector3f(), Vector3f a=Vector3f())
{
	p.setVelocityFrame(f); p.setState({Vector3f(),v,a,0.f}); p.setInputSetpoint(s); return p.update(.01f);
}
}

TEST(VelocityDecimation, CadenceTrueNonuniformTimeAndCounts)
{
	for (int n : {1,2,4}) {
		VelocityDecimation d; d.configure(n,false); uint64_t t=1000000,last=0; unsigned count=0;
		for (int i=0;i<100;++i) {
			ASSERT_TRUE(d.begin(t,.01f,1,true));
			if (i%n==0) { EXPECT_TRUE(d.updated); if(last) { EXPECT_NEAR(d.h,(t-last)*1e-6,1e-8); } last=t; ++count; }
			else { EXPECT_TRUE(d.held); EXPECT_TRUE(std::isnan(d.h)); }
			t+=i%2?12000:8000;
		}
		EXPECT_EQ(d.sequence,count); EXPECT_EQ(count,100u/n);
	}
}

TEST(VelocityDecimation, ParamRejectPendingCancelAndRestart)
{
	VelocityDecimation d;
	for (int bad : {-1,0,3,8,2147483647}) { d.configure(bad,false); EXPECT_TRUE(d.rejected); EXPECT_EQ(d.divisor,1); }
	d.configure(4,true); EXPECT_TRUE(d.pending); EXPECT_EQ(d.divisor,1);
	d.configure(1,true); EXPECT_FALSE(d.pending);
	d.configure(4,false); EXPECT_EQ(d.divisor,4); EXPECT_FALSE(d.pending);
	VelocityDecimation restarted; restarted.configure(d.requested,false); EXPECT_EQ(restarted.divisor,4);
	d.configure(2,false,false); EXPECT_TRUE(d.rejected); EXPECT_EQ(d.divisor,4);
}

TEST(VelocityDecimation, RawClockRejectsDuplicateBackwardsShortLong)
{
	for (uint64_t next : {uint64_t(1000000),uint64_t(999000),uint64_t(1001000),uint64_t(1040001),uint64_t(0)}) {
		VelocityDecimation d; d.configure(4,false); ASSERT_TRUE(d.begin(1000000,.01f,0,true));
		EXPECT_FALSE(d.begin(next,.01f,0,true)); EXPECT_NE(d.fault,0);
		EXPECT_FALSE(d.begin(next+10000,.01f,0,true));
		d.restart(); EXPECT_TRUE(d.begin(2000000,.01f,0,true));
	}
}

TEST(VelocityDecimation, InvalidatePreservesElapsedTimeAndAccumulatedBound)
{
	VelocityDecimation d; d.configure(4,false); ASSERT_TRUE(d.begin(1000000,.01f,1,true));
	ASSERT_TRUE(d.begin(1040000,.01f,1,true)); EXPECT_TRUE(d.held); d.invalidate();
	ASSERT_TRUE(d.begin(1080000,.01f,1,true)); EXPECT_TRUE(d.updated); EXPECT_FLOAT_EQ(d.h,.08f);
}

TEST(VelocityDecimation, PidHoldNewTargetFfThrustAndNoIntegration)
{
	for(int n:{2,4}) {
		PositionControl p; setup(p,n); auto f=frame(); auto s=target(); ASSERT_TRUE(step(p,f,s));
		const auto correction=p.velocityCorrection(), integral=p.velocityIntegral();
		for(int k=1;k<n;++k) {
			f.sample+=10000; s.vx=.2f*k; s.vy=-.1f*k; s.acceleration[0]=.02f*k; s.acceleration[1]=-.01f*k; s.acceleration[2]=-.05f*k;
			ASSERT_TRUE(step(p,f,s)); EXPECT_TRUE(p.velocityDecimation().held);
			for(int i=0;i<3;++i) { EXPECT_FLOAT_EQ(p.velocityIntegral()(i),integral(i)); EXPECT_FLOAT_EQ(p.velocityCorrection()(i),correction(i));
				EXPECT_FLOAT_EQ(p.diagnostic().a_req[i],correction(i)+s.acceleration[i]); }
			EXPECT_FLOAT_EQ(p.diagnostic().v_sp[0],s.vx);
		}
		f.sample+=10000; ASSERT_TRUE(step(p,f,s)); EXPECT_TRUE(p.velocityDecimation().updated);
		EXPECT_NEAR(p.velocityDecimation().h,n*.01f,1e-8f); EXPECT_NE(p.velocityIntegral()(0),integral(0));
	}
}

TEST(VelocityDecimation, PositionAndVelocityFeedforwardRunOnHolds)
{
	PositionControl p; setup(p,4); auto f=frame(); auto s=target(); s.x=s.y=0.f;
	ASSERT_TRUE(step(p,f,s)); const auto c=p.velocityCorrection(); f.sample+=10000; s.x=.3f; s.y=-.2f; s.vx=.2f;
	ASSERT_TRUE(step(p,f,s)); EXPECT_TRUE(p.velocityDecimation().held);
	EXPECT_NEAR(p.diagnostic().v_sp[0],.3f*.95f+.2f,1e-7f); EXPECT_FLOAT_EQ(p.velocityCorrection()(0),c(0));
}

TEST(VelocityDecimation, HteShiftSynchronizesCacheWithoutIntegration)
{
	PositionControl p; setup(p,4); auto f=frame(); auto s=target(0.f,0.f); ASSERT_TRUE(step(p,f,s));
	const float previous=p.velocityIntegral()(2), old_c=p.velocityCorrection()(2);
	p.updateHoverThrust(.55f); const float shift=p.velocityIntegral()(2)-previous;
	EXPECT_NEAR(p.velocityCorrection()(2),old_c+shift,1e-7f);
	f.sample+=10000; ASSERT_TRUE(step(p,f,s)); EXPECT_TRUE(p.velocityDecimation().held);
	EXPECT_FLOAT_EQ(p.velocityIntegral()(2),previous+shift); EXPECT_NEAR(p.diagnostic().thrust[2],-.5f,1e-6f);
}

TEST(VelocityDecimation, EstaIndependentNuTrueHAndHoldNewFf)
{
	for(int n:{2,4}) {
		PositionControl p; setup(p,n,true); auto f=frame(); auto s=target(); ASSERT_TRUE(step(p,f,s));
		for(int k=1;k<=n;++k) { f.sample+=k%2?8000:12000; ASSERT_TRUE(step(p,f,s)); }
		EXPECT_NEAR(p.diagnostic().nu_applied[0],.2f*n*.01f,1e-7f);
		EXPECT_NEAR(p.diagnostic().nu_applied[1],-.2f*n*.01f,1e-7f);
		const auto d=p.diagnostic(); const auto c=p.velocityCorrection(); f.sample+=10000;
		s.acceleration[0]=.1f; s.acceleration[1]=-.2f; ASSERT_TRUE(step(p,f,s));
		EXPECT_TRUE(p.velocityDecimation().held); EXPECT_EQ(p.diagnostic().committed_axes,0);
		for(int i=0;i<2;++i) { EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[i],d.nu_applied[i]); EXPECT_NEAR(p.diagnostic().a_req[i],c(i)+s.acceleration[i],1e-7f); }
	}
}

TEST(VelocityDecimation, HoldSafetyMeasurementAndInnerFailureLatch)
{
	for(bool esta:{false,true}) { for(int fault=0;fault<4;++fault) {
		SCOPED_TRACE(::testing::Message() << "ESTA=" << esta << " fault=" << fault);
		PositionControl p; setup(p,4,esta); auto f=frame(); auto s=target(); ASSERT_TRUE(step(p,f,s));
		f.sample+=10000; Vector3f v;
		if(fault==0) { f.inner_valid=false; } if(fault==1) { f.unmatched_reset_axes=1; }
		if(fault==2) { v(1)=NAN; } if(fault==3) { s.acceleration[0]=INFINITY; }
		EXPECT_FALSE(step(p,f,s,v)); EXPECT_FALSE(p.velocityOutputPublishable());
		f=frame(f.sample+10000); EXPECT_FALSE(step(p,f,target()));
		f.armed=false; f.sample+=10000; EXPECT_TRUE(step(p,f,target()));
	} }
}

TEST(VelocityDecimation, SameFrameRetryDoesNotIntegrateTwice)
{
	PositionControl p; setup(p,4); auto f=frame(); auto s=target(); ASSERT_TRUE(step(p,f,s));
	const auto integral=p.velocityIntegral(); const auto seq=p.velocityDecimation().sequence;
	s.acceleration[0]=.3f; s.acceleration[1]=.2f; p.setInputSetpoint(s); ASSERT_TRUE(p.update(.01f));
	EXPECT_EQ(p.velocityDecimation().sequence,seq);
	for(int i=0;i<3;++i) { EXPECT_FLOAT_EQ(p.velocityIntegral()(i),integral(i)); }
}

TEST(VelocityDecimation, ConstraintDuringHoldFreezesNextPidAndEstaUpdate)
{
	for(bool esta:{false,true}) {
		PositionControl p; setup(p,4,esta); auto f=frame(); auto s=target(.2f,-.1f);
		for(int k=0;k<=4;++k) { ASSERT_TRUE(step(p,f,s)); f.sample+=10000; }
		const auto integral=p.velocityIntegral(); const auto nu=p.diagnostic();
		p.setTiltLimit(.001f); ASSERT_TRUE(step(p,f,s)); EXPECT_TRUE(p.velocityDecimation().held);
		EXPECT_NE(p.intervalPositive()&1,0); EXPECT_NE(p.intervalNegative()&2,0);
		p.setTiltLimit(.7f);
		for(int k=0;k<3;++k) { f.sample+=10000; ASSERT_TRUE(step(p,f,s)); }
		EXPECT_TRUE(p.velocityDecimation().updated);
		if(esta) { EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[0],nu.nu_applied[0]); EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[1],nu.nu_applied[1]); }
		else { EXPECT_FLOAT_EQ(p.velocityIntegral()(0),integral(0)); EXPECT_FLOAT_EQ(p.velocityIntegral()(1),integral(1)); }
	}
}

TEST(VelocityDecimation, LifecycleAndAccelerationOnlyInvalidateCache)
{
	PositionControl p; setup(p,4,true); auto f=frame(); auto s=target();
	for(int k=0;k<=4;++k) { ASSERT_TRUE(step(p,f,s)); f.sample+=10000; }
	f.contact=true; ASSERT_TRUE(step(p,f,s)); EXPECT_TRUE(p.velocityDecimation().updated);
	EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[0],0.f); EXPECT_FLOAT_EQ(p.velocityCorrection()(0),0.f);
	f.contact=false; f.sample+=10000; ASSERT_TRUE(step(p,f,s)); EXPECT_EQ(p.diagnostic().committed_axes,0);
	s.vx=s.vy=NAN; s.acceleration[0]=.03f; s.acceleration[1]=-.02f; f.sample+=10000;
	ASSERT_TRUE(step(p,f,s)); EXPECT_FLOAT_EQ(p.diagnostic().a_req[0],.03f);
	p.resetIntegral(); f.sample+=10000; ASSERT_TRUE(step(p,f,s)); EXPECT_TRUE(p.velocityDecimation().updated);
}

TEST(VelocityDecimation, XyzCannotEnterUnsupportedDecimation)
{
	PositionControl p; setup(p,4,true); Guard::Config c{}; c.axes=7;
	for(int i=0;i<3;++i) { c.gains[i]={1.f,.2f}; c.nu_limit[i]=4.f; c.acceleration_limit[i]=6.f; }
	p.configureVelocityEsta(c,false); p.configureVelocityControl(1,7,false);
	EXPECT_NE(p.velocitySelection().reject(),0); EXPECT_EQ(p.velocitySelection().effectiveAxes(),3);
	p.configureVelocityDivisor(1,false); p.configureVelocityControl(1,7,false); EXPECT_EQ(p.velocitySelection().effectiveAxes(),7);
	p.configureVelocityDivisor(4,false); EXPECT_TRUE(p.velocityDecimation().rejected); EXPECT_EQ(p.velocityDecimation().divisor,1);
}

TEST(VelocityDecimation, IndependentLaggedObjectAllDivisors)
{
	// Independent exact-ZOH first-order acceleration actuator, double plant.
	// Engineering robustness check, not a claim of ideal STA convergence.
	for(bool esta:{false,true}) { for(int n:{1,2,4}) {
		PositionControl p; setup(p,n,esta); auto f=frame(); double v=0.,a=0.; unsigned updates=0;
		for(int k=0;k<2000;++k) {
			const double h=k%2?.012:.008; const double desired=.08*sin(k*.01);
			auto s=target(desired,0.f); s.acceleration[0]=.08*cos(k*.01); s.acceleration[1]=0.f;
			ASSERT_TRUE(step(p,f,s,Vector3f(v,0.f,0.f),Vector3f(a,0.f,0.f)));
			if(p.velocityDecimation().updated) { ++updates; }
			const double u=static_cast<double>(p.diagnostic().a_req[0])+.03; const double decay=exp(-h/.06);
			v+=u*h+(a-u)*.06*(1.-decay); a=u+(a-u)*decay;
			ASSERT_TRUE(std::isfinite(v)); EXPECT_LT(fabs(v),.5); f.sample+=k%2?12000:8000;
		}
		EXPECT_EQ(updates,2000u/n);
	} }
}

TEST(VelocityDecimation, ArmedExitDoesNotClearLatchButDisarmDoes)
{
	PositionControl p; setup(p,4); auto f=frame(); auto s=target(); ASSERT_TRUE(step(p,f,s));
	f.sample+=10000; f.inner_valid=false; EXPECT_FALSE(step(p,f,s));
	f.enabled=false; f.sample+=10000; p.setVelocityFrame(f); EXPECT_NE(p.velocityDecimation().fault,0);
	f=frame(f.sample+10000); EXPECT_FALSE(step(p,f,s));
	f.armed=false; f.sample+=1000000; ASSERT_TRUE(step(p,f,s)); EXPECT_EQ(p.velocityDecimation().fault,0);
	f=frame(f.sample+10000); ASSERT_TRUE(step(p,f,s));
}

TEST(VelocityDecimation, ParameterChangesDeferredUntilDisarmWithoutStateInheritance)
{
	PositionControl p; setup(p,4,true); auto f=frame(); auto s=target();
	for(int k=0;k<5;++k) { ASSERT_TRUE(step(p,f,s)); f.sample+=10000; }
	p.configureVelocityDivisor(2,true); EXPECT_EQ(p.velocityDecimation().divisor,4); EXPECT_TRUE(p.velocityDecimation().pending);
	p.configureVelocityDivisor(4,true); EXPECT_FALSE(p.velocityDecimation().pending);
	f.armed=false; ASSERT_TRUE(step(p,f,s)); p.configureVelocityDivisor(2,false);
	EXPECT_EQ(p.velocityDecimation().divisor,2); f=frame(f.sample+10000); ASSERT_TRUE(step(p,f,s));
	EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[0],0.f); EXPECT_EQ(p.diagnostic().committed_axes,0);
}

TEST(VelocityDecimation, HalfNanFailsBeforeStateCommit)
{
	for(bool esta:{false,true}) {
		PositionControl p; setup(p,4,esta); auto f=frame(); auto s=target(); ASSERT_TRUE(step(p,f,s));
		const auto integral=p.velocityIntegral(); f.sample+=10000; s.vy=NAN;
		EXPECT_FALSE(step(p,f,s)); EXPECT_FALSE(p.velocityOutputPublishable());
		for(int i=0;i<3;++i) { EXPECT_FLOAT_EQ(p.velocityIntegral()(i),integral(i)); }
		EXPECT_EQ(p.diagnostic().committed_axes,0);
	}
}

TEST(VelocityDecimation, IntervalDirectionalGuardAllowsInwardButNotOutwardNu)
{
	for(float sign:{-1.f,1.f}) {
		Guard g; Guard::Config c{}; c.axes=3;
		for(int i=0;i<2;++i) { c.gains[i]={1.f,.2f}; c.nu_limit[i]=.4f; c.acceleration_limit[i]=.8f; }
		g.configure(c,false); auto f=frame(); f.target={{sign*.1f,-sign*.1f,0.f}};
		g.begin(f); g.finish({{0.f,0.f,0.f}},0,true); f.sample+=10000;
		const auto &candidate=g.begin(f); Guard::Vec proxy=candidate.a_req;
		const auto &out=g.finish(proxy,0,true,sign>0.f?1:2,sign>0.f?2:1);
		EXPECT_FLOAT_EQ(out.nu_applied[0],0.f); EXPECT_FLOAT_EQ(out.nu_applied[1],0.f);
		f.sample+=10000; const auto &inward=g.begin(f); proxy=inward.a_req;
		const auto &r=g.finish(proxy,0,true,sign>0.f?2:1,sign>0.f?1:2);
		EXPECT_NEAR(r.nu_applied[0],sign*.002f,1e-7f); EXPECT_NEAR(r.nu_applied[1],-sign*.002f,1e-7f);
	}
}
