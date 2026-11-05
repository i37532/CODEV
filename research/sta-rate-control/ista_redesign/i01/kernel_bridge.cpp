// SPDX-License-Identifier: BSD-3-Clause
// Offline C ABI: calls the actual new C++ kernel, no copied control formula.
#include "ProperIstaRateControl.hpp"
namespace { ProperIstaRateControl controller; }
extern "C" int proper_step(unsigned axis, float rate, float sp, float h,
		float l1, float l2, float g, int reset, float nu, double *out)
{
	if (axis >= 3 || !out) { return -1; }
	if (!controller.setParameters(axis, {l1, l2, g}) || (reset && !controller.reset(axis, nu))) { return -2; }
	out[0] = controller.state()[axis];
	const auto candidate = controller.evaluate(axis, rate, sp, h);
	const auto &r = candidate.result();
	out[1] = r.s; out[2] = r.a; out[3] = r.c_raw; out[4] = r.nu_next;
	out[5] = r.virtual_s; out[6] = r.xi; out[7] = static_cast<int>(r.branch);
	if (r.valid() && !controller.commit(candidate)) { return -3; }
	out[8] = controller.state()[axis];
	return static_cast<int>(r.status);
}
