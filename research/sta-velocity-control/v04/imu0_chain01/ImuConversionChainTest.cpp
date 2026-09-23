// SPDX-License-Identifier: BSD-3-Clause
// Offline diagnosis only. Compile with -fno-access-control for test access,
// not production header edits. Never calls Simulator::start/run or VehicleIMU::Start.
#include <gtest/gtest.h>
#define MODULE_NAME "imu_chain_test"
#include <simulator/simulator.h>
#include <sensors/vehicle_imu/VehicleIMU.hpp>
#include <platforms/posix/apps.h>
#include <px4_platform_common/px4_work_queue/WorkQueueManager.hpp>
#include <cstdlib>
#include <cmath>

// Only asynchronous scheduling is disabled; conversion, driver, uORB and IMU
// Run/integration/publication are the actual production implementations.
extern "C" void __wrap_hrt_call_after(hrt_call *, hrt_abstime, hrt_callout, void *) {}
extern "C" void __wrap_hrt_cancel(hrt_call *) {}
Simulator *Simulator::_instance = nullptr; // no simulator.cpp/network startup linked

class ChainAnchor : public px4::WorkItem
{
public:
	ChainAnchor() : WorkItem("imu_chain_anchor", px4::wq_configurations::nav_and_controllers) {}
	void Run() override {}
};
static ChainAnchor *anchor = nullptr;

