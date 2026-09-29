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
    protocol = repo / 'research/sta-velocity-control/v07/protocol04'
    frozen = json.loads((protocol / 'frozen.json').read_text())
    for name, expected in frozen['assets'].items():
        assert sha(repo / name) == expected, name
    ledger = json.loads((root / 'series04/ledger.json').read_text())
    summary = json.loads((root / 'assessment04/summary.json').read_text())
    audit = json.loads((root / 'recording_audit04/evidence.json').read_text())
    verification = json.loads((root / 'verification_committed04/evidence.json').read_text())
    assert not ledger['success'] and not summary['success'] and not audit['complete']
    assert len(ledger['attempts']) == len(audit['runs']) == 5 and summary['accepted']==4
    assert len(summary['pairs']) == 2 and all(p['accepted'] for p in summary['pairs'])
    assert len(summary['replays']) == 4
    assert all(r['exit_code'] == 0 and r['metrics_byte_identical'] for r in summary['replays'])
    assert verification['success'] and verification['cpp_tests'] == 226 and verification['python_tests'] == 471
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
    (root / 'assessment04/raw_artifacts.sha256').write_text(
        ''.join(f'{sha(path)}  {path}\n' for path in files))
    output.mkdir(parents=True)
    copies = {
        'assessment04/summary.json': 'summary.json',
        'assessment04/raw_artifacts.sha256': 'raw_artifacts.sha256',
        'series04/ledger.json': 'ledger.json',
        'verification_committed04/evidence.json': 'verification.json',
        'recording_audit04/evidence.json': 'recording_audit.json',
        'authorization04.json': 'authorization.json',
        'verification_committed04/logger_file_chain/evidence.json': 'filename_probe.json',
        'verification_committed04/logger_file_chain/tests.xml': 'filename_tests.xml',
        'postprocess.py': 'tools_snapshot/postprocess.py',
        'audit_recording.py': 'tools_snapshot/audit_recording.py',
        'package_results04.py': 'tools_snapshot/package_results04.py',
    }
    for attempt in ledger['attempts']:
        run = Path(attempt['directory']).name
        for name in ('job.json', 'result.json', 'xyz_metrics.json', 'position_log_evidence.json', 'ulog_parameters.json'):
            relative = f'series04/{run}/{name}'
            if (root / relative).exists():
                copies[relative] = f'runs/{run}/{name}'
    manifest = []
    for source, target in copies.items():
        destination = output / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / source, destination)
        manifest.append(dict(source=str(root / source), repository_file=target,
                             sha256=sha(destination)))
    result = dict(status='failed/landing_evidence_poll_deadline', source_head=ledger['source_head'],
                  accepted=4, failed=1, cancelled=13, complete_pairs=2,
                  new_flights=0, raw_files=len(files), ulogs=len(logs),
                  frozen_assets=len(frozen['assets']), parameter_restore_exact=True,
                  raw_index_sha256=sha(output / 'raw_artifacts.sha256'), copies=manifest)
    (output / 'archive.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'copies'}))


if __name__ == '__main__':
    main()
