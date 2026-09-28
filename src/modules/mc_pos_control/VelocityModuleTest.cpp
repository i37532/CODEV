// SPDX-License-Identifier: BSD-3-Clause
// Real Run() and uORB, stepped synchronously; no simulator/actuator consumers.
#include <gtest/gtest.h>
#define MODULE_NAME "mc_pos_control_test"
#include "MulticopterPositionControl.hpp"
#include <platforms/posix/apps.h>
#include <parameters/param.h>
#include <px4_platform_common/px4_work_queue/WorkQueueManager.hpp>

// No timer callback may invoke Run concurrently with the deterministic inputs.
// All uORB, Run, control, takeoff, filtering and diagnostics remain real.
extern "C" void __wrap_hrt_call_after(hrt_call *, hrt_abstime, hrt_callout, void *) {}
extern "C" void __wrap_hrt_cancel(hrt_call *) {}

class VelocityModuleTestAccess
{
public:
	static void step(MulticopterPositionControl &m) { m.Run(); m.ScheduleClear(); }
	static void fastSpool(MulticopterPositionControl &m) { m._takeoff.setSpoolupTime(.008f); }
	static const vehicle_local_position_setpoint_s &cache(const MulticopterPositionControl &m) { return m._setpoint; }
	static void airborne(MulticopterPositionControl &m, uint64_t t) { m._takeoff.updateTakeoffState(true,false,false,1.f,true,t); }
	static void fallback(MulticopterPositionControl &m, uint64_t t, vehicle_local_position_setpoint_s &sp,
		const PositionControlStates &s) { m.failsafe(t,sp,s,false); }
	static bool failsafe(const MulticopterPositionControl &m) { return m._in_failsafe; }
	static float internalLandSpeed(const MulticopterPositionControl &m) { return m._param_mpc_land_speed.get(); }
	static void recovered(MulticopterPositionControl &m, uint64_t t) { m._failsafe_land_hysteresis.set_state_and_update(false,t); }
	static void invalidateGains(MulticopterPositionControl &m)
	{
		m._control.setVelocityGains(matrix::Vector3f(NAN,NAN,NAN),matrix::Vector3f(),matrix::Vector3f());
	}
	static void selectEsta(MulticopterPositionControl &m)
	{
		m._param_mpc_vc_mode.set(1); m._param_mpc_vc_axes.set(1);
		m._param_mpc_vc_l1_x.set(1.f); m._param_mpc_vc_l2_x.set(.2f);
		m._param_mpc_vc_nu_x.set(.4f); m._param_mpc_vc_a_x.set(.8f);
	}
	static void selectXY(MulticopterPositionControl &m)
	{
		selectEsta(m); m._param_mpc_vc_axes.set(3);
		m._param_mpc_vc_l1_y.set(1.5f); m._param_mpc_vc_l2_y.set(.3f);
		m._param_mpc_vc_nu_y.set(.4f); m._param_mpc_vc_a_y.set(.8f);
	}
	static void changeY(MulticopterPositionControl &m) { m._param_mpc_vc_l1_y.set(2.f); }
	static void selectXYZ(MulticopterPositionControl &m)
	{
		selectXY(m); m._param_mpc_vc_axes.set(7);
		m._param_mpc_vc_l1_z.set(2.f); m._param_mpc_vc_l2_z.set(1.f);
		m._param_mpc_vc_nu_z.set(4.f); m._param_mpc_vc_a_z.set(6.f);
	}
	static void enableXYZExcitation(MulticopterPositionControl &m) { m._param_mpc_vct_test.set(4); }
	static void researchTask(MulticopterPositionControl &m,int task) { m._param_mpc_vct_test.set(task); }
	static void enableXYExcitation(MulticopterPositionControl &m) { m._param_mpc_vct_test.set(3); }
	static void selectZ(MulticopterPositionControl &m)
	{
		m._param_mpc_vc_mode.set(1); m._param_mpc_vc_axes.set(4);
		m._param_mpc_vc_l1_z.set(1.f); m._param_mpc_vc_l2_z.set(.2f);
		m._param_mpc_vc_nu_z.set(2.f); m._param_mpc_vc_a_z.set(3.f);
	}
	static void selectPid(MulticopterPositionControl &m) { m._param_mpc_vc_mode.set(0); m._param_mpc_vc_axes.set(0); }
};

class VelocityTestQueueAnchor : public px4::WorkItem
{
public:
	VelocityTestQueueAnchor() : WorkItem("velocity_test_anchor",px4::wq_configurations::nav_and_controllers) {}
	void Run() override {}
};
static VelocityTestQueueAnchor *queue_anchor = nullptr;

