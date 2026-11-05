// SPDX-License-Identifier: BSD-3-Clause
#include "GyroPublicationGuard.hpp"
#include <gtest/gtest.h>
#include <algorithm>
#include <limits>

TEST(GyroPublicationGuard, StartupAndNoFabricatedTime)
{
	GyroPublicationGuard g;
	const auto invalid = g.consider(0, 1, true);
	EXPECT_FALSE(invalid.publish); EXPECT_EQ(invalid.reason, GyroPublicationGuard::Zero);
	EXPECT_EQ(g.lastPublished(), 0u); EXPECT_EQ(g.zero(), 1u);
	EXPECT_TRUE(g.consider(1000000, 1, true).publish);
	EXPECT_EQ(g.lastPublished(), 1000000u);
}

TEST(GyroPublicationGuard, NominalCadenceUnchanged)
{
	for (uint64_t interval : {0u, 125u, 1000u, 4000u, 10000u}) {
		GyroPublicationGuard g; uint64_t marker = 0;

		for (uint64_t sample = 4000; sample < 4000000; sample += 4000) {
			const bool legacy_due = sample >= marker + interval;
			const auto result = g.consider(sample, 1, legacy_due);
			EXPECT_EQ(result.publish, legacy_due);

			if (legacy_due) { marker = std::max(sample - interval, std::min(marker + interval, sample)); }
		}

		EXPECT_EQ(g.duplicates(), 0u); EXPECT_EQ(g.backwards(), 0u);
	}
}

TEST(GyroPublicationGuard, DeviceChangeDoesNotResetMonotonicContract)
{
	GyroPublicationGuard g;
	ASSERT_TRUE(g.consider(1000000, 1, true).publish);
	const auto duplicate = g.consider(1000000, 2, true);
	EXPECT_TRUE(duplicate.switched); EXPECT_TRUE(duplicate.event); EXPECT_FALSE(duplicate.publish);
	EXPECT_EQ(duplicate.reason, GyroPublicationGuard::Duplicate);
	EXPECT_FALSE(g.consider(999000, 2, true).publish);
	EXPECT_EQ(g.lastPublished(), 1000000u);
	EXPECT_TRUE(g.consider(1004000, 2, true).publish);
	EXPECT_EQ(g.duplicates(), 1u); EXPECT_EQ(g.backwards(), 1u); EXPECT_EQ(g.switches(), 1u);
}

TEST(GyroPublicationGuard, CadenceSkippedSampleIsNotCommitted)
{
	GyroPublicationGuard g;
	ASSERT_TRUE(g.consider(1000, 1, true).publish);
	EXPECT_FALSE(g.consider(2000, 1, false).publish);
	EXPECT_EQ(g.lastPublished(), 1000u);
	EXPECT_TRUE(g.consider(2000, 2, true).publish);
	EXPECT_EQ(g.duplicates(), 0u);
}

TEST(GyroPublicationGuard, RealGapAndClockRegressionRemainVisible)
{
	GyroPublicationGuard g;
	g.consider(1000000, 1, true);
	EXPECT_FALSE(g.consider(1, 2, true).publish);
	const auto gap = g.consider(1100000, 2, true);
	ASSERT_TRUE(gap.publish); EXPECT_EQ(g.lastPublished() - gap.previous_sample, 100000u);
	EXPECT_TRUE(g.consider(std::numeric_limits<uint64_t>::max(), 2, true).publish);
	EXPECT_FALSE(g.consider(0, 3, true).publish); // no wrapped artificial time
}

TEST(GyroPublicationGuard, ReplayBothObservedM04Switches)
{
	for (uint64_t sample : {105656000u, 106912000u}) {
		GyroPublicationGuard g;
		ASSERT_TRUE(g.consider(sample - 4000, 1310988, true).publish);
		ASSERT_TRUE(g.consider(sample, 1310988, true).publish);
		const auto rejected = g.consider(sample, 1310996, true);
		ASSERT_FALSE(rejected.publish); EXPECT_TRUE(rejected.switched);
		EXPECT_EQ(rejected.previous_sample, sample);
		ASSERT_TRUE(g.consider(sample + 4000, 1310996, true).publish);
		EXPECT_EQ(g.lastPublished(), sample + 4000);
	}
}
