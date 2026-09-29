// SPDX-License-Identifier: BSD-3-Clause
// Real Simulator -> drivers -> VehicleIMU -> uORB. Only HRT and scheduling
// are controlled in this offline test. No production source is changed.
#include "../../v04/imu0_chain01/ImuConversionChainTest.cpp"
#include <atomic>
static std::atomic<bool> fixed_clock{false};
static hrt_abstime publication_time = 0;
extern "C" hrt_abstime __real_hrt_absolute_time();
extern "C" hrt_abstime __wrap_hrt_absolute_time()
{
	return fixed_clock ? publication_time : __real_hrt_absolute_time();
}

TEST_F(ImuConversionChain, PublicationTieDistinctSamplesAndGenerations)
{
	struct ClockScope {
		~ClockScope() { fixed_clock = false; }
	} cleanup;
	publication_time = sample + 8000;
	fixed_clock = true;
	step(1.f, 0.f, -CONSTANTS_ONE_G);
	vehicle_imu_s first[3]{};
	unsigned generations[3]{};
	for (int i=0; i<3; ++i) { first[i]=integrated[i]; generations[i]=imu[i].get_last_generation(); }
	step(2.f, 0.f, -CONSTANTS_ONE_G);
	for (int i=0; i<3; ++i) {
		EXPECT_EQ(first[i].timestamp, publication_time);
		EXPECT_EQ(integrated[i].timestamp, first[i].timestamp);
		EXPECT_EQ(integrated[i].timestamp_sample - first[i].timestamp_sample, 4000u);
		EXPECT_EQ(integrated[i].delta_angle_dt, 4000u);
		EXPECT_EQ(integrated[i].delta_velocity_dt, 4000u);
		EXPECT_EQ(imu[i].get_last_generation(), generations[i]+1);
		EXPECT_NE(integrated[i].delta_velocity[0], first[i].delta_velocity[0]);
		EXPECT_EQ(integrated[i].delta_velocity_clipping, 0);
	}
}
