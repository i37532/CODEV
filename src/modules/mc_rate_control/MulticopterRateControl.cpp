/****************************************************************************
 *
 *   Copyright (c) 2013-2019 PX4 Development Team. All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 *
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in
 *    the documentation and/or other materials provided with the
 *    distribution.
 * 3. Neither the name PX4 nor the names of its contributors may be
 *    used to endorse or promote products derived from this software
 *    without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
 * FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
 * COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
 * INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
 * BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS
 * OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED
 * AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
 * LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
 * ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 *
 ****************************************************************************/

#include "MulticopterRateControl.hpp"

#include <drivers/drv_hrt.h>
#include <circuit_breaker/circuit_breaker.h>
#include <mathlib/math/Limits.hpp>
#include <mathlib/math/Functions.hpp>

using namespace matrix;
using namespace time_literals;
using math::radians;

static_assert(ControllerSelection::PID == rate_ctrl_selection_s::MODE_PID, "selection mode ABI");
static_assert(ControllerSelection::Accepted == rate_ctrl_selection_s::REQUEST_ACCEPTED, "selection status ABI");
static_assert(ControllerSelection::Unsupported == rate_ctrl_selection_s::REQUEST_UNSUPPORTED, "selection status ABI");
static_assert(ControllerSelection::InvalidMode == rate_ctrl_selection_s::REQUEST_INVALID_MODE, "selection status ABI");
static_assert(ControllerSelection::InvalidAxes == rate_ctrl_selection_s::REQUEST_INVALID_AXES, "selection status ABI");

MulticopterRateControl::MulticopterRateControl(bool vtol) :
	ModuleParams(nullptr),
	WorkItem(MODULE_NAME, px4::wq_configurations::rate_ctrl),
	_actuators_0_pub(vtol ? ORB_ID(actuator_controls_virtual_mc) : ORB_ID(actuator_controls_0)),
	_loop_perf(perf_alloc(PC_ELAPSED, MODULE_NAME": cycle"))
{
	_vehicle_status.vehicle_type = vehicle_status_s::VEHICLE_TYPE_ROTARY_WING;

	parameters_updated();
}

MulticopterRateControl::~MulticopterRateControl()
{
	perf_free(_loop_perf);
}

bool
MulticopterRateControl::init()
{
	if (!_vehicle_angular_velocity_sub.registerCallback()) {
		PX4_ERR("vehicle_angular_velocity callback registration failed!");
		return false;
	}

	return true;
}

