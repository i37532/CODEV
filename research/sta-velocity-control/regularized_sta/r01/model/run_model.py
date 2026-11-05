#!/usr/bin/env python3
"""Execute a predeclared finite offline matrix against actual C++ kernels."""
import argparse
from collections import Counter
import ctypes
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import tempfile
import traceback
import unittest

from model_reference import (GAINS, apply_proxy, disturbance_average, f32, matrix,
                             next_float, noise, numerical_terminal_eligible, plant_step, reference, target, TerminalClock)
from test_reference import ReferenceTests


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
KERNEL = REPO / "src/modules/mc_pos_control/PositionControl"


def digest(path):
    with path.open("rb") as handle:
        h = hashlib.sha256()
        for block in iter(lambda: handle.read(2**20), b""):
            h.update(block)
    return h.hexdigest()


class Kernel:
    evaluations = 0
    def __init__(self, lib, regularized, gains, initial=0.):
        self.lib, self.algorithm = lib, int(regularized)
        self.handle = lib.r01_create()
        self.out = (ctypes.c_float * 4)()
        assert self.handle
        assert lib.r01_config(self.handle, self.algorithm, gains["l1"], gains["l2"], gains["epsilon"]) == 1
        assert lib.r01_reset(self.handle, self.algorithm, initial) == 1

    def close(self):
        if self.handle:
            self.lib.r01_destroy(self.handle)
            self.handle = None

    def evaluate(self, v, sp, h):
        Kernel.evaluations += 1
        status = self.lib.r01_evaluate(self.handle, self.algorithm, v, sp, h, self.out)
        if status:
            raise AssertionError(f"Actual C++ evaluate status {status}: v={v} sp={sp} h={h}")
        return tuple(float(x) for x in self.out)

    def commit(self, applied):
        status = self.lib.r01_commit(self.handle, self.algorithm, applied)
        if status:
            raise AssertionError(f"Actual C++ commit status {status}")


def bind(path):
    lib = ctypes.CDLL(str(path))
    p, f, i = ctypes.c_void_p, ctypes.c_float, ctypes.c_int
    lib.r01_create.restype = p
    lib.r01_destroy.argtypes = [p]
    lib.r01_config.argtypes = [p, i, f, f, f]
    lib.r01_reset.argtypes = [p, i, f]
    lib.r01_evaluate.argtypes = [p, i, f, f, f, ctypes.POINTER(f)]
    lib.r01_commit.argtypes = [p, i, f]
    lib.r01_state.argtypes = [p, i]
    lib.r01_state.restype = f
    return lib


def actual_clock():
    from pyulog import ULog
    evidence = REPO / "research/sta-velocity-control/regularized_sta/r00/evidence/baseline_audit02.json"
    record = json.loads(evidence.read_text())["raw_log_samples"][0]
    path = Path(record["archive"])
    assert digest(path) == record["sha256"]
    events = {r["name"]: r["timestamp_us"] for r in json.loads((path.parent / "result.json").read_text())["events"]}
    ulog = ULog(str(path), ["sta_velocity_ctrl_status"])
    assert not ulog.dropouts and not getattr(ulog, "file_corruption", False)
    d = ulog.get_dataset("sta_velocity_ctrl_status").data
    samples = [int(sample) for sample, publication, elapsed in
               zip(d["timestamp_sample"], d["timestamp"], d["excitation_time"])
               if events["hover_start"] <= publication < events["hover_end"] and 0 <= elapsed < 64]
    intervals = [b-a for a, b in zip(samples, samples[1:])]
    assert len(intervals) == 6399 and set(intervals) == {8000, 12000}
    return intervals, dict(path=str(path), sha256=record["sha256"], samples=len(samples),
                           intervals_us=intervals, histogram=dict(Counter(intervals)),
                           sampling="Actual consecutive main-window timestamp_sample differences; not invented alternating timing")


