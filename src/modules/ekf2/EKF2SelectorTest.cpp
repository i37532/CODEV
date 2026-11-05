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

#if defined(CONFIG_ARCH_BOARD_PX4_SITL)
#include <cstring>
namespace {
void logEqual(const vehicle_local_position_s &a, const vehicle_local_position_log_s &b)
{
	EXPECT_EQ(std::memcmp(&a.timestamp, &b.timestamp, sizeof(a.timestamp)), 0) << "timestamp";
	EXPECT_EQ(std::memcmp(&a.timestamp_sample, &b.timestamp_sample, sizeof(a.timestamp_sample)), 0) << "timestamp_sample";
	EXPECT_EQ(std::memcmp(&a.xy_valid, &b.xy_valid, sizeof(a.xy_valid)), 0) << "xy_valid";
	EXPECT_EQ(std::memcmp(&a.z_valid, &b.z_valid, sizeof(a.z_valid)), 0) << "z_valid";
	EXPECT_EQ(std::memcmp(&a.v_xy_valid, &b.v_xy_valid, sizeof(a.v_xy_valid)), 0) << "v_xy_valid";
	EXPECT_EQ(std::memcmp(&a.v_z_valid, &b.v_z_valid, sizeof(a.v_z_valid)), 0) << "v_z_valid";
	EXPECT_EQ(std::memcmp(&a.x, &b.x, sizeof(a.x)), 0) << "x";
	EXPECT_EQ(std::memcmp(&a.y, &b.y, sizeof(a.y)), 0) << "y";
	EXPECT_EQ(std::memcmp(&a.z, &b.z, sizeof(a.z)), 0) << "z";
	EXPECT_EQ(std::memcmp(&a.delta_xy, &b.delta_xy, sizeof(a.delta_xy)), 0) << "delta_xy";
	EXPECT_EQ(std::memcmp(&a.xy_reset_counter, &b.xy_reset_counter, sizeof(a.xy_reset_counter)), 0) << "xy_reset_counter";
	EXPECT_EQ(std::memcmp(&a.delta_z, &b.delta_z, sizeof(a.delta_z)), 0) << "delta_z";
	EXPECT_EQ(std::memcmp(&a.z_reset_counter, &b.z_reset_counter, sizeof(a.z_reset_counter)), 0) << "z_reset_counter";
	EXPECT_EQ(std::memcmp(&a.vx, &b.vx, sizeof(a.vx)), 0) << "vx";
	EXPECT_EQ(std::memcmp(&a.vy, &b.vy, sizeof(a.vy)), 0) << "vy";
	EXPECT_EQ(std::memcmp(&a.vz, &b.vz, sizeof(a.vz)), 0) << "vz";
	EXPECT_EQ(std::memcmp(&a.z_deriv, &b.z_deriv, sizeof(a.z_deriv)), 0) << "z_deriv";
	EXPECT_EQ(std::memcmp(&a.delta_vxy, &b.delta_vxy, sizeof(a.delta_vxy)), 0) << "delta_vxy";
	EXPECT_EQ(std::memcmp(&a.vxy_reset_counter, &b.vxy_reset_counter, sizeof(a.vxy_reset_counter)), 0) << "vxy_reset_counter";
	EXPECT_EQ(std::memcmp(&a.delta_vz, &b.delta_vz, sizeof(a.delta_vz)), 0) << "delta_vz";
	EXPECT_EQ(std::memcmp(&a.vz_reset_counter, &b.vz_reset_counter, sizeof(a.vz_reset_counter)), 0) << "vz_reset_counter";
	EXPECT_EQ(std::memcmp(&a.ax, &b.ax, sizeof(a.ax)), 0) << "ax";
	EXPECT_EQ(std::memcmp(&a.ay, &b.ay, sizeof(a.ay)), 0) << "ay";
	EXPECT_EQ(std::memcmp(&a.az, &b.az, sizeof(a.az)), 0) << "az";
	EXPECT_EQ(std::memcmp(&a.heading, &b.heading, sizeof(a.heading)), 0) << "heading";
	EXPECT_EQ(std::memcmp(&a.delta_heading, &b.delta_heading, sizeof(a.delta_heading)), 0) << "delta_heading";
	EXPECT_EQ(std::memcmp(&a.heading_reset_counter, &b.heading_reset_counter, sizeof(a.heading_reset_counter)), 0) << "heading_reset_counter";
	EXPECT_EQ(std::memcmp(&a.xy_global, &b.xy_global, sizeof(a.xy_global)), 0) << "xy_global";
	EXPECT_EQ(std::memcmp(&a.z_global, &b.z_global, sizeof(a.z_global)), 0) << "z_global";
	EXPECT_EQ(std::memcmp(&a.ref_timestamp, &b.ref_timestamp, sizeof(a.ref_timestamp)), 0) << "ref_timestamp";
	EXPECT_EQ(std::memcmp(&a.ref_lat, &b.ref_lat, sizeof(a.ref_lat)), 0) << "ref_lat";
	EXPECT_EQ(std::memcmp(&a.ref_lon, &b.ref_lon, sizeof(a.ref_lon)), 0) << "ref_lon";
	EXPECT_EQ(std::memcmp(&a.ref_alt, &b.ref_alt, sizeof(a.ref_alt)), 0) << "ref_alt";
	EXPECT_EQ(std::memcmp(&a.dist_bottom, &b.dist_bottom, sizeof(a.dist_bottom)), 0) << "dist_bottom";
	EXPECT_EQ(std::memcmp(&a.dist_bottom_valid, &b.dist_bottom_valid, sizeof(a.dist_bottom_valid)), 0) << "dist_bottom_valid";
	EXPECT_EQ(std::memcmp(&a.dist_bottom_sensor_bitfield, &b.dist_bottom_sensor_bitfield, sizeof(a.dist_bottom_sensor_bitfield)), 0) << "dist_bottom_sensor_bitfield";
	EXPECT_EQ(std::memcmp(&a.eph, &b.eph, sizeof(a.eph)), 0) << "eph";
	EXPECT_EQ(std::memcmp(&a.epv, &b.epv, sizeof(a.epv)), 0) << "epv";
	EXPECT_EQ(std::memcmp(&a.evh, &b.evh, sizeof(a.evh)), 0) << "evh";
	EXPECT_EQ(std::memcmp(&a.evv, &b.evv, sizeof(a.evv)), 0) << "evv";
	EXPECT_EQ(std::memcmp(&a.vxy_max, &b.vxy_max, sizeof(a.vxy_max)), 0) << "vxy_max";
	EXPECT_EQ(std::memcmp(&a.vz_max, &b.vz_max, sizeof(a.vz_max)), 0) << "vz_max";
	EXPECT_EQ(std::memcmp(&a.hagl_min, &b.hagl_min, sizeof(a.hagl_min)), 0) << "hagl_min";
	EXPECT_EQ(std::memcmp(&a.hagl_max, &b.hagl_max, sizeof(a.hagl_max)), 0) << "hagl_max";
}
void drainLog(uORB::Subscription &sub)
{
	vehicle_local_position_log_s ignored{};
	while (sub.update(&ignored)) {}
}
}

