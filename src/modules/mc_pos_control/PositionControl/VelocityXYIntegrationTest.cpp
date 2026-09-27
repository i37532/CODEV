// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>
#include "PositionControl.hpp"
#include "VelocityXYDiagnosticExcitation.hpp"
#include <cmath>

namespace {
using G = StaVelocityProtection;
using matrix::Vector3f;
G::Config config()
{
	G::Config c{}; c.axes=3;
	c.gains[0]={1.f,.2f}; c.gains[1]={1.5f,.3f};
	c.nu_limit[0]=c.nu_limit[1]=.4f; c.acceleration_limit[0]=c.acceleration_limit[1]=.8f; return c;
}
G::Frame frame(uint64_t t=1000000)
{
	G::Frame f{}; f.sample=t; f.armed=f.enabled=f.flying=true; f.landed=f.contact=false; return f;
}
vehicle_local_position_setpoint_s target(float x=.1f,float y=-.04f)
{
	vehicle_local_position_setpoint_s s{}; s.x=s.y=s.z=NAN;
	s.vx=x; s.vy=y; s.vz=0.f; for(auto &a:s.acceleration) { a=NAN; } return s;
}
void setup(PositionControl &p)
{
	p.setPositionGains(Vector3f(.95f,.95f,1.f));
	p.setVelocityGains(Vector3f(1.8f,1.8f,4.f),Vector3f(.4f,.4f,2.f),Vector3f(.2f,.2f,0.f));
	p.setVelocityLimits(12.f,3.f,1.f); p.setThrustLimits(.12f,1.f);
	p.setTiltLimit(.7f); p.setHoverThrust(.5f);
	p.configureVelocityEsta(config(),false); p.configureVelocityControl(1,3,false);
}
bool step(PositionControl &p,G::Frame f,const vehicle_local_position_setpoint_s &s,Vector3f v=Vector3f())
{
	p.setVelocityFrame(f); p.setState({Vector3f(),v,Vector3f(),s.yaw}); p.setInputSetpoint(s); return p.update(.01f);
}
}

TEST(VelocityXYIntegration, IndependentGainsOldStatesAndFeedforward)
{
	for(float direction:{-1.f,1.f}) {
		PositionControl p; setup(p); auto f=frame(); auto s=target(direction*.1f,-direction*.04f);
		s.acceleration[0]=.03f; s.acceleration[1]=-.02f;
		ASSERT_TRUE(step(p,f,s)); f.sample+=10000; ASSERT_TRUE(step(p,f,s)); const auto d=p.diagnostic();
		EXPECT_NEAR(d.a_sta[0],direction*sqrtf(.1f),1e-6f); EXPECT_NEAR(d.a_sta[1],-direction*.3f,1e-6f);
		EXPECT_NEAR(d.a_req[0],d.a_sta[0]+.03f,1e-6f); EXPECT_NEAR(d.a_req[1],d.a_sta[1]-.02f,1e-6f);
		EXPECT_FLOAT_EQ(d.nu_before[0],0.f); EXPECT_FLOAT_EQ(d.nu_before[1],0.f);
		EXPECT_NEAR(d.nu_applied[0],direction*.002f,1e-7f); EXPECT_NEAR(d.nu_applied[1],-direction*.003f,1e-7f);
		EXPECT_EQ(d.pid_axes,4); EXPECT_EQ(d.committed_axes,3); EXPECT_TRUE(std::isnan(d.nu_applied[2]));
		f.sample+=10000; ASSERT_TRUE(step(p,f,s));
		EXPECT_FLOAT_EQ(p.diagnostic().nu_before[0],d.nu_applied[0]); EXPECT_FLOAT_EQ(p.diagnostic().nu_before[1],d.nu_applied[1]);
	}
}

TEST(VelocityXYIntegration, InvalidSecondAxisOrSameSampleNeverPartiallyCommits)
{
	for(int fault=0;fault<6;++fault) {
		SCOPED_TRACE(fault);
		PositionControl p; setup(p); auto f=frame(); auto s=target();
		ASSERT_TRUE(step(p,f,s)); f.sample+=10000; ASSERT_TRUE(step(p,f,s));
		const auto before=p.diagnostic(); Vector3f v;
		if(fault!=0) { f.sample+=10000; }
		if(fault==1) { s.vy=NAN; } if(fault==2) { v(1)=NAN; }
		if(fault==3) { f.sample+=100000; } if(fault==4) { f.unmatched_reset_axes=2; }
		if(fault==5) { s.acceleration[0]=0.f; s.acceleration[1]=INFINITY; }
		EXPECT_FALSE(step(p,f,s,v)); EXPECT_EQ(p.diagnostic().committed_axes,0);
		// Original constrainXY propagates a half-NaN target to both axes. The
		// invalid output is rejected and the now-inactive pair resets together.
		for(int i=0;i<2;++i) { EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[i],fault==1?0.f:before.nu_applied[i]); }
		EXPECT_FALSE(p.velocityOutputPublishable());
	}
}

