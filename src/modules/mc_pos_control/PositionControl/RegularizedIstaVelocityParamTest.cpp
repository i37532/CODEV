// SPDX-License-Identifier: BSD-3-Clause
// RI03: actual parameter server/BSON and X-only production configuration gate.
#include <gtest/gtest.h>
#include <parameters/param.h>
#include "PositionControl.hpp"
#include <cmath>
#include <cstdio>
#include <unistd.h>

class RegularizedIstaVelocityTestAccess
{
public:
	static void admit(PositionControl &p) { p._regularized_ista_admission = true; }
};

class RegularizedIstaVelocityParam : public ::testing::Test
{
protected:
	static constexpr const char *names[3][5] = {
		{"MPC_VC_L1_X", "MPC_VC_L2_X", "MPC_VC_NU_X", "MPC_VC_A_X", "MPC_VC_EPS_X"},
		{"MPC_VC_L1_Y", "MPC_VC_L2_Y", "MPC_VC_NU_Y", "MPC_VC_A_Y", "MPC_VC_EPS_Y"},
		{"MPC_VC_L1_Z", "MPC_VC_L2_Z", "MPC_VC_NU_Z", "MPC_VC_A_Z", "MPC_VC_EPS_Z"}
	};
	void SetUp() override { param_control_autosave(false); param_reset_all(); }
	void TearDown() override { param_reset_all(); }
	static StaVelocityProtection::Config config(uint8_t axes = 7, uint8_t variant = 4)
	{
		StaVelocityProtection::Config c{}; c.axes = axes; c.variant = variant;

		for (int i = 0; i < 3; ++i) {
			c.gains[i] = {i == 2 ? 2.f : .5f, i == 2 ? 1.f : .1f};
			c.nu_limit[i] = i == 2 ? 4.f : .4f; c.acceleration_limit[i] = i == 2 ? 6.f : .8f;
		}

		return c;
	}
	static void configure(PositionControl &p, const StaVelocityProtection::Config &c, bool armed)
	{
		p.configureVelocityEsta(c, armed); p.configureVelocityControl(c.variant, c.axes, armed);
	}
	static void writeConfig(const StaVelocityProtection::Config &c)
	{
		for (int i = 0; i < 3; ++i) {
			const float values[5] {c.gains[i].lambda1, c.gains[i].lambda2, c.nu_limit[i], c.acceleration_limit[i], c.epsilon[i]};

			for (int j = 0; j < 5; ++j) {
				const param_t key = param_find(names[i][j]); ASSERT_NE(key, PARAM_INVALID);
				ASSERT_EQ(param_set(key, &values[j]), 0);
			}
		}

		const int32_t mode = c.variant, axes = c.axes, div = 1;
		ASSERT_EQ(param_set(param_find("MPC_VC_MODE"), &mode), 0);
		ASSERT_EQ(param_set(param_find("MPC_VC_AXES"), &axes), 0);
		ASSERT_EQ(param_set(param_find("MPC_VC_DIV"), &div), 0);
	}
	static StaVelocityProtection::Config readConfig()
	{
		auto c = config(); int32_t mode = -1, axes = -1;
		EXPECT_EQ(param_get(param_find("MPC_VC_MODE"), &mode), 0);
		EXPECT_EQ(param_get(param_find("MPC_VC_AXES"), &axes), 0);
		c.variant = static_cast<uint8_t>(mode); c.axes = static_cast<uint8_t>(axes);

		for (int i = 0; i < 3; ++i) {
			float values[5] {};

			for (int j = 0; j < 5; ++j) { EXPECT_EQ(param_get(param_find(names[i][j]), &values[j]), 0); }

			c.gains[i] = {values[0], values[1]}; c.nu_limit[i] = values[2];
			c.acceleration_limit[i] = values[3]; c.epsilon[i] = values[4];
		}

		return c;
	}
	static void same(const StaVelocityProtection::Config &a, const StaVelocityProtection::Config &b)
	{
		EXPECT_EQ(a.variant, b.variant); EXPECT_EQ(a.axes, b.axes);

		for (int i = 0; i < 3; ++i) {
			EXPECT_FLOAT_EQ(a.gains[i].lambda1, b.gains[i].lambda1);
			EXPECT_FLOAT_EQ(a.gains[i].lambda2, b.gains[i].lambda2);
			EXPECT_FLOAT_EQ(a.nu_limit[i], b.nu_limit[i]); EXPECT_FLOAT_EQ(a.acceleration_limit[i], b.acceleration_limit[i]);
			EXPECT_FLOAT_EQ(a.epsilon[i], b.epsilon[i]);
		}
	}
};
constexpr const char *RegularizedIstaVelocityParam::names[3][5];

