// SPDX-License-Identifier: BSD-3-Clause
#define MODULE_NAME "logger_functional_test"
#include <gtest/gtest.h>
#include "logged_topics.h"
#ifndef PX4_BOARD_NAME
#define PX4_BOARD_NAME "logger_functional_test"
#endif
#include "logger.h"
#include <lib/parameters/param.h>
using namespace px4::logger;

TEST(EstimatorDiagnosticTopics, PositionEvidenceHasIndependentSlotAndWideMessageId)
{
	static_assert(sizeof(LoggerSubscription{}.msg_id)==2,"ULog IDs must represent 255 distinctly from invalid");
	static_assert(sizeof(logger_status_s{}.num_messages)==2,"Status must represent all 256 subscriptions");
	EXPECT_EQ(MSG_ID_INVALID,UINT16_MAX);
	LoggerSubscription sub; sub.msg_id=255; EXPECT_NE(sub.msg_id,MSG_ID_INVALID);
	LoggedTopics topics;
	ASSERT_TRUE(topics.initialize_logged_topics(static_cast<SDLogProfileMask>(1171)));
	const auto &all=topics.subscriptions();
	EXPECT_EQ(all.count,256);
	for(ORB_ID id : {ORB_ID::vehicle_local_position,ORB_ID::vehicle_local_position_log}) {
		int found=0;
		for(int i=0;i<all.count;++i) if(all.sub[i].id==id && all.sub[i].instance==0) {
			++found; EXPECT_EQ(all.sub[i].interval_ms,0);
		}
		EXPECT_EQ(found,1);
	}
}

TEST(EstimatorDiagnosticTopics, OptInRetainsAllBaselineTopicsWithinCapacity)
{
	LoggedTopics baseline, diagnostic;
	ASSERT_TRUE(baseline.initialize_logged_topics(static_cast<SDLogProfileMask>(147)));
	ASSERT_TRUE(diagnostic.initialize_logged_topics(static_cast<SDLogProfileMask>(147 | 1024)));
	const auto &a = baseline.subscriptions(); const auto &b = diagnostic.subscriptions();
	ASSERT_GT(a.count, 0); ASSERT_LE(b.count, static_cast<int>(LoggedTopics::MAX_TOPICS_NUM));
	ASSERT_EQ(a.count, b.count); // No new subscriptions displace the already-full baseline.
	for (int i = 0; i < a.count; ++i) {
		bool found = false;
		for (int j = 0; j < b.count; ++j) {
			if (a.sub[i].id == b.sub[j].id && a.sub[i].instance == b.sub[j].instance) {
				found = true; EXPECT_LE(b.sub[j].interval_ms, a.sub[i].interval_ms);
			}
		}
		EXPECT_TRUE(found);
	}
	for (ORB_ID id : {ORB_ID::estimator_attitude, ORB_ID::estimator_local_position,
			ORB_ID::estimator_status, ORB_ID::estimator_status_flags}) {
		for (int instance = 0; instance < 6; ++instance) {
			bool found = false;
			for (int j = 0; j < b.count; ++j) {
				if (b.sub[j].id == id && b.sub[j].instance == instance) {
					found = true; EXPECT_EQ(b.sub[j].interval_ms, 0);
				}
			}
			EXPECT_TRUE(found);
		}
	}
	bool baseline_still_throttled = false;
	for (int i = 0; i < a.count; ++i) {
		if (a.sub[i].id == ORB_ID::estimator_local_position) {
			baseline_still_throttled = true; EXPECT_EQ(a.sub[i].interval_ms, 500);
		}
	}
	EXPECT_TRUE(baseline_still_throttled);
	for (ORB_ID id : {ORB_ID::sensor_accel, ORB_ID::vehicle_imu, ORB_ID::vehicle_imu_status}) {
		for (int instance = 0; instance < 3; ++instance) {
			bool found = false;
			for (int j = 0; j < b.count; ++j) {
				if (b.sub[j].id == id && b.sub[j].instance == instance) {
					found = true; EXPECT_EQ(b.sub[j].interval_ms, 0);
				}
			}
			EXPECT_TRUE(found);
		}
	}
}

