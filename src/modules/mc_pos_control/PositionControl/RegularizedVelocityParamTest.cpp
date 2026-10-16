// SPDX-License-Identifier: BSD-3-Clause
// R02: parameter-server/BSON transactions only; no simulator or actuator use.
#include <gtest/gtest.h>
#include <parameters/param.h>
#include "PositionControl.hpp"
#include <cmath>
#include <cstdio>
#include <unistd.h>

class RegularizedVelocityTestAccess
{
public:
	static void admit(PositionControl &p) { p._regularized_test_admission = true; }
};

class RegularizedVelocityParam : public ::testing::Test
{
protected:
	const char *names[3]{"MPC_VC_EPS_X", "MPC_VC_EPS_Y", "MPC_VC_EPS_Z"};
	param_t keys[3]{};
	void SetUp() override
	{
		param_control_autosave(false);
		param_reset_all();
		for (int i = 0; i < 3; ++i) {
			keys[i] = param_find(names[i]); ASSERT_NE(keys[i], PARAM_INVALID);
		}
	}
	void TearDown() override { param_reset_all(); }
	static StaVelocityProtection::Config config()
	{
		StaVelocityProtection::Config c{}; c.axes = 7; c.variant = 3;
		for (int i = 0; i < 3; ++i) {
			c.gains[i] = {.5f, .1f}; c.nu_limit[i] = .4f; c.acceleration_limit[i] = .8f;
		}
		return c;
	}
	static void configure(PositionControl &p, const StaVelocityProtection::Config &c, bool armed)
	{
		p.configureVelocityEsta(c, armed); p.configureVelocityControl(c.variant, c.axes, armed);
	}
};

TEST_F(RegularizedVelocityParam, IndependentDefaultsKeepPidDefault)
{
	const float defaults[3]{.01f, .01f, .02f};
	for (int i = 0; i < 3; ++i) {
		EXPECT_EQ(param_type(keys[i]), PARAM_TYPE_FLOAT);
		float value = NAN; ASSERT_EQ(param_get(keys[i], &value), 0); EXPECT_FLOAT_EQ(value, defaults[i]);
	}
	for (const char *name : {"MPC_VC_MODE", "MPC_VC_AXES"}) {
		int32_t value = -1; ASSERT_EQ(param_get(param_find(name), &value), 0); EXPECT_EQ(value, 0);
	}
	int32_t div = -1; ASSERT_EQ(param_get(param_find("MPC_VC_DIV"), &div), 0); EXPECT_EQ(div, 1);
}

TEST_F(RegularizedVelocityParam, BsonIndependentWidthsAndModeSurviveButProductionRejects)
{
	const float values[3]{.001f, .031f, 1.f};
	for (int i = 0; i < 3; ++i) { ASSERT_EQ(param_set(keys[i], &values[i]), 0); }
	int32_t mode = 3, axes = 7;
	ASSERT_EQ(param_set(param_find("MPC_VC_MODE"), &mode), 0);
	ASSERT_EQ(param_set(param_find("MPC_VC_AXES"), &axes), 0);
	FILE *f = tmpfile(); ASSERT_NE(f, nullptr);
	ASSERT_EQ(param_export(fileno(f), false, nullptr), 0);
	param_reset_all(); ASSERT_EQ(lseek(fileno(f), 0, SEEK_SET), 0);
	ASSERT_EQ(param_import(fileno(f), true), 0); fclose(f);
	auto c = config();
	for (int i = 0; i < 3; ++i) {
		ASSERT_EQ(param_get(keys[i], &c.epsilon[i]), 0); EXPECT_FLOAT_EQ(c.epsilon[i], values[i]);
	}
	ASSERT_EQ(param_get(param_find("MPC_VC_MODE"), &mode), 0); EXPECT_EQ(mode, 3);
	ASSERT_EQ(param_get(param_find("MPC_VC_AXES"), &axes), 0); EXPECT_EQ(axes, 7);
	PositionControl restarted; configure(restarted, c, false);
	EXPECT_EQ(restarted.velocitySelection().effectiveMode(), 0);
	EXPECT_NE(restarted.velocitySelection().reject(), 0);
	EXPECT_EQ(restarted.velocityEstaGeneration(), 0u);
}

