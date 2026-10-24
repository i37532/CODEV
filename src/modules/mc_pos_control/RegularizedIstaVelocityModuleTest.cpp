// SPDX-License-Identifier: BSD-3-Clause
// RI02/RI03: synchronous real Run/uORB execution, not Gazebo flights.
#include <gtest/gtest.h>
#define MODULE_NAME "mc_pos_control_rista_test"
#include "MulticopterPositionControl.hpp"
#include <platforms/posix/apps.h>
#include <parameters/param.h>
#include <px4_platform_common/px4_work_queue/WorkQueueManager.hpp>
#include <cmath>
#include <cstdio>
#include <unistd.h>

extern "C" void __wrap_hrt_call_after(hrt_call *, hrt_abstime, hrt_callout, void *) {}
extern "C" void __wrap_hrt_cancel(hrt_call *) {}

class RegularizedIstaVelocityModuleTestAccess
{
public:
	static void step(MulticopterPositionControl &m) { m.Run(); m.ScheduleClear(); }
	static void admit(MulticopterPositionControl &m) { m._control._regularized_ista_admission = true; }
	static void airborne(MulticopterPositionControl &m, uint64_t time)
	{
		m._takeoff.updateTakeoffState(true, false, false, 1.f, true, time);
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
		m._param_mpc_vc_eps_x.set(.01f); m._param_mpc_vc_eps_y.set(.01f); m._param_mpc_vc_eps_z.set(.02f);
	}
	static void width(MulticopterPositionControl &m, float x) { m._param_mpc_vc_eps_x.set(x); }
	static void divisor(MulticopterPositionControl &m, int32_t div) { m._param_mpc_vc_div.set(div); }
	static void reload(MulticopterPositionControl &m) { m.parameters_update(true); }
	static void fastSpool(MulticopterPositionControl &m) { m._takeoff.setSpoolupTime(.008f); }
	static void poisonPid(MulticopterPositionControl &m)
	{
		m._control.setVelocityGains(matrix::Vector3f(NAN, NAN, NAN), matrix::Vector3f(NAN, NAN, NAN),
					    matrix::Vector3f(NAN, NAN, NAN));
	}
};

class RistaQueueAnchor : public px4::WorkItem
{
public:
	RistaQueueAnchor() : WorkItem("rista_test_anchor", px4::wq_configurations::nav_and_controllers) {}
	void Run() override {}
};
static RistaQueueAnchor *rista_queue_anchor = nullptr;

// WorkQueueManager is process-scoped. Keep one lifetime across the offline,
// production-X and parameterized failure suites, including filtered test runs.
class RistaQueueEnvironment : public ::testing::Environment
{
public:
	void SetUp() override
	{
		ASSERT_EQ(px4::WorkQueueManagerStart(), 0); px4_usleep(20000); rista_queue_anchor = new RistaQueueAnchor();
	}
	void TearDown() override
	{
		delete rista_queue_anchor; rista_queue_anchor = nullptr; px4_usleep(20000);
		EXPECT_EQ(px4::WorkQueueManagerStop(), 0);
	}
};
::testing::Environment *const rista_queue_environment = ::testing::AddGlobalTestEnvironment(new RistaQueueEnvironment());

class RegularizedIstaVelocityModule : public ::testing::Test
{
protected:
	uORB::Publication<vehicle_local_position_s> lp_pub{ORB_ID(vehicle_local_position)};
	uORB::Publication<vehicle_local_position_setpoint_s> target_pub{ORB_ID(trajectory_setpoint)};
	uORB::Publication<vehicle_control_mode_s> mode_pub{ORB_ID(vehicle_control_mode)};
	uORB::Publication<vehicle_land_detected_s> land_pub{ORB_ID(vehicle_land_detected)};
	uORB::Publication<vehicle_constraints_s> limits_pub{ORB_ID(vehicle_constraints)};
	uORB::Publication<sta_rate_ctrl_status_s> rate_pub{ORB_ID(sta_rate_ctrl_status)};
	uORB::Subscription selection_sub{ORB_ID(velocity_ctrl_selection)};
	uORB::Subscription diagnostic_sub{ORB_ID(sta_velocity_ctrl_status)};
	uORB::Subscription output_sub{ORB_ID(vehicle_local_position_setpoint)};
	vehicle_local_position_s lp{};
	vehicle_local_position_setpoint_s target{};
	vehicle_control_mode_s mode{};
	vehicle_land_detected_s land{};
	velocity_ctrl_selection_s selection{};
	sta_velocity_ctrl_status_s diagnostic{};
	vehicle_local_position_setpoint_s output{};
	MulticopterPositionControl *module {nullptr};
	uint32_t previous_seq{0};
	bool rate_fault{false}, rate_termination{false}, publish_target{true};
	void SetUp() override
	{
		apps_map_type apps; init_app_map(apps); ASSERT_TRUE(apps.empty());
		param_control_autosave(false); param_reset_all(); module = new MulticopterPositionControl();
		lp.timestamp = lp.timestamp_sample = 1000000;
		lp.xy_valid = lp.z_valid = lp.v_xy_valid = lp.v_z_valid = true;
		lp.x = 5.f; lp.y = -2.f; lp.z = -2.5f; lp.heading = .2f;
		target.x = lp.x; target.y = lp.y; target.z = lp.z;
		target.vx = .004f; target.vy = -.003f; target.vz = 0.f; target.yaw = lp.heading;
		target.acceleration[0] = .002f; target.acceleration[1] = -.001f;
		mode.flag_multicopter_position_control_enabled = mode.flag_control_auto_enabled = true;
		land.landed = land.ground_contact = true;
		vehicle_constraints_s limits{}; limits.speed_xy = 5.f; limits.speed_up = 3.f; limits.speed_down = 1.f;
		limits.want_takeoff = true;
		ASSERT_TRUE(mode_pub.publish(mode)); ASSERT_TRUE(land_pub.publish(land)); ASSERT_TRUE(limits_pub.publish(limits));
	}
	void TearDown() override { delete module; param_reset_all(); }
	void step(uint64_t dt = 10000, uint64_t delay = 0)
	{
		lp.timestamp_sample += dt; lp.timestamp = lp.timestamp_sample + delay;

		if (publish_target) { target.timestamp = lp.timestamp; EXPECT_TRUE(target_pub.publish(target)); }

		sta_rate_ctrl_status_s rate{}; rate.timestamp = hrt_absolute_time(); rate.div_eff = 1;
		rate.fault = rate_fault; rate.termination = rate_termination; rate.measurement_valid = rate.output_valid = true;
		EXPECT_TRUE(rate_pub.publish(rate)); EXPECT_TRUE(lp_pub.publish(lp));
		RegularizedIstaVelocityModuleTestAccess::step(*module);
		unsigned sr = 0, dr = 0;

		while (sr < 8 && selection_sub.update(&selection)) { ++sr; }

		while (dr < 8 && diagnostic_sub.update(&diagnostic)) { ++dr; }

		ASSERT_GT(sr, 0u); ASSERT_GT(dr, 0u); EXPECT_EQ(selection.publish_seq, ++previous_seq);
		EXPECT_EQ(selection.publish_seq, diagnostic.publish_seq); EXPECT_EQ(selection.timestamp_sample, lp.timestamp_sample);
		EXPECT_EQ(selection.timestamp_sample, diagnostic.timestamp_sample); EXPECT_EQ(selection.input_timestamp, lp.timestamp);
		EXPECT_EQ(selection.input_timestamp, diagnostic.input_timestamp);
		EXPECT_EQ(selection.effective_mode, diagnostic.effective_mode);
		EXPECT_EQ(selection.effective_axes, diagnostic.effective_axes); EXPECT_EQ(selection.pid_calls, diagnostic.pid_calls);
		EXPECT_EQ(selection.ri_version, 1); output_sub.update(&output);
	}
	void arm()
	{
		mode.flag_armed = true; EXPECT_TRUE(mode_pub.publish(mode));
		land.landed = land.ground_contact = false; EXPECT_TRUE(land_pub.publish(land));
		RegularizedIstaVelocityModuleTestAccess::airborne(*module, lp.timestamp);
	}
	void disarm()
	{
		mode.flag_armed = false; EXPECT_TRUE(mode_pub.publish(mode));
		land.landed = land.ground_contact = true; EXPECT_TRUE(land_pub.publish(land));
	}
	void configure(uint8_t axes = 7, bool offline = true)
	{
		if (offline) { RegularizedIstaVelocityModuleTestAccess::admit(*module); }
		RegularizedIstaVelocityModuleTestAccess::request(*module, 4, axes); step();
		ASSERT_EQ(selection.effective_mode, 4); ASSERT_EQ(selection.effective_axes, axes);
		arm(); step(8000); step(12000);
	}
	void expectNoRistaCandidate()
	{
		EXPECT_FALSE(selection.ri_valid); EXPECT_EQ(selection.ri_strict_axes, 0); EXPECT_EQ(selection.ri_commit_axes, 0);

		for (int i = 0; i < 3; ++i) {
			EXPECT_TRUE(std::isnan(selection.ri_p[i])); EXPECT_TRUE(std::isnan(selection.ri_nu_candidate[i]));
			EXPECT_TRUE(std::isnan(selection.ri_a_ideal[i]));
		}
	}
};

