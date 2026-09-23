// SPDX-License-Identifier: BSD-3-Clause
#pragma once
#include "StaVelocityControl.hpp"

/** V03-tested adapter; V04 PositionControl connects only SITL X. Local NED.
 * Caller supplies the complete constrained thrust-map proxy, NOT measured
 * acceleration or body-frame mixer signs. Existing PID ARW is unrelated.
 * begin/evaluate/finish is one transaction per sensor sample, including retries.
 */
class StaVelocityProtection
{
public:

	using Vec = std::array<float, 3>;
	struct Config {
		std::array<StaVelocityControl::Parameters, 3> gains{};
		Vec nu_limit{}, acceleration_limit{};
		uint8_t axes{0};
	};
	struct Frame {
		uint64_t sample{0};
		bool armed{false}, enabled{false}, flying{false}, landed{true}, contact{true};
		bool inner_valid{true}; // Caller verifies measured inner PID, not requested params.
		// Post-position-control target and ACTUALLY consumed (possibly Z-blended) velocity.
		Vec velocity{}, target{}, ff{};
		// Non-covariant EKF reset: target and estimate not translated together.
		uint8_t unmatched_reset_axes{0};
	};
	enum Fault : uint16_t { Time = 1, Measurement = 2, ResetMismatch = 4, Numerical = 8, Feedback = 16 };
	enum Flag : uint16_t { Priming = 1, Inactive = 2, Duplicate = 4, StateLimit = 8,
		CorrectionLimit = 16, OutwardFreeze = 32, Latched = 64, Reset = 128 };
	struct Result {
		Vec s{}, nu_before{}, nu_ideal{}, nu_applied{}, a_sta{}, a_req{}, a_proxy{};
		float raw_dt{0.f};
		uint8_t active_axes{0}, committed_axes{0};
		uint16_t flags{0}, fault{0};
	};

	bool configure(const Config &config, bool armed);
	bool pending() const { return _pending; }
	bool rejected() const { return _rejected; }
	uint32_t generation() const { return _generation; }
	const Result &begin(const Frame &frame);
	// constrained_axes is NED, derived from the common mapping. No motor bits.
	// Validate ALL selected axes and feedback before any axis state is committed.
	const Result &finish(const Vec &proxy, uint8_t constrained_axes, bool feedback_valid);
	const Vec &state() const { return _kernel.state(); }
	static bool validConfig(const Config &config);

private:
	static bool same(const Config &a, const Config &b);
	void resetState();
	void latch(uint16_t reason);
	StaVelocityControl _kernel;
	Config _config{};
	std::array<StaVelocityControl::Candidate, 3> _candidates{};
	Result _result{};
	uint64_t _last_sample{0};
	uint32_t _generation{0};
	uint16_t _fault{0};
	bool _configured{false}, _pending{false}, _rejected{false}, _active{false}, _open{false};
};
