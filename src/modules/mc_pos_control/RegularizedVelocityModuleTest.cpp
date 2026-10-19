// SPDX-License-Identifier: BSD-3-Clause
// R02/R03: real synchronous Run/uORB evidence, never a simulator or flight.
#include <gtest/gtest.h>
#define MODULE_NAME "mc_pos_control_regularized_test"
#include "MulticopterPositionControl.hpp"
#include <platforms/posix/apps.h>
#include <parameters/param.h>
#include <px4_platform_common/px4_work_queue/WorkQueueManager.hpp>
#include <cmath>
#include <cstdio>
#include <unistd.h>

extern "C" void __wrap_hrt_call_after(hrt_call *, hrt_abstime, hrt_callout, void *) {}
extern "C" void __wrap_hrt_cancel(hrt_call *) {}

class RegularizedVelocityTestAccess
{
public:
	static void admit(PositionControl &p) { p._regularized_test_admission = true; }
};

class RegularizedVelocityModuleTestAccess
{
public:
	static void step(MulticopterPositionControl &m) { m.Run(); m.ScheduleClear(); }
	static void admit(MulticopterPositionControl &m) { RegularizedVelocityTestAccess::admit(m._control); }
	static void airborne(MulticopterPositionControl &m, uint64_t t)
	{
		m._takeoff.updateTakeoffState(true, false, false, 1.f, true, t);
	}
	static void request(MulticopterPositionControl &m, int32_t mode, int32_t axes)
	{
		m._param_mpc_vc_mode.set(mode); m._param_mpc_vc_axes.set(axes);
		m._param_mpc_vc_l1_x.set(.5f); m._param_mpc_vc_l2_x.set(.1f);
		m._param_mpc_vc_l1_y.set(.5f); m._param_mpc_vc_l2_y.set(.1f);
		m._param_mpc_vc_l1_z.set(2.f); m._param_mpc_vc_l2_z.set(1.f);
		m._param_mpc_vc_nu_x.set(.4f); m._param_mpc_vc_a_x.set(.8f);
		m._param_mpc_vc_nu_y.set(.4f); m._param_mpc_vc_a_y.set(.8f);
		m._param_mpc_vc_nu_z.set(4.f); m._param_mpc_vc_a_z.set(6.f);
	}
	static void widths(MulticopterPositionControl &m, float x, float y, float z)
	{
		m._param_mpc_vc_eps_x.set(x); m._param_mpc_vc_eps_y.set(y); m._param_mpc_vc_eps_z.set(z);
	}
	static void yGains(MulticopterPositionControl &m, float lambda1, float lambda2)
	{
		m._param_mpc_vc_l1_y.set(lambda1); m._param_mpc_vc_l2_y.set(lambda2);
	}
	static void poisonIdleXyPid(MulticopterPositionControl &m)
	{
		// Test-only observation of NORMAL XY dispatch. Never poison the active Z
		// PID, position P or any parameter store. A full parameter reload would
		// discard this fixture's uncommitted MODE/AXES/STA requests; do not use it.
		m._control.setVelocityGains(
			matrix::Vector3f(NAN, NAN, m._param_mpc_z_vel_p_acc.get()),
			matrix::Vector3f(NAN, NAN, m._param_mpc_z_vel_i_acc.get()),
			matrix::Vector3f(NAN, NAN, m._param_mpc_z_vel_d_acc.get()));
	}
	static void poisonAllIdleVelocityPid(MulticopterPositionControl &m)
	{
		// Only a NORMAL XYZ dispatch probe. No parameter mutation/reload, no
		// Takeoff override and no production-admission friend is invoked here.
		m._control.setVelocityGains(matrix::Vector3f(NAN, NAN, NAN),
			matrix::Vector3f(NAN, NAN, NAN), matrix::Vector3f(NAN, NAN, NAN));
	}
	static void reload(MulticopterPositionControl &m) { m.parameters_update(true); }
	static void fastSpool(MulticopterPositionControl &m) { m._takeoff.setSpoolupTime(.008f); }
	static void pidP(MulticopterPositionControl &m, float value)
	{
		m._param_mpc_xy_vel_p_acc.commit_no_notification(value); m.parameters_update(true);
	}
};

class RegularizedVelocityQueueAnchor : public px4::WorkItem
{
public:
	RegularizedVelocityQueueAnchor() : WorkItem("regularized_test_anchor", px4::wq_configurations::nav_and_controllers) {}
	void Run() override {}
};
static RegularizedVelocityQueueAnchor *regularized_queue_anchor = nullptr;

class RegularizedVelocityModule : public ::testing::Test
{
public:
	static void SetUpTestSuite()
	{
		ASSERT_EQ(px4::WorkQueueManagerStart(), 0); px4_usleep(20000);
		regularized_queue_anchor = new RegularizedVelocityQueueAnchor();
	}
	static void TearDownTestSuite()
	{
		delete regularized_queue_anchor; regularized_queue_anchor = nullptr;
		px4_usleep(20000); EXPECT_EQ(px4::WorkQueueManagerStop(), 0);
	}
protected:
	uORB::Publication<vehicle_local_position_s> lp_pub{ORB_ID(vehicle_local_position)};
	uORB::Publication<vehicle_local_position_setpoint_s> target_pub{ORB_ID(trajectory_setpoint)};
	uORB::Publication<vehicle_control_mode_s> mode_pub{ORB_ID(vehicle_control_mode)};
	uORB::Publication<vehicle_land_detected_s> land_pub{ORB_ID(vehicle_land_detected)};
	uORB::Publication<vehicle_constraints_s> limits_pub{ORB_ID(vehicle_constraints)};
	uORB::Publication<sta_rate_ctrl_status_s> rate_pub{ORB_ID(sta_rate_ctrl_status)};
	uORB::Subscription selection_sub{ORB_ID(velocity_ctrl_selection)};
	uORB::Subscription diagnostic_sub{ORB_ID(sta_velocity_ctrl_status)};
	vehicle_local_position_s lp{};
	vehicle_local_position_setpoint_s target{};
	vehicle_control_mode_s mode{};
	vehicle_land_detected_s land{};
	velocity_ctrl_selection_s selection{};
	sta_velocity_ctrl_status_s diagnostic{};
	MulticopterPositionControl *module{nullptr};
	uint32_t previous_seq{0};
	bool rate_fault{false};
	bool rate_termination{false};
	void SetUp() override
	{
		apps_map_type apps; init_app_map(apps); ASSERT_TRUE(apps.empty());
		param_control_autosave(false); param_reset_all();
		module = new MulticopterPositionControl();
		lp.timestamp = lp.timestamp_sample = 1000000;
		lp.xy_valid = lp.z_valid = lp.v_xy_valid = lp.v_z_valid = true;
		lp.x = 5.f; lp.y = -2.f; lp.z = -2.5f; lp.heading = .2f;
		target.x = lp.x; target.y = lp.y; target.z = lp.z;
		target.vx = .004f; target.vy = -.003f; target.vz = 0.f;
		target.yaw = lp.heading; target.acceleration[0] = .002f; target.acceleration[1] = -.001f;
		mode.flag_multicopter_position_control_enabled = mode.flag_control_auto_enabled = true;
		land.landed = land.ground_contact = true;
		vehicle_constraints_s limits{}; limits.speed_xy = 5.f; limits.speed_up = 3.f; limits.speed_down = 1.f;
		limits.want_takeoff = true;
		ASSERT_TRUE(mode_pub.publish(mode)); ASSERT_TRUE(land_pub.publish(land)); ASSERT_TRUE(limits_pub.publish(limits));
	}
	void TearDown() override { delete module; param_reset_all(); }
	void step(uint64_t dt = 10000, uint64_t publication_delay = 0)
	{
		lp.timestamp_sample += dt; lp.timestamp = lp.timestamp_sample + publication_delay;
		target.timestamp = lp.timestamp; EXPECT_TRUE(target_pub.publish(target));
		sta_rate_ctrl_status_s rate{}; rate.timestamp = hrt_absolute_time(); rate.div_eff = 1;
		rate.fault = rate_fault; rate.termination = rate_termination;
		rate.measurement_valid = rate.output_valid = true; EXPECT_TRUE(rate_pub.publish(rate));
		EXPECT_TRUE(lp_pub.publish(lp)); RegularizedVelocityModuleTestAccess::step(*module);
		unsigned sr = 0, dr = 0;
		while (sr < 8 && selection_sub.update(&selection)) { ++sr; }
		while (dr < 8 && diagnostic_sub.update(&diagnostic)) { ++dr; }
		ASSERT_GT(sr, 0u); ASSERT_GT(dr, 0u);
		EXPECT_EQ(selection.publish_seq, ++previous_seq);
		EXPECT_EQ(selection.publish_seq, diagnostic.publish_seq);
		EXPECT_EQ(selection.timestamp_sample, lp.timestamp_sample);
		EXPECT_EQ(selection.timestamp_sample, diagnostic.timestamp_sample);
		EXPECT_EQ(selection.input_timestamp, diagnostic.input_timestamp);
		EXPECT_EQ(selection.effective_mode, diagnostic.effective_mode);
		EXPECT_EQ(selection.effective_axes, diagnostic.effective_axes);
		EXPECT_EQ(selection.pid_calls, diagnostic.pid_calls);
		EXPECT_EQ(selection.armed, diagnostic.armed); EXPECT_EQ(selection.enabled, diagnostic.enabled);
	}
	void arm()
	{
		mode.flag_armed = true; EXPECT_TRUE(mode_pub.publish(mode));
		land.landed = land.ground_contact = false; EXPECT_TRUE(land_pub.publish(land));
		RegularizedVelocityModuleTestAccess::airborne(*module, lp.timestamp);
	}
	void disarm()
	{
		mode.flag_armed = false; EXPECT_TRUE(mode_pub.publish(mode));
		land.landed = land.ground_contact = true; EXPECT_TRUE(land_pub.publish(land));
	}
	void configureOffline(int32_t axes = 1)
	{
		RegularizedVelocityModuleTestAccess::admit(*module);
		RegularizedVelocityModuleTestAccess::request(*module, 3, axes); step();
		ASSERT_EQ(selection.effective_mode, 3); ASSERT_EQ(selection.effective_axes, axes);
		arm(); step(8000); step(12000);
	}
	void configureProductionX()
	{
		// Deliberately do not invoke the broad offline admission friend.
		RegularizedVelocityModuleTestAccess::request(*module, 3, 1); step();
		ASSERT_EQ(selection.effective_mode, 3); ASSERT_EQ(selection.effective_axes, 1);
		ASSERT_EQ(selection.reject, 0); arm(); step(8000); step(12000);
	}
	void configureProductionZ()
	{
		// Gate B production route: no test-only admission friend is invoked.
		RegularizedVelocityModuleTestAccess::request(*module, 3, 4); step();
		ASSERT_EQ(selection.effective_mode, 3); ASSERT_EQ(selection.effective_axes, 4);
		ASSERT_EQ(selection.reject, 0); EXPECT_FLOAT_EQ(selection.eps_eff[2], .02f);
		EXPECT_TRUE(std::isnan(selection.eps_eff[0])); EXPECT_TRUE(std::isnan(selection.eps_eff[1]));
		arm(); step(8000);
		ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.z_phase, 2); EXPECT_EQ(diagnostic.committed_axes, 0);
		step(12000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.z_phase, 3);
		EXPECT_EQ(diagnostic.committed_axes, 4); EXPECT_EQ(diagnostic.pid_axes, 3);
	}
	void configureProductionXY(float lambda1_y = .5f, float lambda2_y = .1f, float epsilon_y = .01f)
	{
		// Gate C production route: deliberately never invoke admit().
		RegularizedVelocityModuleTestAccess::request(*module, 3, 3);
		RegularizedVelocityModuleTestAccess::yGains(*module, lambda1_y, lambda2_y);
		RegularizedVelocityModuleTestAccess::widths(*module, .01f, epsilon_y, .02f); step();
		ASSERT_EQ(selection.effective_mode, 3); ASSERT_EQ(selection.effective_axes, 3);
		ASSERT_EQ(selection.reject, 0); EXPECT_FLOAT_EQ(selection.eps_eff[0], .01f);
		EXPECT_FLOAT_EQ(selection.eps_eff[1], epsilon_y); EXPECT_TRUE(std::isnan(selection.eps_eff[2]));
		arm(); step(8000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0);
		step(12000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 3);
		EXPECT_EQ(diagnostic.pid_axes, 4); EXPECT_EQ(diagnostic.z_phase, 0);
	}
	void configureProductionXYZ(float lambda1_y = .5f, float lambda2_y = .1f, float epsilon_y = .01f)
	{
		// Requires real Gate D admission. Never calls admit().
		RegularizedVelocityModuleTestAccess::request(*module, 3, 7);
		RegularizedVelocityModuleTestAccess::yGains(*module, lambda1_y, lambda2_y);
		RegularizedVelocityModuleTestAccess::widths(*module, .01f, epsilon_y, .02f); step();
		ASSERT_EQ(selection.effective_mode, 3); ASSERT_EQ(selection.effective_axes, 7);
		ASSERT_EQ(selection.reject, 0); EXPECT_FLOAT_EQ(selection.eps_eff[0], .01f);
		EXPECT_FLOAT_EQ(selection.eps_eff[1], epsilon_y); EXPECT_FLOAT_EQ(selection.eps_eff[2], .02f);
		arm(); step(8000); ASSERT_TRUE(diagnostic.valid);
		EXPECT_EQ(diagnostic.z_phase, 2); EXPECT_EQ(diagnostic.committed_axes, 0); EXPECT_EQ(diagnostic.pid_axes, 7);
		step(12000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.z_phase, 3);
		EXPECT_EQ(diagnostic.committed_axes, 7); EXPECT_EQ(diagnostic.pid_axes, 0);
	}
};

