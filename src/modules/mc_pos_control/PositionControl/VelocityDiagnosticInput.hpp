// SPDX-License-Identifier: BSD-3-Clause
#pragma once
#include <uORB/topics/sta_rate_ctrl_status.h>

/** Observational input only; never changes the rate controller or its queue.
 * uORB queued update() returns the oldest unread message, NOT the latest.
 * Drain at most the advertised queue capacity, preserving bounded Run time.
 */
class VelocityDiagnosticInput
{
public:
	template<typename Subscription>
	static uint8_t drain(Subscription &sub, sta_rate_ctrl_status_s &status)
	{
		uint8_t count = 0;
		while (count < sta_rate_ctrl_status_s::ORB_QUEUE_LENGTH && sub.update(&status)) { ++count; }
		return count;
	}

	static bool fresh(uint64_t now, uint64_t timestamp)
	{
		return timestamp != 0 && now >= timestamp && now - timestamp < 100000;
	}
};
