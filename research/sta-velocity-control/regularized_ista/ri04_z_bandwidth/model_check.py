#!/usr/bin/env python3
"""Finite offline diagnostic, not tuning, firmware protection or flight qualification."""
import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
CORE = REPO / "src/modules/mc_pos_control/PositionControl"
BASE = (2., 1., .02)
MATCHED = (2.2470735044448613, 1.1647156696299077, .02)
CONFIGS = {"rsta": (0, BASE), "rista_base": (1, BASE), "rista_matched_10ms": (1, MATCHED)}
PERIODS = {"8ms": (.008,), "10ms": (.010,), "12ms": (.012,), "alternating8_12ms": (.008, .012)}
SCENARIOS = ("ramp_disturbance", "velocity_target", "target_with_ff", "lag", "noise", "infeasible_clipping")

def f32(x):
    return ctypes.c_float(x).value

def prewarp(l1, l2, epsilon, h0):
    if not all(math.isfinite(x) and x > 0 for x in (l1, l2, epsilon, h0)):
        raise ValueError("finite positive inputs required")
    if not .001 <= epsilon <= 1. or not math.isfinite(f32(h0)) or f32(h0) < 2. ** -126:
        raise ValueError("epsilon/sample outside the float core domain")
    alpha, beta = l1 / math.sqrt(epsilon), l2 / epsilon
    if not all(math.isfinite(x) and x > 0 for x in (alpha, beta)):
        raise ValueError("nonfinite or disappearing derived gain")
    denominator = 1 - h0 * alpha
    numerator = alpha - h0 * beta
    if not all(math.isfinite(x) and x > 0 for x in (denominator, numerator)):
        raise ValueError("positive prewarp domain exceeded")
    result = (numerator / denominator * math.sqrt(epsilon), l2 / denominator, epsilon)
    if not all(math.isfinite(x) and math.isfinite(f32(x)) and f32(x) >= 2. ** -126 for x in result):
        raise ValueError("prewarp output outside positive normal float domain")
    return result

def effective(parameters, h):
    l1, l2, epsilon = parameters
    alpha, beta = l1 / math.sqrt(epsilon), l2 / epsilon
    d = 1 + h * alpha + h * h * beta
    return (alpha + h * beta) / d, beta / d

class Kernel:
    def __init__(self, library, mode, parameters):
        self.lib = ctypes.CDLL(str(library))
        self.lib.band_create.argtypes, self.lib.band_create.restype = [ctypes.c_int], ctypes.c_void_p
        self.lib.band_destroy.argtypes = [ctypes.c_void_p]
        self.lib.band_configure.argtypes = [ctypes.c_void_p] + [ctypes.c_float] * 3
        self.lib.band_reset.argtypes = [ctypes.c_void_p, ctypes.c_float]
        self.lib.band_evaluate.argtypes = [ctypes.c_void_p] + [ctypes.c_float] * 3 + [ctypes.POINTER(ctypes.c_double)]
        self.lib.band_commit.argtypes = [ctypes.c_void_p, ctypes.c_float]
        self.lib.band_state.argtypes, self.lib.band_state.restype = [ctypes.c_void_p], ctypes.c_float
        self.handle = self.lib.band_create(mode)
        if not self.handle or not self.lib.band_configure(self.handle, *parameters):
            raise ValueError("invalid core configuration")
    def close(self):
        if self.handle:
            self.lib.band_destroy(self.handle)
            self.handle = None
    def reset(self, nu):
        return self.lib.band_reset(self.handle, nu)
    def evaluate(self, v, target, h):
        out = (ctypes.c_double * 5)()
        status = self.lib.band_evaluate(self.handle, v, target, h, out)
        return status, list(out)
    def commit(self, nu):
        return self.lib.band_commit(self.handle, nu)
    def state(self):
        return self.lib.band_state(self.handle)

def shape(p, epsilon):
    rho = max(-1., min(1., p / epsilon))
    return (p / math.sqrt(epsilon) if abs(p) <= epsilon else math.copysign(math.sqrt(abs(p)), p)), rho

def reference(mode, parameters, s, nu, h):
    """Independent binary64 monotone bisection, NOT the production analytic root."""
    l1, l2, epsilon = parameters
    p = s
    if mode:
        low, high = 0., abs(s)
        for _ in range(60):
            middle = (low + high) * .5
            psi, rho = shape(middle, epsilon)
            if middle + h * l1 * psi + h * h * l2 * rho < abs(s):
                low = middle
            else:
                high = middle
        p = math.copysign((low + high) * .5, s)
    psi, rho = shape(p, epsilon)
    next_nu = nu - h * l2 * rho
    return p, -l1 * psi + (next_nu if mode else nu), next_nu

def target(t):
    w, b = 2 * math.pi / 8, math.pi / 32
    velocity = .1 * math.sin(w * t) * math.sin(b * t) ** 2
    acceleration = .1 * (w * math.cos(w * t) * math.sin(b * t) ** 2
                           + b * math.sin(w * t) * math.sin(2 * b * t))
    return velocity, acceleration

