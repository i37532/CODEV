// SPDX-License-Identifier: BSD-3-Clause
#define MODULE_NAME "ekf2_selector_test"
#include <gtest/gtest.h>
#include "EKF2Selector.hpp"
#include <platforms/posix/apps.h>
#include <uORB/PublicationMulti.hpp>
#include <px4_platform_common/px4_work_queue/WorkQueueManager.hpp>

class SelectorQueueAnchor : public px4::WorkItem
{
public:
	SelectorQueueAnchor() : WorkItem("selector_test_anchor", px4::wq_configurations::nav_and_controllers) {}
	void Run() override {}
};
class EKF2SelectorPublication : public ::testing::Test
{
public:
	static void SetUpTestSuite()
	{
		hrt_init(); // Functional gtest main initializes uORB/parameters, not HRT.
		ASSERT_EQ(px4::WorkQueueManagerStart(), 0); px4_usleep(20000);
		_anchor = new SelectorQueueAnchor();
	}
	static void TearDownTestSuite()
	{
		delete _anchor; _anchor = nullptr; px4_usleep(20000);
		EXPECT_EQ(px4::WorkQueueManagerStop(), 0);
	}
private:
	static SelectorQueueAnchor *_anchor;
};
SelectorQueueAnchor *EKF2SelectorPublication::_anchor = nullptr;

// Invoke the real production publication functions synchronously. No filter,
// simulator, armed vehicle or ScheduledWorkItem::Run() is started by this test.
class EKF2SelectorTestAccess
{
public:
	static void select(EKF2Selector &s, uint8_t instance, uint64_t status_sample = 0)
	{
		s._selected_instance = instance;
		s._instance[instance].timestamp_sample_last = status_sample;
	}
	static void local(EKF2Selector &s) { s.PublishVehicleLocalPosition(); }
	static void attitude(EKF2Selector &s) { s.PublishVehicleAttitude(); }
	static void global(EKF2Selector &s) { s.PublishVehicleGlobalPosition(); }
	static void odometry(EKF2Selector &s) { s.PublishVehicleOdometry(); }
	static void wind(EKF2Selector &s) { s.PublishWindEstimate(); }
	static uint64_t sample(const EKF2Selector &s) { return s._local_position_last.timestamp_sample; }
	static uint8_t resets(const EKF2Selector &s) { return s._xy_reset_counter; }
	static uint8_t instance(const EKF2Selector &s) { return s._local_position_instance_prev; }
};

namespace {
using Access = EKF2SelectorTestAccess;
template<typename T>
void checkSequence(orb_id_t input_id, orb_id_t output_id, void (*publish)(EKF2Selector &))
{
	apps_map_type apps; init_app_map(apps);
	EKF2Selector selector;
	uORB::PublicationMulti<T> input{input_id};
	uORB::Subscription output{output_id};
	T message{}, received{}; message.timestamp = 1;
	ASSERT_TRUE(input.advertise());
	Access::select(selector, input.get_instance());
	for (uint64_t sample : {10000, 4000, 8000, 10000, 12000}) {
		message.timestamp_sample = sample; ASSERT_TRUE(input.publish(message)); publish(selector);
		if (sample == 10000 && received.timestamp_sample == 0) {
			ASSERT_TRUE(output.update(&received)); EXPECT_EQ(received.timestamp_sample, sample);
		} else if (sample == 12000) {
			ASSERT_TRUE(output.update(&received)); EXPECT_EQ(received.timestamp_sample, sample);
		} else {
			EXPECT_FALSE(output.update(&received)) << "stale sample " << sample;
		}
	}
	// Status lower bound still applies, and a rejected newer candidate must not
	// consume the last-published watermark or suppress the next valid sample.
	Access::select(selector, input.get_instance(), 20000);
	message.timestamp_sample = 16000; ASSERT_TRUE(input.publish(message)); publish(selector);
	EXPECT_FALSE(output.update(&received));
	Access::select(selector, input.get_instance(), 14000);
	message.timestamp_sample = 14000; ASSERT_TRUE(input.publish(message)); publish(selector);
	ASSERT_TRUE(output.update(&received)); EXPECT_EQ(received.timestamp_sample, 14000u);
}
}

