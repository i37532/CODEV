// SPDX-License-Identifier: BSD-3-Clause
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>

/**
 * Pure regularized explicit STA for local NED velocity, not an actuator path.
 *
 * s = v - v_sp [m/s], rho = sat(s / epsilon),
 * Psi = sqrt(max(abs(s), epsilon)) * rho,
 * a_sta = -lambda1 * Psi + nu_k [m/s^2],
 * nu_candidate = nu_k - h * lambda2 * rho [m/s^2].
 *
 * epsilon is [m/s], lambda1 is (m/s^2)/sqrt(m/s), lambda2 is [m/s^3].
 * Output contains only acceleration correction: no feed-forward, mass, rate
 * input gain, thrust or protection mapping. evaluate() uses old nu and never
 * mutates it; the adapter must decide all coupled constraints before commit.
 * This is not the legacy hard-sign ESTA or an implicit STA implementation.
 */
class RI01RegularizedStaVelocityControl
{
public:
	RI01RegularizedStaVelocityControl() = default;
	RI01RegularizedStaVelocityControl(const RI01RegularizedStaVelocityControl &) = delete;
	RI01RegularizedStaVelocityControl &operator=(const RI01RegularizedStaVelocityControl &) = delete;

	struct Parameters {
		float lambda1{0.f};
		float lambda2{0.f};
		float epsilon{0.f};
	};

	enum class Status : uint8_t {
		Ok,
		InvalidAxis,
		Unconfigured,
		InvalidInput,
		InvalidDt,
		NumericalError,
		StaleCandidate,
		InvalidParameters
	};

	struct Nonlinearity {
		Status status{Status::InvalidParameters};
		float psi{std::numeric_limits<float>::quiet_NaN()};
		float rho{std::numeric_limits<float>::quiet_NaN()};
		bool valid() const { return status == Status::Ok; }
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
	private:
		friend class RI01RegularizedStaVelocityControl;
		const RI01RegularizedStaVelocityControl *owner{nullptr};
		size_t sealed_axis{0};
		uint64_t sealed_revision{0};
		std::array<float, 4> sealed{};
	};

	// R00 engineering domain, not a stability guarantee for arbitrary gains.
	static bool validEpsilon(float epsilon);
	static bool validParameters(const Parameters &parameters);
	// Shared definition for a future HTE/seed adapter. Outside the boundary
	// layer s/epsilon is deliberately never evaluated. Inside, Psi=s/sqrt(eps).
	static Nonlinearity nonlinear(float s, float epsilon);

	// Finite positive normal gains; epsilon in [.001, 1] m/s. Every successful
	// configuration update invalidates this axis's candidates, even if equal.
	bool setParameters(size_t axis, const Parameters &parameters);
	Candidate evaluate(size_t axis, float velocity, float velocity_sp, float dt) const;
	bool current(const Candidate &candidate) const;
	Status commit(const Candidate &candidate);
	// Applied state may differ from ideal nu_next. It does not change this
	// step's ideal output (which was evaluated using old nu).
	Status commitProtected(const Candidate &candidate, float applied_nu);
	bool reset(size_t axis, float nu = 0.f);
	void reset();
	const std::array<float, 3> &state() const { return _nu; }

private:
	std::array<Parameters, 3> _parameters{};
	std::array<float, 3> _nu{};
	std::array<bool, 3> _configured{};
	std::array<uint64_t, 3> _revision{};
};
