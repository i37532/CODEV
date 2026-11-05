// SPDX-License-Identifier: BSD-3-Clause
// Reuse the fixed audit fixture and its four valid-range tests unchanged.
// The historical defect/probe tests remain registered, but the repair runner
// explicitly excludes them; it does not alter historical expectations.
#include "../imu0_chain01/ImuConversionChainTest.cpp"
#include <cfloat>

TEST_F(ImuConversionChain, RepairSaturatedPulseKeepsSignAndClippingXYZ)
{
	for (int axis=0; axis<3; ++axis) {
		for (float input : {-250.f,250.f}) {
			for (int k=0;k<4;++k) { axis_step(axis,0.f); }
			double area[3]{};
			for (int k=0;k<5;++k) {
				axis_step(axis,k==0?input:0.f);
				if (k==0) {
					EXPECT_GT(component(raw[0],axis)*input,0.f);
					for (int j=0;j<3;++j) {
						EXPECT_EQ(raw[j].clip_counter[axis],1);
						EXPECT_NE(integrated[j].delta_velocity_clipping & (1u<<axis),0);
					}
				}
				for (int j=0;j<3;++j) { area[j]+=double(integrated[j].delta_velocity[axis]); }
				emit("repaired_pulse",axis,k==0?input:0.f);
			}
			const double clipped=double(input<0.f?INT16_MIN:INT16_MAX)*double(scale);
			EXPECT_NEAR(area[0],clipped*.004,1e-6);
			EXPECT_NEAR(area[1],double(input)*.004,1e-6);
			EXPECT_NEAR(area[2],area[1],1e-6);
			EXPECT_EQ(integrated[0].delta_velocity_clipping,0);
			std::printf("REPAIR_AREA {\"axis\":%d,\"input\":%.9g,\"dv0\":%.12g,\"dv1\":%.12g}\n",
				axis,double(input),area[0],area[1]);
		}
	}
}

TEST_F(ImuConversionChain, RepairEdgesAndHugeFiniteBeforeScaling)
{
	for (int axis=0;axis<3;++axis) {
		for (float value : {-FLT_MAX,-1e20f,-250.f,-157.f,-16.f*CONSTANTS_ONE_G,
				    16.f*CONSTANTS_ONE_G,157.f,250.f,1e20f,FLT_MAX}) {
			// Only conversion/driver checked for extreme float-path amplitudes.
			// Do not claim IMU1/2 integration of FLT_MAX is a physical/safe model.
			mavlink_hil_sensor_t packet{}; packet.fields_updated=7;
			float a[3]{};a[axis]=value;
			packet.xacc=a[0];packet.yacc=a[1];packet.zacc=a[2];
			sample+=4000;sim->update_sensors(sample,packet);
			ASSERT_TRUE(fifo.update(&integer));
			const int16_t count=axis==0?integer.x[0]:axis==1?integer.y[0]:integer.z[0];
			EXPECT_EQ(count,value<0.f?INT16_MIN:INT16_MAX);
			for(int j=0;j<3;++j) {
				ASSERT_TRUE(accel[j].update(&raw[j]));
				EXPECT_TRUE(std::isfinite(component(raw[j],axis)));
				EXPECT_EQ(raw[j].clip_counter[axis],1);
			}
		}
		for(float edge : {INT16_MIN*scale,INT16_MAX*scale,16.f*CONSTANTS_ONE_G}) {
			for(float value : {std::nextafter(edge,-INFINITY),edge,std::nextafter(edge,INFINITY)}) {
				mavlink_hil_sensor_t packet{};packet.fields_updated=7;
				packet.xacc=value;sample+=4000;sim->update_sensors(sample,packet);
				ASSERT_TRUE(fifo.update(&integer));
				EXPECT_GT(float(integer.x[0])*value,0.f);
				EXPECT_NEAR(float(integer.x[0])*scale,value,scale*1.02f);
				for(int j=0;j<3;++j) { ASSERT_TRUE(accel[j].update(&raw[j])); }
				EXPECT_EQ(raw[0].clip_counter[0],1);
			}
		}
	}
}