class VelocityModule : public ::testing::Test
{
public:
	static void SetUpTestSuite()
	{
		ASSERT_EQ(px4::WorkQueueManagerStart(),0);
		px4_usleep(20000); // Manager start is asynchronous, no Run callbacks are registered.
		queue_anchor = new VelocityTestQueueAnchor();
	}
	static void TearDownTestSuite()
	{
		delete queue_anchor; queue_anchor=nullptr; px4_usleep(20000);
		EXPECT_EQ(px4::WorkQueueManagerStop(),0);
	}
protected:
	uORB::Publication<vehicle_local_position_s> lp_pub{ORB_ID(vehicle_local_position)};
	uORB::Publication<vehicle_local_position_setpoint_s> target_pub{ORB_ID(trajectory_setpoint)};
	uORB::Publication<vehicle_control_mode_s> mode_pub{ORB_ID(vehicle_control_mode)};
	uORB::Publication<vehicle_land_detected_s> land_pub{ORB_ID(vehicle_land_detected)};
	uORB::Publication<vehicle_constraints_s> limits_pub{ORB_ID(vehicle_constraints)};
	uORB::Publication<sta_rate_ctrl_status_s> rate_pub{ORB_ID(sta_rate_ctrl_status)};
	uORB::Subscription diag_sub{ORB_ID(sta_velocity_ctrl_status)};
	vehicle_local_position_s lp{};
	vehicle_local_position_setpoint_s target{};
	vehicle_control_mode_s mode{};
	vehicle_land_detected_s land{};
	vehicle_constraints_s limits{};
	MulticopterPositionControl *m{nullptr};
	void SetUp() override
	{
		apps_map_type apps; init_app_map(apps); ASSERT_TRUE(apps.empty());
		param_control_autosave(false); param_reset_all();
		m = new MulticopterPositionControl(); VelocityModuleTestAccess::fastSpool(*m);
		lp.timestamp=lp.timestamp_sample=1000000;
		lp.x=5.f; lp.y=-2.f; lp.z=.58f; lp.heading=1.57f;
		lp.xy_valid=lp.z_valid=lp.v_xy_valid=lp.v_z_valid=true;
		target.timestamp=lp.timestamp; target.x=5.f; target.y=-2.f; target.z=.59f;
		target.vx=target.vy=0.f; target.vz=.7f;
		target.yaw=1.57f; target.acceleration[2]=-.08f;
		mode.flag_armed=mode.flag_multicopter_position_control_enabled=mode.flag_control_auto_enabled=true;
		land.landed=land.ground_contact=true;
		limits.speed_xy=5.f; limits.speed_up=3.f; limits.speed_down=1.f; limits.want_takeoff=true;
		ASSERT_TRUE(mode_pub.publish(mode)); ASSERT_TRUE(land_pub.publish(land));
		ASSERT_TRUE(limits_pub.publish(limits)); ASSERT_TRUE(target_pub.publish(target));
	}
	void TearDown() override { delete m; param_reset_all(); }
	sta_velocity_ctrl_status_s step(uint64_t dt=0, bool new_target=false)
	{
		lp.timestamp+=dt; lp.timestamp_sample=lp.timestamp;
		if (new_target) { target.timestamp=lp.timestamp; EXPECT_TRUE(target_pub.publish(target)); }
		sta_rate_ctrl_status_s rate{}; rate.timestamp=hrt_absolute_time(); rate.div_eff=1;
		rate.measurement_valid=rate.output_valid=true; EXPECT_TRUE(rate_pub.publish(rate));
		EXPECT_TRUE(lp_pub.publish(lp)); VelocityModuleTestAccess::step(*m);
		sta_velocity_ctrl_status_s d{}; unsigned reads=0;
		while (reads < 8 && diag_sub.update(&d)) { ++reads; }
		EXPECT_GT(reads,0u); EXPECT_EQ(d.timestamp_sample,lp.timestamp_sample); return d;
	}
};

TEST_F(VelocityModule, V06TrajectoryBeforePositionPAndSingleFeedforward)
{
	VelocityModuleTestAccess::researchTask(*m,7);
	mode.flag_armed=false; ASSERT_TRUE(mode_pub.publish(mode)); step();
	mode.flag_armed=true; ASSERT_TRUE(mode_pub.publish(mode));
	VelocityModuleTestAccess::airborne(*m,lp.timestamp); land.landed=land.ground_contact=false; ASSERT_TRUE(land_pub.publish(land));
	uORB::Publication<vehicle_status_s> status_pub{ORB_ID(vehicle_status)};
	vehicle_status_s status{}; status.nav_state=vehicle_status_s::NAVIGATION_STATE_AUTO_LOITER; ASSERT_TRUE(status_pub.publish(status));
	target.z=lp.z; target.vz=0.f; target.acceleration[0]=.01f; target.acceleration[1]=-.02f; target.acceleration[2]=0.f;
	float peak=0.f;
	for(int k=0;k<8000;++k) {
		const auto d=step(k%2?12000:8000,true); ASSERT_TRUE(d.valid); EXPECT_EQ(d.excitation_fault,0);
		const auto o=VelocityResearchTask::evaluate(7,d.excitation_time);
		EXPECT_FLOAT_EQ(d.p_sp[0],target.x+o.p[0]); EXPECT_FLOAT_EQ(d.p_sp[1],target.y+o.p[1]);
		EXPECT_FLOAT_EQ(d.v_ff[0],target.vx+o.v[0]); EXPECT_FLOAT_EQ(d.a_ff[0],target.acceleration[0]+o.a[0]);
		EXPECT_FLOAT_EQ(d.a_ff[1],target.acceleration[1]+o.a[1]); EXPECT_FLOAT_EQ(d.p_sp[2],target.z);
		EXPECT_NEAR(d.v_sp[0],.95f*o.p[0]+o.v[0],2e-6f);
		EXPECT_FLOAT_EQ(d.excitation+d.excitation_y+d.excitation_z,0.f);
		EXPECT_FLOAT_EQ(VelocityModuleTestAccess::cache(*m).x,target.x); peak=fmaxf(peak,fabsf(o.p[0]));
	}
	EXPECT_GT(peak,.2f);
	status.nav_state=vehicle_status_s::NAVIGATION_STATE_AUTO_LAND; ASSERT_TRUE(status_pub.publish(status));
	const auto d=step(8000,true); EXPECT_EQ(d.excitation_fault,2); EXPECT_FLOAT_EQ(d.p_sp[0],target.x); EXPECT_FLOAT_EQ(d.a_ff[0],target.acceleration[0]);
}