TEST_F(RegularizedIstaVelocityModule, PidDefaultEmitsVersionButNoInventedImplicitCandidate)
{
	step(); EXPECT_EQ(selection.effective_mode, 0); EXPECT_EQ(selection.effective_axes, 0);
	EXPECT_EQ(selection.variant_eff, 0); expectNoRistaCandidate();
	arm(); step(8000); step(12000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.pid_axes, 7);
	expectNoRistaCandidate(); EXPECT_FALSE(selection.ri_cache_valid);

	for (int i = 0; i < 3; ++i) { EXPECT_TRUE(std::isnan(selection.ri_acc_published[i])); }
}

TEST_F(RegularizedIstaVelocityModule, RI03ProductionOtherMasksRefusedWithoutMutatingPid)
{
	for (int32_t axes : {-1, 0, 2, 3, 4, 5, 6, 7, 8, 257}) {
		RegularizedIstaVelocityModuleTestAccess::request(*module, 4, axes); step();
		EXPECT_EQ(selection.requested_mode, 4); EXPECT_EQ(selection.variant_req, 4);
		EXPECT_EQ(selection.effective_mode, 0); EXPECT_EQ(selection.variant_eff, 0);
		EXPECT_TRUE(selection.reject & VelocityControlSelector::ModeUnimplemented);
		EXPECT_FALSE(selection.reject & VelocityControlSelector::ModeRange); EXPECT_EQ(selection.sta_gen, 0u);
		expectNoRistaCandidate();
	}
	arm(); RegularizedIstaVelocityModuleTestAccess::request(*module, 4, 7); step(8000); step(12000);
	EXPECT_TRUE(selection.pending); EXPECT_EQ(selection.effective_mode, 0); EXPECT_EQ(diagnostic.pid_axes, 7);
	EXPECT_TRUE(diagnostic.valid); expectNoRistaCandidate();
	RegularizedIstaVelocityModuleTestAccess::request(*module, 0, 0); step(); EXPECT_FALSE(selection.pending);
}

TEST_F(RegularizedIstaVelocityModule, NewCandidateUsesCandidateNuAndOneFeedForwardWithTrueSampleDt)
{
	configure(7);

	for (unsigned k = 0; k < 12; ++k) {
		const uint64_t interval = k % 2 ? 12000 : 8000; step(interval, k % 2 ? 3000 : 1000);
		ASSERT_TRUE(diagnostic.valid); ASSERT_TRUE(selection.ri_valid); EXPECT_EQ(selection.ri_commit_axes, 7);
		EXPECT_EQ(diagnostic.pid_axes, 0); EXPECT_EQ(selection.ri_cache_sample, lp.timestamp_sample);
		EXPECT_FLOAT_EQ(selection.ri_h, static_cast<float>(interval) * 1e-6f);

		for (int i = 0; i < 3; ++i) {
			const double p = static_cast<double>(selection.ri_p[i]), epsilon = static_cast<double>(selection.eps_eff[i]);
			const double rho = std::fmax(-1., std::fmin(1., p / epsilon));
			const double psi = std::fabs(p) <= epsilon ? p / std::sqrt(epsilon) : std::copysign(std::sqrt(std::fabs(p)), p);
			const double l1 = i == 2 ? 2. : .5, l2 = i == 2 ? 1. : .1, h = static_cast<double>(selection.ri_h);
			EXPECT_NEAR(p + h * l1 * psi + h * h * l2 * rho, static_cast<double>(diagnostic.s[i]), 3e-7);
			EXPECT_NEAR(static_cast<double>(selection.ri_nu_candidate[i]),
				    static_cast<double>(diagnostic.nu_before[i]) - h * l2 * rho, 3e-7);
			EXPECT_NEAR(static_cast<double>(selection.ri_a_ideal[i]),
				    -l1 * psi + static_cast<double>(selection.ri_nu_candidate[i]), 3e-7);
			EXPECT_NEAR(selection.ri_acc_published[i], selection.ri_a_applied[i] + target.acceleration[i], 3e-7f);
			EXPECT_FLOAT_EQ(selection.ri_acc_published[i], output.acceleration[i]);
			EXPECT_FLOAT_EQ(selection.ri_thrust_published[i], output.thrust[i]);
		}
	}
}

