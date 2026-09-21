// SPDX-License-Identifier: BSD-3-Clause
// Acceptance probes for the unchanged V02 kernel. Failures are evidence, not
// expected-success tests. This file is not registered in the firmware build.
#include "StaVelocityControl.hpp"
#include <gtest/gtest.h>
#include <limits>

using Kernel = StaVelocityControl;

TEST(V03CandidateAudit, ForeignInstanceCannotCommitIntoAnotherController)
{
	Kernel source, target;
	ASSERT_TRUE(source.setParameters(0, {2.f, 1.f}));
	ASSERT_TRUE(target.setParameters(0, {3.f, 2.f}));
	ASSERT_TRUE(source.reset(0, .5f));
	ASSERT_TRUE(target.reset(0, -.5f));
	const auto proposal = source.evaluate(0, 1.f, 0.f, .008f);
	ASSERT_TRUE(proposal.valid());
	EXPECT_NE(target.commit(proposal), Kernel::Status::Ok);
	EXPECT_FLOAT_EQ(target.state()[0], -.5f);
}

TEST(V03CandidateAudit, AxisRetargetCannotCommitWrongAxisState)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {2.f, 1.f}));
	ASSERT_TRUE(kernel.setParameters(1, {3.f, 2.f}));
	ASSERT_TRUE(kernel.reset(0, .5f));
	ASSERT_TRUE(kernel.reset(1, -.5f));
	auto proposal = kernel.evaluate(0, 1.f, 0.f, .008f);
	ASSERT_TRUE(proposal.valid());
	proposal.axis = 1;
	EXPECT_NE(kernel.commit(proposal), Kernel::Status::Ok);
	EXPECT_FLOAT_EQ(kernel.state()[1], -.5f);
}

TEST(V03CandidateAudit, InvalidOutputCannotCommitAnOtherwiseFiniteState)
{
	Kernel kernel;
	ASSERT_TRUE(kernel.setParameters(0, {2.f, 1.f}));
	ASSERT_TRUE(kernel.reset(0, .5f));
	auto proposal = kernel.evaluate(0, 1.f, 0.f, .008f);
	ASSERT_TRUE(proposal.valid());
	proposal.a_sta = std::numeric_limits<float>::quiet_NaN();
	EXPECT_NE(kernel.commit(proposal), Kernel::Status::Ok);
	EXPECT_FLOAT_EQ(kernel.state()[0], .5f);
}