TEST_F(RegularizedIstaVelocityParam, ExistingPidAndIndependentWidthDefaultsUnchanged)
{
	int32_t mode = -1, axes = -1, div = -1;
	ASSERT_EQ(param_get(param_find("MPC_VC_MODE"), &mode), 0); EXPECT_EQ(mode, 0);
	ASSERT_EQ(param_get(param_find("MPC_VC_AXES"), &axes), 0); EXPECT_EQ(axes, 0);
	ASSERT_EQ(param_get(param_find("MPC_VC_DIV"), &div), 0); EXPECT_EQ(div, 1);

	for (int i = 0; i < 3; ++i) {
		for (int j = 0; j < 5; ++j) {
			float value = NAN; const param_t key = param_find(names[i][j]); ASSERT_NE(key, PARAM_INVALID);
			EXPECT_EQ(param_type(key), PARAM_TYPE_FLOAT); ASSERT_EQ(param_get(key, &value), 0);
			EXPECT_FLOAT_EQ(value, j == 4 ? (i == 2 ? .02f : .01f) : 0.f);
		}
	}
}

TEST_F(RegularizedIstaVelocityParam, RI03ProductionAdmitsOnlyDisarmedXWithValidConfiguration)
{
	for (const bool armed : {false, true}) {
		for (int axes = 0; axes <= 7; ++axes) {
			PositionControl p; auto c = config(static_cast<uint8_t>(axes)); configure(p, c, armed);
			const bool admitted = axes == 1;
			EXPECT_EQ(p.velocitySelection().requestedMode(), 4);
			EXPECT_EQ(p.velocitySelection().effectiveMode(), admitted && !armed ? 4 : 0);
			EXPECT_EQ(p.velocitySelection().effectiveAxes(), admitted && !armed ? 1 : 0);
			EXPECT_EQ(bool(p.velocitySelection().reject() & VelocityControlSelector::ModeUnimplemented), !admitted);
			EXPECT_FALSE(p.velocitySelection().reject() & VelocityControlSelector::ModeRange);
			EXPECT_EQ(p.velocityEstaGeneration() > 0, admitted && !armed);
		}
	}
}

TEST_F(RegularizedIstaVelocityParam, SelectorRecognizesButRefusesNewModeAndKeepsLegacyMeanings)
{
	VelocityControlSelector selector;

	for (int mode : {-1, 5, 256}) {
		selector.configure(mode, 0, false); EXPECT_TRUE(selector.reject() & VelocityControlSelector::ModeRange);
	}
	selector.configure(2, 0, false, true, 0, true, true);
	EXPECT_TRUE(selector.reject() & VelocityControlSelector::ModeUnimplemented);

	for (int mode : {1, 3}) {
		selector.configure(mode, 1, false, true, 1, true);
		EXPECT_EQ(selector.effectiveMode(), mode); EXPECT_EQ(selector.reject(), 0);
		selector.configure(4, 1, false, true, 1, true);
		EXPECT_EQ(selector.effectiveMode(), mode); EXPECT_TRUE(selector.reject() & VelocityControlSelector::ModeUnimplemented);
	}
	selector.configure(0, 0, false); EXPECT_EQ(selector.effectiveMode(), 0);
}

TEST_F(RegularizedIstaVelocityParam, OfflineMasksOneThreeFourSevenOnlyAndDivisorOneOnly)
{
	for (int axes = 0; axes <= 7; ++axes) {
		PositionControl p; RegularizedIstaVelocityTestAccess::admit(p); configure(p, config(static_cast<uint8_t>(axes)), false);
		const bool allowed = axes == 1 || axes == 3 || axes == 4 || axes == 7;
		EXPECT_EQ(p.velocitySelection().effectiveMode(), allowed ? 4 : 0);
		EXPECT_EQ(p.velocitySelection().reject() == 0, allowed);
	}

	for (int div : {2, 4}) {
		PositionControl p; RegularizedIstaVelocityTestAccess::admit(p);
		p.configureVelocityDivisor(div, false); ASSERT_EQ(p.velocityDecimation().divisor, div);
		configure(p, config(), false); EXPECT_EQ(p.velocitySelection().effectiveMode(), 0);
		EXPECT_NE(p.velocitySelection().reject(), 0);
	}
}

