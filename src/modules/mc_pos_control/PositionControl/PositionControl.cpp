/****************************************************************************
 *
 *   Copyright (c) 2018 - 2019 PX4 Development Team. All rights reserved.
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

/**
 * @file PositionControl.cpp
 */

#include "PositionControl.hpp"
#include "ControlMath.hpp"
#include "VelocityHostClock.hpp"
#include <float.h>
#include <mathlib/mathlib.h>
#include <px4_platform_common/defines.h>
#include <ecl/geo/geo.h>

using namespace matrix;

void PositionControl::configureVelocityDivisor(int32_t divisor, bool armed)
{
	const int32_t previous = _decimation.divisor;
	const bool supported = _velocity_selector.effectiveMode() == 0 || _velocity_selector.effectiveAxes() < 4;
#if defined(CONFIG_ARCH_BOARD_PX4_SITL)
	_decimation.configure(divisor, armed, supported);
#else
	(void)supported;
	_decimation.configure(divisor, armed, false);
#endif
	if (_decimation.divisor != previous) { _interval_positive = _interval_negative = 0; }
}

void PositionControl::configureVelocityEsta(const StaVelocityProtection::Config &c, bool armed)
{
	_esta_requested = c;
	_esta_config_valid = (c.axes == 1 || c.axes == 3 || c.axes == 4 || c.axes == 7) && StaVelocityProtection::validConfig(c);
	bool different = c.axes != _esta_effective.axes;
	for (unsigned axis = 0; axis < 3; ++axis) {
		if (c.axes & (1u << axis)) {
			different = different || memcmp(&c.gains[axis], &_esta_effective.gains[axis], sizeof(c.gains[axis]))
				|| memcmp(&c.nu_limit[axis], &_esta_effective.nu_limit[axis], sizeof(float))
				|| memcmp(&c.acceleration_limit[axis], &_esta_effective.acceleration_limit[axis], sizeof(float));
		}
	}
	// Disabled/unconfigured gains are not a deferred configuration transaction
	// while running PID. An invalid request while ESTA is effective stays visible.
	_esta_pending = armed && different && (_esta_config_valid || _velocity_selector.effectiveMode() == 1);
	if (!armed && _esta_config_valid && different) {
		_esta_effective = c;
		++_esta_config_generation;
	}
}

void PositionControl::configureVelocityControl(int32_t mode, int32_t axes, bool armed)
{
	const int32_t previous = _velocity_selector.effectiveMode();
	const int32_t previous_axes = _velocity_selector.effectiveAxes();
	bool ready = false;
#if defined(CONFIG_ARCH_BOARD_PX4_SITL)
	ready = _esta_config_valid && (_decimation.divisor == 1 || axes < 4);
#endif
	_velocity_selector.configure(mode, axes, armed, ready, _esta_requested.axes);
	if (previous != _velocity_selector.effectiveMode() || previous_axes != _velocity_selector.effectiveAxes()) {
		++_esta_config_generation;
		// Only experimental-axis PID state is reset on disarmed algorithm change.
		if ((previous_axes | _velocity_selector.effectiveAxes()) & 1) { _vel_int(0) = 0.f; }
		if ((previous_axes | _velocity_selector.effectiveAxes()) & 2) { _vel_int(1) = 0.f; }
		if ((previous_axes | _velocity_selector.effectiveAxes()) & 4) { _vel_int(2) = 0.f; }
		_z_engaged = false;
		_decimation.invalidate();
	}
	StaVelocityProtection::Config c = _esta_effective;
	c.axes = _velocity_selector.effectiveMode() == 1 ? _velocity_selector.effectiveAxes() : 0;
	_velocity_protection.configure(c, armed);
}

void PositionControl::setVelocityFrame(const StaVelocityProtection::Frame &frame)
{
	++_velocity_frame_serial;
	if (!frame.armed && _velocity_frame.armed) { _decimation.restart(); _interval_positive = _interval_negative = 0; }
	_velocity_frame = frame;
	if (!frame.enabled) {
		const uint8_t latched = frame.armed ? _decimation.fault : 0;
		_decimation.restart(); _decimation.fault = latched; _interval_positive = _interval_negative = 0;
	}
	if (!frame.armed || !frame.enabled || _velocity_selector.effectiveMode() == 0) {
		auto inactive = frame;
		inactive.enabled = false;
		_velocity_protection.begin(inactive);
		_z_engaged = false;
		if (!frame.armed) { _esta_failed = false; }
	}
}

void PositionControl::setVelocityGains(const Vector3f &P, const Vector3f &I, const Vector3f &D)
{
	_gain_vel_p = P;
	_gain_vel_i = I;
	_gain_vel_d = D;
}

void PositionControl::setVelocityLimits(const float vel_horizontal, const float vel_up, const float vel_down)
{
	_lim_vel_horizontal = vel_horizontal;
	_lim_vel_up = vel_up;
	_lim_vel_down = vel_down;
}

void PositionControl::setThrustLimits(const float min, const float max)
{
	// make sure there's always enough thrust vector length to infer the attitude
	_lim_thr_min = math::max(min, 10e-4f);
	_lim_thr_max = max;
}

