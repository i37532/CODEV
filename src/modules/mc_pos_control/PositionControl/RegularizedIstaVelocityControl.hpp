// SPDX-License-Identifier: BSD-3-Clause
#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>

/**
 * Compensated boundary-layer implicit STA (RI00 equations RI-1..4).
 * s=v-v_sp [m/s], p+h*lambda1*Psi(p)+h^2*lambda2*rho(p)=s,
 * nu_candidate=nu_old-h*lambda2*rho(p),
 * a_sta=-lambda1*Psi(p)+nu_candidate [m/s^2].
 * Only acceleration correction: no FF, mass, rate g, thrust or protection.
 * Evaluation never changes state. Protected commit does NOT rewrite the ideal
 * output or imply that applied values solve the implicit equations.
 * RI01: test-only library, no production selector/actuator path.
 */
class RegularizedIstaVelocityControl
{
public:
	RegularizedIstaVelocityControl();
	RegularizedIstaVelocityControl(const RegularizedIstaVelocityControl &) = delete;
	RegularizedIstaVelocityControl &operator=(const RegularizedIstaVelocityControl &) = delete;
	RegularizedIstaVelocityControl(RegularizedIstaVelocityControl &&) = delete;
	RegularizedIstaVelocityControl &operator=(RegularizedIstaVelocityControl &&) = delete;
	struct Parameters {
		float lambda1{0.f};
		float lambda2{0.f};
		float epsilon{0.f};
	};
	enum class Status : uint8_t {
		Ok, InvalidAxis, Unconfigured, InvalidInput, InvalidDt,
		NumericalError, StaleCandidate, InvalidParameters
	};
	enum class Branch : uint8_t { Inner, Outer };
	struct Candidate {
		Status status{Status::Unconfigured};
		size_t axis{0};
		Branch branch{Branch::Inner};
		float s{std::numeric_limits<float>::quiet_NaN()};
		float p{std::numeric_limits<float>::quiet_NaN()};
		float psi{std::numeric_limits<float>::quiet_NaN()};
		float rho{std::numeric_limits<float>::quiet_NaN()};
		float a_sta{std::numeric_limits<float>::quiet_NaN()};
		float nu_before{std::numeric_limits<float>::quiet_NaN()};
		float nu_next{std::numeric_limits<float>::quiet_NaN()};
		float dt{std::numeric_limits<float>::quiet_NaN()};
		uint64_t config_generation{0};
		uint64_t reset_generation{0};
		uint64_t state_generation{0};
		bool valid() const { return status == Status::Ok; }
	private:
		friend class RegularizedIstaVelocityControl;
		const RegularizedIstaVelocityControl *owner{nullptr};
		uint64_t instance_id{0};
		size_t sealed_axis{0};
		Branch sealed_branch{Branch::Inner};
		std::array<uint64_t, 3> generations{};
		std::array<float, 8> payload{};
	};
	static bool validEpsilon(float epsilon);
	static bool validParameters(const Parameters &parameters);
	bool setParameters(size_t axis, const Parameters &parameters);
	Candidate evaluate(size_t axis, float velocity, float velocity_sp, float dt) const;
	bool current(const Candidate &candidate) const;
	Status commit(const Candidate &candidate);
	Status commitProtected(const Candidate &candidate, float applied_nu);
	// ALL selected candidates checked before any mutation; no safety policy.
	Status commitBatch(const std::array<Candidate, 3> &candidates, uint8_t mask,
			   const std::array<float, 3> &applied_nu);
	bool reset(size_t axis, float nu = 0.f);
	// RI02 handover: validate every selected seed before changing any axis.
	bool resetBatch(uint8_t mask, const std::array<float, 3> &nu);
	void reset();
	const std::array<float, 3> &state() const { return _nu; }
private:
	static bool incrementable(uint64_t generation);
	const uint64_t _instance_id;
	bool _exhausted{false};
	std::array<Parameters, 3> _parameters{};
	std::array<float, 3> _nu{};
	std::array<bool, 3> _configured{};
	std::array<uint64_t, 3> _config_generation{};
	std::array<uint64_t, 3> _reset_generation{};
	std::array<uint64_t, 3> _state_generation{};
};
