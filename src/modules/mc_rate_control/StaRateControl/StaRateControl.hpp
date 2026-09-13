// SPDX-License-Identifier: BSD-3-Clause
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>

/** Pure explicit-Euler STA kernel. Not an actuator controller or a safety adapter.
 * s = rate - rate_sp [rad/s]; a and nu [rad/s^2]; c_raw = a / g [normalized].
 * No clipping, boundary layer, feedforward, extra PID term or implicit update.
 * Each successful update advances ONLY the selected axis, exactly once.
 * Caller must check Result::valid(); invalid payload is NaN, NOT a safe command.
 */
class StaRateControl
{
public:

	struct Parameters {
		float lambda1{0.f}; // (rad/s^2) / sqrt(rad/s)
		float lambda2{0.f}; // rad/s^3
		float g{0.f};       // rad/s^2 per normalized torque command; requires calibration before flight
	};

	enum class Status : uint8_t {
		Ok, InvalidAxis, Unconfigured, InvalidInput, InvalidDt, NumericalError
	};

	struct Result {
		Status status{Status::Unconfigured};
		float s{std::numeric_limits<float>::quiet_NaN()};
		float a{std::numeric_limits<float>::quiet_NaN()};
		float c_raw{std::numeric_limits<float>::quiet_NaN()};
		float nu_next{std::numeric_limits<float>::quiet_NaN()};
		bool valid() const { return status == Status::Ok; }
	};

	// Gains and dt must be finite, positive NORMAL floats (no subnormal configuration).
	// This numerical domain is NOT a stability region or permission to fly at any dt.
	static bool validParameters(const Parameters &parameters);
	// Invalid configuration leaves the previous configuration AND nu intact.
	// Successful configuration also preserves nu; lifecycle reset belongs to the caller.
	bool setParameters(size_t axis, const Parameters &parameters);
	Result update(size_t axis, float rate, float rate_sp, float dt);
	bool reset(size_t axis, float nu = 0.f); // finite nu [rad/s^2], selected axis only
	void reset();                         // all axes to zero, preserves configuration
	const std::array<float, 3> &state() const { return _nu; }

private:

	std::array<Parameters, 3> _parameters{};
	std::array<float, 3> _nu{};
	std::array<bool, 3> _configured{};
};
