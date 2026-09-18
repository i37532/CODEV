// Copyright (c) 2026 PX4 Development Team. All rights reserved.
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <ControllerSelection.hpp>
#include <RateControl.hpp>

/** PID reference entry point; module composes protected ESTA/ISTA on selected axes.
 * Lifecycle decisions remain in MulticopterRateControl at their original
 * call sites; this adapter adds no output limits, resets or float arithmetic.
 */
class RateControlDispatcher
{
public:
	bool select(int32_t mode, int32_t axes, bool armed, bool esta_ready = false, bool ista_ready = false,
		    bool proper_ista_ready = false)
	{
		return _selection.select(mode, axes, armed, esta_ready, ista_ready, proper_ista_ready);
	}
	const ControllerSelection::Status &selectionStatus() const { return _selection.status(); }
	bool pidRequired() const { return _selection.status().effective_axes != 7; }
	uint32_t pidUpdateSequence() const { return _pid_update_seq; }

	void setGains(const matrix::Vector3f &p, const matrix::Vector3f &i, const matrix::Vector3f &d)
	{
		_pid.setGains(p, i, d);
	}
	void setIntegratorLimit(const matrix::Vector3f &limit) { _pid.setIntegratorLimit(limit); }
	void setFeedForwardGain(const matrix::Vector3f &ff) { _pid.setFeedForwardGain(ff); }
	void setSaturationStatus(const MultirotorMixer::saturation_status &status) { _pid.setSaturationStatus(status); }
	void resetIntegral() { _pid.resetIntegral(); }
	void getRateControlStatus(rate_ctrl_status_s &status) { _pid.getRateControlStatus(status); }

	matrix::Vector3f update(const matrix::Vector3f &rate, const matrix::Vector3f &rate_sp,
				const matrix::Vector3f &angular_accel, float dt, bool landed)
	{
		// No idle PID integration in all-axis ESTA/ISTA. NaNs are placeholders, NOT a
		// safe actuator command: atomic application must replace all three axes.
		// Faults suppress publication, never implicitly resume a stale PID.
		if (!pidRequired()) { return matrix::Vector3f(NAN, NAN, NAN); }
		// Mixed-axis stages compute complete PID once, retaining its state order.
		// The module replaces selected axes using the protected selected algorithm.
		++_pid_update_seq;
		return _pid.update(rate, rate_sp, angular_accel, dt, landed);
	}

private:
	ControllerSelection _selection;
	RateControl _pid;
	uint32_t _pid_update_seq{0};
};
