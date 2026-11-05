"""Non-authorizing MODE4 composition around the final R03 scientific chain.

This is a callable OFFLINE binding, not a production runner/qualification.
No old mode/job/log is relabelled. All new-mode components run on actual MODE4
fields; unchanged old modes delegate to the original final checker. Targets
reuse the same X/Z/H/V shapes with only a private explicit mode-domain update.
"""
from pathlib import Path
import types

import numpy as np

import analyzer
import configuration
from dependencies import check_pins, final_analysis


def clone(function, **bindings):
    copied = types.FunctionType(function.__code__, dict(function.__globals__, **bindings),
                               function.__name__, function.__defaults__, function.__closure__)
    copied.__kwdefaults__ = function.__kwdefaults__
    return copied


def spec(job):
    chain = final_analysis()
    if job.get('gate') not in chain.targets.SPECS:
        raise ValueError('Unknown inherited task gate')
    task, axes, test, duration = chain.targets.SPECS[job['gate']]
    mode = job.get('mode')
    if type(mode) is not int or mode not in (0, 3, 4):
        raise ValueError('RI02 new-mode chain admits only PID/R-STA/R-ISTA')
    configuration.validate(mode, job.get('axes'), job['parameters'], allowed_task_modes=(test,))
    if (job.get('task') != task or job.get('axes') != (axes if mode else 0)
            or job.get('divisor') != 1 or job.get('main_duration_s') != duration
            or job['parameters']['MPC_VCT_TEST'] != test):
        raise ValueError('Wrong exact task/axes/window/divisor')
    return task, axes, test, duration


def windows(job):
    duration = spec(job)[3]
    return [('first_half', 0, duration / 2), ('second_half', duration / 2, duration)]


def targets():
    original = final_analysis()._targets11
    namespace = original.__globals__
    return clone(original, spec=spec,
        check_waveform=clone(namespace['check_waveform'], spec=spec),
        check_position_sum=clone(namespace['check_position_sum'], spec=spec),
        attitude_match=clone(namespace['attitude_match'], spec=spec, windows=windows))


def components(status, selection, job, start, end, steady=False):
    spec(job)
    if job['mode'] in (0, 3):
        # Preserve original modes and scientific predicates. Do not turn 4 into3.
        return final_analysis()._components(status, selection, job, start, end, steady)
    result = analyzer.check(status, selection, job, start, end, steady=steady)
    qfull = analyzer.join(status, selection)
    mask = (status['timestamp'] >= start) & (status['timestamp'] < end)
    x = {k: v[mask] for k, v in status.items()}
    q = {k: v[mask] for k, v in qfull.items()}
    # Required inherited actual-inner checker, not just requested configuration.
    enabled = x['enabled'].astype(bool)
    final_analysis()._inherited.check_inner_evidence({k: v[enabled] for k, v in x.items()})
    for name in ('a_req', 'a_proxy', 'thrust'):
        analyzer.require(np.all(np.isfinite(analyzer.vector(x, name)[enabled])), 'Nonfinite actual output/proxy')
    proxy = analyzer.vector(x, 'thrust') * (9.80665 / x['hover_thrust'][:, None])
    proxy[:, 2] += 9.80665
    analyzer.require(np.allclose(proxy[enabled], analyzer.vector(x, 'a_proxy')[enabled], atol=5e-6, rtol=0),
                     'Actual thrust proxy differs; not measured acceleration')
    return dict(samples=len(x['timestamp']), cadence=result,
                sample_hz=(len(x['timestamp']) - 1) / ((x['timestamp_sample'][-1] - x['timestamp_sample'][0]) * 1e-6)), x, q


def build(checked_provenance, diagnostic_save):
    """Bind the WHOLE scientific engine, with zero authorization capability.

    The provenance callback must verify read-only inputs of an offline fixture;
    it cannot grant flight permission. The returned wrapper always writes a
    diagnostic_payload. Its inner boolean is only diagnostic_checks_complete.
    Relative prewarm/incremental/tail validation is invoked by the entry below.
    """
    chain = final_analysis()
    full = chain.full_analysis(checked_provenance, diagnostic_save)
    return clone(full, check_components=components, check_targets=targets(), spec=spec, windows=windows)


def full_offline_analysis(source, output, protocol, job):
    """Analyze a separately supplied MODE4 archive without accepting a flight.

    RI02 has no such real flight archive. This callable is tested through its
    real bound components/negative fixtures; a full MODE4 ULog run is NOT claimed.
    Inputs must be under a fresh external RI02 fixture area, never an old batch.
    """
    chain = final_analysis()
    source, output = Path(source).resolve(), Path(output).resolve()
    if job.get('mode') != 4 or protocol.get('stage') != 'RI02-offline' or protocol.get('flight_authorized') is not False:
        raise ValueError('Explicit non-authorizing MODE4 offline protocol required')
    if 'batch01' in source.parts or 'RI02' not in source.parts or 'experiments' not in source.parts:
        raise ValueError('Only new RI02 offline fixture sources; no old batch relabel')
    spec(job)
    from replay import snapshot
    import json
    before = snapshot(source)
    if not before:
        raise ValueError('Missing offline input evidence')
    chain._handoff.copy_sidecars(source, output)
    result = dict(diagnostic_only=True, accepted=False, flight_accepted=False,
                  execution_authority_granted=False, new_flights=0, dependency_sha256=check_pins())

    def provenance(run, p, j):
        if Path(run).resolve() != output or p != protocol or j != job:
            raise ValueError('Changed offline source binding')
        chain._handoff.copied_input_binding(source, output)
        # No qualified source, old budget or permission is inherited here.
        if json.loads((source / 'job.json').read_text()) != job:
            raise ValueError('Archive job differs from actual MODE4 request')
        result['prearm_preparation'] = chain.prearm_evidence(source)
        result['post_logger_warmup'] = chain.warmup_evidence(source)
        return dict(stage='RI02-offline', input_sha256=before, flight_authorized=False)

    def save(path, value):
        chain._inherited.save(path, chain._handoff.diagnostic_payload(value)
                              if Path(path).name == 'r03_metrics.json' else value)

    raw = build(provenance, save)(output, protocol, job)
    result.update(diagnostic_checks_complete=raw.get('accepted') is True, error=raw.get('error'),
                  input_sha256_before=before, input_sha256_after=snapshot(source))
    result['inputs_unchanged'] = result['input_sha256_before'] == result['input_sha256_after']
    if raw.get('accepted') is True:
        result['upstream'] = chain.upstream_evidence(source, raw)
    save(output / 'ri02_full_diagnostic.json', result)
    return result
