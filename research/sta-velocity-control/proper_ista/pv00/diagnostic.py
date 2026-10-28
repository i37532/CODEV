"""PV00 fixed finite OFAT matrix. Default dry run; no flight API."""
import argparse
import gzip
import json
import math
import struct
from pathlib import Path

from common import CADENCE, HERE, ROOT, analysis, command, fresh, probe, save, sha


def manifest():
    cases = []
    for name in probe.CONFIGS:
        base = dict(algorithm=name, period=[10000], lag_scale=0., noise_scale=0., noise_frequency=None)
        for scale in (0., .25, .5, 1., 2.):
            cases.append(dict(base, group='lag', value=scale, lag_scale=scale))
        for scale in (0., .25, 1., 2.):
            cases.append(dict(base, group='noise_amplitude', value=scale, noise_scale=scale))
        for hz in (3., 13., 29., 43.):
            cases.append(dict(base, group='noise_frequency', value=hz, noise_scale=1., noise_frequency=hz))
        for period in ([4000], [8000], [10000], [12000], [16000], [8000, 12000]):
            cases.append(dict(base, group='period', value=period, period=period, lag_scale=1.))
        for kind, lag, noise in (('ideal', 0., 0.), ('lag', 1., 0.), ('noise', 0., 1.), ('lag_noise', 1., 1.)):
            cases.append(dict(base, group='recorded', value=kind, lag_scale=lag, noise_scale=noise, period=None))
    assert len(cases) == 69
    return [dict(case, id=f'd{i:03d}') for i, case in enumerate(cases, 1)]


def cascade(state, command_value, h, scale):
    """Analytic ZOH integral; independently checked against RK4 in tests."""
    if scale == 0:
        return [command_value, command_value], h * command_value
    t1, t2 = .06 * scale, .02 * scale
    e1, e2 = math.exp(-h/t1), math.exp(-h/t2)
    x1, x2 = state
    c = (x1-command_value)*t1/(t1-t2)
    integral = command_value*h+(x2-command_value)*t2*(1-e2)+c*(t1*(1-e1)-t2*(1-e2))
    return [command_value+(x1-command_value)*e1,
            command_value+(x2-command_value)*e2+c*(e1-e2)], integral


def periods(case, recorded):
    values = recorded if case['period'] is None else case['period']
    sequence, total = [], 0
    while total < 36_000_000:
        if case['period'] is None and len(sequence) >= len(values):
            raise ValueError('recorded sequence cannot be looped')
        h = values[len(sequence) % len(values)]
        if not isinstance(h, int) or not 2000 <= h <= 40000:
            raise ValueError('invalid raw sample interval')
        sequence.append(h)
        total += h
    if total != 36_000_000:
        raise ValueError('no complete exact 36s prefix; no clipped final sample')
    return sequence


def verify_cadence(out):
    import numpy as np
    from pyulog import ULog
    saved = json.loads(CADENCE.read_text())
    path = Path(saved['source_log']['archive'])
    if not path.is_file():
        raise FileNotFoundError('required raw cadence ULog missing; do not call saved deltas a fresh replay')
    assert sha(path) == saved['source_log']['sha256']
    u = ULog(str(path), message_name_filter_list=['sta_velocity_ctrl_status'])
    assert not u.dropouts and not u.file_corruption
    d = u.get_dataset('sta_velocity_ctrl_status').data
    ix = np.flatnonzero((d['excitation_time'] >= 0) & (d['excitation_time'] < 64)
                       & (d['effective_mode'] == 3) & (d['active_axes'] == 7))
    assert len(ix) == 6400 and np.all(np.diff(ix) == 1)
    sample = d['timestamp_sample'][ix].astype(np.int64)
    delta = np.diff(sample).tolist()
    assert delta == saved['delta_us']
    assert np.all(np.diff(d['publish_seq'][ix].astype(np.int64)) == 1)
    for field, value in (('inner_mode', 0), ('inner_axes', 0), ('inner_divisor', 1)):
        assert np.all(d[field][ix] == value)
    assert np.max(np.abs(d['raw_dt'][ix[1:]]-np.array(delta)*1e-6)) < 1e-8
    assert sha(path) == saved['source_log']['sha256']
    save(out/'cadence.json', dict(source=saved['source_log'], stored_sha256=sha(CADENCE),
                                delta_us=delta, rows=len(ix), raw_redecoded=True,
                                delta_sha256=__import__('hashlib').sha256(struct.pack('<'+'q'*len(delta), *delta)).hexdigest()))
    return delta


