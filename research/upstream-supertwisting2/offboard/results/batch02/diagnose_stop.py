#!/usr/bin/env python3
"""Read-only B02 stop reproduction; never changes acceptance or starts PX4."""
import ast
import copy
import json
from pathlib import Path
import sys

import numpy as np
from pyulog import ULog

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
from prepare import sha256
from runner_contract import _check_diagnostics, check_order
from run import parse_topic

ROOT = Path('/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-ROS-OFFBOARD-20261102-B02')


def source_expectations(function, name, context):
    """Evaluate the actual frozen collector expression, not a retyped reference."""
    tree = ast.parse((HERE / 'run.py').read_text())
    functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                 and node.name == function]
    assert len(functions) == 1
    assignments = [node for node in ast.walk(functions[0]) if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    assert len(assignments) == 1
    expression = assignments[0].value
    return eval(compile(ast.Expression(expression), str(HERE / 'run.py'), 'eval'),
                {'__builtins__': {}}, context)


def diagnose():
    manifest_path = ROOT / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    run = ROOT / 'runs/O002'
    result = json.loads((run / 'result.json').read_text())
    job = json.loads((run / 'job.json').read_text())
    assert result['success'] is False and result['parameter_restore_exact'] is True
    assert result['remaining_simulators'] == []
    assert sha256(HERE / 'run.py') == manifest['assets'][str(HERE / 'run.py')]
    snapshots = [json.loads(line) for line in (run / 'samples.jsonl').read_text().splitlines()]
    last = snapshots[-1]
    assert last['phase'] == 'recover' and 'attitude_sta_status' in last['diagnostics']
    job_missing_hover_config = 'hover_diagnostic_expectations' not in job
    assert job_missing_hover_config
    sampled = source_expectations('sample', 'expectations', {'job': job, 'scored': True})
    verified = source_expectations('verify_configuration', 'expected', {'job': job, 'airborne': True})
    assert sampled == verified == {}
    simulated = copy.deepcopy(last)
    simulated['diagnostics'] = {name: last['diagnostics'][name] for name in sampled}
    try:
        _check_diagnostics(simulated, job, True)
    except ValueError as exc:
        reproduced = repr(exc)
    else:
        raise AssertionError('Frozen collector should reproduce the recorded failure')
    assert reproduced == result['error']
    # This verifies a recorded pre-stop diagnostic snapshot ONLY; not full-flight acceptance.
    _check_diagnostics(last, job, True)
    commands = [json.loads(line) for line in (run / 'commands.jsonl').read_text().splitlines()]
    diagnostic_commands = [row for row in commands if row['argv'][1:] == ['attitude_sta_status', '-n', '1']]
    assert diagnostic_commands and all(row['exit_code'] == 0 for row in diagnostic_commands)
    native = max(result['logs'], key=lambda row: row['bytes'])
    assert sha256(native['archive']) == native['sha256']
    log = ULog(native['archive'], message_name_filter_list=['attitude_sta_status', 'vehicle_status'])
    topics = [topic for topic in log.data_list if topic.name == 'attitude_sta_status' and topic.multi_id == 0]
    assert len(topics) == 1
    topic = topics[0].data
    times = topic['timestamp'].astype(np.int64)
    fields = [name for name in topic if name.startswith('att_')]
    assert len(fields) == 12 and np.all(np.diff(times) > 0)
    assert all(np.isfinite(topic[name]).all() for name in fields)
    stopped_next = False
    try:
        check_order(manifest, 'O003')
    except ValueError as exc:
        assert 'Previous attempt failed' in str(exc)
        stopped_next = True
    assert stopped_next
    return dict(scope='offline diagnostic only; zero flights; no historical acceptance change',
        frozen_runner_sha256=sha256(HERE / 'run.py'), manifest_sha256=sha256(manifest_path),
        result_sha256=sha256(run / 'result.json'), ulog_sha256=native['sha256'],
        missing_hover_configuration=job_missing_hover_config,
        actual_collector_expectations=sampled, actual_verifier_expectations=verified,
        checker_fallback=job['diagnostic_expectations'], reproduced_error=reproduced,
        recorded_diagnostic_snapshot_passed=True, successful_diagnostic_cli_reads=len(diagnostic_commands),
        last_cli_diagnostic=parse_topic(diagnostic_commands[-1]['stdout']),
        native_topic=dict(samples=len(times), first_us=int(times[0]), last_us=int(times[-1]),
            maximum_gap_s=float(np.diff(times).max()) * 1e-6,
            twelve_fields_finite=True, dropout_count=len(log.dropouts), file_corruption=log.file_corruption),
        checks=['frozen_runner_matches_manifest', 'missing_hover_configuration',
                'both_collectors_select_empty', 'checker_reproduces_recorded_error',
                'recorded_snapshot_has_required_diagnostics', 'native_topic_finite_monotonic_present',
                'next_job_rejected'], next_job_rejected=stopped_next,
        interpretation='Collector/checker configuration fallback mismatch, not absent native publication. '
        'Partial flight remains invalid; no complete safety or performance conclusion.')


if __name__ == '__main__':
    print(json.dumps(diagnose(), indent=2, ensure_ascii=False, allow_nan=False))
