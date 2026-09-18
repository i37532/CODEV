// SPDX-License-Identifier: BSD-3-Clause
#include "ControlDecimation.hpp"
#include "../RateControl/RateControlDispatcher.hpp"
#include <gtest/gtest.h>
#include <cstring>

TEST(ControlDecimation, ValidRequestsDeferredAndCancelled)
{
	ControlDecimation d;
	for (int v : {0,3,5,-1}) { EXPECT_FALSE(d.configure(v,false)); EXPECT_FALSE(d.valid()); EXPECT_EQ(d.divisor(),1); }
	EXPECT_TRUE(d.configure(4,false)); d.commit(1000,{{1.f,2.f,3.f}});
	EXPECT_FALSE(d.configure(2,true)); EXPECT_TRUE(d.pending()); EXPECT_EQ(d.divisor(),4); EXPECT_TRUE(d.cached());
	d.configure(4,true); EXPECT_FALSE(d.pending()); EXPECT_TRUE(d.cached());
	EXPECT_TRUE(d.configure(2,false)); EXPECT_FALSE(d.cached());
}

TEST(ControlDecimation, IrregularTimestampsAndRealUpdateCounts)
{
	for (int div : {1,2,4}) {
		ControlDecimation d; d.configure(div,false); uint64_t t=100000,previous=0; int count=0;
		for (int k=0;k<101;++k) {
			t += k%2 ? 3500 : 4500;
			if (d.due(t,.004f)) {
				if (previous) { EXPECT_FLOAT_EQ(d.dt(),float((t-previous)*1e-6f)); }
				d.commit(t,{}); previous=t; ++count;
			}
		}
		EXPECT_EQ(count,1+100/div);
	}
}

TEST(ControlDecimation, HoldNeverRescalesAndThrustIsFresh)
{
	ControlDecimation d; d.configure(4,false); d.commit(100000,{{.1f,-.2f,.3f}});
	for (int k=1;k<4;++k) {
		EXPECT_FALSE(d.due(100000+k*4000,.004f));
		const float thrust=.1f*k; const float scale=1.f+.1f*k; const auto o=d.output(thrust,scale);
		EXPECT_FLOAT_EQ(o[0],.1f*scale); EXPECT_FLOAT_EQ(o[1],-.2f*scale); EXPECT_FLOAT_EQ(o[3],thrust*scale);
	}
	EXPECT_FLOAT_EQ(d.command()[0],.1f); d.reset(); EXPECT_FALSE(d.cached()); EXPECT_TRUE(d.due(116000,.004f));
}

TEST(ControlDecimation, IntervalSaturationAndInvalidFeedback)
{
	ControlDecimation d;
	d.observe({100000,104000,1|8}); d.observe({104000,108000,1|16}); d.observe({108000,112000,1});
	EXPECT_EQ(d.bits(),25); EXPECT_TRUE(d.feedbackValid()); EXPECT_EQ(d.observations(),3u);
	d.observe({1,112000,1}); EXPECT_FALSE(d.feedbackValid()); EXPECT_EQ(d.bits()&1,0);
	d.commit(112000,{}); d.observe({112000,116000,1}); EXPECT_EQ(d.bits(),1); EXPECT_TRUE(d.feedbackValid());
}

TEST(ControlDecimation, LifecycleInvalidatesHoldBeforeTerminationDisarmAndLanding)
{
	for (int event=0;event<6;++event) {
		ControlDecimation d; d.configure(4,false); StaProtection::Frame f;
		f.armed=true; f.rate_enabled=true; f.landed=false; f.maybe_landed=false;
		d.lifecycle(f,false,false); d.commit(100000,{{.1f,.2f,.3f}});
		ASSERT_FALSE(d.due(104000,.004f));
		if (event==0) { f.rate_enabled=false; } // commander termination branch
		if (event==1) { f.armed=false; }
		if (event==2) { f.landed=true; }
		if (event==3) { f.maybe_landed=true; }
		d.lifecycle(f,event==4,event==5); EXPECT_FALSE(d.cached());
		if (f.rate_enabled && event!=5) { EXPECT_TRUE(d.due(108000,.004f)); EXPECT_FLOAT_EQ(d.dt(),.008f); }
	}
}

