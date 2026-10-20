// SPDX-License-Identifier: BSD-3-Clause
#define MODULE_NAME "ekf2_selector_timing_test"
#include <gtest/gtest.h>
#include "EKF2Selector.hpp"
#include <platforms/posix/apps.h>
#include <uORB/PublicationMulti.hpp>
#include <px4_platform_common/px4_work_queue/WorkQueueManager.hpp>
#include <thread>

namespace
{
thread_local bool test_clock_enabled = false;
thread_local hrt_abstime test_clock_us = 0;

class ScopedClock
{
public:
	explicit ScopedClock(hrt_abstime now) : _enabled(test_clock_enabled), _time(test_clock_us)
	{
		test_clock_us = now;
		test_clock_enabled = true;
	}
	~ScopedClock()
	{
		test_clock_us = _time;
		test_clock_enabled = _enabled;
	}
private:
	const bool _enabled;
	const hrt_abstime _time;
};
}

extern "C" hrt_abstime __real_hrt_absolute_time();
extern "C" hrt_abstime __wrap_hrt_absolute_time()
{
	return test_clock_enabled ? test_clock_us : __real_hrt_absolute_time();
}

// No Start(), Run(), callback registration, simulated vehicle or selector
// decision is invoked: only the actual production UpdateErrorScores body.
class EKF2SelectorTimingTestAccess
{
public:
	static void prepare(EKF2Selector &selector, uint8_t primary, hrt_abstime attitude_timestamp)
	{
		estimator_status_s discarded{};
		for (auto &instance : selector._instance) {
			while (instance.estimator_status_sub.update(&discarded)) {}
			instance.healthy = false;
			instance.timeout = true;
			instance.filter_fault = false;
			instance.healthy_count = 0;
			instance.combined_test_ratio = .1f;
			instance.relative_test_ratio = 0.f;
		}
		selector._selected_instance = primary;
		selector._available_instances = primary + 1;
		selector._attitude_last.timestamp = attitude_timestamp;
	}
	static void seed(EKF2Selector &selector, uint8_t index, hrt_abstime sample)
	{
		auto &instance = selector._instance[index];
		instance.timestamp_sample_last = sample;
		instance.healthy = true;
		instance.timeout = false;
		instance.filter_fault = false;
		instance.accel_device_id = 100 + index;
		instance.gyro_device_id = 200 + index;
	}
	static bool update(EKF2Selector &selector) { return selector.UpdateErrorScores(); }
	static bool healthy(const EKF2Selector &s, uint8_t i) { return s._instance[i].healthy; }
	static bool timeout(const EKF2Selector &s, uint8_t i) { return s._instance[i].timeout; }
	static bool fault(const EKF2Selector &s, uint8_t i) { return s._instance[i].filter_fault; }
	static uint8_t recoveries(const EKF2Selector &s, uint8_t i) { return s._instance[i].healthy_count; }
	static hrt_abstime sample(const EKF2Selector &s, uint8_t i) { return s._instance[i].timestamp_sample_last; }
};