TEST_F(EKF2SelectorPublication, QueuedPositionLogPreservesPayloadAndRejectedSampleSemantics)
{
	apps_map_type apps; init_app_map(apps);
	EKF2Selector selector;
	uORB::PublicationMulti<vehicle_local_position_s> input{ORB_ID(estimator_local_position)};
	uORB::Subscription output{ORB_ID(vehicle_local_position)}, log{ORB_ID(vehicle_local_position_log)};
	drainLog(log);
	ASSERT_TRUE(input.advertise()); Access::select(selector,input.get_instance());
	vehicle_local_position_s in{}, original{}; vehicle_local_position_log_s recorded{};
	in.timestamp=1; in.timestamp_sample=10000; in.x=-0.f; in.y=2.5f; in.z=-2.5f;
	in.vx=.2f; in.vz=-.3f; in.heading=.1f; in.ref_lat=47.3977508; in.ref_lon=8.5456073;
	in.xy_reset_counter=255; in.delta_xy[0]=.125f; in.vxy_max=NAN; in.hagl_max=INFINITY;
	ASSERT_TRUE(input.publish(in)); Access::local(selector);
	ASSERT_TRUE(output.update(&original)); ASSERT_TRUE(log.update(&recorded));
	logEqual(original,recorded); EXPECT_EQ(recorded.log_seq,1u);
	in.timestamp_sample=8000; ASSERT_TRUE(input.publish(in)); Access::local(selector);
	EXPECT_FALSE(log.update(&recorded)); EXPECT_FALSE(output.update(&original));
	in.timestamp_sample=12000; in.xy_reset_counter=0; in.x=3.f;
	ASSERT_TRUE(input.publish(in)); Access::local(selector);
	ASSERT_TRUE(output.update(&original)); ASSERT_TRUE(log.update(&recorded));
	logEqual(original,recorded); EXPECT_EQ(recorded.log_seq,2u); EXPECT_EQ(original.xy_reset_counter,0);
}

