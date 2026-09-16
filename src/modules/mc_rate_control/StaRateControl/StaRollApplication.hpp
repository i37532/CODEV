// SPDX-License-Identifier: BSD-3-Clause
#pragma once
#include "StaAxesApplication.hpp"
#include <cmath>

/** No automatic fallback. False means suppress publication and abort SITL.
 * Non-experimental axes retain the original PID bit patterns.
 */
struct StaRollApplication {
	static bool apply(bool selected, bool armed, const StaProtection::Output &esta,
			  const std::array<float, 3> &pid, std::array<float, 3> &command)
	{
		return StaAxesApplication::apply(selected ? 1 : 0, armed, esta, pid, command);
	}
};
