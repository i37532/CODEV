#!/usr/bin/env python3
"""Independent nine-process RI05 replay. Never flies or changes original runs."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from bindings import api, digest, exact, HERE, local, OLD_RUNNER, read, REPO, save, source_binding


def require(value, message):
    if not value:
        raise ValueError(message)


def snapshot(root):
    root = Path(root).resolve()
    require(root.is_dir(), 'Missing original batch')
    files, links = {}, {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            links[str(path)] = os.readlink(path)
            require(path.exists(), 'Broken original model link')
        if path.is_file():
            files[str(path)] = digest(path)
    return dict(files=files, links=links)


def paired_decision(pid, candidate):
    """Independent numeric risk computation, not analyzer.compare's bool."""
    local('analyzer').validate_pair(pid, candidate)
    def scalar(value):
        require(type(value) in (int, float) and math.isfinite(value) and value >= 0, 'Invalid finite nonnegative paired metric')
        return value
    def vector(values):
        require(isinstance(values, list) and len(values) == 3, 'Missing three-axis paired metric')
        return [scalar(v) for v in values]
    checks = {}
    actual, reference = vector(candidate['diagnostic']['error']['rmse']), vector(pid['diagnostic']['error']['rmse'])
    pos, base_pos = vector(candidate['position_rmse']), vector(pid['position_rmse'])
    for i, margin in enumerate((.02, .02, .01)):
        checks['velocity_' + str(i)] = actual[i] <= 1.25 * reference[i] + margin
        checks['position_' + str(i)] = pos[i] <= 1.25 * base_pos[i] + .05
    for window in ('first_half', 'second_half'):
        actual = vector(candidate['diagnostic']['windows'][window]['error']['rmse'])
        reference = vector(pid['diagnostic']['windows'][window]['error']['rmse'])
        for i, margin in enumerate((.02, .02, .01)):
            checks[window + '_velocity_' + str(i)] = actual[i] <= 1.25 * reference[i] + margin
    checks['yaw'] = scalar(candidate['yaw_rmse']) <= 1.25 * scalar(pid['yaw_rmse']) + .02
    return dict(accepted=all(checks.values()), checks=checks, seed=pid['job']['seed'], gate=pid['job']['gate'],
        candidate=candidate['job']['candidate'],
        criterion='Inherited development risk, not a requirement to beat PID or another STA')


def validate_ledger(ledger, protocol):
    local('runner').validate_scope(protocol)
    gate = protocol['gate']
    require(ledger.get('success') is True and ledger.get('stage') == api().stage(gate)
            and ledger.get('revision') == 'ri05' and ledger.get('gate') == gate, 'Not completed RI05 gate')
    for key, value in dict(planned=9, total_budget=18, new_planned=9, prior_attempts=0).items():
        require(type(ledger.get(key)) is int and ledger[key] == value, 'Wrong finite budget: ' + key)
    require(ledger.get('parameter_restore_exact') is True and ledger.get('remaining_simulators') == []
            and ledger.get('unattempted') == [], 'Incomplete cleanup/missing trials')
    require(re.fullmatch('[0-9a-f]{40}', ledger.get('source_head', '')) is not None
            and re.fullmatch('[0-9a-f]{64}', ledger.get('firmware_sha256', '')) is not None, 'Missing source/firmware identity')
    attempts = ledger.get('attempts', [])
    require(len(attempts) == 9, 'Incomplete nine attempts')
    batch = Path(protocol['artifacts']['new_run_root']).resolve()
    for i, (item, job) in enumerate(zip(attempts, protocol['jobs']), 1):
        require(type(item.get('attempt')) is int and item['attempt'] == i and exact(item.get('job'), job)
                and item.get('status') == 'accepted' and Path(item['directory']).resolve() == batch / job['id'],
                'Reordered/substituted/failed attempt')
        require(re.fullmatch('[0-9a-f]{64}', item.get('metrics_sha256', '')) is not None, 'Missing original metrics SHA')
    required_checks = {'yaw'} | {prefix + str(i) for prefix in
        ('velocity_', 'position_', 'first_half_velocity_', 'second_half_velocity_') for i in range(3)}
    pairs = ledger.get('pairs', [])
    require(len(pairs) == 6, 'Missing six paired checks')
    expected = sorted((j['seed'], j['candidate']) for j in protocol['jobs'] if j['mode'])
    actual = []
    for pair in pairs:
        require(pair.get('accepted') is True and pair.get('gate') == gate
                and set(pair.get('checks', {})) == required_checks and all(v is True for v in pair['checks'].values()),
                'Incomplete/failed numeric paired checks')
        actual.append((pair['seed'], pair['candidate']))
    require(sorted(actual) == expected, 'Wrong/duplicated paired identities')


