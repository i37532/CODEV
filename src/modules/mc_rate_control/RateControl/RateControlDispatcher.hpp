// Copyright (c) 2026 PX4 Development Team. All rights reserved.
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <ControllerSelection.hpp>
#include <RateControl.hpp>

/** Controller entry point. M01 dispatches exclusively to the original PID.
 * Lifecycle decisions remain in MulticopterRateControl at their original
 * call sites; this adapter adds no output limits, resets or float arithmetic.
 */
class RateControlDispatcher
{
public:
	bool select(int32_t mode, int32_t axes, bool armed) { return _selection.select(mode, axes, armed); }
	const ControllerSelection::Status &selectionStatus() const { return _selection.status(); }

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
		// Requested mode is diagnostic only until a new controller is implemented.
		// Selection guarantees effective_mode == PID; exactly one PID update.
		return _pid.update(rate, rate_sp, angular_accel, dt, landed);
	}

private:
	ControllerSelection _selection;
	RateControl _pid;
};
