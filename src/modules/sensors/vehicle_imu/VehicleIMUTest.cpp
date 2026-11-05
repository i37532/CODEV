// SPDX-License-Identifier: BSD-3-Clause
// Real VehicleIMU::Run, real queued uORB publications and the actual work queue.
// The fixture deliberately pauses a queue to create a controlled backlog. It
// does NOT claim that the old flight ULog recorded this consumption schedule.
#define MODULE_NAME "vehicle_imu_test"
#include <gtest/gtest.h>
#include "VehicleIMU.hpp"
#include <platforms/posix/apps.h>
#include <hrt_work.h>
#include <px4_platform_common/px4_work_queue/WorkQueueManager.hpp>
#include <uORB/PublicationMulti.hpp>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <memory>
#include <mutex>
#include <vector>

namespace sensors
{
class VehicleIMUTestAccess
{
public:
	static void configure(VehicleIMU &imu, uint64_t sample)
	{
		imu.ParametersUpdate(true);
		imu._accel_calibration.set_device_id(1310988);
		imu._gyro_calibration.set_device_id(1310988);
		sensor_accel_s accel{}; sensor_gyro_s gyro{};
		while (imu._sensor_accel_sub.update(&accel)) {}
		while (imu._sensor_gyro_sub.update(&gyro)) {}
		imu._accel_last_generation = imu._sensor_accel_sub.get_last_generation();
		imu._gyro_last_generation = imu._sensor_gyro_sub.get_last_generation();
		imu._accel_timestamp_sample_last = sample;
		imu._gyro_timestamp_sample_last = sample;
		imu._gyro_timestamp_last = sample;
		imu._accel_interval_us = 4000;
		imu._gyro_interval_us = 4000;
		imu._intervals_configured = true;
		imu._update_integrator_config = false;
		imu._sensor_gyro_sub.set_required_updates(1);
		imu._accel_integrator.set_reset_samples(1);
		imu._gyro_integrator.set_reset_samples(1);
		imu._accel_integrator.set_reset_interval(2000);
		imu._gyro_integrator.set_reset_interval(2000);
		// Seed a constant previous sample so independent trapezoid expectations
		// are exact apart from ordinary binary32 roundoff.
		imu._accel_integrator.put(matrix::Vector3f(0.f, 0.f, -9.f), .004f);
		imu._gyro_integrator.put(matrix::Vector3f(.25f, 0.f, 0.f), .004f);
		imu._accel_integrator.reset(); imu._gyro_integrator.reset();
		imu._gyro_update_latency_mean.reset();
		for (int i = 0; i < 1000; ++i) { imu._gyro_update_latency_mean.update(matrix::Vector2f(0.f, 0.f)); }
		// Isolate a callback loss from the backup timer. Test-only; no parameter
		// or production timing threshold changes. No further input is published.
		imu._backup_schedule_timeout_us = 1000000;
	}
	static unsigned pending(VehicleIMU &imu)
	{
		class Probe : public uORB::Subscription {
		public:
			using uORB::Subscription::Subscription;
			using uORB::Subscription::get_node;
		};
		Probe node{ORB_ID(sensor_gyro), imu._sensor_gyro_sub.get_instance()};
		if (!node.advertised()) { return 0; }
		return node.get_node()->updates_available(imu._sensor_gyro_sub.get_last_generation());
	}
	static uint8_t outputInstance(VehicleIMU &imu) { return imu._vehicle_imu_pub.get_instance(); }
	static uint64_t sample(VehicleIMU &imu) { return imu._gyro_timestamp_sample_last; }
	static uint32_t runs(VehicleIMU &imu) { return imu._run_count; }
	static uint64_t gyroGaps(VehicleIMU &imu) { return perf_event_count(imu._gyro_generation_gap_perf); }
	static uint64_t accelGaps(VehicleIMU &imu) { return perf_event_count(imu._accel_generation_gap_perf); }
};
}