void
MulticopterRateControl::parameters_updated()
{
	// rate control parameters
	// The controller gain K is used to convert the parallel (P + I/s + sD) form
	// to the ideal (K * [1 + 1/sTi + sTd]) form
	const Vector3f rate_k = Vector3f(_param_mc_rollrate_k.get(), _param_mc_pitchrate_k.get(), _param_mc_yawrate_k.get());

	_rate_control.setGains(
		rate_k.emult(Vector3f(_param_mc_rollrate_p.get(), _param_mc_pitchrate_p.get(), _param_mc_yawrate_p.get())),
		rate_k.emult(Vector3f(_param_mc_rollrate_i.get(), _param_mc_pitchrate_i.get(), _param_mc_yawrate_i.get())),
		rate_k.emult(Vector3f(_param_mc_rollrate_d.get(), _param_mc_pitchrate_d.get(), _param_mc_yawrate_d.get())));

	_rate_control.setIntegratorLimit(
		Vector3f(_param_mc_rr_int_lim.get(), _param_mc_pr_int_lim.get(), _param_mc_yr_int_lim.get()));

	_rate_control.setFeedForwardGain(
		Vector3f(_param_mc_rollrate_ff.get(), _param_mc_pitchrate_ff.get(), _param_mc_yawrate_ff.get()));
	// Diagnostic copies only: original PID setters and their timing are untouched.
	_research_p = rate_k.emult(Vector3f(_param_mc_rollrate_p.get(), _param_mc_pitchrate_p.get(),
					    _param_mc_yawrate_p.get()));
	_research_d = rate_k.emult(Vector3f(_param_mc_rollrate_d.get(), _param_mc_pitchrate_d.get(),
					    _param_mc_yawrate_d.get()));
	_research_ff = Vector3f(_param_mc_rollrate_ff.get(), _param_mc_pitchrate_ff.get(), _param_mc_yawrate_ff.get());
	_sta_requested.mode = _param_mc_rtc_mode.get();
	_sta_requested.axes = _param_mc_sta_axes.get();
	_sta_requested.c_limit = 0.15f; // frozen normalized R/P command bound
#if defined(CONFIG_ARCH_BOARD_PX4_SITL)
	int32_t airframe = 0;
	param_get(param_find("SYS_AUTOSTART"), &airframe);
	_research_iris = airframe == 10016;
#endif
	// Uncalibrated defaults are zero. Read/stage as one configuration; begin()
	// applies it only while disarmed. No experimental values affect original PID.
	const char *l1[] = {"MC_STA_L1_R", "MC_STA_L1_P", "MC_STA_L1_Y"};
	const char *l2[] = {"MC_STA_L2_R", "MC_STA_L2_P", "MC_STA_L2_Y"};
	const char *g[] = {"MC_STA_G_R", "MC_STA_G_P", "MC_STA_G_Y"};
	const char *nu[] = {"MC_STA_NU_R", "MC_STA_NU_P", "MC_STA_NU_Y"};

	for (size_t i = 0; i < 3; ++i) {
		param_get(param_find(l1[i]), &_sta_requested.gains[i].lambda1);
		param_get(param_find(l2[i]), &_sta_requested.gains[i].lambda2);
		param_get(param_find(g[i]), &_sta_requested.gains[i].g);
		param_get(param_find(nu[i]), &_sta_requested.nu_limit[i]);
	}


	// manual rate control acro mode rate limits
	_acro_rate_max = Vector3f(radians(_param_mc_acro_r_max.get()), radians(_param_mc_acro_p_max.get()),
				  radians(_param_mc_acro_y_max.get()));

	_actuators_0_circuit_breaker_enabled = circuit_breaker_enabled_by_val(_param_cbrk_rate_ctrl.get(), CBRK_RATE_CTRL_KEY);
}