TEST_F(RegularizedVelocityModule, DefaultPidHasUnusedWidthsAndExactDiagnosticJoin)
{
	step(); EXPECT_EQ(selection.effective_mode, 0); EXPECT_EQ(selection.effective_axes, 0);
	EXPECT_EQ(selection.variant_req, 0); EXPECT_EQ(selection.variant_eff, 0);
	EXPECT_EQ(selection.div_eff, 1); EXPECT_EQ(selection.sta_gen, 0u);
	EXPECT_FLOAT_EQ(selection.eps_req[0], .01f); EXPECT_FLOAT_EQ(selection.eps_req[1], .01f);
	EXPECT_FLOAT_EQ(selection.eps_req[2], .02f);
	for (int i = 0; i < 3; ++i) { EXPECT_TRUE(std::isnan(selection.eps_eff[i])); }
	arm(); step(8000); step(12000);
	EXPECT_EQ(diagnostic.inner_mode, 0); EXPECT_EQ(diagnostic.inner_axes, 0); EXPECT_EQ(diagnostic.inner_divisor, 1);
	EXPECT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.pid_axes, 7);
}

TEST_F(RegularizedVelocityModule, ProductionGateDRejectsUnadmittedMasksWithoutEffectiveMutation)
{
	for (const int32_t axes : {-1, 0, 2, 5, 6, 8, 257}) {
		RegularizedVelocityModuleTestAccess::request(*module, 3, axes); step();
		EXPECT_EQ(selection.requested_mode, 3); EXPECT_EQ(selection.variant_req, 3);
		EXPECT_EQ(selection.effective_mode, 0); EXPECT_EQ(selection.variant_eff, 0);
		EXPECT_NE(selection.reject, 0); EXPECT_EQ(selection.sta_gen, 0u);
		for (int i = 0; i < 3; ++i) { EXPECT_TRUE(std::isnan(selection.eps_eff[i])); }
	}
	RegularizedVelocityModuleTestAccess::request(*module, 3, 1); step();
	ASSERT_EQ(selection.effective_mode, 3); ASSERT_EQ(selection.effective_axes, 1); ASSERT_EQ(selection.reject, 0);
	const auto generation = selection.sta_gen; ASSERT_GT(generation, 0u);
	for (const int32_t axes : {-1, 0, 2, 5, 6, 8, 257}) {
		RegularizedVelocityModuleTestAccess::request(*module, 3, axes); step();
		EXPECT_EQ(selection.requested_axes, axes); EXPECT_EQ(selection.effective_mode, 3);
		EXPECT_EQ(selection.variant_eff, 3); EXPECT_EQ(selection.effective_axes, 1);
		EXPECT_NE(selection.reject, 0); EXPECT_EQ(selection.sta_gen, generation);
		EXPECT_FLOAT_EQ(selection.eps_eff[0], .01f);
	}
	RegularizedVelocityModuleTestAccess::request(*module, 0, 0); step();
	ASSERT_EQ(selection.effective_mode, 0);
	for (int32_t unavailable : {-1, 2, 4, 256}) {
		RegularizedVelocityModuleTestAccess::request(*module, unavailable, 0); step();
		EXPECT_EQ(selection.variant_req, 255); EXPECT_NE(selection.reject, 0); EXPECT_EQ(selection.effective_mode, 0);
	}
}

TEST_F(RegularizedVelocityModule, ProductionXActualOutputUsesEffectiveWidthAndOldNu)
{
	configureProductionX();
	for (unsigned k = 0; k < 12; ++k) {
		step(k % 2 ? 12000 : 8000); ASSERT_TRUE(diagnostic.valid);
		ASSERT_EQ(selection.variant_eff, 3); ASSERT_EQ(diagnostic.committed_axes, 1);
		EXPECT_EQ(diagnostic.pid_axes, 6); EXPECT_FLOAT_EQ(selection.eps_eff[0], .01f);
		EXPECT_TRUE(std::isnan(selection.eps_eff[1])); EXPECT_TRUE(std::isnan(selection.eps_eff[2]));
		const double s = static_cast<double>(diagnostic.s[0]);
		const double eps = static_cast<double>(selection.eps_eff[0]);
		const double psi = std::fabs(s) <= eps ? s / std::sqrt(eps) : std::copysign(std::sqrt(std::fabs(s)), s);
		const double rho = std::fmax(-1., std::fmin(1., s / eps));
		EXPECT_NEAR(static_cast<double>(diagnostic.a_sta[0]), -.5 * psi + static_cast<double>(diagnostic.nu_before[0]), 2e-7);
		EXPECT_NEAR(static_cast<double>(diagnostic.nu_ideal[0]), static_cast<double>(diagnostic.nu_before[0])
			- static_cast<double>(diagnostic.raw_dt) * .1 * rho, 2e-7);
		EXPECT_NEAR(diagnostic.a_req[0], diagnostic.a_sta[0] + target.acceleration[0], 2e-7f);
		EXPECT_EQ(selection.sta_gen, diagnostic.config_generation);
		printf("R03_SAMPLE {\"mode\":%d,\"axes\":%d,\"seq\":%u,\"sample\":%llu,\"eps\":%.9g,\"s\":%.9g,\"before\":%.9g,\"ideal\":%.9g,\"applied\":%.9g,\"a\":%.9g}\n",
			selection.effective_mode, selection.effective_axes, selection.publish_seq,
			static_cast<unsigned long long>(selection.timestamp_sample), static_cast<double>(selection.eps_eff[0]),
			static_cast<double>(diagnostic.s[0]), static_cast<double>(diagnostic.nu_before[0]),
			static_cast<double>(diagnostic.nu_ideal[0]), static_cast<double>(diagnostic.nu_applied[0]), static_cast<double>(diagnostic.a_sta[0]));
	}
}

TEST_F(RegularizedVelocityModule, EpsilonArmedRequestCancelDisarmAndInvalidRequestRemainDistinct)
{
	configureProductionX(); const uint32_t generation = selection.sta_gen;
	RegularizedVelocityModuleTestAccess::widths(*module, .03f, .01f, .02f); step();
	EXPECT_TRUE(selection.sta_pending); EXPECT_FALSE(selection.pending);
	EXPECT_EQ(selection.sta_gen, generation); EXPECT_FLOAT_EQ(selection.eps_req[0], .03f);
	EXPECT_FLOAT_EQ(selection.eps_eff[0], .01f);
	RegularizedVelocityModuleTestAccess::widths(*module, .01f, .01f, .02f); step();
	EXPECT_FALSE(selection.sta_pending); EXPECT_EQ(selection.sta_gen, generation);
	RegularizedVelocityModuleTestAccess::widths(*module, .03f, .01f, .02f); step();
	disarm(); step(); EXPECT_FALSE(selection.sta_pending); EXPECT_GT(selection.sta_gen, generation);
	EXPECT_FLOAT_EQ(selection.eps_eff[0], .03f); EXPECT_FLOAT_EQ(diagnostic.nu_applied[0], 0.f);
	const uint32_t accepted = selection.sta_gen;
	RegularizedVelocityModuleTestAccess::widths(*module, NAN, .01f, .02f); step();
	EXPECT_TRUE(selection.sta_reject); EXPECT_NE(selection.reject, 0);
	EXPECT_TRUE(std::isnan(selection.eps_req[0])); EXPECT_FLOAT_EQ(selection.eps_eff[0], .03f);
	EXPECT_EQ(selection.sta_gen, accepted); EXPECT_EQ(selection.effective_mode, 3);
}

