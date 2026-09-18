// SPDX-License-Identifier: BSD-3-Clause
#pragma once

#include "StaRateControl.hpp"

/** Offline-only, unconstrained Proper Implicit STA (arXiv:2406.16094v1,
 * PDF (11a), (12), (13)). Not the original IstaRateControl / MODE=2.
 * s=rate-rate_sp [rad/s], a/nu [rad/s^2], c_raw=a/g [normalized].
 * virtual_s = s + dt*(a-nu_next), NOT the next physical plant state.
 * No clipping, protection, feedforward or actuator connection.
 * Positive normal gains/dt; finite normal-or-zero states and results.
 * Binary64 intermediates, checked binary32 narrowing, no iterative solve.
 * Numerical validity is not the theorem's gain condition or flight approval.
 * Serial use only. Candidates must not outlive their owning object.
 */
class ProperIstaRateControl
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

	// Read-only ideal candidate. evaluate() never changes nu; commit() accepts
	// only this object's current axis generation, at most once. A reset or
	// successful parameter change invalidates outstanding candidates on that axis.
	// No API for committing a clipped/frozen candidate: that belongs to I02.
	class Candidate
	{
	public:
		const Result &result() const { return _result; }
	private:
		friend class ProperIstaRateControl;
		Result _result{};
		const ProperIstaRateControl *_owner{nullptr};
		size_t _axis{3};
		uint64_t _generation{0};
	};

	ProperIstaRateControl() = default;
	ProperIstaRateControl(const ProperIstaRateControl &) = delete;
	ProperIstaRateControl &operator=(const ProperIstaRateControl &) = delete;
	static bool validParameters(const Parameters &parameters);
	bool setParameters(size_t axis, const Parameters &parameters); // preserves nu
	Candidate evaluate(size_t axis, float rate, float rate_sp, float dt) const;
	bool commit(const Candidate &candidate);
	Result update(size_t axis, float rate, float rate_sp, float dt); // evaluate + one commit
	bool reset(size_t axis, float nu = 0.f);
	void reset(); // all axes; preserves parameters
	const std::array<float, 3> &state() const { return _nu; }

private:
	std::array<Parameters, 3> _parameters{};
	std::array<float, 3> _nu{};
	std::array<bool, 3> _configured{};
	std::array<uint64_t, 3> _generation{};
};
