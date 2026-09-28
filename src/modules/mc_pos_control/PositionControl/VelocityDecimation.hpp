// SPDX-License-Identifier: BSD-3-Clause
#pragma once
#include <cstdint>
#include <cmath>

// Sensor-clock scheduler, not a Run() divider. Resetting a cache does not
// discard elapsed integration time. Same-frame retries never integrate twice.
class VelocityDecimation
{
public:
	void configure(int32_t request, bool armed, bool supported = true)
	{
		requested = request;
		rejected = (request != 1 && request != 2 && request != 4) || (request != 1 && !supported);
		pending = armed && request != divisor;
		if (!armed && !rejected && request != divisor) { divisor = request; restart(); }
	}
	void invalidate() { _cached = false; }
	void restart() { _sample = _update = 0; _count = 0; _cached = false; _key = 0; fault = 0; }
	bool begin(uint64_t sample, float legacy_dt, uint32_t key, bool armed)
	{
		updated = held = false; h = NAN; raw_dt = _sample ? (static_cast<int64_t>(sample) - static_cast<int64_t>(_sample)) * 1e-6f : NAN;
		if (!armed) { fault = 0; }
		const bool bad = !sample || (_sample && (!std::isfinite(raw_dt) || raw_dt < .002f || raw_dt > .04f));
		_sample = sample;
		if (bad) { fault = 1; _cached = false; return false; }
		if (fault) { return false; }
		++_count;
		if (!_cached || key != _key || _count >= divisor) {
			h = _update ? (static_cast<int64_t>(sample) - static_cast<int64_t>(_update)) * 1e-6f : legacy_dt;
			// Separate domains: raw callbacks remain 2..40ms, accumulated h may
			// reach N*40ms. Never clamp h or hide a missed callback.
			if (!std::isfinite(h) || h < .002f || h > .04f * divisor) { fault = 2; return false; }
			_update = sample; _key = key; _count = 0; _cached = true;
			updated = true; ++sequence;
		} else { held = true; }
		return true;
	}
	int32_t requested{1}, divisor{1};
	bool pending{false}, rejected{false}, updated{false}, held{false};
	uint8_t fault{0};
	uint32_t sequence{0};
	float h{NAN}, raw_dt{NAN};
private:
	uint64_t _sample{0}, _update{0};
	uint32_t _key{0};
	int32_t _count{0};
	bool _cached{false};
};