TEST_F(RegularizedIstaVelocityModule, RI03ProductionXUsesOtherTwoPidAxesAndUnselectedImplicitValuesStayNan)
{
	configure(1, false); step(8000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.pid_axes, 6);
	EXPECT_EQ(selection.ri_commit_axes, 1); ASSERT_TRUE(selection.ri_valid);

	for (int i = 1; i < 3; ++i) { EXPECT_TRUE(std::isnan(selection.ri_p[i])); EXPECT_TRUE(std::isnan(selection.ri_a_ideal[i])); }
}

TEST_F(RegularizedIstaVelocityModule, XyzSeedLogsInverseRelationWithoutPretendingNormalImplicitCommit)
{
	RegularizedIstaVelocityModuleTestAccess::admit(*module);
	RegularizedIstaVelocityModuleTestAccess::request(*module, 4, 7); step(); arm(); step(8000);
	ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.z_phase, 2); EXPECT_EQ(selection.ri_commit_axes, 0);
	EXPECT_FALSE(selection.ri_valid); EXPECT_GT(selection.ri_seed_h, 0.f);

	for (int i = 0; i < 3; ++i) {
		const double p = static_cast<double>(selection.ri_p[i]), epsilon = static_cast<double>(selection.eps_eff[i]);
		const double rho = std::fmax(-1., std::fmin(1., p / epsilon));
		const double psi = std::fabs(p) <= epsilon ? p / std::sqrt(epsilon) : std::copysign(std::sqrt(std::fabs(p)), p);
		const double h = static_cast<double>(selection.ri_seed_h), l1 = i == 2 ? 2. : .5, l2 = i == 2 ? 1. : .1;
		EXPECT_NEAR(p + h * l1 * psi + h * h * l2 * rho, static_cast<double>(diagnostic.s[i]), 3e-7);
		const double seeded_output = -l1 * psi + static_cast<double>(selection.ri_nu_applied[i]) - h * l2 * rho;
		EXPECT_NEAR(seeded_output, static_cast<double>(selection.ri_a_applied[i]), 3e-7);
		EXPECT_TRUE(std::isnan(selection.ri_nu_candidate[i])); EXPECT_TRUE(std::isnan(selection.ri_a_ideal[i]));
		EXPECT_FLOAT_EQ(selection.ri_acc_published[i], output.acceleration[i]);
	}
}

TEST_F(RegularizedIstaVelocityModule, WholeConfigurationArmedStageCancellationAndDisarmApplication)
{
	configure(); const auto generation = selection.sta_gen;
	RegularizedIstaVelocityModuleTestAccess::width(*module, .03f); step(8000);
	EXPECT_TRUE(selection.sta_pending); EXPECT_FALSE(selection.pending); EXPECT_EQ(selection.sta_gen, generation);
	EXPECT_FLOAT_EQ(selection.eps_req[0], .03f); EXPECT_FLOAT_EQ(selection.eps_eff[0], .01f);
	RegularizedIstaVelocityModuleTestAccess::width(*module, .01f); step(12000); EXPECT_FALSE(selection.sta_pending);
	RegularizedIstaVelocityModuleTestAccess::width(*module, .03f); step(8000); disarm(); step(12000);
	EXPECT_FALSE(selection.sta_pending); EXPECT_GT(selection.sta_gen, generation);
	EXPECT_FLOAT_EQ(selection.eps_eff[0], .03f);
	expectNoRistaCandidate();
}

TEST_F(RegularizedIstaVelocityModule, ArmedAlgorithmRequestDoesNotTakeEffectUntilDisarm)
{
	configure(); const auto generation = selection.sta_gen;
	RegularizedIstaVelocityModuleTestAccess::request(*module, 3, 7); step(8000);
	EXPECT_TRUE(selection.pending); EXPECT_EQ(selection.effective_mode, 4); EXPECT_EQ(selection.sta_gen, generation);
	RegularizedIstaVelocityModuleTestAccess::request(*module, 4, 7); step(12000); EXPECT_FALSE(selection.pending);
	RegularizedIstaVelocityModuleTestAccess::request(*module, 3, 7); disarm(); step(8000);
	EXPECT_EQ(selection.effective_mode, 3); EXPECT_FALSE(selection.pending); expectNoRistaCandidate();
	arm(); step(12000); step(8000); EXPECT_EQ(selection.variant_eff, 3); EXPECT_TRUE(diagnostic.valid);
}

TEST_F(RegularizedIstaVelocityModule, NormalXyzNeverEvaluatesIdlePidAsFallbackOutput)
{
	configure(); RegularizedIstaVelocityModuleTestAccess::poisonPid(*module); step(8000);
	ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.pid_axes, 0); EXPECT_EQ(selection.ri_commit_axes, 7);

	for (int i = 0; i < 3; ++i) { EXPECT_TRUE(std::isfinite(selection.ri_acc_published[i])); }
}

