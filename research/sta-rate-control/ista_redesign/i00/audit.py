#!/usr/bin/env python3
"""I00 offline scalar audit. Production float kernels vs binary64 inclusion solver.

No flight imports, no Proper-ISTA implementation, no production changes.
Independent plant state is never replaced by the kernel's virtual state.
Outputs must be new; numerical failures are evidence, not silently skipped.
"""
import argparse
import ctypes
import hashlib
import itertools
import json
import math
from pathlib import Path
import struct

import numpy as np


def f32(value):
    return struct.unpack('f', struct.pack('f', value))[0]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def implicit(s, nu, h, l1, l2, g):
    """Binary64 reference: solve the monotone inclusion in virtual state z.

    Not the production analytic/rationalized square-root formula. 80 bisections
    of z + h*l1*sqrt(z) + h*h*l2 = abs(s+h*nu), when outside the inclusion gap.
    """
    target = s + h * nu
    q = h * h * l2
    if abs(target) <= q:
        xi, z = target / q, 0.0
        next_nu = -s / h
        return dict(a=next_nu, c=next_nu/g, nu=next_nu, z=z, xi=xi, branch=2)
    sign = math.copysign(1.0, target)
    lo, hi = 0.0, abs(target) - q
    for _ in range(80):
        mid = (lo + hi) * .5
        if mid + h*l1*math.sqrt(mid) + q > abs(target):
            hi = mid
        else:
            lo = mid
    z = sign * (lo + hi) * .5
    next_nu = nu - h*l2*sign
    a = -l1*math.sqrt(abs(z))*sign + next_nu
    return dict(a=a, c=a/g, nu=next_nu, z=z, xi=sign, branch=1 if sign > 0 else 3)


def explicit(s, nu, h, l1, l2, g):
    sign = float(s > 0) - float(s < 0)
    a = -l1*math.sqrt(abs(s))*sign + nu
    return dict(a=a, c=a/g, nu=nu-h*l2*sign)


class Kernel:
    def __init__(self, path):
        self.lib = ctypes.CDLL(str(Path(path).resolve()))
        self.fn = self.lib.audit_step
        self.fn.argtypes = [ctypes.c_int, ctypes.c_uint] + [ctypes.c_float]*6 + [ctypes.c_int, ctypes.c_float, ctypes.POINTER(ctypes.c_double)]
        self.fn.restype = ctypes.c_int

    def step(self, mode, s, nu, h, l1, l2, g, reset=False, axis=0):
        raw = (ctypes.c_double * 9)()
        status = self.fn(mode, axis, s, 0., h, l1, l2, g, int(reset), nu, raw)
        if status != 0:
            raise ValueError(f'production status={status}, mode={mode}, s={s}, nu={nu}, h={h}')
        r = dict(zip(('old', 's', 'a', 'c', 'nu', 'z', 'xi', 'branch', 'state'), raw))
        if r['nu'] != r['state']:
            raise AssertionError('Candidate/state mismatch')
        return r


def moments(samples):
    x = np.asarray(samples, dtype=np.float64)
    if x.size == 0 or not np.all(np.isfinite(x)):
        raise ValueError('Empty/nonfinite samples')
    mean = np.mean(x, axis=0)
    variance = np.var(x, axis=0, ddof=0)
    mse = np.mean(x*x, axis=0)
    residual = np.max(np.abs(mse - (mean*mean + variance)))
    if residual > 1e-12 * max(1., float(np.max(mse))):
        raise AssertionError('Moment decomposition inconsistent')
    return dict(mean=np.asarray(mean).tolist(), std=np.sqrt(variance).tolist(),
                rmse=np.sqrt(mse).tolist(), identity_residual=float(residual))


def disturbance_average(d0, slope, t, h):
    return d0 + slope*(t + .5*h)  # exact interval average of affine disturbance