class ImuConversionChain : public ::testing::Test
{
public:
	static void SetUpTestSuite()
	{
		ASSERT_EQ(px4::WorkQueueManagerStart(), 0);
		px4_usleep(20000);
		anchor = new ChainAnchor();
	}
	static void TearDownTestSuite()
	{
		delete anchor; anchor = nullptr;
		px4_usleep(20000);
		EXPECT_EQ(px4::WorkQueueManagerStop(), 0);
	}
protected:
	Simulator *sim{nullptr};
	sensors::VehicleIMU *imus[3]{};
	uORB::Subscription accel[3]{{ORB_ID(sensor_accel),0},{ORB_ID(sensor_accel),1},{ORB_ID(sensor_accel),2}};
	uORB::Subscription imu[3]{{ORB_ID(vehicle_imu),0},{ORB_ID(vehicle_imu),1},{ORB_ID(vehicle_imu),2}};
	uORB::Subscription fifo{ORB_ID(sensor_accel_fifo)};
	sensor_accel_s raw[3]{};
	vehicle_imu_s integrated[3]{};
	sensor_accel_fifo_s integer{};
	uint64_t sample{1000000};
	static constexpr float scale = CONSTANTS_ONE_G / 2048.f;
	void SetUp() override
	{
		apps_map_type apps; init_app_map(apps); ASSERT_TRUE(apps.empty());
		param_control_autosave(false); param_reset_all();
		int32_t hz = 250;
		ASSERT_EQ(param_set_no_notification(param_find("IMU_INTEG_RATE"), &hz), 0);
		sim = new Simulator();
		for (int j=0; j<3; ++j) {
			ASSERT_EQ(sim->_px4_accel[j].get_instance(), j);
			imus[j] = new sensors::VehicleIMU(j,j,j,px4::wq_configurations::nav_and_controllers);
			imu[j].ChangeInstance(imus[j]->_vehicle_imu_pub.get_instance());
			// uORB retains queued samples across fixture destruction. A fresh
			// offline case must not consume the preceding case's sensor clock.
			sensor_accel_s old_accel{}; sensor_gyro_s old_gyro{};
			while (imus[j]->_sensor_accel_sub.update(&old_accel)) {}
			while (imus[j]->_sensor_gyro_sub.update(&old_gyro)) {}
			while (accel[j].update(&raw[j])) {}
			while (imu[j].update(&integrated[j])) {}
		}
		while (fifo.update(&integer)) {}
		for (int k=0; k<150; ++k) { step(0.f,0.f,-CONSTANTS_ONE_G,false); }
		for (int j=0; j<3; ++j) {
			ASSERT_TRUE(imus[j]->_intervals_configured);
			ASSERT_EQ(integrated[j].delta_velocity_dt, 4000);
		}
	}
	void TearDown() override
	{
		for (auto *v : imus) { delete v; }
		delete sim; param_reset_all();
	}
	void step(float x,float y,float z,bool require_integral=true)
	{
		sample += 4000;
		mavlink_hil_sensor_t packet{};
		packet.fields_updated = 0x3f; // accel + gyro only
		packet.xacc=x; packet.yacc=y; packet.zacc=z;
		// Actual production conversion; no copied narrowing expression in this test.
		sim->update_sensors(sample, packet);
		ASSERT_TRUE(fifo.update(&integer));
		for (int j=0; j<3; ++j) {
			ASSERT_TRUE(accel[j].update(&raw[j]));
			EXPECT_EQ(raw[j].timestamp_sample,sample);
			imus[j]->Run(); imus[j]->ScheduleClear();
			bool available=imu[j].update(&integrated[j]);
			if (require_integral) {
				ASSERT_TRUE(available);
				EXPECT_EQ(integrated[j].timestamp_sample,sample);
				EXPECT_EQ(integrated[j].delta_velocity_dt,4000);
			}
		}
	}
	static float component(const sensor_accel_s &v,int axis) { return axis==0 ? v.x : axis==1 ? v.y : v.z; }
	void axis_step(int axis,float value)
	{
		float a[3]{0.f,0.f,0.f}; a[axis]=value; step(a[0],a[1],a[2]);
	}
	void emit(const char *tag,int axis,float input) const
	{
		std::printf("IMU_CHAIN_ROW {\"tag\":\"%s\",\"axis\":%d,\"input\":%.9g,\"sample\":%llu,\"fifo\":%d,\"a0\":%.9g,\"a1\":%.9g,\"a2\":%.9g,\"clip0\":%u,\"clip1\":%u,\"dv0\":%.9g,\"dv1\":%.9g,\"dv2\":%.9g,\"dv_clip0\":%u,\"dv_clip1\":%u}\n",
			tag,axis,double(input),(unsigned long long)sample,
			int(axis==0?integer.x[0]:axis==1?integer.y[0]:integer.z[0]),
			double(component(raw[0],axis)),double(component(raw[1],axis)),double(component(raw[2],axis)),
			unsigned(raw[0].clip_counter[axis]),unsigned(raw[1].clip_counter[axis]),
			double(integrated[0].delta_velocity[axis]),double(integrated[1].delta_velocity[axis]),
			double(integrated[2].delta_velocity[axis]),unsigned(integrated[0].delta_velocity_clipping),
			unsigned(integrated[1].delta_velocity_clipping));
	}
};

TEST_F(ImuConversionChain, InRangeThreeAxesAndDeviceIsolation)
{
	for(int axis=0;axis<3;++axis) {
		for(float value : {-150.f,-100.f,-9.80665f,-1.f,0.f,1.f,100.f,150.f}) {
			for(int k=0;k<3;++k) { axis_step(axis,value); }
			EXPECT_NEAR(component(raw[0],axis),value,scale*1.01f);
			EXPECT_FLOAT_EQ(component(raw[1],axis),value);
			EXPECT_FLOAT_EQ(component(raw[2],axis),value);
			for(int j=0;j<3;++j) {
				EXPECT_NEAR(integrated[j].delta_velocity[axis],value*.004f,scale*.0041f);
				EXPECT_EQ(integrated[j].delta_velocity_clipping,0);
				for(int other=0;other<3;++other) {
					if(other!=axis) { EXPECT_FLOAT_EQ(integrated[j].delta_velocity[other],0.f); }
				}
			}
			emit("in_range",axis,value);
		}
	}
}