TEST_F(RegularizedIstaVelocityModule, GroundSuppressionAndLongRampNeverIntegrateImplicitNu)
{
	RegularizedIstaVelocityModuleTestAccess::admit(*module);
	RegularizedIstaVelocityModuleTestAccess::request(*module, 4, 7);
	step(); RegularizedIstaVelocityModuleTestAccess::fastSpool(*module);
	mode.flag_armed = true; ASSERT_TRUE(mode_pub.publish(mode));
	unsigned ground = 0, ramp = 0;

	for (unsigned k = 0; k < 6002; ++k) {
		step(10000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0); expectNoRistaCandidate();

		for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(diagnostic.nu_applied[i], 0.f); }

		if (diagnostic.pid_axes == 0) { ++ground; } else if (diagnostic.pid_axes == 7) { ++ramp; }
	}

	EXPECT_GT(ground, 0u); EXPECT_GT(ramp, 0u);
	// External timeout/cancel; no new takeoff timer or land detector behavior.
	disarm(); step(); expectNoRistaCandidate(); arm(); step(8000); step(12000);
	ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(selection.ri_commit_axes, 7);
}

TEST_F(RegularizedIstaVelocityModule, ContactBounceAndRearmingRequireFreshSeedBeforeCommit)
{
	configure();

	for (unsigned bounce = 0; bounce < 2; ++bounce) {
		land.ground_contact = true; ASSERT_TRUE(land_pub.publish(land)); step(8000);
		ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0); expectNoRistaCandidate();
		land.ground_contact = false; ASSERT_TRUE(land_pub.publish(land)); step(12000);
		ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0);
		step(8000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(selection.ri_commit_axes, 7);
	}

	disarm(); step(12000); expectNoRistaCandidate();

	for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(diagnostic.nu_applied[i], 0.f); }

	arm(); step(8000); EXPECT_EQ(diagnostic.committed_axes, 0); step(12000); EXPECT_EQ(selection.ri_commit_axes, 7);
}

TEST_F(RegularizedIstaVelocityModule, InnerTerminationFaultLatchesAndSameSampleFailsafeCannotCommit)
{
	configure(); const auto before = diagnostic; rate_termination = true; step(8000);
	EXPECT_EQ(diagnostic.pid_calls, 2); EXPECT_NE(diagnostic.first_fail, 0); EXPECT_FALSE(diagnostic.valid);
	EXPECT_NE(diagnostic.fault, 0); EXPECT_EQ(diagnostic.committed_axes, 0); EXPECT_EQ(diagnostic.output_timestamp, 0u);
	EXPECT_EQ(selection.ri_commit_axes, 0);

	for (int i = 0; i < 3; ++i) {
		EXPECT_FLOAT_EQ(diagnostic.nu_applied[i], before.nu_applied[i]); EXPECT_TRUE(std::isnan(selection.ri_acc_published[i]));
	}

	rate_termination = false; step(12000); EXPECT_FALSE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0);
	disarm(); step(8000); EXPECT_EQ(diagnostic.fault, 0); arm(); step(12000); step(8000); EXPECT_TRUE(diagnostic.valid);
}

TEST_F(RegularizedIstaVelocityModule, MeasurementLossAndRecoveryNeverAutomaticallyClearLatch)
{
	configure(); const auto before = diagnostic; lp.v_z_valid = false; step(8000);
	EXPECT_FALSE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0); EXPECT_NE(diagnostic.fault, 0);

	for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(diagnostic.nu_applied[i], before.nu_applied[i]); }

	lp.v_z_valid = true; step(12000); EXPECT_FALSE(diagnostic.valid); EXPECT_EQ(selection.ri_commit_axes, 0);
	disarm(); step(8000); arm(); step(12000); step(8000); EXPECT_TRUE(diagnostic.valid);
}

TEST_F(RegularizedIstaVelocityModule, HalfHorizontalNanNoPartialSeedAndRetryCannotBecomeSuccess)
{
	configure(); const auto before = diagnostic;
	target.x = NAN; target.vx = NAN; target.acceleration[0] = NAN; step(8000);
	EXPECT_FALSE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0); EXPECT_NE(diagnostic.first_fail, 0);
	EXPECT_EQ(selection.ri_commit_axes, 0); EXPECT_EQ(diagnostic.output_timestamp, 0u);

	for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(diagnostic.nu_applied[i], before.nu_applied[i]); }
}

TEST_F(RegularizedIstaVelocityModule, PureAccelerationDoesNotClaimImplicitEvaluation)
{
	configure(); target.x = target.y = target.z = target.vx = target.vy = target.vz = NAN;
	step(8000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.active_axes, 0); expectNoRistaCandidate();
	EXPECT_EQ(diagnostic.committed_axes, 0);
}

TEST_F(RegularizedIstaVelocityModule, ExitReentryAndFreshTakeoffHaveNoStaleCandidates)
{
	configure(); mode.flag_multicopter_position_control_enabled = false; ASSERT_TRUE(mode_pub.publish(mode)); step(8000);
	EXPECT_FALSE(selection.enabled); EXPECT_EQ(selection.pid_calls, 0); expectNoRistaCandidate();
	mode.flag_multicopter_position_control_enabled = true; ASSERT_TRUE(mode_pub.publish(mode)); step(12000);
	EXPECT_EQ(diagnostic.committed_axes, 0); step(8000); EXPECT_TRUE(diagnostic.valid);
	EXPECT_EQ(selection.ri_commit_axes, 7);
}

TEST_F(RegularizedIstaVelocityModule, DuplicateSampleAndLongGapDoNotHideBehindLegacyClampedDt)
{
	configure(); const auto before = diagnostic; step(0);
	EXPECT_EQ(diagnostic.committed_axes, 0); EXPECT_EQ(selection.ri_commit_axes, 0);

	for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(diagnostic.nu_applied[i], before.nu_applied[i]); }

	step(50000); EXPECT_FALSE(diagnostic.valid); EXPECT_NE(diagnostic.fault, 0);
	EXPECT_FLOAT_EQ(diagnostic.used_dt, .04f); EXPECT_GT(diagnostic.raw_dt, .04f);
	EXPECT_EQ(diagnostic.output_timestamp, 0u);
}

TEST_F(RegularizedIstaVelocityModule, FreshVelocityResetCannotBeMistakenForCovariantTargetReset)
{
	configure(); const auto before = diagnostic; ++lp.vxy_reset_counter; lp.delta_vxy[0] = .1f;
	step(8000); EXPECT_FALSE(diagnostic.valid); EXPECT_TRUE(diagnostic.reset_bits & 1);
	EXPECT_EQ(diagnostic.committed_axes, 0); EXPECT_NE(diagnostic.fault, 0);

	for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(diagnostic.nu_applied[i], before.nu_applied[i]); }
}

