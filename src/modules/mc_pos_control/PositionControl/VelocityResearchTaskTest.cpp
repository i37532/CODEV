// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>
#include "VelocityResearchTask.hpp"
#include "VelocityDiagnosticExcitation.hpp"
#include <uORB/topics/vehicle_local_position_setpoint.h>

TEST(VelocityResearchTask, EndpointsDisabledAndHover)
{
	for (int mode=0;mode<=8;++mode) {
		for(float t : {-1.f,0.f,64.f,65.f,NAN,INFINITY}) {
			auto o=VelocityResearchTask::evaluate(mode,t);
			EXPECT_FLOAT_EQ(o.p[0]+o.p[1]+o.v[0]+o.v[1]+o.a[0]+o.a[1]+o.yaw+o.yaw_rate,0.f);
		}
	}
	for(float t : {1.f,16.f,32.f,63.f}) { EXPECT_FLOAT_EQ(VelocityResearchTask::evaluate(5,t).p[0],0.f); }
}

TEST(VelocityResearchTask, IndependentDoublePositionDerivatives)
{
	const double pi=acos(-1.);
	auto position=[pi](double t,int axis) { return (axis==0?.5:.25)*pow(sin(pi*t/64),4)*sin((axis+1)*2*pi*t/32); };
	for(int n=1;n<640;++n) {
		const float t=n*.1f; const auto o=VelocityResearchTask::evaluate(7,t);
		for(int axis=0;axis<2;++axis) {
			const double time=static_cast<double>(t), h=.001;
			const double p=position(time,axis), v=(position(time+h,axis)-position(time-h,axis))/(2*h);
			const double a=(position(time+h,axis)-2*p+position(time-h,axis))/(h*h);
			EXPECT_NEAR(static_cast<double>(o.p[axis]),p,1e-6);
			EXPECT_NEAR(static_cast<double>(o.v[axis]),v,1e-6);
			EXPECT_NEAR(static_cast<double>(o.a[axis]),a,1e-6);
		}
	}
}

TEST(VelocityResearchTask, BoundedSameTranslationAndSmoothEndpoints)
{
	for(int n=0;n<=6400;++n) {
		auto a=VelocityResearchTask::evaluate(6,n*.01f), b=VelocityResearchTask::evaluate(7,n*.01f);
		for(int i=0;i<2;++i) { EXPECT_FLOAT_EQ(a.p[i],b.p[i]); EXPECT_FLOAT_EQ(a.v[i],b.v[i]); EXPECT_FLOAT_EQ(a.a[i],b.a[i]); }
		EXPECT_LE(hypotf(a.p[0],a.p[1]),.56f); EXPECT_LE(hypotf(a.v[0],a.v[1]),.18f);
		EXPECT_LE(hypotf(a.a[0],a.a[1]),.08f); EXPECT_LE(fabsf(b.yaw),.524f); EXPECT_LE(fabsf(b.yaw_rate),.16f);
		EXPECT_FLOAT_EQ(a.yaw,0.f);
	}
	for(float t : {.0001f,63.9999f}) { auto a=VelocityResearchTask::evaluate(7,t); EXPECT_LT(fabsf(a.a[0])+fabsf(a.a[1]),1e-7f); }
}

TEST(VelocityResearchTask, FeedforwardOnceNedIndependentOfHeadingAndZUnchanged)
{
	vehicle_local_position_setpoint_s sp{}; sp.x=3.f; sp.y=-2.f; sp.z=-2.5f; sp.vx=.03f; sp.vy=NAN;
	sp.vz=.1f; sp.acceleration[0]=.01f; sp.acceleration[1]=NAN; sp.acceleration[2]=-.02f; sp.yaw=3.1f; sp.yawspeed=.1f;
	const auto original=sp; const auto o=VelocityResearchTask::evaluate(7,20.f); VelocityResearchTask::apply(sp,o);
	EXPECT_FLOAT_EQ(sp.x,original.x+o.p[0]); EXPECT_FLOAT_EQ(sp.y,original.y+o.p[1]); EXPECT_FLOAT_EQ(sp.z,original.z);
	EXPECT_FLOAT_EQ(sp.vx,original.vx+o.v[0]); EXPECT_FLOAT_EQ(sp.vy,o.v[1]); EXPECT_FLOAT_EQ(sp.vz,original.vz);
	EXPECT_FLOAT_EQ(sp.acceleration[0],original.acceleration[0]+o.a[0]); EXPECT_FLOAT_EQ(sp.acceleration[1],o.a[1]);
	EXPECT_FLOAT_EQ(sp.acceleration[2],original.acceleration[2]); EXPECT_LE(fabsf(sp.yaw),3.141593f);
	auto other=original; other.yaw=-1.f; VelocityResearchTask::apply(other,o); EXPECT_FLOAT_EQ(sp.x,other.x); EXPECT_FLOAT_EQ(sp.vy,other.vy);
}

TEST(VelocityResearchTask, GuardedClockGateAbortAndRearm)
{
	VelocityDiagnosticExcitation clock; uint64_t t=1000000; clock.update(t,false,false);
	for(int n=0;n<8000;++n) { t+=n%2?12000:8000; clock.update(t,true,true); ASSERT_EQ(clock.fault(),0); }
	EXPECT_GT(clock.time(),64.f); clock.update(t+8000,true,false); EXPECT_EQ(clock.fault(),2);
	clock.update(t+16000,true,true); EXPECT_EQ(clock.fault(),2);
	clock.update(t+24000,false,false); EXPECT_EQ(clock.fault(),0); clock.update(t+32000,true,true); EXPECT_FLOAT_EQ(clock.time(),-12.f);
	clock.abort(); EXPECT_NE(clock.fault()&4,0);
}