TEST_F(ImuConversionChain, RepairInvalidVectorAtomicRejectionAndRecovery)
{
	for(int k=0;k<4;++k) { step(0.f,0.f,0.f); }
	uint32_t errors=0;
	for(int axis=0;axis<3;++axis) {
		for(float bad : {NAN,INFINITY,-INFINITY}) {
			const auto before=sim->_last_accel_fifo;
			mavlink_hil_sensor_t packet{};packet.fields_updated=0x3f;
			float a[3]{};a[axis]=bad;
			packet.xacc=a[0];packet.yacc=a[1];packet.zacc=a[2];
			sample+=4000;sim->update_sensors(sample,packet);++errors;
			EXPECT_FALSE(fifo.updated());
			EXPECT_EQ(sim->_last_accel_fifo.timestamp_sample,before.timestamp_sample);
			EXPECT_EQ(sim->_last_accel_fifo.z[0],before.z[0]);
			for(int j=0;j<3;++j) {
				EXPECT_FALSE(accel[j].updated());
				EXPECT_EQ(sim->_px4_accel[j]._error_count,errors);
				imus[j]->Run();imus[j]->ScheduleClear();
				EXPECT_FALSE(imu[j].updated());
			}
			// Recovery has a real 8 ms accelerometer gap, never a fabricated 4 ms.
			packet.xacc=packet.yacc=packet.zacc=0.f;
			sample+=4000;sim->update_sensors(sample,packet);
			ASSERT_TRUE(fifo.update(&integer));EXPECT_FLOAT_EQ(integer.dt,8000.f);
			for(int j=0;j<3;++j) {
				ASSERT_TRUE(accel[j].update(&raw[j]));
				EXPECT_EQ(raw[j].error_count,errors);
				EXPECT_EQ(raw[j].timestamp_sample,sample);
				imus[j]->Run();imus[j]->ScheduleClear();
				ASSERT_TRUE(imu[j].update(&integrated[j]));
				EXPECT_EQ(integrated[j].delta_velocity_dt,8000);
				EXPECT_FLOAT_EQ(integrated[j].delta_velocity[axis],0.f);
				// Existing asynchronous gyro/accel alignment is not changed here.
				EXPECT_LE(integrated[j].timestamp_sample,sample);
			}
			// Consume pending gyro and restore the fixture's nominal timing.
			for(int k=0;k<4;++k) {
				sample+=4000;sim->update_sensors(sample,packet);
				ASSERT_TRUE(fifo.update(&integer));
				for(int j=0;j<3;++j) {
					ASSERT_TRUE(accel[j].update(&raw[j]));
					imus[j]->Run();imus[j]->ScheduleClear();
					while(imu[j].update(&integrated[j])) {}
				}
			}
		}
	}
}

TEST_F(ImuConversionChain, RepairMissingFieldsAndLongInvalidStreak)
{
	for(int k=0;k<4;++k) { step(0.f,0.f,0.f); }
	mavlink_hil_sensor_t packet{};packet.xacc=NAN;
	for(uint32_t mask : {0u,1u,2u,3u,4u,5u,6u}) {
		packet.fields_updated=mask;sim->update_sensors(sample,packet);
		for(int j=0;j<3;++j) {
			EXPECT_FALSE(accel[j].updated());EXPECT_EQ(sim->_px4_accel[j]._error_count,0);
		}
	}
	packet.fields_updated=0x3f;
	const uint64_t last_valid=sim->_last_accel_fifo.timestamp_sample;
	for(int k=0;k<20;++k) {
		sample+=4000;sim->update_sensors(sample,packet);
		EXPECT_FALSE(fifo.updated());
		for(int j=0;j<3;++j) {
			EXPECT_FALSE(accel[j].updated());
			imus[j]->Run();imus[j]->ScheduleClear();EXPECT_FALSE(imu[j].updated());
		}
	}
	EXPECT_EQ(sim->_last_accel_fifo.timestamp_sample,last_valid);
	packet.xacc=0.f;
	bool recovered[3]{};
	for(int k=0;k<8;++k) {
		sample+=4000;sim->update_sensors(sample,packet);
		ASSERT_TRUE(fifo.update(&integer));
		if(k==0) { EXPECT_FLOAT_EQ(integer.dt,84000.f); }
		for(int j=0;j<3;++j) {
			ASSERT_TRUE(accel[j].update(&raw[j]));EXPECT_EQ(raw[j].error_count,20);
			imus[j]->Run();imus[j]->ScheduleClear();
			if(imu[j].update(&integrated[j])) {
				recovered[j]=true;
				EXPECT_LE(integrated[j].delta_velocity_dt,65535);
				for(float v:integrated[j].delta_velocity) { EXPECT_TRUE(std::isfinite(v));EXPECT_FLOAT_EQ(v,0.f); }
			}
		}
	}
	for(bool v:recovered) { EXPECT_TRUE(v); }
}