def plant_step(x, motor, c, g, dbar, h, scenario):
    """Exact interval integral for scalar ZOH command; lag tau=.025s if selected."""
    acceleration = g*c
    if scenario == 'saturation':
        acceleration = max(-.2, min(.2, acceleration))
    clipped = abs(acceleration - g*c) > 1e-12
    if scenario == 'lag':
        decay = math.exp(-h/.025)
        increment = acceleration*h + (motor-acceleration)*.025*(1-decay)
        motor = acceleration + (motor-acceleration)*decay
    else:
        increment = acceleration*h
        motor = acceleration
    return x + increment + h*dbar, motor, clipped


def case_grid():
    # This grid is fixed before execution; no parameter selection is performed.
    cases = []
    for mode, h, g, d, nu in itertools.product((1, 2), (.004, .008, .016), (1., 112.763533), (-.45, 0., .45), (-.3, 0., .3)):
        cases.append(dict(mode=mode, h=h, g=g, d0=d, slope=0., nu0=nu,
                          x0=0. if d == 0. and nu == 0. else .12,
                          scenario='ideal', duration=60., tail_seconds=10.))
    for mode, h, slope in itertools.product((1, 2), (.004, .008, .016), (-.01, .01)):
        cases.append(dict(mode=mode, h=h, g=112.763533, d0=.15, slope=slope, nu0=.3,
                          x0=.12, scenario='ramp', duration=60., tail_seconds=10.))
    for mode, h, scenario in itertools.product((1, 2), (.004, .008, .016), ('noise', 'saturation', 'lag')):
        cases.append(dict(mode=mode, h=h, g=112.763533, d0=-.45, slope=0., nu0=0.,
                          x0=.12, scenario=scenario, duration=20., tail_seconds=5.))
    return cases