TEST_F(VelocityModule, XYZRealRunHandoverHteAndContact)
{
	VelocityModuleTestAccess::selectXYZ(*m); mode.flag_armed=false; ASSERT_TRUE(mode_pub.publish(mode));
	EXPECT_EQ(step().effective_axes,7);
	mode.flag_armed=true; ASSERT_TRUE(mode_pub.publish(mode));
	VelocityModuleTestAccess::airborne(*m,lp.timestamp); land.landed=land.ground_contact=false; ASSERT_TRUE(land_pub.publish(land));
	target.z=lp.z; target.vz=0.f; target.acceleration[2]=0.f;
	auto d=step(12000,true); ASSERT_TRUE(d.valid); EXPECT_EQ(d.z_phase,2); EXPECT_EQ(d.pid_axes,7);
	for(int k=0;k<100;++k) { ASSERT_TRUE(step(10000,true).valid); }
	target.vx=.1f; target.vy=-.04f; target.vz=.01f; d=step(8000,true);
	ASSERT_TRUE(d.valid); EXPECT_EQ(d.pid_axes,0); EXPECT_EQ(d.active_axes,7); EXPECT_EQ(d.committed_axes,7);
	EXPECT_NEAR(d.nu_applied[0],.0016f,1e-7f); EXPECT_NEAR(d.nu_applied[1],-.0024f,1e-7f); EXPECT_NEAR(d.nu_applied[2],.008f,1e-7f);
	uORB::Publication<hover_thrust_estimate_s> publisher{ORB_ID(hover_thrust_estimate)};
	hover_thrust_estimate_s h{}; h.timestamp=hrt_absolute_time(); h.valid=true; h.hover_thrust=d.hover_thrust+.01f;
	ASSERT_TRUE(publisher.publish(h)); auto after=step(12000,true); ASSERT_TRUE(after.valid);
	EXPECT_NE(after.z_hte_shift,0.f); EXPECT_FLOAT_EQ(after.nu_before[0],d.nu_applied[0]); EXPECT_FLOAT_EQ(after.nu_before[1],d.nu_applied[1]);
	VelocityModuleTestAccess::selectPid(*m); after=step(8000,true); EXPECT_TRUE(after.pending); EXPECT_EQ(after.effective_axes,7);
	VelocityModuleTestAccess::selectXYZ(*m); EXPECT_FALSE(step(12000,true).pending);
	land.ground_contact=true; ASSERT_TRUE(land_pub.publish(land)); d=step(8000,true);
	ASSERT_TRUE(d.valid); EXPECT_EQ(d.z_phase,1); EXPECT_EQ(d.committed_axes,0); EXPECT_FLOAT_EQ(d.a_ff[2],100.f);
}

TEST_F(VelocityModule, XYZResetRetriesCannotPartiallyCommitOrPublish)
{
	VelocityModuleTestAccess::selectXYZ(*m); mode.flag_armed=false; ASSERT_TRUE(mode_pub.publish(mode)); step();
	mode.flag_armed=true; ASSERT_TRUE(mode_pub.publish(mode));
	VelocityModuleTestAccess::airborne(*m,lp.timestamp); land.landed=land.ground_contact=false; ASSERT_TRUE(land_pub.publish(land));
	target.z=lp.z; target.vz=0.f; target.acceleration[2]=0.f;
	ASSERT_TRUE(step(12000,true).valid); ASSERT_TRUE(step(8000,true).valid);
	lp.vz_reset_counter++; lp.delta_vz=.01f; const auto d=step(12000,true);
	EXPECT_EQ(d.pid_calls,2); EXPECT_NE(d.first_fail,0); EXPECT_EQ(d.retry_result,2);
	EXPECT_FALSE(d.valid); EXPECT_EQ(d.committed_axes,0); EXPECT_EQ(d.output_timestamp,0u);
}

TEST_F(VelocityModule, XYZStimulusCompleteRealRunAndAllOutputsClear)
{
	VelocityModuleTestAccess::enableXYZExcitation(*m);
	mode.flag_armed=false; ASSERT_TRUE(mode_pub.publish(mode)); step();
	mode.flag_armed=true; ASSERT_TRUE(mode_pub.publish(mode));
	VelocityModuleTestAccess::airborne(*m,lp.timestamp); land.landed=land.ground_contact=false; ASSERT_TRUE(land_pub.publish(land));
	uORB::Publication<vehicle_status_s> status_pub{ORB_ID(vehicle_status)};
	vehicle_status_s status{}; status.nav_state=vehicle_status_s::NAVIGATION_STATE_AUTO_LOITER; ASSERT_TRUE(status_pub.publish(status));
	target.z=lp.z; target.vz=0.f; target.acceleration[2]=0.f;
	float peaks[3]{};
	for(int k=0;k<8000;++k) {
		const auto d=step(k%2?12000:8000,true); ASSERT_TRUE(d.valid); EXPECT_EQ(d.excitation_fault,0);
		float x,y,z; VelocityXYZDiagnosticExcitation::waveform(d.excitation_time,x,y,z);
		EXPECT_FLOAT_EQ(d.excitation,x); EXPECT_FLOAT_EQ(d.excitation_y,y); EXPECT_FLOAT_EQ(d.excitation_z,z);
		EXPECT_FLOAT_EQ(d.v_sp[0],x); EXPECT_FLOAT_EQ(d.v_sp[1],y); EXPECT_FLOAT_EQ(d.v_sp[2],z);
		peaks[0]=fmaxf(peaks[0],fabsf(x)); peaks[1]=fmaxf(peaks[1],fabsf(y)); peaks[2]=fmaxf(peaks[2],fabsf(z));
	}
	for(float peak:peaks) { EXPECT_GT(peak,.05f); }
	status.nav_state=vehicle_status_s::NAVIGATION_STATE_AUTO_LAND; ASSERT_TRUE(status_pub.publish(status));
	auto d=step(10000,true); EXPECT_EQ(d.excitation_fault,VelocityDiagnosticExcitation::Gate);
	EXPECT_FLOAT_EQ(d.excitation,0.f); EXPECT_FLOAT_EQ(d.excitation_y,0.f); EXPECT_FLOAT_EQ(d.excitation_z,0.f);
	mode.flag_armed=false; ASSERT_TRUE(mode_pub.publish(mode)); EXPECT_EQ(step(10000,true).excitation_fault,0);
}

