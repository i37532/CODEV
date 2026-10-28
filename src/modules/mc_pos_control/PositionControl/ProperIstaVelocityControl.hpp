// SPDX-License-Identifier: BSD-3-Clause
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>

/**
 * Independent Proper Implicit velocity core, arXiv:2406.16094v1 (11a)/(12)/(13).
 * s=v-v_sp [m/s], a_sta/nu [m/s^2]. Only acceleration correction: no FF,
 * mass, rate input gain, gravity, protection, uORB, or actuator admission.
 * z=s+h*(a_sta-nu_next) is virtual, not the next measured velocity error.
 * Ideal candidates use the old nu and are committed separately, at most once.
 * Float inputs/state/output; binary64 solve and z/xi diagnostics. Gradual
 * subnormals and round-to-nearest are required. PV01 qualifies x86 SSE SITL
 * only; other architectures explicitly reject until separately validated.
 * No deadzone or regularization.
 * Serial use; object reconstruction is distinguished by a nonwrapping ID.
 */
class ProperIstaVelocityControl
{
public:
	ProperIstaVelocityControl();
	ProperIstaVelocityControl(const ProperIstaVelocityControl &) = delete;
	ProperIstaVelocityControl &operator=(const ProperIstaVelocityControl &) = delete;
	ProperIstaVelocityControl(ProperIstaVelocityControl &&) = delete;
	ProperIstaVelocityControl &operator=(ProperIstaVelocityControl &&) = delete;

	struct Parameters {
		float lambda1{0.f};
		float lambda2{0.f};
	};

	enum class Status : uint8_t {
		Ok, InvalidAxis, Unconfigured, InvalidInput, InvalidDt,
		NumericalError, StaleCandidate, InvalidParameters, UnsupportedEnvironment
	};
	enum class Branch : uint8_t { Positive = 1, Sliding = 2, Negative = 3, Invalid = 255 };
	struct Candidate {
		Status status{Status::Unconfigured};
		size_t axis{0};
		Branch branch{Branch::Invalid};
		float s{std::numeric_limits<float>::quiet_NaN()};
		double virtual_s{std::numeric_limits<double>::quiet_NaN()};
		double xi{std::numeric_limits<double>::quiet_NaN()};
		float a_sta{std::numeric_limits<float>::quiet_NaN()};
		float nu_before{std::numeric_limits<float>::quiet_NaN()};
		float nu_next{std::numeric_limits<float>::quiet_NaN()};
		float dt{std::numeric_limits<float>::quiet_NaN()};
		uint64_t config_generation{0};
		uint64_t reset_generation{0};
		uint64_t state_generation{0};
		bool valid() const { return status == Status::Ok; }
	private:
		friend class ProperIstaVelocityControl;
		const ProperIstaVelocityControl *owner{nullptr};
		uint64_t instance_id{0};
		size_t sealed_axis{0};
		Branch sealed_branch{Branch::Invalid};
		std::array<uint64_t, 3> generations{};
		std::array<float, 5> payload{};
		std::array<double, 2> wide_payload{};
	};

	// Observes but never changes the floating-point environment. Unsupported
	// FTZ/DAZ/rounding/fast-math fails closed before subnormal input widening.
	static bool floatingPointEnvironmentSupported();
	static bool validParameters(const Parameters &parameters);
	bool setParameters(size_t axis, const Parameters &parameters); // preserves nu
	Candidate evaluate(size_t axis, float velocity, float velocity_sp, float dt) const;
	bool current(const Candidate &candidate) const;
	Status commit(const Candidate &candidate); // ideal state only, no PV02 protection API
	bool reset(size_t axis, float nu = 0.f);
	bool reset(); // all axes atomically, preserving parameters
	const std::array<float, 3> &state() const { return _nu; }

private:
	static bool incrementable(uint64_t generation);
	const uint64_t _instance_id;
	std::array<Parameters, 3> _parameters{};
	std::array<float, 3> _nu{};
	std::array<bool, 3> _configured{};
	std::array<uint64_t, 3> _config_generation{};
	std::array<uint64_t, 3> _reset_generation{};
	std::array<uint64_t, 3> _state_generation{};
};
