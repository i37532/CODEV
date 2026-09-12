// Copyright (c) 2026 PX4 Development Team. All rights reserved.
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <stdint.h>

/** M01 selection policy: PID is the only executable controller. */
class ControllerSelection
{
public:
	enum Mode : uint8_t { PID = 0 };
	enum RequestStatus : uint8_t {
		Accepted = 0,
		Unsupported = 1,
		InvalidMode = 2,
		InvalidAxes = 3
	};

	struct Status {
		int32_t requested_mode{0};
		int32_t requested_axes{0};
		uint8_t effective_mode{PID};
		uint8_t effective_axes{0};
		RequestStatus request_status{Accepted};
		bool pending{false};
	};

	/** Returns true only when the externally visible selection status changes.
	 * Unsupported/invalid requests are diagnosed immediately. The latest request
	 * is evaluated as a configuration only while disarmed. Returning to the
	 * last evaluated request while armed cancels the pending change.
	 * No request or rejection resets the PID integrator.
	 */
	bool select(int32_t mode, int32_t axes, bool armed)
	{
		const RequestStatus reason = validate(mode, axes);
		const bool pending = armed && (mode != _evaluated_mode || axes != _evaluated_axes);
		const bool changed = mode != _status.requested_mode || axes != _status.requested_axes
				     || reason != _status.request_status || pending != _status.pending;
		_status.requested_mode = mode;
		_status.requested_axes = axes;
		_status.request_status = reason;
		_status.pending = pending;

		if (!armed) {
			_evaluated_mode = mode;
			_evaluated_axes = axes;
		}

		// Both the initial and last supported configuration are PID in M01.
		// Effective axes are zero even when an inactive PID mask is requested.
		return changed;
	}

	const Status &status() const { return _status; }

	static const char *statusName(uint8_t value)
	{
		switch (value) {
		case Accepted: return "accepted";

		case Unsupported: return "unsupported";

		case InvalidMode: return "invalid_mode";

		case InvalidAxes: return "invalid_axes";

		default: return "unknown";
		}
	}

private:
	static RequestStatus validate(int32_t mode, int32_t axes)
	{
		// Check raw signed values before any narrowing conversion/bit masking.
		if (mode < 0 || mode > 2) {
			return InvalidMode;
		}

		if (axes < 0 || axes > 7) {
			return InvalidAxes;
		}

		return mode == PID ? Accepted : Unsupported;
	}

	Status _status{};
	int32_t _evaluated_mode{0};
	int32_t _evaluated_axes{0};
};