void PositionControl::updateHoverThrust(const float hover_thrust_new)
{
	if (_velocity_selector.effectiveMode() == 1 && (_velocity_selector.effectiveAxes() & 4) && _z_engaged) {
		// Fixed error/FF and XY demand: body_z is independent of Z acceleration.
		// Preserve pre-limit collective thrust, including at nonzero tilt. Refuse
		// saturated/invalid states rather than silently clipping a continuity seed.
		const float s = _diagnostic.s[2];
		const float correction = -_esta_effective.gains[2].lambda1 * sqrtf(fabsf(s)) * sign(s)
			+ _velocity_protection.state()[2];
		const float ff = PX4_ISFINITE(_diagnostic.a_ff[2]) ? _diagnostic.a_ff[2] : 0.f;
		const float shift = (_hover_thrust / hover_thrust_new - 1.f) * (correction + ff - CONSTANTS_ONE_G);
		if (!PX4_ISFINITE(hover_thrust_new) || hover_thrust_new < .1f || hover_thrust_new > .9f
		    || (_diagnostic.constraint_bits & 6) || !_velocity_protection.shiftZ(shift, correction)) {
			_esta_failed = true;
		} else { _z_hte_shift += shift; }
		setHoverThrust(hover_thrust_new);
		return;
	}
	const float before = _vel_int(2);
	_vel_int(2) += (hover_thrust_new - _hover_thrust) * (CONSTANTS_ONE_G / hover_thrust_new);
	// HTE is not a velocity integration step. Apply exactly its integral shift
	// to the held Z correction, not to a previously mapped thrust vector.
	if (_decimation.divisor > 1 && PX4_ISFINITE(_correction(2))) { _correction(2) += _vel_int(2) - before; }
	setHoverThrust(hover_thrust_new);
}

void PositionControl::setState(const PositionControlStates &states)
{
	_pos = states.position;
	_vel = states.velocity;
	_yaw = states.yaw;
	_vel_dot = states.acceleration;
}

void PositionControl::setInputSetpoint(const vehicle_local_position_setpoint_s &setpoint)
{
	_pos_sp = Vector3f(setpoint.x, setpoint.y, setpoint.z);
	_vel_sp = Vector3f(setpoint.vx, setpoint.vy, setpoint.vz);
	_acc_sp = Vector3f(setpoint.acceleration);
	_yaw_sp = setpoint.yaw;
	_yawspeed_sp = setpoint.yawspeed;
}

bool PositionControl::update(const float dt)
{
	const Vector3f integral_before = _vel_int;
	// Observe only; PID operations and integration order remain untouched.
	_pos_sp.copyTo(_diagnostic.p_sp);
	_vel_sp.copyTo(_diagnostic.v_ff);
	_acc_sp.copyTo(_diagnostic.a_ff);
	// x and y input setpoints always have to come in pairs
	const bool valid = (PX4_ISFINITE(_pos_sp(0)) == PX4_ISFINITE(_pos_sp(1)))
			   && (PX4_ISFINITE(_vel_sp(0)) == PX4_ISFINITE(_vel_sp(1)))
			   && (PX4_ISFINITE(_acc_sp(0)) == PX4_ISFINITE(_acc_sp(1)));

	_positionControl();
	// Explicit, default-off SITL test input. Original position P is unchanged.
#if defined(CONFIG_ARCH_BOARD_PX4_SITL)
	if (fabsf(_diagnostic_excitation) > 0.f || fabsf(_diagnostic_excitation_y) > 0.f) {
		if (_diagnostic_vertical) {
			_vel_sp(2) = math::constrain(_vel_sp(2) + _diagnostic_excitation, -_lim_vel_up, _lim_vel_down);
		} else {
			_vel_sp.xy() = ControlMath::constrainXY(_vel_sp.xy(), Vector2f(_diagnostic_excitation, _diagnostic_excitation_y), _lim_vel_horizontal);
		}
	}
#endif
#if defined(CONFIG_ARCH_BOARD_PX4_SITL)
	if (fabsf(_diagnostic_excitation_z) > 0.f) {
		_vel_sp(2) = math::constrain(_vel_sp(2) + _diagnostic_excitation_z, -_lim_vel_up, _lim_vel_down);
	}
#endif
	const uint64_t velocity_started = velocityHostClock();
	_velocityControl(dt);

	_yawspeed_sp = PX4_ISFINITE(_yawspeed_sp) ? _yawspeed_sp : 0.f;
	_yaw_sp = PX4_ISFINITE(_yaw_sp) ? _yaw_sp : _yaw; // TODO: better way to disable yaw control

	bool success = valid && _updateSuccessful() && !_decimation.fault;
	_recordDiagnostic(success);
	if (_velocity_selector.effectiveMode() == 1) {
		StaVelocityProtection::Vec proxy{};
		for (int i = 0; i < 3; ++i) { proxy[i] = _diagnostic.a_proxy[i]; }
		const uint8_t constrained_axes = (_diagnostic.constraint_bits ? 3 : 0)
			| ((_diagnostic.constraint_bits & 6) ? 4 : 0);
		const auto &r = _velocity_protection.finish(proxy, constrained_axes, success && !_esta_failed,
			_decimation.divisor > 1 ? _interval_positive : 0, _decimation.divisor > 1 ? _interval_negative : 0);
		_esta_failed = _esta_failed || !success || r.fault;
		success = success && !_esta_failed;
		_diagnostic.valid = success;
		_diagnostic.fault = _esta_failed;
		_diagnostic.active_axes = _z_phase ? (_z_phase == 3 ? r.active_axes : 0) : r.active_axes;
		if (!_z_phase) { _diagnostic.pid_axes &= ~_velocity_selector.effectiveAxes(); }
		if (_z_phase == 3) { _diagnostic.pid_axes &= ~4u; }
		if (_velocity_selector.effectiveAxes() == 7 && (_z_phase == 3 || _z_phase == 4)) {
			_diagnostic.pid_axes = 0;
			_diagnostic.active_axes = r.active_axes;
		}
		_diagnostic.sta_flags = r.flags;
		_diagnostic.sta_fault = r.fault;
		_diagnostic.committed_axes = r.committed_axes;
		_diagnostic.config_pending = _esta_pending;
		_diagnostic.config_generation = _esta_config_generation;
		for (unsigned axis = 0; axis < 3; ++axis) {
			if (_velocity_selector.effectiveAxes() & (1u << axis)) {
				_diagnostic.nu_before[axis] = r.nu_before[axis];
				_diagnostic.nu_ideal[axis] = r.nu_ideal[axis];
				_diagnostic.nu_applied[axis] = r.nu_applied[axis];
				_diagnostic.a_sta[axis] = (_z_phase && _z_phase != 3) ? NAN : r.a_sta[axis];
				if (_velocity_selector.effectiveAxes() == 7) {
					_diagnostic.a_sta[axis] = ((_z_phase == 3 || _z_phase == 4) && (r.active_axes & (1u << axis))) ? r.a_sta[axis] : NAN;
				}
			}
		}
	}
	_diagnostic.z_phase = _z_phase;
	_diagnostic.z_hte_shift = _z_hte_shift;
	_z_hte_shift = 0.f;
	if (_decimation.divisor > 1) {
		if (!success) { _vel_int = integral_before; _decimation.fault = _decimation.fault ? _decimation.fault : 3; _decimation.invalidate(); }
		if (!_decimated_retry) {
			if (_decimation.updated) { _interval_positive = _interval_negative = 0; }
			for (unsigned i = 0; i < 3; ++i) {
				const uint8_t affected = (_diagnostic.constraint_bits ? 3 : 0) | ((_diagnostic.constraint_bits & 6) ? 4 : 0);
				const float residual = _diagnostic.a_req[i] - _diagnostic.a_proxy[i];
				if ((affected & (1u << i)) && PX4_ISFINITE(residual)) {
					if (residual > 0.f) { _interval_positive |= 1u << i; }
					if (residual < 0.f) { _interval_negative |= 1u << i; }
				}
			}
		}
		_diagnostic.fault = _diagnostic.fault || _decimation.fault;
	}
	_velocity_path_ns = velocity_started ? velocityHostClock() - velocity_started : 0;
	return success;
}