TEST_F(VelocityModule, XYRealRunIndependentStatesAndArmedYChange)
{
	VelocityModuleTestAccess::selectXY(*m); mode.flag_armed=false; ASSERT_TRUE(mode_pub.publish(mode));
	auto d=step(); ASSERT_EQ(d.effective_axes,3);
	mode.flag_armed=true; ASSERT_TRUE(mode_pub.publish(mode));
	VelocityModuleTestAccess::airborne(*m,lp.timestamp); land.landed=land.ground_contact=false; ASSERT_TRUE(land_pub.publish(land));
	target.z=lp.z; target.vz=0.f; target.acceleration[2]=0.f;
	// Let the original tilt slew limiter leave its zero-angle ground state.
	for(int k=0;k<100;++k) { ASSERT_TRUE(step(10000,true).valid); }
	target.vx=.1f; target.vy=-.04f; d=step(8000,true);
	ASSERT_TRUE(d.valid); EXPECT_EQ(d.committed_axes,3); EXPECT_EQ(d.pid_axes,4); EXPECT_EQ(d.z_phase,0);
	EXPECT_NEAR(d.nu_applied[0],.0016f,1e-7f); EXPECT_NEAR(d.nu_applied[1],-.0024f,1e-7f);
	VelocityModuleTestAccess::changeY(*m); d=step(12000,true); EXPECT_TRUE(d.config_pending);
	EXPECT_NEAR(d.a_sta[1],-.3f-.0024f,1e-6f);
	VelocityModuleTestAccess::selectXY(*m); EXPECT_FALSE(step(8000,true).config_pending);
	mode.flag_armed=false; ASSERT_TRUE(mode_pub.publish(mode)); d=step(12000,true);
	EXPECT_EQ(d.committed_axes,0); EXPECT_FLOAT_EQ(d.nu_applied[0],0.f); EXPECT_FLOAT_EQ(d.nu_applied[1],0.f);
}

TEST_F(VelocityModule, XYStimulusWiringSampleClockAndExitClear)
{
	VelocityModuleTestAccess::enableXYExcitation(*m);
	mode.flag_armed=false; ASSERT_TRUE(mode_pub.publish(mode)); step();
	mode.flag_armed=true; ASSERT_TRUE(mode_pub.publish(mode));
	VelocityModuleTestAccess::airborne(*m,lp.timestamp); land.landed=land.ground_contact=false; ASSERT_TRUE(land_pub.publish(land));
	uORB::Publication<vehicle_status_s> status_pub{ORB_ID(vehicle_status)};
	vehicle_status_s status{}; status.nav_state=vehicle_status_s::NAVIGATION_STATE_AUTO_LOITER; ASSERT_TRUE(status_pub.publish(status));
	target.z=lp.z; target.vz=0.f; target.acceleration[2]=0.f;
	float peak_x=0.f,peak_y=0.f;
	for(int k=0;k<8000;++k) {
		const auto d=step(10000,true); ASSERT_TRUE(d.valid); EXPECT_EQ(d.excitation_fault,0);
		float x,y; VelocityXYDiagnosticExcitation::waveform(d.excitation_time,x,y);
		EXPECT_FLOAT_EQ(d.excitation,x); EXPECT_FLOAT_EQ(d.excitation_y,y);
		EXPECT_FLOAT_EQ(d.v_sp[0],x); EXPECT_FLOAT_EQ(d.v_sp[1],y);
		peak_x=fmaxf(peak_x,fabsf(x)); peak_y=fmaxf(peak_y,fabsf(y));
	}
	EXPECT_GT(peak_x,.1f); EXPECT_GT(peak_y,.1f);
	status.nav_state=vehicle_status_s::NAVIGATION_STATE_AUTO_LAND; ASSERT_TRUE(status_pub.publish(status));
	auto d=step(10000,true); EXPECT_EQ(d.excitation_fault,VelocityDiagnosticExcitation::Gate);
	EXPECT_FLOAT_EQ(d.excitation,0.f); EXPECT_FLOAT_EQ(d.excitation_y,0.f);
	mode.flag_armed=false; ASSERT_TRUE(mode_pub.publish(mode)); d=step(10000,true); EXPECT_EQ(d.excitation_fault,0);
}

TEST_F(VelocityModule, XYResetSameFrameRetryCannotPublishOrPartiallyCommit)
{
	VelocityModuleTestAccess::selectXY(*m); mode.flag_armed=false; ASSERT_TRUE(mode_pub.publish(mode)); step();
	mode.flag_armed=true; ASSERT_TRUE(mode_pub.publish(mode));
	VelocityModuleTestAccess::airborne(*m,lp.timestamp); land.landed=land.ground_contact=false; ASSERT_TRUE(land_pub.publish(land));
	target.z=lp.z; target.vz=0.f; target.vx=.1f; target.vy=-.04f; target.acceleration[2]=0.f;
	ASSERT_TRUE(step(12000,true).valid); ASSERT_TRUE(step(8000,true).valid);
	lp.vxy_reset_counter++; lp.delta_vxy[1]=.01f;
	const auto d=step(12000,true); EXPECT_EQ(d.pid_calls,2); EXPECT_NE(d.first_fail,0);
	EXPECT_EQ(d.retry_result,2); EXPECT_FALSE(d.valid); EXPECT_EQ(d.committed_axes,0); EXPECT_EQ(d.output_timestamp,0u);
}

TEST_F(VelocityModule, PidWithOnlyZCandidateConfiguredHasNoPhantomPending)
{
	VelocityModuleTestAccess::selectZ(*m); VelocityModuleTestAccess::selectPid(*m);
	mode.flag_armed=false; ASSERT_TRUE(mode_pub.publish(mode)); EXPECT_FALSE(step().config_pending);
	mode.flag_armed=true; ASSERT_TRUE(mode_pub.publish(mode));
	for(int k=0;k<20;++k) {
		const auto d=step(k%2?8000:12000,true); ASSERT_TRUE(d.valid);
		EXPECT_EQ(d.effective_mode,0); EXPECT_EQ(d.effective_axes,0); EXPECT_FALSE(d.config_pending);
		EXPECT_EQ(d.first_fail,0); EXPECT_EQ(d.retry_result,0);
	}
}

