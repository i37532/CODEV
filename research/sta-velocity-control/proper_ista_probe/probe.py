#!/usr/bin/env python3
"""Research-only three-core scalar comparison. Default is a no-write dry run."""
import argparse
import ctypes
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
VELOCITY = REPO / 'src/modules/mc_pos_control/PositionControl'
RATE = REPO / 'src/modules/mc_rate_control/StaRateControl'
CONFIGS = {'rsta': (0, (2., 1., .02)), 'rista': (1, (2., 1., .02)),
           'proper': (2, (2., 1., 0.))}
PERIODS = {'8ms': (8000,), '10ms': (10000,), '12ms': (12000,),
           'alternating8_12ms': (8000, 12000)}
SCENARIOS = ('constant_positive', 'constant_negative', 'zero_transient',
             'ramp_positive', 'ramp_negative', 'velocity_target', 'target_with_ff',
             'lag', 'noise', 'lag_noise', 'feasible_clipping', 'infeasible_clipping')
END_US = 36_000_000
PRODUCTION_PATHS = ['src', 'msg', 'Tools', 'sitl', 'ROMFS', 'boards', 'platforms',
                    'CMakeLists.txt', '.gitmodules']


def f32(x):
    return ctypes.c_float(x).value


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def shape(s, epsilon):
    rho = max(-1., min(1., s / epsilon))
    psi = s / math.sqrt(epsilon) if abs(s) <= epsilon else math.copysign(math.sqrt(abs(s)), s)
    return psi, rho


def reference(mode, params, s, nu, h):
    """Independent monotone solver; returns p, a, next_nu, xi/rho.

    Proper a comes from the prediction equation, not its production output
    expression. No production quadratic-root formula is copied here.
    """
    l1, l2, epsilon = params
    if not all(math.isfinite(x) for x in (l1, l2, epsilon, s, nu, h)):
        raise ValueError('nonfinite reference input')
    if h <= 0 or l1 <= 0 or l2 <= 0 or mode not in (0, 1, 2):
        raise ValueError('invalid reference configuration')
    if (mode == 2 and epsilon != 0) or (mode != 2 and epsilon <= 0):
        raise ValueError('algorithm/epsilon mismatch')
    if mode == 0:
        psi, rho = shape(s, epsilon)
        return s, nu - l1 * psi, nu - h * l2 * rho, rho
    q = h * h * l2
    if mode == 2 and abs(s) <= q:
        p, xi = 0., s / q
    else:
        # Subtract q once, before bisection: re-adding q in each comparison
        # loses root resolution at the first float outside the sliding region.
        rhs = abs(s) - q if mode == 2 else abs(s)
        lo, hi = 0., rhs
        for _ in range(100):
            mid = (lo + hi) / 2
            if mode == 2:
                value = mid + h * l1 * math.sqrt(mid)
            else:
                psi, rho = shape(mid, epsilon)
                value = mid + h * l1 * psi + q * rho
            if value < rhs:
                lo = mid
            else:
                hi = mid
        p = math.copysign((lo + hi) / 2, s)
        xi = math.copysign(1., s) if mode == 2 else shape(p, epsilon)[1]
    nxt = nu - h * l2 * xi
    a = (nxt if mode == 2 else nu) + (p - s) / h
    return p, a, nxt, xi


def candidate_residual(mode, params, c, h):
    """Scaled defining-equation and graph checks on the rounded C++ interface."""
    l1, l2, epsilon = params
    s, p, a, old, nxt, xi, branch = c
    def residual(lhs, *terms):
        return abs(lhs - sum(terms)) / max(1e-30, abs(lhs), *(abs(x) for x in terms))
    if mode == 0:
        psi, rho = shape(s, epsilon)
        return max(residual(a, -l1 * psi, old), residual(nxt, old, -h*l2*rho), abs(xi-rho))
    if mode == 1:
        psi, rho = shape(p, epsilon)
        # Check the implementation's branch label at its float-rounded
        # threshold, while the independent p root and equations remain double.
        a_step = f32(h*l1)
        b_step = f32(h*f32(h*l2))
        boundary = f32(f32(epsilon + f32(a_step*f32(math.sqrt(epsilon)))) + b_step)
        expected_branch = 0 if abs(s) <= boundary else 1
        if branch != expected_branch:
            raise AssertionError('R-ISTA branch identity mismatch')
        return max(residual(p, s, h*a, -h*old), residual(a, -l1*psi, nxt),
                   residual(nxt, old, -h*l2*rho), abs(xi-rho))
    expected_branch = 2 if abs(s) <= h*h*l2 else (1 if s > 0 else 3)
    if branch != expected_branch or abs(xi) > 1. or (p and xi != math.copysign(1., p)):
        raise AssertionError('Proper branch or inclusion mismatch')
    return max(residual(p, s, h*a, -h*nxt),
               residual(a, -l1*math.sqrt(abs(p))*xi, 2*nxt, -old),
               residual(nxt, old, -h*l2*xi))


