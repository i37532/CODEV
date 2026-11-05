#!/usr/bin/env python3
"""Independent binary64 bisection oracle + exact-ZOH scalar plant. OFFLINE only.

No analytic/rationalized production root is copied. Bisection solves the
monotone implicit inclusion in sqrt(|virtual_s|); 120 iterations, offline only.
Double reference comparisons condition on the same float input/state, whereas
closed-loop comparisons additionally evolve an independent binary64 controller.
"""
import argparse
import json
import math
from pathlib import Path
import random
import struct
import subprocess


def f32(x):
    return struct.unpack('f', struct.pack('f', x))[0]


def reference(s, nu, h, l1, l2, g):
    target = s + h * nu
    q = h * h * l2
    if abs(target) <= q:
        return dict(branch=2, xi=target / q, virtual_s=0.0, nu_next=-s / h,
                    a=-s / h, c_raw=-s / h / g)
    sign = math.copysign(1.0, target)
    magnitude = abs(target) - q
    low, high = 0.0, min(math.sqrt(magnitude), magnitude / (h * l1))
    for _ in range(120):
        mid = (low + high) / 2.0
        if mid * mid + h * l1 * mid > magnitude:
            high = mid
        else:
            low = mid
    root = (low + high) / 2.0
    next_nu = nu - h * l2 * sign
    a = -l1 * root * sign + next_nu
    return dict(branch=1 if sign > 0 else 3, xi=sign, virtual_s=sign * root * root,
                nu_next=next_nu, a=a, c_raw=a / g)


class Probe:
    def __init__(self, executable, raw):
        self.process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, text=True, bufsize=1)
        self.raw = raw
        self.count = 0

    def step(self, axis, rate, sp, h, l1, l2, g, reset=False, nu=0.0):
        values = [axis, f32(rate), f32(sp), f32(h), f32(l1), f32(l2), f32(g), int(reset), f32(nu)]
        self.process.stdin.write(' '.join(map(str, values)) + '\n')
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        fields = list(map(float, line.split()))
        assert len(fields) == 10, ('probe terminated', line)
        status, branch, old, s, a, c, next_nu, virtual_s, xi, state = fields
        out = dict(status=int(status), branch=int(branch), old=old, s=s, a=a, c_raw=c,
                   nu_next=next_nu, virtual_s=virtual_s, xi=xi, state=state)
        self.raw.write(json.dumps(dict(input=values, output=out), allow_nan=False) + '\n')
        self.count += 1
        assert status == 0, out
        assert state == next_nu
        return out

    def close(self):
        self.process.stdin.close()
        assert self.process.wait(timeout=10) == 0


