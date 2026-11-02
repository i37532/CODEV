#!/usr/bin/env python3
"""Offline-only regression; never overwrites a run or grants flight acceptance."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import types

import numpy as np
from pyulog import ULog

import analyze as a
import heading_check as h


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rejection(function):
    try:
        function()
    except ValueError as exc:
        return repr(exc)
    raise AssertionError('Expected rejection, got acceptance')


def run(attempt, frozen_analyzer):
    attempt = Path(attempt).resolve()
    original = json.loads((attempt/'result.json').read_text())
    job = json.loads((attempt/'job.json').read_text())
    origin = json.loads((attempt/'origin.json').read_text())
    manifest_path = attempt.parent.parent/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    a.require(original['success'] is False and original['independent_replay_passed'] is False,
              'This regression is for the stopped O001, not a result conversion tool')
    expected = manifest['assets'][str(Path(a.__file__).resolve())]
    a.require(sha(frozen_analyzer) == expected, 'Wrong frozen analyzer snapshot')
    protected = [p for p in attempt.rglob('*') if p.is_file()] + [manifest_path]
    before = {str(p): sha(p) for p in protected}
    record = max(original['logs'], key=lambda row: row['bytes'])
    path = Path(record['archive'])
    if not path.is_absolute(): path = attempt/path
    a.require(sha(path) == record['sha256'], 'ULog hash mismatch')
    frozen = types.ModuleType('frozen_offboard_audit')
    frozen.__file__ = a.__file__  # Preserve original relative import resolution.
    exec(compile(Path(frozen_analyzer).read_text(), str(frozen_analyzer), 'exec'), frozen.__dict__)
    args = (path, original['events'], origin, job, attempt/'ros/sent.jsonl')
    old_error = rejection(lambda: frozen.audit_native_log(*args))
    current_strict = rejection(lambda: a.audit_native_log(*args))
    a.require(old_error == current_strict == original['analysis_error'], 'Historical rejection changed')
    revised = dict(job, heading_reset_policy=h.POLICY)
    revised_args = (path, original['events'], origin, revised, attempt/'ros/sent.jsonl')
    new = a.audit_native_log(*revised_args)
    again = a.audit_native_log(*revised_args)
    a.require(new == again, 'Nondeterministic offline replay')

    # Corrupt copies in memory only. Never modify a ULog or result on disk.
    base = ULog(str(path), message_name_filter_list=list(a.BASE_TOPICS)+list(a.diagnostic_contract(job))+list(h.TOPICS))
    def data(log, name): return next(d.data for d in log.data_list if d.name == name and d.multi_id == 0)
    def assign(log, name, key, when, value):
        d=data(log,name);d[key]=d[key].copy();d[key][d['timestamp']>=when]=value
    cases = []
    for key in (*h.PV_COUNTERS, 'heading_reset_counter'):
        cases.append(('late/'+key, lambda u,k=key: assign(u,'vehicle_local_position',k,80000000,9)))
    for key in ('primary_instance','instance_changed_count','gyro_fault_detected'):
        cases.append(('selector/'+key,lambda u,k=key: assign(u,'estimator_selector_status',k,60000000,9)))
    cases += [
        ('missing_flags', lambda u: setattr(u,'_data_list',[d for d in u.data_list if d.name!='estimator_status_flags'])),
        ('missing_alignment',lambda u: assign(u,'estimator_status_flags','cs_mag_aligned_in_flight',38200000,0)),
        ('bad_quaternion',lambda u: assign(u,'vehicle_attitude','delta_q_reset[3]',49600000,.2)),
        ('filter_fault',lambda u: assign(u,'estimator_status','filter_fault_flags',60000000,1)),
        ('wrong_inner_mode',lambda u: assign(u,'sta_rate_ctrl_status','effective_mode',60000000,1)),
        ('wrong_outer_mode',lambda u: assign(u,'sta_velocity_ctrl_status','effective_mode',60000000,4)),
        ('future_position_sample',lambda u: assign(u,'vehicle_local_position','timestamp_sample',60000000,999999999)),
        ('wrong_actual_target',lambda u: assign(u,'trajectory_setpoint','z',68000000,-3.9)),
        ('yaw_not_settled',lambda u: assign(u,'vehicle_local_position','heading',55000000,2.)),
    ]
    mutations = []
    for label, mutate in cases:
        changed = copy.deepcopy(base)
        mutate(changed)
        error = rejection(lambda: a.audit_native_log(*revised_args, ulog_class=lambda *args, **kw: changed))
        mutations.append(dict(case=label, rejected=True, error=error, memory_only=True))

    # Existing four-system Navigator results use their OWN unchanged contract.
    # Do not apply Offboard nav=14 rules to old nav=4 runs or merge the samples.
    legacy_manifest = Path(a.__file__).parent.parent/'results/four_systems/manifest04_pid.json'
    legacy_metrics = json.loads((legacy_manifest.parent/'metrics.json').read_text())
    old_manifest = json.loads(legacy_manifest.read_text())
    old_rows = {r['job']['id']: r for r in legacy_metrics['runs']}
    historical = []
    for old_job in old_manifest['jobs']:
        row, unused = a._legacy.analyze_job(old_manifest, old_job, legacy_manifest)
        prior = old_rows[old_job['id']]
        a.require(row['metrics'] == prior['metrics'] and row['runner_success'] == prior['runner_success']
                  and row['analysis_valid'] == prior['analysis_valid'], 'Old four-system replay changed')
        historical.append(dict(id=old_job['id'], result_sha256=row['result_sha256'],
            ulog=row['ulog'], original_acceptance_unchanged=True, metrics_exact=True))
    after = {str(p):sha(p) for p in protected}
    a.require(before == after, 'Original attempt evidence changed')
    return dict(diagnostic_only=True, flight_accepted=False, new_flights=0,
        original_success=original['success'], original_outcome_unchanged=True,
        frozen_error=old_error, revised_strict_error=current_strict,
        revised_offline_checks_passed=True, deterministic_replay_equal=True,
        heading_evidence=new['heading_evidence'], in_memory_negative_cases=mutations,
        historical_four_system_replays=historical, protected_sha256=before,
        protected_after_equal=True, frozen_analyzer_sha256=expected,
        tool_sha256={str(p.resolve()):sha(p) for p in (Path(a.__file__),Path(h.__file__),Path(__file__))},
        note='Policy-development replay only. O001 stays failed; not a new flight or accepted comparison sample.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=Path, required=True)
    parser.add_argument('--frozen-analyzer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    a.require(not args.output.exists(), 'Refusing existing replay evidence')
    a.require(not args.output.resolve().is_relative_to(args.attempt.resolve()), 'Output must be outside original attempt')
    result=run(args.attempt,args.frozen_analyzer)
    with args.output.open('x') as stream:
        stream.write(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    print(json.dumps(dict(offline_checks_passed=True,new_flights=0,original_success=False,
        negative_cases=len(result['in_memory_negative_cases']),
        old_system_logs=len(result['historical_four_system_replays']),output=str(args.output))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