TEST_F(RegularizedVelocityModule, ProductionXModeRequestsCancelAndDisarmWithoutStaleState)
{
	configureProductionX(); ASSERT_TRUE(diagnostic.valid); const auto generation = selection.sta_gen;
	for (const int32_t unadmitted : {2, 5, 6}) {
		RegularizedVelocityModuleTestAccess::request(*module, 3, unadmitted); step(8000);
		EXPECT_TRUE(selection.pending); EXPECT_NE(selection.reject, 0); EXPECT_EQ(selection.effective_mode, 3);
		EXPECT_EQ(selection.effective_axes, 1); EXPECT_EQ(selection.sta_gen, generation); EXPECT_TRUE(diagnostic.valid);
		RegularizedVelocityModuleTestAccess::request(*module, 3, 1); step(12000);
		EXPECT_FALSE(selection.pending); EXPECT_FALSE(selection.sta_pending); EXPECT_EQ(selection.reject, 0);
		EXPECT_EQ(selection.sta_gen, generation);
	}
	for (const int32_t next : {1, 0, 3}) {
		const auto previous = selection.effective_mode;
		RegularizedVelocityModuleTestAccess::request(*module, next, next ? 1 : 0); step(8000);
		EXPECT_TRUE(selection.pending); EXPECT_EQ(selection.effective_mode, previous); EXPECT_EQ(selection.reject, 0);
		RegularizedVelocityModuleTestAccess::request(*module, previous, previous ? 1 : 0); step(12000);
		EXPECT_FALSE(selection.pending); EXPECT_EQ(selection.effective_mode, previous);
		RegularizedVelocityModuleTestAccess::request(*module, next, next ? 1 : 0); step(8000);
		EXPECT_TRUE(selection.pending); disarm(); step(12000);
		EXPECT_FALSE(selection.pending); EXPECT_EQ(selection.effective_mode, next); EXPECT_EQ(selection.reject, 0);
		if (next) { EXPECT_FLOAT_EQ(diagnostic.nu_applied[0], 0.f); }
		else { EXPECT_TRUE(std::isnan(diagnostic.nu_applied[0])); }
		arm(); step(8000); EXPECT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0);
		step(12000); EXPECT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.pid_axes, next ? 6 : 7);
		EXPECT_EQ(diagnostic.committed_axes, next ? 1 : 0);
	}
}

TEST_F(RegularizedVelocityModule, OriginalEstaWidthEditsDoNotResetStateOrGeneration)
{
	RegularizedVelocityModuleTestAccess::request(*module, 1, 1); step(); arm(); step(8000); step(12000);
	ASSERT_EQ(selection.effective_mode, 1); ASSERT_TRUE(diagnostic.valid);
	const uint32_t generation = selection.sta_gen; const float previous = diagnostic.nu_applied[0];
	RegularizedVelocityModuleTestAccess::widths(*module, NAN, -.2f, INFINITY); step(8000);
	EXPECT_FALSE(selection.sta_pending); EXPECT_FALSE(selection.sta_reject);
	EXPECT_EQ(selection.sta_gen, generation); EXPECT_EQ(selection.variant_eff, 1);
	EXPECT_FLOAT_EQ(diagnostic.nu_before[0], previous); EXPECT_TRUE(diagnostic.valid);
	for (int i = 0; i < 3; ++i) { EXPECT_TRUE(std::isnan(selection.eps_eff[i])); }
}

TEST_F(RegularizedVelocityModule, OriginalPidGainUpdatesRemainImmediateWhileArmed)
{
	step(); arm(); step(8000); step(12000); ASSERT_TRUE(diagnostic.valid);
	RegularizedVelocityModuleTestAccess::pidP(*module, 2.7f); step(8000);
	ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(selection.effective_mode, 0); EXPECT_FALSE(selection.pending);
	for (int i = 0; i < 2; ++i) {
		// Constant measured velocity implies zero measured derivative; before-state
		// integral is reconstructed from its actual post-update diagnostic state.
		const float error = diagnostic.v_sp[i] - diagnostic.v[i];
		float gain_i = 0.f; ASSERT_EQ(param_get(param_find("MPC_XY_VEL_I_ACC"), &gain_i), 0);
		EXPECT_NEAR(selection.correction[i], 2.7f * error + selection.integral[i] - error * gain_i * diagnostic.used_dt, 2e-6f);
	}
}

TEST_F(RegularizedVelocityModule, SavedModeAndWidthsReloadAdmitProductionGateDXZXYXYZ)
{
	const float values[3]{.013f, .024f, .035f};
	const char *names[3]{"MPC_VC_EPS_X", "MPC_VC_EPS_Y", "MPC_VC_EPS_Z"};
	const char *gain_names[12]{"MPC_VC_L1_X", "MPC_VC_L2_X", "MPC_VC_NU_X", "MPC_VC_A_X",
		"MPC_VC_L1_Y", "MPC_VC_L2_Y", "MPC_VC_NU_Y", "MPC_VC_A_Y",
		"MPC_VC_L1_Z", "MPC_VC_L2_Z", "MPC_VC_NU_Z", "MPC_VC_A_Z"};
	const float gains[12]{.5f, .1f, .4f, .8f, .5f, .1f, .4f, .8f, 2.f, 1.f, 4.f, 6.f};
	for (const int32_t requested_axes : {1, 3, 4, 7}) {
		for (int i = 0; i < 3; ++i) { ASSERT_EQ(param_set(param_find(names[i]), &values[i]), 0); }
		for (int i = 0; i < 12; ++i) { ASSERT_EQ(param_set(param_find(gain_names[i]), &gains[i]), 0); }
		int32_t mode_value = 3, axes = requested_axes;
		ASSERT_EQ(param_set(param_find("MPC_VC_MODE"), &mode_value), 0);
		ASSERT_EQ(param_set(param_find("MPC_VC_AXES"), &axes), 0);
		FILE *f = tmpfile(); ASSERT_NE(f, nullptr); ASSERT_EQ(param_export(fileno(f), false, nullptr), 0);
		param_reset_all(); ASSERT_EQ(lseek(fileno(f), 0, SEEK_SET), 0);
		ASSERT_EQ(param_import(fileno(f), true), 0); fclose(f);
		delete module; module = new MulticopterPositionControl(); previous_seq = 0; step();
		EXPECT_EQ(selection.requested_mode, 3); EXPECT_EQ(selection.requested_axes, requested_axes);
		EXPECT_FALSE(selection.sta_reject); // all gains/widths valid: rejection must be the stage gate
		const bool admitted = requested_axes == 1 || requested_axes == 4 || requested_axes == 3 || requested_axes == 7;
		if (admitted) {
			EXPECT_EQ(selection.effective_mode, 3); EXPECT_EQ(selection.effective_axes, requested_axes);
			EXPECT_EQ(selection.reject, 0);
		} else {
			EXPECT_EQ(selection.effective_mode, 0); EXPECT_NE(selection.reject, 0);
		}
		for (int i = 0; i < 3; ++i) {
			EXPECT_FLOAT_EQ(selection.eps_req[i], values[i]);
			if (admitted && (requested_axes & (1 << i))) { EXPECT_FLOAT_EQ(selection.eps_eff[i], values[i]); }
			else { EXPECT_TRUE(std::isnan(selection.eps_eff[i])); }
		}
	}
}

TEST_F(RegularizedVelocityModule, FailsafeSameSampleKeepsSingleJoinedPublication)
{
	configureProductionX(); const uint32_t sequence = selection.publish_seq;
	rate_fault = true; step(8000);
	EXPECT_EQ(selection.publish_seq, sequence + 1); EXPECT_EQ(selection.pid_calls, 2);
	EXPECT_FALSE(diagnostic.valid); EXPECT_NE(diagnostic.first_fail, 0); EXPECT_EQ(diagnostic.committed_axes, 0);
	EXPECT_EQ(diagnostic.output_timestamp, 0u); EXPECT_EQ(selection.variant_eff, 3);
	EXPECT_FLOAT_EQ(selection.eps_eff[0], .01f); EXPECT_EQ(selection.sta_gen, diagnostic.config_generation);
}

TEST_F(RegularizedVelocityModule, DistinctPublicationAndSampleClocksKeepExactJoinAndRawDt)
{
	configureProductionX(); step(12000, 4000);
	ASSERT_TRUE(diagnostic.valid);
	EXPECT_EQ(selection.input_timestamp - selection.timestamp_sample, 4000u);
	EXPECT_NEAR(diagnostic.raw_dt, .012f, 1e-7f);
	EXPECT_NEAR(diagnostic.input_dt, .016f, 1e-7f);
	const float rho = math::constrain(diagnostic.s[0] / selection.eps_eff[0], -1.f, 1.f);
	EXPECT_NEAR(diagnostic.nu_ideal[0], diagnostic.nu_before[0] - .012f * .1f * rho, 2e-7f);
	step(8000, 0); ASSERT_TRUE(diagnostic.valid);
	EXPECT_NEAR(diagnostic.raw_dt, .008f, 1e-7f); EXPECT_NEAR(diagnostic.input_dt, .004f, 1e-7f);
}