def trajectory(library, case, recorded, out):
    mode, nominal = probe.CONFIGS[case['algorithm']]
    params = tuple(map(probe.f32, nominal))
    core = probe.Kernel(library, mode, params)
    assert core.reset(.1)
    v = vr = .03
    nu_r = .1
    lag = [0., 0.]
    lag_r = [0., 0.]
    full, tail, reference_tail = probe.Metrics(), probe.Metrics(), probe.Metrics()
    max_step = max_residual = max_closed = 0.
    sliding = tail_sliding = tail_updates = us = updates = 0
    stop = None
    trace = out / (case['id'] + '.jsonl.gz')
    try:
        with gzip.open(trace, 'wt') as stream:
            for hu in periods(case, recorded):
                t, h = us/1e6, hu/1e6
                sp, _ = probe.target(t)
                if case['noise_frequency'] is None:
                    noise = case['noise_scale']*(.001*math.sin(2*math.pi*13*t)+.0005*math.sin(2*math.pi*29*t))
                else:
                    noise = .001*math.sin(2*math.pi*case['noise_frequency']*t)
                status, c = core.evaluate(v+noise, sp, h)
                if status:
                    stop = dict(t=t, status=status, velocity=v, target=sp, noise=noise, h=h, nu=core.state())
                    break
                same = probe.reference(mode, params, c[0], c[3], probe.f32(h))
                err = max(abs(c[2]-same[1])/(1+abs(same[1])), abs(c[4]-same[2])/(1+abs(same[2])))
                if mode:
                    err = max(err, abs(c[1]-same[0])/max(1e-30, abs(same[0])), abs(c[5]-same[3]))
                residual = probe.candidate_residual(mode, params, c, probe.f32(h))
                max_step, max_residual = max(max_step, err), max(max_residual, residual)
                if err > 2e-6 or residual > 2e-6:
                    raise AssertionError(('independent mismatch', case['id'], t, err, residual))
                _, ar, nr, _ = probe.reference(mode, nominal, vr+noise-sp, nu_r, h)
                assert core.commit()
                full.add(h, v-sp, v+noise-sp, c[2], c[4], False)
                if us >= 12_000_000:
                    tail.add(h, v-sp, v+noise-sp, c[2], c[4], False)
                    reference_tail.add(h, vr-sp, vr+noise-sp, ar, nr, False)
                    tail_sliding += int(mode == 2 and c[6] == 2)
                    tail_updates += 1
                sliding += int(mode == 2 and c[6] == 2)
                item = dict(t=t, h=h, v=v, v_sp=sp, measurement=v+noise, s=c[0],
                            p=c[1] if math.isfinite(c[1]) else None, a_ideal=c[2], a_applied=c[2],
                            nu_before=c[3], nu_candidate=c[4], nu_applied=core.state(),
                            constrained=False, branch=c[6], reference_velocity=vr, reference_nu=nu_r)
                stream.write(json.dumps(item, allow_nan=False, separators=(',', ':'))+'\n')
                lag, integral = cascade(lag, c[2], h, case['lag_scale'])
                lag_r, integral_r = cascade(lag_r, ar, h, case['lag_scale'])
                v += integral + .15*h
                vr += integral_r + .15*h
                nu_r = nr
                max_closed = max(max_closed, abs(v-vr))
                assert all(math.isfinite(x) for x in (v, vr, nr))
                updates += 1
                us += hu
    finally:
        core.close()
    result = dict(case=case, stop=stop, seconds=us/1e6, updates=updates,
                  full=full.result(), tail=tail.result(), double_tail=reference_tail.result(),
                  max_step=max_step, max_residual=max_residual, max_closed=max_closed,
                  sliding_fraction=sliding/updates if mode == 2 and updates else None,
                  tail_sliding_fraction=tail_sliding/tail_updates if mode == 2 and tail_updates else None,
                  trace=str(trace), trace_sha256=sha(trace))
    # A separate summation path reads what was actually stored, not the accumulator.
    with gzip.open(trace, 'rt') as stream:
        points = [json.loads(line) for line in stream]
    analysis.verify(result['full'], analysis.aggregate(points))
    analysis.verify(result['tail'], analysis.aggregate([p for p in points if p['t'] >= 12]))
    result['independent_metric_replay'] = True
    return result


def linear_mechanism():
    import numpy as np
    rows = []
    for h in (.004, .008, .010, .012, .016):
        for scale in (0., .25, .5, 1., 2.):
            def advance(x):
                s, nu, x1, x2 = x
                a = nu-2*s/h
                lag, integ = cascade([x1, x2], a, h, scale)
                return np.array([s+integ, nu-s/h, *lag])
            matrix = np.column_stack([advance(x) for x in np.eye(4)])
            roots = np.linalg.eigvals(matrix)
            rows.append(dict(h=h, lag_scale=scale, matrix=matrix.tolist(),
                             eigenvalues=[[float(x.real), float(x.imag)] for x in roots],
                             radius=float(max(abs(roots)))))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--library', type=Path, default=ROOT/'original01/kernels.so')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps(dict(flight_authorized=False, trajectories=69, manifest=manifest()), indent=2))
        return
    if args.output is None:
        parser.error('new external --output required')
    out = fresh(args.output)
    result = dict(success=False, flight_authorized=False, new_flights=0, manifest=manifest(), rows=[],
                  protocol_sha256=sha(HERE/'PROTOCOL_CN.md'), library_sha256=sha(args.library),
                  sources={str(p):sha(p) for p in [Path(__file__), HERE/'common.py', probe.HERE/'probe.py']})
    save(out/'summary.json', result)
    try:
        recorded = verify_cadence(out)
        result['linear_mechanism'] = linear_mechanism()
        for case in result['manifest']:
            row = trajectory(args.library, case, recorded, out)
            result['rows'].append(row)
            save(out/'summary.json', result)
            print(case['id'], case['algorithm'], case['group'], case['value'], row['seconds'], flush=True)
        result['success'] = len(result['rows']) == 69
        result['complete'] = sum(r['stop'] is None for r in result['rows'])
        result['updates'] = sum(r['updates'] for r in result['rows'])
    except Exception as error:
        result['error'] = repr(error)
        raise
    finally:
        save(out/'summary.json', result)


if __name__ == '__main__':
    main()
