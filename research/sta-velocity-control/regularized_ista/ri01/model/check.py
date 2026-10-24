#!/usr/bin/env python3
"""RI01 independent numerical checks; no simulator or parameter-write API."""
import argparse
import csv
import ctypes as C
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import traceback
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
CORE = REPO / 'src/modules/mc_pos_control/PositionControl'
SOURCE = Path('/home/yr/Desktop/STA-ISTA-MATLAB-PX4')
CADENCE = HERE.parents[1] / 'ri00/results/cadence.json'
GAINS = {'XY': (.5, .1, .01, .4), 'Z': (2., 1., .02, 4.)}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1048576), b''):
            digest.update(data)
    return digest.hexdigest()


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def f32(value):
    return C.c_float(value).value


def next32(value, direction):
    # Boundary tests here need positive neighbors only.
    assert value > 0 and direction in (-1, 1)
    bits = struct.unpack('<I', struct.pack('<f', value))[0]
    return struct.unpack('<f', struct.pack('<I', bits + direction))[0]


def nonlinear(p, eps):
    rho = max(-1., min(1., p / eps))
    return rho, math.sqrt(max(abs(p), eps)) * rho


def solve(s, h, k1, k2, eps):
    """Monotonic binary64 bisection only: no production analytic branches."""
    if s == 0.:
        return 0.
    lo, hi = 0., abs(s)
    for _ in range(64):
        mid = (lo + hi) * .5
        rho, psi = nonlinear(mid, eps)
        value = mid + h * k1 * psi + h * h * k2 * rho
        if value > abs(s):
            hi = mid
        else:
            lo = mid
    return math.copysign((lo + hi) * .5, s)


def oracle(s, h, k1, k2, eps, nu):
    p = solve(s, h, k1, k2, eps)
    rho, psi = nonlinear(p, eps)
    candidate = nu - h * k2 * rho
    return (s, p, psi, rho, -k1 * psi + candidate, nu, candidate, h)


def residual(values, k1, k2, eps):
    s, p, _, _, a, nu, candidate, h = values
    rho, psi = nonlinear(p, eps)
    return max(abs(p - s - h * (a - nu)) / (1 + abs(p) + abs(s)),
               abs(candidate - nu + h * k2 * rho) / (1 + abs(nu)),
               abs(a + k1 * psi - candidate) / (1 + abs(a)))


class Kernel:
    def __init__(self, library, gains):
        self.lib = library
        self.handle = self.lib.ri01_create()
        for axis in range(3):
            assert self.lib.ri01_configure(self.handle, axis, *gains[:3]) == 1

    def close(self):
        if self.handle:
            self.lib.ri01_destroy(self.handle)
            self.handle = None

    def reset(self, nu, axis=0):
        assert self.lib.ri01_reset(self.handle, axis, nu) == 1

    def evaluate(self, v, vsp, h, axis=0):
        values = (C.c_double * 8)()
        status = self.lib.ri01_evaluate(self.handle, axis, v, vsp, h, values)
        return status, list(values)

    def commit(self, nu=None, axis=0):
        return self.lib.ri01_commit(self.handle, axis, int(nu is not None), nu or 0.)

    def state(self, axis=0):
        return self.lib.ri01_state(self.handle, axis)


def load_library(path):
    lib = C.CDLL(str(path))
    lib.ri01_create.argtypes = []
    lib.ri01_create.restype = C.c_void_p
    lib.ri01_destroy.argtypes = [C.c_void_p]
    lib.ri01_destroy.restype = None
    lib.ri01_configure.argtypes = [C.c_void_p, C.c_int, C.c_float, C.c_float, C.c_float]
    lib.ri01_configure.restype = C.c_int
    lib.ri01_reset.argtypes = [C.c_void_p, C.c_int, C.c_float]
    lib.ri01_reset.restype = C.c_int
    lib.ri01_evaluate.argtypes = [C.c_void_p, C.c_int, C.c_float, C.c_float, C.c_float,
                                 C.POINTER(C.c_double)]
    lib.ri01_evaluate.restype = C.c_int
    lib.ri01_commit.argtypes = [C.c_void_p, C.c_int, C.c_int, C.c_float]
    lib.ri01_commit.restype = C.c_int
    lib.ri01_state.argtypes = [C.c_void_p, C.c_int]
    lib.ri01_state.restype = C.c_float
    return lib