class Kernel:
    def __init__(self, library, mode, params):
        self.lib = ctypes.CDLL(str(library))
        for name, args, result in (
            ('probe_create', [ctypes.c_int], ctypes.c_void_p),
            ('probe_destroy', [ctypes.c_void_p], None),
            ('probe_configure', [ctypes.c_void_p, ctypes.c_int] + [ctypes.c_float] * 3, ctypes.c_int),
            ('probe_reset', [ctypes.c_void_p, ctypes.c_int, ctypes.c_float], ctypes.c_int),
            ('probe_evaluate', [ctypes.c_void_p, ctypes.c_int] + [ctypes.c_float] * 3 +
             [ctypes.POINTER(ctypes.c_double)], ctypes.c_int),
            ('probe_commit', [ctypes.c_void_p, ctypes.c_int], ctypes.c_int),
            ('probe_commit_protected', [ctypes.c_void_p, ctypes.c_int, ctypes.c_float], ctypes.c_int),
            ('probe_state', [ctypes.c_void_p, ctypes.c_int], ctypes.c_float)):
            function = getattr(self.lib, name)
            function.argtypes, function.restype = args, result
        self.handle = self.lib.probe_create(mode)
        if not self.handle:
            raise ValueError('invalid mode')
        for axis in range(3):
            if not self.lib.probe_configure(self.handle, axis, *params):
                self.close()
                raise ValueError('invalid parameters')

    def close(self):
        if self.handle:
            self.lib.probe_destroy(self.handle)
            self.handle = None

    def reset(self, nu=0., axis=2):
        return bool(self.lib.probe_reset(self.handle, axis, nu))

    def evaluate(self, v, sp, h, axis=2):
        out = (ctypes.c_double * 7)()
        code = self.lib.probe_evaluate(self.handle, axis, v, sp, h, out)
        return code, list(out)

    def commit(self, applied=None, axis=2):
        if applied is None:
            return bool(self.lib.probe_commit(self.handle, axis))
        return bool(self.lib.probe_commit_protected(self.handle, axis, applied))

    def state(self, axis=2):
        return self.lib.probe_state(self.handle, axis)


def target(t):
    w, b = 2 * math.pi / 9, math.pi / 36
    v = .1 * math.sin(w * t) * math.sin(b * t) ** 2
    ff = .1 * (w * math.cos(w * t) * math.sin(b * t) ** 2 +
               b * math.sin(w * t) * math.sin(2 * b * t))
    return v, ff


def cascade(lag, command, h):
    """Exact two-lag ZOH states AND integrated acceleration (not endpoint Euler)."""
    tau1, tau2 = .06, .02
    e1, e2 = math.exp(-h / tau1), math.exp(-h / tau2)
    x1, x2 = lag
    coupling = (x1 - command) * tau1 / (tau1 - tau2)
    integral = (command * h + (x2 - command) * tau2 * (1 - e2) +
                coupling * (tau1 * (1 - e1) - tau2 * (1 - e2)))
    return [command + (x1 - command) * e1,
            command + (x2 - command) * e2 + coupling * (e1 - e2)], integral


def protect(a, nxt, old, scenario):
    if scenario not in ('feasible_clipping', 'infeasible_clipping'):
        return a, nxt, False
    limit = .25 if scenario == 'feasible_clipping' else .05
    applied = max(-limit, min(limit, a))
    freeze = (a > limit and nxt > old) or (a < -limit and nxt < old)
    state = max(-4., min(4., old if freeze else nxt))
    return applied, state, applied != a or state != nxt