TEST(ControlDecimation, PidHoldsIntegralAndIntervalSaturation)
{
	for (int div : {2,4}) {
		ControlDecimation d; d.configure(div,false); RateControlDispatcher pid;
		pid.setGains(matrix::Vector3f(.1f,.1f,.1f),matrix::Vector3f(.1f,.1f,.1f),{});
		pid.setIntegratorLimit(matrix::Vector3f(.3f,.3f,.3f));
		for (int k=0;k<21;++k) {
			const uint64_t t=100000+4000*k; rate_ctrl_status_s before{},after{};pid.getRateControlStatus(before);
			d.observe({t,t,uint16_t(k==1 ? 1|8 : 1)});
			if (d.due(t,.004f)) {
				MultirotorMixer::saturation_status sat; sat.value=d.bits();pid.setSaturationStatus(sat);
				const auto u=pid.update({},matrix::Vector3f(.1f,.1f,.1f),{},d.dt(),false);
				pid.getRateControlStatus(after);
				if (k==div) { EXPECT_FLOAT_EQ(before.rollspeed_integ,after.rollspeed_integ); }
				d.commit(t,{{u(0),u(1),u(2)}});
			} else {
				pid.getRateControlStatus(after); EXPECT_FLOAT_EQ(before.rollspeed_integ,after.rollspeed_integ);
			}
		}
		EXPECT_EQ(pid.pidUpdateSequence(),uint32_t(1+20/div));
	}
}

TEST(ControlDecimation, N1PidBitwiseSequenceAndIntegral)
{
	RateControl original; RateControlDispatcher wrapped; ControlDecimation d;
	original.setIntegratorLimit(matrix::Vector3f(.3f,.3f,.3f)); wrapped.setIntegratorLimit(matrix::Vector3f(.3f,.3f,.3f));
	for (int k=0;k<2048;++k) {
		const matrix::Vector3f p(.1f,.12f,.2f), i(.05f,.04f,.03f), gain_d(.01f,.02f,.03f), ff(.03f,.02f,.01f);
		original.setGains(p,i,gain_d); wrapped.setGains(p,i,gain_d);
		original.setFeedForwardGain(ff); wrapped.setFeedForwardGain(ff);
		MultirotorMixer::saturation_status sat; sat.value=uint16_t(k%512);
		original.setSaturationStatus(sat); wrapped.setSaturationStatus(sat);
		if (k%59==0) { original.resetIntegral(); wrapped.resetIntegral(); }
		const matrix::Vector3f rate(sinf(k*.02f),cosf(k*.01f),.1f), sp(.2f,-.3f,.1f), acc(.01f,-.02f,.03f);
		const float h=k%2 ? .0035f : .0045f;
		ASSERT_TRUE(d.due(100000+uint64_t(k)*4000,h));
		const auto a=original.update(rate,sp,acc,h,k%31==0); const auto b=wrapped.update(rate,sp,acc,h,k%31==0);
		for (int axis=0;axis<3;++axis) { const float x=a(axis),y=b(axis); EXPECT_EQ(std::memcmp(&x,&y,sizeof(float)),0); }
		d.commit(100000+uint64_t(k)*4000,{{b(0),b(1),b(2)}});
		rate_ctrl_status_s x{},y{}; original.getRateControlStatus(x); wrapped.getRateControlStatus(y);
		EXPECT_FLOAT_EQ(x.rollspeed_integ,y.rollspeed_integ); EXPECT_FLOAT_EQ(x.pitchspeed_integ,y.pitchspeed_integ);
	}
}