TEST_F(RegularizedIstaVelocityModule, HteUsesActualAppliedCorrectionCacheNotFreshImplicitSolve)
{
	int32_t enabled = 1; ASSERT_EQ(param_set(param_find("MPC_USE_HTE"), &enabled), 0);
	RegularizedIstaVelocityModuleTestAccess::reload(*module); target.vz = -.004f; target.acceleration[2] = .003f;
	configure(); step(8000); ASSERT_TRUE(selection.ri_cache_valid); const auto before = selection;
	const auto old = diagnostic;
	const float next_hover = old.hover_thrust + .01f;
	const double shift = (static_cast<double>(old.hover_thrust) / static_cast<double>(next_hover) - 1.)
			     * (static_cast<double>(before.ri_a_applied[2]) + static_cast<double>(target.acceleration[2]) - 9.80665);
	uORB::Publication<hover_thrust_estimate_s> publisher{ORB_ID(hover_thrust_estimate)};
	hover_thrust_estimate_s estimate{}; estimate.timestamp = hrt_absolute_time(); estimate.valid = true;
	estimate.hover_thrust = next_hover; ASSERT_TRUE(publisher.publish(estimate)); step(12000);
	ASSERT_TRUE(diagnostic.valid); EXPECT_FLOAT_EQ(diagnostic.hover_thrust, next_hover);
	EXPECT_NEAR(static_cast<double>(diagnostic.z_hte_shift), shift, 3e-6);
	EXPECT_NEAR(static_cast<double>(diagnostic.nu_before[2]), static_cast<double>(old.nu_applied[2]) + shift, 3e-6);

	for (int i = 0; i < 2; ++i) { EXPECT_FLOAT_EQ(diagnostic.nu_before[i], old.nu_applied[i]); }

	EXPECT_EQ(selection.ri_commit_axes, 7);
}

TEST_F(RegularizedIstaVelocityModule, RI03BsonSavedConfigurationRestartAdmitsOnlyProductionX)
{
	const char *names[15] {"MPC_VC_L1_X", "MPC_VC_L2_X", "MPC_VC_NU_X", "MPC_VC_A_X", "MPC_VC_EPS_X",
			       "MPC_VC_L1_Y", "MPC_VC_L2_Y", "MPC_VC_NU_Y", "MPC_VC_A_Y", "MPC_VC_EPS_Y",
			       "MPC_VC_L1_Z", "MPC_VC_L2_Z", "MPC_VC_NU_Z", "MPC_VC_A_Z", "MPC_VC_EPS_Z"
			      };
	const float values[15] {.5f, .1f, .4f, .8f, .013f, .5f, .1f, .4f, .8f, .024f, 2.f, 1.f, 4.f, 6.f, .035f};

	for (const int32_t axes : {1, 3, 4, 7}) {
		for (int i = 0; i < 15; ++i) { ASSERT_EQ(param_set(param_find(names[i]), &values[i]), 0); }

		const int32_t requested_mode = 4;
		ASSERT_EQ(param_set(param_find("MPC_VC_MODE"), &requested_mode), 0);
		ASSERT_EQ(param_set(param_find("MPC_VC_AXES"), &axes), 0);
		FILE *file = tmpfile(); ASSERT_NE(file, nullptr); ASSERT_EQ(param_export(fileno(file), false, nullptr), 0);
		param_reset_all(); ASSERT_EQ(lseek(fileno(file), 0, SEEK_SET), 0);
		ASSERT_EQ(param_import(fileno(file), true), 0); fclose(file);
		delete module; module = new MulticopterPositionControl(); previous_seq = 0; step();
		EXPECT_EQ(selection.requested_mode, 4); EXPECT_EQ(selection.requested_axes, axes);
		EXPECT_EQ(selection.variant_req, 4); EXPECT_EQ(selection.effective_mode, axes == 1 ? 4 : 0);
		EXPECT_EQ(selection.reject == 0, axes == 1); EXPECT_FALSE(selection.sta_reject);
		EXPECT_EQ(selection.sta_gen > 0, axes == 1); expectNoRistaCandidate();
		if (axes == 1) {
			arm(); step(8000); step(12000); ASSERT_TRUE(diagnostic.valid);
			EXPECT_EQ(selection.ri_commit_axes, 1); EXPECT_EQ(diagnostic.pid_axes, 6);
			disarm(); step(8000);
		}

		for (int i = 0; i < 15; ++i) {
			float actual = NAN; ASSERT_EQ(param_get(param_find(names[i]), &actual), 0); EXPECT_FLOAT_EQ(actual, values[i]);
		}
	}
}

TEST_F(RegularizedIstaVelocityModule, PositionAndHeadingResetRetainExistingTargetCompensation)
{
	configure(); const auto before = diagnostic; const auto old_target = output;
	publish_target = false;
	++lp.xy_reset_counter; lp.delta_xy[0] = .3f; lp.delta_xy[1] = -.2f;
	lp.x += lp.delta_xy[0]; lp.y += lp.delta_xy[1];
	++lp.heading_reset_counter; lp.delta_heading = .05f; lp.heading += lp.delta_heading;
	step(8000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.reset_bits & (4 | 16), 4 | 16);
	EXPECT_NEAR(diagnostic.s[0], before.s[0], 1e-6f); EXPECT_NEAR(diagnostic.s[1], before.s[1], 1e-6f);
	EXPECT_NEAR(output.x, old_target.x + .3f, 1e-6f); EXPECT_NEAR(output.y, old_target.y - .2f, 1e-6f);
	EXPECT_NEAR(output.yaw, old_target.yaw + .05f, 1e-6f); EXPECT_EQ(selection.ri_commit_axes, 7);
}

TEST_F(RegularizedIstaVelocityModule, CovariantHorizontalVelocityResetHasNoImplicitStateReset)
{
	configure(); const auto before = diagnostic; publish_target = false;
	++lp.vxy_reset_counter; lp.delta_vxy[0] = .03f; lp.delta_vxy[1] = -.02f;
	lp.vx += lp.delta_vxy[0]; lp.vy += lp.delta_vxy[1]; step(8000);
	ASSERT_TRUE(diagnostic.valid); EXPECT_TRUE(diagnostic.reset_bits & 1); EXPECT_EQ(selection.ri_commit_axes, 7);

	for (int i = 0; i < 2; ++i) {
		EXPECT_NEAR(diagnostic.s[i], before.s[i], 1e-6f); EXPECT_FLOAT_EQ(diagnostic.nu_before[i], before.nu_applied[i]);
	}
}