TEST(EstimatorDiagnosticTopics, TimingBitAndDefaultAreExplicit)
{
	EXPECT_EQ(static_cast<int32_t>(SDLogProfileMask::SITL_IMU_TIMING), 2048);
	const param_t handle = param_find("SDLOG_PROFILE");
	ASSERT_NE(handle, PARAM_INVALID);
	int32_t value = -1;
	ASSERT_EQ(param_get_default_value(handle, &value), 0);
	EXPECT_EQ(value, 1);
}

TEST(EstimatorDiagnosticTopics, LegacyProfilesKeepAllRawGyroInstancesThrottled)
{
	for (int32_t profile : {1, 147, 1041, 1171}) {
		LoggedTopics topics;
		ASSERT_TRUE(topics.initialize_logged_topics(static_cast<SDLogProfileMask>(profile)));
		const auto &all = topics.subscriptions();
		int found = 0;

		for (int i = 0; i < all.count; ++i) {
			if (all.sub[i].id == ORB_ID::sensor_gyro) {
				EXPECT_EQ(all.sub[i].interval_ms, 1000) << "profile " << profile;
				EXPECT_LT(all.sub[i].instance, 4);
				++found;
			}
		}

		EXPECT_EQ(found, 4);
	}
}

namespace
{
void checkTimingOnlyChangesExistingGyro(int32_t profile, int expected_count)
{
	LoggedTopics baseline, timing;
	ASSERT_TRUE(baseline.initialize_logged_topics(static_cast<SDLogProfileMask>(profile)));
	ASSERT_TRUE(timing.initialize_logged_topics(static_cast<SDLogProfileMask>(profile | 2048)));
	const auto &a = baseline.subscriptions();
	const auto &b = timing.subscriptions();
	ASSERT_EQ(a.count, b.count);

	if (expected_count > 0) {
		EXPECT_EQ(a.count, expected_count);
	}

	int changed = 0;
	int fourth_gyro = 0;

	for (int i = 0; i < a.count; ++i) {
		// Index equality deliberately verifies subscription order, not just set membership.
		EXPECT_EQ(a.sub[i].id, b.sub[i].id);
		EXPECT_EQ(a.sub[i].instance, b.sub[i].instance);

		if ((a.sub[i].id == ORB_ID::sensor_gyro) && (a.sub[i].instance < 3)) {
			EXPECT_EQ(a.sub[i].interval_ms, 1000);
			EXPECT_EQ(b.sub[i].interval_ms, 0);
			++changed;

		} else {
			EXPECT_EQ(a.sub[i].interval_ms, b.sub[i].interval_ms);
		}

		if ((b.sub[i].id == ORB_ID::sensor_gyro) && (b.sub[i].instance == 3)) {
			EXPECT_EQ(b.sub[i].interval_ms, 1000);
			++fourth_gyro;
		}
	}

	EXPECT_EQ(changed, 3);
	EXPECT_EQ(fourth_gyro, 1);
}
}

TEST(EstimatorDiagnosticTopics, TimingOptInPreservesAll256ResearchSlotsAndOtherIntervals)
{
	checkTimingOnlyChangesExistingGyro(1171, 256);
}

TEST(EstimatorDiagnosticTopics, ActualRevision06ProfileOnlyChangesThreeGyroIntervals)
{
	// The frozen revision06 experiment used 1041, not the larger 1171 fixture.
	// Do not infer this profile's subscription count from the 256-slot fixture.
	checkTimingOnlyChangesExistingGyro(1041, 0);
}

TEST(EstimatorDiagnosticTopics, TimingOptInIsIndependentOfEstimatorDiagnosticBit)
{
	checkTimingOnlyChangesExistingGyro(1, 0);
}

TEST(EstimatorDiagnosticTopics, TimingBitAloneDoesNotCreateSubscriptions)
{
	LoggedTopics topics;
	EXPECT_FALSE(topics.initialize_logged_topics(SDLogProfileMask::SITL_IMU_TIMING));
	EXPECT_EQ(topics.subscriptions().count, 0);
}
