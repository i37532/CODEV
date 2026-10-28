// PV01 research ABI, not linked to firmware. Constraint import is a scalar
// diagnostic only: commit ideal state, then explicit reset of external state.
// It is NOT a production protection adapter or a strict implicit solution.
#include "ProperIstaVelocityControl.hpp"
#include <array>
#include <new>
using Core = ProperIstaVelocityControl;
struct Handle { Core core; std::array<Core::Candidate, 3> candidate{}; };
extern "C" {
void *probe_create(int mode) { return mode == 2 ? new (std::nothrow) Handle : nullptr; }
void probe_destroy(void *p) { delete static_cast<Handle *>(p); }
int probe_configure(void *p, int axis, float l1, float l2, float epsilon)
{
	return p && epsilon == 0.f && static_cast<Handle *>(p)->core.setParameters(axis, {l1, l2});
}
int probe_reset(void *p, int axis, float nu) { return p && static_cast<Handle *>(p)->core.reset(axis, nu); }
int probe_evaluate(void *p, int axis, float v, float sp, float h, double *out)
{
	if (!p || !out || axis < 0 || axis > 2) { return 255; }
	auto &self = *static_cast<Handle *>(p);
	auto &c = self.candidate[axis]; c = self.core.evaluate(axis, v, sp, h);
	out[0] = c.s; out[1] = c.virtual_s; out[2] = c.a_sta;
	out[3] = c.nu_before; out[4] = c.nu_next; out[5] = c.xi;
	out[6] = static_cast<int>(c.branch);
	return static_cast<int>(c.status);
}
int probe_commit(void *p, int axis)
{
	if (!p || axis < 0 || axis > 2) { return 0; }
	auto &self = *static_cast<Handle *>(p);
	return self.core.commit(self.candidate[axis]) == Core::Status::Ok;
}
int probe_commit_protected(void *p, int axis, float imported)
{
	if (!probe_commit(p, axis)) { return 0; }
	return static_cast<Handle *>(p)->core.reset(axis, imported);
}
float probe_state(void *p, int axis) { return static_cast<Handle *>(p)->core.state().at(axis); }
}
