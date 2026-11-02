#!/usr/bin/env python3
"""Offline B02/CLI regression. Does not rewrite results or qualify new flights."""
import argparse
import json
from pathlib import Path

import numpy as np
from pyulog import ULog

from analyze import audit_native_log
from prepare import sha256
from run import collect_diagnostics, parse_topic, check_parameters, parse_parameters
from runner_contract import _check_diagnostics, check_order

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-ROS-OFFBOARD-20261102-B02')


def replay():
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    protected = {str(path): sha256(path) for path in ROOT.rglob('*') if path.is_file()}
    fixture_path = HERE / 'results/diagnostic_fix01/cli_fixture.json'
    fixture = json.loads(fixture_path.read_text())
    assert fixture['manifest_sha256'] == sha256(ROOT / 'manifest.json')
    cli_replays = []
    for job in manifest['jobs'][:4]:
        row = fixture['systems'][job['system']]
        assert sha256(row['command_path']) == row['command_sha256']
        assert sha256(row['parameters_path']) == row['parameters_sha256']
        commands = [json.loads(line) for line in Path(row['command_path']).read_text().splitlines()]
        check_parameters(parse_parameters(row['parameter_lines']), job['expected_parameters'])
        for topic, record in row['diagnostics'].items():
            original = commands[record['row_index']]
            assert original['argv'][1:] == [topic, '-n', '1']
            assert original['stdout'] == record['stdout']
        for scored in (False, True):
            reads = []
            def read_topic(topic):
                reads.append(topic)
                return parse_topic(row['diagnostics'][topic]['stdout'])
            actual = collect_diagnostics(job, scored, read_topic)
            _check_diagnostics({'diagnostics': actual}, job, scored)
            assert len(reads) == len(set(reads)) == len(actual)
        cli_replays.append(dict(system=job['system'], original_stdout_verified=True,
                                both_configuration_paths_passed=True))
    replay_rows = []
    for name in ('O001', 'O002'):
        root = ROOT / 'runs' / name
        result = json.loads((root / 'result.json').read_text())
        job = json.loads((root / 'job.json').read_text())
        origin = json.loads((root / 'origin.json').read_text())
        raw = max(result['logs'], key=lambda row: row['bytes'])
        assert sha256(raw['archive']) == raw['sha256']
        args = (raw['archive'], result['events'], origin, job, root / 'ros/sent.jsonl')
        if name == 'O001':
            current = audit_native_log(*args)
            assert current == json.loads((root / 'metrics.json').read_text())
            assert current == json.loads((root / 'independent_replay.json').read_text())
            replay_rows.append(dict(id=name, original_success=True, complete_metrics_exact=True,
                                    ulog_sha256=raw['sha256']))
        else:
            log = ULog(raw['archive'], message_name_filter_list=['attitude_sta_status'])
            topics = [item for item in log.data_list if item.name == 'attitude_sta_status' and item.multi_id == 0]
            assert len(topics) == 1 and not log.file_corruption and not log.dropouts
            data = topics[0].data
            assert np.all(np.diff(data['timestamp'].astype(np.int64)) > 0)
            assert all(np.isfinite(values).all() for values in data.values())
            try:
                audit_native_log(*args)
            except ValueError as exc:
                rejected = str(exc)
            else:
                raise AssertionError('Partial STA2 task must not become accepted')
            assert rejected == 'Unpaired phase event: hover'
            assert result['success'] is False and result['independent_replay_passed'] is False
            replay_rows.append(dict(id=name, original_success=False, still_rejected=rejected,
                                    native_diagnostic_samples=len(data['timestamp']), ulog_sha256=raw['sha256']))
    try:
        check_order(manifest, 'O003')
    except ValueError as exc:
        assert 'Previous attempt failed' in str(exc)
    else:
        raise AssertionError('Failed batch must remain closed')
    assert protected == {path: sha256(path) for path in protected}
    return dict(new_flights=0, diagnostic_only=True, new_manifest_created=False,
        cli_fixture_sha256=sha256(fixture_path), cli_replays=cli_replays, ulog_replays=replay_rows,
        original_evidence_unchanged=True, protected_files=len(protected),
        source_sha256={name: sha256(HERE / name) for name in
                       ('run.py', 'runner_contract.py', 'analyze.py', 'test_diagnostic_wiring.py', 'replay_diagnostic_fix.py')})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve().is_relative_to(ROOT):
        raise ValueError('Require a new output outside the frozen batch')
    result = replay()
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
