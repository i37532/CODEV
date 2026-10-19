// SPDX-License-Identifier: BSD-3-Clause
// R02/R03: parameter-server/BSON transactions only; no simulator or flight.
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

TEST_F(RegularizedVelocityParam, BsonReloadAdmitsGateDXOrZOrXyOrXyzAndChecksEverySelectedWidth)
{
	const float values[3]{.001f, .031f, 1.f};
	for (const int32_t requested_axes : {1, 2, 3, 4, 5, 6, 7}) {
		for (int i = 0; i < 3; ++i) { ASSERT_EQ(param_set(keys[i], &values[i]), 0); }
		int32_t mode = 3, axes = requested_axes;
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
		ASSERT_EQ(param_get(param_find("MPC_VC_AXES"), &axes), 0); EXPECT_EQ(axes, requested_axes);
		c.axes = static_cast<uint8_t>(axes);
		PositionControl restarted; configure(restarted, c, false);
		if (requested_axes == 1 || requested_axes == 4 || requested_axes == 3 || requested_axes == 7) {
			EXPECT_EQ(restarted.velocitySelection().effectiveMode(), 3);
			EXPECT_EQ(restarted.velocitySelection().effectiveAxes(), requested_axes);
			EXPECT_EQ(restarted.velocitySelection().reject(), 0); EXPECT_GT(restarted.velocityEstaGeneration(), 0u);
			for (int selected = 0; selected < 3; ++selected) {
				if (requested_axes & (1 << selected)) {
					EXPECT_FLOAT_EQ(restarted.effectiveVelocityEsta().epsilon[selected], values[selected]);
				}
			}
		} else {
			EXPECT_EQ(restarted.velocitySelection().effectiveMode(), 0);
			EXPECT_NE(restarted.velocitySelection().reject(), 0); EXPECT_EQ(restarted.velocityEstaGeneration(), 0u);
		}
	}
}

TEST_F(RegularizedVelocityParam, InvalidRawParameterIsNotClampedIntoAdmission)
{
	for (float value : {-.01f, 0.f, .000999f, 1.001f, INFINITY, NAN}) {
		ASSERT_EQ(param_set(keys[0], &value), 0);
		auto c = config(); c.axes = 1; ASSERT_EQ(param_get(keys[0], &c.epsilon[0]), 0);
		if (std::isnan(value)) { EXPECT_TRUE(std::isnan(c.epsilon[0])); }
		else { EXPECT_FLOAT_EQ(c.epsilon[0], value); }
		EXPECT_FALSE(StaVelocityProtection::validConfig(c));
		PositionControl p; configure(p, c, false);
		EXPECT_EQ(p.velocitySelection().effectiveMode(), 0);
		EXPECT_TRUE(p.velocityEstaRejected()); EXPECT_NE(p.velocitySelection().reject(), 0);
	}
}