TEST_F(ImuConversionChain, RepairInvalidFirstPacketDoesNotSeedFifo)
{
	delete sim;sim=new Simulator();
	for(int j=0;j<3;++j) { while(accel[j].update(&raw[j])) {} }
	while(fifo.update(&integer)) {}
	mavlink_hil_sensor_t packet{};packet.fields_updated=7;packet.zacc=NAN;
	sim->update_sensors(sample,packet);
	EXPECT_EQ(sim->_last_accel_fifo.timestamp_sample,0);EXPECT_EQ(sim->_last_accel_fifo.samples,0);
	EXPECT_FALSE(fifo.updated());
	for(int j=0;j<3;++j) { EXPECT_FALSE(accel[j].updated()); }
	packet.zacc=-CONSTANTS_ONE_G;sample+=4000;sim->update_sensors(sample,packet);
	ASSERT_TRUE(fifo.update(&integer));EXPECT_EQ(integer.z[0],-2048);
	for(int j=0;j<3;++j) {
		ASSERT_TRUE(accel[j].update(&raw[j]));EXPECT_EQ(raw[j].error_count,1);
	}
	EXPECT_FLOAT_EQ(raw[0].z,-.5f*CONSTANTS_ONE_G);
}

TEST_F(ImuConversionChain, RepairBlockedAndStuckInjectionPreserved)
{
	sim->_accel_stuck[0]=true;sim->_accel_blocked[1]=true;
	const auto before=sim->_last_accel_fifo;
	mavlink_hil_sensor_t packet{};packet.fields_updated=7;packet.zacc=NAN;
	sample+=4000;sim->update_sensors(sample,packet);
	ASSERT_TRUE(fifo.update(&integer));EXPECT_EQ(integer.timestamp_sample,before.timestamp_sample);
	EXPECT_TRUE(accel[0].update(&raw[0]));EXPECT_FALSE(accel[1].updated());EXPECT_FALSE(accel[2].updated());
	EXPECT_EQ(sim->_px4_accel[0]._error_count,0);EXPECT_EQ(sim->_px4_accel[1]._error_count,0);
	EXPECT_EQ(sim->_px4_accel[2]._error_count,1);
	sim->_accel_stuck[0]=false;sim->_accel_blocked[1]=false;
	packet.zacc=-CONSTANTS_ONE_G;sample+=4000;sim->update_sensors(sample,packet);
	ASSERT_TRUE(fifo.update(&integer));EXPECT_EQ(integer.timestamp_sample,sample);
	for(int j=0;j<3;++j) { ASSERT_TRUE(accel[j].update(&raw[j])); }
}

TEST_F(ImuConversionChain, RepairValidTrace2048AgainstFrozenSource)
{
	uint32_t state=0x1066a1u;
	for(int n=0;n<2048;++n) {
		float a[3];
		for(int axis=0;axis<3;++axis) {
			state=1664525u*state+1013904223u;
			a[axis]=float(int(state%60001u)-30000)*scale;
		}
		if(n<4) { a[0]=a[1]=a[2]= n==0?0.f:n==1?-0.f:n==2?FLT_MIN:std::numeric_limits<float>::denorm_min(); }
		step(a[0],a[1],a[2]);
		std::printf("REPAIR_TRACE %d %llu %d %d %d",n,(unsigned long long)sample,int(integer.x[0]),int(integer.y[0]),int(integer.z[0]));
		for(int j=0;j<3;++j) {
			std::printf(" %u %.9g %.9g %.9g %u %u %u %u %u %.9g %.9g %.9g %u",
				unsigned(raw[j].device_id),double(raw[j].x),double(raw[j].y),double(raw[j].z),unsigned(raw[j].clip_counter[0]),
				unsigned(raw[j].clip_counter[1]),unsigned(raw[j].clip_counter[2]),unsigned(raw[j].error_count),
				unsigned(integrated[j].delta_velocity_dt),double(integrated[j].delta_velocity[0]),
				double(integrated[j].delta_velocity[1]),double(integrated[j].delta_velocity[2]),unsigned(integrated[j].delta_velocity_clipping));
		}
		std::printf("\n");
	}
}
