// SPDX-License-Identifier: BSD-3-Clause
#pragma once
#include <px4_platform_common/defines.h>
#include <cstdint>
#if defined(__PX4_POSIX) && defined(__linux__)
#include <time.h>
#endif
inline uint64_t velocityHostClock()
{
#if defined(__PX4_POSIX) && defined(__linux__)
	struct timespec ts {};
	if (system_clock_gettime(CLOCK_MONOTONIC, &ts) == 0) {
		return uint64_t(ts.tv_sec) * 1000000000ULL + uint64_t(ts.tv_nsec);
	}
#endif
	return 0;
}
