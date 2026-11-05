// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>
#include <uORB/Publication.hpp>
#include <uORB/Subscription.hpp>
#include "VelocityDiagnosticInput.hpp"
#include <platforms/posix/apps.h>

TEST(VelocityDiagnosticInput, ActualUorb250HzPublisher100HzConsumerReproducesAndFixesStaleRead)
{
	// Anchor PX4's existing daemon stub in this functional test executable.
	apps_map_type apps; init_app_map(apps); ASSERT_TRUE(apps.empty());
	uORB::Publication<sta_rate_ctrl_status_s> pub{ORB_ID(sta_rate_ctrl_status)};
	uORB::Subscription old_sub{ORB_ID(sta_rate_ctrl_status)}, fixed_sub{ORB_ID(sta_rate_ctrl_status)};
	sta_rate_ctrl_status_s sent{}, old{}, fixed{};
	sent.timestamp = 1000000; ASSERT_TRUE(pub.publish(sent));
	VelocityDiagnosticInput::drain(old_sub, old); VelocityDiagnosticInput::drain(fixed_sub, fixed);
	int invalid_old = 0, reads = 0;
	for (unsigned tick = 1; tick <= 500; ++tick) {
		sent.timestamp = 1000000 + tick * 4000; sent.publish_seq = tick;
		ASSERT_TRUE(pub.publish(sent));
		if (tick % 5 == 2 || tick % 5 == 0) { // 8/12 ms alternating callbacks
			ASSERT_TRUE(old_sub.update(&old));
			reads += VelocityDiagnosticInput::drain(fixed_sub, fixed);
			if (!VelocityDiagnosticInput::fresh(sent.timestamp, old.timestamp)) { ++invalid_old; }
			ASSERT_EQ(fixed.timestamp, sent.timestamp); ASSERT_EQ(fixed.publish_seq, tick);
			ASSERT_TRUE(VelocityDiagnosticInput::fresh(sent.timestamp, fixed.timestamp));
		}
	}
	EXPECT_GT(invalid_old, 100); EXPECT_EQ(sent.timestamp - old.timestamp, 124000);
	EXPECT_EQ(reads, 500);
}

TEST(VelocityDiagnosticInput, QueueOverrunBoundedDrainAndRetainedBadMode)
{
	uORB::Publication<sta_rate_ctrl_status_s> pub{ORB_ID(sta_rate_ctrl_status)};
	uORB::Subscription sub{ORB_ID(sta_rate_ctrl_status)};
	sta_rate_ctrl_status_s sent{}, got{};
	sent.timestamp = 5000000; pub.publish(sent); VelocityDiagnosticInput::drain(sub, got);
	for (unsigned i = 1; i <= 40; ++i) {
		sent.timestamp += 4000; sent.publish_seq = i; sent.effective_mode = 2;
		ASSERT_TRUE(pub.publish(sent));
	}
	EXPECT_EQ(VelocityDiagnosticInput::drain(sub, got), 32);
	EXPECT_EQ(got.publish_seq, 40); EXPECT_EQ(got.effective_mode, 2); // Do not relabel a wrong algorithm as PID.
	EXPECT_EQ(VelocityDiagnosticInput::drain(sub, got), 0);
	EXPECT_EQ(got.publish_seq, 40);
}

TEST(VelocityDiagnosticInput, ZeroFutureAndExactExpiryRejected)
{
	EXPECT_FALSE(VelocityDiagnosticInput::fresh(1000000, 0));
	EXPECT_FALSE(VelocityDiagnosticInput::fresh(1000000, 1000001));
	EXPECT_FALSE(VelocityDiagnosticInput::fresh(1000000, 900000));
	EXPECT_TRUE(VelocityDiagnosticInput::fresh(1000000, 900001));
	EXPECT_TRUE(VelocityDiagnosticInput::fresh(1000000, 1000000));
}
