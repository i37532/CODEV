// SPDX-License-Identifier: BSD-3-Clause
// Deterministic evidence: real uORB, two independently scheduled subscribers.
// No controller, estimator, logger, or topic queue is modified.
#include "../../v04/imu0_chain01/ImuConversionChainTest.cpp"
#include <uORB/topics/vehicle_local_position.h>

TEST_F(ImuConversionChain, LatestValueSubscriberCanMissConsumedPosition)
{
	static_assert(uORB::DefaultQueueSize<vehicle_local_position_s>::value == 1,
		"Re-audit when the position queue changes");
	uORB::Publication<vehicle_local_position_s> pub{ORB_ID(vehicle_local_position)};
	uORB::Subscription control{ORB_ID(vehicle_local_position)};
	uORB::Subscription logging{ORB_ID(vehicle_local_position)};
	vehicle_local_position_s in{}, fast{}, slow{};
	in.timestamp = in.timestamp_sample = 99304000;
	ASSERT_TRUE(pub.publish(in));
	ASSERT_TRUE(control.update(&fast));
	ASSERT_TRUE(logging.update(&slow));
	const unsigned generation = logging.get_last_generation();
	in.timestamp = in.timestamp_sample = 99316000;
	ASSERT_TRUE(pub.publish(in));
	ASSERT_TRUE(control.update(&fast));
	EXPECT_EQ(fast.timestamp, 99316000u);
	// Logger has not copied this generation when the next sample is published.
	in.timestamp = in.timestamp_sample = 99324000;
	ASSERT_TRUE(pub.publish(in));
	ASSERT_TRUE(logging.update(&slow));
	EXPECT_EQ(slow.timestamp, 99324000u);
	EXPECT_EQ(logging.get_last_generation() - generation, 2u);
	EXPECT_FALSE(logging.update(&slow)); // Waiting cannot recover the overwritten row.
	EXPECT_EQ(fast.timestamp, 99316000u); // The controller did receive it.
}

TEST_F(ImuConversionChain, PromptSubscriberRetainsEachPosition)
{
	uORB::Publication<vehicle_local_position_s> pub{ORB_ID(vehicle_local_position)};
	uORB::Subscription logging{ORB_ID(vehicle_local_position)};
	vehicle_local_position_s in{}, read{};
	for (uint64_t t : {99304000ull, 99316000ull, 99324000ull}) {
		in.timestamp = in.timestamp_sample = t;
		ASSERT_TRUE(pub.publish(in));
		ASSERT_TRUE(logging.update(&read));
		EXPECT_EQ(read.timestamp, t);
		EXPECT_EQ(read.timestamp_sample, t);
	}
}