def grid(lib):
    count, maximum = 0, 0.
    for gain_class in ("xy", "z"):
        for epsilon in (.001, .01, .02, 1.):
            gains = {k: f32(v) for k, v in dict(GAINS[gain_class], epsilon=epsilon).items()}
            eps = gains["epsilon"]
            positive = [eps/2, eps, next_float(eps, 0.), next_float(eps, math.inf), 10*eps]
            errors = [0.] + positive + [-x for x in positive]
            for error in errors:
                for nu in (-.2, 0., .2):
                    for h in (.002, .008, .012, .04):
                        for sp in (0., .375):
                            kernel = Kernel(lib, True, gains, nu)
                            try:
                                v, sp, h = f32(error+sp), f32(sp), f32(h)
                                s, a, old, candidate = kernel.evaluate(v, sp, h)
                                expected_s = f32(v-sp)
                                expected_a, expected_nu = reference(expected_s, f32(nu), h, gains, True)
                                differences = [abs(x-y)/(1+abs(y)) for x, y in
                                               [(s, expected_s), (a, expected_a), (candidate, expected_nu)]]
                                maximum = max(maximum, *differences)
                                assert max(differences) <= 2e-6, (gain_class, epsilon, error, nu, h, differences)
                                assert old == f32(nu)
                                kernel.commit(candidate)
                                count += 1
                            finally:
                                kernel.close()
    assert count == 2112
    return dict(cases=count, maximum_scaled_local_difference=maximum, threshold=2e-6,
                note="Inputs/parameters explicitly rounded to float first; production float subtraction mirrored only for interface representation")