TEST_F(EKF2SelectorPublication, LocalPositionMonotonicAcrossRejectedSamples)
{
	checkSequence<vehicle_local_position_s>(ORB_ID(estimator_local_position), ORB_ID(vehicle_local_position), Access::local);
}
TEST_F(EKF2SelectorPublication, AttitudeMonotonicAcrossRejectedSamples)
{
	checkSequence<vehicle_attitude_s>(ORB_ID(estimator_attitude), ORB_ID(vehicle_attitude), Access::attitude);
}
TEST_F(EKF2SelectorPublication, GlobalPositionMonotonicAcrossRejectedSamples)
{
	checkSequence<vehicle_global_position_s>(ORB_ID(estimator_global_position), ORB_ID(vehicle_global_position), Access::global);
}
TEST_F(EKF2SelectorPublication, OdometryMonotonicAcrossRejectedSamples)
{
	checkSequence<vehicle_odometry_s>(ORB_ID(estimator_odometry), ORB_ID(vehicle_odometry), Access::odometry);
}
TEST_F(EKF2SelectorPublication, WindMonotonicAcrossRejectedSamples)
{
	checkSequence<wind_s>(ORB_ID(estimator_wind), ORB_ID(wind), Access::wind);
}

TEST_F(EKF2SelectorPublication, RejectedInstanceMustNotMutateResetBaseline)
{
	apps_map_type apps; init_app_map(apps);
	EKF2Selector selector;
	uORB::PublicationMulti<vehicle_local_position_s> first{ORB_ID(estimator_local_position)}, second{ORB_ID(estimator_local_position)};
	uORB::Subscription output{ORB_ID(vehicle_local_position)};
	ASSERT_TRUE(first.advertise()); ASSERT_TRUE(second.advertise());
	vehicle_local_position_s m{}, got{}; m.timestamp = 1; m.timestamp_sample = 10000; m.x = 2.f;
	Access::select(selector, first.get_instance()); ASSERT_TRUE(first.publish(m)); Access::local(selector);
	ASSERT_TRUE(output.update(&got)); EXPECT_EQ(got.xy_reset_counter, 0);
	Access::select(selector, second.get_instance()); m.timestamp_sample = 4000; m.x = 100.f;
	ASSERT_TRUE(second.publish(m)); Access::local(selector); EXPECT_FALSE(output.update(&got));
	EXPECT_EQ(Access::sample(selector), 10000u); EXPECT_EQ(Access::resets(selector), 0);
	EXPECT_EQ(Access::instance(selector), first.get_instance());
	m.timestamp_sample = 12000; m.x = 3.f; m.z = -2.f; m.vx = .1f; m.vz = .2f; m.heading = .3f;
	ASSERT_TRUE(second.publish(m)); Access::local(selector); ASSERT_TRUE(output.update(&got));
	EXPECT_EQ(got.xy_reset_counter, 1); EXPECT_FLOAT_EQ(got.delta_xy[0], 1.f);
	EXPECT_EQ(got.z_reset_counter, 1); EXPECT_FLOAT_EQ(got.delta_z, -2.f);
	EXPECT_EQ(got.vxy_reset_counter, 1); EXPECT_FLOAT_EQ(got.delta_vxy[0], .1f);
	EXPECT_EQ(got.vz_reset_counter, 1); EXPECT_FLOAT_EQ(got.delta_vz, .2f);
	EXPECT_EQ(got.heading_reset_counter, 1); EXPECT_NEAR(got.delta_heading, .3f, 1e-6f);
}

TEST_F(EKF2SelectorPublication, TransientStaleInstanceDoesNotCreatePhantomReset)
{
	EKF2Selector selector;
	uORB::PublicationMulti<vehicle_local_position_s> first{ORB_ID(estimator_local_position)}, second{ORB_ID(estimator_local_position)};
	uORB::Subscription output{ORB_ID(vehicle_local_position)};
	ASSERT_TRUE(first.advertise()); ASSERT_TRUE(second.advertise());
	vehicle_local_position_s m{}, got{}; m.timestamp = 1; m.timestamp_sample = 10000;
	Access::select(selector, first.get_instance()); ASSERT_TRUE(first.publish(m)); Access::local(selector);
	ASSERT_TRUE(output.update(&got));
	Access::select(selector, second.get_instance()); m.timestamp_sample = 9000; m.x = 100.f;
	ASSERT_TRUE(second.publish(m)); Access::local(selector); EXPECT_FALSE(output.update(&got));
	Access::select(selector, first.get_instance()); m.timestamp_sample = 12000; m.x = .1f;
	ASSERT_TRUE(first.publish(m)); Access::local(selector); ASSERT_TRUE(output.update(&got));
	EXPECT_EQ(got.xy_reset_counter, 0); EXPECT_EQ(got.z_reset_counter, 0);
	EXPECT_EQ(got.vxy_reset_counter, 0); EXPECT_EQ(got.vz_reset_counter, 0); EXPECT_EQ(got.heading_reset_counter, 0);
}