uint16_t PositionControl::inputValidity() const
{
	uint16_t mask = 0;
	for (int i = 0; i < 3; ++i) {
		if (PX4_ISFINITE(_diagnostic.p_sp[i])) { mask |= 1u << i; }
		if (PX4_ISFINITE(_diagnostic.v_ff[i])) { mask |= 1u << (i + 3); }
		if (PX4_ISFINITE(_diagnostic.a_ff[i])) { mask |= 1u << (i + 6); }
		if (PX4_ISFINITE(_vel(i))) { mask |= 1u << (i + 9); }
		if (PX4_ISFINITE(_vel_dot(i))) { mask |= 1u << (i + 12); }
	}
	return mask;
}

uint16_t PositionControl::failureReason() const
{
	uint16_t reason = 0;
	if ((PX4_ISFINITE(_diagnostic.p_sp[0]) != PX4_ISFINITE(_diagnostic.p_sp[1]))
	    || (PX4_ISFINITE(_diagnostic.v_ff[0]) != PX4_ISFINITE(_diagnostic.v_ff[1]))
	    || (PX4_ISFINITE(_diagnostic.a_ff[0]) != PX4_ISFINITE(_diagnostic.a_ff[1]))) { reason |= 1; }
	for (int i = 0; i < 3; ++i) {
		if (PX4_ISFINITE(_pos_sp(i)) && !PX4_ISFINITE(_pos(i))) { reason |= 2; }
		if (PX4_ISFINITE(_vel_sp(i)) && (!PX4_ISFINITE(_vel(i)) || !PX4_ISFINITE(_vel_dot(i)))) { reason |= 4; }
		if (!PX4_ISFINITE(_acc_sp(i))) { reason |= 8; }
		if (!PX4_ISFINITE(_thr_sp(i))) { reason |= 16; }
	}
	if (_velocity_selector.effectiveMode() == 1 && _esta_failed) { reason |= 32; }
	return reason;
}

void PositionControl::_recordDiagnostic(bool success)
{
	_diagnostic.valid = success;
	_diagnostic.fault = false;
	_diagnostic.active_axes = _diagnostic.committed_axes = 0;
	_diagnostic.sta_flags = _diagnostic.sta_fault = 0;
	_diagnostic.config_pending = _esta_pending;
	_diagnostic.config_generation = _esta_config_generation;
	_vel_sp.copyTo(_diagnostic.v_sp);
	_vel.copyTo(_diagnostic.v);
	_vel_dot.copyTo(_diagnostic.v_dot);
	_acc_sp.copyTo(_diagnostic.a_req);
	_thr_sp.copyTo(_diagnostic.thrust);
	_diagnostic.hover_thrust = _hover_thrust;
	_diagnostic.tilt_limit = _lim_tilt;
	_diagnostic.thrust_min = _lim_thr_min;
	_diagnostic.thrust_max = _lim_thr_max;
	_diagnostic.pid_axes = 0;
	_diagnostic.constraint_bits = 0;
	for (int i = 0; i < 3; ++i) {
		_diagnostic.s[i] = _vel(i) - _vel_sp(i);
		_diagnostic.nu_before[i] = _diagnostic.nu_ideal[i] = _diagnostic.nu_applied[i] = _diagnostic.a_sta[i] = NAN;
		_diagnostic.a_proxy[i] = _thr_sp(i) * (CONSTANTS_ONE_G / _hover_thrust) + (i == 2 ? CONSTANTS_ONE_G : 0.f);
		if (PX4_ISFINITE(_vel_sp(i)) && PX4_ISFINITE(_vel(i)) && PX4_ISFINITE(_vel_dot(i))) { _diagnostic.pid_axes |= 1 << i; }
	}
	// Reconstruct mapping constraints for evidence only; no second PID update.
	Vector3f body_z = Vector3f(-_acc_sp(0), -_acc_sp(1), CONSTANTS_ONE_G).normalized();
	if (acosf(math::constrain(body_z(2), -1.f, 1.f)) > _lim_tilt) { _diagnostic.constraint_bits |= 1; }
	ControlMath::limitTilt(body_z, Vector3f(0, 0, 1), _lim_tilt);
	const float collective = (_acc_sp(2) * (_hover_thrust / CONSTANTS_ONE_G) - _hover_thrust) / body_z(2);
	if (collective > -_lim_thr_min) { _diagnostic.constraint_bits |= 2; }
	const Vector3f mapped = body_z * math::min(collective, -_lim_thr_min);
	if (mapped(2) < -_lim_thr_max) { _diagnostic.constraint_bits |= 4; }
	if (mapped.xy().norm() > _thr_sp.xy().norm() + 1e-6f) { _diagnostic.constraint_bits |= 8; }
}

