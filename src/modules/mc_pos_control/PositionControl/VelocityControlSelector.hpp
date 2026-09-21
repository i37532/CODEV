// SPDX-License-Identifier: BSD-3-Clause
#pragma once

#include <cstdint>

/** Configuration gate only. PID gains and integrator lifecycle are independent.
 * Requests use signed parameter-width values: validate before any narrowing.
 * V01 accepts only (PID, no experimental axes). Rejected requests never become
 * effective; while armed a differing request remains pending until cancelled
 * or considered on disarm. Rejection describes the current request immediately.
 */
class VelocityControlSelector
{
public:

	enum Reject : uint8_t { None = 0, ModeRange = 1, ModeUnimplemented = 2, AxesUnavailable = 4 };

	void configure(int32_t mode, int32_t axes, bool armed)
	{
		_requested_mode = mode;
		_requested_axes = axes;
		_reject = None;

		if (mode < 0 || mode > 2) { _reject |= ModeRange; }
		else if (mode != 0) { _reject |= ModeUnimplemented; }

		if (axes != 0) { _reject |= AxesUnavailable; }

		_pending = armed && (mode != _effective_mode || axes != _effective_axes);

		if (!armed && _reject == None) {
			_effective_mode = mode;
			_effective_axes = axes;
		}
	}

	int32_t requestedMode() const { return _requested_mode; }
	int32_t requestedAxes() const { return _requested_axes; }
	int32_t effectiveMode() const { return _effective_mode; }
	int32_t effectiveAxes() const { return _effective_axes; }
	bool pending() const { return _pending; }
	uint8_t reject() const { return _reject; }

private:
	int32_t _requested_mode{0}, _requested_axes{0};
	int32_t _effective_mode{0}, _effective_axes{0};
	uint8_t _reject{None};
	bool _pending{false};
};