namespace
{
using Access = sensors::VehicleIMUTestAccess;
using Steady = std::chrono::steady_clock;

class QueueAnchor : public px4::WorkItem
{
public:
	QueueAnchor() : WorkItem("imu_test_anchor", px4::wq_configurations::nav_and_controllers) {}
	void Run() override {}
};

// A bounded, explicitly released worker pause; no production lock is changed.
class QueuePause : public px4::WorkItem
{
public:
	QueuePause() : WorkItem("imu_test_pause", px4::wq_configurations::nav_and_controllers) {}
	~QueuePause() override { release(); ScheduleClear(); }
	bool start()
	{
		ScheduleNow();
		std::unique_lock<std::mutex> lock(_mutex);
		return _cv.wait_for(lock, std::chrono::seconds(1), [this] { return _entered; });
	}
	void release()
	{
		std::unique_lock<std::mutex> lock(_mutex);
		_release = true; _cv.notify_all();
		if (_entered) { _cv.wait_for(lock, std::chrono::seconds(1), [this] { return _finished; }); }
	}
	void Run() override
	{
		std::unique_lock<std::mutex> lock(_mutex); _entered = true; _cv.notify_all();
		_cv.wait_for(lock, std::chrono::seconds(2), [this] { return _release; });
		_finished = true; _cv.notify_all();
	}
private:
	std::mutex _mutex; std::condition_variable _cv;
	bool _entered{false}, _release{false}, _finished{false};
};

class Consumer : public px4::WorkItem
{
public:
	explicit Consumer(uint8_t instance) : WorkItem("imu_test_consumer", px4::wq_configurations::nav_and_controllers),
		_sub(this, ORB_ID(vehicle_imu), instance)
	{
		vehicle_imu_s old{}; while (_sub.update(&old)) {}
		_sub.registerCallback();
	}
	~Consumer() override { stop(); }
	void stop() { _sub.unregisterCallback(); ScheduleClear(); }
	void Run() override
	{
		vehicle_imu_s value{};
		while (_sub.update(&value)) {
			std::lock_guard<std::mutex> lock(_mutex); _values.push_back(value);
		}
		_cv.notify_all();
	}
	bool wait(size_t n, int milliseconds = 150)
	{
		std::unique_lock<std::mutex> lock(_mutex);
		return _cv.wait_for(lock, std::chrono::milliseconds(milliseconds), [this, n] { return _values.size() >= n; });
	}
	std::vector<vehicle_imu_s> values()
	{
		std::lock_guard<std::mutex> lock(_mutex); return _values;
	}
private:
	uORB::SubscriptionCallbackWorkItem _sub;
	std::mutex _mutex; std::condition_variable _cv;
	std::vector<vehicle_imu_s> _values;
};

class Harness
{
public:
	explicit Harness(bool own_pause = true)
	{
		if (own_pause) { EXPECT_TRUE(pause.start()); }
		EXPECT_TRUE(accel.advertise()); EXPECT_TRUE(gyro.advertise());
		imu.reset(new sensors::VehicleIMU(0, accel.get_instance(), gyro.get_instance(), px4::wq_configurations::nav_and_controllers));
		EXPECT_TRUE(imu->Start());
		base = hrt_absolute_time() - 60000;
		Access::configure(*imu, base);
		consumer.reset(new Consumer(Access::outputInstance(*imu)));
	}
	~Harness()
	{
		pause.release(); QueuePause cleanup; EXPECT_TRUE(cleanup.start());
		consumer->stop(); imu->Stop(); consumer.reset(); imu.reset(); cleanup.release();
	}
	void publish(unsigned index, float gx = .25f, float az = -9.f)
	{
		publishAccel(index, az); publishGyro(index, gx);
	}
	void publishAccel(unsigned index, float z = -9.f)
	{
		sensor_accel_s a{}; a.timestamp = hrt_absolute_time();
		a.timestamp_sample = base + index * 4000; a.device_id = 1310988;
		a.samples = 1; a.z = z; EXPECT_TRUE(accel.publish(a));
	}
	void publishGyro(unsigned index, float x = .25f)
	{
		sensor_gyro_s g{}; g.timestamp = hrt_absolute_time();
		g.timestamp_sample = base + index * 4000; g.device_id = 1310988;
		g.samples = 1; g.x = x; EXPECT_TRUE(gyro.publish(g));
	}
	void release() { pause.release(); }
	QueuePause pause;
	uORB::PublicationMulti<sensor_accel_s> accel{ORB_ID(sensor_accel)};
	uORB::PublicationMulti<sensor_gyro_s> gyro{ORB_ID(sensor_gyro)};
	std::unique_ptr<sensors::VehicleIMU> imu;
	std::unique_ptr<Consumer> consumer;
	uint64_t base{0};
};
}

class VehicleIMURealQueue : public ::testing::Test
{
public:
	static void SetUpTestSuite()
	{
		hrt_init(); hrt_work_queue_init(); // Real Run schedules HRT; publication-only fixtures do not.
		ASSERT_EQ(px4::WorkQueueManagerStart(), 0); px4_usleep(80000);
		_anchor = new QueueAnchor();
	}
	static void TearDownTestSuite()
	{
		delete _anchor; _anchor = nullptr; px4_usleep(20000); EXPECT_EQ(px4::WorkQueueManagerStop(), 0);
	}
private:
	static QueueAnchor *_anchor;
};
QueueAnchor *VehicleIMURealQueue::_anchor = nullptr;