void PositionControl::_positionControl()
{
	// P-position controller
	Vector3f vel_sp_position = (_pos_sp - _pos).emult(_gain_pos_p);
	// Position and feed-forward velocity setpoints or position states being NAN results in them not having an influence
	ControlMath::addIfNotNanVector3f(_vel_sp, vel_sp_position);
	// make sure there are no NAN elements for further reference while constraining
	ControlMath::setZeroIfNanVector3f(vel_sp_position);

	// Constrain horizontal velocity by prioritizing the velocity component along the
	// the desired position setpoint over the feed-forward term.
	_vel_sp.xy() = ControlMath::constrainXY(vel_sp_position.xy(), (_vel_sp - vel_sp_position).xy(), _lim_vel_horizontal);
	// Constrain velocity in z-direction.
	_vel_sp(2) = math::constrain(_vel_sp(2), -_lim_vel_up, _lim_vel_down);
}

void PositionControl::_velocityControl(const float dt)
{
	_z_phase = 0;
	if (_decimation.divisor > 1) { _velocityControlDecimated(dt); return; }
	_decimation.updated = true; _decimation.held = false; _decimation.h = dt; ++_decimation.sequence;
	// Only accepted configurations reach dispatch. V01 has exactly one backend.
	switch (_velocity_selector.effectiveMode()) {
	case 0:
		_velocityControlPid(dt);
		break;
	case 1:
		if (_velocity_selector.effectiveAxes() == 7) { _velocityControlEstaXYZ(dt); }
		else if (_velocity_selector.effectiveAxes() == 4) { _velocityControlEstaZ(dt); }
		else if (_velocity_selector.effectiveAxes() == 3) { _velocityControlEstaXY(dt); }
		else { _velocityControlEstaX(dt); }
		break;
	}
}

void PositionControl::_mapHeldCorrection()
{
	ControlMath::addIfNotNanVector3f(_acc_sp, _correction);
	_accelerationControl();
	_thr_sp(2) = math::max(_thr_sp(2), -_lim_thr_max);
	const float remainder = _lim_thr_max * _lim_thr_max - _thr_sp(2) * _thr_sp(2);
	const float maximum = remainder > 0.f ? sqrtf(remainder) : 0.f;
	const Vector2f horizontal(_thr_sp);
	if (horizontal.norm() > maximum) { _thr_sp.xy() = horizontal / horizontal.norm() * maximum; }
}