TEST_F(RegularizedVelocityModule, TerminationRemainsLatchedUntilDisarmAndFreshHandover)
{
	configureOffline(7); ASSERT_TRUE(diagnostic.valid);
	rate_termination = true; step(8000);
	EXPECT_FALSE(diagnostic.valid); EXPECT_TRUE(diagnostic.fault); EXPECT_EQ(diagnostic.pid_calls, 2);
	EXPECT_EQ(diagnostic.committed_axes, 0); EXPECT_EQ(diagnostic.output_timestamp, 0u);
	rate_termination = false; step(12000);
	EXPECT_FALSE(diagnostic.valid); EXPECT_EQ(diagnostic.output_timestamp, 0u);
	disarm(); step(8000); EXPECT_FALSE(diagnostic.fault);
	for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(diagnostic.nu_applied[i], 0.f); }
	arm(); step(12000); EXPECT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.z_phase, 2);
	EXPECT_EQ(diagnostic.committed_axes, 0);
	step(8000); EXPECT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 7);
}

TEST_F(RegularizedVelocityModule, LongGroundWaitAndExternalTimeoutCancelNeverIntegrateNu)
{
	// Takeoff has no independent timeout detector. The experiment runner owns
	// its deadline/cancel command; model that command by disarming after 60 s.
	RegularizedVelocityModuleTestAccess::admit(*module);
	RegularizedVelocityModuleTestAccess::request(*module, 3, 7);
	RegularizedVelocityModuleTestAccess::fastSpool(*module); step();
	mode.flag_armed = true; ASSERT_TRUE(mode_pub.publish(mode));
	const uint64_t started = lp.timestamp_sample;
	unsigned suppressed = 0, ramp_pid = 0;
	for (unsigned k = 0; k < 6002; ++k) {
		step(k % 2 ? 12000 : 8000);
		ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0);
		EXPECT_EQ(diagnostic.z_phase, 1); EXPECT_EQ(diagnostic.pid_calls, 1);
		// z_phase=1 dispatches the unchanged PID function. pid_axes, however,
		// describes enabled finite velocity targets, not that function call.
		// Ground suppression makes all velocity targets NaN: no axis is active.
		if (diagnostic.reset_bits & 32) {
			++suppressed; EXPECT_EQ(diagnostic.pid_axes, 0); EXPECT_FLOAT_EQ(diagnostic.a_ff[2], 100.f);
			for (float value : diagnostic.v_sp) { EXPECT_TRUE(std::isnan(value)); }
		} else {
			++ramp_pid; EXPECT_EQ(diagnostic.pid_axes, 7);
			EXPECT_EQ(diagnostic.takeoff_state, static_cast<uint8_t>(TakeoffState::rampup));
			for (float value : diagnostic.v_sp) { EXPECT_TRUE(std::isfinite(value)); }
		}
		for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(diagnostic.nu_applied[i], 0.f); }
	}
	EXPECT_GT(suppressed, 0u); EXPECT_GT(ramp_pid, 0u); EXPECT_EQ(suppressed + ramp_pid, 6002u);
	printf("R02_GROUND_WAIT suppressed=%u ramp_pid=%u duration_us=%llu\n", suppressed, ramp_pid,
		static_cast<unsigned long long>(lp.timestamp_sample - started));
	EXPECT_GT(lp.timestamp_sample - started, 60000000u);
	disarm(); step(8000); EXPECT_EQ(diagnostic.takeoff_state, static_cast<uint8_t>(TakeoffState::disarmed));
	EXPECT_EQ(diagnostic.committed_axes, 0); EXPECT_FALSE(diagnostic.fault);
	arm(); step(12000); EXPECT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.z_phase, 2);
	step(8000); EXPECT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 7);
}

TEST_F(RegularizedVelocityModule, RepeatedContactBounceClearsNuAndUsesOneFreshHandover)
{
	configureOffline(7);
	for (unsigned bounce = 0; bounce < 3; ++bounce) {
		step(8000); ASSERT_TRUE(diagnostic.valid); ASSERT_EQ(diagnostic.committed_axes, 7);
		land.ground_contact = true; ASSERT_TRUE(land_pub.publish(land)); step(12000);
		ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.z_phase, 1); EXPECT_EQ(diagnostic.committed_axes, 0);
		for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(diagnostic.nu_applied[i], 0.f); }
		land.ground_contact = false; ASSERT_TRUE(land_pub.publish(land)); step(8000);
		ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.z_phase, 2); EXPECT_EQ(diagnostic.committed_axes, 0);
		step(12000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.z_phase, 3); EXPECT_EQ(diagnostic.committed_axes, 7);
	}
}

TEST_F(RegularizedVelocityModule, InvalidMeasurementRecoveryOrModeReentryCannotClearFault)
{
	configureOffline(7); lp.v_z_valid = false; step(8000);
	EXPECT_FALSE(diagnostic.valid); EXPECT_EQ(diagnostic.pid_calls, 2); EXPECT_EQ(diagnostic.committed_axes, 0);
	EXPECT_EQ(diagnostic.output_timestamp, 0u);
	lp.v_z_valid = true; step(12000); EXPECT_FALSE(diagnostic.valid); EXPECT_EQ(diagnostic.output_timestamp, 0u);
	mode.flag_multicopter_position_control_enabled = false; ASSERT_TRUE(mode_pub.publish(mode)); step(8000);
	EXPECT_EQ(diagnostic.pid_calls, 0); EXPECT_EQ(diagnostic.output_timestamp, 0u);
	mode.flag_multicopter_position_control_enabled = true; ASSERT_TRUE(mode_pub.publish(mode)); step(12000);
	EXPECT_FALSE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0); EXPECT_EQ(diagnostic.output_timestamp, 0u);
	disarm(); step(8000); EXPECT_FALSE(diagnostic.fault); arm(); step(12000);
	EXPECT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.z_phase, 2); EXPECT_EQ(diagnostic.committed_axes, 0);
}

TEST_F(RegularizedVelocityModule, ProductionZActualOutputUsesOldNuOneFfAndOnlyHorizontalPid)
{
	target.vz = -.004f; target.acceleration[2] = .002f;
	configureProductionZ(); ASSERT_TRUE(diagnostic.valid);
	float kp = 0.f, kd = 0.f;
	ASSERT_EQ(param_get(param_find("MPC_XY_VEL_P_ACC"), &kp), 0);
	ASSERT_EQ(param_get(param_find("MPC_XY_VEL_D_ACC"), &kd), 0);
	const float idle_z_integral = selection.integral[2];
	for (unsigned k = 0; k < 12; ++k) {
		const float before_integral[2]{selection.integral[0], selection.integral[1]};
		step(k % 2 ? 12000 : 8000); ASSERT_TRUE(diagnostic.valid);
		ASSERT_EQ(selection.effective_mode, 3); ASSERT_EQ(selection.effective_axes, 4);
		ASSERT_EQ(selection.variant_eff, 3); ASSERT_EQ(diagnostic.z_phase, 3);
		ASSERT_EQ(diagnostic.active_axes, 4); ASSERT_EQ(diagnostic.committed_axes, 4);
		EXPECT_NEAR(diagnostic.raw_dt, k % 2 ? .012f : .008f, 1.e-7f);
		EXPECT_EQ(diagnostic.pid_axes, 3); EXPECT_EQ(diagnostic.pid_calls, 1);
		EXPECT_EQ(diagnostic.inner_mode, 0); EXPECT_EQ(diagnostic.inner_axes, 0); EXPECT_EQ(diagnostic.inner_divisor, 1);
		EXPECT_EQ(selection.sta_gen, diagnostic.config_generation);
		EXPECT_FLOAT_EQ(selection.eps_eff[2], .02f);
		const double s = static_cast<double>(diagnostic.s[2]);
		const double eps = static_cast<double>(selection.eps_eff[2]);
		const double psi = std::fabs(s) <= eps ? s / std::sqrt(eps) : std::copysign(std::sqrt(std::fabs(s)), s);
		const double rho = std::fmax(-1., std::fmin(1., s / eps));
		EXPECT_NEAR(static_cast<double>(diagnostic.a_sta[2]), -2. * psi + static_cast<double>(diagnostic.nu_before[2]), 3e-7);
		EXPECT_NEAR(static_cast<double>(diagnostic.nu_ideal[2]), static_cast<double>(diagnostic.nu_before[2])
			- static_cast<double>(diagnostic.raw_dt) * rho, 3e-7);
		EXPECT_NEAR(diagnostic.a_req[2], diagnostic.a_sta[2] + target.acceleration[2], 3e-7f);
		EXPECT_FLOAT_EQ(selection.integral[2], idle_z_integral); // No idle Z PID integral in normal Z STA.
		for (int i = 0; i < 2; ++i) {
			EXPECT_TRUE(std::isnan(selection.eps_eff[i])); EXPECT_TRUE(std::isnan(diagnostic.nu_applied[i]));
			const float expected = kp * (diagnostic.v_sp[i] - diagnostic.v[i]) + before_integral[i] - kd * diagnostic.v_dot[i];
			EXPECT_NEAR(selection.correction[i], expected, 2e-6f);
			EXPECT_NEAR(diagnostic.a_req[i], expected + target.acceleration[i], 2e-6f);
		}
	}
}

TEST_F(RegularizedVelocityModule, ProductionZGroundContactAndReentryKeepBoundedOneSampleHandover)
{
	RegularizedVelocityModuleTestAccess::request(*module, 3, 4); step();
	ASSERT_EQ(selection.effective_axes, 4); ASSERT_EQ(selection.reject, 0);
	for (unsigned k = 0; k < 8; ++k) {
		step(k % 2 ? 12000 : 8000); ASSERT_TRUE(diagnostic.valid);
		EXPECT_EQ(diagnostic.z_phase, 1); EXPECT_EQ(diagnostic.committed_axes, 0);
		EXPECT_FLOAT_EQ(diagnostic.nu_applied[2], 0.f);
	}
	target.vz = -.004f; target.acceleration[2] = .002f;
	arm(); step(8000); ASSERT_TRUE(diagnostic.valid);
	EXPECT_EQ(diagnostic.z_phase, 2); EXPECT_EQ(diagnostic.committed_axes, 0); EXPECT_EQ(diagnostic.pid_axes, 7);
	step(12000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.z_phase, 3); EXPECT_EQ(diagnostic.committed_axes, 4);
	for (unsigned bounce = 0; bounce < 3; ++bounce) {
		land.ground_contact = true; ASSERT_TRUE(land_pub.publish(land)); step(8000);
		ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.z_phase, 1); EXPECT_EQ(diagnostic.committed_axes, 0);
		EXPECT_FLOAT_EQ(diagnostic.nu_applied[2], 0.f);
		// Ground suppression may make all target axes NaN; pid_axes is not a call count.
		EXPECT_EQ(diagnostic.pid_calls, 1); EXPECT_TRUE(diagnostic.pid_axes == 0 || diagnostic.pid_axes == 7);
		land.ground_contact = false; ASSERT_TRUE(land_pub.publish(land)); step(12000);
		ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.z_phase, 2); EXPECT_EQ(diagnostic.committed_axes, 0);
		step(8000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.z_phase, 3);
		EXPECT_EQ(diagnostic.pid_axes, 3); EXPECT_EQ(diagnostic.committed_axes, 4);
	}
	disarm(); step(12000); EXPECT_FLOAT_EQ(diagnostic.nu_applied[2], 0.f);
	arm(); step(8000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.z_phase, 2); EXPECT_EQ(diagnostic.committed_axes, 0);
	step(12000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 4);
}

