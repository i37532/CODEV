// SPDX-License-Identifier: BSD-3-Clause
#pragma once

#include "ProperIstaRateControl.hpp"
#include "StaProtection.hpp"

/** Offline-only protection adapter for ProperIstaRateControl.
 *
 * It deliberately has no dependency from mc_rate_control.  Ideal implicit
 * candidates and constrained applied values are separate data.  If nu is
 * changed by protection, the algebraic output mapping is a += 2*(nu-nu*),
 * which follows PDF (11a); the resulting tuple is explicitly not advertised
 * as a strict solution of the original implicit equations.
 */
class ProperIstaProtection
{
public:
	enum class Fault : uint8_t { None, FirstSample, DuplicateTime, BackwardTime, LongGap, ShortDt,
				       Measurement, Configuration, Numerical };
	struct Config {
		bool enabled{false};
		int32_t axes{0};
		std::array<ProperIstaRateControl::Parameters, 3> gains{};
		std::array<float, 3> nu_limit{};
		float c_limit{1.f};
	};
	struct Frame {
		uint64_t sample{0};
		bool armed{false};
		bool rate_enabled{false};
		bool measurement_valid{true};
		bool update_allowed{false}; // lifecycle gate supplied by offline test/I03
	};
	struct Output {
		Output();
		bool valid{false};
		bool updated{false};
		std::array<float, 3> ideal_a{}, ideal_c{}, ideal_nu{}, virtual_s{}, xi{};
		std::array<float, 3> state_mapped_a{}, preclip_c{}, applied_c{}, applied_nu{};
		std::array<uint8_t, 3> branch{}, limits{};
		std::array<bool, 3> strict_implicit{};
	};

	void begin(const Config &requested, const Frame &frame);
	Output step(const std::array<float, 3> &rate, const std::array<float, 3> &sp,
		    const StaProtection::Feedback &feedback, float dt);
	bool acknowledge();
	Fault fault() const { return _fault; }
	bool abortRequested() const { return _fault != Fault::None; }
	bool pending() const { return _pending; }
	const std::array<float, 3> state() const;
	static bool validConfig(const Config &config);

private:
	static bool same(const Config &a, const Config &b);
	void reset();
	void latch(Fault fault) { if (_fault == Fault::None) { _fault = fault; } }
	Config _config{};
	Frame _frame{}, _previous{};
	std::array<ProperIstaRateControl, 3> _kernel{};
	uint64_t _last_sample{0};
	Fault _fault{Fault::None};
	bool _started{false};
	bool _pending{false};
	bool _used{false};
};