void PositionControl::_velocityControlDecimated(float dt)
{
	auto frame = _velocity_frame;
	uint8_t enabled_axes = 0;
	for (int i = 0; i < 3; ++i) {
		frame.velocity[i] = _vel(i); frame.target[i] = _vel_sp(i); frame.ff[i] = _acc_sp(i);
		if (PX4_ISFINITE(_vel_sp(i))) { enabled_axes |= 1u << i; }
	}
	bool measurement_valid = true;
	for (int i = 0; i < 3; ++i) {
		measurement_valid = measurement_valid && !std::isinf(frame.ff[i])
			&& (!(enabled_axes & (1u << i)) || (PX4_ISFINITE(_vel(i)) && PX4_ISFINITE(_vel_dot(i))));
	}
	const uint32_t key = enabled_axes | (frame.armed << 3) | (frame.flying << 4)
		| (frame.landed << 5) | (frame.contact << 6) | (_esta_config_generation << 7);
	_decimated_retry = _consumed_frame_serial == _velocity_frame_serial;
	if (!_decimated_retry) {
		_consumed_frame_serial = _velocity_frame_serial;
		_decimation.begin(frame.sample, dt, key, frame.armed);
	}
	if (!measurement_valid || (frame.armed && (!frame.inner_valid || frame.unmatched_reset_axes)) || _decimation.fault) {
		_decimation.fault = _decimation.fault ? _decimation.fault : 4;
		_acc_sp = Vector3f(NAN, NAN, NAN); _thr_sp = _acc_sp; return;
	}
	const bool update = _decimation.updated && !_decimated_retry;
	const uint8_t sta_axes = _velocity_selector.effectiveMode() == 1 ? _velocity_selector.effectiveAxes() : 0;
	frame.evaluate = update;
	frame.integration_dt = update ? _decimation.h : 0.f;
	frame.divisor = _decimation.divisor;
	const StaVelocityProtection::Result *candidate = nullptr;
	if (sta_axes && !_decimated_retry) {
		candidate = &_velocity_protection.begin(frame);
		_esta_failed = _esta_failed || candidate->fault || (candidate->flags & StaVelocityProtection::Duplicate);
	}
	if (update) {
		// Hold precisely the pre-FF correction. Do not subtract FF afterwards:
		// subtraction can lose information and breaks NaN acceleration-only use.
		for (int i = 0; i < 3; ++i) {
			if (sta_axes & (1u << i)) {
				_correction(i) = 0.f;
				if (candidate && (candidate->active_axes & (1u << i))
				    && !(candidate->flags & (StaVelocityProtection::Priming | StaVelocityProtection::Latched))) {
					_correction(i) = math::constrain(candidate->a_sta[i], -_esta_effective.acceleration_limit[i], _esta_effective.acceleration_limit[i]);
				}
			} else {
				_correction(i) = (_vel_sp(i) - _vel(i)) * _gain_vel_p(i) + _vel_int(i) - _vel_dot(i) * _gain_vel_d(i);
			}
		}
	}
	// Current FF, HTE, tilt and Z-priority/XY-remainder constraints EVERY callback.
	_mapHeldCorrection();
	if (update) {
		Vector3f error = _vel_sp - _vel;
		// Apply original PID ARW at updates only. Interval constraints impose an
		// additional conservative freeze; no body mixer flags or PID ARW on nu.
		const Vector2f limited = Vector2f(_thr_sp) * (CONSTANTS_ONE_G / _hover_thrust);
		error.xy() = Vector2f(error) - (2.f / _gain_vel_p(0)) * (Vector2f(_acc_sp) - limited);
		if ((_thr_sp(2) >= -_lim_thr_min && error(2) >= 0.f)
		    || (_thr_sp(2) <= -_lim_thr_max && error(2) <= 0.f)) { error(2) = 0.f; }
		ControlMath::setZeroIfNanVector3f(error);
		for (int i = 0; i < 3; ++i) {
			if (sta_axes & (1u << i)) { _vel_int(i) = 0.f; }
			else if (!((_interval_positive | _interval_negative) & (1u << i))) {
				_vel_int(i) += error(i) * _gain_vel_i(i) * _decimation.h;
			}
		}
		_vel_int(2) = math::min(fabsf(_vel_int(2)), CONSTANTS_ONE_G) * sign(_vel_int(2));
	}
}

void PositionControl::_velocityControlPid(const float dt)
{
	// PID velocity control
	Vector3f vel_error = _vel_sp - _vel;
	Vector3f acc_sp_velocity = vel_error.emult(_gain_vel_p) + _vel_int - _vel_dot.emult(_gain_vel_d);
	_correction = acc_sp_velocity; // observational only; original PID order below is unchanged

	// No control input from setpoints or corresponding states which are NAN
	ControlMath::addIfNotNanVector3f(_acc_sp, acc_sp_velocity);

	_accelerationControl();

	// Integrator anti-windup in vertical direction
	if ((_thr_sp(2) >= -_lim_thr_min && vel_error(2) >= 0.0f) ||
	    (_thr_sp(2) <= -_lim_thr_max && vel_error(2) <= 0.0f)) {
		vel_error(2) = 0.f;
	}

	// Saturate maximal vertical thrust
	_thr_sp(2) = math::max(_thr_sp(2), -_lim_thr_max);

	// Get allowed horizontal thrust after prioritizing vertical control
	const float thrust_max_squared = _lim_thr_max * _lim_thr_max;
	const float thrust_z_squared = _thr_sp(2) * _thr_sp(2);
	const float thrust_max_xy_squared = thrust_max_squared - thrust_z_squared;
	float thrust_max_xy = 0;

	if (thrust_max_xy_squared > 0) {
		thrust_max_xy = sqrtf(thrust_max_xy_squared);
	}

	// Saturate thrust in horizontal direction
	const Vector2f thrust_sp_xy(_thr_sp);
	const float thrust_sp_xy_norm = thrust_sp_xy.norm();

	if (thrust_sp_xy_norm > thrust_max_xy) {
		_thr_sp.xy() = thrust_sp_xy / thrust_sp_xy_norm * thrust_max_xy;
	}

	// Use tracking Anti-Windup for horizontal direction: during saturation, the integrator is used to unsaturate the output
	// see Anti-Reset Windup for PID controllers, L.Rundqwist, 1990
	const Vector2f acc_sp_xy_limited = Vector2f(_thr_sp) * (CONSTANTS_ONE_G / _hover_thrust);
	const float arw_gain = 2.f / _gain_vel_p(0);
	vel_error.xy() = Vector2f(vel_error) - (arw_gain * (Vector2f(_acc_sp) - acc_sp_xy_limited));

	// Make sure integral doesn't get NAN
	ControlMath::setZeroIfNanVector3f(vel_error);
	// Update integral part of velocity control
	_vel_int += vel_error.emult(_gain_vel_i) * dt;

	// limit thrust integral
	_vel_int(2) = math::min(fabsf(_vel_int(2)), CONSTANTS_ONE_G) * sign(_vel_int(2));
}