TEST_F(RegularizedVelocityParam, InvalidRawParameterIsNotClampedIntoAdmission)
{
	for (float value : {-.01f, 0.f, .000999f, 1.001f, INFINITY, NAN}) {
		ASSERT_EQ(param_set(keys[0], &value), 0);
		auto c = config(); ASSERT_EQ(param_get(keys[0], &c.epsilon[0]), 0);
		if (std::isnan(value)) { EXPECT_TRUE(std::isnan(c.epsilon[0])); }
		else { EXPECT_FLOAT_EQ(c.epsilon[0], value); }
		EXPECT_FALSE(StaVelocityProtection::validConfig(c));
		PositionControl p; RegularizedVelocityTestAccess::admit(p); configure(p, c, false);
		EXPECT_EQ(p.velocitySelection().effectiveMode(), 0);
		EXPECT_TRUE(p.velocityEstaRejected()); EXPECT_NE(p.velocitySelection().reject(), 0);
	}
}

TEST_F(RegularizedVelocityParam, ValidInclusiveBoundariesAndSelectedAxisOnly)
{
	for (float value : {.001f, 1.f}) {
		auto c = config(); c.axes = 1; c.epsilon = {{value, NAN, INFINITY}};
		PositionControl p; RegularizedVelocityTestAccess::admit(p); configure(p, c, false);
		EXPECT_EQ(p.velocitySelection().effectiveMode(), 3);
		EXPECT_FLOAT_EQ(p.effectiveVelocityEsta().epsilon[0], value);
		EXPECT_FALSE(p.velocityEstaRejected());
	}
}

TEST_F(RegularizedVelocityParam, EpsilonOnlyArmedStageCancelAndDisarmGeneration)
{
	PositionControl p; RegularizedVelocityTestAccess::admit(p);
	const auto initial = config(); configure(p, initial, false);
	const uint32_t generation = p.velocityEstaGeneration(); ASSERT_GT(generation, 0u);
	auto request = initial; request.epsilon[1] = .021f;
	configure(p, request, true);
	EXPECT_TRUE(p.velocityEstaPending()); EXPECT_FALSE(p.velocitySelection().pending());
	EXPECT_FLOAT_EQ(p.effectiveVelocityEsta().epsilon[1], initial.epsilon[1]);
	EXPECT_EQ(p.velocityEstaGeneration(), generation);
	configure(p, initial, true); EXPECT_FALSE(p.velocityEstaPending());
	configure(p, request, true); EXPECT_TRUE(p.velocityEstaPending());
	configure(p, request, false); EXPECT_FALSE(p.velocityEstaPending());
	EXPECT_GT(p.velocityEstaGeneration(), generation);
	EXPECT_FLOAT_EQ(p.effectiveVelocityEsta().epsilon[1], request.epsilon[1]);
	const uint32_t accepted = p.velocityEstaGeneration();
	configure(p, request, false); EXPECT_EQ(p.velocityEstaGeneration(), accepted);
}

TEST_F(RegularizedVelocityParam, InvalidWidthPreservesEffectiveConfig)
{
	PositionControl p; RegularizedVelocityTestAccess::admit(p);
	const auto initial = config(); configure(p, initial, false);
	const uint32_t generation = p.velocityEstaGeneration();
	auto invalid = initial; invalid.epsilon[2] = NAN;
	configure(p, invalid, true); EXPECT_TRUE(p.velocityEstaPending()); EXPECT_TRUE(p.velocityEstaRejected());
	configure(p, invalid, false);
	EXPECT_EQ(p.velocitySelection().effectiveMode(), 3); EXPECT_NE(p.velocitySelection().reject(), 0);
	EXPECT_EQ(p.velocityEstaGeneration(), generation);
	EXPECT_FLOAT_EQ(p.effectiveVelocityEsta().epsilon[2], initial.epsilon[2]);
}

TEST_F(RegularizedVelocityParam, OriginalEstaIgnoresEpsilonWithoutResetOrPending)
{
	PositionControl p; auto c = config(); c.variant = 1;
	configure(p, c, false); ASSERT_EQ(p.velocitySelection().effectiveMode(), 1);
	const uint32_t generation = p.velocityEstaGeneration();
	c.epsilon = {{NAN, -.2f, INFINITY}};
	configure(p, c, true); EXPECT_FALSE(p.velocityEstaPending()); EXPECT_FALSE(p.velocityEstaRejected());
	configure(p, c, false); EXPECT_EQ(p.velocityEstaGeneration(), generation);
	EXPECT_EQ(p.velocitySelection().effectiveMode(), 1);
}
