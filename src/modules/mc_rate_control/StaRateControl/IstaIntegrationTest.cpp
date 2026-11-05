// SPDX-License-Identifier: BSD-3-Clause
#include "StaAxesApplication.hpp"
#include "../RateControl/RateControlDispatcher.hpp"
#include "../../mc_att_control/AttitudeControl/ResearchPulse.hpp"
#include <gtest/gtest.h>
#include <cmath>

namespace
{
using G = StaProtection;
G::Config config(int mode = 2, int axes = 7)
{
	G::Config c; c.mode = mode; c.axes = axes; c.c_limit = .15f;
	c.gains = {{{2.2f,.05f,130.575283f},{2.4f,.08f,112.763533f},{1.5f,.02f,34.582326f}}};
	c.nu_limit = {{3.f,3.f,3.f}}; return c;
}
G::Frame frame(uint64_t t, bool armed = true)
{
	G::Frame f; f.sample = t; f.armed = armed; f.rate_enabled = true;
	f.experiment_active = true; f.landed = !armed; f.maybe_landed = !armed; return f;
}
G::Feedback fb(uint16_t bits = 1) { return {1000000,1004000,bits}; }
void start(G &g, const G::Config &c)
{
	g.begin(c, frame(1000000, false)); g.begin(c, frame(1004000));
}
}

TEST(IstaIntegration, CapabilityModesMasksAndArmedDeferral)
{
	for (int mode : {0,1,2}) {
		for (int mask = 0; mask <= 7; ++mask) {
			ControllerSelection s; const auto c = config(mode, mask);
			const bool ready = StaAxesApplication::ready(true, c);
			EXPECT_FALSE(StaAxesApplication::ready(false, c));
			s.select(mode, mask, false, ready && mode == 1, ready && mode == 2);
			const bool accepted = mode == 0 || mask == 1 || mask == 3 || mask == 7;
			EXPECT_EQ(s.status().request_status, accepted ? ControllerSelection::Accepted : ControllerSelection::Unsupported);
			EXPECT_EQ(s.status().effective_mode, accepted ? mode : 0);
			if (mode && accepted) {
				s.select(0, 0, true); EXPECT_EQ(s.status().effective_mode, mode); EXPECT_TRUE(s.status().pending);
				s.select(0, 0, false); EXPECT_EQ(s.status().effective_mode, 0); EXPECT_FALSE(s.status().pending);
			}
		}
	}
}

TEST(IstaIntegration, IdealCandidatesAxesIsolationAndMapping)
{
	for (int mask : {1,3,7}) {
		G g; auto c = config(2, mask); start(g,c); IstaRateControl ideal;
		for (size_t i = 0; i < 3; ++i) { ideal.setParameters(i,c.gains[i]); }
		const std::array<float,3> rates{{.1f,-.1f,.07f}};
		const auto out = g.step(rates, {}, fb()); ASSERT_TRUE(out.valid);
		for (size_t i = 0; i < 3; ++i) {
			if (mask & (1<<i)) {
				const auto r = ideal.update(i,rates[i],0.f,g.rawDt()); ASSERT_TRUE(r.valid());
				EXPECT_FLOAT_EQ(out.a[i],r.a); EXPECT_FLOAT_EQ(out.nu_candidate[i],r.nu_next);
				EXPECT_FLOAT_EQ(out.nu[i],r.nu_next); EXPECT_FLOAT_EQ(out.c_applied[i],r.c_raw);
				EXPECT_FLOAT_EQ(out.xi[i],r.xi); EXPECT_FLOAT_EQ(out.virtual_s[i],r.virtual_s);
			} else { EXPECT_EQ(out.nu[i],0.f); EXPECT_EQ(out.branch[i],255); EXPECT_TRUE(std::isnan(out.xi[i])); }
		}
		EXPECT_FALSE(g.step(rates,{},fb()).valid);
	}
}

TEST(IstaIntegration, BothSaturationDirectionsAndConstrainedOutput)
{
	for (size_t axis = 0; axis < 3; ++axis) {
		for (float sign : {-1.f,1.f}) {
			G g; auto c = config(); start(g,c); std::array<float,3> rate{}; rate[axis]=sign*.2f;
			const uint16_t bit = 1 << (sign > 0.f ? 4 + 2*axis : 3 + 2*axis);
			const auto out = g.step(rate,{},fb(1|bit)); ASSERT_TRUE(out.valid);
			EXPECT_NE(out.limits[axis] & G::MixerFreeze,0); EXPECT_EQ(out.nu[axis],0.f);
			EXPECT_NE(out.nu_candidate[axis],0.f);
			EXPECT_FLOAT_EQ(out.a_protected[axis],out.a[axis]-out.nu_candidate[axis]);
			EXPECT_FLOAT_EQ(out.c_applied[axis],out.a_protected[axis]/c.gains[axis].g);
			G opposite; start(opposite,c);
			const auto free = opposite.step(rate,{},fb(1|(1 << (sign > 0.f ? 3+2*axis : 4+2*axis))));
			ASSERT_TRUE(free.valid); EXPECT_EQ(free.limits[axis],0); EXPECT_EQ(free.nu[axis],free.nu_candidate[axis]);
		}
	}
}