def grid(lib):
    families = dict(GAINS, source_XY=(3., 1., .005, 1.7), source_Z=(20., 40., .01, 6.))
    worst_error = worst_residual = worst_reference_residual = 0.
    count = 0
    for name, gains in families.items():
        k1, k2, eps, _ = map(f32, gains)
        core = Kernel(lib, gains)
        try:
            for dt in (.002, .008, .012, .04):
                h = f32(dt)
                # This is only a boundary input constructor, not an output reference.
                b = f32(f32(eps + f32(f32(h * k1) * f32(math.sqrt(eps))))
                        + f32(f32(h * h) * k2))
                positive = [1e-12, eps, b, next32(b, -1), next32(b, 1), .2, 2.]
                errors = [0.] + [sign * value for value in positive for sign in (-1, 1)]
                for s in errors:
                    for nu in (-.3, 0., .3):
                        core.reset(nu)
                        status, actual = core.evaluate(s, 0., h)
                        assert status == 0, (name, h, s, nu, status)
                        reference = oracle(f32(s), h, k1, k2, eps, f32(nu))
                        error = max(abs(x-y)/(1+abs(y)) for x, y in zip(actual, reference))
                        r = residual(actual, k1, k2, eps)
                        rr = residual(reference, k1, k2, eps)
                        worst_error = max(worst_error, error)
                        worst_residual = max(worst_residual, r)
                        worst_reference_residual = max(worst_reference_residual, rr)
                        assert error <= 3e-6 and r <= 3e-6 and rr <= 2e-12
                        assert core.commit() == 0
                        count += 1
        finally:
            core.close()
    return dict(cases=count, max_scaled_candidate_error=worst_error,
                max_scaled_three_equation_residual=worst_residual,
                max_scaled_oracle_residual=worst_reference_residual,
                tolerance=3e-6, oracle_tolerance=2e-12)


def fixtures(lib):
    path = SOURCE / 'tests/matlab/controller_reference.csv'
    before = sha(path)
    total = compared = protected = skipped = 0
    maximum = [0., 0., 0., 0.]
    with path.open() as stream:
        for raw in csv.DictReader(stream):
            row = {key: float(value) for key, value in raw.items()}
            total += 1
            if row['algorithm'] != 1.:
                skipped += 1
                continue
            gains = row['k1'], row['k2'], row['epsilon'], row['nu_max']
            core = Kernel(lib, gains)
            try:
                core.reset(row['nu'])
                status, values = core.evaluate(-row['error'], 0., row['dt'])
                assert status == 0, (total, status)
                correction, nu, candidate = values[4:7]
                # Isolated reconstruction of original wrapper; NOT PX4 protection.
                raw_output = correction + row['accel_ff']
                applied_output = max(row['lo'], min(row['hi'], raw_output))
                freeze = ((raw_output > row['hi'] and candidate > nu)
                          or (raw_output < row['lo'] and candidate < nu))
                applied_nu = max(-row['nu_max'], min(row['nu_max'], nu if freeze else candidate))
                actual = correction, raw_output, applied_output, applied_nu
                expected = (row['expected_raw'] - row['accel_ff'], row['expected_raw'],
                            row['expected_limited'], row['expected_next'])
                for index, (a, b) in enumerate(zip(actual, expected)):
                    error = abs(a-b)/(1+abs(b))
                    maximum[index] = max(maximum[index], error)
                    assert error <= 3e-5, (total, index, a, b, error)
                assert core.commit(applied_nu) == 0
                assert abs(core.state()-row['expected_next']) <= 3e-5*(1+abs(row['expected_next']))
                protected += int(freeze or applied_nu != candidate or applied_output != raw_output)
                compared += 1
            finally:
                core.close()
    assert sha(path) == before and compared > 0
    return dict(path=str(path), sha256=before, total_csv_rows=total, rista_rows=compared,
                old_sta_rows_not_counted=skipped, protected_wrapper_rows=protected,
                max_scaled_errors=dict(zip(('correction','raw','limited','applied_nu'), maximum)),
                tolerance=3e-5, matlab_executed=False,
                mapping='s=-error; nu unchanged; remove FF for pure-core check; then independently reconstruct original wrapper')