def trajectory(lib, spec, intervals):
    regularized = spec["algorithm"] == "rsta"
    gains = {k: f32(v) for k, v in GAINS[spec["gain_class"]].items()}
    scenario, timing = spec["scenario"], spec["timing"]
    nu0 = {"zero": .05, "constant_positive": -.05, "constant_negative": .05}.get(scenario, 0.)
    initial_v = 0. if scenario == "infeasible" else .08
    actual = (initial_v, 0., 0.)
    double = actual
    double_nu = f32(nu0)
    kernel = Kernel(lib, regularized, gains, nu0)
    t, steps, local_error, trajectory_error, nu_peak, velocity_peak = 0., 0, 0., 0., 0., 0.
    weighted_e2 = weighted_m2 = weighted_e = elapsed = tv = 0.
    tail_sum = tail_e2 = tail_time = 0.
    limited_count = frozen_count = 0
    previous_correction = None
    terminal_hold = 0.
    terminal_clock = TerminalClock()
    early_terminal = False
    try:
        while t < 30.:
            h = intervals[steps] * 1e-6 if timing == "actual_log" else {"fixed_008": .008, "fixed_010": .01, "fixed_012": .012}[timing]
            target_v, ff = target(t, scenario)
            measurement_noise = noise(t, scenario)
            measurement = actual[0] + measurement_noise
            s, a, old, candidate = kernel.evaluate(measurement, target_v, h)
            represented_s = f32(f32(measurement)-f32(target_v))
            check_a, check_nu = reference(represented_s, old, f32(h), gains, regularized)
            local_error = max(local_error, abs(a-check_a)/(1+abs(check_a)),
                              abs(candidate-check_nu)/(1+abs(check_nu)), abs(s-represented_s)/(1+abs(represented_s)))
            assert local_error <= 2e-6, (spec, "local reference", local_error)
            total_limit = .2 if scenario == "infeasible" else 100.
            applied, next_nu, correction, limited, frozen = apply_proxy(a, old, candidate, ff, gains, total_limit)
            assert abs(next_nu) <= gains["nu_limit"] + 2e-7
            if not limited:
                assert applied == correction + ff
            kernel.commit(next_nu)
            da, dn = reference(double[0] + measurement_noise-target_v, double_nu, f32(h), gains, regularized)
            double_applied, double_nu, _, _, _ = apply_proxy(da, double_nu, dn, ff, gains, total_limit)
            d = disturbance_average(t, h, scenario)
            lag = scenario in ("lag", "lag_noise_tracking")
            actual_next = plant_step(actual, applied, h, d, lag)
            double_next = plant_step(double, double_applied, h, d, lag)
            assert all(math.isfinite(x) for x in (*actual_next, *double_next, old, next_nu))
            velocity_peak = max(velocity_peak, abs(actual[0]))
            nu_peak = max(nu_peak, abs(old), abs(next_nu))
            assert velocity_peak < 50., (spec, "offline sanity velocity", velocity_peak)
            trajectory_error = max(trajectory_error, abs(actual_next[0]-double_next[0]))
            if regularized:
                assert trajectory_error <= 2e-4, (spec, "independent double trajectory", trajectory_error)
            error = actual[0]-target_v
            weighted_e2 += h*error**2
            weighted_m2 += h*(measurement-target_v)**2
            weighted_e += h*error
            elapsed += h
            if t >= 25.:
                tail_sum += h*error
                tail_e2 += h*error**2
                tail_time += h
            if previous_correction is not None:
                tv += abs(correction-previous_correction)
            previous_correction = correction
            limited_count += int(limited)
            frozen_count += int(frozen)
            t += h
            steps += 1
            actual, double = actual_next, double_next
            eligible = numerical_terminal_eligible(regularized, scenario, actual[0], f32(next_nu), double[0], double_nu)
            terminal_hold = terminal_clock.observe(eligible, t)
            if terminal_hold >= 1.:
                early_terminal = True
                break
        tail_mean = tail_sum/tail_time if tail_time else None
        tail_rmse = math.sqrt(tail_e2/tail_time) if tail_time else None
        if regularized and scenario in ("zero", "constant_positive", "constant_negative"):
            assert early_terminal or (tail_rmse is not None and tail_rmse <= 5e-4), (spec, "ideal constant tail", tail_rmse)
        slope_prediction = None
        if regularized and scenario in ("ramp_positive", "ramp_negative"):
            slope = .002 if scenario == "ramp_positive" else -.002
            slope_prediction = gains["epsilon"] * slope/gains["l2"]
            assert abs(tail_mean-slope_prediction) <= 5e-4, (spec, "ramp tail", tail_mean, slope_prediction)
        if scenario == "infeasible":
            assert actual[0] > 20. and limited_count > 0
        mean = weighted_e/elapsed
        return dict(**spec, accepted_check=True, steps=steps, duration_s=elapsed,
                    nu0=nu0, gains=gains, actual_final_velocity=actual[0], actual_peak_velocity=velocity_peak,
                    peak_nu=nu_peak, velocity_rmse=math.sqrt(weighted_e2/elapsed),
                    measured_velocity_rmse=math.sqrt(weighted_m2/elapsed), error_mean=mean,
                    error_variance=max(0., weighted_e2/elapsed-mean**2), tail_mean=tail_mean,
                    tail_rmse=tail_rmse, ramp_particular_prediction=slope_prediction,
                    correction_tv_per_s=tv/elapsed, limited_steps=limited_count, frozen_steps=frozen_count,
                    early_terminal=early_terminal, terminal_hold_s=terminal_hold, final_nu=f32(next_nu),
                    terminal_first_observed_time_s=terminal_clock.first_time,
                    maximum_scaled_local_difference=local_error, maximum_double_velocity_difference=trajectory_error,
                    conclusion="expected_infeasible_not_control_success" if scenario == "infeasible" else "finite_declared_model_check")
    finally:
        kernel.close()