void PositionControl::_velocityControlEstaX(const float dt)
{
	// Y/Z preserve PID arithmetic and common limits. X has no PID contribution.
	auto frame = _velocity_frame;
	for (int i = 0; i < 3; ++i) {
		frame.velocity[i] = _vel(i); frame.target[i] = _vel_sp(i); frame.ff[i] = _acc_sp(i);
	}
	const auto &candidate = _velocity_protection.begin(frame);
	_esta_failed = _esta_failed || candidate.fault || (candidate.flags & StaVelocityProtection::Duplicate);
	Vector3f vel_error = _vel_sp - _vel;
	Vector3f acc_sp_velocity(NAN, NAN, NAN);
	for (int i = 1; i < 3; ++i) {
		acc_sp_velocity(i) = vel_error(i) * _gain_vel_p(i) + _vel_int(i) - _vel_dot(i) * _gain_vel_d(i);
	}
	_correction = acc_sp_velocity;
	_correction(0) = 0.f;
	// Inactive/priming X uses original acceleration-only FF and zero correction.
	// It never substitutes X PID. An invalid transaction is not publishable.
	_acc_sp(0) = PX4_ISFINITE(_acc_sp(0)) ? _acc_sp(0) : 0.f;
	if (candidate.active_axes && !(candidate.flags & (StaVelocityProtection::Priming | StaVelocityProtection::Latched))) {
		_acc_sp(0) = candidate.a_req[0];
		_correction(0) = math::constrain(candidate.a_sta[0], -_esta_effective.acceleration_limit[0], _esta_effective.acceleration_limit[0]);
	}

	// No control input from setpoints or corresponding states which are NAN
	ControlMath::addIfNotNanVector3f(_acc_sp, acc_sp_velocity);

	_accelerationControl();

	// Integrator anti-windup in vertical direction
	if ((_thr_sp(2) >= -_lim_thr_min && vel_error(2) >= 0.0f) ||
	    (_thr_sp(2) <= -_lim_thr_max && vel_error(2) <= 0.0f)) {
		vel_error(2) = 0.f;
	}

	// Saturate maximal vertical thrust
	_thr_sp(2) = math::max(_thr_sp(2), -_lim_thr_max);

	// Get allowed horizontal thrust after prioritizing vertical control
	const float thrust_max_squared = _lim_thr_max * _lim_thr_max;
	const float thrust_z_squared = _thr_sp(2) * _thr_sp(2);
	const float thrust_max_xy_squared = thrust_max_squared - thrust_z_squared;
	float thrust_max_xy = 0;

	if (thrust_max_xy_squared > 0) {
		thrust_max_xy = sqrtf(thrust_max_xy_squared);
	}

	// Saturate thrust in horizontal direction
	const Vector2f thrust_sp_xy(_thr_sp);
	const float thrust_sp_xy_norm = thrust_sp_xy.norm();

	if (thrust_sp_xy_norm > thrust_max_xy) {
		_thr_sp.xy() = thrust_sp_xy / thrust_sp_xy_norm * thrust_max_xy;
	}

	// Use tracking Anti-Windup for horizontal direction: during saturation, the integrator is used to unsaturate the output
	// see Anti-Reset Windup for PID controllers, L.Rundqwist, 1990
	const Vector2f acc_sp_xy_limited = Vector2f(_thr_sp) * (CONSTANTS_ONE_G / _hover_thrust);
	const float arw_gain = 2.f / _gain_vel_p(0);
	vel_error.xy() = Vector2f(vel_error) - (arw_gain * (Vector2f(_acc_sp) - acc_sp_xy_limited));

	// Make sure integral doesn't get NAN
	ControlMath::setZeroIfNanVector3f(vel_error);
	// Update integral part of velocity control
	for (int i = 1; i < 3; ++i) { _vel_int(i) += vel_error(i) * _gain_vel_i(i) * dt; }
	_vel_int(0) = 0.f;

	// limit thrust integral
	_vel_int(2) = math::min(fabsf(_vel_int(2)), CONSTANTS_ONE_G) * sign(_vel_int(2));
}

void PositionControl::_velocityControlEstaXY(const float dt)
{
	// Horizontal ESTA with independent states and one protected transaction.
	// Z retains PID/HTE and thrust priority; there is no idle horizontal PID.
	auto frame = _velocity_frame;
	for (int i = 0; i < 3; ++i) {
		frame.velocity[i] = _vel(i); frame.target[i] = _vel_sp(i); frame.ff[i] = _acc_sp(i);
	}
	const auto &candidate = _velocity_protection.begin(frame);
	_esta_failed = _esta_failed || candidate.fault || (candidate.flags & StaVelocityProtection::Duplicate);
	Vector3f vel_error = _vel_sp - _vel;
	Vector3f correction(NAN, NAN, vel_error(2) * _gain_vel_p(2) + _vel_int(2) - _vel_dot(2) * _gain_vel_d(2));
	_correction = correction;
	for (int i = 0; i < 2; ++i) {
		_correction(i) = 0.f;
		_acc_sp(i) = PX4_ISFINITE(_acc_sp(i)) ? _acc_sp(i) : 0.f;
		if ((candidate.active_axes & (1u << i)) && !(candidate.flags & (StaVelocityProtection::Priming | StaVelocityProtection::Latched))) {
			_acc_sp(i) = candidate.a_req[i];
			_correction(i) = math::constrain(candidate.a_sta[i], -_esta_effective.acceleration_limit[i], _esta_effective.acceleration_limit[i]);
		}
	}
	ControlMath::addIfNotNanVector3f(_acc_sp, correction);
	_accelerationControl();
	if ((_thr_sp(2) >= -_lim_thr_min && vel_error(2) >= 0.f)
	    || (_thr_sp(2) <= -_lim_thr_max && vel_error(2) <= 0.f)) { vel_error(2) = 0.f; }
	_thr_sp(2) = math::max(_thr_sp(2), -_lim_thr_max);
	const float remainder = _lim_thr_max * _lim_thr_max - _thr_sp(2) * _thr_sp(2);
	const float max_xy = remainder > 0.f ? sqrtf(remainder) : 0.f;
	const Vector2f horizontal(_thr_sp);
	if (horizontal.norm() > max_xy) { _thr_sp.xy() = horizontal / horizontal.norm() * max_xy; }
	// No PID tracking-ARW term is applied to either ESTA state. The guard uses
	// per-axis residuals of the common thrust-mapping proxy after both limits.
	ControlMath::setZeroIfNanVector3f(vel_error);
	_vel_int(0) = _vel_int(1) = 0.f;
	_vel_int(2) += vel_error(2) * _gain_vel_i(2) * dt;
	_vel_int(2) = math::min(fabsf(_vel_int(2)), CONSTANTS_ONE_G) * sign(_vel_int(2));
}