TEST_F(RegularizedVelocityModule, ProductionZAndXArmedMaskRequestsCancelAndApplyOnlyOnDisarm)
{
	target.vz = -.004f; configureProductionZ();
	for (const int32_t next_axes : {1, 4}) {
		const int32_t previous_axes = selection.effective_axes;
		const uint32_t generation = selection.sta_gen;
		RegularizedVelocityModuleTestAccess::request(*module, 3, next_axes); step(8000);
		EXPECT_TRUE(selection.pending); EXPECT_EQ(selection.reject, 0); EXPECT_EQ(selection.effective_axes, previous_axes);
		EXPECT_EQ(selection.sta_gen, generation); EXPECT_TRUE(diagnostic.valid);
		RegularizedVelocityModuleTestAccess::request(*module, 3, previous_axes); step(12000);
		EXPECT_FALSE(selection.pending); EXPECT_FALSE(selection.sta_pending); EXPECT_EQ(selection.sta_gen, generation);
		RegularizedVelocityModuleTestAccess::request(*module, 3, next_axes); step(8000);
		disarm(); step(12000);
		ASSERT_EQ(selection.effective_mode, 3); ASSERT_EQ(selection.effective_axes, next_axes);
		EXPECT_FALSE(selection.pending); EXPECT_FALSE(selection.sta_pending); EXPECT_GT(selection.sta_gen, generation);
		const int selected_axis = next_axes == 4 ? 2 : 0;
		EXPECT_FLOAT_EQ(diagnostic.nu_applied[selected_axis], 0.f);
		arm(); step(8000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0);
		if (next_axes == 4) { EXPECT_EQ(diagnostic.z_phase, 2); }
		step(12000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, next_axes);
		EXPECT_EQ(diagnostic.pid_axes, next_axes == 4 ? 3 : 6);
	}
}

TEST_F(RegularizedVelocityModule, ProductionZEpsilonRequestsCancelAndApplyWithFreshState)
{
	target.vz = -.004f; configureProductionZ(); const uint32_t generation = selection.sta_gen;
	RegularizedVelocityModuleTestAccess::widths(*module, .01f, .01f, .03f); step(8000);
	EXPECT_TRUE(selection.sta_pending); EXPECT_FALSE(selection.pending); EXPECT_EQ(selection.sta_gen, generation);
	EXPECT_FLOAT_EQ(selection.eps_req[2], .03f); EXPECT_FLOAT_EQ(selection.eps_eff[2], .02f);
	RegularizedVelocityModuleTestAccess::widths(*module, .01f, .01f, .02f); step(12000);
	EXPECT_FALSE(selection.sta_pending); EXPECT_EQ(selection.sta_gen, generation);
	RegularizedVelocityModuleTestAccess::widths(*module, .01f, .01f, .03f); step(8000);
	disarm(); step(12000); EXPECT_FALSE(selection.sta_pending); EXPECT_GT(selection.sta_gen, generation);
	EXPECT_FLOAT_EQ(selection.eps_eff[2], .03f); EXPECT_FLOAT_EQ(diagnostic.nu_applied[2], 0.f);
	arm(); step(8000); EXPECT_EQ(diagnostic.z_phase, 2); EXPECT_EQ(diagnostic.committed_axes, 0);
	step(12000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 4);
	const uint32_t accepted = selection.sta_gen;
	disarm(); step(8000); RegularizedVelocityModuleTestAccess::widths(*module, .01f, .01f, NAN); step(12000);
	EXPECT_TRUE(selection.sta_reject); EXPECT_NE(selection.reject, 0); EXPECT_EQ(selection.sta_gen, accepted);
	EXPECT_TRUE(std::isnan(selection.eps_req[2])); EXPECT_FLOAT_EQ(selection.eps_eff[2], .03f);
}

TEST_F(RegularizedVelocityModule, ProductionZRealHoverEstimateUsesRegularizedCorrectionAndOneFf)
{
	int32_t enable_hte = 1; ASSERT_EQ(param_set(param_find("MPC_USE_HTE"), &enable_hte), 0);
	RegularizedVelocityModuleTestAccess::reload(*module);
	target.vz = -.004f; target.acceleration[2] = .002f;
	configureProductionZ(); step(8000); ASSERT_TRUE(diagnostic.valid);
	const auto before = diagnostic; ASSERT_EQ(before.constraint_bits & 6, 0);
	const double s = static_cast<double>(before.s[2]); const double eps = static_cast<double>(selection.eps_eff[2]);
	const double psi = std::fabs(s) <= eps ? s / std::sqrt(eps) : std::copysign(std::sqrt(std::fabs(s)), s);
	const double next_correction = -2. * psi + static_cast<double>(before.nu_applied[2]);
	const float next_hover = before.hover_thrust + .01f;
	const double expected_shift = (static_cast<double>(before.hover_thrust) / static_cast<double>(next_hover) - 1.)
		* (next_correction + static_cast<double>(target.acceleration[2]) - 9.80665);
	uORB::Publication<hover_thrust_estimate_s> publisher{ORB_ID(hover_thrust_estimate)};
	hover_thrust_estimate_s estimate{}; estimate.timestamp = hrt_absolute_time(); estimate.valid = true;
	estimate.hover_thrust = next_hover; ASSERT_TRUE(publisher.publish(estimate)); step(12000);
	ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.z_phase, 3); EXPECT_EQ(diagnostic.committed_axes, 4);
	EXPECT_EQ(diagnostic.pid_axes, 3); EXPECT_FLOAT_EQ(diagnostic.hover_thrust, next_hover);
	EXPECT_NEAR(diagnostic.z_hte_shift, expected_shift, 3e-6);
	EXPECT_NEAR(diagnostic.nu_before[2], static_cast<double>(before.nu_applied[2]) + expected_shift, 3e-6);
	EXPECT_NEAR(diagnostic.a_req[2], next_correction + expected_shift + static_cast<double>(target.acceleration[2]), 3e-6);
	// Compare the mapped current old-nu candidate, not the previous sample's
	// output: the previous sample has already advanced its integral once.
	const double expected_z_thrust = ((next_correction + static_cast<double>(target.acceleration[2])) / 9.80665 - 1.)
		* static_cast<double>(before.hover_thrust);
	EXPECT_NEAR(diagnostic.thrust[2], expected_z_thrust, 3e-6);
	for (int i = 0; i < 2; ++i) { EXPECT_TRUE(std::isnan(diagnostic.nu_applied[i])); }
}

TEST_F(RegularizedVelocityModule, ProductionZMeasurementFaultAndHteCannotClearLatchOrCommitTwice)
{
	int32_t enable_hte = 1; ASSERT_EQ(param_set(param_find("MPC_USE_HTE"), &enable_hte), 0);
	RegularizedVelocityModuleTestAccess::reload(*module);
	target.vz = -.004f; configureProductionZ(); lp.v_z_valid = false; step(8000);
	ASSERT_FALSE(diagnostic.valid); EXPECT_NE(diagnostic.first_fail, 0); EXPECT_EQ(diagnostic.pid_calls, 2);
	EXPECT_EQ(diagnostic.committed_axes, 0); EXPECT_EQ(diagnostic.output_timestamp, 0u);
	const auto failed = diagnostic; const uint32_t seq = selection.publish_seq;
	uORB::Publication<hover_thrust_estimate_s> publisher{ORB_ID(hover_thrust_estimate)};
	hover_thrust_estimate_s estimate{}; estimate.timestamp = hrt_absolute_time(); estimate.valid = true;
	estimate.hover_thrust = failed.hover_thrust + .01f; ASSERT_TRUE(publisher.publish(estimate));
	lp.v_z_valid = true; step(12000);
	EXPECT_EQ(selection.publish_seq, seq + 1); EXPECT_FALSE(diagnostic.valid); EXPECT_TRUE(diagnostic.fault);
	EXPECT_EQ(diagnostic.committed_axes, 0); EXPECT_EQ(diagnostic.output_timestamp, 0u);
	EXPECT_FLOAT_EQ(diagnostic.nu_applied[2], failed.nu_applied[2]); EXPECT_FLOAT_EQ(diagnostic.hover_thrust, failed.hover_thrust);
	disarm(); step(8000); EXPECT_FALSE(diagnostic.fault); EXPECT_FLOAT_EQ(diagnostic.nu_applied[2], 0.f);
	arm(); step(12000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.z_phase, 2); EXPECT_EQ(diagnostic.committed_axes, 0);
	step(8000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 4);
}