def underflow_negative_case(lib):
    gains = {k: f32(v) for k, v in GAINS["z"].items()}
    kernel = Kernel(lib, True, gains, .05)
    state, t, steps = (.08, 0., 0.), 0., 0
    try:
        while t < 30.:
            before = float(lib.r01_state(kernel.handle, 1))
            status = lib.r01_evaluate(kernel.handle, 1, state[0], 0., .008, kernel.out)
            Kernel.evaluations += 1
            after = float(lib.r01_state(kernel.handle, 1))
            assert after == before, "evaluate mutated state"
            if status:
                commit_status = lib.r01_commit(kernel.handle, 1, before)
                final = float(lib.r01_state(kernel.handle, 1))
                assert status == 5 and commit_status != 0 and final == before
                return dict(accepted_negative_check=True, control_success=False, stop_time_s=t,
                            valid_steps=steps, numerical_error_status=status, invalid_commit_status=commit_status,
                            actual_velocity=state[0], represented_velocity=f32(state[0]),
                            nu_before=before, nu_after_evaluate=after, nu_after_invalid_commit=final,
                            label="reproduced documented subnormal refusal, not a flight failure or full30s success")
            _, a, old, candidate = [float(x) for x in kernel.out]
            applied, nu, _, _, _ = apply_proxy(a, old, candidate, 0., gains, 100.)
            kernel.commit(nu)
            state = plant_step(state, applied, .008, 0., False)
            t += .008
            steps += 1
        raise AssertionError("Expected subnormal domain refusal was not reproduced")
    finally:
        kernel.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite existing evidence")
    result = dict(schema=1, stage="R01 offline independent model", success=False, commands=[],
                  protocol_sha256=digest(HERE / "PROTOCOL02_CN.md"), protocol_v1_sha256=digest(HERE / "PROTOCOL_CN.md"), intended_matrix=matrix(),
                  rows=[], matlab_executed=False, flights=0, epsilon_search_points=0,
                  fixed_epsilon=[.01, .01, .02], sanitizer=args.sanitize)
    try:
        build = Path(tempfile.mkdtemp(prefix="r01-model-"))
        cpp = [KERNEL / "RegularizedStaVelocityControl.cpp", KERNEL / "StaVelocityControl.cpp", HERE / "bridge.cpp"]
        inputs = cpp + [KERNEL / "RegularizedStaVelocityControl.hpp", KERNEL / "StaVelocityControl.hpp",
                        HERE / "model_reference.py", HERE / "test_reference.py", HERE / "run_model.py",
                        HERE / "PROTOCOL_CN.md", HERE / "PROTOCOL02_CN.md"]
        result["source_sha256"] = {str(p.relative_to(REPO)): digest(p) for p in inputs}
        command = ["g++", "-std=c++14", "-O2", "-fPIC", "-shared", "-Wall", "-Wextra", "-Werror",
                   "-pedantic-errors", "-I", str(KERNEL), *map(str, cpp), "-o", str(build / "bridge.so")]
        if args.sanitize:
            command[1:1] = ["-fsanitize=undefined,float-cast-overflow", "-fno-sanitize-recover=all"]
        p = subprocess.run(command, cwd=str(REPO), capture_output=True, text=True)
        result["commands"].append(dict(argv=command, cwd=str(REPO), exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr))
        assert p.returncode == 0, p.stderr
        result["build_directory"] = str(build)
        stream = io.StringIO()
        test_result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReferenceTests))
        result["unit_tests"] = dict(count=test_result.testsRun, failures=len(test_result.failures), errors=len(test_result.errors), output=stream.getvalue())
        assert test_result.wasSuccessful()
        intervals, result["actual_clock"] = actual_clock()
        lib = bind(build / "bridge.so")
        result["one_step_grid"] = grid(lib)
        for spec in matrix():
            result["current_case"] = spec
            result["rows"].append(trajectory(lib, spec, intervals))
        result["underflow_negative_case"] = underflow_negative_case(lib)
        result["success"] = len(result["rows"]) == 160
    except Exception:
        result["error"] = traceback.format_exc()
    if "source_sha256" in result:
        result["source_sha256_end"] = {name: digest(REPO / name) for name in result["source_sha256"]}
        result["source_unchanged_during_verification"] = result["source_sha256"] == result["source_sha256_end"]
        if not result["source_unchanged_during_verification"]:
            result["success"] = False
            result["error"] = result.get("error", "") + "Source changed during verification"
    result["actual_kernel_evaluations"] = Kernel.evaluations
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps(dict(success=result["success"], rows=len(result["rows"]),
                          actual_kernel_evaluations=result.get("actual_kernel_evaluations"),
                          output=str(args.output), error=result.get("error")), ensure_ascii=False))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