TEST_F(VelocityModule, ZSelectionRealModuleRampHandoverMixedVelocityAndContact)
{
	VelocityModuleTestAccess::selectZ(*m);
	mode.flag_armed=false; ASSERT_TRUE(mode_pub.publish(mode));
	auto d=step(); EXPECT_EQ(d.effective_axes,4); EXPECT_EQ(d.z_phase,1);
	mode.flag_armed=true; ASSERT_TRUE(mode_pub.publish(mode)); target.z=lp.z; target.vz=0.f;
	d=step(8000,true); EXPECT_EQ(d.committed_axes,0);
	VelocityModuleTestAccess::airborne(*m,lp.timestamp);
	land.landed=land.ground_contact=false; ASSERT_TRUE(land_pub.publish(land));
	d=step(12000,true); ASSERT_TRUE(d.valid); EXPECT_EQ(d.z_phase,2); EXPECT_EQ(d.pid_axes,7);
	d=step(8000,true); ASSERT_TRUE(d.valid); EXPECT_EQ(d.z_phase,3); EXPECT_EQ(d.pid_axes,3); EXPECT_EQ(d.committed_axes,4);
	target.z=NAN; target.vz=.3f; target.acceleration[2]=.02f; lp.vz=.1f; lp.z_deriv=.2f;
	d=step(12000,true); ASSERT_TRUE(d.valid); EXPECT_EQ(d.z_phase,3);
	const float w=.3f/VelocityModuleTestAccess::internalLandSpeed(*m);
	EXPECT_NEAR(d.v[2],.2f*w+.1f*(1.f-w),1e-6f);
	EXPECT_NEAR(d.a_req[2],d.a_sta[2]+.02f,1e-6f);
	land.ground_contact=true; ASSERT_TRUE(land_pub.publish(land)); d=step(8000,true);
	ASSERT_TRUE(d.valid); EXPECT_EQ(d.z_phase,1); EXPECT_EQ(d.committed_axes,0); EXPECT_FLOAT_EQ(d.a_ff[2],100.f);
}

TEST_F(VelocityModule, ZHoverEstimatorUpdateKeepsMappingContinuous)
{
	VelocityModuleTestAccess::selectZ(*m); mode.flag_armed=false; ASSERT_TRUE(mode_pub.publish(mode)); step();
	mode.flag_armed=true; ASSERT_TRUE(mode_pub.publish(mode));
	VelocityModuleTestAccess::airborne(*m,lp.timestamp); land.landed=land.ground_contact=false; ASSERT_TRUE(land_pub.publish(land));
	target.z=lp.z; target.vz=0.f; target.acceleration[2]=0.f;
	ASSERT_TRUE(step(12000,true).valid); auto before=step(8000,true); ASSERT_TRUE(before.valid);
	uORB::Publication<hover_thrust_estimate_s> publisher{ORB_ID(hover_thrust_estimate)};
	hover_thrust_estimate_s h{}; h.timestamp=hrt_absolute_time(); h.valid=true; h.hover_thrust=before.hover_thrust+.01f;
	ASSERT_TRUE(publisher.publish(h)); auto after=step(12000,true); ASSERT_TRUE(after.valid);
	EXPECT_FLOAT_EQ(after.hover_thrust,h.hover_thrust); EXPECT_NE(after.z_hte_shift,0.f);
	EXPECT_NEAR(after.thrust[2],before.thrust[2],1e-6f); EXPECT_EQ(after.pid_axes,3);
}

TEST_F(VelocityModule, ZResetFailsClosedAndSameSampleFailsafeCannotCommit)
{
	VelocityModuleTestAccess::selectZ(*m); mode.flag_armed=false; ASSERT_TRUE(mode_pub.publish(mode)); step();
	mode.flag_armed=true; ASSERT_TRUE(mode_pub.publish(mode));
	VelocityModuleTestAccess::airborne(*m,lp.timestamp); land.landed=land.ground_contact=false; ASSERT_TRUE(land_pub.publish(land));
	target.z=lp.z; target.vz=0.f; target.acceleration[2]=0.f;
	ASSERT_TRUE(step(12000,true).valid); ASSERT_TRUE(step(8000,true).valid);
	lp.vz_reset_counter++; lp.delta_vz=.01f;
	const auto d=step(12000,true);
	EXPECT_EQ(d.pid_calls,2); EXPECT_NE(d.first_fail,0); EXPECT_EQ(d.retry_result,2); EXPECT_FALSE(d.valid);
	EXPECT_EQ(d.committed_axes,0); EXPECT_EQ(d.output_timestamp,0u); EXPECT_TRUE(d.fault);
}

TEST_F(VelocityModule, ZMissingMeasurementNeverPublishesAutomaticPidTakeover)
{
	VelocityModuleTestAccess::selectZ(*m); mode.flag_armed=false; ASSERT_TRUE(mode_pub.publish(mode)); step();
	mode.flag_armed=true; ASSERT_TRUE(mode_pub.publish(mode));
	VelocityModuleTestAccess::airborne(*m,lp.timestamp); land.landed=land.ground_contact=false; ASSERT_TRUE(land_pub.publish(land));
	target.z=lp.z; target.vz=0.f; target.acceleration[2]=0.f;
	ASSERT_TRUE(step(12000,true).valid); lp.v_z_valid=false;
	const auto d=step(8000,true); EXPECT_FALSE(d.valid); EXPECT_EQ(d.output_timestamp,0u); EXPECT_EQ(d.committed_axes,0);
	lp.v_z_valid=true; EXPECT_FALSE(step(12000,true).valid);
}

TEST_F(VelocityModule, FiftyHzTargetHundredHzCallbacksRampWithoutNewTarget)
{
	auto d=step(); EXPECT_TRUE(std::isnan(d.p_sp[2])); EXPECT_FLOAT_EQ(d.a_ff[2],100.f);
	EXPECT_FLOAT_EQ(VelocityModuleTestAccess::cache(*m).z,target.z);
	d=step(8000); EXPECT_EQ(d.takeoff_state,static_cast<uint8_t>(TakeoffState::rampup));
	EXPECT_EQ(d.setpoint_timestamp,1000000u); EXPECT_EQ(d.pid_calls,1); EXPECT_TRUE(d.valid);
	EXPECT_EQ(d.first_fail,0); EXPECT_EQ(d.retry_result,0); EXPECT_EQ(d.excitation_fault,0);
	EXPECT_FLOAT_EQ(d.p_sp[2],target.z); EXPECT_TRUE(std::isnan(d.a_ff[2]));
	for(int k=0;k<40;++k) { d=step(k%2 ? 8000 : 12000,k%2==0); EXPECT_EQ(d.pid_calls,1); EXPECT_EQ(d.first_fail,0); }
}

