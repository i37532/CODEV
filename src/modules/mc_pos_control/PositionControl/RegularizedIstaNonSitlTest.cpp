// SPDX-License-Identifier: BSD-3-Clause
// Compile the actual implementation with the SITL branch disabled. Renaming
// isolates this instance from the normal SITL library used by the other tests.
#include <gtest/gtest.h>
#include <px4_platform_common/defines.h>
#undef CONFIG_ARCH_BOARD_PX4_SITL
#define PositionControl NonSitlPositionControl
#include "PositionControl.cpp"
#undef PositionControl

#if defined(CONFIG_ARCH_BOARD_PX4_SITL)
#error The non-SITL admission test must not compile the SITL admission branch.
#endif

class RegularizedIstaVelocityTestAccess
{
public:
	static void admit(NonSitlPositionControl &p) { p._regularized_ista_admission = true; }
};

TEST(RegularizedIstaNonSitl, ActualPositionImplementationRejectsEveryModeFourMaskAndDivisor)
{
	for (const bool armed : {false, true}) {
		for (const int32_t axes : {-1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 257}) {
			for (const int32_t div : {-1, 0, 1, 2, 3, 4, 8}) {
				NonSitlPositionControl p;
				StaVelocityProtection::Config c{}; c.variant = 4;
				c.axes = axes > 0 && axes < 8 ? static_cast<uint8_t>(axes) : 1;
				c.gains = {{{.5f, .1f}, {.5f, .1f}, {2.f, 1.f}}};
				c.nu_limit = {{.4f, .4f, 4.f}}; c.acceleration_limit = {{.8f, .8f, 6.f}};
				// Even the offline later-mask override cannot bypass the target gate.
				RegularizedIstaVelocityTestAccess::admit(p);
				p.configureVelocityDivisor(div, false); p.configureVelocityEsta(c, armed);
				p.configureVelocityControl(4, axes, armed);
				EXPECT_EQ(p.velocitySelection().effectiveMode(), 0);
				EXPECT_EQ(p.velocitySelection().effectiveAxes(), 0);
				EXPECT_TRUE(p.velocitySelection().reject() & VelocityControlSelector::ModeUnimplemented);
				EXPECT_EQ(p.velocityEstaGeneration(), 0u);
			}
		}
	}
}

TEST(RegularizedIstaNonSitl, DefaultPidAndReservedModeTwoRetainTheirMeaning)
{
	NonSitlPositionControl p;
	p.configureVelocityControl(0, 0, false);
	EXPECT_EQ(p.velocitySelection().reject(), 0); EXPECT_EQ(p.velocitySelection().effectiveMode(), 0);
	p.configureVelocityControl(2, 0, false);
	EXPECT_TRUE(p.velocitySelection().reject() & VelocityControlSelector::ModeUnimplemented);
	EXPECT_EQ(p.velocitySelection().effectiveMode(), 0);
}