TEST(ControlDecimation, SafetyCheckedDuringHoldForAllModes)
{
	for (int mode : {0,1,2,3}) {
		for (int fault : {0,1,2,3}) {
			StaProtection g; StaProtection::Config c; c.mode=mode; c.axes=mode == 3 ? 1 : (mode ? 7 : 0);
			c.gains={{{2.f,.1f,100.f},{2.f,.1f,100.f},{2.f,.1f,100.f}}}; c.nu_limit={{3.f,3.f,3.f}};
			StaProtection::Frame f; f.sample=100000; f.rate_enabled=true; f.decimated=true; f.experiment_active=mode!=0;
			g.begin(c,f); f.sample+=4000; f.armed=true; f.landed=false; f.maybe_landed=false; g.begin(c,f);
			ASSERT_FALSE(g.abortRequested());
			f.sample += fault==0 ? 0 : fault==1 ? -1000 : fault==2 ? 21000 : 4000;
			if (fault==3) { f.measurement_valid=false; }
			g.begin(c,f); EXPECT_TRUE(g.abortRequested()); EXPECT_FALSE(g.acknowledge());
			f.armed=false; g.begin(c,f); EXPECT_TRUE(g.acknowledge()); EXPECT_FALSE(g.abortRequested());
		}
	}
}

TEST(ControlDecimation, EstaIstaUseMeasuredIntervalAndNoHoldIntegration)
{
	for (int mode : {1,2,3}) {
		for (int div : {2,4}) {
			StaProtection g; StaProtection::Config c; c.mode=mode; c.axes=mode == 3 ? 1 : 7;
			c.gains={{{2.f,.1f,100.f},{2.f,.1f,100.f},{2.f,.1f,100.f}}}; c.nu_limit={{3.f,3.f,3.f}};
			StaProtection::Frame f; f.sample=100000; f.rate_enabled=true; f.experiment_active=true;
			g.begin(c,f); f.armed=true; f.landed=false; f.maybe_landed=false;
			ControlDecimation d; d.configure(div,false); int updates=0;
			for (int k=0;k<41;++k) {
				f.sample+=k%2 ? 3500 : 4500; const auto before=g.state(); g.begin(c,f);
				d.observe({f.sample,f.sample,1});
				if (d.due(f.sample,g.rawDt())) {
					const auto out=g.step({.2f,-.1f,.05f},{},{f.sample,f.sample,d.bits()},true,d.dt());
					ASSERT_TRUE(out.valid); EXPECT_NE(g.state(),before); d.commit(f.sample,out.c_applied); ++updates;
				} else { EXPECT_EQ(g.state(),before); }
			}
			EXPECT_EQ(updates,1+40/div);
		}
	}
}

TEST(ControlDecimation, ScalarClosedLoopBeforeFlight)
{
	// Independent exact ZOH integrator plant at sensor rate, actuator held by N.
	for (int mode : {0,1,2}) {
		for (int div : {1,2,4}) {
			ControlDecimation d; d.configure(div,false); RateControl pid;
			pid.setGains(matrix::Vector3f(.15f,.15f,.15f),matrix::Vector3f(.02f,.02f,.02f),matrix::Vector3f());
			pid.setIntegratorLimit(matrix::Vector3f(.3f,.3f,.3f));
			StaRateControl esta; IstaRateControl ista;
			esta.setParameters(0,{2.2f,.05f,130.f}); ista.setParameters(0,{2.2f,.05f,130.f});
			double rate=.1; double tail_error=0.; uint64_t t=100000;
			for (int k=0;k<6000;++k) {
				const uint64_t us=k%2 ? 3500 : 4500; t+=us;
				if (d.due(t,float(us)*1e-6f)) {
					float command;
					if (mode==0) { command=pid.update(matrix::Vector3f(float(rate),0.f,0.f),{}, {},d.dt(),false)(0); }
					else if (mode==1) { command=esta.update(0,float(rate),0.f,d.dt()).c_raw; }
					else { command=ista.update(0,float(rate),0.f,d.dt()).c_raw; }
					ASSERT_TRUE(std::isfinite(command)); ASSERT_LT(fabsf(command),.15f); d.commit(t,{{command,0.f,0.f}});
				}
				rate+=double(us)*1e-6*(130.*double(d.command()[0])+.01);
				if (k>5000) { tail_error=std::max(tail_error,std::abs(rate)); }
			}
			EXPECT_LT(tail_error,.003) << mode << " div " << div;
		}
	}
}