TEST_F(VelocityModule, LegalDescentCapLimitsLandingWithoutChangingStoredLandParameter)
{
	const param_t down_key = param_find("MPC_Z_VEL_MAX_DN"), land_key = param_find("MPC_LAND_SPEED");
	ASSERT_NE(down_key, PARAM_INVALID); ASSERT_NE(land_key, PARAM_INVALID);
	for (float cap : {1.f, .5f, 1.f}) {
		delete m; m = nullptr;
		float requested_land = .7f;
		ASSERT_EQ(param_set(down_key, &cap), 0); ASSERT_EQ(param_set(land_key, &requested_land), 0);
		m = new MulticopterPositionControl(); VelocityModuleTestAccess::fastSpool(*m);
		EXPECT_FLOAT_EQ(VelocityModuleTestAccess::internalLandSpeed(*m), math::min(cap, .7f));
		float stored_land = 0.f; ASSERT_EQ(param_get(land_key, &stored_land), 0);
		EXPECT_FLOAT_EQ(stored_land, .7f); // no out-of-metadata param write to .5
		land.landed = land.ground_contact = true; ASSERT_TRUE(land_pub.publish(land));
		step(8000, true); VelocityModuleTestAccess::airborne(*m, lp.timestamp);
		land.landed = land.ground_contact = false; ASSERT_TRUE(land_pub.publish(land));
		target.z = NAN; target.vz = .7f; target.acceleration[2] = 0.f;
		target.vx = .1f; lp.z_deriv = .2f; lp.vz = .1f;
		for (float constraint : {1.f, NAN, .4f}) {
			limits.speed_down = constraint; ASSERT_TRUE(limits_pub.publish(limits));
			const auto d = step(12000, true);
			ASSERT_TRUE(d.valid); EXPECT_EQ(d.first_fail, 0); EXPECT_EQ(d.retry_result, 0);
			EXPECT_EQ(d.effective_mode, 0); EXPECT_EQ(d.pid_axes, 7);
			const float expected = math::min(.7f, math::min(cap, std::isfinite(constraint) ? constraint : cap));
			EXPECT_FLOAT_EQ(d.v_sp[2], expected); EXPECT_NEAR(d.v_sp[0], .1f, 1e-6f);
			EXPECT_FLOAT_EQ(d.v[2], .2f); // existing landing mixed-velocity path retained
		}
	}
}

TEST_F(VelocityModule, CommonLandingParametersKeepTargetAboveDetectorIntentBoundary)
{
	delete m; m = nullptr;
	float cap = .55f, land_speed = .6f;
	ASSERT_EQ(param_set(param_find("MPC_Z_VEL_MAX_DN"), &cap), 0);
	ASSERT_EQ(param_set(param_find("MPC_LAND_SPEED"), &land_speed), 0);
	m = new MulticopterPositionControl(); VelocityModuleTestAccess::fastSpool(*m);
	step(8000, true); VelocityModuleTestAccess::airborne(*m, lp.timestamp);
	land.landed = land.ground_contact = false; ASSERT_TRUE(land_pub.publish(land));
	target.z = NAN; target.vz = .6f; target.acceleration[2] = 0.f;
	lp.z_deriv = .2f; lp.vz = .1f;
	const auto d = step(12000, true);
	ASSERT_TRUE(d.valid); EXPECT_EQ(d.first_fail, 0); EXPECT_EQ(d.retry_result, 0);
	EXPECT_EQ(d.effective_mode, 0); EXPECT_EQ(d.pid_axes, 7);
	EXPECT_FLOAT_EQ(d.v_sp[2], cap); EXPECT_GE(d.v_sp[2], .9f * land_speed);
	EXPECT_FLOAT_EQ(d.v[2], .2f); EXPECT_FLOAT_EQ(VelocityModuleTestAccess::internalLandSpeed(*m), cap);
	float stored_land = 0.f; ASSERT_EQ(param_get(param_find("MPC_LAND_SPEED"), &stored_land), 0);
	EXPECT_FLOAT_EQ(stored_land, land_speed);
}

TEST_F(VelocityModule, EstimatorResetsAdjustCacheOnceNotSuppressedCopy)
{
	step(); lp.xy_reset_counter=lp.z_reset_counter=lp.vxy_reset_counter=lp.vz_reset_counter=lp.heading_reset_counter=1;
	lp.delta_xy[0]=2.f; lp.delta_xy[1]=-3.f; lp.delta_z=.4f;
	lp.delta_vxy[0]=.1f; lp.delta_vxy[1]=.2f; lp.delta_vz=.3f; lp.delta_heading=.2f;
	auto d=step(8000); EXPECT_EQ(d.pid_calls,1);
	const auto c=VelocityModuleTestAccess::cache(*m);
	EXPECT_FLOAT_EQ(c.x,7.f); EXPECT_FLOAT_EQ(c.y,-5.f); EXPECT_FLOAT_EQ(c.z,.99f);
	EXPECT_FLOAT_EQ(c.vx,.1f); EXPECT_FLOAT_EQ(c.vy,.2f); EXPECT_FLOAT_EQ(c.vz,1.f); EXPECT_FLOAT_EQ(c.yaw,1.77f);
	step(12000); const auto next=VelocityModuleTestAccess::cache(*m);
	EXPECT_FLOAT_EQ(c.x,next.x); EXPECT_FLOAT_EQ(c.z,next.z); EXPECT_FLOAT_EQ(c.yaw,next.yaw);
	d=step(8000,true); EXPECT_FLOAT_EQ(d.p_sp[0],target.x); EXPECT_FLOAT_EQ(d.p_sp[2],target.z);
}