TEST(IstaIntegration, InvalidFeedbackNuLimitOutputLimitAndGroundFreeze)
{
	for (int type = 0; type < 4; ++type) {
		G g; auto c=config();
		if (type==1) { c.nu_limit[0]=.00001f; }
		if (type==2) { c.c_limit=.00001f; }
		start(g,c);
		if (type==3) { auto f=frame(1008000); f.maybe_landed=true; g.begin(c,f); }
		const auto out=g.step({.2f,0.f,0.f},{},type==0 ? fb(0) : fb(),true);
		ASSERT_TRUE(out.valid);
		if (type==0 || type==2 || type==3) { EXPECT_EQ(out.nu[0],0.f); }
		if (type==0) { EXPECT_NE(out.limits[0]&G::FeedbackInvalid,0); }
		if (type==1) { EXPECT_FLOAT_EQ(out.nu[0],-.00001f); EXPECT_NE(out.limits[0]&G::NuLimit,0); }
		if (type==2) { EXPECT_LE(fabsf(out.c_applied[0]),c.c_limit); EXPECT_NE(out.limits[0]&G::OutputLimit,0); }
		if (type==3) { EXPECT_FALSE(out.updated); }
		EXPECT_NE(out.nu[0],out.nu_candidate[0]);
		EXPECT_FLOAT_EQ(out.a_protected[0],out.a[0]+(out.nu[0]-out.nu_candidate[0]));
	}
}

TEST(IstaIntegration, NoStaleStateAcrossAlgorithmsAndDisarmReload)
{
	G g; auto c=config(); start(g,c); ASSERT_TRUE(g.step({.2f,-.2f,.1f},{},fb()).valid);
	const auto state=g.state(); auto changed=config(1); changed.gains[0].lambda1=2.5f;
	g.begin(changed,frame(1008000)); EXPECT_TRUE(g.pending()); EXPECT_EQ(g.config().mode,2); EXPECT_EQ(g.state(),state);
	g.begin(c,frame(1012000)); EXPECT_FALSE(g.pending()); EXPECT_EQ(g.state(),state);
	for (int mode : {1,2,0,2,1,2}) {
		c=config(mode,mode ? 7 : 0); g.begin(c,frame(1020000,false));
		for (float nu:g.state()) { EXPECT_EQ(nu,0.f); }
		if (!mode) { continue; }
		G fresh; fresh.begin(c,frame(1020000,false));
		g.begin(c,frame(1024000)); fresh.begin(c,frame(1024000));
		const auto a=g.step({.2f,-.2f,.1f},{},fb()), b=fresh.step({.2f,-.2f,.1f},{},fb());
		ASSERT_TRUE(a.valid); ASSERT_TRUE(b.valid); EXPECT_EQ(a.c_raw,b.c_raw); EXPECT_EQ(a.nu,b.nu);
	}
}

TEST(IstaIntegration, FaultsAreAtomicLatchAndNeverFallbackToIdlePid)
{
	for (int fault=0; fault<3; ++fault) {
		G g; auto c=config(); start(g,c); ASSERT_TRUE(g.step({.1f,.1f,.1f},{},fb()).valid);
		const auto before=g.state(); auto f=frame(fault==0 ? 1004000 : 1008000);
		if (fault==1) { f.measurement_valid=false; }
		g.begin(c,f); auto rate=std::array<float,3>{{.1f,.1f,.1f}};
		if (fault==2) { rate[2]=NAN; }
		const auto out=g.step(rate,{},fb()); EXPECT_FALSE(out.valid); EXPECT_TRUE(g.abortRequested());
		EXPECT_EQ(before,g.state()); EXPECT_FALSE(g.acknowledge());
		std::array<float,3> command{}; EXPECT_FALSE(StaAxesApplication::apply(7,true,out,{},command));
		g.begin(c,frame(1012000,false)); ASSERT_TRUE(g.acknowledge());
		for (float nu:g.state()) { EXPECT_EQ(nu,0.f); }
	}
	RateControlDispatcher d; d.select(2,7,false,false,true); EXPECT_FALSE(d.pidRequired());
	const auto seq=d.pidUpdateSequence(); const auto result=d.update({},{},{},.004f,false);
	EXPECT_TRUE(std::isnan(result(0))); EXPECT_EQ(d.pidUpdateSequence(),seq);
	d.resetIntegral(); d.select(0,0,false); EXPECT_TRUE(d.pidRequired());
	const auto pid=d.update({},{},{},.004f,false); EXPECT_EQ(pid(0),0.f); EXPECT_EQ(d.pidUpdateSequence(),seq+1);
}

TEST(IstaIntegration, IndependentCoupledLaggedPlantBeforeFlight)
{
	for (float pitch_l1 : {2.4f,2.f}) {
	for (double mismatch : {.8,1.,1.2}) {
		G g; auto c=config(); c.gains[1].lambda1=pitch_l1; g.begin(c,frame(1000000,false));
		double angle[3]{}, rate[3]{}, accel[3]{};
		for (int k=1;k<=15000;++k) {
			std::array<float,3> measured{},sp{};
			for (int i=0;i<3;++i) {
				measured[i]=static_cast<float>(rate[i]);
				sp[i]=static_cast<float>(-(i==2 ? 2.8 : 6.5)*angle[i])+ResearchPulse::threeAxis(.004f*k-15.f,i,false);
			}
			g.begin(c,frame(1000000+k*4000)); const auto out=g.step(measured,sp,fb()); ASSERT_TRUE(out.valid);
			const double command[3]{out.c_applied[0],out.c_applied[1],out.c_applied[2]};
			const double target[3]{130.575283*command[0]+19.039183*command[2],112.763533*command[1]-.484,
					      -.067051*command[0]+34.582326*command[2]};
			for (int i=0;i<3;++i) {
				accel[i]+=(mismatch*target[i]-accel[i])*(1.-exp(-.004/.025));
				rate[i]+=.004*accel[i]; angle[i]+=.004*rate[i];
				ASSERT_TRUE(std::isfinite(rate[i])); ASSERT_LT(fabs(rate[i]),1.); ASSERT_LT(fabs(angle[i]),.261799);
			}
		}
		for (double a:angle) { EXPECT_LT(fabs(a),.01); }
	}
	}
}