def recompute_pairs(ledger, metrics):
    blocks = {}
    for item in ledger['attempts']:
        job = item['job']
        require(job['id'] in metrics and exact(metrics[job['id']]['job'], job), 'Missing/wrong replayed pair member')
        block = blocks.setdefault(job['seed'], {})
        require(job['mode'] not in block, 'Duplicate paired mode')
        block[job['mode']] = metrics[job['id']]
    decisions = []
    for item in ledger['attempts']:
        job = item['job']
        if job['mode']:
            decision = paired_decision(blocks[job['seed']][0], blocks[job['seed']][job['mode']])
            require(decision['accepted'] is True, 'Frozen paired risk failed')
            decisions.append(decision)
    require(len(decisions) == 6 and exact(decisions, ledger['pairs']), 'Independent paired decisions changed')
    return decisions


def check_result_binding(item, ledger):
    run = Path(item['directory'])
    require(digest(run / 'r03_metrics.json') == item['metrics_sha256'], 'Original metrics SHA changed')
    metrics = read(run / 'r03_metrics.json')
    result = read(run / 'result.json')
    require(metrics.get('accepted') is True and result.get('success') is True
            and exact(metrics['job'], item['job']) and result.get('source_head') == ledger['source_head']
            and result.get('binary_sha256') == ledger['firmware_sha256'], 'Original result/identity differs')
    require(exact(metrics.get('candidate_numeric_binding'), source_binding()), 'Original math/chain binding changed')
    binding = metrics.get('binding', {})
    require(binding.get('source_head') == ledger['source_head'] and binding.get('firmware_sha256') == ledger['firmware_sha256']
            and binding.get('revision') == 'ri05' and binding.get('stage') == api().stage(ledger['gate']), 'Original qualification binding changed')
    return metrics