TEST_F(RegularizedIstaVelocityModule, VerticalVelocityResetFailsClosedDespiteCachedTargetCompensation)
{
	configure(); const auto before = diagnostic; publish_target = false;
	++lp.vz_reset_counter; lp.delta_vz = .03f; lp.vz += .03f; lp.z_deriv += .03f; step(8000);
	EXPECT_TRUE(diagnostic.reset_bits & 2); EXPECT_FALSE(diagnostic.valid); EXPECT_NE(diagnostic.fault, 0);
	EXPECT_EQ(diagnostic.committed_axes, 0); EXPECT_EQ(diagnostic.output_timestamp, 0u);

	for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(diagnostic.nu_applied[i], before.nu_applied[i]); }
}

TEST_F(RegularizedIstaVelocityModule, VerticalPositionResetFailsClosedAcrossMixedZVelocityPath)
{
	configure(); const auto before = diagnostic; publish_target = false;
	++lp.z_reset_counter; lp.delta_z = .1f; lp.z += .1f; step(8000);
	EXPECT_TRUE(diagnostic.reset_bits & 8); EXPECT_FALSE(diagnostic.valid); EXPECT_NE(diagnostic.fault, 0);
	EXPECT_EQ(diagnostic.committed_axes, 0); EXPECT_EQ(diagnostic.output_timestamp, 0u);

	for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(diagnostic.nu_applied[i], before.nu_applied[i]); }
}

TEST_F(RegularizedIstaVelocityModule, ExistingProductionRstaSurvivesRejectedRistaRequestWhileArmed)
{
	RegularizedIstaVelocityModuleTestAccess::request(*module, 3, 7); step(); arm(); step(8000); step(12000);
	ASSERT_EQ(selection.effective_mode, 3); ASSERT_TRUE(diagnostic.valid); const auto generation = selection.sta_gen;
	RegularizedIstaVelocityModuleTestAccess::request(*module, 4, 7);
	RegularizedIstaVelocityModuleTestAccess::width(*module, .05f); step(8000);
	EXPECT_EQ(selection.variant_req, 4); EXPECT_EQ(selection.variant_eff, 3); EXPECT_TRUE(selection.pending);
	EXPECT_TRUE(selection.reject & VelocityControlSelector::ModeUnimplemented); EXPECT_EQ(selection.sta_gen, generation);
	EXPECT_FLOAT_EQ(selection.eps_eff[0], .01f); EXPECT_TRUE(diagnostic.valid); expectNoRistaCandidate();
	disarm(); step(12000); EXPECT_EQ(selection.effective_mode, 3); EXPECT_EQ(selection.sta_gen, generation);
}

TEST_F(RegularizedIstaVelocityModule, FullQueueEightPreservesEveryJoinedPublicationAcrossBursts)
{
	configure();

	for (unsigned burst = 0; burst < 16; ++burst) {
		const uint32_t preceding = previous_seq;

		for (unsigned k = 0; k < 8; ++k) {
			lp.timestamp_sample += k % 2 ? 12000 : 8000; lp.timestamp = lp.timestamp_sample;
			target.timestamp = lp.timestamp; ASSERT_TRUE(target_pub.publish(target));
			sta_rate_ctrl_status_s rate{}; rate.timestamp = hrt_absolute_time(); rate.div_eff = 1;
			rate.measurement_valid = rate.output_valid = true; ASSERT_TRUE(rate_pub.publish(rate));
			ASSERT_TRUE(lp_pub.publish(lp)); RegularizedIstaVelocityModuleTestAccess::step(*module);
		}

		for (unsigned k = 0; k < 8; ++k) {
			ASSERT_TRUE(selection_sub.update(&selection)); ASSERT_TRUE(diagnostic_sub.update(&diagnostic));
			EXPECT_EQ(selection.publish_seq, preceding + k + 1); EXPECT_EQ(selection.publish_seq, diagnostic.publish_seq);
			EXPECT_EQ(selection.timestamp_sample, diagnostic.timestamp_sample);
			EXPECT_EQ(selection.input_timestamp, diagnostic.input_timestamp); EXPECT_EQ(selection.ri_version, 1);
			EXPECT_EQ(selection.effective_mode, 4); EXPECT_EQ(selection.ri_commit_axes, 7); EXPECT_TRUE(selection.ri_valid);
		}

		EXPECT_FALSE(selection_sub.updated()); EXPECT_FALSE(diagnostic_sub.updated()); previous_seq += 8;
	}
}

class RegularizedIstaProductionX : public RegularizedIstaVelocityModule {};

TEST_F(RegularizedIstaProductionX, SignedNorthCommandUsesActualEightTwelveMsAndOneFeedforward)
{
	configure(1, false);
	for (unsigned k = 0; k < 128; ++k) {
		target.vx = (k / 16) % 2 ? -.03f : .03f;
		const uint64_t dt = k % 2 ? 12000 : 8000;
		step(dt, k % 2 ? 3000 : 1000);
		ASSERT_TRUE(diagnostic.valid); ASSERT_TRUE(selection.ri_valid);
		EXPECT_EQ(selection.effective_mode, 4); EXPECT_EQ(selection.effective_axes, 1);
		EXPECT_EQ(selection.reject, 0); EXPECT_EQ(diagnostic.pid_axes, 6);
		EXPECT_EQ(selection.ri_commit_axes, 1); EXPECT_EQ(selection.ri_strict_axes, 1);
		EXPECT_GT(selection.ri_a_ideal[0] * target.vx, 0.f);
		EXPECT_FLOAT_EQ(selection.ri_h, static_cast<float>(dt) * 1e-6f);
		const double p = static_cast<double>(selection.ri_p[0]), h = static_cast<double>(selection.ri_h);
		const double rho = std::fmax(-1., std::fmin(1., p / .01));
		const double psi = std::sqrt(std::fmax(std::fabs(p), .01)) * rho;
		EXPECT_NEAR(p + h * .5 * psi + h * h * .1 * rho, static_cast<double>(diagnostic.s[0]), 3e-7);
		EXPECT_NEAR(static_cast<double>(selection.ri_a_ideal[0]),
			    -.5 * psi + static_cast<double>(selection.ri_nu_candidate[0]), 3e-7);
		EXPECT_NEAR(selection.ri_acc_published[0], selection.ri_a_applied[0] + target.acceleration[0], 3e-7f);
		EXPECT_FLOAT_EQ(selection.ri_acc_published[0], output.acceleration[0]);
		for (int i = 1; i < 3; ++i) {
			EXPECT_TRUE(std::isnan(selection.ri_p[i])); EXPECT_TRUE(std::isnan(selection.ri_nu_candidate[i]));
			EXPECT_TRUE(std::isfinite(output.acceleration[i])); EXPECT_TRUE(std::isnan(diagnostic.nu_applied[i]));
		}
	}
}

