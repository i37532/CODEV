// SPDX-License-Identifier: BSD-3-Clause
// RI01 offline bridge only: no module registration and no actuator path.
#include "RegularizedIstaVelocityControl.hpp"
#include <array>
#include <cstddef>

namespace {
using Core = RegularizedIstaVelocityControl;
struct Handle {
	Core core;
	std::array<Core::Candidate, 3> candidates{};
};
}

extern "C" {
void *ri01_create() { return new Handle; }
void ri01_destroy(void *opaque) { delete static_cast<Handle *>(opaque); }
int ri01_configure(void *opaque, int axis, float k1, float k2, float eps)
{
	return static_cast<Handle *>(opaque)->core.setParameters(static_cast<size_t>(axis), {k1, k2, eps}) ? 1 : 0;
}
int ri01_reset(void *opaque, int axis, float nu)
{
	return static_cast<Handle *>(opaque)->core.reset(static_cast<size_t>(axis), nu) ? 1 : 0;
}
int ri01_evaluate(void *opaque, int axis, float v, float vsp, float h, double *out)
{
	auto &handle = *static_cast<Handle *>(opaque);
	auto c = handle.core.evaluate(static_cast<size_t>(axis), v, vsp, h);
	if (axis >= 0 && axis < 3) { handle.candidates[axis] = c; }
	out[0] = c.s; out[1] = c.p; out[2] = c.psi; out[3] = c.rho;
	out[4] = c.a_sta; out[5] = c.nu_before; out[6] = c.nu_next; out[7] = c.dt;
	return static_cast<int>(c.status);
}
int ri01_commit(void *opaque, int axis, int protect, float applied_nu)
{
	auto &handle = *static_cast<Handle *>(opaque);
	if (axis < 0 || axis >= 3) { return -1; }
	return static_cast<int>(protect ? handle.core.commitProtected(handle.candidates[axis], applied_nu)
			       : handle.core.commit(handle.candidates[axis]));
}
float ri01_state(void *opaque, int axis)
{
	return static_cast<Handle *>(opaque)->core.state()[axis];
}
}
