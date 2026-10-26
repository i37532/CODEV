#!/usr/bin/env python3
"""RI07 post-run result collection; no flight, tuning or admission changes.

Uses the preregistered RI06 statistical implementation unchanged. The two
independent groups keep their H/V block correlation. Run only after replay03.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
STAGE = HERE.parents[1]
sys.path.insert(0, str(STAGE / 'tools'))
import bindings as b

stats = b.load('final_statistics', STAGE.parent / 'ri06/statistical_plan.py')
LABEL = {'PID': 'pid', 'RSTA': 'STA', 'RISTA': 'ISTA'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def strict(value):
    """No implicit replacement of nonfinite scientific values."""
    return json.dumps(value, indent=2, allow_nan=False, ensure_ascii=False) + '\n'


def write_new(path, value):
    serialized = strict(value)
    with Path(path).open('x') as stream:
        stream.write(serialized)


def finite(value):
    require(type(value) in (int, float) and math.isfinite(value), 'Nonfinite/non-numeric metric')
    return float(value)


def vector(value):
    require(isinstance(value, list) and len(value) == 3, 'Expected XYZ vector')
    return [finite(x) for x in value]


def window_semantics(diagnostic, nominal_seconds):
    """Keep frozen [0,64)/[0,32)/[32,64) selection separate from sample weights.

    The frozen analyzer sums un-clipped sensor intervals. That sum is NOT a
    request-window boundary. Validity remains with the exact original analyzer
    and replay, not a new result-layer equality or widened flight tolerance.
    """
    require(type(nominal_seconds) in (int,float) and nominal_seconds==64,
            'Wrong frozen nominal task window')
    require(set(diagnostic['windows'])=={'first_half','second_half'},'Wrong half-window layout')
    main=finite(diagnostic['seconds'])
    halves={k:finite(v['seconds']) for k,v in diagnostic['windows'].items()}
    require(main>0 and all(v>0 for v in halves.values()),'Nonpositive sample weight sum')
    require(math.isclose(main,math.fsum(halves.values()),rel_tol=0,abs_tol=1e-12),
            'Reported disjoint half weights do not sum to main weights')
    return dict(nominal_main_seconds=64,nominal_half_seconds=32,
                weighted_main_seconds=main,weighted_half_seconds=halves,
                note='Frozen analyzer retains full sensor intervals; no clipping, interpolation or new admission rule')


def paired_matrices(rows):
    """Missing observations remain NaN; never zero or favourable-subset fill."""
    members = {}
    for row in rows:
        j = row['job']
        require(j['group'] in ('A', 'B') and j['task'] in ('H', 'V'), 'Unknown group/task')
        require(type(j['block']) is int and 1 <= j['block'] <= 20, 'Wrong paired block')
        names = ('RSTA', 'RISTA') if j['group'] == 'A' else ('PID', 'RSTA', 'RISTA')
        require(j['candidate'] in names, 'Unregistered algorithm')
        expected_seed = (85000 if j['group'] == 'A' else 85100) + j['block']
        require(j['seed'] == expected_seed, 'Wrong formal seed')
        key = (j['group'], j['block'], j['task'], j['candidate'])
        require(key not in members, 'Duplicate paired member')
        if row['accepted'] is True:
            members[key] = finite(row['J'])
        else:
            members[key] = None
    result = {}
    for group, labels in stats.COMPARISONS.items():
        a = np.full((20, len(labels)), np.nan)
        for column, label in enumerate(labels):
            task, comparison = label.split(':')
            later, earlier = comparison.split('-')
            for block in range(1, 21):
                values = [members.get((group, block, task, c)) for c in (later, earlier)]
                if all(x is not None for x in values):
                    a[block-1, column] = values[0] - values[1]
        result[group] = a
    return result


def summarize_groups(rows):
    result = []
    for group in ('A', 'B'):
        for task in ('H', 'V'):
            for candidate in (('RSTA', 'RISTA') if group == 'A' else ('PID', 'RSTA', 'RISTA')):
                selected = [r for r in rows if r['job']['group'] == group and r['job']['task'] == task
                            and r['job']['candidate'] == candidate and r['accepted']]
                require(len(selected) == 20, 'Complete20 observations required for final group summary')
                def mean(key):
                    return np.mean([r[key] for r in selected], axis=0).tolist()
                result.append(dict(group=group, task=task, candidate=candidate, label=LABEL[candidate], n=20,
                    J_mean=mean('J'), J_sd=float(np.std([r['J'] for r in selected], ddof=1)),
                    velocity_rmse_mean=mean('velocity_rmse'), position_rmse_mean=mean('position_rmse'),
                    yaw_rmse_mean=mean('yaw_rmse'), nominal_height_rmse_mean=mean('nominal_height_rmse'),
                    nominal_height_peak_max=max(r['nominal_height_peak'] for r in selected),
                    correction_tv_per_s_mean=mean('correction_tv_per_s'),
                    thrust_tv_per_s_mean=mean('thrust_tv_per_s'),
                    common_0_7hz_rms_mean=mean('common_0_7hz_rms'),
                    constraint_fraction_max=max(r['constraints'] for r in selected),
                    update_hz_range=[min(r['update_hz'] for r in selected), max(r['update_hz'] for r in selected)],
                    host_kernel_mean_run_percentiles_us=mean('host_kernel_percentiles_us'),
                    host_module_mean_run_percentiles_us=mean('host_module_percentiles_us')))
    return result


def verify_log(entry):
    path = Path(entry['archive'])
    require(path.is_file() and path.stat().st_size == entry['bytes'], 'Missing/changed ULog size')
    require(b.digest(path) == entry['sha256'], 'Changed ULog fingerprint')
    return dict(path=str(path), sha256=entry['sha256'], bytes=entry['bytes'])


def collect(replay_dir):
    p, replay = b.api(), b.local('replay')
    p.check()
    protocol = p.load_protocol('FORMAL')
    batch = Path(protocol['artifacts']['new_run_root'])
    replay.verify_complete(replay_dir, gate='FORMAL')
    ledger = b.read(batch / 'ledger.json')
    gate = b.read(batch.parent / 'gate_pass.json')
    require(gate['accepted'] is True and gate['replay_summary_sha256'] == b.digest(replay_dir / 'summary.json'),
            'Missing final replay gate')
    orchestration=b.read(replay_dir/'summary.json')['orchestration']
    require(orchestration==dict(workers=4,source=str(HERE/'parallel_replay.py'),
            sha256=b.digest(HERE/'parallel_replay.py'),analyzer_changed=False),
            'Changed parallel decode orchestration')
    before = replay.snapshot(batch)
    rows, inputs, logs, configurations, incremental = [], {}, [], {}, []
    def pin(path):
        inputs[str(path)] = b.digest(path)
    for path in (batch/'ledger.json', batch.parent/'gate_pass.json', replay_dir/'summary.json',
                 STAGE/'execution.json', STAGE/'gates/FORMAL/frozen.json', Path(stats.__file__)):
        pin(path)
    for path in HERE.glob('*.py'):
        pin(path)
    interrupted_path=batch.parent/'replay02/summary.json'
    interrupted=b.read(interrupted_path);pin(interrupted_path)
    require(interrupted['success'] is False and interrupted['new_flights']==0
            and interrupted['source_inputs_unchanged'] is True
            and interrupted['ledger_sha256']==b.digest(batch/'ledger.json'),
            'Changed interrupted read-only replay record')
    qref = b.read(batch/'qualification_reference.json')
    require(qref['sha256'] == b.digest(qref['path']), 'Changed qualification')
    q = b.read(qref['path']); pin(Path(qref['path']))
    for item in ledger['attempts']:
        job = item['job']; run = Path(item['directory'])
        m = replay.check_result_binding(item, ledger)
        result = b.read(run/'result.json')
        receipt_path = batch.parent/'replay01'/(job['id']+'_receipt.json')
        receipt = b.read(receipt_path)
        require(item['replay_receipt_sha256'] == b.digest(receipt_path), 'Changed incremental replay receipt')
        expected = [sys.executable, '-B', str(STAGE/'tools/analyzer.py'), str(run), '--output',
                    str(batch.parent/'replay01'/job['id'])]
        require(receipt['exit_code'] == 0 and receipt['argv'] == expected, 'Wrong/failed incremental replay command')
        require(receipt['log_sha256'] == b.digest(batch.parent/'replay01'/(job['id']+'.log')), 'Changed replay log')
        require(b.exact(m, b.read(Path(item['independent_replay'])/'r03_metrics.json')), 'Incremental metrics changed')
        require(b.digest(run/'spectra.json') == b.digest(Path(item['independent_replay'])/'spectra.json'), 'Spectrum changed')
        incremental.append(dict(id=job['id'], receipt=str(receipt_path), sha256=b.digest(receipt_path), exit_code=0))
        require(all(m['baseline_checks'].values()), 'Required baseline check failed')
        require(m['first_invocation']['first_failures'] == 0 and m['first_invocation']['retries'] == 0,
                'Unexpected same-sample retry/failure')
        require(m['position_log']['sequence_gaps'] == 0, 'Position record gap')
        require(any(e['name'] == 'takeoff_command' for e in result['events']) and
                any(e['name'] == 'landed_disarmed' for e in result['events']), 'Missing takeoff/landing evidence')
        d = m['diagnostic']; rmse = vector(d['error']['rmse'])
        require(math.isclose(finite(d['J']), sum(rmse)/3, rel_tol=1e-14, abs_tol=1e-15), 'Wrong XYZ J')
        timing=window_semantics(d,protocol['excitation']['duration_s'])
        config_key = job['group']+'/'+job['task']+'/'+job['candidate']
        config = dict(parameters=job['parameters'], sha256=job['parameters_sha256'], candidate_index=job['candidate_index'])
        if config_key in configurations:
            require(b.exact(configurations[config_key], config), 'Parameters changed within group/task/algorithm')
        configurations[config_key] = config
        for entry in result['logs']:
            logs.append(dict(id=job['id'], **verify_log(entry)))
        for name in ('r03_metrics.json', 'result.json', 'job.json', 'run_protocol.json', 'parameter_restore.json', 'spectra.json'):
            pin(run/name)
        pin(receipt_path)
        rows.append(dict(job={k:job[k] for k in ('id','group','block','seed','task','candidate','mode','axes',
                                               'divisor','candidate_index','parameters_sha256')}, accepted=True,
            J=d['J'], window_time_semantics=timing, velocity_rmse=rmse, velocity_mean=vector(d['error']['mean']),
            velocity_variance=vector(d['error']['variance']), windows=d['windows'],
            position_rmse=vector(m['position_rmse']), yaw_rmse=finite(m['yaw_rmse']),
            nominal_height_rmse=finite(m['height']['rmse']), nominal_height_peak=finite(m['height']['max_abs']),
            height_includes_intentional_motion=job['task']=='V',
            correction_tv_per_s=vector(d['correction_tv_per_second']),
            thrust_tv_per_s=vector(d['normalized_thrust_tv_per_second']),
            constraints=finite(d['constraint_fraction']), maximum_constraint_s=d['maximum_continuous_constraint_s'],
            true_updates=d['actual_updates'], nu_peak=d['nu_peak'],
            update_hz=finite(m['spectral_summary']['update_hz']),
            common_0_7hz_rms=vector(m['spectral_summary']['common_0_7hz_rms']),
            host_kernel_percentiles_us=[finite(m['host_cost']['path_ns'][k]) for k in ('median_us','p95_us','p99_us')],
            host_module_percentiles_us=[finite(m['host_cost']['module_ns'][k]) for k in ('median_us','p95_us','p99_us')],
            lifecycle=m['lifecycle'], actual_output=m['actual_output'], rate_actuator=m['rate_actuator'],
            observation_cadence=m['observation']['cadence'], flight_cadence=m['flight']['cadence'],
            first_invocation=m['first_invocation'], position_log=m['position_log'],
            metadata=dict(metrics_path=str(run/'r03_metrics.json'), source_head=result['source_head'],
                          firmware_sha256=result['binary_sha256'])))
    matrices = paired_matrices(rows)
    statistical = {g:dict(primary=stats.summarize(a,g), exploratory_sign_flip=stats.exploratory_sign_flip(a,g))
                   for g,a in matrices.items()}
    require(all(x['primary']['common_complete_blocks'] == 20 for x in statistical.values()), 'Incomplete formal blocks')
    after = replay.snapshot(batch)
    require(before == after, 'Original batch changed during collection')
    package = dict(stage='RI07', accepted=True, planned=200, attempts=200, takeoffs=200, accepted_runs=200,
        A=80, B=120, independent_replays=200, additional_full_replays=200, paired_risk_checks=80,
        failed=0, invalid=0, missing=0, retries=0, parameter_restore_exact=True, remaining_simulators=[],
        source_head=ledger['source_head'], firmware_sha256=ledger['firmware_sha256'], qualification=q['counts'],
        qualification_path=qref['path'], qualification_sha256=qref['sha256'],
        parameters=configurations, rows=rows, group_summary=summarize_groups(rows), statistics=statistical,
        paired_differences={g:a.tolist() for g,a in matrices.items()},
        inputs=inputs, logs=logs, log_bytes=sum(x['bytes'] for x in logs),
        incremental_replays=incremental, original_inputs_unchanged=True,
        interrupted_readonly_replay=dict(path=str(interrupted_path),sha256=b.digest(interrupted_path),
            replayed=interrupted['replayed'],success=False,new_flights=0,error=interrupted.get('error'),
            reason='Intentional stop of redundant sequential replay; restarted all200 with bounded4 decoder processes; no flight retry'),
        original_snapshot_sha256=hashlib.sha256(strict(after).encode()).hexdigest(),
        scope='Iris SITL XYZ velocity; position P, attitude/rate PID, DIV1; no hardware claim',
        limitations=['Only IMU innovation explicitly seeded; other random sources/scheduling not fully independent.',
          'H/V share blocks; A and B are separate. n20 is a precision/budget choice, not guaranteed power.',
          '8-family Bonferroni percentile bootstrap; common-complete and available pairs separately reported.',
          'All accepted here; inference remains conditional on fixed safety/log criteria and limited tasks.',
          'Same external trajectory does not imply identical internally composed velocity setpoints.',
          'A differs in compensation/prediction as well as discretization; not a pure Euler effect.',
          'Protected applied outputs/states are not strict unconstrained implicit solutions.',
          'TV is not energy; host wall-clock cost is not board CPU; partial downstream coverage retained.',
          '200 original samples, not400: repeating log decoding creates no new flight samples.'])
    strict(package)
    return package


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replay', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    require(not args.output.exists(), 'New output path required')
    value=collect(args.replay.resolve())
    write_new(args.output, value)
    print(strict(dict(accepted=True, attempts=200, logs=len(value['logs']), log_bytes=value['log_bytes'],
                     output=str(args.output), sha256=b.digest(args.output))))
