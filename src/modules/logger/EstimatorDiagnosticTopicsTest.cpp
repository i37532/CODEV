// SPDX-License-Identifier: BSD-3-Clause
#define MODULE_NAME "logger_functional_test"
#include <gtest/gtest.h>
#include "logged_topics.h"
#ifndef PX4_BOARD_NAME
#define PX4_BOARD_NAME "logger_functional_test"
#endif
#include "logger.h"
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