class Metrics:
    def __init__(self):
        self.duration = self.squared = self.measured_squared = self.total = self.peak = 0.
        self.measured_total = self.measured_peak = 0.
        self.tv = self.output_peak = self.nu_peak = self.limit_time = 0.
        self.last = None
        self.samples = 0

    def add(self, h, error, measured, output, nu, limited):
        self.duration += h
        self.squared += h * error * error
        self.measured_squared += h * measured * measured
        self.measured_total += h * measured
        self.measured_peak = max(self.measured_peak, abs(measured))
        self.total += h * error
        self.peak = max(self.peak, abs(error))
        self.output_peak = max(self.output_peak, abs(output))
        self.nu_peak = max(self.nu_peak, abs(nu))
        self.limit_time += h * bool(limited)
        if self.last is not None:
            self.tv += abs(output - self.last)
        self.last = output
        self.samples += 1

    def result(self):
        if not self.duration:
            return None
        return dict(seconds=self.duration, samples=self.samples, rmse=math.sqrt(self.squared / self.duration),
                    measured_rmse=math.sqrt(self.measured_squared / self.duration), mean=self.total / self.duration,
                    measured_mean=self.measured_total / self.duration, measured_peak_error=self.measured_peak,
                    peak_error=self.peak, correction_tv_per_s=self.tv / self.duration,
                    peak_correction=self.output_peak, peak_nu=self.nu_peak,
                    constrained_fraction=self.limit_time / self.duration)


def theoretical(name, period, scenario):
    if not scenario.startswith('ramp_') or len(PERIODS[period]) != 1:
        return None
    h = PERIODS[period][0] / 1e6
    r = -.1 if scenario.endswith('negative') else .1
    if name == 'proper':
        return r * h * h
    base = r * .02
    return base if name == 'rsta' else r * (.02 + h * 2 * math.sqrt(.02) + h * h)


def trajectory(library, name, period, scenario, trace):
    mode, nominal = CONFIGS[name]
    params = tuple(map(f32, nominal))
    core = Kernel(library, mode, params)
    sign = -1 if scenario.endswith('negative') else 1
    v = vr = sign * .03
    nr = sign * .1
    assert core.reset(nr)
    lag, lagr = [0., 0.], [0., 0.]
    full, tail, reference_tail = Metrics(), Metrics(), Metrics()
    us = steps = 0
    maximum_step_difference = maximum_closed_difference = maximum_residual = 0.
    double_theory_deviation = float_theory_deviation = 0.
    theory = theoretical(name, period, scenario)
    status, stop = 'complete', None
    sliding = layer = 0
    try:
        with gzip.open(trace, 'wt', encoding='utf-8') as output:
            while us < END_US:
                hu = PERIODS[period][steps % len(PERIODS[period])]
                assert us + hu <= END_US
                t, h = us / 1e6, hu / 1e6
                dynamic = scenario not in SCENARIOS[:5]
                sp, derivative = target(t) if dynamic else (0., 0.)
                ff = derivative if scenario == 'target_with_ff' else 0.
                noise = (.001 * math.sin(2 * math.pi * 13 * t) +
                         .0005 * math.sin(2 * math.pi * 29 * t)) if scenario in ('noise', 'lag_noise') else 0.
                code, c = core.evaluate(v + noise, sp, h)
                if code:
                    status = 'core_domain_rejection'
                    stop = dict(t=t, code=code, velocity=v, target=sp, noise=noise, h=h, nu=core.state())
                    break
                same = reference(mode, params, c[0], c[3], f32(h))
                delta = max(abs(c[2] - same[1]) / (1 + abs(same[1])),
                            abs(c[4] - same[2]) / (1 + abs(same[2])))
                if mode:
                    delta = max(delta, abs(c[1] - same[0]) / max(1e-30, abs(same[0])), abs(c[5]-same[3]))
                equations = candidate_residual(mode, params, c, f32(h))
                maximum_residual = max(maximum_residual, equations)
                maximum_step_difference = max(maximum_step_difference, delta)
                if delta > 2e-6 or equations > 2e-6:
                    raise AssertionError(f'independent step mismatch {name}/{period}/{scenario}: {delta}')
                _, ar, nnr, _ = reference(mode, nominal, vr + noise - sp, nr, h)
                a, nxt, limited = protect(c[2], c[4], c[3], scenario)
                ar, nnr, limited_r = protect(ar, nnr, nr, scenario)
                if not core.commit(nxt if scenario.endswith('clipping') else None):
                    raise AssertionError('candidate commit rejected')
                full.add(h, v - sp, v + noise - sp, a, nxt, limited)
                if us >= 12_000_000:
                    tail.add(h, v - sp, v + noise - sp, a, nxt, limited)
                    reference_tail.add(h, vr - sp, vr + noise - sp, ar, nnr, limited_r)
                    if theory is not None:
                        double_theory_deviation = max(double_theory_deviation, abs(vr - sp - theory))
                        float_theory_deviation = max(float_theory_deviation, abs(v - sp - theory))
                if mode == 2:
                    sliding += int(c[6] == 2)
                else:
                    layer += int(abs(c[0] if mode == 0 else c[1]) <= params[2])
                disturbance = 0. if scenario == 'zero_transient' else sign * .15
                if scenario.startswith('ramp_'):
                    disturbance += sign * .1 * (t + h / 2)
                item = dict(t=t, h=h, v=v, v_sp=sp, measurement=v + noise, s=c[0],
                            p=c[1] if math.isfinite(c[1]) else None, a_ideal=c[2], a_applied=a,
                            nu_before=c[3], nu_candidate=c[4], nu_applied=core.state(),
                            ff=ff, disturbance_average=disturbance, constrained=limited,
                            strict_implicit=(not limited if mode else None), branch=c[6],
                            reference_velocity=vr, reference_nu=nr)
                output.write(json.dumps(item, separators=(',', ':'), allow_nan=False) + '\n')
                if scenario in ('lag', 'lag_noise'):
                    lag, integration = cascade(lag, a + ff, h)
                    lagr, integration_r = cascade(lagr, ar + ff, h)
                else:
                    integration, integration_r = h * (a + ff), h * (ar + ff)
                v += integration + h * disturbance
                vr += integration_r + h * disturbance
                nr = nnr
                maximum_closed_difference = max(maximum_closed_difference, abs(v - vr))
                if not all(math.isfinite(x) for x in (v, vr, nr, nxt)):
                    raise AssertionError('nonfinite object')
                steps += 1
                us += hu
    finally:
        core.close()
    return dict(algorithm=name, period=period, scenario=scenario, status=status, stop=stop,
                updates=steps, seconds=us / 1e6, full=full.result(), tail_12_36=tail.result(),
                independent_double_tail=reference_tail.result(), terminal_velocity=v,
                max_scaled_same_input_difference=maximum_step_difference,
                max_scaled_candidate_residual=maximum_residual,
                max_independent_closed_velocity_difference=maximum_closed_difference,
                theory_error=theory, max_double_theory_deviation=double_theory_deviation if theory is not None else None,
                max_float_theory_deviation=float_theory_deviation if theory is not None else None,
                sliding_fraction=sliding / steps if mode == 2 and steps else None,
                regularization_fraction=layer / steps if mode != 2 and steps else None,
                expected_tracking_failure=scenario == 'infeasible_clipping',
                trace=str(trace), trace_sha256=sha(trace))