TEST_F(RegularizedVelocityParam, ValidInclusiveBoundariesAndSelectedAxisOnly)
{
	for (float value : {.001f, 1.f}) {
		auto c = config(); c.axes = 1; c.epsilon = {{value, NAN, INFINITY}};
		PositionControl p; configure(p, c, false);
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

TEST_F(RegularizedVelocityParam, ProductionZSelectedEpsilonDomainAndUnselectedWidths)
{
	for (const float width : {.001f, 1.f}) {
		PositionControl p; auto c = config(); c.axes = 4; c.epsilon = {{NAN, INFINITY, width}};
		configure(p, c, false); ASSERT_EQ(p.velocitySelection().effectiveMode(), 3);
		EXPECT_EQ(p.velocitySelection().effectiveAxes(), 4); EXPECT_FALSE(p.velocityEstaRejected());
		EXPECT_FLOAT_EQ(p.effectiveVelocityEsta().epsilon[2], width);
	}
	for (const float width : {-.01f, 0.f, .000999f, 1.001f, INFINITY, NAN}) {
		ASSERT_EQ(param_set(keys[2], &width), 0);
		PositionControl p; auto c = config(); c.axes = 4; ASSERT_EQ(param_get(keys[2], &c.epsilon[2]), 0);
		EXPECT_FALSE(StaVelocityProtection::validConfig(c)); configure(p, c, false);
		EXPECT_EQ(p.velocitySelection().effectiveMode(), 0); EXPECT_TRUE(p.velocityEstaRejected());
		EXPECT_NE(p.velocitySelection().reject(), 0);
	}
}

TEST_F(RegularizedVelocityParam, ProductionZArmedEpsilonCancelDisarmAndCumulativeXSwitch)
{
	PositionControl p; auto initial = config(); initial.axes = 4;
	configure(p, initial, false); ASSERT_EQ(p.velocitySelection().effectiveMode(), 3);
	ASSERT_EQ(p.velocitySelection().effectiveAxes(), 4); const auto generation = p.velocityEstaGeneration();
	auto changed = initial; changed.epsilon[2] = .031f;
	configure(p, changed, true); EXPECT_TRUE(p.velocityEstaPending()); EXPECT_FALSE(p.velocitySelection().pending());
	EXPECT_EQ(p.velocityEstaGeneration(), generation); EXPECT_FLOAT_EQ(p.effectiveVelocityEsta().epsilon[2], .02f);
	configure(p, initial, true); EXPECT_FALSE(p.velocityEstaPending());
	configure(p, changed, true); configure(p, changed, false);
	EXPECT_FALSE(p.velocityEstaPending()); EXPECT_GT(p.velocityEstaGeneration(), generation);
	EXPECT_FLOAT_EQ(p.effectiveVelocityEsta().epsilon[2], .031f);
	const auto accepted = p.velocityEstaGeneration();
	auto unused = changed; unused.epsilon[0] = NAN; unused.epsilon[1] = INFINITY;
	configure(p, unused, true); EXPECT_FALSE(p.velocityEstaPending()); EXPECT_FALSE(p.velocityEstaRejected());
	configure(p, unused, false); EXPECT_EQ(p.velocityEstaGeneration(), accepted);
	auto x = initial; x.axes = 1;
	configure(p, x, true); EXPECT_TRUE(p.velocitySelection().pending()); EXPECT_EQ(p.velocitySelection().effectiveAxes(), 4);
	configure(p, changed, true); EXPECT_FALSE(p.velocitySelection().pending()); EXPECT_FALSE(p.velocityEstaPending());
	configure(p, x, false); EXPECT_EQ(p.velocitySelection().effectiveAxes(), 1); EXPECT_GT(p.velocityEstaGeneration(), accepted);
	configure(p, changed, false); EXPECT_EQ(p.velocitySelection().effectiveAxes(), 4);
	p.configureVelocityControl(0, 0, false); EXPECT_EQ(p.velocitySelection().effectiveMode(), 0);
}

TEST_F(RegularizedVelocityParam, ProductionXyRequiresBothWidthsAndIgnoresOnlyUnselectedZ)
{
	for (const float width : {.001f, 1.f}) {
		PositionControl p; auto c = config(); c.axes = 3; c.epsilon = {{width, width, NAN}};
		configure(p, c, false); ASSERT_EQ(p.velocitySelection().effectiveMode(), 3);
		EXPECT_EQ(p.velocitySelection().effectiveAxes(), 3); EXPECT_FALSE(p.velocityEstaRejected());
		for (int i = 0; i < 2; ++i) { EXPECT_FLOAT_EQ(p.effectiveVelocityEsta().epsilon[i], width); }
	}
	for (int axis = 0; axis < 2; ++axis) {
		for (const float width : {-.01f, 0.f, .000999f, 1.001f, INFINITY, NAN}) {
			ASSERT_EQ(param_set(keys[axis], &width), 0);
			PositionControl p; auto c = config(); c.axes = 3;
			ASSERT_EQ(param_get(keys[axis], &c.epsilon[axis]), 0); EXPECT_FALSE(StaVelocityProtection::validConfig(c));
			configure(p, c, false); EXPECT_EQ(p.velocitySelection().effectiveMode(), 0);
			EXPECT_TRUE(p.velocityEstaRejected()); EXPECT_NE(p.velocitySelection().reject(), 0);
		}
	}
}

TEST_F(RegularizedVelocityParam, ProductionXyzAllWidthsRequiredAndSelectedChangesAreAtomic)
{
	for (const float width : {.001f, 1.f}) {
		PositionControl p; auto c = config(); c.epsilon = {{width, width, width}};
		configure(p, c, false); ASSERT_EQ(p.velocitySelection().effectiveMode(), 3);
		ASSERT_EQ(p.velocitySelection().effectiveAxes(), 7); EXPECT_EQ(p.velocitySelection().reject(), 0);
		for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(p.effectiveVelocityEsta().epsilon[i], width); }
	}
	for (int axis = 0; axis < 3; ++axis) {
		PositionControl p; const auto initial = config(); configure(p, initial, false);
		ASSERT_EQ(p.velocitySelection().effectiveAxes(), 7); const auto generation = p.velocityEstaGeneration();
		auto changed = initial; changed.epsilon[axis] = .031f;
		configure(p, changed, true); EXPECT_TRUE(p.velocityEstaPending()); EXPECT_FALSE(p.velocitySelection().pending());
		EXPECT_EQ(p.velocityEstaGeneration(), generation);
		for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(p.effectiveVelocityEsta().epsilon[i], initial.epsilon[i]); }
		configure(p, initial, true); EXPECT_FALSE(p.velocityEstaPending());
		for (const float invalid_width : {-.01f, 0.f, .000999f, 1.001f, INFINITY, NAN}) {
			auto invalid = changed; invalid.epsilon[(axis + 1) % 3] = .04f; invalid.epsilon[axis] = invalid_width;
			configure(p, invalid, true); EXPECT_TRUE(p.velocityEstaPending()); EXPECT_TRUE(p.velocityEstaRejected());
			configure(p, invalid, false); EXPECT_NE(p.velocitySelection().reject(), 0);
			EXPECT_EQ(p.velocitySelection().effectiveAxes(), 7); EXPECT_EQ(p.velocityEstaGeneration(), generation);
			for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(p.effectiveVelocityEsta().epsilon[i], initial.epsilon[i]); }
		}
		configure(p, changed, false); EXPECT_EQ(p.velocitySelection().reject(), 0);
		EXPECT_GT(p.velocityEstaGeneration(), generation); EXPECT_FALSE(p.velocityEstaPending());
		for (int i = 0; i < 3; ++i) { EXPECT_FLOAT_EQ(p.effectiveVelocityEsta().epsilon[i], changed.epsilon[i]); }
		const auto accepted = p.velocityEstaGeneration(); configure(p, changed, false);
		EXPECT_EQ(p.velocityEstaGeneration(), accepted);
	}
}