void PositionControl::_velocityControlEstaZ(const float dt)
{
	auto frame = _velocity_frame;
	for (int i = 0; i < 3; ++i) {
		frame.velocity[i] = _vel(i); frame.target[i] = _vel_sp(i); frame.ff[i] = _acc_sp(i);
	}
	const auto &candidate = _velocity_protection.begin(frame);
	_esta_failed = _esta_failed || candidate.fault || (candidate.flags & StaVelocityProtection::Duplicate);
	const bool ground = !frame.armed || !frame.enabled || !frame.flying || frame.landed || frame.contact;
	_z_phase = ground ? 1 : (!PX4_ISFINITE(_vel_sp(2)) ? 4 : 3);
	_z_engaged = false;
	if (ground || (_z_phase == 4 && !_esta_failed)) {
		// Preserve original takeoff ramp/contact suppression and acceleration-only
		// semantics. These phases are explicitly NOT claimed as Z ESTA.
		_velocityControlPid(dt);
		return;
	}
	if ((candidate.flags & StaVelocityProtection::Priming) && !_esta_failed) {
		const float ff = PX4_ISFINITE(_acc_sp(2)) ? _acc_sp(2) : 0.f;
		_velocityControlPid(dt); // one boundary sample, same-frame PID output
		const float s = _vel(2) - _vel_sp(2);
		const float correction = _acc_sp(2) - ff;
		const float nu = correction + _esta_effective.gains[2].lambda1 * sqrtf(fabsf(s)) * sign(s);
		const float ideal_z = (_acc_sp(2) / CONSTANTS_ONE_G - 1.f) * _hover_thrust;
		if (!PX4_ISFINITE(correction) || fabsf(correction) > _esta_effective.acceleration_limit[2]
		    || !PX4_ISFINITE(ideal_z) || fabsf(ideal_z - _thr_sp(2)) > 1e-6f
		    || !_velocity_protection.seedZ(nu)) { _esta_failed = true; }
		_z_phase = 2;
		_z_engaged = !_esta_failed;
		return;
	}
	// Normal flight: calculate only XY PID. Never run idle Z PID or add its
	// integral/derivative to ESTA. The common position P and FF remain upstream.
	Vector3f vel_error = _vel_sp - _vel;
	Vector3f correction(NAN, NAN, NAN);
	for (int i = 0; i < 2; ++i) {
		correction(i) = vel_error(i) * _gain_vel_p(i) + _vel_int(i) - _vel_dot(i) * _gain_vel_d(i);
	}
	_acc_sp(2) = !_esta_failed && candidate.active_axes == 4 ? candidate.a_req[2] : NAN;
	_correction = correction;
	_correction(2) = !_esta_failed && candidate.active_axes == 4
		? math::constrain(candidate.a_sta[2], -_esta_effective.acceleration_limit[2], _esta_effective.acceleration_limit[2]) : NAN;
	ControlMath::addIfNotNanVector3f(_acc_sp, correction);
	_accelerationControl();
	_thr_sp(2) = math::max(_thr_sp(2), -_lim_thr_max);
	const float remaining = _lim_thr_max * _lim_thr_max - _thr_sp(2) * _thr_sp(2);
	const float xy_max = remaining > 0.f ? sqrtf(remaining) : 0.f;
	const Vector2f xy(_thr_sp);
	if (xy.norm() > xy_max) { _thr_sp.xy() = xy / xy.norm() * xy_max; }
	const Vector2f limited = Vector2f(_thr_sp) * (CONSTANTS_ONE_G / _hover_thrust);
	vel_error.xy() = Vector2f(vel_error) - (2.f / _gain_vel_p(0)) * (Vector2f(_acc_sp) - limited);
	ControlMath::setZeroIfNanVector3f(vel_error);
	for (int i = 0; i < 2; ++i) { _vel_int(i) += vel_error(i) * _gain_vel_i(i) * dt; }
	_z_engaged = !_esta_failed;
}

