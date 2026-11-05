// SPDX-License-Identifier: BSD-3-Clause
// Offline probe of the real header, NOT a replacement controller or simulator.
#include "VelocityDiagnosticExcitation.hpp"
#include <cstdio>
#include <cmath>

namespace
{
int tests = 0;
int failures = 0;

void check(const char *name, bool pass, unsigned fault)
{
	++tests;
	if (!pass) { ++failures; }
	std::printf("%s %s fault=%u\n", pass ? "PASS" : "FAIL", name, fault);
}

struct Timeline {
	VelocityDiagnosticExcitation excitation;
	uint64_t sample{1000000};
	float peak{0.f};
	Timeline()
	{
		excitation.update(sample, false, false);
		sample += 10000;
		excitation.update(sample, true, true);
		// 60 s valid airborne AUTO_LOITER, including the complete 12+32 s wave.
		for (int i = 0; i < 6000; ++i) {
			sample += 10000;
			peak = std::fmax(peak, std::fabs(excitation.update(sample, true, true)));
		}
	}
};
}

int main()
{
	{
		Timeline t;
		check("CompleteObservationBeforeLanding", t.peak > 0.1f
		      && t.excitation.time() == 48.f && t.excitation.fault() == 0,
		      t.excitation.fault());
	}
	{
		Timeline t;
		// Run's gate explicitly requires AUTO_LOITER. AUTO_LAND is a false gate
		// while still armed, even though the waveform has completely finished.
		const float output = t.excitation.update(t.sample + 10000, true, false);
		std::printf("NOMINAL_LANDING time=%.3f output=%.3f fault=%u (Gate=2)\n",
			    static_cast<double>(t.excitation.time()), static_cast<double>(output),
			    static_cast<unsigned>(t.excitation.fault()));
		// Intentionally tests the frozen protocol02 whole-armed zero rule.
		// Expected to fail: preserve this result, don't change zero to two here.
		check("FrozenProtocolAllowsNominalLanding", output == 0.f && t.excitation.fault() == 0,
		      t.excitation.fault());
	}
	{
		VelocityDiagnosticExcitation e;
		e.update(1000000, true, true);
		const float output = e.update(1010000, true, false);
		e.update(1020000, true, true);
		check("EarlyGateLossStillLatched", output == 0.f
		      && e.fault() == VelocityDiagnosticExcitation::Gate, e.fault());
	}
	{
		Timeline t;
		t.excitation.update(t.sample, true, false); // real duplicate timestamp
		check("ClockFaultNotHiddenByLanding", t.excitation.fault()
		      == (VelocityDiagnosticExcitation::Clock | VelocityDiagnosticExcitation::Gate),
		      t.excitation.fault());
	}
	{
		Timeline t;
		t.excitation.abort(); // real controller failure must stay visible
		t.excitation.update(t.sample + 10000, true, false);
		check("ControllerFaultNotHiddenByLanding", t.excitation.fault()
		      == (VelocityDiagnosticExcitation::Controller | VelocityDiagnosticExcitation::Gate),
		      t.excitation.fault());
	}
	{
		Timeline t;
		t.excitation.update(t.sample + 10000, true, false);
		t.excitation.update(t.sample + 20000, false, false);
		check("DisarmClearsLatch", t.excitation.fault() == 0 && t.excitation.time() == -1.f,
		      t.excitation.fault());
	}

	std::printf("SUMMARY tests=%d passed=%d failed=%d\n", tests, tests - failures, failures);
	return failures ? 1 : 0;
}