namespace
{
using Access = EKF2SelectorTimingTestAccess;
constexpr hrt_abstime Now = 1000000000000ULL;

class TimingQueueAnchor : public px4::WorkItem
{
public:
	TimingQueueAnchor() : WorkItem("selector_timing_anchor", px4::wq_configurations::nav_and_controllers) {}
	void Run() override {}
};

class EKF2SelectorTiming : public ::testing::Test
{
public:
	static void SetUpTestSuite()
	{
		hrt_init();
		ASSERT_EQ(px4::WorkQueueManagerStart(), 0);
		// Only setup/teardown use host-clock waits. Timing assertions never sleep.
		px4_usleep(20000);
		_anchor = new TimingQueueAnchor();
	}
	static void TearDownTestSuite()
	{
		EXPECT_FALSE(test_clock_enabled);
		delete _anchor;
		_anchor = nullptr;
		px4_usleep(20000);
		EXPECT_EQ(px4::WorkQueueManagerStop(), 0);
	}
protected:
	void SetUp() override { EXPECT_FALSE(test_clock_enabled); }
	void TearDown() override { EXPECT_FALSE(test_clock_enabled); }
private:
	static TimingQueueAnchor *_anchor;
};
TimingQueueAnchor *EKF2SelectorTiming::_anchor = nullptr;

estimator_status_s status(hrt_abstime sample, uint32_t fault = 0)
{
	estimator_status_s message{};
	message.timestamp = Now;
	message.timestamp_sample = sample;
	message.vel_test_ratio = .1f;
	message.pos_test_ratio = .1f;
	message.hgt_test_ratio = .1f;
	message.accel_device_id = 100;
	message.gyro_device_id = 200;
	message.filter_fault_flags = fault;
	return message;
}

void checkBoundary(hrt_abstime attitude_age, hrt_abstime status_age, bool timed_out)
{
	EKF2Selector selector;
	Access::prepare(selector, 0, Now - attitude_age);
	Access::seed(selector, 0, Now - status_age);
	{
		ScopedClock clock(Now);
		ASSERT_EQ(hrt_absolute_time(), Now);
		Access::update(selector);
	}
	EXPECT_EQ(Access::timeout(selector, 0), timed_out);
	EXPECT_EQ(Access::healthy(selector, 0), !timed_out);
	EXPECT_FALSE(Access::fault(selector, 0));
	EXPECT_EQ(Access::sample(selector, 0), Now - status_age);
}

// One fixture suite owns one WorkQueueManager lifecycle. PX4's process-global
// manager is not restarted between parameterized and ordinary test suites.
TEST_F(EKF2SelectorTiming, StaleAttitudeStatus19999us) { checkBoundary(10001, 19999, false); }
TEST_F(EKF2SelectorTiming, StaleAttitudeStatus20000us) { checkBoundary(10001, 20000, false); }
TEST_F(EKF2SelectorTiming, StaleAttitudeStatus20001us) { checkBoundary(10001, 20001, true); }
TEST_F(EKF2SelectorTiming, FreshAttitudeStatus49999us) { checkBoundary(10000, 49999, false); }
TEST_F(EKF2SelectorTiming, FreshAttitudeStatus50000us) { checkBoundary(10000, 50000, false); }
TEST_F(EKF2SelectorTiming, FreshAttitudeStatus50001us) { checkBoundary(10000, 50001, true); }
TEST_F(EKF2SelectorTiming, Attitude9999usUses50ms) { checkBoundary(9999, 24000, false); }
TEST_F(EKF2SelectorTiming, Attitude10000usUses50ms) { checkBoundary(10000, 24000, false); }
TEST_F(EKF2SelectorTiming, Attitude10001usUses20ms) { checkBoundary(10001, 24000, true); }

TEST_F(EKF2SelectorTiming, ClockOverrideIsThreadLocalAndRestored)
{
	const hrt_abstime before = __real_hrt_absolute_time();
	hrt_abstime other_thread = 0;
	{
		ScopedClock clock(Now);
		EXPECT_EQ(hrt_absolute_time(), Now);
		std::thread worker([&other_thread]() { other_thread = hrt_absolute_time(); });
		worker.join();
		EXPECT_EQ(hrt_absolute_time(), Now);
	}
	const hrt_abstime after = __real_hrt_absolute_time();
	EXPECT_GE(other_thread, before);
	EXPECT_LE(other_thread, after);
	EXPECT_GE(hrt_absolute_time(), after);
	EXPECT_FALSE(test_clock_enabled);
}

TEST_F(EKF2SelectorTiming, QueuedFreshStatusPreventsNoUpdateTimeout)
{
	EKF2Selector selector;
	uORB::PublicationMulti<estimator_status_s> input{ORB_ID(estimator_status)};
	ASSERT_TRUE(input.advertise());
	const uint8_t i = input.get_instance();
	ASSERT_LT(i, EKF2_MAX_INSTANCES);
	Access::prepare(selector, i, Now - 24000);
	Access::seed(selector, i, Now - 60001);
	ASSERT_TRUE(input.publish(status(Now - 4000)));
	{
		ScopedClock clock(Now);
		EXPECT_TRUE(Access::update(selector));
		EXPECT_FALSE(Access::update(selector));
	}
	EXPECT_TRUE(Access::healthy(selector, i));
	EXPECT_FALSE(Access::timeout(selector, i));
	EXPECT_EQ(Access::sample(selector, i), Now - 4000);
}

TEST_F(EKF2SelectorTiming, NewlyPublishedOldSampleDefersTimeoutOnlyOneUpdate)
{
	EKF2Selector selector;
	uORB::PublicationMulti<estimator_status_s> input{ORB_ID(estimator_status)};
	ASSERT_TRUE(input.advertise());
	const uint8_t i = input.get_instance();
	ASSERT_LT(i, EKF2_MAX_INSTANCES);
	Access::prepare(selector, i, Now - 24000);
	Access::seed(selector, i, Now - 4000);
	// A fresh publication does not make its old sample timestamp fresh. This
	// documents existing branch order; it does not propose a timeout waiver.
	ASSERT_TRUE(input.publish(status(Now - 60001)));
	{
		ScopedClock clock(Now);
		EXPECT_TRUE(Access::update(selector));
		EXPECT_FALSE(Access::timeout(selector, i));
		EXPECT_TRUE(Access::healthy(selector, i));
		EXPECT_TRUE(Access::update(selector));
	}
	EXPECT_TRUE(Access::timeout(selector, i));
	EXPECT_FALSE(Access::healthy(selector, i));
	EXPECT_EQ(Access::sample(selector, i), Now - 60001);
}

TEST_F(EKF2SelectorTiming, NewHealthyStatusRecoversTimeoutWithoutSharingState)
{
	EKF2Selector selector;
	uORB::PublicationMulti<estimator_status_s> input{ORB_ID(estimator_status)};
	ASSERT_TRUE(input.advertise());
	const uint8_t i = input.get_instance();
	ASSERT_LT(i, EKF2_MAX_INSTANCES);
	Access::prepare(selector, i, Now - 24000);
	Access::seed(selector, i, Now - 24000);
	{
		ScopedClock clock(Now);
		EXPECT_TRUE(Access::update(selector));
		ASSERT_TRUE(Access::timeout(selector, i));
		EXPECT_EQ(Access::recoveries(selector, i), 0);
		ASSERT_TRUE(input.publish(status(Now - 4000)));
		EXPECT_TRUE(Access::update(selector));
	}
	EXPECT_TRUE(Access::healthy(selector, i));
	EXPECT_FALSE(Access::timeout(selector, i));
	EXPECT_FALSE(Access::fault(selector, i));
	EXPECT_EQ(Access::recoveries(selector, i), 1);
}

TEST_F(EKF2SelectorTiming, FilterFaultIsNotClearedByFreshPublicationTime)
{
	EKF2Selector selector;
	uORB::PublicationMulti<estimator_status_s> input{ORB_ID(estimator_status)};
	ASSERT_TRUE(input.advertise());
	const uint8_t i = input.get_instance();
	ASSERT_LT(i, EKF2_MAX_INSTANCES);
	Access::prepare(selector, i, Now - 24000);
	Access::seed(selector, i, Now - 4000);
	ASSERT_TRUE(input.publish(status(Now - 4000, 1)));
	{
		ScopedClock clock(Now);
		EXPECT_TRUE(Access::update(selector));
		EXPECT_TRUE(Access::fault(selector, i));
		EXPECT_FALSE(Access::healthy(selector, i));
		EXPECT_FALSE(Access::timeout(selector, i));
		ASSERT_TRUE(input.publish(status(Now - 2000)));
		EXPECT_TRUE(Access::update(selector));
	}
	EXPECT_FALSE(Access::fault(selector, i));
	EXPECT_TRUE(Access::healthy(selector, i));
	EXPECT_FALSE(Access::timeout(selector, i));
	EXPECT_EQ(Access::recoveries(selector, i), 1);
}

TEST_F(EKF2SelectorTiming, InstancesHaveIndependentSampleTimeoutAndFaultState)
{
	EKF2Selector selector;
	uORB::PublicationMulti<estimator_status_s> first{ORB_ID(estimator_status)};
	uORB::PublicationMulti<estimator_status_s> second{ORB_ID(estimator_status)};
	ASSERT_TRUE(first.advertise());
	ASSERT_TRUE(second.advertise());
	const uint8_t a = first.get_instance(), b = second.get_instance();
	ASSERT_LT(a, EKF2_MAX_INSTANCES);
	ASSERT_LT(b, EKF2_MAX_INSTANCES);
	ASSERT_NE(a, b);
	Access::prepare(selector, a, Now - 24000);
	Access::seed(selector, a, Now - 24000);
	Access::seed(selector, b, Now - 4000);
	{
		ScopedClock clock(Now);
		EXPECT_TRUE(Access::update(selector));
		EXPECT_TRUE(Access::timeout(selector, a));
		EXPECT_FALSE(Access::healthy(selector, a));
		EXPECT_FALSE(Access::timeout(selector, b));
		EXPECT_TRUE(Access::healthy(selector, b));
		ASSERT_TRUE(first.publish(status(Now - 1000)));
		ASSERT_TRUE(second.publish(status(Now - 3000, 2)));
		EXPECT_TRUE(Access::update(selector));
	}
	EXPECT_FALSE(Access::timeout(selector, a));
	EXPECT_TRUE(Access::healthy(selector, a));
	EXPECT_FALSE(Access::fault(selector, a));
	EXPECT_FALSE(Access::timeout(selector, b));
	EXPECT_FALSE(Access::healthy(selector, b));
	EXPECT_TRUE(Access::fault(selector, b));
	EXPECT_EQ(Access::sample(selector, a), Now - 1000);
	EXPECT_EQ(Access::sample(selector, b), Now - 3000);
}
}