TEST_F(RegularizedIstaProductionX, ArmedPidRequestStagesCancelsAndAdmitsOnlyAfterDisarm)
{
	step(); arm(); step(8000);
	RegularizedIstaVelocityModuleTestAccess::request(*module, 4, 1); step(12000);
	EXPECT_TRUE(selection.pending); EXPECT_EQ(selection.reject, 0);
	EXPECT_EQ(selection.effective_mode, 0); EXPECT_EQ(diagnostic.pid_axes, 7); expectNoRistaCandidate();
	RegularizedIstaVelocityModuleTestAccess::request(*module, 0, 0); step(8000);
	EXPECT_FALSE(selection.pending); EXPECT_EQ(selection.effective_mode, 0);
	RegularizedIstaVelocityModuleTestAccess::request(*module, 4, 1); step(12000);
	disarm(); step(8000); EXPECT_EQ(selection.effective_mode, 4); EXPECT_FALSE(selection.pending);
	expectNoRistaCandidate(); arm(); step(12000); step(8000);
	EXPECT_TRUE(diagnostic.valid); EXPECT_EQ(selection.ri_commit_axes, 1); EXPECT_EQ(diagnostic.pid_axes, 6);
}

TEST_F(RegularizedIstaProductionX, ArmedConfigCancelAndDisarmApplyKeepXStateAndRejectLaterMasks)
{
	configure(1, false); const auto generation = selection.sta_gen;
	RegularizedIstaVelocityModuleTestAccess::width(*module, .03f); step(8000);
	EXPECT_TRUE(selection.sta_pending); EXPECT_EQ(selection.sta_gen, generation);
	EXPECT_FLOAT_EQ(selection.eps_eff[0], .01f); EXPECT_EQ(selection.ri_commit_axes, 1);
	RegularizedIstaVelocityModuleTestAccess::width(*module, .01f); step(12000);
	EXPECT_FALSE(selection.sta_pending);
	for (const int32_t axes : {2, 3, 4, 5, 6, 7}) {
		RegularizedIstaVelocityModuleTestAccess::request(*module, 4, axes); step(8000);
		EXPECT_TRUE(selection.pending); EXPECT_NE(selection.reject, 0);
		EXPECT_EQ(selection.effective_axes, 1); EXPECT_EQ(selection.sta_gen, generation);
		EXPECT_TRUE(diagnostic.valid); EXPECT_EQ(selection.ri_commit_axes, 1);
	}
	RegularizedIstaVelocityModuleTestAccess::request(*module, 4, 1); step(12000);
	EXPECT_FALSE(selection.pending); EXPECT_FALSE(selection.sta_pending); EXPECT_EQ(selection.reject, 0);
	RegularizedIstaVelocityModuleTestAccess::width(*module, .03f); step(8000); disarm(); step(12000);
	EXPECT_GT(selection.sta_gen, generation); EXPECT_FLOAT_EQ(selection.eps_eff[0], .03f);
	EXPECT_FALSE(selection.sta_pending); expectNoRistaCandidate(); EXPECT_FLOAT_EQ(diagnostic.nu_applied[0], 0.f);
	arm(); step(8000); step(12000); EXPECT_EQ(selection.ri_commit_axes, 1); EXPECT_TRUE(diagnostic.valid);
}

TEST_F(RegularizedIstaProductionX, OtherDivisorsCannotBecomeEffectiveOrChangeArmedX)
{
	for (const int32_t div : {-1, 0, 2, 3, 4, 8, 257}) {
		RegularizedIstaVelocityModuleTestAccess::request(*module, 0, 0);
		RegularizedIstaVelocityModuleTestAccess::divisor(*module, 1); step();
		RegularizedIstaVelocityModuleTestAccess::divisor(*module, div);
		RegularizedIstaVelocityModuleTestAccess::request(*module, 4, 1); step();
		EXPECT_EQ(selection.effective_mode, 0); EXPECT_NE(selection.reject, 0); expectNoRistaCandidate();
	}
	RegularizedIstaVelocityModuleTestAccess::divisor(*module, 1); configure(1, false);
	for (const int32_t div : {2, 4}) {
		RegularizedIstaVelocityModuleTestAccess::divisor(*module, div); step(8000);
		EXPECT_EQ(selection.effective_mode, 4); EXPECT_EQ(selection.div_eff, 1);
		EXPECT_TRUE(selection.div_pending); EXPECT_TRUE(selection.div_reject); EXPECT_NE(selection.reject, 0);
		EXPECT_TRUE(diagnostic.valid); EXPECT_EQ(selection.ri_commit_axes, 1);
	}
	RegularizedIstaVelocityModuleTestAccess::divisor(*module, 1); step(12000);
	EXPECT_FALSE(selection.div_pending); EXPECT_FALSE(selection.div_reject); EXPECT_EQ(selection.reject, 0);
}

TEST_F(RegularizedIstaProductionX, ContactExitAndRearmingPrimeWithoutReusingImplicitState)
{
	configure(1, false); ASSERT_NE(diagnostic.nu_applied[0], 0.f);
	land.ground_contact = true; ASSERT_TRUE(land_pub.publish(land)); step(8000);
	EXPECT_TRUE(diagnostic.valid); EXPECT_EQ(selection.ri_commit_axes, 0); EXPECT_FLOAT_EQ(diagnostic.nu_applied[0], 0.f);
	land.ground_contact = false; ASSERT_TRUE(land_pub.publish(land)); step(12000);
	EXPECT_EQ(selection.ri_commit_axes, 0); step(8000); EXPECT_EQ(selection.ri_commit_axes, 1);
	mode.flag_multicopter_position_control_enabled = false; ASSERT_TRUE(mode_pub.publish(mode)); step(12000);
	EXPECT_FALSE(selection.enabled); expectNoRistaCandidate();
	mode.flag_multicopter_position_control_enabled = true; ASSERT_TRUE(mode_pub.publish(mode)); step(8000);
	EXPECT_EQ(selection.ri_commit_axes, 0); step(12000); EXPECT_EQ(selection.ri_commit_axes, 1);
	disarm(); step(8000); EXPECT_FLOAT_EQ(diagnostic.nu_applied[0], 0.f); expectNoRistaCandidate();
	arm(); step(12000); EXPECT_EQ(selection.ri_commit_axes, 0);
	step(8000); EXPECT_TRUE(diagnostic.valid); EXPECT_EQ(selection.ri_commit_axes, 1);
}

