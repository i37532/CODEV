// SPDX-License-Identifier: BSD-3-Clause
#pragma once
#include <cstdint>

/** Publication contract, independent of the rate scheduler's lagging marker.
 * Keep the last actual publication across device/FIFO changes. Do not rewrite
 * timestamps: a real gap is still visible downstream. Filtering is unchanged.
 */
class GyroPublicationGuard
{
public:
	enum Reason : uint8_t { Accepted = 0, Duplicate = 1, Backward = 2, Zero = 3, NotDue = 4 };
	struct Result {
		bool publish{false}, switched{false}, event{false};
		Reason reason{NotDue};
		uint64_t previous_sample{0};
	};
	Result consider(uint64_t sample, uint32_t device, bool due)
	{
		Result result;
		result.previous_sample = _last_published;
		result.switched = _device != 0 && device != _device;
		result.event = _device != device;

		if (result.switched) { ++_switches; }

		_device = device;

		if (sample == 0) { result.reason = Zero; ++_zero; }

		else if (sample == _last_published) { result.reason = Duplicate; ++_duplicate; }

		else if (sample < _last_published) { result.reason = Backward; ++_backward; }

		else if (due) { result.reason = Accepted; result.publish = true; _last_published = sample; }

		if (result.reason == Duplicate || result.reason == Backward || result.reason == Zero) { result.event = true; }

		return result;
	}
	uint32_t duplicates() const { return _duplicate; }
	uint32_t backwards() const { return _backward; }
	uint32_t zero() const { return _zero; }
	uint32_t switches() const { return _switches; }
	uint64_t lastPublished() const { return _last_published; }
private:
	uint64_t _last_published{0};
	uint32_t _device{0}, _duplicate{0}, _backward{0}, _zero{0}, _switches{0};
};