TEST_F(VelocityModule, GroundContactAndExitDoNotPoisonLatestTarget)
{
	step(); VelocityModuleTestAccess::airborne(*m,lp.timestamp);
	land.landed=false; land.ground_contact=true; land_pub.publish(land);
	auto d=step(8000); EXPECT_FLOAT_EQ(d.a_ff[2],100.f);
	EXPECT_FLOAT_EQ(VelocityModuleTestAccess::cache(*m).z,target.z);
	land.ground_contact=false; land_pub.publish(land);
	d=step(12000); EXPECT_EQ(d.pid_calls,1); EXPECT_FLOAT_EQ(d.p_sp[2],target.z);
	EXPECT_FLOAT_EQ(d.a_ff[2],target.acceleration[2]);
	mode.flag_multicopter_position_control_enabled=false; mode_pub.publish(mode);
	d=step(8000); EXPECT_EQ(d.pid_calls,0);
	mode.flag_multicopter_position_control_enabled=true; mode_pub.publish(mode);
	d=step(12000); EXPECT_EQ(d.pid_calls,1); EXPECT_FLOAT_EQ(d.p_sp[2],target.z);
}

TEST_F(VelocityModule, FreshTargetAtEstimatorResetIsNotTranslatedAgain)
{
	step(); lp.xy_reset_counter=1; lp.delta_xy[0]=2.f; lp.delta_xy[1]=-3.f;
	auto d=step(8000,true); EXPECT_EQ(d.pid_calls,1);
	EXPECT_FLOAT_EQ(d.p_sp[0],target.x); EXPECT_FLOAT_EQ(d.p_sp[1],target.y);
	d=step(12000); EXPECT_FLOAT_EQ(d.p_sp[0],target.x); EXPECT_FLOAT_EQ(d.p_sp[1],target.y);
}

// V04 heading audit: test the real cache policy, not a copied yaw formula.
TEST_F(VelocityModule, HeadingOldCachePositiveNegativeWrapAndSingleApplication)
{
	step();
	for (float delta : {.2f, -.3f, 3.2f, -6.3f}) {
		const float before = VelocityModuleTestAccess::cache(*m).yaw;
		++lp.heading_reset_counter; lp.delta_heading = delta;
		auto d = step(8000);
		EXPECT_EQ(d.reset_bits & 16, 16); EXPECT_EQ(d.first_fail, 0); EXPECT_EQ(d.retry_result, 0);
		EXPECT_FLOAT_EQ(VelocityModuleTestAccess::cache(*m).yaw, before + delta);
		step(12000); // Persistent delta field must not be applied again without a new counter.
		EXPECT_FLOAT_EQ(VelocityModuleTestAccess::cache(*m).yaw, before + delta);
	}
}

TEST_F(VelocityModule, HeadingFreshSameTimestampAndNewerTargetNotDoubleCompensated)
{
	step();
	for (uint64_t lead : {uint64_t(0), uint64_t(1000)}) {
		++lp.heading_reset_counter; lp.delta_heading = .2f;
		target.yaw = -3.12f; target.timestamp = lp.timestamp + 8000 + lead;
		ASSERT_TRUE(target_pub.publish(target));
		auto d = step(8000);
		EXPECT_EQ(d.reset_bits & 16, 16); EXPECT_EQ(d.first_fail, 0); EXPECT_EQ(d.retry_result, 0);
		EXPECT_EQ(d.setpoint_timestamp, target.timestamp);
		EXPECT_FLOAT_EQ(VelocityModuleTestAccess::cache(*m).yaw, target.yaw);
		step(12000);
		EXPECT_FLOAT_EQ(VelocityModuleTestAccess::cache(*m).yaw, target.yaw);
	}
}

TEST_F(VelocityModule, GenuineInvalidTargetLogsFirstFailureAndExplicitAbortNotClock)
{
	step(); step(8000); target.x=1.f; target.y=NAN;
	auto d=step(12000,true);
	EXPECT_EQ(d.pid_calls,2); EXPECT_NE(d.first_fail & 1,0); EXPECT_EQ(d.retry_result,1);
	EXPECT_TRUE(d.valid); EXPECT_EQ(d.excitation_fault,VelocityDiagnosticExcitation::Controller);
	EXPECT_EQ(d.first_input & 3,1); EXPECT_TRUE(std::isnan(d.p_sp[0])); EXPECT_TRUE(std::isnan(d.p_sp[2]));
	EXPECT_FLOAT_EQ(d.v_ff[0],0.f); EXPECT_FLOAT_EQ(d.v_ff[2],0.f);
	EXPECT_FALSE(d.failsafe); EXPECT_NEAR(matrix::Eulerf(matrix::Quatf(d.q_sp)).psi(),lp.heading,1e-6f);
	target.x=lp.x; target.y=lp.y; d=step(8000,true);
	EXPECT_EQ(d.pid_calls,1); EXPECT_EQ(d.first_fail,0); EXPECT_EQ(d.excitation_fault,VelocityDiagnosticExcitation::Controller);
	mode.flag_armed=false; mode_pub.publish(mode); d=step(12000);
	EXPECT_EQ(d.excitation_fault,0);
}

TEST_F(VelocityModule, FallbackImmediatelyUsesVelocityStopAndPreservesYaw)
{
	PositionControlStates s{matrix::Vector3f(5,-2,-3),matrix::Vector3f(.1f,.2f,.3f),matrix::Vector3f(),1.57f};
	vehicle_local_position_setpoint_s sp{};
	VelocityModuleTestAccess::fallback(*m,1000000,sp,s);
	EXPECT_FALSE(VelocityModuleTestAccess::failsafe(*m));
	EXPECT_TRUE(std::isnan(sp.x)); EXPECT_TRUE(std::isnan(sp.z)); EXPECT_TRUE(std::isnan(sp.yaw));
	EXPECT_FLOAT_EQ(sp.vx,0.f); EXPECT_FLOAT_EQ(sp.vy,0.f); EXPECT_FLOAT_EQ(sp.vz,0.f);
	VelocityModuleTestAccess::fallback(*m,1199999,sp,s); EXPECT_FALSE(VelocityModuleTestAccess::failsafe(*m));
	VelocityModuleTestAccess::fallback(*m,1200000,sp,s); EXPECT_TRUE(VelocityModuleTestAccess::failsafe(*m));
	VelocityModuleTestAccess::recovered(*m,1200001);
	VelocityModuleTestAccess::fallback(*m,1210000,sp,s); EXPECT_FALSE(VelocityModuleTestAccess::failsafe(*m));
}

