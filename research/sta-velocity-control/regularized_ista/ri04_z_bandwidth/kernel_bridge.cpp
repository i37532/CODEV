// SPDX-License-Identifier: BSD-3-Clause
// Offline bridge only: unchanged production cores, no module or actuator path.
#include "RegularizedIstaVelocityControl.hpp"
#include "RegularizedStaVelocityControl.hpp"
#include <limits>

namespace {
struct Handle {
	int mode;
	RegularizedStaVelocityControl sta;
	RegularizedIstaVelocityControl ista;
	RegularizedStaVelocityControl::Candidate sta_candidate;
	RegularizedIstaVelocityControl::Candidate ista_candidate;
	explicit Handle(int value) : mode(value) {}
};
}
extern "C" {
void *band_create(int mode) { return (mode == 0 || mode == 1) ? new Handle(mode) : nullptr; }
void band_destroy(void *opaque) { delete static_cast<Handle *>(opaque); }
int band_configure(void *opaque, float l1, float l2, float epsilon)
{
	auto &h = *static_cast<Handle *>(opaque);
	return h.mode ? h.ista.setParameters(2, {l1, l2, epsilon}) : h.sta.setParameters(2, {l1, l2, epsilon});
}
int band_reset(void *opaque, float nu)
{
	auto &h = *static_cast<Handle *>(opaque);
	return h.mode ? h.ista.reset(2, nu) : h.sta.reset(2, nu);
}
int band_evaluate(void *opaque, float velocity, float target, float dt, double *out)
{
	auto &h = *static_cast<Handle *>(opaque);
	if (h.mode) {
		h.ista_candidate = h.ista.evaluate(2, velocity, target, dt);
		const auto &c = h.ista_candidate;
		out[0] = c.s; out[1] = c.p; out[2] = c.a_sta; out[3] = c.nu_before; out[4] = c.nu_next;
		return static_cast<int>(c.status);
	}
	h.sta_candidate = h.sta.evaluate(2, velocity, target, dt);
	const auto &c = h.sta_candidate;
	out[0] = c.s; out[1] = std::numeric_limits<double>::quiet_NaN();
	out[2] = c.a_sta; out[3] = c.nu_before; out[4] = c.nu_next;
	return static_cast<int>(c.status);
}
int band_commit(void *opaque, float applied_nu)
{
	auto &h = *static_cast<Handle *>(opaque);
	return h.mode ? static_cast<int>(h.ista.commitProtected(h.ista_candidate, applied_nu))
	       : static_cast<int>(h.sta.commitProtected(h.sta_candidate, applied_nu));
}
float band_state(void *opaque)
{
	auto &h = *static_cast<Handle *>(opaque);
	return h.mode ? h.ista.state()[2] : h.sta.state()[2];
}
}
