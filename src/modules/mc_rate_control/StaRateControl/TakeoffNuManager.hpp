// SPDX-License-Identifier: BSD-3-Clause
#pragma once

#include <cstdint>
#include <limits>

/** Offline-validated, opt-in lifecycle gate for research nu state.
 *
 * Inputs deliberately mirror onboard estimates and land-detector flags.  No
 * simulator truth is accepted.  The default-disabled path has no effect on the
 * existing controller lifecycle.  A fault remains frozen until disarm so a
 * timeout or estimator discontinuity cannot silently release stale state.
 */
class TakeoffNuManager
{
public:
	enum class State : uint8_t { Disabled, Idle, Waiting, ConfirmingTakeoff, Released, ConfirmingLanding, LandedHold, Fault };
	enum class Event : uint8_t { None, Arm, TakeoffCandidate, TakeoffCancelled, Released, LandingCandidate,
				       LandingCancelled, Landed, EstimatorJump, Timeout, Disarm };

	struct Config {
		bool enabled{false};
		float release_height_m{0.12f};
		float max_takeoff_vz_m_s{0.20f}; // NED: upward is negative
		float max_estimator_step_m{0.50f};
		float landing_height_m{0.08f};
		float max_landing_speed_m_s{0.15f};
		uint64_t takeoff_confirm_us{200000};
		uint64_t landing_confirm_us{500000};
		uint64_t wait_timeout_us{10000000};
	};

	struct Input {
		uint64_t sample{0};
		bool selected{false};
		bool armed{false};
		bool rate_enabled{false};
		bool landed{true};
		bool maybe_landed{true};
		bool estimate_valid{false};
		float z_m{std::numeric_limits<float>::quiet_NaN()}; // local-position NED
		float vz_m_s{std::numeric_limits<float>::quiet_NaN()};
	};

	struct Decision {
		State state{State::Disabled};
		Event event{Event::None};
		bool freeze{false};
		bool reset{false};
		bool abort{false};
	};

	static bool validConfig(const Config &config);
	static bool sameConfig(const Config &a, const Config &b);
	bool setConfig(const Config &config);
	Decision update(const Input &input);
	void reset();
	const Config &config() const { return _config; }
	State state() const { return _state; }

private:
	bool estimateValid(const Input &input) const;
	bool takeoffEvidence(const Input &input) const;
	bool landingEvidence(const Input &input) const;
	Decision decision(Event event = Event::None, bool reset_state = false) const;
	void enterWaiting(const Input &input);

	Config _config{};
	State _state{State::Disabled};
	uint64_t _wait_start{0};
	uint64_t _confirm_start{0};
	uint64_t _last_sample{0};
	float _arm_z{0.f};
	float _last_z{0.f};
	bool _baseline_valid{false};
};