def run_replay(output, *, gate='C', finalize=False):
    protocol = api().load_protocol(gate)
    api().require_execution_authority(gate)
    batch = Path(protocol['artifacts']['new_run_root']).resolve()
    output = Path(output).resolve()
    require(output != batch and batch not in output.parents and output.parent == batch.parent, 'New independent replay directory under same gate required')
    ledger = read(batch / 'ledger.json')
    validate_ledger(ledger, protocol)
    reference = read(batch / 'qualification_reference.json')
    qpath = Path(reference['path'])
    require(reference['sha256'] == digest(qpath), 'Batch qualification reference changed')
    q = api().archive_qualification(gate, ledger['source_head'], qpath)
    require(q['firmware_sha256'] == ledger['firmware_sha256'], 'Batch qualified firmware differs')
    before = snapshot(batch)
    output.mkdir(parents=True, exist_ok=False)
    summary = dict(stage=api().stage(gate), revision='ri05', gate=gate, source_head=ledger['source_head'], success=False,
        new_flights=0, replayed=0, commands=[], ledger_sha256=digest(batch / 'ledger.json'),
        original_input_sha256_before=before, qualified_firmware_sha256=ledger['firmware_sha256'])
    metrics = {}
    try:
        for item in ledger['attempts']:
            source = Path(item['directory'])
            original = check_result_binding(item, ledger)
            destination = output / item['job']['id']
            command = [sys.executable, '-B', str(HERE / 'analyzer.py'), str(source), '--output', str(destination)]
            log = output / (item['job']['id'] + '.log')
            began = time.monotonic()
            with log.open('xb') as stream:
                completed = subprocess.run(command, cwd=REPO, stdout=stream, stderr=subprocess.STDOUT)
            summary['commands'].append(dict(argv=command, cwd=str(REPO), returncode=completed.returncode,
                elapsed_s=time.monotonic() - began, log=str(log), log_sha256=digest(log)))
            require(completed.returncode == 0, 'Independent analyzer failed: ' + item['job']['id'])
            repeated = read(destination / 'r03_metrics.json')
            require(repeated.get('accepted') is True and exact(original, repeated), 'All JSON values/types/order must reproduce exactly')
            require(digest(source / 'spectra.json') == digest(destination / 'spectra.json'), 'Spectrum bytes changed')
            metrics[item['job']['id']] = repeated
            summary['replayed'] += 1
            print(item['job']['id'], 'replayed', flush=True)
        summary['pairs'] = recompute_pairs(ledger, metrics)
        summary['success'] = summary['replayed'] == 9 and len(summary['pairs']) == 6
    except BaseException as error:
        summary['error'] = repr(error)
    finally:
        summary['original_input_sha256_after'] = snapshot(batch)
        summary['source_inputs_unchanged'] = summary['original_input_sha256_after'] == before
        summary['success'] = summary['success'] and summary['source_inputs_unchanged']
        save(output / 'summary.json', summary)
    if finalize:
        require(summary['success'], 'Cannot finalize incomplete/changed replay')
        verify_complete(output, gate=gate)
        receipt = dict(stage=api().stage(gate), revision='ri05', gate=gate, accepted=True, planned=9, attempts=9,
            accepted_runs=9, independent_replays=9, paired_checks=6, missing=0, source_head=ledger['source_head'],
            firmware_sha256=ledger['firmware_sha256'], ledger_sha256=digest(batch / 'ledger.json'),
            replay_summary_path=str(output / 'summary.json'), replay_summary_sha256=digest(output / 'summary.json'),
            parameter_restore_exact=True, new_flights_by_replay=0,
            scope='Iris SITL fixed-parameter '+api().valid_gate(gate)['task']+' development only; not formal tuning or real hardware')
        path = batch.parent / 'gate_pass.json'
        with path.open('x') as stream:
            json.dump(receipt, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
    return summary


def verify_complete(output, *, gate='C'):
    """Read artifacts and recheck all nine identities and six numeric decisions."""
    protocol = api().load_protocol(gate)
    batch = Path(protocol['artifacts']['new_run_root']).resolve()
    output = Path(output).resolve()
    require(output.parent == batch.parent and output != batch, 'Wrong replay scope')
    ledger, summary = read(batch / 'ledger.json'), read(output / 'summary.json')
    validate_ledger(ledger, protocol)
    api().require_execution_authority(gate)
    reference = read(batch / 'qualification_reference.json')
    qpath = Path(reference['path'])
    require(reference['sha256'] == digest(qpath), 'Batch qualification reference changed')
    qualification = api().archive_qualification(gate, ledger['source_head'], qpath)
    require(qualification['firmware_sha256'] == ledger['firmware_sha256'], 'Batch qualified firmware differs')
    require(summary.get('success') is True and summary.get('source_inputs_unchanged') is True
            and summary.get('replayed') == 9 and summary.get('new_flights') == 0
            and summary.get('ledger_sha256') == digest(batch / 'ledger.json')
            and summary.get('original_input_sha256_after') == snapshot(batch), 'Incomplete/stale replay evidence')
    require(len(summary.get('commands', [])) == 9 and all(r['returncode'] == 0 for r in summary['commands']), 'Missing actual nine independent decoders')
    metrics = {}
    for item, command in zip(ledger['attempts'], summary['commands']):
        name = item['job']['id']
        require(command['argv'] == [sys.executable, '-B', str(HERE / 'analyzer.py'), item['directory'], '--output', str(output / name)]
                and command['log_sha256'] == digest(Path(command['log'])), 'Changed independent replay command/log')
        original = check_result_binding(item, ledger)
        repeated = read(output / name / 'r03_metrics.json')
        require(exact(original, repeated) and digest(Path(item['directory']) / 'spectra.json') == digest(output / name / 'spectra.json'), 'Replay result changed')
        metrics[name] = repeated
    require(exact(recompute_pairs(ledger, metrics), summary['pairs']), 'Stored replay pairs changed')
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gate', choices=('C', 'D'), default='C')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--finalize', action='store_true')
    args = parser.parse_args()
    result = run_replay(args.output, gate=args.gate, finalize=args.finalize)
    print(json.dumps({k: v for k, v in result.items() if k not in ('original_input_sha256_before', 'original_input_sha256_after')}, indent=2))
    raise SystemExit(0 if result['success'] else 1)