TEST(VelocityXYIntegration, GuardProxyFailureIsAtomic)
{
	G g; g.configure(config(),false); auto f=frame(); f.target={{.1f,-.04f,0.f}};
	g.begin(f); g.finish({{0.f,0.f,0.f}},0,true); f.sample+=10000; g.begin(f);
	const auto &r=g.finish({{.2f,NAN,0.f}},3,true);
	EXPECT_NE(r.fault,0); EXPECT_EQ(r.committed_axes,0);
	EXPECT_FLOAT_EQ(g.state()[0],0.f); EXPECT_FLOAT_EQ(g.state()[1],0.f);
}

TEST(VelocityXYIntegration, VerticalPriorityAndVectorLimitFreezeOutwardStates)
{
	PositionControl p; setup(p); auto f=frame(); auto s=target(.2f,-.2f);
	s.acceleration[0]=s.acceleration[1]=0.f; s.acceleration[2]=-30.f;
	ASSERT_TRUE(step(p,f,s)); f.sample+=10000; ASSERT_TRUE(step(p,f,s));
	const auto &d=p.diagnostic(); EXPECT_TRUE(d.constraint_bits&4); EXPECT_TRUE(d.constraint_bits&8);
	EXPECT_EQ(d.committed_axes,3); EXPECT_TRUE(d.sta_flags&G::OutwardFreeze);
	for(int i=0;i<2;++i) { EXPECT_FLOAT_EQ(d.thrust[i],0.f); EXPECT_FLOAT_EQ(d.nu_applied[i],0.f); }
	EXPECT_FLOAT_EQ(d.thrust[2],-1.f);
}

TEST(VelocityXYIntegration, NonzeroTiltLimitAffectsBothAxesWithoutSharingNu)
{
	PositionControl p; setup(p); p.setTiltLimit(.005f); auto f=frame(); auto s=target(.2f,-.1f);
	ASSERT_TRUE(step(p,f,s)); f.sample+=10000; ASSERT_TRUE(step(p,f,s));
	const auto &d=p.diagnostic(); EXPECT_TRUE(d.constraint_bits&1); EXPECT_EQ(d.committed_axes,3);
	EXPECT_GT(d.thrust[0],0.f); EXPECT_LT(d.thrust[1],0.f);
	EXPECT_FLOAT_EQ(d.nu_applied[0],0.f); EXPECT_FLOAT_EQ(d.nu_applied[1],0.f);
}

TEST(VelocityXYIntegration, ZPidAndHteUnchangedForMatchedHorizontalDemand)
{
	PositionControl p,pid; setup(p); setup(pid); pid.configureVelocityControl(0,0,false);
	auto f=frame(); auto s=target(0.f,0.f); s.vz=.03f;
	for(int i=0;i<200;++i) {
		if(i==100) { p.updateHoverThrust(.55f); pid.updateHoverThrust(.55f); }
		ASSERT_TRUE(step(p,f,s)); ASSERT_TRUE(step(pid,f,s));
		EXPECT_FLOAT_EQ(p.diagnostic().a_req[2],pid.diagnostic().a_req[2]);
		EXPECT_FLOAT_EQ(p.diagnostic().thrust[2],pid.diagnostic().thrust[2]); f.sample+=10000;
	}
}

TEST(VelocityXYIntegration, YArmedChangePendingCancelAndDisarmApply)
{
	PositionControl p; setup(p); auto f=frame(); auto s=target(); ASSERT_TRUE(step(p,f,s));
	auto c=config(); c.gains[1].lambda1=2.f; p.configureVelocityEsta(c,true);
	f.sample+=10000; ASSERT_TRUE(step(p,f,s)); EXPECT_TRUE(p.diagnostic().config_pending);
	EXPECT_NEAR(p.diagnostic().a_sta[1],-.3f,1e-6f);
	p.configureVelocityEsta(config(),true); f.sample+=10000; ASSERT_TRUE(step(p,f,s)); EXPECT_FALSE(p.diagnostic().config_pending);
	f.armed=false; f.sample+=10000; ASSERT_TRUE(step(p,f,s));
	p.configureVelocityEsta(c,false); p.configureVelocityControl(1,3,false);
	f=frame(f.sample+10000); ASSERT_TRUE(step(p,f,s)); f.sample+=10000; ASSERT_TRUE(step(p,f,s));
	EXPECT_NEAR(p.diagnostic().a_sta[1],-.4f,1e-6f);
}

TEST(VelocityXYIntegration, MasksOneThreePidAndSevenReject)
{
	PositionControl p; setup(p); auto c=config();
	for(int axes:{1,3,0,3,1,3}) {
		c.axes=axes?axes:3; p.configureVelocityEsta(c,false); p.configureVelocityControl(axes?1:0,axes,false);
		EXPECT_EQ(p.velocitySelection().effectiveAxes(),axes); EXPECT_EQ(p.velocitySelection().reject(),0);
	}
	p.configureVelocityControl(1,1,true); EXPECT_TRUE(p.velocitySelection().pending()); EXPECT_EQ(p.velocitySelection().effectiveAxes(),3);
	p.configureVelocityControl(1,3,true); EXPECT_FALSE(p.velocitySelection().pending());
	p.configureVelocityControl(1,7,false); EXPECT_NE(p.velocitySelection().reject(),0); EXPECT_EQ(p.velocitySelection().effectiveAxes(),3);
	c.axes=7; p.configureVelocityEsta(c,false); p.configureVelocityControl(1,7,false); EXPECT_NE(p.velocitySelection().reject(),0);
}

