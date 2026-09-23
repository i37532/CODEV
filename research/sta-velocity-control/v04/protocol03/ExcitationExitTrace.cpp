// SPDX-License-Identifier: BSD-3-Clause
// Trace the production header, classified independently by Python protocol gates.
#include "VelocityDiagnosticExcitation.hpp"
#include <cstdio>
int main()
{
	VelocityDiagnosticExcitation e;
	uint64_t t = 1000000;
	e.update(t, true, true);
	for (int i = 0; i < 6000; ++i) { t += 10000; e.update(t, true, true); }
	float output = e.update(t + 10000, true, false);
	std::printf("landing %u %.9g\n", unsigned(e.fault()), double(output));
	output = e.update(t + 10000, true, false);
	std::printf("duplicate %u %.9g\n", unsigned(e.fault()), double(output));
	output = e.update(t + 20000, false, false);
	std::printf("disarm %u %.9g\n", unsigned(e.fault()), double(output));
	e.update(t + 30000, true, true);
	e.abort();
	output = e.update(t + 40000, true, false);
	std::printf("controller %u %.9g\n", unsigned(e.fault()), double(output));
}