def simulate(kernel, spec, output):
    h, g, l1, l2 = map(f32, (spec['h'], spec['g'], 2.4, .08))
    mode, scenario = spec['mode'], spec['scenario']
    x, xd, nd = spec['x0'], spec['x0'], f32(spec['nu0'])
    motor = md = 0.
    samples = []
    maximum_local_error = 0.
    maximum_residual = 0.
    clips = 0
    terminal = False
    oracle = implicit if mode == 2 else explicit
    for k in range(round(spec['duration']/h)):
        t = k*h
        noise = .002*math.sin(137*t) if scenario == 'noise' else 0.
        r = kernel.step(mode, x+noise, spec['nu0'], h, l1, l2, g, reset=(k == 0))
        ref = oracle(r['s'], r['old'], h, l1, l2, g)
        local = max(abs(r[key]-ref[key]) for key in ('a', 'c', 'nu'))
        maximum_local_error = max(maximum_local_error, local)
        if local > 2e-6*max(1., abs(ref['a']), abs(ref['nu'])):
            raise AssertionError(('local reference', spec, k, r, ref))
        if mode == 2:
            if r['branch'] != ref['branch']:
                raise AssertionError(('branch', spec, k))
            residual = max(abs(r['z']-(r['s']+h*r['a'])),
                           abs(r['nu']-(r['old']-h*l2*r['xi'])),
                           abs(r['a']-(-l1*math.sqrt(abs(r['z']))*r['xi']+r['nu'])),
                           abs(r['z']-(r['s']+h*g*r['c'])))
            maximum_residual = max(maximum_residual, residual)
            if residual > 2e-6*max(1., abs(r['a']), abs(r['old'])):
                raise AssertionError(('implicit residual', spec, k, residual))
        rd = oracle(xd+noise, nd, h, l1, l2, g)
        dbar = disturbance_average(spec['d0'], spec['slope'], t, h)
        nx, motor, clipped = plant_step(x, motor, r['c'], g, dbar, h, scenario)
        nxd, md, _ = plant_step(xd, md, rd['c'], g, dbar, h, scenario)
        # Prediction for the previous disturbance interval, indexed at x_k.
        expected_bias = h*disturbance_average(spec['d0'], spec['slope'], t-h, h)
        samples.append((t, x, r['s'], r['old'], r['a'], r['c'], r['nu'], r['z'], r['xi'],
                        dbar, nx, xd, rd['nu'], expected_bias, float(clipped), r['branch']))
        clips += int(clipped)
        x, xd, nd = nx, nxd, rd['nu']
        # Avoid underflow beyond the kernel's declared domain; do not pad a tail.
        if mode == 2 and scenario == 'ideal' and spec['d0'] == 0. and spec['nu0'] != 0.:
            if max(abs(x), abs(xd)) < 1e-7 and max(abs(r['nu']), abs(nd)) < 1e-6:
                terminal = True
                break
    a = np.asarray(samples)
    if not np.all(np.isfinite(a)):
        raise AssertionError('Nonfinite trajectory')
    np.savez_compressed(output, samples=a, columns=np.array([
        't', 'x', 'measured_s', 'nu_before', 'a', 'c', 'nu_next', 'virtual_s', 'xi',
        'd_interval_average', 'x_next', 'double_x', 'double_nu_next', 'expected_bias', 'clipped', 'branch']))
    entry = dict(**spec, h_float=h, g_float=g, lambda1=l1, lambda2=l2, steps=len(a),
                 terminal_tolerance_reached=terminal, raw_path=str(output), raw_sha256=digest(output),
                 max_local_reference_abs_error=maximum_local_error,
                 max_implicit_abs_residual=maximum_residual if mode == 2 else None,
                 max_double_trajectory_abs_error=float(np.max(abs(a[:, 1]-a[:, 11]))),
                 max_actual_next_minus_nominal_prediction=float(np.max(abs(a[:, 10]-(a[:, 1]+h*a[:, 4])))),
                 clipped_samples=clips, tail=None)
    if not terminal:
        tail = a[a[:, 0] >= spec['duration']-spec['tail_seconds']]
        if len(tail) < round(spec['tail_seconds']/h)-1:
            raise AssertionError('Incomplete tail')
        entry['tail'] = dict(production=moments(tail[:, 1]), reference=moments(tail[:, 11]),
                             nu_mean=float(np.mean(tail[:, 6])), virtual_mean=float(np.mean(tail[:, 7])) if mode == 2 else None,
                             max_bias_relation_error=float(np.max(abs(tail[:, 1]-tail[:, 13]))))
        if mode == 2 and scenario in ('ideal', 'ramp'):
            if entry['tail']['max_bias_relation_error'] > 5e-5:
                raise AssertionError(('bias relation', entry))
        if scenario == 'saturation' and clips == 0:
            raise AssertionError('Saturation scenario did not clip')
    elif abs(x) >= 1e-7 or abs(xd) >= 1e-7:
        raise AssertionError('Zero-disturbance terminal criterion')
    if mode == 2 and entry['max_double_trajectory_abs_error'] > 2e-4:
        raise AssertionError(('double trajectory', entry))
    return entry


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--library', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    kernel = Kernel(args.library)
    result = dict(success=False, cases=[], library_sha256=digest(args.library),
                  scope='Offline development; no flight, no Proper-ISTA, no production protection',
                  tolerances=dict(local_scaled=2e-6, ista_trajectory_abs=2e-4, bias_abs=5e-5))
    write_json(out/'planned_cases.json', case_grid())
    try:
        for n, spec in enumerate(case_grid()):
            print(f'case {n+1}/{len(case_grid())}: {spec}', flush=True)
            entry = simulate(kernel, spec, out/f'case_{n:03}.npz')
            write_json(out/f'case_{n:03}.json', entry)
            result['cases'].append(entry)
        result['success'] = True
    except Exception as exc:
        result['failure'] = repr(exc)
        raise
    finally:
        result['production_updates'] = sum(r['steps'] for r in result['cases'])
        write_json(out/'summary.json', result)


if __name__ == '__main__':
    main()
