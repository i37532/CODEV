// SPDX-License-Identifier: BSD-3-Clause
// Research-only C ABI. Link the unchanged production kernels; no flight path.
#include "RegularizedStaVelocityControl.hpp"
#include "RegularizedIstaVelocityControl.hpp"
#include "ProperIstaRateControl.hpp"

#include <array>
#include <limits>
#include <new>

namespace {
constexpr int invalid_axis = 1;
constexpr int invalid_input = 4;
constexpr double nan = std::numeric_limits<double>::quiet_NaN();

struct Handle {
	explicit Handle(int value) : algorithm(value) {}
	const int algorithm;
	RegularizedStaVelocityControl rsta;
	RegularizedIstaVelocityControl rista;
	ProperIstaRateControl proper;
	std::array<RegularizedStaVelocityControl::Candidate, 3> rsta_candidates{};
	std::array<RegularizedIstaVelocityControl::Candidate, 3> rista_candidates{};
	std::array<ProperIstaRateControl::Candidate, 3> proper_candidates{};
	std::array<bool, 3> ready{};
	std::array<float, 3> epsilon{};
};

bool validAxis(int axis) { return axis >= 0 && axis < 3; }

void clearOutput(double *out)
{
	if (out) {
		for (int i = 0; i < 6; ++i) { out[i] = nan; }
		out[6] = -1.;
	}
}
}