TEST(VelocityXYIntegration, GroundContactDisarmAndReentryResetBothStates)
{
	for(int reason=0;reason<5;++reason) {
		PositionControl p; setup(p); auto f=frame(); auto s=target(); ASSERT_TRUE(step(p,f,s));
		f.sample+=10000; ASSERT_TRUE(step(p,f,s)); EXPECT_NE(p.diagnostic().nu_applied[1],0.f);
		if(reason==0) { f.armed=false; } if(reason==1) { f.contact=true; } if(reason==2) { f.landed=true; }
		if(reason==3) { f.enabled=false; } if(reason==4) { f.flying=false; }
		f.sample+=10000; ASSERT_TRUE(step(p,f,s));
		for(int i=0;i<2;++i) { EXPECT_FLOAT_EQ(p.diagnostic().nu_applied[i],0.f); }
		f=frame(f.sample+10000); ASSERT_TRUE(step(p,f,s)); EXPECT_EQ(p.diagnostic().committed_axes,0);
		f.sample+=10000; ASSERT_TRUE(step(p,f,s)); EXPECT_NEAR(p.diagnostic().nu_applied[0],.002f,1e-7f);
		EXPECT_NEAR(p.diagnostic().nu_applied[1],-.003f,1e-7f);
	}
}

TEST(VelocityXYIntegration, SmoothZeroAreaBoundedWaveformAndOldXRegression)
{
	double sums[3][2]{}; float highs[3][2]{}, lows[3][2]{};
	for(int k=0;k<=64000;++k) {
		float x,y,t=k*.001f; VelocityXYDiagnosticExcitation::waveform(t,x,y);
		EXPECT_LE(hypotf(x,y),.200001f);
		if(t<=32.f) { EXPECT_FLOAT_EQ(x,VelocityDiagnosticExcitation::waveform(t)); }
		const int w=t<32.f?0:t<48.f?1:2;
		float v[2]{x,y}; for(int i=0;i<2;++i) { sums[w][i]+=static_cast<double>(v[i])*.001; highs[w][i]=fmaxf(highs[w][i],v[i]); lows[w][i]=fminf(lows[w][i],v[i]); }
	}
	for(auto &sum:sums) { for(double v:sum) { EXPECT_NEAR(v,0.,2e-6); } }
	EXPECT_GT(highs[0][0],.1f); EXPECT_LT(lows[0][0],-.1f); EXPECT_GT(highs[1][1],.1f); EXPECT_LT(lows[1][1],-.1f);
	for(int i=0;i<2;++i) { EXPECT_GT(highs[2][i],.07f); EXPECT_LT(lows[2][i],-.07f); }
	for(float t:{-1.f,0.f,32.f,48.f,64.f,INFINITY,NAN}) { float x,y; VelocityXYDiagnosticExcitation::waveform(t,x,y); EXPECT_NEAR(x,0.f,1e-6f); EXPECT_NEAR(y,0.f,1e-6f); }
}

TEST(VelocityXYIntegration, IndependentTwoAxisObjectWithLagAndCoupling)
{
	for(double gain:{.8,1.,1.2}) {
		PositionControl p; setup(p); auto f=frame(); double v[2]{}, a[2]{}, motor[2]{}, sums[2]{}; double t=0.;
		for(int k=0;k<7000;++k) {
			const double h=k%2?.012:.008; float x,y; VelocityXYDiagnosticExcitation::waveform(t,x,y);
			ASSERT_TRUE(step(p,f,target(x,y),Vector3f(v[0],v[1],0.f)));
			const auto &d=p.diagnostic(); double next[2]{};
			for(int i=0;i<2;++i) {
				const double demand=static_cast<double>(d.thrust[i])*9.80665/.5;
				a[i]=demand+(a[i]-demand)*exp(-h/.08);
				next[i]=a[i]*h+(motor[i]-a[i])*.03*(1.-exp(-h/.03));
				motor[i]=a[i]+(motor[i]-a[i])*exp(-h/.03);
				sums[i]+=static_cast<double>(d.s[i])*static_cast<double>(d.s[i])*h; EXPECT_LE(fabsf(d.nu_applied[i]),.400001f);
			}
			v[0]+=gain*(next[0]+.05*next[1])+.02*h; v[1]+=gain*(next[1]-.05*next[0])-.015*h;
			EXPECT_LT(fabs(v[0]),1.); EXPECT_LT(fabs(v[1]),1.); t+=h; f.sample+=k%2?12000:8000;
		}
		for(double sum:sums) { EXPECT_LT(sqrt(sum/t),.08); }
	}
}
