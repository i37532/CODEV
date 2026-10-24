#!/usr/bin/env python3
"""Read-only complete final-chain replay into a NEW diagnostic directory.

Historical verdicts/identities are never changed, no accepted receipt is made.
Old ESTA is permissible ONLY as an existing regression log, not a new group.
"""
import argparse
import copy
import json
from pathlib import Path
import traceback

from dependencies import OLD, check_pins, digest, final_analysis, load

SCIENCE = ('diagnostic', 'spectral_summary', 'host_cost', 'position_rmse', 'yaw_rmse', 'height',
           'lifecycle', 'pid_reconstruction', 'actual_output', 'rate_actuator', 'landing',
           'landing_health', 'mixer', 'first_invocation', 'exit', 'task_targets', 'height_task')


def exact(a, b):
    return json.dumps(a, sort_keys=True, separators=(',', ':'), allow_nan=True) == json.dumps(b, sort_keys=True, separators=(',', ':'), allow_nan=True)


def science_equal(key, actual, recorded, revision):
    """One audited descriptive-string migration; all values/types stay exact."""
    if key == 'task_targets' and revision == 'r03_revision09':
        old = 'unique exact publication intersection'
        new = 'complete equal-time groups in single-publisher order; exact payload and callback identity'
        if (recorded.get('attitude', {}).get('association') == old
                and actual.get('attitude', {}).get('association') == new):
            expected = copy.deepcopy(recorded)
            expected['attitude']['association'] = new
            return exact(actual, expected)
    return exact(actual, recorded)


def snapshot(source):
    return {str(p): digest(p) for p in sorted(Path(source).rglob('*')) if p.is_file()}


def replay(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    job = json.loads((source / 'job.json').read_text())
    revision = job.get('revision')
    if revision not in ('r03_revision09', 'r03_revision10', 'r03_revision11'):
        raise ValueError('Unsupported historical revision; do not rewrite old identities')
    recorded = json.loads((source / 'r03_metrics.json').read_text())
    if recorded.get('accepted') is not True:
        raise ValueError('Failed logs need failure audit; never relabel as complete replay')
    before, pins = snapshot(source), check_pins()
    original = load('original_' + revision, OLD / revision / 'analyzer.py')
    chain = final_analysis()
    protocol = original.replay_protocol(source, job)
    original._archive_scope(source, protocol, job)
    chain._handoff.copy_sidecars(source, output)
    result = dict(stage='RI02-offline-replay', diagnostic_only=True, accepted=False,
                  flight_accepted=False, execution_authority_granted=False, new_flights=0,
                  original_revision=revision, original_job=job, source=str(source), output=str(output),
                  input_sha256_before=before, dependency_sha256=pins, success=False)
    preparation, warmup = {}, {}
    try:
        def provenance(run, p, j):
            if Path(run).resolve() != output:
                raise ValueError('Wrong diagnostic directory')
            chain._handoff.copied_input_binding(source, output)
            binding = original.provenance(source, p, j)
            preparation.update(original.prearm_evidence(source))
            if hasattr(original, 'warmup_evidence'):
                warmup.update(original.warmup_evidence(source))
            else:
                warmup.update(valid=True, original_revision=revision,
                              note='Original prearm/warmup contract retained; no fabricated later receipt')
            return binding

        def save(path, value):
            if Path(path).name == 'r03_metrics.json':
                value = chain._handoff.diagnostic_payload(value)
            chain._inherited.save(path, value)

        raw = chain.full_analysis(provenance, save)(output, protocol, job)
        result['full_chain_complete'] = raw.get('accepted') is True
        result['error'] = raw.get('error')
        result['prearm_preparation'] = preparation
        result['post_logger_warmup'] = warmup
        if raw.get('accepted') is True:
            result['upstream'] = original.upstream_evidence(source, raw)
        result['science_exact_without_description_migration'] = {key: exact(raw.get(key), recorded.get(key)) for key in SCIENCE}
        result['science_equal'] = {key: science_equal(key, raw.get(key), recorded.get(key), revision) for key in SCIENCE}
        result['description_migration'] = dict(permitted_path='task_targets.attitude.association',
            applicable_original_revision='r03_revision09', numeric_values_changed=False,
            applied=not result['science_exact_without_description_migration']['task_targets'] and result['science_equal']['task_targets'])
        result['spectrum_equal'] = (output / 'spectra.json').exists() and digest(output / 'spectra.json') == digest(source / 'spectra.json')
        result['success'] = result['full_chain_complete'] and all(result['science_equal'].values()) and result['spectrum_equal']
    except Exception as error:
        result.update(error=repr(error), traceback=traceback.format_exc(), success=False)
    finally:
        result['input_sha256_after'] = snapshot(source)
        result['historical_inputs_unchanged'] = before == result['input_sha256_after']
        result['historical_verdict_unchanged'] = exact(recorded, json.loads((source / 'r03_metrics.json').read_text()))
        result['dependency_unchanged'] = pins == check_pins()
        result['success'] = result['success'] and result['historical_inputs_unchanged'] and result['historical_verdict_unchanged'] and result['dependency_unchanged']
        (output / 'ri02_replay_summary.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = replay(args.source, args.output)
    print(json.dumps({k: v for k, v in result.items() if k not in ('input_sha256_before', 'input_sha256_after', 'original_job')}, indent=2))
    raise SystemExit(0 if result['success'] else 1)