TEST_F(EKF2SelectorPublication, PositionLogBurstDoesNotChangeLatestValueControlQueue)
{
	static_assert(uORB::DefaultQueueSize<vehicle_local_position_s>::value==1,"Control queue must remain latest value");
	static_assert(vehicle_local_position_log_s::ORB_QUEUE_LENGTH==32,"Bounded evidence queue");
	LocalPositionLog recording;
	uORB::Publication<vehicle_local_position_s> control_pub{ORB_ID(vehicle_local_position)};
	uORB::Subscription control{ORB_ID(vehicle_local_position)}, log{ORB_ID(vehicle_local_position_log)};
	drainLog(log); vehicle_local_position_s in{}, current{}; vehicle_local_position_log_s saved{};
	for(unsigned i=1;i<=32;++i) {
		in.timestamp=in.timestamp_sample=i*10000; in.x=float(i);
		ASSERT_TRUE(control_pub.publish(in)); recording.publish(in);
	}
	ASSERT_TRUE(control.update(&current)); EXPECT_EQ(current.timestamp,320000u);
	EXPECT_FALSE(control.update(&current));
	for(unsigned i=1;i<=32;++i) {
		ASSERT_TRUE(log.update(&saved)); EXPECT_EQ(saved.log_seq,i);
		EXPECT_EQ(saved.timestamp,i*10000u); EXPECT_FLOAT_EQ(saved.x,float(i));
	}
	EXPECT_FALSE(log.update(&saved));
}

TEST_F(EKF2SelectorPublication, PositionLogOverflowRemainsDetectable)
{
	LocalPositionLog recording; uORB::Subscription log{ORB_ID(vehicle_local_position_log)};
	drainLog(log); vehicle_local_position_s in{}; vehicle_local_position_log_s saved{};
	in.timestamp=in.timestamp_sample=10000; recording.publish(in);
	ASSERT_TRUE(log.update(&saved)); EXPECT_EQ(saved.log_seq,1u);
	for(unsigned i=2;i<=34;++i) { in.timestamp=in.timestamp_sample=i*10000; recording.publish(in); }
	ASSERT_TRUE(log.update(&saved)); EXPECT_EQ(saved.log_seq,3u); // Missing seq2 cannot be called lossless.
	for(unsigned i=4;i<=34;++i) { ASSERT_TRUE(log.update(&saved)); EXPECT_EQ(saved.log_seq,i); }
	EXPECT_FALSE(log.update(&saved));
}

TEST_F(EKF2SelectorPublication, PositionLogKeepsPublicationAndSampleClocksUnmodified)
{
	LocalPositionLog recording; uORB::Subscription log{ORB_ID(vehicle_local_position_log)};
	drainLog(log); vehicle_local_position_s in{}; vehicle_local_position_log_s saved{};
	in.timestamp=20000;
	for(uint64_t t : {10000u, 12000u}) {
		in.timestamp_sample=t; recording.publish(in);
		ASSERT_TRUE(log.update(&saved)); EXPECT_EQ(saved.timestamp,20000u); EXPECT_EQ(saved.timestamp_sample,t);
	}
}

TEST_F(EKF2SelectorPublication, PositionLogCopiesEveryFieldWithoutConversion)
{
	LocalPositionLog recording; uORB::Subscription log{ORB_ID(vehicle_local_position_log)};
	drainLog(log); vehicle_local_position_s in{}; vehicle_local_position_log_s saved{};
	in.timestamp = 1;
	in.timestamp_sample = 2;
	in.xy_valid = true;
	in.z_valid = true;
	in.v_xy_valid = true;
	in.v_z_valid = true;
	in.x = 7.25f;
	in.y = 8.25f;
	in.z = 9.25f;
	in.delta_xy[0] = 10.25f;
	in.delta_xy[1] = 11.25f;
	in.xy_reset_counter = 11;
	in.delta_z = 12.25f;
	in.z_reset_counter = 13;
	in.vx = 14.25f;
	in.vy = 15.25f;
	in.vz = 16.25f;
	in.z_deriv = 17.25f;
	in.delta_vxy[0] = 18.25f;
	in.delta_vxy[1] = 19.25f;
	in.vxy_reset_counter = 19;
	in.delta_vz = 20.25f;
	in.vz_reset_counter = 21;
	in.ax = 22.25f;
	in.ay = 23.25f;
	in.az = 24.25f;
	in.heading = 25.25f;
	in.delta_heading = 26.25f;
	in.heading_reset_counter = 27;
	in.xy_global = true;
	in.z_global = true;
	in.ref_timestamp = 30;
	in.ref_lat = 31.123456789;
	in.ref_lon = 32.123456789;
	in.ref_alt = 33.25f;
	in.dist_bottom = 34.25f;
	in.dist_bottom_valid = true;
	in.dist_bottom_sensor_bitfield = 36;
	in.eph = 37.25f;
	in.epv = 38.25f;
	in.evh = 39.25f;
	in.evv = 40.25f;
	in.vxy_max = 41.25f;
	in.vz_max = 42.25f;
	in.hagl_min = 43.25f;
	in.hagl_max = 44.25f;
	recording.publish(in); ASSERT_TRUE(log.update(&saved)); logEqual(in,saved);
}
#endif
