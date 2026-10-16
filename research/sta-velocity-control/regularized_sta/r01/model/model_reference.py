#!/usr/bin/env python3
"""Independent double mathematical reference and exact held-input plant."""
import math
import struct

GAINS = {"xy": dict(l1=.5, l2=.1, epsilon=.01, nu_limit=.4, correction_limit=.8),
         "z": dict(l1=2., l2=1., epsilon=.02, nu_limit=4., correction_limit=6.)}
SCENARIOS = ("zero", "constant_positive", "constant_negative", "ramp_positive", "ramp_negative",
             "tracking_ff", "noise", "lag", "infeasible", "lag_noise_tracking")
TIMINGS = ("fixed_008", "fixed_010", "fixed_012", "actual_log")


def f32(value):
    return struct.unpack("f", struct.pack("f", value))[0]


def next_float(value, direction):
    value = f32(value)
    bits = struct.unpack("I", struct.pack("f", value))[0]
    bits += 1 if (value >= 0) == (direction > value) else -1
    return struct.unpack("f", struct.pack("I", bits))[0]


def clip(value, low, high):
    return min(high, max(low, value))


def reference(s, nu, h, gains, regularized):
    if regularized:
        sigma = clip(s / gains["epsilon"], -1., 1.)
        psi = math.sqrt(max(abs(s), gains["epsilon"])) * sigma
    else:
        sigma = (s > 0) - (s < 0)
        psi = math.sqrt(abs(s)) * sigma
    return -gains["l1"] * psi + nu, nu - h * gains["l2"] * sigma


def apply_proxy(a, old_nu, next_nu, ff, gains, total_limit):
    """Scalar research constraint proxy, not production coupled protection."""
    correction = clip(a, -gains["correction_limit"], gains["correction_limit"])
    total = correction + ff
    applied = clip(total, -total_limit, total_limit)
    candidate = clip(next_nu, -gains["nu_limit"], gains["nu_limit"])
    delta = candidate - old_nu
    frozen = (a - correction) * delta > 0 or (total - applied) * delta > 0
    return applied, old_nu if frozen else candidate, correction, (a != correction or total != applied), frozen


def target(t, scenario):
    if scenario in ("tracking_ff", "lag_noise_tracking"):
        w = 2 * math.pi / 8
        return .12 * math.sin(w * t), .12 * w * math.cos(w * t)
    return 0., 0.


def noise(t, scenario):
    if scenario in ("noise", "lag_noise_tracking"):
        return .002 * math.sin(2 * math.pi * 23 * t) + .001 * math.sin(2 * math.pi * 37 * t)
    return 0.


def disturbance_average(t, h, scenario):
    if scenario == "zero":
        return 0.
    if scenario == "constant_positive":
        return .08
    if scenario == "constant_negative":
        return -.08
    if scenario == "ramp_positive":
        return .02 + .002 * (t + h / 2)
    if scenario == "ramp_negative":
        return -.02 - .002 * (t + h / 2)
    if scenario == "infeasible":
        return 1.2
    return .04


def plant_step(state, command, h, disturbance, lag):
    """State=(velocity,attitude-channel,motor-channel); exact cascade ZOH."""
    v, x, y = state
    if not lag:
        return v + h * (command + disturbance), command, command
    tau1, tau2 = .04, .025
    e1, e2 = math.exp(-h / tau1), math.exp(-h / tau2)
    coefficient = (x - command) * tau1 / (tau1 - tau2)
    integral = command * h + (y - command) * tau2 * (1 - e2)
    integral += coefficient * (tau1 * (1 - e1) - tau2 * (1 - e2))
    new_x = command + (x - command) * e1
    new_y = command + (y - command) * e2 + coefficient * (e1 - e2)
    return v + integral + h * disturbance, new_x, new_y


def matrix():
    return [dict(algorithm=algorithm, gain_class=gain_class, timing=timing, scenario=scenario)
            for algorithm in ("esta", "rsta") for gain_class in ("xy", "z")
            for timing in TIMINGS for scenario in SCENARIOS]


def numerical_terminal_eligible(regularized, scenario, actual_s, actual_nu, double_s, double_nu):
    return (regularized and scenario == "zero"
            and all(abs(x) < 1e-12 for x in (actual_s, actual_nu, double_s, double_nu)))


class TerminalClock:
    """Duration is measured between eligible observations, not before the first."""
    def __init__(self):
        self.first_time = None

    def observe(self, eligible, time):
        if not eligible:
            self.first_time = None
            return 0.
        if self.first_time is None:
            self.first_time = time
        return time - self.first_time
