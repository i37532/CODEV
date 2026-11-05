// SPDX-License-Identifier: BSD-3-Clause
#pragma once

#include "StaRateControl.hpp"

/** Pure analytic implicit STA; NOT connected to the dispatcher in M07.
 * Same s=rate-rate_sp, a/nu [rad/s^2], c_raw=a/g units as ESTA.
 * virtual_s predicts the unconstrained unit-acceleration object, not a vehicle.
 * No saturation, anti-windup, lifecycle policy or runtime iterative solver.
 * Double intermediates protect float inputs against cancellation/product overflow.
 * Nonzero subnormal/overflowing float outputs are rejected atomically (no FTZ reliance).
 * Rounded outputs must satisfy each implicit equation within 8 float epsilons
 * of its largest term; extreme double cancellation is otherwise rejected too.
 * Numerical validity is not stability, a safe command, or permission to fly.
 */
class IstaRateControl
{
public:

	using Parameters = StaRateControl::Parameters;
	using Status = StaRateControl::Status;
	enum class Branch : uint8_t { Positive = 1, Sliding = 2, Negative = 3, Invalid = 255 };
	struct Result : StaRateControl::Result {
		float virtual_s{std::numeric_limits<float>::quiet_NaN()};
		float xi{std::numeric_limits<float>::quiet_NaN()};
		Branch branch{Branch::Invalid};
	};

	static bool validParameters(const Parameters &parameters);
	bool setParameters(size_t axis, const Parameters &parameters); // preserves nu; invalid is atomic
	Result update(size_t axis, float rate, float rate_sp, float dt);
	bool reset(size_t axis, float nu = 0.f); // same finite-state contract as ESTA
	void reset();
	const std::array<float, 3> &state() const { return _nu; }

private:
	std::array<Parameters, 3> _parameters{};
	std::array<float, 3> _nu{};
	std::array<bool, 3> _configured{};
};