TEST_F(VelocityModule, MissingMeasurementLoggedBeforeRecoveryWithoutFalseClockFault)
{
	step(); step(8000); lp.v_xy_valid=false;
	auto d=step(12000,true); EXPECT_EQ(d.pid_calls,2); EXPECT_NE(d.first_fail & 4,0);
	EXPECT_EQ(d.first_input & ((3u<<9)|(3u<<12)),0);
	EXPECT_EQ(d.retry_result,1); EXPECT_TRUE(std::isnan(d.v_ff[0])); EXPECT_FLOAT_EQ(d.a_ff[0],0.f);
	EXPECT_EQ(d.excitation_fault,VelocityDiagnosticExcitation::Controller);
	lp.v_xy_valid=true; d=step(8000,true); EXPECT_EQ(d.pid_calls,1); EXPECT_EQ(d.first_fail,0);
	EXPECT_EQ(d.excitation_fault,VelocityDiagnosticExcitation::Controller);
}

TEST_F(VelocityModule, FallbackInvalidVelocityOrDerivativeUsesExplicitAcceleration)
{
	PositionControlStates s{matrix::Vector3f(),matrix::Vector3f(.1f,.2f,.3f),matrix::Vector3f(),1.f};
	vehicle_local_position_setpoint_s sp{};
	s.acceleration(0)=NAN; VelocityModuleTestAccess::fallback(*m,1000000,sp,s);
	EXPECT_TRUE(std::isnan(sp.vx)); EXPECT_TRUE(std::isnan(sp.vy));
	EXPECT_FLOAT_EQ(sp.acceleration[0],0.f); EXPECT_FLOAT_EQ(sp.acceleration[1],0.f); EXPECT_GT(sp.vz,0.f);
	s.velocity(2)=NAN; VelocityModuleTestAccess::fallback(*m,1008000,sp,s);
	EXPECT_TRUE(std::isnan(sp.vz)); EXPECT_FLOAT_EQ(sp.acceleration[2],.3f);
	s.velocity=matrix::Vector3f(); s.acceleration=matrix::Vector3f(0.f,0.f,NAN);
	VelocityModuleTestAccess::fallback(*m,1020000,sp,s);
	EXPECT_FLOAT_EQ(sp.vx,0.f); EXPECT_TRUE(std::isnan(sp.vz)); EXPECT_FLOAT_EQ(sp.acceleration[2],.3f);
}

TEST_F(VelocityModule, InvalidRetryCannotPublishEvenInPid)
{
	step(); step(8000); VelocityModuleTestAccess::invalidateGains(*m);
	auto d=step(12000,true);
	EXPECT_EQ(d.pid_calls,2); EXPECT_NE(d.first_fail & 8,0);
	EXPECT_EQ(d.retry_result,2); EXPECT_FALSE(d.valid);
	EXPECT_EQ(d.output_timestamp,0u); EXPECT_EQ(d.attitude_timestamp,0u);
}

TEST_F(VelocityModule, EstaFailureNeverDoubleCommitsOrPublishesRetry)
{
	mode.flag_armed=false; mode_pub.publish(mode); VelocityModuleTestAccess::selectEsta(*m);
	auto d=step(); ASSERT_EQ(d.effective_mode,1);
	mode.flag_armed=true; mode_pub.publish(mode); land.landed=land.ground_contact=false; land_pub.publish(land);
	VelocityModuleTestAccess::airborne(*m,lp.timestamp);
	d=step(8000,true); EXPECT_TRUE(d.valid);
	d=step(12000,true); ASSERT_TRUE(d.valid); ASSERT_EQ(d.committed_axes,1);
	target.y=NAN; d=step(8000,true);
	EXPECT_EQ(d.effective_mode,1); EXPECT_EQ(d.pid_calls,2); EXPECT_EQ(d.committed_axes,0);
	EXPECT_NE(d.first_fail & 1,0); EXPECT_EQ(d.retry_result,2); EXPECT_TRUE(d.fault);
	EXPECT_EQ(d.output_timestamp,0u); EXPECT_EQ(d.excitation_fault,VelocityDiagnosticExcitation::Controller);
	target.y=lp.y; d=step(12000,true); EXPECT_FALSE(d.valid); EXPECT_EQ(d.committed_axes,0);
	mode.flag_armed=false; mode_pub.publish(mode); d=step(8000,true);
	EXPECT_FALSE(d.fault); EXPECT_EQ(d.excitation_fault,0); EXPECT_FLOAT_EQ(d.nu_applied[0],0.f);
}

TEST(VelocityExcitationRepair, AbortDoesNotAdvanceClockAndStillLatchesRealFailure)
{
	VelocityDiagnosticExcitation e; e.update(1000000,true,false); e.abort(); e.abort();
	EXPECT_EQ(e.fault(),VelocityDiagnosticExcitation::Controller);
	EXPECT_FLOAT_EQ(e.update(1008000,true,true),0.f); EXPECT_EQ(e.fault(),VelocityDiagnosticExcitation::Controller);
	e.update(1010000,false,false); EXPECT_EQ(e.fault(),0);
	e.update(1020000,true,true); e.update(1020000,true,true);
	EXPECT_NE(e.fault() & VelocityDiagnosticExcitation::Clock,0);
}

TEST(VelocityExcitationRepair, BackwardsGapGateAndDisarmRemainDistinct)
{
	VelocityDiagnosticExcitation e; e.update(1000000,true,false); e.update(999999,true,false);
	EXPECT_EQ(e.fault(),VelocityDiagnosticExcitation::Clock);
	e.update(1000000,false,false); e.update(1010000,true,true); e.update(1050001,true,true);
	EXPECT_EQ(e.fault(),VelocityDiagnosticExcitation::Clock);
	e.update(1060000,false,false); e.update(1070000,true,true); e.update(1080000,true,false);
	EXPECT_EQ(e.fault(),VelocityDiagnosticExcitation::Gate);
}