void
MulticopterRateControl::Run()
{
	if (should_exit()) {
		_vehicle_angular_velocity_sub.unregisterCallback();
		exit_and_cleanup();
		return;
	}

	perf_begin(_loop_perf);

	// Check if parameters have changed
	if (_parameter_update_sub.updated()) {
		// clear update
		parameter_update_s param_update;
		_parameter_update_sub.copy(&param_update);

		updateParams();
		parameters_updated();
	}

	/* run controller on gyro changes */
	vehicle_angular_velocity_s angular_velocity;

	if (_vehicle_angular_velocity_sub.update(&angular_velocity)) {

		// grab corresponding vehicle_angular_acceleration immediately after vehicle_angular_velocity copy
		vehicle_angular_acceleration_s v_angular_acceleration{};
		_vehicle_angular_acceleration_sub.copy(&v_angular_acceleration);

		const hrt_abstime now = angular_velocity.timestamp_sample;

		// Guard against too small (< 0.125ms) and too large (> 20ms) dt's.
		const float dt = math::constrain(((now - _last_run) * 1e-6f), 0.000125f, 0.02f);
		_last_run = now;

		const Vector3f angular_accel{v_angular_acceleration.xyz};
		const Vector3f rates{angular_velocity.xyz};

		/* check for updates in other topics */
		_v_control_mode_sub.update(&_v_control_mode);

		if (_vehicle_land_detected_sub.updated()) {
			vehicle_land_detected_s vehicle_land_detected;

			if (_vehicle_land_detected_sub.copy(&vehicle_land_detected)) {
				_landed = vehicle_land_detected.landed;
				_maybe_landed = vehicle_land_detected.maybe_landed;
			}
		}

		_vehicle_status_sub.update(&_vehicle_status);

		// Selection uses the latest arming state. Existing PID parameter updates
		// above remain immediate and retain their original scheduling/order.
		const bool esta_ready = StaAxesApplication::ready(_research_iris, _sta_requested);
		const bool selection_changed = _rate_control.select(_param_mc_rtc_mode.get(), _param_mc_sta_axes.get(),
					       _v_control_mode.flag_armed, esta_ready);

		if (selection_changed || !_selection_published) {
			const auto &selection = _rate_control.selectionStatus();
			rate_ctrl_selection_s status{};
			status.timestamp = hrt_absolute_time();
			status.requested_mode = selection.requested_mode;
			status.requested_axes = selection.requested_axes;
			status.effective_mode = selection.effective_mode;
			status.effective_axes = selection.effective_axes;
			status.request_status = selection.request_status;
			status.pending = selection.pending;
			_selection_status_pub.publish(status);
			_selection_published = true;

			if (selection.request_status != ControllerSelection::Accepted) {
				PX4_WARN("controller request mode=%ld axes=%ld: %s; effective=%u axes=%u, pending=%d",
					 (long)selection.requested_mode, (long)selection.requested_axes,
					 ControllerSelection::statusName(selection.request_status), (unsigned)selection.effective_mode,
					 (unsigned)selection.effective_axes, (int)selection.pending);
			}
		}

		if (_landing_gear_sub.updated()) {
			landing_gear_s landing_gear;

			if (_landing_gear_sub.copy(&landing_gear)) {
				if (landing_gear.landing_gear != landing_gear_s::GEAR_KEEP) {
					_landing_gear = landing_gear.landing_gear;
				}
			}
		}

		if (_v_control_mode.flag_control_manual_enabled && !_v_control_mode.flag_control_attitude_enabled) {
			// generate the rate setpoint from sticks
			manual_control_setpoint_s manual_control_setpoint;

			if (_manual_control_setpoint_sub.update(&manual_control_setpoint)) {
				// manual rates control - ACRO mode
				const Vector3f man_rate_sp{
					math::superexpo(manual_control_setpoint.y, _param_mc_acro_expo.get(), _param_mc_acro_supexpo.get()),
					math::superexpo(-manual_control_setpoint.x, _param_mc_acro_expo.get(), _param_mc_acro_supexpo.get()),
					math::superexpo(manual_control_setpoint.r, _param_mc_acro_expo_y.get(), _param_mc_acro_supexpoy.get())};

				_rates_sp = man_rate_sp.emult(_acro_rate_max);
				_thrust_sp = math::constrain(manual_control_setpoint.z, 0.0f, 1.0f);

				// publish rate setpoint
				vehicle_rates_setpoint_s v_rates_sp{};
				v_rates_sp.roll = _rates_sp(0);
				v_rates_sp.pitch = _rates_sp(1);
				v_rates_sp.yaw = _rates_sp(2);
				v_rates_sp.thrust_body[0] = 0.0f;
				v_rates_sp.thrust_body[1] = 0.0f;
				v_rates_sp.thrust_body[2] = -_thrust_sp;
				v_rates_sp.timestamp = hrt_absolute_time();

				_v_rates_sp_pub.publish(v_rates_sp);
			}

		} else {
			// use rates setpoint topic
			vehicle_rates_setpoint_s v_rates_sp;

			if (_v_rates_sp_sub.update(&v_rates_sp)) {
				_research_input_valid = PX4_ISFINITE(v_rates_sp.roll) && PX4_ISFINITE(v_rates_sp.pitch)
							&& PX4_ISFINITE(v_rates_sp.yaw) && PX4_ISFINITE(v_rates_sp.thrust_body[2]);
				_research_sp_timestamp = v_rates_sp.timestamp;
				_rates_sp(0) = PX4_ISFINITE(v_rates_sp.roll)  ? v_rates_sp.roll  : rates(0);
				_rates_sp(1) = PX4_ISFINITE(v_rates_sp.pitch) ? v_rates_sp.pitch : rates(1);
				_rates_sp(2) = PX4_ISFINITE(v_rates_sp.yaw)   ? v_rates_sp.yaw   : rates(2);
				_thrust_sp = -v_rates_sp.thrust_body[2];
				_research_test_addition = v_rates_sp.research_roll_addition;
				_research_pitch_addition = v_rates_sp.research_pitch_addition;
				_research_yaw_addition = v_rates_sp.research_yaw_addition;
				_research_test_elapsed = v_rates_sp.research_elapsed;
			}
		}

		// Research timing does not replace legacy clamped dt. Mixer diagnostics
		// below record the exact feedback consumed by PID, without another read.
		StaProtection::Frame frame{};
		frame.sample = now; frame.armed = _v_control_mode.flag_armed;
		frame.rate_enabled = _v_control_mode.flag_control_rates_enabled && !_actuators_0_circuit_breaker_enabled;
		frame.landed = _landed; frame.maybe_landed = _maybe_landed;

		for (int i = 0; i < 3; ++i) {
			frame.measurement_valid = frame.measurement_valid && PX4_ISFINITE(rates(i))
						  && PX4_ISFINITE(angular_accel(i)) && PX4_ISFINITE(_rates_sp(i));
		}

		frame.experiment_active = _rate_control.selectionStatus().effective_mode == ControllerSelection::ESTA;

		if (frame.experiment_active) {
			const uint64_t clock_now = hrt_absolute_time();
			frame.measurement_valid = frame.measurement_valid && _research_input_valid
						  && _research_sp_timestamp > 0 && clock_now >= _research_sp_timestamp
						  && clock_now - _research_sp_timestamp < 100000;
		}

		StaProtection::Config staged = _sta_requested;

		if (staged.mode != 0 && !esta_ready) { staged.c_limit = 0.f; }

		_sta_guard.begin(staged, frame);
		sta_rate_ctrl_status_s research{};
		research.measurement_valid = frame.measurement_valid;
		research.timestamp_sample = now;
		research.publish_seq = ++_research_publish_seq;
		research.config_seq = _sta_guard.configSequence();
		research.config_pending = _sta_guard.pending(); research.config_valid = _sta_guard.configValid();
		research.raw_dt = _sta_guard.rawDt(); research.dt = dt;
		research.timing_status = _sta_guard.timing(); research.fault = _sta_guard.fault();
		research.reset_reason = _sta_guard.resetReason(); research.abort_requested = _sta_guard.abortRequested();
		const auto &selection = _rate_control.selectionStatus();
		research.requested_mode = selection.requested_mode; research.requested_axes = selection.requested_axes;
		research.effective_mode = selection.effective_mode; research.effective_axes = selection.effective_axes;
		research.request_status = selection.request_status; research.pending = selection.pending;
		research.armed = frame.armed; research.landed = _landed; research.maybe_landed = _maybe_landed;
		research.rate_enabled = frame.rate_enabled;
		research.experiment_frozen = true;
		research.research_roll_addition = _research_test_addition;
		research.research_pitch_addition = _research_pitch_addition;
		research.research_yaw_addition = _research_yaw_addition;
		research.research_elapsed = _research_test_elapsed;
		research.battery_scale = 1.f;

		for (int i = 0; i < 3; ++i) {
			research.rate[i] = rates(i); research.rate_sp[i] = _rates_sp(i); research.angular_accel[i] = angular_accel(i);
			research.s[i] = rates(i) - _rates_sp(i); research.nu[i] = _sta_guard.state()[i];
			research.nu_before[i] = _sta_guard.state()[i];
			research.lambda1[i] = _sta_guard.config().gains[i].lambda1;
			research.lambda2[i] = _sta_guard.config().gains[i].lambda2;
			research.g[i] = _sta_guard.config().gains[i].g;
			research.a_raw[i] = research.xi[i] = research.virtual_state[i] = NAN;
			research.c_raw[i] = research.c_applied[i] = NAN;
			research.pid_integral_before[i] = research.pid_integral_after[i] = NAN;
			research.ista_branch[i] = 255;
			research.pid_p[i] = _research_p(i); research.pid_d[i] = _research_d(i); research.pid_ff[i] = _research_ff(i);
		}

		// run the rate controller
		if (_v_control_mode.flag_control_rates_enabled && !_actuators_0_circuit_breaker_enabled) {

			// reset integral if disarmed
			if (!_v_control_mode.flag_armed || _vehicle_status.vehicle_type != vehicle_status_s::VEHICLE_TYPE_ROTARY_WING) {
				_rate_control.resetIntegral();
				research.pid_reset = true;
			}

			// update saturation status from mixer feedback
			if (_motor_limits_sub.updated()) {
				multirotor_motor_limits_s motor_limits;

				if (_motor_limits_sub.copy(&motor_limits)) {
					MultirotorMixer::saturation_status saturation_status;
					saturation_status.value = motor_limits.saturation_status;

					_rate_control.setSaturationStatus(saturation_status);
					_research_motor = motor_limits; // exact already-consumed feedback; no extra subscription copy
				}
			}

			rate_ctrl_status_s integral_before{};
			_rate_control.getRateControlStatus(integral_before);
			research.pid_integral_before[0] = integral_before.rollspeed_integ;
			research.pid_integral_before[1] = integral_before.pitchspeed_integ;
			research.pid_integral_before[2] = integral_before.yawspeed_integ;
			research.pid_frozen = _maybe_landed || _landed;
			// run rate controller
			Vector3f att_control = _rate_control.update(rates, _rates_sp, angular_accel, dt, _maybe_landed || _landed);
			research.pid_updated = _rate_control.pidRequired();
			research.pid_frozen = research.pid_frozen || !research.pid_updated;
			StaProtection::Output experiment{};

			if (frame.experiment_active && frame.armed) {
				experiment = _sta_guard.step({rates(0), rates(1), rates(2)}, {_rates_sp(0), _rates_sp(1), _rates_sp(2)},
				{_research_motor.timestamp, hrt_absolute_time(), _research_motor.saturation_status}, true);
			}

			std::array<float, 3> mixed{};
			const bool emit = StaAxesApplication::apply(selection.effective_axes, frame.armed, experiment,
			{att_control(0), att_control(1), att_control(2)}, mixed);

			for (int i = 0; i < 3; ++i) { att_control(i) = mixed[i]; }

			research.fault = _sta_guard.fault(); research.abort_requested = _sta_guard.abortRequested();

			if (frame.experiment_active) {
				research.experiment_updated = experiment.updated;
				research.experiment_frozen = !experiment.updated;
				for (int i = 0; i < 3; ++i) {
					if (selection.effective_axes & (1 << i)) {
						research.a_raw[i] = experiment.a[i]; research.nu[i] = _sta_guard.state()[i];
						research.limits[i] = experiment.limits[i];
					}
				}
			}

			// publish rate controller status
			rate_ctrl_status_s rate_ctrl_status{};
			_rate_control.getRateControlStatus(rate_ctrl_status);
			research.pid_integral_after[0] = rate_ctrl_status.rollspeed_integ;
			research.pid_integral_after[1] = rate_ctrl_status.pitchspeed_integ;
			research.pid_integral_after[2] = rate_ctrl_status.yawspeed_integ;
			research.updated = emit;

			if (emit) { ++_research_update_seq; }

			rate_ctrl_status.timestamp = hrt_absolute_time();
			_controller_status_pub.publish(rate_ctrl_status);

			// publish actuator controls
			actuator_controls_s actuators{};
			actuators.control[actuator_controls_s::INDEX_ROLL] = PX4_ISFINITE(att_control(0)) ? att_control(0) : 0.0f;
			actuators.control[actuator_controls_s::INDEX_PITCH] = PX4_ISFINITE(att_control(1)) ? att_control(1) : 0.0f;
			actuators.control[actuator_controls_s::INDEX_YAW] = PX4_ISFINITE(att_control(2)) ? att_control(2) : 0.0f;
			actuators.control[actuator_controls_s::INDEX_THROTTLE] = PX4_ISFINITE(_thrust_sp) ? _thrust_sp : 0.0f;
			actuators.control[actuator_controls_s::INDEX_LANDING_GEAR] = _landing_gear;
			actuators.timestamp_sample = angular_velocity.timestamp_sample;

			// scale effort by battery status if enabled
			if (_param_mc_bat_scale_en.get()) {
				if (_battery_status_sub.updated()) {
					battery_status_s battery_status;

					if (_battery_status_sub.copy(&battery_status) && battery_status.connected && battery_status.scale > 0.f) {
						_battery_status_scale = battery_status.scale;
					}
				}

				if (_battery_status_scale > 0.0f) {
					research.battery_scale = _battery_status_scale;

					for (int i = 0; i < 4; i++) {
						actuators.control[i] *= _battery_status_scale;
					}
				}
			}

			actuators.timestamp = hrt_absolute_time();

			// Invalid ESTA suppresses publication; no zero-torque or PID fallback.
			// The local monitor aborts SITL even if lockstep stops at this sample.
			if (emit) { _actuators_0_pub.publish(actuators); }

			research.output_valid = emit;

			for (int i = 0; i < 3; ++i) {
				research.c_raw[i] = att_control(i);
				research.c_applied[i] = actuators.control[i];
				research.output_valid = research.output_valid && PX4_ISFINITE(att_control(i)) && PX4_ISFINITE(actuators.control[i]);
			}

			if (frame.experiment_active && frame.armed) {
				for (int i = 0; i < 3; ++i) {
					if (selection.effective_axes & (1 << i)) { research.c_raw[i] = experiment.c_raw[i]; }
				}
			}

			if (!emit) { for (int i = 0; i < 3; ++i) { research.c_applied[i] = NAN; } }

		} else if (_v_control_mode.flag_control_termination_enabled) {
			research.termination = true;

			if (!_vehicle_status.is_vtol) {
				// publish actuator controls
				actuator_controls_s actuators{};
				actuators.timestamp = hrt_absolute_time();
				_actuators_0_pub.publish(actuators);
			}
		}

		research.update_seq = _research_update_seq;
		research.pid_update_seq = _rate_control.pidUpdateSequence();
		research.timestamp = hrt_absolute_time();
		research.motor_timestamp = _research_motor.timestamp;
		research.motor_update_seq = _research_motor.update_seq;
		research.motor_saturation = _research_motor.saturation_status;
		research.motor_valid = StaProtection::Feedback{_research_motor.timestamp, research.timestamp, _research_motor.saturation_status}.valid();
		_sta_status_pub.publish(research);
	}

	perf_end(_loop_perf);
}