TEST_F(RegularizedVelocityModule, ProductionXYIndependentStateOldNuOneFfAndActualZPid)
{
	target.vz = -.004f; target.acceleration[2] = .003f;
	configureProductionXY(.7f, .2f, .02f);
	float kp_z = 0.f, ki_z = 0.f, kd_z = 0.f;
	ASSERT_EQ(param_get(param_find("MPC_Z_VEL_P_ACC"), &kp_z), 0);
	ASSERT_EQ(param_get(param_find("MPC_Z_VEL_I_ACC"), &ki_z), 0);
	ASSERT_EQ(param_get(param_find("MPC_Z_VEL_D_ACC"), &kd_z), 0);
	const double lambda1[2]{.5, .7}, lambda2[2]{.1, .2};
	for (unsigned k = 0; k < 12; ++k) {
		const float previous_nu[2]{diagnostic.nu_applied[0], diagnostic.nu_applied[1]};
		const float old_z_integral = selection.integral[2];
		step(k % 2 ? 12000 : 8000); ASSERT_TRUE(diagnostic.valid);
		ASSERT_EQ(selection.effective_mode, 3); ASSERT_EQ(selection.effective_axes, 3);
		EXPECT_EQ(selection.variant_eff, 3); EXPECT_EQ(selection.sta_gen, diagnostic.config_generation);
		EXPECT_EQ(diagnostic.active_axes, 3); EXPECT_EQ(diagnostic.committed_axes, 3);
		EXPECT_EQ(diagnostic.pid_axes, 4); EXPECT_EQ(diagnostic.pid_calls, 1); // One module update, not a kernel-call count.
		EXPECT_EQ(diagnostic.inner_mode, 0); EXPECT_EQ(diagnostic.inner_axes, 0); EXPECT_EQ(diagnostic.inner_divisor, 1);
		EXPECT_EQ(diagnostic.constraint_bits, 0); EXPECT_EQ(diagnostic.z_phase, 0);
		EXPECT_NEAR(diagnostic.raw_dt, k % 2 ? .012f : .008f, 1.e-7f);
		for (int i = 0; i < 2; ++i) {
			const double s = static_cast<double>(diagnostic.s[i]);
			const double eps = static_cast<double>(selection.eps_eff[i]);
			const double psi = std::fabs(s) <= eps ? s / std::sqrt(eps) : std::copysign(std::sqrt(std::fabs(s)), s);
			const double rho = std::fmax(-1., std::fmin(1., s / eps));
			EXPECT_FLOAT_EQ(diagnostic.nu_before[i], previous_nu[i]);
			EXPECT_NEAR(static_cast<double>(diagnostic.a_sta[i]), -lambda1[i] * psi + static_cast<double>(previous_nu[i]), 3e-7);
			EXPECT_NEAR(static_cast<double>(diagnostic.nu_ideal[i]), static_cast<double>(previous_nu[i])
				- static_cast<double>(diagnostic.raw_dt) * lambda2[i] * rho, 3e-7);
			EXPECT_NEAR(diagnostic.nu_applied[i], diagnostic.nu_ideal[i], 3e-7f);
			EXPECT_NEAR(diagnostic.a_req[i], diagnostic.a_sta[i] + target.acceleration[i], 3e-7f);
			EXPECT_FLOAT_EQ(selection.integral[i], 0.f);
		}
		EXPECT_TRUE(std::isnan(selection.eps_eff[2])); EXPECT_TRUE(std::isnan(diagnostic.nu_applied[2]));
		const float z_error = diagnostic.v_sp[2] - diagnostic.v[2];
		const float expected_z = kp_z * z_error + old_z_integral - kd_z * diagnostic.v_dot[2];
		EXPECT_NEAR(selection.correction[2], expected_z, 2e-6f);
		EXPECT_NEAR(diagnostic.a_req[2], expected_z + target.acceleration[2], 2e-6f);
		EXPECT_NEAR(selection.integral[2], old_z_integral + z_error * ki_z * diagnostic.used_dt, 2e-6f);
	}
	EXPECT_LT(diagnostic.nu_applied[0] * diagnostic.nu_applied[1], 0.f);
	// Hold Y error exactly zero while changing X. Y still has a legal finite
	// target and nonzero acceleration FF, but its retained nu must not follow X.
	target.vy = 0.f; const float held_y_nu = diagnostic.nu_applied[1];
	for (unsigned k = 0; k < 6; ++k) {
		target.vx = k % 2 ? -.005f : .004f; step(k % 2 ? 12000 : 8000);
		ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 3);
		EXPECT_FLOAT_EQ(diagnostic.s[1], 0.f); EXPECT_FLOAT_EQ(diagnostic.nu_before[1], held_y_nu);
		EXPECT_FLOAT_EQ(diagnostic.nu_applied[1], held_y_nu);
		EXPECT_NEAR(diagnostic.a_req[1], held_y_nu + target.acceleration[1], 3e-7f);
	}
}

TEST_F(RegularizedVelocityModule, ProductionXYUnusedHorizontalPidCannotContaminateNormalOutput)
{
	configureProductionXY(); const uint32_t generation = selection.sta_gen;
	ASSERT_EQ(selection.effective_mode, 3); ASSERT_EQ(selection.effective_axes, 3);
	RegularizedVelocityModuleTestAccess::poisonIdleXyPid(*module);
	for (unsigned k = 0; k < 4; ++k) {
		step(k % 2 ? 12000 : 8000); ASSERT_TRUE(diagnostic.valid);
		ASSERT_EQ(selection.effective_mode, 3); ASSERT_EQ(selection.effective_axes, 3);
		EXPECT_EQ(selection.variant_eff, 3); EXPECT_EQ(selection.sta_gen, generation);
		EXPECT_EQ(selection.reject, 0); EXPECT_FALSE(selection.pending); EXPECT_FALSE(selection.sta_pending);
		EXPECT_EQ(diagnostic.pid_axes, 4); EXPECT_EQ(diagnostic.committed_axes, 3);
		for (int i = 0; i < 3; ++i) { EXPECT_TRUE(std::isfinite(diagnostic.a_req[i])); EXPECT_TRUE(std::isfinite(diagnostic.thrust[i])); }
		EXPECT_FLOAT_EQ(selection.integral[0], 0.f); EXPECT_FLOAT_EQ(selection.integral[1], 0.f);
	}
	// Do not use poisoned gains to draw claims about PID, ground or switching.
	// Only this test controller object's unused gains were changed; no parameter
	// storage, production admission or mode/gain reload was involved.
}

TEST_F(RegularizedVelocityModule, ProductionXYGroundContactAndControlReentryResetBothStates)
{
	RegularizedVelocityModuleTestAccess::request(*module, 3, 3); step();
	ASSERT_EQ(selection.effective_axes, 3); EXPECT_EQ(selection.reject, 0);
	for (unsigned k = 0; k < 8; ++k) {
		step(k % 2 ? 12000 : 8000); ASSERT_TRUE(diagnostic.valid);
		EXPECT_EQ(diagnostic.committed_axes, 0);
		EXPECT_FLOAT_EQ(diagnostic.nu_applied[0], 0.f); EXPECT_FLOAT_EQ(diagnostic.nu_applied[1], 0.f);
	}
	arm(); step(8000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0);
	step(12000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 3);
	for (unsigned bounce = 0; bounce < 3; ++bounce) {
		land.ground_contact = true; ASSERT_TRUE(land_pub.publish(land)); step(8000);
		ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0);
		EXPECT_FLOAT_EQ(diagnostic.nu_applied[0], 0.f); EXPECT_FLOAT_EQ(diagnostic.nu_applied[1], 0.f);
		land.ground_contact = false; ASSERT_TRUE(land_pub.publish(land)); step(12000);
		ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0);
		EXPECT_FLOAT_EQ(diagnostic.nu_applied[0], 0.f); EXPECT_FLOAT_EQ(diagnostic.nu_applied[1], 0.f);
		step(8000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 3); EXPECT_EQ(diagnostic.pid_axes, 4);
	}
	mode.flag_multicopter_position_control_enabled = false; ASSERT_TRUE(mode_pub.publish(mode)); step(12000);
	EXPECT_EQ(diagnostic.pid_calls, 0); EXPECT_EQ(diagnostic.output_timestamp, 0u); EXPECT_EQ(diagnostic.committed_axes, 0);
	mode.flag_multicopter_position_control_enabled = true; ASSERT_TRUE(mode_pub.publish(mode)); step(8000);
	ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0);
	EXPECT_FLOAT_EQ(diagnostic.nu_applied[0], 0.f); EXPECT_FLOAT_EQ(diagnostic.nu_applied[1], 0.f);
	step(12000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 3);
	disarm(); step(8000); EXPECT_FLOAT_EQ(diagnostic.nu_applied[0], 0.f); EXPECT_FLOAT_EQ(diagnostic.nu_applied[1], 0.f);
}

TEST_F(RegularizedVelocityModule, ProductionXYAndXMaskRequestsCancelAndApplyOnlyDisarmed)
{
	configureProductionXY();
	// MODE3 XZ remains unavailable in gate D; retain the armed rejection/cancel probe.
	RegularizedVelocityModuleTestAccess::request(*module, 3, 5); step(8000);
	EXPECT_TRUE(selection.pending); EXPECT_NE(selection.reject, 0); EXPECT_EQ(selection.effective_axes, 3);
	RegularizedVelocityModuleTestAccess::request(*module, 3, 3); step(12000);
	EXPECT_FALSE(selection.pending); EXPECT_EQ(selection.reject, 0);
	for (const int32_t next_axes : {1, 3}) {
		const int32_t previous_axes = selection.effective_axes; const uint32_t generation = selection.sta_gen;
		RegularizedVelocityModuleTestAccess::request(*module, 3, next_axes); step(8000);
		EXPECT_TRUE(selection.pending); EXPECT_EQ(selection.reject, 0); EXPECT_EQ(selection.effective_axes, previous_axes);
		EXPECT_EQ(selection.sta_gen, generation); EXPECT_TRUE(diagnostic.valid);
		RegularizedVelocityModuleTestAccess::request(*module, 3, previous_axes); step(12000);
		EXPECT_FALSE(selection.pending); EXPECT_FALSE(selection.sta_pending); EXPECT_EQ(selection.sta_gen, generation);
		RegularizedVelocityModuleTestAccess::request(*module, 3, next_axes); step(8000); disarm(); step(12000);
		ASSERT_EQ(selection.effective_axes, next_axes); EXPECT_FALSE(selection.pending); EXPECT_GT(selection.sta_gen, generation);
		for (int i = 0; i < 2; ++i) {
			if (next_axes & (1 << i)) { EXPECT_FLOAT_EQ(diagnostic.nu_applied[i], 0.f); }
			else { EXPECT_TRUE(std::isnan(diagnostic.nu_applied[i])); }
		}
		arm(); step(8000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0);
		step(12000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, next_axes);
		EXPECT_EQ(diagnostic.pid_axes, next_axes == 3 ? 4 : 6);
	}
}