def trajectory(library, name, period, scenario):
    mode, nominal = CONFIGS[name]
    parameters = tuple(map(f32, nominal))
    kernel = Kernel(library, mode, parameters)
    kernel.reset(.1)
    v = vr = .03
    nr = f32(.1)
    lag = [0., 0.]
    lagr = [0., 0.]
    t = squared = tv = last = maximum_reference_error = 0.
    settled_squared = settled_duration = 0.
    steps = clipped = 0
    status = "complete"
    try:
        while t < 32. - 1e-10:
            h = min(PERIODS[period][steps % len(PERIODS[period])], 32. - t)
            hc = f32(h)
            sp, ff = target(t) if scenario != "ramp_disturbance" else (0., 0.)
            sp = f32(sp)
            ff = ff if scenario == "target_with_ff" else 0.
            noise = .001 * math.sin(2 * math.pi * 13 * t) + .0005 * math.sin(2 * math.pi * 29 * t) if scenario == "noise" else 0.
            code, c = kernel.evaluate(v + noise, sp, hc)
            if code:
                status = "core_domain_rejection"
                break
            _, ar, next_nr = reference(mode, parameters, vr + noise - sp, nr, hc)
            a, next_nu = c[2], c[4]
            if scenario == "infeasible_clipping":
                clipped += abs(a) > .05
                a, ar = max(-.05, min(.05, a)), max(-.05, min(.05, ar))
                next_nu, next_nr = max(-4., min(4., next_nu)), max(-4., min(4., next_nr))
            if kernel.commit(next_nu):
                raise AssertionError("candidate commit failed")
            nr = next_nr
            applied, applied_r = a + ff, ar + ff
            if scenario == "lag":
                for index, tau in enumerate((.06, .02)):
                    gain = 1 - math.exp(-h / tau)
                    lag[index] += gain * (applied - lag[index])
                    lagr[index] += gain * (applied_r - lagr[index])
                    applied, applied_r = lag[index], lagr[index]
            disturbance = .15 + (.002 * (t + h / 2) if scenario == "ramp_disturbance" else 0.)
            squared += h * (v - sp) ** 2
            settled_weight = max(0., t + h - max(t, 8.))
            settled_squared += settled_weight * (v - sp) ** 2
            settled_duration += settled_weight
            tv += abs(a - last) if steps else 0.
            last = a
            v, vr = v + h * (applied + disturbance), vr + h * (applied_r + disturbance)
            maximum_reference_error = max(maximum_reference_error, abs(v - vr))
            if not all(math.isfinite(x) for x in (v, vr, nr, next_nu)):
                raise AssertionError("nonfinite model state")
            steps += 1
            t += h
    finally:
        kernel.close()
    return dict(config=name, period=period, scenario=scenario, status=status, updates=steps,
                seconds=t, velocity_rmse=math.sqrt(squared / t) if t else None, correction_tv_per_s=tv / t if t else None,
                velocity_rmse_8_to_32s=math.sqrt(settled_squared / settled_duration) if settled_duration else None,
                clipped_updates=clipped, terminal_velocity=v, double_reference_max_velocity_difference=maximum_reference_error,
                expected_tracking_failure=scenario == "infeasible_clipping",
                claim="engineering diagnostic, not PX4 adapter equivalence or flight safety")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    library = args.output / "kernels.so"
    sources = [HERE / "kernel_bridge.cpp", CORE / "RegularizedStaVelocityControl.cpp", CORE / "RegularizedIstaVelocityControl.cpp"]
    command = ["g++", "-std=c++14", "-O2", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror", "-pedantic-errors", "-I", str(CORE), *map(str, sources), "-o", str(library)]
    compile_result = subprocess.run(command, capture_output=True, text=True)
    (args.output / "compile.log").write_text(compile_result.stdout + compile_result.stderr)
    evidence = {"compile_command": command, "compile_exit": compile_result.returncode,
                "sources": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources + [
                    CORE / "RegularizedStaVelocityControl.hpp", CORE / "RegularizedIstaVelocityControl.hpp",
                    Path(__file__), HERE / "test_model.py"]}}
    if compile_result.returncode:
        (args.output / "summary.json").write_text(json.dumps(evidence, indent=2) + "\n")
        return compile_result.returncode
    env = dict(os.environ, RI04_BANDWIDTH_LIBRARY=str(library.resolve()), PYTHONDONTWRITEBYTECODE="1")
    tests = subprocess.run([sys.executable, "-B", str(HERE / "test_model.py"), "-v"], env=env, capture_output=True, text=True)
    (args.output / "tests.log").write_text(tests.stdout + tests.stderr)
    evidence["unit_test_exit"] = tests.returncode
    rows = []
    if not tests.returncode:
        rows = [trajectory(library, name, period, scenario) for name in CONFIGS for period in PERIODS for scenario in SCENARIOS]
    valid = len(rows) == 72 and all(r["status"] == "complete" and r["double_reference_max_velocity_difference"] < 2e-4 for r in rows)
    counterexamples = [r for r in rows if r["expected_tracking_failure"]]
    valid = valid and len(counterexamples) == 12 and all(r["clipped_updates"] > 0 and abs(r["terminal_velocity"]) > 2. for r in counterexamples)
    evidence.update(success=valid, rows=rows, trajectory_count=len(rows), total_updates=sum(r["updates"] for r in rows),
                    tracked_counterexamples=len(counterexamples), fixed_candidate=prewarp(*BASE, .01),
                    restrictions=["No flight, tuning sweep or production edits", "Independent scalar object, not PX4 protection/HTE/landing simulation", "Deterministic noise; trajectories not independent statistical samples", "Final hold may be shortened to end exactly at32s (12ms sequence ends with8ms)", "No must-win assertion or future flight qualification"])
    (args.output / "summary.json").write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: evidence[k] for k in ("success", "trajectory_count", "total_updates", "tracked_counterexamples")}))
    return 0 if valid else 1

if __name__ == "__main__":
    sys.exit(main())
