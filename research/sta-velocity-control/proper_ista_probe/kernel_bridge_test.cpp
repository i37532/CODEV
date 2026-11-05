// SPDX-License-Identifier: BSD-3-Clause
// Standalone named tests for the research C ABI, linked to the actual cores.
#include "RegularizedStaVelocityControl.hpp"
#include "RegularizedIstaVelocityControl.hpp"
#include "ProperIstaRateControl.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

extern "C" {
void *probe_create(int algorithm);
void probe_destroy(void *opaque);
int probe_configure(void *opaque, int axis, float l1, float l2, float eps);
int probe_reset(void *opaque, int axis, float nu);
int probe_evaluate(void *opaque, int axis, float velocity, float target, float dt, double *out);
int probe_commit(void *opaque, int axis);
int probe_commit_protected(void *opaque, int axis, float applied_nu);
float probe_state(void *opaque, int axis);
}

namespace {
constexpr float l1 = 2.f;
constexpr float l2 = 3.f;
constexpr float dt = .02f;
constexpr float quiet_nan = std::numeric_limits<float>::quiet_NaN();
constexpr float inf = std::numeric_limits<float>::infinity();
using Output = std::array<double, 7>;

void require(bool condition, const std::string &message)
{
	if (!condition) { throw std::runtime_error(message); }
}

void close(double actual, double expected, const std::string &message, double tolerance = 3e-6)
{
	require(std::isfinite(actual) && std::isfinite(expected)
		&& std::fabs(actual - expected) <= tolerance * std::max({1., std::fabs(actual), std::fabs(expected)}),
		message + " (actual=" + std::to_string(actual) + ", expected=" + std::to_string(expected) + ")");
}

void invalidOutput(const Output &out)
{
	for (size_t i = 0; i < 6; ++i) { require(std::isnan(out[i]), "failed output must be NaN"); }
	require(out[6] == -1., "failed branch must be -1");
}

struct Probe {
	explicit Probe(int value, bool configure = true) : algorithm(value), handle(probe_create(value))
	{
		require(handle != nullptr, "create valid algorithm");
		if (configure) {
			for (int axis = 0; axis < 3; ++axis) { require(config(axis) == 1, "configure axis"); }
		}
	}
	~Probe() { probe_destroy(handle); }
	Probe(const Probe &) = delete;
	Probe &operator=(const Probe &) = delete;
	float epsilon() const { return algorithm == 2 ? 0.f : .1f; }
	int config(int axis) { return probe_configure(handle, axis, l1, l2, epsilon()); }
	Output eval(int axis = 0, float velocity = 1.f, float target = 0.f, float step = dt)
	{
		Output out{};
		require(probe_evaluate(handle, axis, velocity, target, step, out.data()) == 0, "evaluate succeeds");
		return out;
	}
	int algorithm;
	void *handle;
};

struct Tests {
	int count{0};
	int failures{0};
	void run(const std::string &name, const std::function<void()> &test)
	{
		++count;
		try {
			test();
			std::cout << "PASS " << name << '\n';
		} catch (const std::exception &error) {
			++failures;
			std::cerr << "FAIL " << name << ": " << error.what() << '\n';
		}
	}
};

void directCoreParity(int algorithm)
{
	Probe probe(algorithm);
	RegularizedStaVelocityControl rsta;
	RegularizedIstaVelocityControl rista;
	ProperIstaRateControl proper;
	require(rsta.setParameters(1, {l1, l2, .1f}), "direct RSTA parameters");
	require(rista.setParameters(1, {l1, l2, .1f}), "direct RISTA parameters");
	require(proper.setParameters(1, {l1, l2, 1.f}), "direct Proper parameters");
	for (float velocity : {2.f, .03f, 0.f, -.0004f, -.03f, -2.f}) {
		require(probe_reset(probe.handle, 1, .37f), "bridge reset");
		require(rsta.reset(1, .37f) && rista.reset(1, .37f) && proper.reset(1, .37f), "direct reset");
		const Output out = probe.eval(1, velocity);
		Output expected{};
		if (algorithm == 0) {
			const auto c = rsta.evaluate(1, velocity, 0.f, dt);
			require(c.valid(), "direct RSTA valid");
			expected = {{c.s, std::numeric_limits<double>::quiet_NaN(), c.a_sta, c.nu_before,
				c.nu_next, RegularizedStaVelocityControl::nonlinear(c.s, .1f).rho, -1.}};
			require(rsta.commit(c) == RegularizedStaVelocityControl::Status::Ok, "direct RSTA commit");
		} else if (algorithm == 1) {
			const auto c = rista.evaluate(1, velocity, 0.f, dt);
			require(c.valid(), "direct RISTA valid");
			expected = {{c.s, c.p, c.a_sta, c.nu_before, c.nu_next, c.rho, static_cast<double>(c.branch)}};
			require(rista.commit(c) == RegularizedIstaVelocityControl::Status::Ok, "direct RISTA commit");
		} else {
			const auto c = proper.evaluate(1, velocity, 0.f, dt);
			const auto &r = c.result();
			require(r.valid(), "direct Proper valid");
			expected = {{r.s, r.virtual_s, r.a, .37f, r.nu_next, r.xi, static_cast<double>(r.branch)}};
			close(r.a, r.c_raw, "g=1 algebraic identity", 0.);
			require(proper.commit(c), "direct Proper commit");
		}
		for (size_t i = 0; i < out.size(); ++i) {
			if (std::isnan(expected[i])) { require(std::isnan(out[i]), "RSTA p is unavailable"); }
			else { close(out[i], expected[i], "direct field parity " + std::to_string(i), 0.); }
		}
		require(probe_commit(probe.handle, 1), "bridge strict commit");
		const float direct = algorithm == 0 ? rsta.state()[1] : algorithm == 1 ? rista.state()[1] : proper.state()[1];
		close(probe_state(probe.handle, 1), direct, "direct state parity", 0.);
	}
}
}