TEST_F(ImuConversionChain, SafeIntegerEdgesAndActualClipThreshold)
{
	for(float count : {-32768.f,-32767.f,-32735.f,-32734.f,32734.f,32735.f,32766.f,32767.f}) {
		const float value=count*scale;
		for(int k=0;k<3;++k) { axis_step(2,value); }
		EXPECT_NEAR(component(raw[0],2),value,scale*1.01f);
		// Assert against the published integer, not a floating-point boundary guess.
		const bool clipped=std::abs(int(integer.z[0]))>=32735;
		EXPECT_EQ(raw[0].clip_counter[2]>0,clipped);
		EXPECT_EQ((integrated[0].delta_velocity_clipping & vehicle_imu_s::CLIPPING_Z)>0,clipped);
		emit("integer_edge",2,value);
	}
}

TEST_F(ImuConversionChain, FifoDriverHalfSampleAndIntegratorPulseArea)
{
	for(int k=0;k<4;++k) { axis_step(2,0.f); }
	double area[3]{};
	for(int k=0;k<5;++k) {
		axis_step(2,k==0?-100.f:0.f);
		if(k<2) { EXPECT_NEAR(raw[0].z,-50.f,scale); }
		else { EXPECT_FLOAT_EQ(raw[0].z,0.f); }
		for(int j=0;j<3;++j) { area[j]+=double(integrated[j].delta_velocity[2]); }
		emit("bounded_pulse",2,k==0?-100.f:0.f);
	}
	for(int j=0;j<3;++j) { EXPECT_NEAR(area[j],-.4,double(scale)*.0041); }
}

TEST_F(ImuConversionChain, NonAccelFieldMaskDoesNotPublishAcceleration)
{
	mavlink_hil_sensor_t packet{}; packet.fields_updated=0;
	packet.xacc=packet.yacc=packet.zacc=NAN;
	sim->update_sensors(sample,packet);
	for(auto &s : accel) { EXPECT_FALSE(s.updated()); }
	EXPECT_FALSE(fifo.updated());
}

// These assert observed DEFECT REPRODUCTION, not safe production behavior.
// Execute separately from the range-valid suite and under UBSan (expected failure).
TEST_F(ImuConversionChain, OverflowPulsePropagatesSignFlipWithoutImu0Clip)
{
	for(int axis=0;axis<3;++axis) {
		for(float impulse : {-250.f,250.f}) {
			for(int k=0;k<4;++k) { axis_step(axis,0.f); }
			double area[3]{};
			for(int k=0;k<5;++k) {
				axis_step(axis,k==0?impulse:0.f);
				if(k==0) {
					EXPECT_LT(component(raw[0],axis)*impulse,0.f);
					EXPECT_EQ(raw[0].clip_counter[axis],0);
					EXPECT_EQ(raw[1].clip_counter[axis],1);
				}
				EXPECT_EQ(integrated[0].delta_velocity_clipping,0);
				for(int j=0;j<3;++j) { area[j]+=double(integrated[j].delta_velocity[axis]); }
				emit("overflow_pulse",axis,k==0?impulse:0.f);
			}
			EXPECT_LT(area[0]*double(impulse),0.);
			EXPECT_NEAR(area[1],double(impulse)*.004,1e-6);
			EXPECT_NEAR(area[2],area[1],1e-6);
			std::printf("IMU_CHAIN_AREA {\"axis\":%d,\"input\":%.9g,\"dv0\":%.12g,\"dv1\":%.12g,\"difference\":%.12g}\n",
				axis,double(impulse),area[0],area[1],area[0]-area[1]);
		}
	}
}

TEST_F(ImuConversionChain, InvalidConversionProbe)
{
	const char *value=std::getenv("IMU_AUDIT_INPUT");
	ASSERT_NE(value,nullptr);
	axis_step(2,std::strtof(value,nullptr));
	// UBSan must stop in the unmodified Simulator conversion before reaching this.
	FAIL() << "Out-of-range conversion was not diagnosed";
}