TEST_F(RegularizedVelocityModule, ProductionXYAlgorithmRequestsCancelAndResetStateAcrossDisarm)
{
	configureProductionXY();
	for (const int32_t next_mode : {1, 0, 3}) {
		const int32_t previous_mode = selection.effective_mode;
		const uint32_t generation = selection.sta_gen;
		RegularizedVelocityModuleTestAccess::request(*module, next_mode, next_mode ? 3 : 0); step(8000);
		EXPECT_TRUE(selection.pending); EXPECT_EQ(selection.reject, 0); EXPECT_EQ(selection.effective_mode, previous_mode);
		EXPECT_EQ(selection.sta_gen, generation);
		RegularizedVelocityModuleTestAccess::request(*module, previous_mode, previous_mode ? 3 : 0); step(12000);
		EXPECT_FALSE(selection.pending); EXPECT_FALSE(selection.sta_pending); EXPECT_EQ(selection.sta_gen, generation);
		RegularizedVelocityModuleTestAccess::request(*module, next_mode, next_mode ? 3 : 0); step(8000);
		disarm(); step(12000); ASSERT_EQ(selection.effective_mode, next_mode);
		EXPECT_EQ(selection.effective_axes, next_mode ? 3 : 0); EXPECT_FALSE(selection.pending);
		for (int i = 0; i < 2; ++i) {
			if (next_mode) { EXPECT_FLOAT_EQ(diagnostic.nu_applied[i], 0.f); }
			else { EXPECT_TRUE(std::isnan(diagnostic.nu_applied[i])); }
			if (next_mode == 3) { EXPECT_FLOAT_EQ(selection.eps_eff[i], .01f); }
			else { EXPECT_TRUE(std::isnan(selection.eps_eff[i])); }
		}
		arm(); step(8000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0);
		step(12000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, next_mode ? 3 : 0);
		EXPECT_EQ(diagnostic.pid_axes, next_mode ? 4 : 7);
	}
}

TEST_F(RegularizedVelocityModule, ProductionXYRealHoverEstimateKeepsOriginalZPidAndNoHorizontalRebase)
{
	int32_t enable_hte = 1; ASSERT_EQ(param_set(param_find("MPC_USE_HTE"), &enable_hte), 0);
	RegularizedVelocityModuleTestAccess::reload(*module);
	target.vz = -.004f; target.acceleration[2] = .003f; configureProductionXY(); step(8000);
	ASSERT_TRUE(diagnostic.valid); const auto before = diagnostic;
	const float old_z_integral = selection.integral[2];
	float kp_z = 0.f, ki_z = 0.f, kd_z = 0.f;
	ASSERT_EQ(param_get(param_find("MPC_Z_VEL_P_ACC"), &kp_z), 0);
	ASSERT_EQ(param_get(param_find("MPC_Z_VEL_I_ACC"), &ki_z), 0);
	ASSERT_EQ(param_get(param_find("MPC_Z_VEL_D_ACC"), &kd_z), 0);
	const float next_hover = before.hover_thrust + .01f;
	const double hte_integral_shift = (static_cast<double>(next_hover) - static_cast<double>(before.hover_thrust))
		* (9.80665 / static_cast<double>(next_hover));
	uORB::Publication<hover_thrust_estimate_s> publisher{ORB_ID(hover_thrust_estimate)};
	hover_thrust_estimate_s estimate{}; estimate.timestamp = hrt_absolute_time(); estimate.valid = true;
	estimate.hover_thrust = next_hover; ASSERT_TRUE(publisher.publish(estimate)); step(12000);
	ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 3); EXPECT_EQ(diagnostic.pid_axes, 4);
	EXPECT_EQ(diagnostic.constraint_bits & 6, 0); EXPECT_FLOAT_EQ(diagnostic.hover_thrust, next_hover);
	EXPECT_FLOAT_EQ(diagnostic.z_hte_shift, 0.f); // Z remains PID; no Z nu exists here.
	EXPECT_TRUE(std::isnan(diagnostic.nu_applied[2]));
	for (int i = 0; i < 2; ++i) { EXPECT_FLOAT_EQ(diagnostic.nu_before[i], before.nu_applied[i]); }
	const float error = diagnostic.v_sp[2] - diagnostic.v[2];
	const double expected = static_cast<double>(kp_z * error - kd_z * diagnostic.v_dot[2])
		+ static_cast<double>(old_z_integral) + hte_integral_shift;
	EXPECT_NEAR(selection.correction[2], expected, 3e-6);
	EXPECT_NEAR(diagnostic.a_req[2], expected + static_cast<double>(target.acceleration[2]), 3e-6);
	EXPECT_NEAR(selection.integral[2], static_cast<double>(old_z_integral) + hte_integral_shift
		+ static_cast<double>(error * ki_z * diagnostic.used_dt), 3e-6);
}

TEST_F(RegularizedVelocityModule, ProductionXYFaultRetryCannotPartiallyCommitOrClearByControlReentry)
{
	configureProductionXY(); const auto before = diagnostic; const uint32_t sequence = selection.publish_seq;
	rate_fault = true; step(8000);
	EXPECT_EQ(selection.publish_seq, sequence + 1); EXPECT_EQ(diagnostic.pid_calls, 2);
	EXPECT_FALSE(diagnostic.valid); EXPECT_TRUE(diagnostic.fault); EXPECT_NE(diagnostic.first_fail, 0);
	EXPECT_EQ(diagnostic.committed_axes, 0); EXPECT_EQ(diagnostic.output_timestamp, 0u);
	for (int i = 0; i < 2; ++i) { EXPECT_FLOAT_EQ(diagnostic.nu_applied[i], before.nu_applied[i]); }
	rate_fault = false; step(12000); EXPECT_FALSE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0);
	mode.flag_multicopter_position_control_enabled = false; ASSERT_TRUE(mode_pub.publish(mode)); step(8000);
	EXPECT_EQ(diagnostic.pid_calls, 0); EXPECT_EQ(diagnostic.output_timestamp, 0u);
	mode.flag_multicopter_position_control_enabled = true; ASSERT_TRUE(mode_pub.publish(mode)); step(12000);
	EXPECT_FALSE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0); EXPECT_EQ(diagnostic.output_timestamp, 0u);
	disarm(); step(8000); EXPECT_FALSE(diagnostic.fault);
	for (int i = 0; i < 2; ++i) { EXPECT_FLOAT_EQ(diagnostic.nu_applied[i], 0.f); }
	arm(); step(12000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0);
	step(8000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 3);
}

TEST_F(RegularizedVelocityModule, ProductionXYZIndependentStateOneFfRealSampleClockAndJoinedMode)
{
	target.vz = -.004f; target.acceleration[2] = .003f; configureProductionXYZ(.7f, .2f, .02f);
	const double lambda1[3]{.5, .7, 2.}, lambda2[3]{.1, .2, 1.};
	for (unsigned k = 0; k < 12; ++k) {
		const auto before = diagnostic;
		step(k % 2 ? 12000 : 8000, k % 2 ? 4000 : 0); ASSERT_TRUE(diagnostic.valid);
		ASSERT_EQ(selection.effective_mode, 3); ASSERT_EQ(selection.effective_axes, 7);
		EXPECT_EQ(selection.variant_eff, 3); EXPECT_EQ(selection.sta_gen, diagnostic.config_generation);
		EXPECT_EQ(diagnostic.active_axes, 7); EXPECT_EQ(diagnostic.committed_axes, 7);
		EXPECT_EQ(diagnostic.pid_axes, 0); EXPECT_EQ(diagnostic.pid_calls, 1);
		// pid_calls counts PositionControl updates, not invocations of a PID kernel.
		EXPECT_EQ(diagnostic.inner_mode, 0); EXPECT_EQ(diagnostic.inner_axes, 0); EXPECT_EQ(diagnostic.inner_divisor, 1);
		EXPECT_EQ(diagnostic.constraint_bits, 0); EXPECT_EQ(diagnostic.z_phase, 3);
		EXPECT_NEAR(diagnostic.raw_dt, k % 2 ? .012f : .008f, 1.e-7f);
		EXPECT_EQ(selection.input_timestamp - selection.timestamp_sample, k % 2 ? 4000u : 0u);
		for (int i = 0; i < 3; ++i) {
			const double s = static_cast<double>(diagnostic.s[i]), eps = static_cast<double>(selection.eps_eff[i]);
			const double psi = std::fabs(s) <= eps ? s / std::sqrt(eps) : std::copysign(std::sqrt(std::fabs(s)), s);
			const double rho = std::fmax(-1., std::fmin(1., s / eps));
			EXPECT_FLOAT_EQ(diagnostic.nu_before[i], before.nu_applied[i]);
			EXPECT_NEAR(static_cast<double>(diagnostic.a_sta[i]), -lambda1[i] * psi + static_cast<double>(before.nu_applied[i]), 3e-7);
			EXPECT_NEAR(static_cast<double>(diagnostic.nu_ideal[i]), static_cast<double>(before.nu_applied[i])
				- static_cast<double>(diagnostic.raw_dt) * lambda2[i] * rho, 3e-7);
			EXPECT_FLOAT_EQ(diagnostic.nu_applied[i], diagnostic.nu_ideal[i]);
			EXPECT_NEAR(diagnostic.a_req[i], diagnostic.a_sta[i] + target.acceleration[i], 3e-7f);
			EXPECT_FLOAT_EQ(selection.integral[i], 0.f); EXPECT_TRUE(std::isfinite(diagnostic.thrust[i]));
		}
	}
	// Legal XYZ targets, but Y/Z exact-zero error: only X changes its own nu.
	target.vy = target.vz = 0.f;
	const float held_y = diagnostic.nu_applied[1], held_z = diagnostic.nu_applied[2];
	for (unsigned k = 0; k < 6; ++k) {
		target.vx = k % 2 ? -.005f : .004f; step(k % 2 ? 12000 : 8000);
		ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 7);
		EXPECT_FLOAT_EQ(diagnostic.s[1], 0.f); EXPECT_FLOAT_EQ(diagnostic.s[2], 0.f);
		EXPECT_FLOAT_EQ(diagnostic.nu_applied[1], held_y); EXPECT_FLOAT_EQ(diagnostic.nu_applied[2], held_z);
	}
}

