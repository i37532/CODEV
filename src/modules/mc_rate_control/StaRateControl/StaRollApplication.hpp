// SPDX-License-Identifier: BSD-3-Clause
#pragma once
#include "StaProtection.hpp"
#include <cmath>

/** No automatic fallback. False means suppress publication and abort SITL.
 * Non-experimental axes retain the original PID bit patterns.
 */
struct StaRollApplication {
	static bool apply(bool selected, bool armed, const StaProtection::Output &esta,
			  const std::array<float, 3> &pid, std::array<float, 3> &command)
	{
		command = pid;

		if (!selected) { return true; }

		if (!armed) { command[0] = 0.f; return true; } // motors disarmed, NOT a fault response

		if (!esta.valid || !std::isfinite(esta.c_applied[0])) { return false; }

		command[0] = esta.c_applied[0];
		return true;
	}
};
