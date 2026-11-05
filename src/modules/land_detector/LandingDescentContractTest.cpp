// SPDX-License-Identifier: BSD-3-Clause
// Actual detector and uORB. No changed detection thresholds or simulated flight.
#include <gtest/gtest.h>
#define MODULE_NAME "land_contract_test"
#include "MulticopterLandDetector.h"
#include <parameters/param.h>
#include <platforms/posix/apps.h>
#include <px4_platform_common/px4_work_queue/WorkQueueManager.hpp>

class ContactProbe : public land_detector::MulticopterLandDetector
{
public:
	void airborne()
	{
		_armed = true;
		const auto t = hrt_absolute_time();
		_landed_hysteresis.set_state_and_update(false, t);
		_maybe_landed_hysteresis.set_state_and_update(false, t);
		_ground_contact_hysteresis.set_state_and_update(false, t);
		_update_params();
	}
	bool step(float vz, bool valid = true)
	{
		_vehicle_local_position.timestamp = hrt_absolute_time();
		_vehicle_local_position.v_z_valid = valid;
		_vehicle_local_position.v_xy_valid = true;
		_vehicle_local_position.vz = vz;
		_update_topics();
		return _get_ground_contact_state();
	}
	bool descending() { return _get_in_descend(); }
};

class LandingContractAnchor : public px4::WorkItem
{
public:
	LandingContractAnchor() : WorkItem("landing_contract_anchor", px4::wq_configurations::nav_and_controllers) {}
	void Run() override {}
};
static LandingContractAnchor *landing_anchor = nullptr;

class LandingDescentContract : public ::testing::Test
{
public:
	static void SetUpTestSuite()
	{
		hrt_init(); // Functional gtest main does not initialize the HRT cancellation lock.
		ASSERT_EQ(px4::WorkQueueManagerStart(), 0); px4_usleep(20000);
		landing_anchor = new LandingContractAnchor();
	}
	static void TearDownTestSuite()
	{
		delete landing_anchor; landing_anchor = nullptr; px4_usleep(20000);
		EXPECT_EQ(px4::WorkQueueManagerStop(), 0);
	}
protected:
	void SetUp() override
	{
		apps_map_type apps; init_app_map(apps); ASSERT_TRUE(apps.empty());
		param_control_autosave(false); param_reset_all();
	}
	void TearDown() override { param_reset_all(); }
	uORB::Publication<vehicle_control_mode_s> mode_pub{ORB_ID(vehicle_control_mode)};
	uORB::Publication<vehicle_local_position_setpoint_s> sp_pub{ORB_ID(trajectory_setpoint)};
	uORB::Publication<actuator_controls_s> actuator_pub{ORB_ID(actuator_controls_0)};
	void signals(float target, float throttle = .1f)
	{
		vehicle_control_mode_s mode{}; mode.flag_control_climb_rate_enabled = true;
		ASSERT_TRUE(mode_pub.publish(mode));
		vehicle_local_position_setpoint_s sp{}; sp.timestamp = hrt_absolute_time(); sp.vz = target;
		ASSERT_TRUE(sp_pub.publish(sp));
		actuator_controls_s actuator{}; actuator.control[actuator_controls_s::INDEX_THROTTLE] = throttle;
		ASSERT_TRUE(actuator_pub.publish(actuator));
	}
	void landSpeed(float speed)
	{
		const param_t key = param_find("MPC_LAND_SPEED"); ASSERT_NE(key, PARAM_INVALID);
		ASSERT_EQ(param_set(key, &speed), 0);
	}
};

TEST_F(LandingDescentContract, ReproduceHalfMeterCapWithStoredPointSevenRejectsContact)
{
	landSpeed(.7f); ContactProbe p; p.airborne(); signals(.5f);
	EXPECT_FALSE(p.step(0.f)); EXPECT_FALSE(p.descending());
}

TEST_F(LandingDescentContract, OriginalPointSevenAcceptsContact)
{
	landSpeed(.7f); ContactProbe p; p.airborne(); signals(.7f);
	EXPECT_TRUE(p.step(0.f)); EXPECT_TRUE(p.descending());
}

TEST_F(LandingDescentContract, LegalPointSixAndPointFiveFiveCapPermitContact)
{
	landSpeed(.6f); ContactProbe p; p.airborne(); signals(.55f);
	EXPECT_TRUE(p.step(0.f)); EXPECT_TRUE(p.descending());
}

TEST_F(LandingDescentContract, ExactIntentBoundaryAndFloatNeighbors)
{
	landSpeed(.6f); ContactProbe p; p.airborne(); const float threshold = .9f * .6f;
	signals(std::nextafter(threshold, 0.f)); EXPECT_FALSE(p.step(0.f)); EXPECT_FALSE(p.descending());
	signals(threshold); EXPECT_TRUE(p.step(0.f)); EXPECT_TRUE(p.descending());
	signals(std::nextafter(threshold, 1.f)); EXPECT_TRUE(p.step(0.f)); EXPECT_TRUE(p.descending());
}

TEST_F(LandingDescentContract, MotionThrottleInvalidMeasurementAndNanTargetStillReject)
{
	landSpeed(.6f); ContactProbe p; p.airborne(); signals(.55f);
	EXPECT_FALSE(p.step(1.f)); EXPECT_FALSE(p.step(0.f, false));
	signals(.55f, .6f); EXPECT_FALSE(p.step(0.f));
	signals(NAN); EXPECT_FALSE(p.step(0.f)); EXPECT_FALSE(p.descending());
	signals(-.55f); EXPECT_FALSE(p.step(0.f)); EXPECT_FALSE(p.descending());
}