TEST_F(RegularizedIstaVelocityParam, RI03CompleteBsonConfigurationAdmitsOnlyXAfterReload)
{
	for (const uint8_t axes : {1, 3, 4, 7}) {
		auto original = config(axes);

		for (int i = 0; i < 3; ++i) {
			original.gains[i].lambda1 += .03f * static_cast<float>(i + 1);
			original.epsilon[i] += .001f * static_cast<float>(i + 1);
		}

		writeConfig(original); FILE *file = tmpfile(); ASSERT_NE(file, nullptr);
		ASSERT_EQ(param_export(fileno(file), false, nullptr), 0); param_reset_all();
		ASSERT_EQ(lseek(fileno(file), 0, SEEK_SET), 0); ASSERT_EQ(param_import(fileno(file), true), 0); fclose(file);
		const auto loaded = readConfig(); same(original, loaded);
		PositionControl production; configure(production, loaded, false);
		EXPECT_EQ(production.velocitySelection().effectiveMode(), axes == 1 ? 4 : 0);
		EXPECT_EQ(production.velocitySelection().reject() == 0, axes == 1);
		if (axes == 1) { same(production.effectiveVelocityEsta(), original); }
		PositionControl offline; RegularizedIstaVelocityTestAccess::admit(offline); configure(offline, loaded, false);
		ASSERT_EQ(offline.velocitySelection().effectiveMode(), 4); same(offline.effectiveVelocityEsta(), original);
	}
}

TEST_F(RegularizedIstaVelocityParam, AllFifteenValuesStageCancelThenCommitTogetherOnDisarm)
{
	PositionControl p; RegularizedIstaVelocityTestAccess::admit(p); const auto initial = config();
	configure(p, initial, false);
	ASSERT_EQ(p.velocitySelection().effectiveMode(), 4); const auto generation = p.velocityEstaGeneration();
	auto changed = initial;

	for (int i = 0; i < 3; ++i) {
		changed.gains[i].lambda1 *= 1.1f; changed.gains[i].lambda2 *= 1.1f;
		changed.nu_limit[i] *= 1.1f; changed.acceleration_limit[i] *= 1.1f; changed.epsilon[i] *= 1.1f;
	}

	configure(p, changed, true); EXPECT_TRUE(p.velocityEstaPending()); EXPECT_FALSE(p.velocitySelection().pending());
	EXPECT_EQ(p.velocityEstaGeneration(), generation); same(p.effectiveVelocityEsta(), initial);
	configure(p, initial, true); EXPECT_FALSE(p.velocityEstaPending()); same(p.effectiveVelocityEsta(), initial);
	configure(p, changed, true); configure(p, changed, false);
	EXPECT_FALSE(p.velocityEstaPending()); EXPECT_EQ(p.velocitySelection().reject(), 0);
	EXPECT_GT(p.velocityEstaGeneration(), generation); same(p.effectiveVelocityEsta(), changed);
	const auto committed = p.velocityEstaGeneration(); configure(p, changed, false);
	EXPECT_EQ(p.velocityEstaGeneration(), committed);
}

TEST_F(RegularizedIstaVelocityParam, InvalidLastAxisNeverPartiallyCommitsOtherRequestedValues)
{
	PositionControl p; RegularizedIstaVelocityTestAccess::admit(p); const auto initial = config();
	configure(p, initial, false);
	const auto generation = p.velocityEstaGeneration();

	for (const float invalid : {NAN, INFINITY, -.01f, 0.f, .000999f, 1.001f}) {
		auto changed = initial; changed.gains[0].lambda1 = .6f; changed.nu_limit[1] = .5f; changed.epsilon[2] = invalid;
		configure(p, changed, true); EXPECT_TRUE(p.velocityEstaPending()); EXPECT_TRUE(p.velocityEstaRejected());
		configure(p, changed, false); EXPECT_NE(p.velocitySelection().reject(), 0);
		EXPECT_EQ(p.velocityEstaGeneration(), generation); same(p.effectiveVelocityEsta(), initial);
	}
}

TEST_F(RegularizedIstaVelocityParam, SelectedGainLimitAndWidthRawNanInfValuesAreNeverClamped)
{
	for (int field = 0; field < 5; ++field) {
		for (const float invalid : {NAN, INFINITY, -1.f, 0.f}) {
			writeConfig(config()); ASSERT_EQ(param_set(param_find(names[2][field]), &invalid), 0);
			const auto raw = readConfig(); EXPECT_FALSE(StaVelocityProtection::validConfig(raw));
			PositionControl p; RegularizedIstaVelocityTestAccess::admit(p); configure(p, raw, false);
			EXPECT_TRUE(p.velocityEstaRejected()); EXPECT_EQ(p.velocitySelection().effectiveMode(), 0);
		}
	}
}

TEST_F(RegularizedIstaVelocityParam, AcceptedEpsilonEndpointsRemainExact)
{
	for (float epsilon : {.001f, 1.f}) {
		PositionControl p; RegularizedIstaVelocityTestAccess::admit(p); auto c = config(); c.epsilon.fill(epsilon);
		configure(p, c, false); ASSERT_EQ(p.velocitySelection().effectiveMode(), 4);

		for (int axis = 0; axis < 3; ++axis) { EXPECT_FLOAT_EQ(p.effectiveVelocityEsta().epsilon[axis], epsilon); }
	}
}

