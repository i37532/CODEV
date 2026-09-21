// SPDX-License-Identifier: BSD-3-Clause
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>

/**
 * Pure explicit-Euler super-twisting kernel for the local NED velocity loop.
 *
 * This class is deliberately not wired into PositionControl in V02.  It has no
 * thrust, attitude, mass, input-gain or feed-forward mapping: its output is an
 * acceleration correction a_sta [m/s^2].  The future V03 adapter must add the
 * existing acceleration feed-forward exactly once, then decide whether it may
 * commit this candidate after all coupled constraints have been evaluated.
 *
 * s = v - v_sp [m/s]
 * a_sta = -lambda1 sqrt(|s|) sign(s) + nu_k [m/s^2]
 * nu_next = nu_k - h lambda2 sign(s) [m/s^2]
 *
 * lambda1 is (m/s^2)/sqrt(m/s), lambda2 is m/s^3 and h is seconds.  This is
 * an explicit update: evaluate() observes and outputs the old nu, while
 * commit() advances nu exactly once.  It is neither an actuator controller nor
 * a safety/constraint adapter.
 */
class StaVelocityControl
{
public:

	struct Parameters {
		float lambda1{0.f};
		float lambda2{0.f};
	};

	enum class Status : uint8_t {
		Ok,
		InvalidAxis,
		Unconfigured,
		InvalidInput,
		InvalidDt,
		NumericalError,
		StaleCandidate
	};

	struct Candidate {
		Status status{Status::Unconfigured};
		size_t axis{0};
		float s{std::numeric_limits<float>::quiet_NaN()};
		float a_sta{std::numeric_limits<float>::quiet_NaN()};
		float nu_before{std::numeric_limits<float>::quiet_NaN()};
		float nu_next{std::numeric_limits<float>::quiet_NaN()};
		uint64_t revision{0};
		bool valid() const { return status == Status::Ok; }
	};

	// Configuration values must be finite positive normal floats.  Updating a
	// configuration preserves nu but invalidates an already evaluated candidate.
	static bool validParameters(const Parameters &parameters);
	bool setParameters(size_t axis, const Parameters &parameters);

	// evaluate() never mutates state. commit() accepts a candidate at most once;
	// a reset, parameter update or prior commit makes it stale.
	Candidate evaluate(size_t axis, float velocity, float velocity_sp, float dt) const;
	Status commit(const Candidate &candidate);

	bool reset(size_t axis, float nu = 0.f);
	void reset();
	const std::array<float, 3> &state() const { return _nu; }

private:
	std::array<Parameters, 3> _parameters{};
	std::array<float, 3> _nu{};
	std::array<bool, 3> _configured{};
	std::array<uint64_t, 3> _revision{};
};
