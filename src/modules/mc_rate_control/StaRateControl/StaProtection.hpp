// SPDX-License-Identifier: BSD-3-Clause
#pragma once
#include "StaRateControl.hpp"
#include "IstaRateControl.hpp"
#include "ProperIstaRateControl.hpp"
#include "TakeoffNuManager.hpp"

/** Shared research adapter. ESTA/ISTA support Iris SITL AXES=1/3/7; I05-A
 * permits Proper-ISTA on calibrated Iris SITL AXES=1/3.
 * PID does not pass through these limits/resets. A fault returns invalid output,
 * latches until explicit disarmed acknowledgement, and requests SITL abort.
 * No automatic PID takeover, zero-torque fallback or commander override.
 */
class StaProtection
{
public:

	enum Fault : uint8_t { None, FirstSample, DuplicateTime, BackwardTime, LongGap, ShortDt, Measurement, Configuration, Numerical,
			       TakeoffManagement };
	enum Reset : uint16_t { Startup = 1, Disarm = 2, Exit = 4, Landed = 8, ConfigChanged = 16, Acknowledge = 32,
				TakeoffManaged = 64 };
	enum Limit : uint8_t { MixerFreeze = 1, FeedbackInvalid = 2, NuLimit = 4, OutputLimit = 8 };
	struct Config {
		int32_t mode{0}, axes{0};
		std::array<StaRateControl::Parameters, 3> gains{};
		std::array<float, 3> nu_limit{}; // rad/s^2; zero is unconfigured, not a flight default
		float c_limit{1.f};
		TakeoffNuManager::Config takeoff{}; // experimental and default-off
	};
	struct Frame {
		uint64_t sample{0};
		bool armed{false}, rate_enabled{false}, landed{true}, maybe_landed{true};
		bool measurement_valid{true}, experiment_active{false};
		bool decimated{false}; // timing/measurement latch also protects decimated PID
		bool local_position_valid{false};
		float local_z{std::numeric_limits<float>::quiet_NaN()}; // onboard NED estimate only
		float local_vz{std::numeric_limits<float>::quiet_NaN()};
	};
	struct StateDecision {
		float nu{std::numeric_limits<float>::quiet_NaN()};
		uint8_t limits{0};
		bool valid{false};
	};
	struct Feedback {
		uint64_t timestamp{0}, now{0}; // publication-clock age, not sensor-clock age
		uint16_t bits{0};
		bool valid() const { return (bits & 1) && timestamp > 0 && now >= timestamp && now - timestamp <= 20000; }
	};
	struct Output {
		Output()
		{
			const float nan = std::numeric_limits<float>::quiet_NaN();
			a.fill(nan); c_raw.fill(nan); c_applied.fill(nan); nu_candidate.fill(nan);
			xi.fill(nan); virtual_s.fill(nan); a_protected.fill(nan); branch.fill(255);
		}
		bool valid{false}, updated{false};
		std::array<float, 3> a{}, c_raw{}, c_applied{}, nu{};
		std::array<float, 3> nu_candidate{}, xi{}, virtual_s{}, a_protected{};
		std::array<uint8_t, 3> branch{};
		std::array<uint8_t, 3> limits{};
	};

	void begin(const Config &requested, const Frame &frame);
	Output step(const std::array<float, 3> &rate, const std::array<float, 3> &sp, const Feedback &feedback,
		    bool allow_frozen = false, float update_dt = 0.f);
	bool acknowledge(); // only disarmed; never silently clear a flight fault
	const Config &config() const { return _config; }
	const std::array<float, 3> &state() const
	{
		return _config.mode == 2 ? _ista.state() : (_config.mode == 3 ? _proper.state() : _kernel.state());
	}
	float rawDt() const { return _raw_dt; }
	Fault timing() const { return _timing; }
	Fault fault() const { return _fault; }
	uint16_t resetReason() const { return _reset; }
	bool pending() const { return _pending; }
	bool configValid() const { return _request_valid; }
	bool canUpdate() const { return _allowed && !_used && _fault == None; }
	bool abortRequested() const { return _fault != None; }
	TakeoffNuManager::State takeoffState() const { return _takeoff.state(); }
	const TakeoffNuManager::Decision &takeoffDecision() const { return _takeoff_decision; }
	uint32_t configSequence() const { return _config_seq; }
	static bool validConfig(const Config &config);
	static StateDecision protectState(float old_nu, float candidate_nu, float candidate_c, float g,
					 float nu_limit, float c_limit, const Feedback &feedback);

private:
	static bool same(const Config &a, const Config &b);
	void clear(uint16_t reason) { _kernel.reset(); _ista.reset(); _proper.reset(); _reset |= reason; }
	void latch(Fault fault) { if (_fault == None) { _fault = fault; } }
	Config _config{};
	Frame _previous{}, _frame{};
	StaRateControl _kernel;
	IstaRateControl _ista;
	ProperIstaRateControl _proper;
	TakeoffNuManager _takeoff;
	TakeoffNuManager::Decision _takeoff_decision{};
	uint64_t _last_sample{0};
	uint32_t _config_seq{0};
	uint16_t _reset{0};
	float _raw_dt{0.f};
	Fault _timing{FirstSample}, _fault{None};
	bool _started{false}, _pending{false}, _request_valid{false}, _allowed{false}, _used{false};
};