TEST_F(RegularizedVelocityParam, ProductionMasksAndModesPersistBsonAndRestartWithoutTestAdmission)
{
	const float values[3]{.013f, .024f, .035f};
	for (const int32_t requested_mode : {0, 1, 3}) {
		for (const int32_t requested_mask : {1, 4, 3, 7}) {
			const int32_t requested_axes = requested_mode ? requested_mask : 0;
			for (int i = 0; i < 3; ++i) { ASSERT_EQ(param_set(keys[i], &values[i]), 0); }
			ASSERT_EQ(param_set(param_find("MPC_VC_MODE"), &requested_mode), 0);
			ASSERT_EQ(param_set(param_find("MPC_VC_AXES"), &requested_axes), 0);
			FILE *f = tmpfile(); ASSERT_NE(f, nullptr); ASSERT_EQ(param_export(fileno(f), false, nullptr), 0);
			param_reset_all(); ASSERT_EQ(lseek(fileno(f), 0, SEEK_SET), 0);
			ASSERT_EQ(param_import(fileno(f), true), 0); fclose(f);
			int32_t mode = -1, axes = -1; ASSERT_EQ(param_get(param_find("MPC_VC_MODE"), &mode), 0);
			ASSERT_EQ(param_get(param_find("MPC_VC_AXES"), &axes), 0);
			EXPECT_EQ(mode, requested_mode); EXPECT_EQ(axes, requested_axes);
			PositionControl restarted; auto c = config(); c.variant = mode == 3 ? 3 : 1; c.axes = static_cast<uint8_t>(axes);
			for (int i = 0; i < 3; ++i) {
				ASSERT_EQ(param_get(keys[i], &c.epsilon[i]), 0); EXPECT_FLOAT_EQ(c.epsilon[i], values[i]);
			}
			if (mode) { restarted.configureVelocityEsta(c, false); }
			restarted.configureVelocityControl(mode, axes, false);
			EXPECT_EQ(restarted.velocitySelection().effectiveMode(), mode);
			EXPECT_EQ(restarted.velocitySelection().effectiveAxes(), axes); EXPECT_EQ(restarted.velocitySelection().reject(), 0);
			if (mode == 3) {
				for (int i = 0; i < 3; ++i) {
					if (axes & (1 << i)) { EXPECT_FLOAT_EQ(restarted.effectiveVelocityEsta().epsilon[i], values[i]); }
				}
			}
		}
	}
	// The production gate's existing rejection tests separately retain MODE=2
	// and AXES=2/5/6 rejection. Persistence does not broaden their valid domain.
}

