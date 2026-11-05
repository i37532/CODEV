// SPDX-License-Identifier: BSD-3-Clause
// Offline C ABI only. Calls unchanged production kernels; no PX4 transport.
#include "IstaRateControl.hpp"

namespace {
StaRateControl esta;
IstaRateControl ista;
}

extern "C" int audit_step(int mode, unsigned axis, float rate, float sp, float h,
		float l1, float l2, float g, int reset, float nu, double *out)
{
	if (axis >= 3 || (mode != 1 && mode != 2) || !out) { return -1; }
	const StaRateControl::Parameters p{l1, l2, g};
	if (mode == 1) {
		if (!esta.setParameters(axis, p) || (reset && !esta.reset(axis, nu))) { return -2; }
		out[0] = static_cast<double>(esta.state()[axis]);
		const auto r = esta.update(axis, rate, sp, h);
		out[1] = r.s; out[2] = r.a; out[3] = r.c_raw; out[4] = r.nu_next;
		out[5] = 0.0; out[6] = 0.0; out[7] = 0.0; // not applicable to ESTA
		out[8] = esta.state()[axis];
		return static_cast<int>(r.status);
	}
	if (!ista.setParameters(axis, p) || (reset && !ista.reset(axis, nu))) { return -2; }
	out[0] = static_cast<double>(ista.state()[axis]);
	const auto r = ista.update(axis, rate, sp, h);
	out[1] = r.s; out[2] = r.a; out[3] = r.c_raw; out[4] = r.nu_next;
	out[5] = r.virtual_s; out[6] = r.xi; out[7] = static_cast<int>(r.branch);
	out[8] = ista.state()[axis];
	return static_cast<int>(r.status);
}