int main()
{
	Tests tests;
	tests.run("creation_rejects_unknown_algorithms", [] {
		for (int algorithm : {-1, 3, 100}) { require(probe_create(algorithm) == nullptr, "invalid mode"); }
		probe_destroy(nullptr);
	});
	tests.run("null_handle_api", [] {
		Output out{};
		require(!probe_configure(nullptr, 0, l1, l2, .1f), "null configure");
		require(!probe_reset(nullptr, 0, 0.f), "null reset");
		require(probe_evaluate(nullptr, 0, 1.f, 0.f, dt, out.data()) != 0, "null evaluate");
		invalidOutput(out);
		require(probe_evaluate(nullptr, 0, 1.f, 0.f, dt, nullptr) != 0, "null evaluate/output");
		require(!probe_commit(nullptr, 0), "null commit");
		require(!probe_commit_protected(nullptr, 0, 0.f), "null protected commit");
		require(std::isnan(probe_state(nullptr, 0)), "null state");
	});
	const char *names[] = {"RSTA", "RISTA", "Proper"};
	for (int algorithm = 0; algorithm < 3; ++algorithm) {
		const auto run = [&](const std::string &name, const std::function<void()> &test) {
			tests.run(std::string(names[algorithm]) + "/" + name, test);
		};
		run("unconfigured_and_no_candidate", [=] {
			Probe p(algorithm, false);
			Output out{};
			require(probe_evaluate(p.handle, 0, 1.f, 0.f, dt, out.data()) == 2, "unconfigured status");
			invalidOutput(out);
			require(!probe_commit(p.handle, 0) && !probe_commit_protected(p.handle, 0, 0.f), "no candidate");
			close(probe_state(p.handle, 0), 0., "initial state");
		});
		run("parameter_validation", [=] {
			Probe p(algorithm);
			for (float invalid : {0.f, -1.f, quiet_nan, inf, std::numeric_limits<float>::denorm_min()}) {
				require(!probe_configure(p.handle, 0, invalid, l2, p.epsilon()), "reject lambda1");
				require(!probe_configure(p.handle, 0, l1, invalid, p.epsilon()), "reject lambda2");
			}
			for (float invalid : {-1.f, quiet_nan, inf, 2.f}) {
				require(!probe_configure(p.handle, 0, l1, l2, invalid), "reject epsilon");
			}
			if (algorithm == 2) {
				for (float invalid : {.001f, .1f, std::numeric_limits<float>::denorm_min()}) {
					require(!probe_configure(p.handle, 0, l1, l2, invalid), "Proper requires exact zero epsilon");
				}
			} else {
				require(!probe_configure(p.handle, 0, l1, l2, 0.f), "regularized needs positive epsilon");
				require(probe_configure(p.handle, 0, l1, l2, .001f), "minimum epsilon");
				require(probe_configure(p.handle, 0, l1, l2, 1.f), "maximum epsilon");
			}
		});
		for (float error : {1.f, -1.f, 0.f}) {
			run("error_" + std::to_string(error), [=] {
				Probe p(algorithm);
				const auto out = p.eval(0, error + .5f, .5f);
				close(out[0], error, "error convention v-target");
				close(probe_state(p.handle, 0), 0., "evaluate cannot change state");
				close(out[3], 0., "old state");
				if (error == 0.f) { close(out[2], 0., "zero correction"); close(out[4], 0., "zero update"); }
				else { require(out[2] * error < 0. && out[4] * error < 0., "negative feedback"); }
				require(probe_commit(p.handle, 0), "strict commit");
				close(probe_state(p.handle, 0), out[4], "candidate state applied", 0.);
			});
		}
		run("nonzero_nu_translation", [=] {
			Probe p(algorithm);
			for (float error : {1.f, -.03f, 0.f}) {
				require(probe_reset(p.handle, 0, 0.f), "reset zero");
				const auto base = p.eval(0, error);
				require(probe_reset(p.handle, 0, .7f), "reset nonzero");
				const auto shifted = p.eval(0, error);
				close(shifted[2] - base[2], .7f, "acceleration shifts with old nu");
				close(shifted[4] - base[4], .7f, "next state shifts with old nu");
				close(shifted[3], .7f, "reported old nu");
				close(shifted[5], base[5], "rho/xi independent of old nu");
				if (algorithm != 0) { close(shifted[1], base[1], "implicit residual independent of old nu"); }
			}
		});
		run("per_axis_candidates_and_state_isolation", [=] {
			Probe p(algorithm);
			std::array<Output, 3> out{};
			for (int axis = 0; axis < 3; ++axis) {
				require(probe_reset(p.handle, axis, .2f * axis), "seed axis");
				out[axis] = p.eval(axis, float(axis + 1));
			}
			for (int axis : {2, 0, 1}) {
				require(probe_commit(p.handle, axis), "all outstanding axis candidates commit");
				close(probe_state(p.handle, axis), out[axis][4], "correct axis state", 0.);
			}
			for (int axis = 0; axis < 3; ++axis) { close(probe_state(p.handle, axis), out[axis][4], "other states retained", 0.); }
		});
		run("reset_invalidates_selected_axis_only", [=] {
			Probe p(algorithm);
			p.eval(0); const auto other = p.eval(1);
			require(probe_reset(p.handle, 0, .4f), "reset selected axis");
			require(!probe_commit(p.handle, 0), "reset candidate stale");
			require(probe_commit(p.handle, 1), "other axis remains current");
			close(probe_state(p.handle, 0), .4f, "reset seed");
			close(probe_state(p.handle, 1), other[4], "other axis commit");
		});
		run("configure_preserves_nu_invalidates_selected_axis_only", [=] {
			Probe p(algorithm);
			require(probe_reset(p.handle, 0, .4f), "seed selected axis");
			p.eval(0); p.eval(1);
			require(p.config(0), "equal parameter update accepted");
			close(probe_state(p.handle, 0), .4f, "configure preserves nu");
			require(!probe_commit(p.handle, 0), "configuration candidate stale");
			require(probe_commit(p.handle, 1), "other axis candidate remains current");
		});
		run("latest_candidate_replaces_previous", [=] {
			Probe p(algorithm);
			const auto first = p.eval(0, 1.f);
			const auto second = p.eval(0, -1.f);
			require(first[4] != second[4], "different candidate states");
			require(probe_commit(p.handle, 0), "latest candidate commit");
			close(probe_state(p.handle, 0), second[4], "latest candidate selected", 0.);
		});
		run("repeated_commit_rejected", [=] {
			Probe p(algorithm);
			const auto out = p.eval();
			require(probe_commit(p.handle, 0), "initial commit");
			require(!probe_commit(p.handle, 0), "repeat strict rejected");
			require(!probe_commit_protected(p.handle, 0, .9f), "repeat protected rejected");
			close(probe_state(p.handle, 0), out[4], "repeat cannot alter state", 0.);
		});
		for (const std::string kind : {"velocity", "target", "dt"}) {
			run("failed_evaluation_discards_candidate_" + kind, [=] {
				Probe p(algorithm);
				for (float invalid : {quiet_nan, inf, -inf}) {
					p.eval();
					Output out{};
					const int status = probe_evaluate(p.handle, 0, kind == "velocity" ? invalid : 1.f,
						kind == "target" ? invalid : 0.f, kind == "dt" ? invalid : dt, out.data());
					require(status == (kind == "dt" ? 4 : 3), "original input error status");
					invalidOutput(out);
					require(!probe_commit(p.handle, 0), "failed evaluation removes strict candidate");
					require(!probe_commit_protected(p.handle, 0, .8f), "failed evaluation removes protected candidate");
					close(probe_state(p.handle, 0), 0., "failure preserves state");
				}
			});
		}
		run("nonpositive_or_subnormal_dt_rejected", [=] {
			Probe p(algorithm);
			for (float invalid : {0.f, -dt, std::numeric_limits<float>::denorm_min()}) {
				p.eval();
				Output out{};
				require(probe_evaluate(p.handle, 0, 1.f, 0.f, invalid, out.data()) == 4, "invalid dt status");
				invalidOutput(out);
				require(!probe_commit(p.handle, 0), "invalid dt discards candidate");
			}
		});
		run("numerical_failure_discards_candidate", [=] {
			Probe p(algorithm);
			p.eval();
			Output out{};
			const float maximum = std::numeric_limits<float>::max();
			require(probe_evaluate(p.handle, 0, maximum, -maximum, dt, out.data()) == 5, "overflow numerical status");
			invalidOutput(out);
			require(!probe_commit(p.handle, 0), "overflow discards candidate");
		});
		run("null_output_discards_selected_candidate", [=] {
			Probe p(algorithm);
			p.eval(0); p.eval(1);
			require(probe_evaluate(p.handle, 0, 1.f, 0.f, dt, nullptr) != 0, "null output rejected");
			require(!probe_commit(p.handle, 0), "null output discards selected candidate");
			require(probe_commit(p.handle, 1), "null output preserves other axis candidate");
		});
		run("invalid_axis_api", [=] {
			Probe p(algorithm);
			for (int axis : {-1, 3, std::numeric_limits<int>::max()}) {
				require(!p.config(axis), "invalid configure axis");
				require(!probe_reset(p.handle, axis, 0.f), "invalid reset axis");
				require(!probe_commit(p.handle, axis), "invalid commit axis");
				require(!probe_commit_protected(p.handle, axis, 0.f), "invalid protected axis");
				require(std::isnan(probe_state(p.handle, axis)), "invalid state axis");
				for (int valid_axis = 0; valid_axis < 3; ++valid_axis) { p.eval(valid_axis); }
				Output out{};
				require(probe_evaluate(p.handle, axis, 1.f, 0.f, dt, out.data()) == 1, "invalid evaluation axis");
				invalidOutput(out);
				for (int valid_axis = 0; valid_axis < 3; ++valid_axis) {
					require(!probe_commit(p.handle, valid_axis), "invalid axis discards outstanding candidates");
					close(probe_state(p.handle, valid_axis), 0., "invalid axis preserves state");
				}
			}
		});
		run("strict_and_protected_state_semantics", [=] {
			Probe strict(algorithm), protected_probe(algorithm);
			const auto ideal = strict.eval();
			const auto constrained = protected_probe.eval();
			for (size_t i = 0; i < ideal.size(); ++i) {
				if (std::isnan(ideal[i])) { require(std::isnan(constrained[i]), "identical unavailable output"); }
				else { close(ideal[i], constrained[i], "same ideal evaluation", 0.); }
			}
			require(probe_commit(strict.handle, 0), "strict commit accepted");
			require(probe_commit_protected(protected_probe.handle, 0, .25f), "protected commit accepted");
			close(probe_state(strict.handle, 0), ideal[4], "strict follows nu_next", 0.);
			close(probe_state(protected_probe.handle, 0), .25f, "protected follows supplied state", 0.);
			require(!probe_commit(protected_probe.handle, 0), "protected consumes candidate once");
			const auto next = protected_probe.eval();
			close(next[3], .25f, "next evaluation sees applied state", 0.);
			close(next[2] - constrained[2], .25f, "applied state affects subsequent ideal output");
		});
		run("invalid_protected_commit_preserves_candidate", [=] {
			Probe p(algorithm);
			const auto out = p.eval();
			for (float invalid : {quiet_nan, inf, -inf}) {
				require(!probe_commit_protected(p.handle, 0, invalid), "nonfinite protected state rejected");
				close(probe_state(p.handle, 0), 0., "failed protected commit cannot mutate state");
			}
			require(probe_commit(p.handle, 0), "valid candidate can retry after failed protected state");
			close(probe_state(p.handle, 0), out[4], "retry applies ideal state", 0.);
		});
		run("invalid_configuration_or_reset_preserves_candidate", [=] {
			Probe p(algorithm);
			const auto out = p.eval();
			require(!probe_configure(p.handle, 0, -l1, l2, p.epsilon()), "invalid configuration rejected");
			require(!probe_reset(p.handle, 0, quiet_nan), "invalid reset rejected");
			require(probe_commit(p.handle, 0), "invalid parameter/reset does not stale candidate");
			close(probe_state(p.handle, 0), out[4], "candidate retained", 0.);
		});
		run("separate_handle_ownership", [=] {
			Probe first(algorithm), second(algorithm);
			const auto out = first.eval();
			require(!probe_commit(second.handle, 0), "second handle has no first-handle candidate");
			second.eval(0, -1.f);
			require(probe_reset(second.handle, 0, .4f), "reset independent handle");
			require(probe_commit(first.handle, 0), "other handle cannot invalidate candidate");
			close(probe_state(first.handle, 0), out[4], "first handle state", 0.);
			close(probe_state(second.handle, 0), .4f, "second handle state");
		});
		run("actual_core_output_and_commit_parity", [=] { directCoreParity(algorithm); });
	}
	tests.run("Proper_sliding_branch_and_virtual_identity", [] {
		Probe p(2);
		for (float s : {-.0006f, 0.f, .0006f, -.5f, .5f}) {
			require(probe_reset(p.handle, 0, .2f), "nonzero seed");
			const auto out = p.eval(0, s);
			close(out[1], out[0] + dt * (out[2] - out[4]), "virtual_s compensated identity");
			close(out[4], .2f - dt * l2 * out[5], "xi state update");
			if (std::fabs(s) < .001f) {
				close(out[1], 0., "sliding virtual_s");
				close(out[6], 2., "sliding branch");
				close(out[2], .2f - 2.f * s / dt, "sliding correction");
			} else { close(out[6], s > 0.f ? 1. : 3., "signed outer branch"); }
		}
	});
	std::cout << "Tests run: " << tests.count << ", passed: " << tests.count - tests.failures
		<< ", failed: " << tests.failures << '\n';
	return tests.failures == 0 ? 0 : 1;
}
