#!/usr/bin/env python3
"""Independent inclusion/plant checks of the offline Proper-ISTA C++ kernel.

The oracle bisects a monotone inclusion in z (no analytic quadratic root).
The binary64 plant integrates g*c+d; never uses virtual_s as physical state.
No flight/parameter I/O. New output directories only. See PROTOCOL_CN.md.
"""
import argparse
import ctypes
import itertools
import json
import math
from pathlib import Path
import struct

import numpy as np


def f32(x):
    return struct.unpack('f', struct.pack('f', x))[0]


def write_json(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def reference(s, nu, h, l1, l2, g, iterations=100):
    """Solve z+h*l1*sqrt(|z|)*xi+h²*l2*xi=s, xi in Sgn(z).

    For nonzero z, bisection of its magnitude, NOT production's rationalized
    root. Then obtain a from z=s+h*(a-nu_next), independently of (12a).
    """
    q = h*h*l2
    if abs(s) <= q:
        z, xi = 0., s/q
    else:
        sign = math.copysign(1., s)
        delta = abs(s)-q
        lo, hi = 0., delta
        for _ in range(iterations):
            mid = (lo+hi)*.5
            if mid + h*l1*math.sqrt(mid) > delta:
                hi = mid
            else:
                lo = mid
        z, xi = sign*(lo+hi)*.5, sign
    next_nu = nu-h*l2*xi
    a = next_nu+(z-s)/h
    return dict(z=z, xi=xi, nu=next_nu, a=a, c=a/g,
                branch=2 if z == 0. else (1 if z > 0. else 3))


def residuals(r, nu, h, l1, l2, g):
    """Scaled residuals of the ORIGINAL three equations and command mapping."""
    equations = [(r['z'], [r['s'], h*r['a'], -h*r['nu']]),
                 (r['nu'], [nu, -h*l2*r['xi']]),
                 (r['a'], [-l1*math.sqrt(abs(r['z']))*r['xi'], 2*r['nu'], -nu]),
                 (r['a'], [g*r['c']])]
    return [abs(lhs-sum(rhs))/max([abs(lhs), *map(abs, rhs), 1e-300]) for lhs, rhs in equations]


class Kernel:
    def __init__(self, library):
        self.lib = ctypes.CDLL(str(Path(library).resolve()))
        self.fn = self.lib.proper_step
        self.fn.argtypes = [ctypes.c_uint]+[ctypes.c_float]*6+[ctypes.c_int, ctypes.c_float, ctypes.POINTER(ctypes.c_double)]
        self.fn.restype = ctypes.c_int

    def raw(self, s, nu, h, l1, l2, g, reset=True, axis=0, sp=0.):
        values = (ctypes.c_double*9)()
        code = self.fn(axis, s, sp, h, l1, l2, g, int(reset), nu, values)
        return code, dict(zip(('old', 's', 'a', 'c', 'nu', 'z', 'xi', 'branch', 'state'), values))

    def step(self, *args, **kwargs):
        code, r = self.raw(*args, **kwargs)
        if code != 0:
            raise AssertionError(f'C++ rejected status={code}, args={args}, kwargs={kwargs}')
        assert r['nu'] == r['state'], r
        return r


def samples(kernel):
    rng = np.random.default_rng(1012026)
    inputs = []
    for k in range(6000):
        h, l1, l2, g, nu = map(f32, (10**rng.uniform(-4, -1.3), 10**rng.uniform(-1, 1.2),
                                    10**rng.uniform(-2.3, .6), 10**rng.uniform(-.3, 2.3), rng.uniform(-3, 3)))
        # Explicitly exercise inclusion interior, near exterior and general s.
        s = f32(rng.uniform(-2, 2)*h*h*l2 if k % 2 == 0 else rng.uniform(-2, 2))
        inputs.append((s, nu, h, l1, l2, g))
    for nu, bound in itertools.product((-.25, 0., .25), (-.0625, .0625)):
        b = np.float32(bound)
        for s in (np.nextafter(b, np.float32(-np.inf)), b, np.nextafter(b, np.float32(np.inf))):
            inputs.append((float(s), nu, .125, 2., 4., 3.))
    inputs.append((float(np.nextafter(np.float32(1), np.float32(np.inf))), 0., 1., 16., 1., 1.))
    rows, max_error, max_residual = [], 0., 0.
    branches = {1: 0, 2: 0, 3: 0}
    for values in inputs:
        s, nu, h, l1, l2, g = values
        r = kernel.step(*values)
        ref = reference(s, nu, h, l1, l2, g)
        assert int(r['branch']) == ref['branch']
        assert abs(r['xi']) <= 1.
        scale = max(abs(nu), abs(s/h), l1*math.sqrt(abs(s)), h*l2, 1e-30)
        for field in ('a', 'nu', 'c', 'z', 'xi'):
            specific = {'a': scale, 'nu': max(abs(nu), h*l2), 'c': scale/g,
                        'z': max(abs(ref['z']), 1e-30), 'xi': 1.}[field]
            error = abs(r[field]-ref[field])/specific
            max_error = max(max_error, error)
            assert error <= 2e-6, (field, error, values, r, ref)
        res = max(residuals(r, nu, h, l1, l2, g))
        assert res <= 8*np.finfo(np.float32).eps, (res, values)
        max_residual = max(max_residual, res)
        branches[int(r['branch'])] += 1
        rows.append([*values, r['a'], r['c'], r['nu'], r['z'], r['xi'], res])
    return dict(count=len(rows), branches=branches, max_scaled_reference_error=max_error,
                max_scaled_equation_residual=max_residual), np.asarray(rows)


def grid():
    cases = []
    for h, g, d, nu in itertools.product((.004, .008, .016), (1., 112.763533), (-.45, 0., .45), (-.3, 0., .3)):
        cases.append(dict(kind='constant', h=h, g=g, d=d, nu0=nu))
    for h, g, m in itertools.product((.004, .008, .016), (1., 112.763533), (-.01, .01)):
        cases.append(dict(kind='ramp', h=h, g=g, d=.15, slope=m, nu0=.3))
    for h, g in itertools.product((.004, .008, .016), (1., 112.763533)):
        cases.append(dict(kind='sine', h=h, g=g, d=.15, nu0=.3))
    for h in (.004, .008, .016):
        cases.append(dict(kind='variable_dt', h=h, g=112.763533, d=-.45, nu0=.3))
        for kind in ('noise', 'saturation', 'lag'):
            cases.append(dict(kind=kind, h=h, g=112.763533, d=-.45, nu0=.3))
    assert len(cases) == 84
    return cases


def disturbance(spec, t, h):
    if spec['kind'] == 'ramp':
        return spec['d']+spec['slope']*(t+h*.5)
    if spec['kind'] == 'sine':
        return spec['d']+.02*(math.cos(.5*t)-math.cos(.5*(t+h)))/(.5*h)
    return spec['d']


def plant(x, motor, command, g, d, h, kind):
    acceleration = g*command
    if kind == 'saturation':
        acceleration = max(-.2, min(.2, acceleration)) # intentionally insufficient against .45
    if kind == 'lag':
        decay = math.exp(-h/.025)
        step = acceleration*h+(motor-acceleration)*.025*(1-decay)
        motor = acceleration+(motor-acceleration)*decay
    else:
        step, motor = acceleration*h, acceleration
    return x+step+h*d, motor


def simulate(kernel, spec):
    nominal_h, g, l1, l2 = map(f32, (spec['h'], spec['g'], 2.4, .08))
    kind = spec['kind']
    duration = 20. if kind in ('noise', 'saturation', 'lag') else 60.
    x = xd = .12
    nu = f32(spec['nu0']); nud = float(nu)
    motor = md = t = 0.
    rows = []; max_local = max_traj = max_residual = 0.
    stopped = False
    while t < duration:
        k = len(rows)
        h = f32(nominal_h*(.5, 1.5, 1., .75, 1.25)[k % 5]) if kind == 'variable_dt' else nominal_h
        noise = .002*math.sin(137*t) if kind == 'noise' else 0.
        s = f32(x+noise)
        r = kernel.step(s, nu, h, l1, l2, g, reset=k == 0)
        local = reference(s, r['old'], h, l1, l2, g)
        independent = reference(xd+noise, nud, h, l1, l2, g)
        max_local = max(max_local, *(abs(r[key]-local[key]) for key in ('a', 'nu', 'c', 'z', 'xi')))
        max_residual = max(max_residual, *residuals(r, r['old'], h, l1, l2, g))
        dbar = disturbance(spec, t, h)
        xnext, motor = plant(x, motor, r['c'], g, dbar, h, kind)
        xdnext, md = plant(xd, md, independent['c'], g, dbar, h, kind)
        max_traj = max(max_traj, abs(xnext-xdnext))
        rows.append([t, h, x, xd, r['old'], r['a'], r['c'], r['nu'], r['z'], r['xi'], dbar, xnext])
        x, xd, nu, nud, t = xnext, xdnext, r['nu'], independent['nu'], t+h
        if kind == 'constant' and spec['d'] == 0. and max(abs(x), abs(nu)) < 1e-12:
            stopped = True # numerical terminal criterion, not machine-exact finite-time proof
            break
    data = np.asarray(rows)
    tail = data[data[:, 0] >= duration-10., 2]
    summary = dict(spec=spec, updates=len(rows), stopped_at_numerical_terminal=stopped,
                   max_local_reference_abs=max_local, max_independent_trajectory_abs=max_traj,
                   max_scaled_equation_residual=max_residual, final_x=x, final_nu=nu)
    assert max_residual <= 8*np.finfo(np.float32).eps
    assert max_traj < 2e-4, summary
    assert max_local < 2e-5, summary
    if stopped:
        assert kind == 'constant' and spec['d'] == 0.
        summary['tail'] = None
    else:
        assert len(tail) > 0
        summary['tail'] = dict(mean=float(np.mean(tail)), rmse=float(np.sqrt(np.mean(tail*tail))), peak=float(np.max(abs(tail))))
        if kind == 'constant':
            assert np.max(abs(tail)) < 2e-6, summary
        elif kind == 'ramp':
            expected = spec['slope']*nominal_h*nominal_h
            summary['expected_ramp_s'] = expected
            summary['max_tail_ramp_deviation'] = float(np.max(abs(tail-expected)))
            assert summary['max_tail_ramp_deviation'] < 2e-6, summary
        elif kind == 'sine':
            summary['fixed_h_theory_bound'] = .01*nominal_h*nominal_h
            assert np.max(abs(tail)) <= summary['fixed_h_theory_bound']+2e-6, summary
        elif kind == 'saturation':
            assert abs(summary['tail']['mean']) > 1., 'Intentionally infeasible case must not be called converged'
    return summary, data


def main():
    p = argparse.ArgumentParser(); p.add_argument('--library', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(); out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    kernel = Kernel(args.library)
    summary = dict(success=False, reference=None, cases=[])
    try:
        summary['reference'], raw = samples(kernel)
        np.savez_compressed(out/'reference.npz', samples=raw)
        for i, spec in enumerate(grid()):
            item, raw = simulate(kernel, spec)
            np.savez_compressed(out/f'case_{i:03d}.npz', samples=raw)
            summary['cases'].append(item)
        summary['updates'] = sum(c['updates'] for c in summary['cases'])
        summary['success'] = True
    except Exception as exc:
        summary['failure'] = repr(exc)
        raise
    finally:
        write_json(out/'summary.json', summary)
    print(f"{summary['reference']['count']} reference samples; {len(summary['cases'])} plant cases; {summary['updates']} C++ updates")


if __name__ == '__main__':
    main()