extern "C" {
// 0 = regularized explicit STA; 1 = regularized ISTA; 2 = Proper ISTA.
// Handles and candidates are serial-use only, like the underlying kernels.
void *probe_create(int algorithm)
{
	return algorithm >= 0 && algorithm <= 2 ? new (std::nothrow) Handle(algorithm) : nullptr;
}

void probe_destroy(void *opaque) { delete static_cast<Handle *>(opaque); }

int probe_configure(void *opaque, int axis, float l1, float l2, float eps)
{
	if (!opaque || !validAxis(axis)) { return 0; }
	auto &h = *static_cast<Handle *>(opaque);
	bool ok = false;
	if (h.algorithm == 0) {
		ok = h.rsta.setParameters(axis, {l1, l2, eps});
	} else if (h.algorithm == 1) {
		ok = h.rista.setParameters(axis, {l1, l2, eps});
	} else {
		// Strict offline scalar reinterpretation: s [m/s], a/nu [m/s^2].
		// g=1 only makes c_raw=a algebraically inside the unchanged rate core.
		// It is NOT a physical velocity/actuator unit-response assumption or
		// calibration. No feedforward, thrust, protection policy or flight use.
		if (eps != 0.f) { return 0; }
		ok = h.proper.setParameters(axis, {l1, l2, 1.f});
	}
	if (ok) {
		h.epsilon[axis] = eps;
		h.ready[axis] = false;
	}
	return ok ? 1 : 0;
}

int probe_reset(void *opaque, int axis, float nu)
{
	if (!opaque || !validAxis(axis)) { return 0; }
	auto &h = *static_cast<Handle *>(opaque);
	const bool ok = h.algorithm == 0 ? h.rsta.reset(axis, nu)
		: h.algorithm == 1 ? h.rista.reset(axis, nu) : h.proper.reset(axis, nu);
	if (ok) { h.ready[axis] = false; }
	return ok ? 1 : 0;
}

// Caller supplies seven doubles: [s, p, a, nu_before, nu_next, rho/xi, branch].
// RSTA: p=NaN, branch=-1, rho from the core's unchanged nonlinear() helper.
// RISTA: p is the implicit residual, branch 0=Inner/1=Outer.
// Proper: p is virtual_s (not next physical velocity), branch
// 1=Positive/2=Sliding/3=Negative. No feedforward is added to any output.
// Return 0 on success; 1..5 are original core status values. A bad handle or
// output pointer returns bridge error 4 (not an algorithm input-status claim).
// Invalid output fields are NaN/-1.
// A failed evaluation clears the selected candidate; an invalid axis clears
// all candidates on this handle, because no selected axis can be identified.
int probe_evaluate(void *opaque, int axis, float velocity, float target, float dt, double *out)
{
	clearOutput(out);
	if (!opaque) { return invalid_input; }
	auto &h = *static_cast<Handle *>(opaque);
	if (!validAxis(axis)) {
		h.ready.fill(false);
		return invalid_axis;
	}
	h.ready[axis] = false;
	if (!out) { return invalid_input; }
	if (h.algorithm == 0) {
		h.rsta_candidates[axis] = h.rsta.evaluate(axis, velocity, target, dt);
		const auto &c = h.rsta_candidates[axis];
		if (!c.valid()) { return static_cast<int>(c.status); }
		out[0] = c.s;
		out[2] = c.a_sta;
		out[3] = c.nu_before;
		out[4] = c.nu_next;
		out[5] = RegularizedStaVelocityControl::nonlinear(c.s, h.epsilon[axis]).rho;
	} else if (h.algorithm == 1) {
		h.rista_candidates[axis] = h.rista.evaluate(axis, velocity, target, dt);
		const auto &c = h.rista_candidates[axis];
		if (!c.valid()) { return static_cast<int>(c.status); }
		out[0] = c.s;
		out[1] = c.p;
		out[2] = c.a_sta;
		out[3] = c.nu_before;
		out[4] = c.nu_next;
		out[5] = c.rho;
		out[6] = static_cast<int>(c.branch);
	} else {
		const float nu_before = h.proper.state()[axis];
		h.proper_candidates[axis] = h.proper.evaluate(axis, velocity, target, dt);
		const auto &r = h.proper_candidates[axis].result();
		if (!r.valid()) { return static_cast<int>(r.status); }
		out[0] = r.s;
		out[1] = r.virtual_s;
		out[2] = r.a;
		out[3] = nu_before;
		out[4] = r.nu_next;
		out[5] = r.xi;
		out[6] = static_cast<int>(r.branch);
	}
	h.ready[axis] = true;
	return 0;
}

int probe_commit(void *opaque, int axis)
{
	if (!opaque || !validAxis(axis)) { return 0; }
	auto &h = *static_cast<Handle *>(opaque);
	if (!h.ready[axis]) { return 0; }
	const bool ok = h.algorithm == 0
		? h.rsta.commit(h.rsta_candidates[axis]) == RegularizedStaVelocityControl::Status::Ok
		: h.algorithm == 1
		? h.rista.commit(h.rista_candidates[axis]) == RegularizedIstaVelocityControl::Status::Ok
		: h.proper.commit(h.proper_candidates[axis]);
	if (ok) { h.ready[axis] = false; }
	return ok ? 1 : 0;
}

int probe_commit_protected(void *opaque, int axis, float applied_nu)
{
	if (!opaque || !validAxis(axis)) { return 0; }
	auto &h = *static_cast<Handle *>(opaque);
	if (!h.ready[axis]) { return 0; }
	const bool ok = h.algorithm == 0
		? h.rsta.commitProtected(h.rsta_candidates[axis], applied_nu) == RegularizedStaVelocityControl::Status::Ok
		: h.algorithm == 1
		? h.rista.commitProtected(h.rista_candidates[axis], applied_nu) == RegularizedIstaVelocityControl::Status::Ok
		: h.proper.commitProtected(h.proper_candidates[axis], applied_nu);
	if (ok) { h.ready[axis] = false; }
	return ok ? 1 : 0;
}

float probe_state(void *opaque, int axis)
{
	if (!opaque || !validAxis(axis)) { return std::numeric_limits<float>::quiet_NaN(); }
	const auto &h = *static_cast<Handle *>(opaque);
	return h.algorithm == 0 ? h.rsta.state()[axis]
		: h.algorithm == 1 ? h.rista.state()[axis] : h.proper.state()[axis];
}
}