TEST_F(RegularizedVelocityModule, ProductionXYZNormalUnusedPidPoisonDoesNotTouchParameterStore)
{
	configureProductionXYZ(); const uint32_t generation = selection.sta_gen;
	const char *names[6]{"MPC_XY_VEL_P_ACC", "MPC_XY_VEL_I_ACC", "MPC_XY_VEL_D_ACC",
		"MPC_Z_VEL_P_ACC", "MPC_Z_VEL_I_ACC", "MPC_Z_VEL_D_ACC"};
	float before[6]{};
	for (int i = 0; i < 6; ++i) { ASSERT_EQ(param_get(param_find(names[i]), &before[i]), 0); ASSERT_TRUE(std::isfinite(before[i])); }
	RegularizedVelocityModuleTestAccess::poisonAllIdleVelocityPid(*module);
	for (unsigned k = 0; k < 4; ++k) {
		step(k % 2 ? 12000 : 8000); ASSERT_TRUE(diagnostic.valid);
		ASSERT_EQ(selection.effective_mode, 3); ASSERT_EQ(selection.effective_axes, 7);
		EXPECT_EQ(selection.sta_gen, generation); EXPECT_EQ(selection.reject, 0); EXPECT_FALSE(selection.pending);
		EXPECT_EQ(diagnostic.pid_axes, 0); EXPECT_EQ(diagnostic.committed_axes, 7); EXPECT_EQ(diagnostic.z_phase, 3);
		for (int i = 0; i < 3; ++i) {
			EXPECT_TRUE(std::isfinite(diagnostic.a_req[i])); EXPECT_TRUE(std::isfinite(diagnostic.thrust[i]));
			EXPECT_FLOAT_EQ(selection.integral[i], 0.f);
		}
	}
	for (int i = 0; i < 6; ++i) {
		float after = NAN; ASSERT_EQ(param_get(param_find(names[i]), &after), 0); EXPECT_FLOAT_EQ(after, before[i]);
	}
	// Do not use these poisoned object gains for ground/landing, mode changes
	// or fallback claims. The object is destroyed at fixture teardown.
}

TEST_F(RegularizedVelocityModule, ProductionXYZGroundContactTerminationAndFreshOneFrameHandover)
{
	RegularizedVelocityModuleTestAccess::request(*module, 3, 7); step();
	ASSERT_EQ(selection.effective_axes, 7); EXPECT_EQ(selection.reject, 0);
	for (unsigned k = 0; k < 8; ++k) {
		step(k % 2 ? 12000 : 8000); ASSERT_TRUE(diagnostic.valid);
		EXPECT_EQ(diagnostic.z_phase, 1); EXPECT_EQ(diagnostic.committed_axes, 0);
		for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(diagnostic.nu_applied[i], 0.f); }
	}
	arm(); step(8000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.z_phase, 2);
	EXPECT_EQ(diagnostic.committed_axes, 0); EXPECT_EQ(diagnostic.pid_axes, 7);
	step(12000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 7); EXPECT_EQ(diagnostic.pid_axes, 0);
	for (unsigned bounce = 0; bounce < 2; ++bounce) {
		land.ground_contact = true; ASSERT_TRUE(land_pub.publish(land)); step(8000);
		ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.z_phase, 1); EXPECT_EQ(diagnostic.committed_axes, 0);
		for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(diagnostic.nu_applied[i], 0.f); }
		land.ground_contact = false; ASSERT_TRUE(land_pub.publish(land)); step(12000);
		ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.z_phase, 2); EXPECT_EQ(diagnostic.committed_axes, 0);
		step(8000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 7);
	}
	const auto before = diagnostic; const uint32_t sequence = selection.publish_seq;
	rate_termination = true; step(12000);
	EXPECT_EQ(selection.publish_seq, sequence + 1); EXPECT_EQ(diagnostic.pid_calls, 2);
	EXPECT_FALSE(diagnostic.valid); EXPECT_TRUE(diagnostic.fault); EXPECT_NE(diagnostic.first_fail, 0);
	EXPECT_EQ(diagnostic.committed_axes, 0); EXPECT_EQ(diagnostic.output_timestamp, 0u);
	for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(diagnostic.nu_applied[i], before.nu_applied[i]); }
	rate_termination = false; step(8000); EXPECT_FALSE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0);
	disarm(); step(12000); EXPECT_FALSE(diagnostic.fault);
	for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(diagnostic.nu_applied[i], 0.f); }
	arm(); step(8000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.z_phase, 2); EXPECT_EQ(diagnostic.committed_axes, 0);
	step(12000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 7); EXPECT_EQ(diagnostic.pid_axes, 0);
}

TEST_F(RegularizedVelocityModule, ProductionXYZMasksModesStageCancelAndResetOnlyAfterDisarm)
{
	configureProductionXYZ();
	for (const int32_t next_axes : {1, 4, 3, 7}) {
		const int32_t previous_axes = selection.effective_axes; const uint32_t generation = selection.sta_gen;
		RegularizedVelocityModuleTestAccess::request(*module, 3, next_axes); step(8000);
		EXPECT_TRUE(selection.pending); EXPECT_EQ(selection.reject, 0); EXPECT_EQ(selection.effective_axes, previous_axes);
		EXPECT_EQ(selection.sta_gen, generation);
		RegularizedVelocityModuleTestAccess::request(*module, 3, previous_axes); step(12000);
		EXPECT_FALSE(selection.pending); EXPECT_FALSE(selection.sta_pending); EXPECT_EQ(selection.sta_gen, generation);
		RegularizedVelocityModuleTestAccess::request(*module, 3, next_axes); step(8000); disarm(); step(12000);
		ASSERT_EQ(selection.effective_axes, next_axes); EXPECT_FALSE(selection.pending);
		for (int i = 0; i < 3; ++i) {
			if (next_axes & (1 << i)) { EXPECT_FLOAT_EQ(diagnostic.nu_applied[i], 0.f); }
			else { EXPECT_TRUE(std::isnan(diagnostic.nu_applied[i])); }
		}
		arm(); step(8000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0);
		step(12000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, next_axes);
		EXPECT_EQ(diagnostic.pid_axes, 7 ^ next_axes);
	}
	for (const int32_t next_mode : {1, 0, 3}) {
		const int32_t previous_mode = selection.effective_mode; const uint32_t generation = selection.sta_gen;
		RegularizedVelocityModuleTestAccess::request(*module, next_mode, next_mode ? 7 : 0); step(8000);
		EXPECT_TRUE(selection.pending); EXPECT_EQ(selection.effective_mode, previous_mode); EXPECT_EQ(selection.sta_gen, generation);
		RegularizedVelocityModuleTestAccess::request(*module, previous_mode, previous_mode ? 7 : 0); step(12000);
		EXPECT_FALSE(selection.pending); EXPECT_FALSE(selection.sta_pending); EXPECT_EQ(selection.sta_gen, generation);
		RegularizedVelocityModuleTestAccess::request(*module, next_mode, next_mode ? 7 : 0); step(8000);
		disarm(); step(12000); ASSERT_EQ(selection.effective_mode, next_mode); EXPECT_EQ(selection.effective_axes, next_mode ? 7 : 0);
		for (int i = 0; i < 3; ++i) {
			if (next_mode) { EXPECT_FLOAT_EQ(diagnostic.nu_applied[i], 0.f); }
			else { EXPECT_TRUE(std::isnan(diagnostic.nu_applied[i])); }
			if (next_mode == 3) { EXPECT_TRUE(std::isfinite(selection.eps_eff[i])); }
			else { EXPECT_TRUE(std::isnan(selection.eps_eff[i])); }
		}
		arm(); step(8000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0);
		step(12000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, next_mode ? 7 : 0);
		EXPECT_EQ(diagnostic.pid_axes, next_mode ? 0 : 7);
	}
}

TEST_F(RegularizedVelocityModule, ProductionXYZRealHtePreservesCurrentCollectiveAndNeverRebasesXy)
{
	int32_t enable_hte = 1; ASSERT_EQ(param_set(param_find("MPC_USE_HTE"), &enable_hte), 0);
	RegularizedVelocityModuleTestAccess::reload(*module);
	target.vz = -.004f; target.acceleration[2] = .003f; configureProductionXYZ(); step(8000);
	ASSERT_TRUE(diagnostic.valid); const auto before = diagnostic; ASSERT_EQ(before.constraint_bits & 6, 0);
	const double s = static_cast<double>(before.s[2]), eps = static_cast<double>(selection.eps_eff[2]);
	const double psi = std::fabs(s) <= eps ? s / std::sqrt(eps) : std::copysign(std::sqrt(std::fabs(s)), s);
	const double correction = -2. * psi + static_cast<double>(before.nu_applied[2]);
	const float next_hover = before.hover_thrust + .01f;
	const double shift = (static_cast<double>(before.hover_thrust) / static_cast<double>(next_hover) - 1.)
		* (correction + static_cast<double>(target.acceleration[2]) - 9.80665);
	uORB::Publication<hover_thrust_estimate_s> publisher{ORB_ID(hover_thrust_estimate)};
	hover_thrust_estimate_s estimate{}; estimate.timestamp = hrt_absolute_time(); estimate.valid = true;
	estimate.hover_thrust = next_hover; ASSERT_TRUE(publisher.publish(estimate)); step(12000);
	ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 7); EXPECT_EQ(diagnostic.pid_axes, 0);
	EXPECT_FLOAT_EQ(diagnostic.hover_thrust, next_hover); EXPECT_NEAR(diagnostic.z_hte_shift, shift, 3e-6);
	EXPECT_NEAR(diagnostic.nu_before[2], static_cast<double>(before.nu_applied[2]) + shift, 3e-6);
	EXPECT_NEAR(diagnostic.a_req[2], correction + shift + static_cast<double>(target.acceleration[2]), 3e-6);
	const double expected_thrust_z = ((correction + static_cast<double>(target.acceleration[2])) / 9.80665 - 1.)
		* static_cast<double>(before.hover_thrust);
	EXPECT_NEAR(diagnostic.thrust[2], expected_thrust_z, 3e-6);
	for (int i = 0; i < 2; ++i) { EXPECT_FLOAT_EQ(diagnostic.nu_before[i], before.nu_applied[i]); }
	for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(selection.integral[i], 0.f); }
}