def lag_step(velocity, first, second, command, disturbance, h):
    t1, t2 = .06, .02
    e1, e2 = math.exp(-h/t1), math.exp(-h/t2)
    integral = (command*h + (second-command)*t2*(1-e2)
                + (first-command)*t1/(t1-t2)*(t1*(1-e1)-t2*(1-e2)))
    next_second = (command + (second-command)*e2
                   + (first-command)*t1/(t1-t2)*(e1-e2))
    next_first = command + (first-command)*e1
    return velocity + integral + disturbance*h, next_first, next_second


def scenario_list():
    cases = [dict(kind='constant', d=d, nu0=nu)
             for d in (-.15, 0., .15) for nu in (-.1, 0., .1)]
    cases += [dict(kind='ramp', d=.03, ramp=r, nu0=.1) for r in (-.002, .002)]
    cases += [dict(kind=kind, d=.15, nu0=.1)
              for kind in ('target_ff', 'measurement_noise', 'two_stage_lag', 'lag_and_noise')]
    cases += [dict(kind='limited', d=.15, nu0=0., limit=limit) for limit in (.3, .05)]
    assert len(cases) == 17
    return cases


def closed_loops(lib, output):
    cadence = json.loads(CADENCE.read_text())
    delta = cadence['delta_us']
    assert len(delta) == 6399
    assert hashlib.sha256(struct.pack('<'+'q'*len(delta), *delta)).hexdigest() == cadence['delta_sha256']
    timebases = {'fixed_8ms': [.008], 'fixed_12ms': [.012],
                 'measured_sequence': [x*1e-6 for x in delta]}
    results = []
    total_steps = 0
    for family, gains in GAINS.items():
        for timing, steps in timebases.items():
            for case in scenario_list():
                identifier = f'{family}_{timing}_{len(results)+1:03d}'
                core = Kernel(lib, gains)
                core.reset(case['nu0'])
                k1, k2, eps, cap = gains
                velocity, reference_velocity = .05, .05
                reference_nu = case['nu0']
                lag1 = lag2 = ref_lag1 = ref_lag2 = 0.
                t = 0.
                rows = []
                max_error = 0.
                protection_steps = 0
                exhausted = None
                try:
                    while t < 60. - 1e-9:
                        h = steps[len(rows) % len(steps)]
                        target = .1*math.sin(.4*t) if case['kind'] == 'target_ff' else 0.
                        next_target = .1*math.sin(.4*(t+h)) if case['kind'] == 'target_ff' else 0.
                        ff = (next_target-target)/h
                        d = case['d'] + case.get('ramp', 0.)*(t+.5*h)
                        noisy = case['kind'] in ('measurement_noise', 'lag_and_noise')
                        noise = .003*math.sin(17*t)+.002*math.cos(29*t) if noisy else 0.
                        before = core.state()
                        status, actual = core.evaluate(velocity+noise, target, h)
                        if status != 0:
                            assert (case['kind'] == 'constant' and case['d'] == 0.
                                    and max(abs(velocity-target), abs(before)) < 1e-30
                                    and max(abs(reference_velocity-target), abs(reference_nu)) < 1e-28), (
                                        identifier, t, status, velocity, before)
                            assert core.state() == before
                            exhausted = dict(time=t, status=status, last_velocity=velocity,
                                             last_nu=before, reference_velocity=reference_velocity,
                                             reference_nu=reference_nu, state_unchanged=True)
                            break
                        ref = oracle(reference_velocity+noise-target, h, k1, k2, eps, reference_nu)
                        correction, nu_before, candidate = actual[4:7]
                        ref_correction, ref_before, ref_candidate = ref[4:7]
                        applied, ref_applied = correction, ref_correction
                        limit = case.get('limit')
                        freeze = ref_freeze = False
                        if limit is not None:
                            applied = max(-limit, min(limit, correction))
                            ref_applied = max(-limit, min(limit, ref_correction))
                            freeze = ((correction > limit and candidate > nu_before)
                                      or (correction < -limit and candidate < nu_before))
                            ref_freeze = ((ref_correction > limit and ref_candidate > ref_before)
                                          or (ref_correction < -limit and ref_candidate < ref_before))
                        applied_nu = max(-cap, min(cap, nu_before if freeze else candidate))
                        reference_nu = max(-cap, min(cap, ref_before if ref_freeze else ref_candidate))
                        protected = applied != correction or applied_nu != candidate
                        protection_steps += int(protected)
                        assert core.commit(applied_nu) == 0
                        if case['kind'] in ('two_stage_lag', 'lag_and_noise'):
                            velocity, lag1, lag2 = lag_step(velocity, lag1, lag2, applied+ff, d, h)
                            reference_velocity, ref_lag1, ref_lag2 = lag_step(
                                reference_velocity, ref_lag1, ref_lag2, ref_applied+ff, d, h)
                        else:
                            velocity += h*(applied+ff+d)
                            reference_velocity += h*(ref_applied+ff+d)
                        assert all(math.isfinite(x) for x in (*actual, velocity, reference_velocity, reference_nu))
                        max_error = max(max_error, abs(velocity-reference_velocity))
                        assert max_error <= 2e-4, (identifier, t, max_error)
                        rows.append((t+h, h, velocity-next_target, reference_velocity-next_target,
                                     actual[1], correction, applied, core.state(), candidate, ff, d,
                                     int(not protected)))
                        total_steps += 1
                        t += h
                finally:
                    core.close()
                assert rows
                duration = rows[-1][0]
                tail = [row for row in rows if row[0] > duration-10.]
                weight = sum(row[1] for row in tail)
                mean = sum(row[1]*row[2] for row in tail)/weight
                rmse = math.sqrt(sum(row[1]*row[2]**2 for row in tail)/weight)
                expected = None
                conclusion = 'finite_trajectory_consistency_only'
                if exhausted is not None:
                    conclusion = 'numeric_domain_exhausted_not_full_60s'
                elif timing != 'measured_sequence' and case['kind'] == 'constant':
                    assert abs(mean) <= 2e-5, (identifier, mean)
                    conclusion = 'fixed_h_ideal_constant_equilibrium_checked'
                elif timing != 'measured_sequence' and case['kind'] == 'ramp':
                    h = steps[0]
                    expected = case['ramp']*(eps+h*k1*math.sqrt(eps)+h*h*k2)/k2
                    assert abs(mean-expected) <= 2e-5, (identifier, mean, expected)
                    conclusion = 'fixed_h_layer_ramp_bias_checked'
                elif case.get('limit') == .05:
                    assert rows[-1][2] > 4.
                    conclusion = 'infeasible_actuation_not_convergent'
                path = output / (identifier+'.csv')
                with path.open('x') as stream:
                    writer = csv.writer(stream)
                    writer.writerow(('t','h','error','reference_error','p','ideal_correction',
                                     'applied_correction','applied_nu','ideal_nu','ff','disturbance','strict_implicit'))
                    writer.writerows(rows)
                results.append(dict(id=identifier, family=family, gains=gains, timing=timing, scenario=case,
                                    planned_duration_s=60., executed_duration_s=duration, steps=len(rows),
                                    max_double_reference_velocity_difference=max_error,
                                    tail_time_weighted_mean=mean, tail_time_weighted_rmse=rmse,
                                    ramp_theory=expected, protection_steps=protection_steps,
                                    numeric_domain_exhaustion=exhausted, conclusion=conclusion,
                                    trajectory=dict(path=str(path), bytes=path.stat().st_size, sha256=sha(path))))
                print(identifier, conclusion, f'mean={mean:.9g} diff={max_error:.3g}', flush=True)
    assert len(results) == 102
    return dict(trajectories=results, count=len(results), kernel_updates=total_steps,
                actual_cadence_json_sha256=sha(CADENCE), actual_cadence_delta_sha256=cadence['delta_sha256'],
                matlab_executed=False, simulator_executed=False, new_flight_seeds=0,
                independent_double_reference=True, not_independent_statistical_samples=True)