int MulticopterRateControl::print_status()
{
	// Read a uORB snapshot instead of racing the work queue's controller state.
	uORB::Subscription sub{ORB_ID(rate_ctrl_selection)};
	rate_ctrl_selection_s status{};

	if (sub.copy(&status)) {
		PX4_INFO("requested: mode=%ld axes=%ld; effective: mode=%u axes=%u; request=%s; pending=%d",
			 (long)status.requested_mode, (long)status.requested_axes,
			 (unsigned)status.effective_mode, (unsigned)status.effective_axes,
			 ControllerSelection::statusName(status.request_status), (int)status.pending);

	} else {
		PX4_INFO("selection status awaiting first gyro update");
	}

	return 0;
}

int MulticopterRateControl::task_spawn(int argc, char *argv[])
{
	bool vtol = false;

	if (argc > 1) {
		if (strcmp(argv[1], "vtol") == 0) {
			vtol = true;
		}
	}

	MulticopterRateControl *instance = new MulticopterRateControl(vtol);

	if (instance) {
		_object.store(instance);
		_task_id = task_id_is_work_queue;

		if (instance->init()) {
			return PX4_OK;
		}

	} else {
		PX4_ERR("alloc failed");
	}

	delete instance;
	_object.store(nullptr);
	_task_id = -1;

	return PX4_ERROR;
}

int MulticopterRateControl::custom_command(int argc, char *argv[])
{
	return print_usage("unknown command");
}

int MulticopterRateControl::print_usage(const char *reason)
{
	if (reason) {
		PX4_WARN("%s\n", reason);
	}

	PRINT_MODULE_DESCRIPTION(
		R"DESCR_STR(
### Description
This implements the multicopter rate controller. It takes rate setpoints (in acro mode
via `manual_control_setpoint` topic) as inputs and outputs actuator control messages.

The controller has a PID loop for angular rate error.

)DESCR_STR");

	PRINT_MODULE_USAGE_NAME("mc_rate_control", "controller");
	PRINT_MODULE_USAGE_COMMAND("start");
	PRINT_MODULE_USAGE_ARG("vtol", "VTOL mode", true);
	PRINT_MODULE_USAGE_DEFAULT_COMMANDS();

	return 0;
}

extern "C" __EXPORT int mc_rate_control_main(int argc, char *argv[])
{
	return MulticopterRateControl::main(argc, argv);
}