def compare(out, h, l1, l2, g):
    ref = reference(out['s'], out['old'], h, l1, l2, g)
    assert out['branch'] == ref['branch'], (out, ref)
    errors = {}
    for key in ('a', 'nu_next', 'c_raw', 'virtual_s', 'xi'):
        # Relative to the component itself, including near-boundary tiny roots.
        scale = max(abs(ref[key]), 1e-35)
        err = abs(out[key] - ref[key]) / scale
        assert err < 3e-6, (key, err, out, ref)
        errors[key] = err
    assert -1 <= out['xi'] <= 1
    # All three equations after independent float rounding, with operation scales.
    s, a, v, xi, old, new = (out[k] for k in ('s', 'a', 'virtual_s', 'xi', 'old', 'nu_next'))
    residuals = [abs(v - (s + h * a)) / max(1e-30, abs(v), abs(s), abs(h * a)),
                 abs(new - (old - h * l2 * xi)) / max(1e-30, abs(old), abs(h * l2)),
                 abs(a - (-l1 * math.sqrt(abs(v)) * xi + new)) /
                 max(1e-30, abs(a), abs(new), l1 * math.sqrt(abs(v))),
                 abs(v - (s + h * g * out['c_raw'])) /
                 max(1e-30, abs(v), abs(s), abs(h * g * out['c_raw']))]
    assert max(residuals) < 8e-7, (residuals, out)
    return max(errors.values()), max(residuals)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    rng = random.Random(7072026)
    result = dict(seed=7072026, oracle='binary64 monotone bisection, 120 offline iterations',
                  ideal_tolerance=dict(rate=1e-7, nu=1e-6), branches={1: 0, 2: 0, 3: 0},
                  max_reference_relative_error=0.0, max_equation_scaled_residual=0.0, closed_loops=[])
    with (args.output / 'samples.jsonl').open('w') as raw:
        probe = Probe(args.probe, raw)
        try:
            # Randomized scales, all branches, nonzero old states and setpoints.
            for k in range(6000):
                h = f32(10 ** rng.uniform(-4, -0.3))
                l1, l2, g = [f32(10 ** rng.uniform(-2, 3)) for _ in range(3)]
                nu = f32(rng.uniform(-2, 2))
                if k % 3 == 0:
                    s = f32(-h * nu + rng.uniform(-.95, .95) * h * h * l2)
                    sp = 0.0
                else:
                    s, sp = f32(rng.uniform(-5, 5)), f32(rng.uniform(-1, 1))
                out = probe.step(k % 3, s, sp, h, l1, l2, g, True, nu)
                error, residual = compare(out, h, l1, l2, g)
                result['branches'][out['branch']] += 1
                result['max_reference_relative_error'] = max(result['max_reference_relative_error'], error)
                result['max_equation_scaled_residual'] = max(result['max_equation_scaled_residual'], residual)
            result['reference_samples'] = 6000

            # Exact binary boundaries and binary32 neighbours, tiny nonzero roots,
            # float q underflow and discriminant overflow: same independent oracle.
            edge_inputs = []
            for sign in (-1, 1):
                for s in (f32(.0625 - 2**-28), .0625, f32(.0625 + 2**-27)):
                    edge_inputs.append((sign * s, .125, 2., 4., 3.))
                edge_inputs.append((sign * f32(1 + 2**-23), 1., 16., 1., 7.))
            edge_inputs += [(0., 2**-126, 2**-126, 2**-126, 1.),
                            (.25, 1e-15, 1., 1e-20, 1.), (1e20, 1., 1e20, 1., 1.)]
            for s, h, l1, l2, g in edge_inputs:
                s, h, l1, l2, g = map(f32, (s, h, l1, l2, g))
                out = probe.step(0, s, 0., h, l1, l2, g, True, 0.)
                compare(out, h, l1, l2, g)
            result['edge_reference_samples'] = len(edge_inputs)

            # Independent x[k+1]=x[k]+h*(g*c_applied+d); never assign virtual_s to x.
            # Four scenarios are separate results, no implicit-equation claim for
            # the disturbed/noisy/saturated ACTUAL next object state.
            for h0 in (.001, .01, .1):
                for g0 in (.5, 1.0, 130.575283):
                    for scenario in ('ideal', 'disturbance', 'noise', 'saturation'):
                        h, g, l1, l2 = map(f32, (h0, g0, 10.0, 6.0))
                        x, xd, nd = 2.0, 2.0, 0.0
                        errors, deviations = [], []
                        clipped, prediction_difference, settled = 0, 0.0, False
                        for k in range(round(6 / h)):
                            t = k * h
                            noise = .001 * math.sin(17 * t) if scenario == 'noise' else 0.0
                            disturbance = .2 * math.sin(2 * t) if scenario == 'disturbance' else 0.0
                            out = probe.step(0, x + noise, 0, h, l1, l2, g, k == 0, 0)
                            compare(out, h, l1, l2, g)
                            double_out = reference(xd + noise, nd, h, l1, l2, g)
                            command, double_command = out['c_raw'], double_out['c_raw']
                            if scenario == 'saturation':
                                limit = 2.0 / g # fixed acceleration authority across g, no state freeze
                                command = min(limit, max(-limit, command))
                                double_command = min(limit, max(-limit, double_command))
                                clipped += int(command != out['c_raw'])
                            x += h * (g * command + disturbance)
                            xd += h * (g * double_command + disturbance)
                            nd = double_out['nu_next']
                            errors.append(abs(x))
                            deviations.append(abs(x - xd))
                            prediction_difference = max(prediction_difference, abs(x - out['virtual_s']))
                            if scenario in ('ideal', 'saturation') and abs(x) < 1e-7 and abs(out['nu_next']) < 1e-6:
                                settled = True
                                break # tolerance reached, NOT an exact finite-time/forever-zero claim
                        tail = errors[-min(len(errors), max(1, round(.5 / h))):]
                        entry = dict(scenario=scenario, h=h, g=g, steps=len(errors), settled_to_tolerance=settled,
                                     final_abs_error=errors[-1], tail_rmse=math.sqrt(sum(e*e for e in tail)/len(tail)),
                                     max_double_trajectory_difference=max(deviations), clipped_samples=clipped,
                                     max_actual_vs_ideal_prediction=prediction_difference)
                        result['closed_loops'].append(entry)
                        if scenario in ('ideal', 'saturation'):
                            assert settled, entry
                        else:
                            assert entry['tail_rmse'] < .05, entry
                        assert entry['max_double_trajectory_difference'] < 2e-4, entry
                        if scenario == 'saturation':
                            assert clipped > 0 and prediction_difference > .01, entry
            result['production_updates'] = probe.count
        finally:
            probe.close()
    result['passed'] = True
    (args.output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'closed_loops'}, indent=2))
    print('closed loops:', len(result['closed_loops']))


if __name__ == '__main__':
    main()
