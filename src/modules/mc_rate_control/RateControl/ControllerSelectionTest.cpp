// Copyright (c) 2026 PX4 Development Team. All rights reserved.
// SPDX-License-Identifier: BSD-3-Clause

#include <gtest/gtest.h>
#include <ControllerSelection.hpp>
#include <limits>

TEST(ControllerSelection, DefaultPid)
{
	ControllerSelection selector;
	const auto &s = selector.status();
	EXPECT_EQ(s.requested_mode, 0);
	EXPECT_EQ(s.requested_axes, 0);
	EXPECT_EQ(s.effective_mode, ControllerSelection::PID);
	EXPECT_EQ(s.effective_axes, 0);
	EXPECT_EQ(s.request_status, ControllerSelection::Accepted);
	EXPECT_FALSE(s.pending);
	EXPECT_FALSE(selector.select(0, 0, false));
	EXPECT_FALSE(selector.select(0, 0, true));
}

TEST(ControllerSelection, EveryValidMaskForEveryKnownMode)
{
	for (int mode = 0; mode <= 2; ++mode) {
		for (int axes = 0; axes <= 7; ++axes) {
			SCOPED_TRACE(::testing::Message() << "mode=" << mode << " axes=" << axes);
			ControllerSelection selector;
			selector.select(mode, axes, false);
			const auto &s = selector.status();
			EXPECT_EQ(s.requested_mode, mode);
			EXPECT_EQ(s.requested_axes, axes);
			EXPECT_EQ(s.effective_mode, ControllerSelection::PID);
			EXPECT_EQ(s.effective_axes, 0);
			EXPECT_EQ(s.request_status, mode == 0 ? ControllerSelection::Accepted : ControllerSelection::Unsupported);
			EXPECT_FALSE(s.pending);
			EXPECT_FALSE(selector.select(mode, axes, false));
		}
	}
}

TEST(ControllerSelection, RejectsRawInvalidValuesWithoutTruncation)
{
	const int32_t invalid[] = {-1, -256, 256, std::numeric_limits<int32_t>::min(), std::numeric_limits<int32_t>::max()};
	ControllerSelection selector;

	for (int32_t value : invalid) {
		selector.select(value, 0, false);
		EXPECT_EQ(selector.status().requested_mode, value);
		EXPECT_EQ(selector.status().request_status, ControllerSelection::InvalidMode);
		EXPECT_EQ(selector.status().effective_mode, ControllerSelection::PID);
		selector.select(0, value, false);
		EXPECT_EQ(selector.status().requested_axes, value);
		EXPECT_EQ(selector.status().request_status, ControllerSelection::InvalidAxes);
		EXPECT_EQ(selector.status().effective_axes, 0);
	}

	selector.select(3, 0, false);
	EXPECT_EQ(selector.status().request_status, ControllerSelection::InvalidMode);
	selector.select(1, 8, false);
	EXPECT_EQ(selector.status().request_status, ControllerSelection::InvalidAxes);
}

TEST(ControllerSelection, ArmedLatestRequestEvaluatedOnDisarm)
{
	ControllerSelection selector;
	EXPECT_TRUE(selector.select(1, 1, true));
	EXPECT_TRUE(selector.status().pending);
	EXPECT_EQ(selector.status().request_status, ControllerSelection::Unsupported);
	EXPECT_FALSE(selector.select(1, 1, true));
	EXPECT_TRUE(selector.select(2, 7, true));
	EXPECT_EQ(selector.status().requested_mode, 2);
	EXPECT_EQ(selector.status().effective_mode, ControllerSelection::PID);
	EXPECT_TRUE(selector.status().pending);
	EXPECT_TRUE(selector.select(2, 7, false));
	EXPECT_FALSE(selector.status().pending);
	EXPECT_EQ(selector.status().request_status, ControllerSelection::Unsupported);
	EXPECT_FALSE(selector.select(2, 7, true));
	EXPECT_TRUE(selector.select(0, 0, true));
	EXPECT_TRUE(selector.status().pending);
	EXPECT_TRUE(selector.select(0, 0, false));
	EXPECT_FALSE(selector.status().pending);
	EXPECT_EQ(selector.status().request_status, ControllerSelection::Accepted);
}

TEST(ControllerSelection, CancelsPendingRequestAndIgnoresMaskInPid)
{
	ControllerSelection selector;
	selector.select(0, 7, true);
	EXPECT_TRUE(selector.status().pending);
	EXPECT_EQ(selector.status().effective_axes, 0);
	selector.select(0, 0, true);
	EXPECT_FALSE(selector.status().pending);
	selector.select(0, 7, false);
	EXPECT_FALSE(selector.status().pending);
	EXPECT_EQ(selector.status().effective_axes, 0);
	selector.select(-1, -1, true);
	EXPECT_TRUE(selector.status().pending);
	EXPECT_EQ(selector.status().request_status, ControllerSelection::InvalidMode);
	selector.select(0, 7, true);
	EXPECT_FALSE(selector.status().pending);
}
