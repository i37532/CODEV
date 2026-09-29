"""Archive stopped V07 evidence only after flight/replay/audit writers exit.

No flight authority and no verdict rewriting. The repository must still match
the frozen flight assets. Large ULogs stay external; originals are rehashed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root, repo, output = args.root.resolve(), args.repo.resolve(), args.output.resolve()
    assert root.is_dir() and repo.is_dir() and not output.exists()
    protocol = repo / 'research/sta-velocity-control/v07/protocol05'
    frozen = json.loads((protocol / 'frozen.json').read_text())
    for name, expected in frozen['assets'].items():
        assert sha(repo / name) == expected, name
    ledger = json.loads((root / 'series05/ledger.json').read_text())
    summary = json.loads((root / 'assessment05/summary.json').read_text())
    audit = json.loads((root / 'recording_audit05/evidence.json').read_text())
    verification = json.loads((root / 'verification_committed05/evidence.json').read_text())
    assert not ledger['success'] and not summary['success'] and not audit['complete']
    assert len(ledger['attempts']) == len(audit['runs']) == 2 and summary['accepted']==1
    assert len(summary['pairs']) == 0
    assert len(summary['replays']) == 1
    assert all(r['exit_code'] == 0 and r['metrics_byte_identical'] for r in summary['replays'])
    assert verification['success'] and verification['cpp_tests'] == 226 and verification['python_tests'] == 479
    assert ledger['parameter_restore_exact'] and not ledger['remaining_simulators']
    parameter = repo / 'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
    assert sha(parameter) == ledger['original_parameter_sha256']
    logs = []
    for attempt in ledger['attempts']:
        assert attempt['status'] in ('accepted','failed')
        record = json.loads((Path(attempt['directory']) / 'result.json').read_text())
        for log in record['logs']:
            assert sha(Path(log['archive'])) == log['sha256']
            logs.append(log)
    # Run without redirecting stdout to a file under root: no index of open files.
    files = sorted(p for p in root.rglob('*') if p.is_file()
                   and not p.is_symlink() and p.name != 'raw_artifacts.sha256')
    (root / 'assessment05/raw_artifacts.sha256').write_text(
        ''.join(f'{sha(path)}  {path}\n' for path in files))
    output.mkdir(parents=True)
    copies = {
        'assessment05/summary.json': 'summary.json',
        'assessment05/raw_artifacts.sha256': 'raw_artifacts.sha256',
        'series05/ledger.json': 'ledger.json',
        'verification_committed05/evidence.json': 'verification.json',
        'recording_audit05/evidence.json': 'recording_audit.json',
        'authorization05.json': 'authorization.json',
        'verification_committed05/logger_file_chain/evidence.json': 'filename_probe.json',
        'verification_committed05/logger_file_chain/tests.xml': 'filename_tests.xml',
        'verification_committed05/pending_clock_audit/evidence.json': 'pending_audit.json',
        'postprocess.py': 'tools_snapshot/postprocess.py',
        'audit_recording.py': 'tools_snapshot/audit_recording.py',
        'package_results05.py': 'tools_snapshot/package_results05.py',
    }
    for attempt in ledger['attempts']:
        run = Path(attempt['directory']).name
        for name in ('job.json', 'result.json', 'xyz_metrics.json', 'position_log_evidence.json', 'ulog_parameters.json','landing_pending_poll.jsonl'):
            relative = f'series05/{run}/{name}'
            if (root / relative).exists():
                copies[relative] = f'runs/{run}/{name}'
    manifest = []
    for source, target in copies.items():
        destination = output / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / source, destination)
        manifest.append(dict(source=str(root / source), repository_file=target,
                             sha256=sha(destination)))
    result = dict(status='failed/raw_ulog_writer_dropout', source_head=ledger['source_head'],
                  accepted=1, failed=1, cancelled=16, complete_pairs=0,
                  new_flights=0, raw_files=len(files), ulogs=len(logs),
                  frozen_assets=len(frozen['assets']), parameter_restore_exact=True,
                  raw_index_sha256=sha(output / 'raw_artifacts.sha256'), copies=manifest)
    (output / 'archive.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'copies'}))


if __name__ == '__main__':
    main()