TEST_F(EKF2SelectorPublication, AttitudeResetDeltaUsesLastPublishedQuaternion)
{
	EKF2Selector selector;
	uORB::PublicationMulti<vehicle_attitude_s> first{ORB_ID(estimator_attitude)}, second{ORB_ID(estimator_attitude)};
	uORB::Subscription output{ORB_ID(vehicle_attitude)};
	ASSERT_TRUE(first.advertise()); ASSERT_TRUE(second.advertise());
	vehicle_attitude_s m{}, got{}; m.timestamp = 1; m.timestamp_sample = 10000;
	m.q[0] = 1.f; m.delta_q_reset[0] = 1.f;
	Access::select(selector, first.get_instance()); ASSERT_TRUE(first.publish(m)); Access::attitude(selector);
	ASSERT_TRUE(output.update(&got));
	Access::select(selector, second.get_instance()); m.timestamp_sample = 4000;
	matrix::Quatf(matrix::Eulerf(0.f, 0.f, 1.f)).copyTo(m.q);
	ASSERT_TRUE(second.publish(m)); Access::attitude(selector); EXPECT_FALSE(output.update(&got));
	m.timestamp_sample = 12000; const matrix::Quatf expected(matrix::Eulerf(0.f, 0.f, .3f)); expected.copyTo(m.q);
	ASSERT_TRUE(second.publish(m)); Access::attitude(selector); ASSERT_TRUE(output.update(&got));
	EXPECT_EQ(got.quat_reset_counter, 1);
	for (int axis = 0; axis < 4; ++axis) { EXPECT_NEAR(got.delta_q_reset[axis], expected(axis), 1e-6f); }
}

TEST_F(EKF2SelectorPublication, StaleGlobalResetDoesNotConsumeNextValidReset)
{
	EKF2Selector selector;
	uORB::PublicationMulti<vehicle_global_position_s> input{ORB_ID(estimator_global_position)};
	uORB::Subscription output{ORB_ID(vehicle_global_position)};
	ASSERT_TRUE(input.advertise()); Access::select(selector, input.get_instance());
	vehicle_global_position_s m{}, got{}; m.timestamp = 1; m.timestamp_sample = 10000;
	ASSERT_TRUE(input.publish(m)); Access::global(selector); ASSERT_TRUE(output.update(&got));
	m.timestamp_sample = 4000; m.alt_reset_counter = 1; m.delta_alt = 99.f;
	ASSERT_TRUE(input.publish(m)); Access::global(selector); EXPECT_FALSE(output.update(&got));
	m.timestamp_sample = 12000; m.delta_alt = 2.f;
	ASSERT_TRUE(input.publish(m)); Access::global(selector); ASSERT_TRUE(output.update(&got));
	EXPECT_EQ(got.alt_reset_counter, 1); EXPECT_FLOAT_EQ(got.delta_alt, 2.f);
}

TEST_F(EKF2SelectorPublication, NominalSamplesAndCounterWrapPreservePayload)
{
	EKF2Selector selector;
	uORB::PublicationMulti<vehicle_local_position_s> input{ORB_ID(estimator_local_position)};
	uORB::Subscription output{ORB_ID(vehicle_local_position)};
	ASSERT_TRUE(input.advertise()); Access::select(selector, input.get_instance());
	vehicle_local_position_s m{}, got{}; m.timestamp = 1; m.xy_reset_counter = 255;
	for (int k = 1; k <= 2048; ++k) {
		m.timestamp_sample = uint64_t(k) * 8000; m.x = float(k) * .125f;
		if (k == 2) { m.xy_reset_counter = 0; m.delta_xy[0] = .125f; }
		ASSERT_TRUE(input.publish(m)); Access::local(selector); ASSERT_TRUE(output.update(&got));
		EXPECT_EQ(got.timestamp_sample, m.timestamp_sample); EXPECT_FLOAT_EQ(got.x, m.x);
		EXPECT_EQ(got.xy_reset_counter, m.xy_reset_counter);
		EXPECT_FLOAT_EQ(got.delta_xy[0], m.delta_xy[0]);
	}
}