class OracleTests(unittest.TestCase):
    def test_root_residual_and_odd_symmetry(self):
        for s in (0., 1e-12, .001, .02, .5, 10.):
            positive = oracle(s, .012, .5, .1, .01, .13)
            self.assertLess(residual(positive, .5, .1, .01), 2e-12)
            self.assertEqual(solve(-s, .012, .5, .1, .01), -positive[1])

    def test_state_used_in_current_output(self):
        values = oracle(.02, .012, .5, .1, .01, .13)
        self.assertNotEqual(values[6], values[5])
        self.assertAlmostEqual(values[4], -.5*values[2]+values[6], places=15)

    def test_ff_once_and_ned_sign(self):
        positive = oracle(.05, .008, .5, .1, .01, 0.)
        self.assertLess(positive[4], 0.)
        self.assertEqual(positive[4]+.3-positive[4], .3)

    def test_lag_exact_equilibrium(self):
        for h in (.008, .012):
            v, a, b = lag_step(.2, .3, .3, .3, -.3, h)
            self.assertAlmostEqual(v, .2, places=15)
            self.assertAlmostEqual(a, .3, places=15)
            self.assertAlmostEqual(b, .3, places=15)

    def test_lag_short_step_composition(self):
        whole = lag_step(.2, -.1, .4, .3, -.2, .012)
        half = lag_step(.2, -.1, .4, .3, -.2, .006)
        halves = lag_step(*half, .3, -.2, .006)
        for x, y in zip(whole, halves):
            self.assertAlmostEqual(x, y, places=14)

    def test_protected_state_does_not_restore_implicit_solution(self):
        values = list(oracle(.2, .012, .5, .1, .01, .1))
        self.assertLess(residual(values, .5, .1, .01), 2e-12)
        values[6] = values[5]
        self.assertGreater(residual(values, .5, .1, .01), 1e-5)


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    commands = []
    source_paths = list(HERE.glob('*.py')) + list(HERE.glob('*.cpp')) + [HERE/'SPEC_CN.md', CADENCE,
        CORE/'RegularizedIstaVelocityControl.cpp', CORE/'RegularizedIstaVelocityControl.hpp',
        SOURCE/'tests/matlab/controller_reference.csv', SOURCE/'tests/matlab/export_controller_reference.m']
    fingerprints = {str(p): dict(sha256=sha(p), bytes=p.stat().st_size) for p in source_paths}
    save(output/'inputs.json', fingerprints)
    def command(argv, cwd=REPO):
        result = subprocess.run(argv, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        path = output/f'command_{len(commands)+1:02d}.log'
        with path.open('x') as stream:
            stream.write(result.stdout)
        commands.append(dict(argv=argv, cwd=str(cwd), exit_code=result.returncode,
                             output=str(path), sha256=sha(path)))
        save(output/f'command_{len(commands):02d}.json', commands[-1])
        if result.returncode:
            raise RuntimeError(f'command failed: {argv}: {result.stdout}')
        return result.stdout
    try:
        command(['git','branch','--show-current'])
        command(['git','rev-parse','HEAD'])
        command(['g++','--version'])
        command(['sha256sum','--check','SHA256SUMS.txt'], SOURCE)
        library = output/'ri01_model_bridge.so'
        command(['g++','-std=c++14','-O2','-Wall','-Wextra','-Werror','-pedantic-errors',
                 '-fPIC','-shared','-I'+str(CORE), str(HERE/'kernel_bridge.cpp'),
                 str(CORE/'RegularizedIstaVelocityControl.cpp'), '-o', str(library)])
        with (output/'oracle_tests.log').open('x') as stream:
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(OracleTests))
        assert result.testsRun == 6 and result.wasSuccessful()
        lib = load_library(library)
        one_step = grid(lib)
        save(output/'grid.json', one_step)
        saved_fixture = fixtures(lib)
        save(output/'fixtures.json', saved_fixture)
        objects = closed_loops(lib, output)
        save(output/'objects.json', objects)
        assert all(sha(path) == entry['sha256'] for path, entry in fingerprints.items()), 'inputs changed during run'
        summary = dict(status='passed', exit_code=0, commands=commands, oracle_tests=result.testsRun,
                       grid=one_step, fixture=saved_fixture, object_trajectories=objects['count'],
                       kernel_updates=objects['kernel_updates'],
                       numeric_domain_exhaustions=sum(x['numeric_domain_exhaustion'] is not None for x in objects['trajectories']),
                       infeasible_counterexamples=sum(x['conclusion']=='infeasible_actuation_not_convergent' for x in objects['trajectories']),
                       max_object_difference=max(x['max_double_reference_velocity_difference'] for x in objects['trajectories']),
                       matlab_available=shutil.which('matlab'), matlab_executed=False,
                       no_flight=True, no_new_seed=True, inputs_unchanged=True,
                       library_sha256=sha(library), python=sys.version)
        save(output/'summary.json', summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    except BaseException as error:
        save(output/'failure.json', dict(type=type(error).__name__, error=str(error),
                                        traceback=traceback.format_exc(), commands=commands, exit_code=1))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.output)