TEST_F(RegularizedIstaVelocityParam, IndependentFullAlgorithmConfigurationsRestoreWithoutInheritance)
{
	PositionControl p; RegularizedIstaVelocityTestAccess::admit(p);
	const auto explicit_config = config(7, 3); auto implicit_config = config(7, 4);

	for (int i = 0; i < 3; ++i) {
		implicit_config.gains[i].lambda1 *= 1.2f; implicit_config.gains[i].lambda2 *= .9f;
		implicit_config.nu_limit[i] *= 1.1f; implicit_config.acceleration_limit[i] *= 1.1f;
		implicit_config.epsilon[i] *= 1.3f;
	}

	configure(p, explicit_config, false); same(p.effectiveVelocityEsta(), explicit_config);
	const auto generation = p.velocityEstaGeneration(); configure(p, implicit_config, true);
	EXPECT_TRUE(p.velocitySelection().pending()); EXPECT_TRUE(p.velocityEstaPending());
	same(p.effectiveVelocityEsta(), explicit_config); EXPECT_EQ(p.velocityEstaGeneration(), generation);
	configure(p, explicit_config, true); EXPECT_FALSE(p.velocitySelection().pending());
	EXPECT_FALSE(p.velocityEstaPending());
	configure(p, implicit_config, false); same(p.effectiveVelocityEsta(), implicit_config);
	EXPECT_EQ(p.velocitySelection().effectiveMode(), 4); EXPECT_GT(p.velocityEstaGeneration(), generation);
	configure(p, explicit_config, false); same(p.effectiveVelocityEsta(), explicit_config);
	EXPECT_EQ(p.velocitySelection().effectiveMode(), 3);
}

TEST_F(RegularizedIstaVelocityParam, ProductionRejectedNewRequestCannotMutateExistingRstaConfiguration)
{
	PositionControl p; const auto original = config(3, 3); configure(p, original, false);
	ASSERT_EQ(p.velocitySelection().effectiveMode(), 3); const auto generation = p.velocityEstaGeneration();
	auto request = config(7, 4); request.epsilon[0] = .05f; request.gains[1].lambda1 = .7f;

	for (bool armed : {true, false}) {
		configure(p, request, armed); EXPECT_EQ(p.velocitySelection().effectiveMode(), 3);
		EXPECT_EQ(p.velocitySelection().effectiveAxes(), 3); EXPECT_EQ(p.velocityEstaGeneration(), generation);
		EXPECT_NE(p.velocitySelection().reject(), 0); same(p.effectiveVelocityEsta(), original);
	}
	configure(p, original, true); EXPECT_FALSE(p.velocitySelection().pending()); EXPECT_FALSE(p.velocityEstaPending());
}

TEST_F(RegularizedIstaVelocityParam, RI03ProductionXRejectsEveryOtherDivisorAndMismatchedConfiguration)
{
	for (int32_t div : {-1, 0, 2, 3, 4, 8, 257}) {
		PositionControl p; p.configureVelocityDivisor(div, false); configure(p, config(1), false);
		EXPECT_EQ(p.velocitySelection().effectiveMode(), 0);
		EXPECT_NE(p.velocitySelection().reject(), 0); EXPECT_EQ(p.velocityEstaGeneration(), 0u);
	}

	for (const uint8_t axes : {2, 3, 4, 5, 6, 7}) {
		PositionControl p; p.configureVelocityEsta(config(axes), false);
		p.configureVelocityControl(4, 1, false);
		EXPECT_EQ(p.velocitySelection().effectiveMode(), 0);
		EXPECT_TRUE(p.velocitySelection().reject() & VelocityControlSelector::AxesUnavailable);
	}

	for (const uint8_t variant : {0, 1, 2, 3}) {
		PositionControl p; p.configureVelocityEsta(config(1, variant), false);
		p.configureVelocityControl(4, 1, false);
		EXPECT_EQ(p.velocitySelection().effectiveMode(), 0);
		EXPECT_TRUE(p.velocitySelection().reject() & VelocityControlSelector::ModeUnimplemented);
	}
}

TEST_F(RegularizedIstaVelocityParam, RI03ProductionXRejectsRawInvalidSelectedParameters)
{
	for (int field = 0; field < 5; ++field) {
		for (const float invalid : {NAN, INFINITY, -1.f, 0.f}) {
			writeConfig(config(1)); ASSERT_EQ(param_set(param_find(names[0][field]), &invalid), 0);
			PositionControl p; configure(p, readConfig(), false);
			EXPECT_TRUE(p.velocityEstaRejected()); EXPECT_EQ(p.velocitySelection().effectiveMode(), 0);
			EXPECT_EQ(p.velocityEstaGeneration(), 0u);
		}
	}
}