TEST_F(VehicleIMURealQueue, SingleRealPublicationRetainsSampleDtAndIntegral)
{
	Harness h; h.publish(1); h.release(); ASSERT_TRUE(h.consumer->wait(1));
	const auto values = h.consumer->values(); ASSERT_EQ(values.size(), 1u);
	EXPECT_EQ(values[0].timestamp_sample, h.base + 4000);
	EXPECT_EQ(values[0].delta_angle_dt, 4000); EXPECT_EQ(values[0].delta_velocity_dt, 4000);
	EXPECT_NEAR(values[0].delta_angle[0], .001, 1e-8);
	EXPECT_NEAR(values[0].delta_velocity[2], -.036, 1e-7);
}

TEST_F(VehicleIMURealQueue, SevenQueuedSamplesNeedNoNewSensorCallbackToDrain)
{
	Harness h;
	for (unsigned i = 1; i <= 7; ++i) { h.publish(i); }
	EXPECT_EQ(Access::pending(*h.imu), 7u);
	h.release();
	const bool drained = h.consumer->wait(7);
	QueuePause observed; ASSERT_TRUE(observed.start());
	const auto values = h.consumer->values();
	std::printf("REAL_UORB_BACKLOG: delivered=%zu pending=%u last_sample=%llu base=%llu\n",
		values.size(), Access::pending(*h.imu), static_cast<unsigned long long>(Access::sample(*h.imu)),
		static_cast<unsigned long long>(h.base));
	EXPECT_TRUE(drained) << "All seven real input generations must drain before backup, without a new publisher callback";
	EXPECT_EQ(values.size(), 7u); EXPECT_EQ(Access::pending(*h.imu), 0u);
	for (size_t i = 0; i < values.size(); ++i) {
		EXPECT_EQ(values[i].timestamp_sample, h.base + (i + 1) * 4000);
		EXPECT_EQ(values[i].delta_angle_dt, 4000); EXPECT_EQ(values[i].delta_velocity_dt, 4000);
		EXPECT_NEAR(values[i].delta_angle[0], .001, 1e-8);
		EXPECT_NEAR(values[i].delta_velocity[2], -.036, 1e-7);
	}
	observed.release();
}

TEST_F(VehicleIMURealQueue, SequentialNoBacklogRetainsTrapezoidsAndDoesNotReschedule)
{
	Harness h;
	for (unsigned i = 1; i <= 6; ++i) {
		h.publish(i, .25f + .125f * i, -9.f + .25f * i);
		if (i == 1) { h.release(); }
		ASSERT_TRUE(h.consumer->wait(i));
	}
	px4_usleep(30000); QueuePause observed; ASSERT_TRUE(observed.start());
	const auto values = h.consumer->values(); ASSERT_EQ(values.size(), 6u);
	EXPECT_EQ(Access::runs(*h.imu), 6u); EXPECT_EQ(Access::pending(*h.imu), 0u);
	for (unsigned i = 1; i <= 6; ++i) {
		const double prior_g = .25 + .125 * (i - 1), current_g = .25 + .125 * i;
		const double prior_a = -9. + .25 * (i - 1), current_a = -9. + .25 * i;
		EXPECT_EQ(values[i - 1].timestamp_sample, h.base + i * 4000);
		EXPECT_EQ(values[i - 1].delta_angle_dt, 4000);
		EXPECT_EQ(values[i - 1].delta_velocity_dt, 4000);
		EXPECT_NEAR(values[i - 1].delta_angle[0], .002 * (prior_g + current_g), 1e-8);
		EXPECT_NEAR(values[i - 1].delta_velocity[2], .002 * (prior_a + current_a), 1e-7);
	}
	observed.release();
}

TEST_F(VehicleIMURealQueue, QueuedVaryingValuesPreserveEverySampleAndTrapezoid)
{
	Harness h;
	for (unsigned i = 1; i <= 8; ++i) { h.publish(i, .25f + .125f * i, -9.f + .25f * i); }
	h.release(); ASSERT_TRUE(h.consumer->wait(8));
	QueuePause observed; ASSERT_TRUE(observed.start());
	const auto values = h.consumer->values(); ASSERT_EQ(values.size(), 8u);
	EXPECT_EQ(Access::runs(*h.imu), 8u); EXPECT_EQ(Access::pending(*h.imu), 0u);
	EXPECT_EQ(Access::gyroGaps(*h.imu), 0u); EXPECT_EQ(Access::accelGaps(*h.imu), 0u);
	for (unsigned i = 1; i <= 8; ++i) {
		EXPECT_EQ(values[i - 1].timestamp_sample, h.base + i * 4000);
		EXPECT_EQ(values[i - 1].delta_angle_dt, 4000);
		EXPECT_EQ(values[i - 1].delta_velocity_dt, 4000);
		EXPECT_NEAR(values[i - 1].delta_angle[0], .004 * (.25 + .125 * (i - .5)), 1e-8);
		EXPECT_NEAR(values[i - 1].delta_velocity[2], .004 * (-9. + .25 * (i - .5)), 1e-7);
	}
	observed.release();
}

