// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>
#include "VelocityAxisAblationTask.hpp"
#include "PositionControl.hpp"

TEST(VelocityAblationTask, IndependentPositionDerivativesAndIntegral)
{
	const double pi=acos(-1.);
	auto position=[pi](double t) { return .1*pow(sin(pi*t/64.),4)*sin(2*pi*t/32.); };
	double integral=0., previous=0.;
	for(int k=0;k<=64000;++k) {
		float t=k*.001f; const auto z=VelocityAxisAblationTask::vertical(t);
		EXPECT_LE(fabsf(z.p),.1f); EXPECT_LE(fabsf(z.v),.04f); EXPECT_LE(fabsf(z.a),.02f);
		if(k && k<64000) {
			const double h=.001,time=t,p=position(time);
			EXPECT_NEAR(z.p,p,1e-7); EXPECT_NEAR(z.v,(position(time+h)-position(time-h))/(2*h),1e-7);
			EXPECT_NEAR(z.a,(position(time+h)-2*p+position(time-h))/(h*h),1e-7);
		}
		if(k) { integral+=(double(z.v)+previous)*.0005; }
		previous=z.v;
	}
	EXPECT_NEAR(integral,0.,1e-7);
	for(float t:{-1.f,0.f,64.f,65.f,NAN,INFINITY}) {
		auto z=VelocityAxisAblationTask::vertical(t); EXPECT_FLOAT_EQ(z.p+z.v+z.a,0.f);
	}
}

TEST(VelocityAblationTask, HorizontalUnchangedOneFeedforwardFreshCacheAndHeading)
{
	vehicle_local_position_setpoint_s base{}; base.x=2.f; base.y=-1.f; base.z=-2.5f;
	base.vx=.01f; base.vy=NAN; base.vz=.02f; base.acceleration[2]=.03f; base.yaw=1.5f;
	for(int k=0;k<6400;++k) {
		auto h=base,v=base; float t=k*.01f; VelocityResearchTask::apply(h,VelocityResearchTask::evaluate(6,t));
		VelocityAxisAblationTask::apply(v,t); auto z=VelocityAxisAblationTask::vertical(t);
		EXPECT_FLOAT_EQ(v.x,h.x); EXPECT_FLOAT_EQ(v.y,h.y); EXPECT_FLOAT_EQ(v.vx,h.vx); EXPECT_FLOAT_EQ(v.vy,h.vy);
		EXPECT_FLOAT_EQ(v.acceleration[0],h.acceleration[0]); EXPECT_FLOAT_EQ(v.acceleration[1],h.acceleration[1]);
		EXPECT_FLOAT_EQ(v.yaw,h.yaw); EXPECT_FLOAT_EQ(v.yawspeed,h.yawspeed);
		EXPECT_FLOAT_EQ(v.z,base.z+z.p); EXPECT_FLOAT_EQ(v.vz,base.vz+z.v); EXPECT_FLOAT_EQ(v.acceleration[2],base.acceleration[2]+z.a);
	}
	base.vz=base.acceleration[2]=NAN; auto copy=base; VelocityAxisAblationTask::apply(copy,20.f);
	auto z=VelocityAxisAblationTask::vertical(20.f); EXPECT_FLOAT_EQ(copy.vz,z.v); EXPECT_FLOAT_EQ(copy.acceleration[2],z.a);
	EXPECT_TRUE(std::isnan(base.vz)); EXPECT_FLOAT_EQ(base.z,-2.5f);
}

class VelocityAblationModel : public ::testing::TestWithParam<int> {};
INSTANTIATE_TEST_SUITE_P(AllMasks,VelocityAblationModel,::testing::Values(0,1,2,3,4,5,6,7));
TEST_P(VelocityAblationModel, BothTasksPositionPWithIndependentLaggedPlant)
{
	using matrix::Vector3f; const int axes=GetParam();
	for(int vertical=0;vertical<2;++vertical) {
		PositionControl c; c.setPositionGains(Vector3f(.95f,.95f,1.f));
		c.setVelocityGains(Vector3f(2.16f,2.16f,4.f),Vector3f(.48f,.48f,2.f),Vector3f(.24f,.24f,0.f));
		c.setVelocityLimits(12.f,3.f,.55f); c.setThrustLimits(.12f,1.f); c.setTiltLimit(.785398f); c.setHoverThrust(.5f);
		StaVelocityProtection::Config config{}; config.axes=axes;
		for(int i=0;i<3;++i) { config.gains[i]={i==2?2.f:.5f,i==2?1.f:.1f}; config.nu_limit[i]=i==2?4.f:.4f; config.acceleration_limit[i]=i==2?6.f:.8f; }
		c.configureVelocityEsta(config,false); c.configureVelocityControl(axes?1:0,axes,false);
		StaVelocityProtection::Frame f{}; f.sample=1000000; f.armed=f.enabled=f.flying=true; f.landed=f.contact=false;
		double p[3]{0.,0.,-2.5},v[3]{},attitude[3]{},actuator[3]{},square[3]{};
		for(int k=0;k<9000;++k) {
			const double h=k%2?.008:.012; f.sample+=static_cast<uint64_t>(h*1e6);
			vehicle_local_position_setpoint_s sp{}; sp.z=-2.5f;
			const float t=k*.01f-12.f;
			if(vertical) { VelocityAxisAblationTask::apply(sp,t); } else { VelocityResearchTask::apply(sp,VelocityResearchTask::evaluate(6,t)); }
			c.setVelocityFrame(f); c.setInputSetpoint(sp); c.setState({Vector3f(p[0],p[1],p[2]),Vector3f(v[0],v[1],v[2]),Vector3f(actuator[0],actuator[1],actuator[2]),0.f});
			ASSERT_TRUE(c.update(h)); auto d=c.diagnostic();
			if(k>1) { ASSERT_EQ(d.committed_axes,axes); ASSERT_EQ(d.pid_axes,7^axes); }
			for(int i=0;i<3;++i) {
				const double mapped=double(d.thrust[i])*9.80665/.5+(i==2?9.80665:0.);
				attitude[i]+=(1.-exp(-h/.04))*(mapped-attitude[i]);
				actuator[i]+=(1.-exp(-h/.03))*(attitude[i]-actuator[i]);
				v[i]+=h*(actuator[i]+(i==1?-.004:.003)); p[i]+=h*v[i];
				ASSERT_TRUE(std::isfinite(v[i])); ASSERT_LT(fabs(v[i]),.6);
				if(t>=0.f && t<64.f) { const double e=v[i]-double(d.v_sp[i]); square[i]+=e*e; }
			}
			ASSERT_LT(hypot(p[0],p[1]),2.); ASSERT_GT(-p[2],1.5); ASSERT_LT(-p[2],3.5);
		}
		for(int i=0;i<3;++i) { EXPECT_LT(sqrt(square[i]/6400),.1); }
	}
}
