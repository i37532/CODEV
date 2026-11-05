#!/usr/bin/env python3
"""Read-only two-run replay after RI04's first failure; never grants gate pass.

The frozen analyzer is launched in a fresh process for each already accepted
run. Only their single existing PID/R-STA pair is recomputed. The failed
MODE4 attempt and all six unattempted jobs retain their original status.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent / 'tools'
sys.path.insert(0, str(TOOLS))
import bindings

replay = bindings.local('replay')
runner = bindings.local('runner')
SOURCE_HEAD = '74327418e18eafd421e18b48fe3964fdad63cfb5'


def require(value, message):
    if not value:
        raise ValueError(message)


def validate_stopped(ledger, protocol):
    """This result script cannot accept a complete, resumed or altered batch."""
    runner.validate_scope(protocol)
    require(ledger.get('success') is False and ledger.get('stage') == 'RI04-B'
            and ledger.get('revision') == 'ri04' and ledger.get('gate') == 'B', 'Not the stopped RI04 B batch')
    require(ledger.get('source_head') == SOURCE_HEAD, 'Wrong original flight source')
    for key, value in dict(planned=9, total_budget=9, new_planned=9, prior_attempts=0).items():
        require(type(ledger.get(key)) is int and ledger[key] == value, 'Changed original budget ' + key)
    require(ledger.get('parameter_restore_exact') is True and ledger.get('remaining_simulators') == [],
            'Missing exact restoration/owned-process cleanup')
    jobs = protocol['jobs']
    attempts = ledger.get('attempts', [])
    require(len(attempts) == 3 and [item.get('status') for item in attempts] == ['accepted', 'accepted', 'failed'],
            'Only two accepted attempts followed by first failure may be replayed')
    require([item['job']['mode'] for item in attempts] == [0, 3, 4], 'Wrong stopped algorithm order')
    batch = Path(protocol['artifacts']['new_run_root']).resolve()
    for index, (attempt, job) in enumerate(zip(attempts, jobs), 1):
        require(type(attempt.get('attempt')) is int and attempt['attempt'] == index
                and bindings.exact(attempt.get('job'), job)
                and Path(attempt['directory']).resolve() == batch / job['id'], 'Attempt identity/order differs')
    require(ledger.get('unattempted') == [job['id'] for job in jobs[3:]], 'Missing/unattempted entries changed')
    require(len(ledger.get('pairs', [])) == 1, 'Only one pre-failure pair exists')
    pair = ledger['pairs'][0]
    checks = {'yaw'} | {prefix + str(i) for prefix in
        ('velocity_', 'position_', 'first_half_velocity_', 'second_half_velocity_') for i in range(3)}
    require(pair.get('accepted') is True and pair.get('gate') == 'B' and pair.get('candidate') == 'RSTA'
            and pair.get('seed') == jobs[0]['seed'] and set(pair.get('checks', {})) == checks
            and all(value is True for value in pair['checks'].values()), 'Original single pair is incomplete/changed')
    return attempts[:2]


def single_pair(ledger, metrics):
    require(set(metrics) == {'run001', 'run002'}, 'Replay must not fill failed/missing cells')
    for item in ledger['attempts'][:2]:
        require(bindings.exact(metrics[item['job']['id']]['job'], item['job']), 'Pair member job changed')
    # Independent arithmetic from frozen analyzer.compare, not stored booleans.
    decision = replay.paired_decision(metrics['run001'], metrics['run002'])
    require(decision['accepted'] is True and bindings.exact([decision], ledger['pairs']),
            'Independent single pair differs from original')
    return decision


def run(output):
    protocol = bindings.api().load_protocol('B')
    batch = Path(protocol['artifacts']['new_run_root']).resolve()
    output = Path(output).resolve()
    require(output.parent == batch.parent and output != batch and not output.exists(),
            'Fresh independent sibling replay directory required')
    require(not (batch.parent / 'gate_pass.json').exists(), 'Stopped batch must not have a gate pass')
    ledger = bindings.read(batch / 'ledger.json')
    accepted = validate_stopped(ledger, protocol)
    reference = bindings.read(batch / 'qualification_reference.json')
    qpath = Path(reference['path'])
    require(bindings.digest(qpath) == reference['sha256'], 'Original qualification reference changed')
    qualified = bindings.api().archive_qualification('B', SOURCE_HEAD, qpath)
    require(qualified['firmware_sha256'] == ledger['firmware_sha256'], 'Qualified firmware changed')
    before = replay.snapshot(batch)
    output.mkdir(parents=True, exist_ok=False)
    summary = dict(stage='RI04-B-stopped-result-replay', success=False,
        meaning_of_success='Two existing accepted runs reproduce; NOT RI04 acceptance',
        stage_accepted=False, gate_pass_generated=False, new_flights=0,
        source_head=SOURCE_HEAD, result_script_sha256=bindings.digest(Path(__file__)),
        planned=9, attempted=3, accepted_before_replay=2, failed_before_replay=1,
        failed_run_preserved='run003', unattempted=ledger['unattempted'], replayed=0,
        commands=[], ledger_sha256=bindings.digest(batch / 'ledger.json'),
        original_input_sha256_before=before)
    repeated = {}
    try:
        for item in accepted:
            source = Path(item['directory'])
            original = replay.check_result_binding(item, ledger)
            destination = output / item['job']['id']
            command = [sys.executable, '-B', str(TOOLS / 'analyzer.py'), str(source), '--output', str(destination)]
            log = output / (item['job']['id'] + '.log')
            started = time.monotonic()
            with log.open('xb') as stream:
                finished = subprocess.run(command, cwd=bindings.REPO, stdout=stream, stderr=subprocess.STDOUT)
            summary['commands'].append(dict(argv=command, cwd=str(bindings.REPO), exit_code=finished.returncode,
                elapsed_s=time.monotonic() - started, log=str(log), log_sha256=bindings.digest(log)))
            require(finished.returncode == 0, 'Independent accepted-run analyzer failed: ' + item['job']['id'])
            value = bindings.read(destination / 'r03_metrics.json')
            require(value.get('accepted') is True and bindings.exact(original, value),
                    'All metrics values/types/list order must match the original')
            require(bindings.digest(source / 'spectra.json') == bindings.digest(destination / 'spectra.json'),
                    'Spectrum bytes changed')
            repeated[item['job']['id']] = value
            summary['replayed'] += 1
            print(item['job']['id'], 'accepted-run replay verified; stage remains failed', flush=True)
        summary['single_pair'] = single_pair(ledger, repeated)
        summary['pair_count'] = 1
        summary['success'] = summary['replayed'] == 2
    except BaseException as error:
        summary['error'] = repr(error)
    finally:
        summary['original_input_sha256_after'] = replay.snapshot(batch)
        summary['source_inputs_unchanged'] = summary['original_input_sha256_after'] == before
        summary['gate_pass_absent'] = not (batch.parent / 'gate_pass.json').exists()
        summary['success'] = summary['success'] and summary['source_inputs_unchanged'] and summary['gate_pass_absent']
        bindings.save(output / 'summary.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps({key: value for key, value in result.items()
                     if not key.startswith('original_input_sha256')}, indent=2))
    raise SystemExit(0 if result['success'] else 1)