TEST_F(VehicleIMURealQueue, GyroWithoutAccelDoesNotSpinAndResumesOnExplicitWake)
{
	Harness h; for (unsigned i = 1; i <= 3; ++i) { h.publishGyro(i); }
	h.release(); px4_usleep(40000);
	QueuePause observed; ASSERT_TRUE(observed.start());
	EXPECT_EQ(Access::runs(*h.imu), 1u); EXPECT_EQ(Access::pending(*h.imu), 2u);
	EXPECT_EQ(h.consumer->values().size(), 0u);
	for (unsigned i = 1; i <= 3; ++i) { h.publishAccel(i); }
	// Accel is not a registered scheduling source. This explicit wake represents
	// the unchanged backup/external wake; it does not replace the real Run body.
	h.imu->ScheduleNow(); observed.release(); ASSERT_TRUE(h.consumer->wait(3));
	QueuePause final_state; ASSERT_TRUE(final_state.start());
	EXPECT_EQ(Access::runs(*h.imu), 4u); EXPECT_EQ(Access::pending(*h.imu), 0u);
	const auto values = h.consumer->values(); ASSERT_EQ(values.size(), 3u);
	for (unsigned i = 1; i <= 3; ++i) {
		EXPECT_EQ(values[i - 1].timestamp_sample, h.base + i * 4000);
		EXPECT_EQ(values[i - 1].delta_angle_dt, 4000);
		EXPECT_EQ(values[i - 1].delta_velocity_dt, 4000);
	}
	final_state.release();
}

TEST_F(VehicleIMURealQueue, QueueOverflowKeepsOriginalGapCatchupAndIntegratedDuration)
{
	Harness h; for (unsigned i = 1; i <= 11; ++i) { h.publish(i); }
	h.release(); ASSERT_TRUE(h.consumer->wait(1));
	QueuePause observed; ASSERT_TRUE(observed.start());
	const auto values = h.consumer->values(); ASSERT_EQ(values.size(), 1u);
	EXPECT_EQ(Access::pending(*h.imu), 0u);
	EXPECT_EQ(Access::gyroGaps(*h.imu), 1u); EXPECT_EQ(Access::accelGaps(*h.imu), 1u);
	EXPECT_EQ(values[0].timestamp_sample, h.base + 44000);
	EXPECT_EQ(values[0].delta_angle_dt, 44000); EXPECT_EQ(values[0].delta_velocity_dt, 44000);
	EXPECT_NEAR(values[0].delta_angle[0], .011, 1e-7);
	EXPECT_NEAR(values[0].delta_velocity[2], -.396, 1e-6);
	observed.release();
}

TEST_F(VehicleIMURealQueue, TwoRealInstancesKeepQueuesAndIntegralsIndependent)
{
	QueuePause initial; ASSERT_TRUE(initial.start()); Harness first(false), second(false);
	ASSERT_NE(first.gyro.get_instance(), second.gyro.get_instance());
	ASSERT_NE(Access::outputInstance(*first.imu), Access::outputInstance(*second.imu));
	for (unsigned i = 1; i <= 7; ++i) { first.publish(i); }
	second.publish(1, -.5f, -8.f); initial.release();
	ASSERT_TRUE(first.consumer->wait(7)); ASSERT_TRUE(second.consumer->wait(1));
	QueuePause observed; ASSERT_TRUE(observed.start());
	const auto a = first.consumer->values(), b = second.consumer->values();
	ASSERT_EQ(a.size(), 7u); ASSERT_EQ(b.size(), 1u);
	EXPECT_EQ(Access::runs(*first.imu), 7u); EXPECT_EQ(Access::runs(*second.imu), 1u);
	EXPECT_EQ(Access::pending(*first.imu), 0u); EXPECT_EQ(Access::pending(*second.imu), 0u);
	EXPECT_EQ(b[0].timestamp_sample, second.base + 4000);
	EXPECT_NEAR(b[0].delta_angle[0], -.0005, 1e-8); // prior .25, current -.5
	EXPECT_NEAR(b[0].delta_velocity[2], -.034, 1e-7);
	for (unsigned i = 1; i <= 7; ++i) {
		EXPECT_EQ(a[i - 1].timestamp_sample, first.base + i * 4000);
		EXPECT_NEAR(a[i - 1].delta_angle[0], .001, 1e-8);
	}
	observed.release();
}