TEST_F(RegularizedIstaProductionX, CovariantPositionHeadingAndHorizontalVelocityResetsPreserveError)
{
	configure(1, false); const auto before = diagnostic; publish_target = false;
	++lp.xy_reset_counter; lp.delta_xy[0] = .3f; lp.delta_xy[1] = -.2f;
	lp.x += lp.delta_xy[0]; lp.y += lp.delta_xy[1];
	++lp.heading_reset_counter; lp.delta_heading = .05f; lp.heading += lp.delta_heading;
	++lp.vxy_reset_counter; lp.delta_vxy[0] = .03f; lp.delta_vxy[1] = -.02f;
	lp.vx += lp.delta_vxy[0]; lp.vy += lp.delta_vxy[1]; step(8000);
	ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.reset_bits & (1 | 4 | 16), 1 | 4 | 16);
	EXPECT_NEAR(diagnostic.s[0], before.s[0], 1e-6f);
	EXPECT_FLOAT_EQ(diagnostic.nu_before[0], before.nu_applied[0]); EXPECT_EQ(selection.ri_commit_axes, 1);
}

TEST_F(RegularizedIstaProductionX, GroundRampAndCancelledTakeoffNeverIntegrateImplicitNu)
{
	RegularizedIstaVelocityModuleTestAccess::request(*module, 4, 1); step();
	ASSERT_EQ(selection.effective_mode, 4); RegularizedIstaVelocityModuleTestAccess::fastSpool(*module);
	mode.flag_armed = true; ASSERT_TRUE(mode_pub.publish(mode));
	unsigned ground = 0, ramp = 0;
	for (unsigned k = 0; k < 6002; ++k) {
		step(10000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.committed_axes, 0);
		EXPECT_FLOAT_EQ(diagnostic.nu_applied[0], 0.f); expectNoRistaCandidate();
		if (diagnostic.pid_axes == 0) { ++ground; } else if (diagnostic.pid_axes == 6) { ++ramp; }
	}
	EXPECT_GT(ground, 0u); EXPECT_GT(ramp, 0u);
	disarm(); step(8000); expectNoRistaCandidate();
	arm(); step(12000); EXPECT_EQ(selection.ri_commit_axes, 0);
	step(8000); EXPECT_TRUE(diagnostic.valid); EXPECT_EQ(selection.ri_commit_axes, 1);
}

TEST_F(RegularizedIstaProductionX, LegalPairedNanAccelerationOnlyResetsAndPrimesOnReentry)
{
	configure(1, false); const auto original = target;
	target.x = target.y = target.vx = target.vy = NAN;
	step(8000); ASSERT_TRUE(diagnostic.valid); EXPECT_EQ(diagnostic.active_axes, 0);
	EXPECT_EQ(selection.ri_commit_axes, 0); EXPECT_FLOAT_EQ(diagnostic.nu_applied[0], 0.f); expectNoRistaCandidate();
	EXPECT_FLOAT_EQ(output.acceleration[0], target.acceleration[0]);
	target = original; step(12000); EXPECT_EQ(selection.ri_commit_axes, 0);
	step(8000); EXPECT_TRUE(diagnostic.valid); EXPECT_EQ(selection.ri_commit_axes, 1);
}

class RegularizedIstaProductionXFailure : public RegularizedIstaVelocityModule,
	public ::testing::WithParamInterface<int> {};
INSTANTIATE_TEST_SUITE_P(AllFailures, RegularizedIstaProductionXFailure, ::testing::Values(0, 1, 2, 3, 4, 5, 6, 7));

TEST_P(RegularizedIstaProductionXFailure, LatchRejectsRecoveryAndSameSampleRetryUntilDisarm)
{
	configure(1, false); const auto before = diagnostic; const auto original_target = target;
	const int kind = GetParam();
	if (kind == 0) { rate_termination = true; }
	if (kind == 1) { rate_fault = true; }
	if (kind == 2) { lp.v_xy_valid = false; }
	if (kind == 3) { ++lp.vxy_reset_counter; lp.delta_vxy[0] = .1f; }
	if (kind == 4) { target.x = NAN; target.vx = NAN; target.acceleration[0] = NAN; }
	if (kind == 7) { lp.v_z_valid = false; } // Unselected PID Z still needs valid feedback.
	step(kind == 5 ? 50000 : (kind == 6 ? 0 : 8000));
	EXPECT_FALSE(diagnostic.valid); EXPECT_NE(diagnostic.first_fail, 0);
	EXPECT_NE(diagnostic.fault, 0); EXPECT_EQ(diagnostic.committed_axes, 0);
	EXPECT_EQ(selection.ri_commit_axes, 0); EXPECT_EQ(diagnostic.output_timestamp, 0u);
	EXPECT_FLOAT_EQ(diagnostic.nu_applied[0], before.nu_applied[0]);
	rate_termination = rate_fault = false; lp.v_xy_valid = lp.v_z_valid = true; target = original_target;
	step(12000); EXPECT_FALSE(diagnostic.valid); EXPECT_EQ(selection.ri_commit_axes, 0);
	EXPECT_FLOAT_EQ(diagnostic.nu_applied[0], before.nu_applied[0]);
	disarm(); step(8000); EXPECT_EQ(diagnostic.fault, 0); EXPECT_FLOAT_EQ(diagnostic.nu_applied[0], 0.f);
	arm(); step(12000); EXPECT_EQ(selection.ri_commit_axes, 0);
	step(8000); EXPECT_TRUE(diagnostic.valid); EXPECT_EQ(selection.ri_commit_axes, 1);
}