void PositionControl::_velocityControlEstaXYZ(const float dt)
{
	auto frame = _velocity_frame;
	for (int i = 0; i < 3; ++i) {
		frame.velocity[i] = _vel(i); frame.target[i] = _vel_sp(i); frame.ff[i] = _acc_sp(i);
	}
	const auto &candidate = _velocity_protection.begin(frame);
	_esta_failed = _esta_failed || candidate.fault || (candidate.flags & StaVelocityProtection::Duplicate);
	const bool ground = !frame.armed || !frame.enabled || !frame.flying || frame.landed || frame.contact;
	_z_phase = ground ? 1 : ((candidate.active_axes & 4) ? 3 : 4);
	_z_engaged = false;
	if (ground) {
		_velocityControlPid(dt); // unchanged ramp/contact control, explicitly logged as PID
		return;
	}
	if ((candidate.flags & StaVelocityProtection::Priming) && !_esta_failed) {
		const Vector3f ff = _acc_sp;
		_velocityControlPid(dt); // exactly one continuous boundary sample, no STA integration
		StaVelocityProtection::Vec seeds{};
		for (unsigned i = 0; i < 3; ++i) {
			if (candidate.active_axes & (1u << i)) {
				const float correction = _acc_sp(i) - (PX4_ISFINITE(ff(i)) ? ff(i) : 0.f);
				const float s = _vel(i) - _vel_sp(i);
				seeds[i] = correction + _esta_effective.gains[i].lambda1 * sqrtf(fabsf(s)) * sign(s);
				if (!PX4_ISFINITE(correction) || fabsf(correction) > _esta_effective.acceleration_limit[i]) { _esta_failed = true; }
			}
		}
		// A clipped PID demand cannot be claimed to transfer continuously into an
		// unconstrained STA state. Verify the whole original thrust map, not a
		// component-wise acceleration proxy (which differs at nonzero tilt/Z).
		Vector3f body_z = Vector3f(-_acc_sp(0), -_acc_sp(1), CONSTANTS_ONE_G).normalized();
		if (atan2f(Vector2f(_acc_sp).norm(), CONSTANTS_ONE_G) > _lim_tilt) { _esta_failed = true; }
		// Use the same finite-precision mapping, even when the tilt constraint
		// is inactive: limitTilt reconstructs the direction through acos/sin.
		ControlMath::limitTilt(body_z, Vector3f(0, 0, 1), _lim_tilt);
		const Vector3f ideal = body_z * ((_acc_sp(2) / CONSTANTS_ONE_G - 1.f) * _hover_thrust / body_z(2));
		for (int i = 0; i < 3; ++i) {
			if (!PX4_ISFINITE(ideal(i)) || fabsf(ideal(i) - _thr_sp(i)) > 1e-6f) { _esta_failed = true; }
		}
		if (!_esta_failed && !_velocity_protection.seedXYZ(seeds)) { _esta_failed = true; }
		_z_phase = 2;
		_z_engaged = !_esta_failed && (candidate.active_axes & 4);
		return;
	}
	// Normal flight: no velocity PID calculations/integration on any axis.
	// Inactive components retain their acceleration-only FF, never stale nu.
	for (unsigned i = 0; i < 3; ++i) {
		if (candidate.active_axes & (1u << i)) { _acc_sp(i) = !_esta_failed ? candidate.a_req[i] : NAN; }
		_correction(i) = !_esta_failed && (candidate.active_axes & (1u << i))
			? math::constrain(candidate.a_sta[i], -_esta_effective.acceleration_limit[i], _esta_effective.acceleration_limit[i]) : NAN;
	}
	_accelerationControl();
	_thr_sp(2) = math::max(_thr_sp(2), -_lim_thr_max);
	const float remainder = _lim_thr_max * _lim_thr_max - _thr_sp(2) * _thr_sp(2);
	const float max_xy = remainder > 0.f ? sqrtf(remainder) : 0.f;
	const Vector2f horizontal(_thr_sp);
	if (horizontal.norm() > max_xy) { _thr_sp.xy() = horizontal / horizontal.norm() * max_xy; }
	_vel_int.zero();
	_z_engaged = !_esta_failed && (candidate.active_axes & 4);
}

void PositionControl::_accelerationControl()
{
	// Assume standard acceleration due to gravity in vertical direction for attitude generation
	Vector3f body_z = Vector3f(-_acc_sp(0), -_acc_sp(1), CONSTANTS_ONE_G).normalized();
	ControlMath::limitTilt(body_z, Vector3f(0, 0, 1), _lim_tilt);
	// Scale thrust assuming hover thrust produces standard gravity
	float collective_thrust = _acc_sp(2) * (_hover_thrust / CONSTANTS_ONE_G) - _hover_thrust;
	// Project thrust to planned body attitude
	collective_thrust /= (Vector3f(0, 0, 1).dot(body_z));
	collective_thrust = math::min(collective_thrust, -_lim_thr_min);
	_thr_sp = body_z * collective_thrust;
}

bool PositionControl::_updateSuccessful()
{
	bool valid = true;

	// For each controlled state the estimate has to be valid
	for (int i = 0; i <= 2; i++) {
		if (PX4_ISFINITE(_pos_sp(i))) {
			valid = valid && PX4_ISFINITE(_pos(i));
		}

		if (PX4_ISFINITE(_vel_sp(i))) {
			valid = valid && PX4_ISFINITE(_vel(i)) && PX4_ISFINITE(_vel_dot(i));
		}
	}

	// There has to be a valid output accleration and thrust setpoint otherwise there was no
	// setpoint-state pair for each axis that can get controlled
	valid = valid && PX4_ISFINITE(_acc_sp(0)) && PX4_ISFINITE(_acc_sp(1)) && PX4_ISFINITE(_acc_sp(2));
	valid = valid && PX4_ISFINITE(_thr_sp(0)) && PX4_ISFINITE(_thr_sp(1)) && PX4_ISFINITE(_thr_sp(2));
	return valid;
}

void PositionControl::getLocalPositionSetpoint(vehicle_local_position_setpoint_s &local_position_setpoint) const
{
	local_position_setpoint.x = _pos_sp(0);
	local_position_setpoint.y = _pos_sp(1);
	local_position_setpoint.z = _pos_sp(2);
	local_position_setpoint.yaw = _yaw_sp;
	local_position_setpoint.yawspeed = _yawspeed_sp;
	local_position_setpoint.vx = _vel_sp(0);
	local_position_setpoint.vy = _vel_sp(1);
	local_position_setpoint.vz = _vel_sp(2);
	_acc_sp.copyTo(local_position_setpoint.acceleration);
	_thr_sp.copyTo(local_position_setpoint.thrust);
}

void PositionControl::getAttitudeSetpoint(vehicle_attitude_setpoint_s &attitude_setpoint) const
{
	ControlMath::thrustToAttitude(_thr_sp, _yaw_sp, attitude_setpoint);
	attitude_setpoint.yaw_sp_move_rate = _yawspeed_sp;
}