TEST_F(RegularizedVelocityParam, ProductionXyWidthTransactionCannotPartiallyAcceptOneAxis)
{
	PositionControl p; auto initial = config(); initial.axes = 3; initial.epsilon = {{.01f, .02f, .03f}};
	configure(p, initial, false); ASSERT_EQ(p.velocitySelection().effectiveAxes(), 3);
	const auto generation = p.velocityEstaGeneration(); auto changed = initial; changed.epsilon[1] = .031f;
	configure(p, changed, true); EXPECT_TRUE(p.velocityEstaPending()); EXPECT_FALSE(p.velocitySelection().pending());
	EXPECT_EQ(p.velocityEstaGeneration(), generation);
	EXPECT_FLOAT_EQ(p.effectiveVelocityEsta().epsilon[0], .01f); EXPECT_FLOAT_EQ(p.effectiveVelocityEsta().epsilon[1], .02f);
	configure(p, initial, true); EXPECT_FALSE(p.velocityEstaPending());
	auto invalid = changed; invalid.epsilon[0] = .04f; invalid.epsilon[1] = NAN;
	configure(p, invalid, true); EXPECT_TRUE(p.velocityEstaPending()); EXPECT_TRUE(p.velocityEstaRejected());
	configure(p, invalid, false); EXPECT_NE(p.velocitySelection().reject(), 0);
	EXPECT_EQ(p.velocityEstaGeneration(), generation); EXPECT_EQ(p.velocitySelection().effectiveAxes(), 3);
	EXPECT_FLOAT_EQ(p.effectiveVelocityEsta().epsilon[0], .01f); EXPECT_FLOAT_EQ(p.effectiveVelocityEsta().epsilon[1], .02f);
	configure(p, changed, false); EXPECT_GT(p.velocityEstaGeneration(), generation);
	EXPECT_FLOAT_EQ(p.effectiveVelocityEsta().epsilon[0], .01f); EXPECT_FLOAT_EQ(p.effectiveVelocityEsta().epsilon[1], .031f);
	const auto accepted = p.velocityEstaGeneration(); auto unused = changed; unused.epsilon[2] = NAN;
	configure(p, unused, true); EXPECT_FALSE(p.velocityEstaPending()); EXPECT_FALSE(p.velocityEstaRejected());
	configure(p, unused, false); EXPECT_EQ(p.velocityEstaGeneration(), accepted);
	for (const uint8_t axes : {1, 4, 3}) {
		auto next = initial; next.axes = axes; configure(p, next, false);
		EXPECT_EQ(p.velocitySelection().effectiveMode(), 3); EXPECT_EQ(p.velocitySelection().effectiveAxes(), axes);
		EXPECT_EQ(p.velocitySelection().reject(), 0);
	}
	auto xz = initial; xz.axes = 5; const auto before_xz = p.velocityEstaGeneration();
	configure(p, xz, false); EXPECT_NE(p.velocitySelection().reject(), 0);
	EXPECT_EQ(p.velocitySelection().effectiveAxes(), 3); EXPECT_EQ(p.velocityEstaGeneration(), before_xz);
}