def manifest():
    return [dict(algorithm=a, period=p, scenario=s) for a in CONFIGS for p in PERIODS for s in SCENARIOS]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps(dict(offline_only=True, flight_authorized=False, configs=CONFIGS,
                              duration_s=36, trajectory_count=len(manifest()), manifest=manifest()), indent=2))
        return 0
    if args.output is None:
        parser.error('--execute requires a NEW --output directory')
    out = args.output.resolve()
    if out == REPO or REPO in out.parents:
        parser.error('large evidence must be outside repository')
    out.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    removed = {key: env.pop(key) for key in list(env) if key.startswith('GTEST_')}
    receipt = dict(success=False, offline_only=True, flight_authorized=False, new_flights=0,
                   commands=[], rows=[], removed_gtest_env=removed, manifest=manifest())

    def command(name, argv):
        result = subprocess.run(argv, cwd=REPO, env=env, capture_output=True, text=True)
        log = out / (name + '.log')
        log.write_text(result.stdout + result.stderr)
        receipt['commands'].append(dict(name=name, argv=argv, exit_code=result.returncode,
                                        log=str(log), sha256=sha(log)))
        save(out / 'summary.json', receipt)
        if result.returncode:
            raise RuntimeError(f'{name} failed; output retained')
        return result.stdout

    try:
        receipt['entry_head'] = command('head', ['git', 'rev-parse', 'HEAD']).strip()
        receipt['branch'] = command('branch', ['git', 'branch', '--show-current']).strip()
        command('worktree', ['git', 'status', '--short', '--branch'])
        receipt['submodules'] = command('submodules', ['git', 'submodule', 'status', '--recursive'])
        dirty = command('submodule_worktrees', ['git', 'submodule', 'foreach', '--quiet', '--recursive', 'git status --porcelain'])
        if dirty.strip() or any(line[:1] != ' ' for line in receipt['submodules'].splitlines()):
            raise RuntimeError('submodule state mismatch')
        if command('production_diff_before', ['git', 'diff', receipt['entry_head'], '--', *PRODUCTION_PATHS]):
            raise RuntimeError('production changed')
        sources = [HERE / 'kernel_bridge.cpp', VELOCITY / 'RegularizedStaVelocityControl.cpp',
                   VELOCITY / 'RegularizedIstaVelocityControl.cpp', RATE / 'ProperIstaRateControl.cpp']
        inputs = sources + list(HERE.glob('*.py')) + list(HERE.glob('*.md')) + [HERE / 'kernel_bridge_test.cpp',
                  VELOCITY / 'RegularizedStaVelocityControl.hpp', VELOCITY / 'RegularizedIstaVelocityControl.hpp',
                  RATE / 'ProperIstaRateControl.hpp', RATE / 'StaRateControl.hpp']
        receipt['input_sha256'] = {str(p): sha(p) for p in inputs}
        for path in inputs:
            destination = out / 'source_snapshot' / path.relative_to(REPO)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        command('compiler', ['g++', '--version'])
        flags = ['g++', '-std=c++14', '-O2', '-Wall', '-Wextra', '-Werror', '-pedantic-errors',
                 '-I', str(VELOCITY), '-I', str(RATE)]
        library = out / 'kernels.so'
        command('compile_shared', flags + ['-shared', '-fPIC', *map(str, sources), '-o', str(library)])
        executable = out / 'kernel_bridge_test'
        command('compile_tests', flags + [*map(str, sources), str(HERE / 'kernel_bridge_test.cpp'), '-o', str(executable)])
        command('cpp_bridge_tests', [str(executable)])
        env['PROPER_VELOCITY_LIBRARY'] = str(library)
        command('python_tests', [sys.executable, '-B', str(HERE / 'test_probe.py'), '-v'])
        existing = command('existing_cpp', ['ctest', '--test-dir', 'build/px4_sitl_test', '-V', '-R',
                           'PositionControl|ControlMath|Takeoff|RateControl|Regularized|VelocityZ|VelocityRista|ProperIsta'])
        receipt['existing_cpp_cases'] = sum(map(int, re.findall(r'\[==========\] (\d+) tests? from .*? ran\.', existing)))
        if receipt['existing_cpp_cases'] <= 0:
            raise RuntimeError('no actual existing C++ tests')
        for item in manifest():
            name = '__'.join(item.values())
            row = trajectory(library, item['algorithm'], item['period'], item['scenario'], out / (name + '.jsonl.gz'))
            receipt['rows'].append(row)
            save(out / 'summary.json', receipt)
            print(name, row['status'], row['updates'], flush=True)
        if command('production_diff_after', ['git', 'diff', receipt['entry_head'], '--', *PRODUCTION_PATHS]):
            raise RuntimeError('production changed during run')
        for path, digest in receipt['input_sha256'].items():
            if sha(path) != digest:
                raise RuntimeError('input changed during run: ' + path)
        checks = [r for r in receipt['rows'] if r['theory_error'] is not None]
        receipt['theory_checks'] = dict(count=len(checks), passed=all(
            r['status'] == 'complete' and r['max_double_theory_deviation'] <= 1e-11 and
            (r['algorithm'] != 'proper' or r['max_float_theory_deviation'] <= 5e-7) for r in checks))
        counterexamples = [r for r in receipt['rows'] if r['expected_tracking_failure']]
        receipt['infeasible_checks_passed'] = len(counterexamples) == 12 and all(
            r['status'] == 'complete' and r['full']['constrained_fraction'] > 0 and abs(r['terminal_velocity']) > 2.
            for r in counterexamples)
        receipt.update(success=len(receipt['rows']) == 144 and receipt['theory_checks']['passed'] and
                       receipt['infeasible_checks_passed'],
                       complete_trajectories=sum(r['status'] == 'complete' for r in receipt['rows']),
                       rejected_trajectories=sum(r['status'] != 'complete' for r in receipt['rows']),
                       total_updates=sum(r['updates'] for r in receipt['rows']),
                       matlab_rerun=False, firmware_build=False,
                       note='Completion of diagnostics is not convergence, flight qualification or universal superiority.')
    except Exception as error:
        receipt['error'] = repr(error)
        raise
    finally:
        save(out / 'summary.json', receipt)
    print(json.dumps({key: receipt[key] for key in ('success', 'complete_trajectories', 'rejected_trajectories',
                                                   'total_updates', 'theory_checks', 'existing_cpp_cases')}))
    return 0 if receipt['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
