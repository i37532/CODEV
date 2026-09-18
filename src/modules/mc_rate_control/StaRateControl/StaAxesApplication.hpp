// SPDX-License-Identifier: BSD-3-Clause
#pragma once
#include "StaProtection.hpp"
#include <cmath>

/** Iris model gate and atomic selected-axis application. No automatic PID takeover. */
struct StaAxesApplication {
	static bool ready(bool iris_sitl, const StaProtection::Config &c)
	{
		const bool legacy_ready = (c.mode == 1 || c.mode == 2) && (c.axes == 1 || c.axes == 3 || c.axes == 7);
		// I04 intentionally exposes Proper-ISTA only on roll and only with the
		// established lifecycle selected by I03. Pitch/yaw expansion belongs to I05.
		const bool proper_ready = c.mode == 3 && c.axes == 1 && !c.takeoff.enabled;
		return iris_sitl && (legacy_ready || proper_ready)
		       && StaProtection::validConfig(c) && fabsf(c.gains[0].g - 130.575283f) < .01f
		       && (c.axes == 1 || fabsf(c.gains[1].g - 112.763533f) < .01f)
		       && (c.axes != 7 || fabsf(c.gains[2].g - 34.582326f) < .01f);
	}

	static bool apply(uint8_t axes, bool armed, const StaProtection::Output &esta,
			  const std::array<float, 3> &pid, std::array<float, 3> &command)
	{
		command = pid;
		if (axes == 0) { return true; }
		if (axes != 1 && axes != 3 && axes != 7) { return false; }
		// Validate all selected axes before modifying any output.
		if (armed) {
			if (!esta.valid) { return false; }
			for (size_t i = 0; i < 3; ++i) {
				if ((axes & (1 << i)) && !std::isfinite(esta.c_applied[i])) { return false; }
			}
		}
		for (size_t i = 0; i < 3; ++i) {
			if (axes & (1 << i)) { command[i] = armed ? esta.c_applied[i] : 0.f; }
		}
		return true;
	}
};
