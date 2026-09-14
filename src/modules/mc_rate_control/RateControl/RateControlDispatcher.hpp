// Copyright (c) 2026 PX4 Development Team. All rights reserved.
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <ControllerSelection.hpp>
#include <RateControl.hpp>

/** PID reference entry point; M04 module composes protected ESTA on roll only.
 * Lifecycle decisions remain in MulticopterRateControl at their original
 * call sites; this adapter adds no output limits, resets or float arithmetic.
 */
class RateControlDispatcher
{
public:
	bool select(int32_t mode, int32_t axes, bool armed, bool esta_ready = false) { return _selection.select(mode, axes, armed, esta_ready); }
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
		// M04 computes the complete PID once so pitch/yaw state order is unchanged.
		// The module replaces only roll using the separately protected ESTA output.
		return _pid.update(rate, rate_sp, angular_accel, dt, landed);
	}

private:
	ControllerSelection _selection;
	RateControl _pid;
};
