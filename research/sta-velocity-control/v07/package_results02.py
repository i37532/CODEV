"""Archive stopped V07 batch evidence. Read-only w.r.t. flights and source assets.

Run only after all flight/replay log writers have exited. This creates an index,
not a new acceptance decision. Re-running requires a different --output.
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
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    assert root.is_dir() and not output.exists()
    repo = Path(__file__).resolve().parents[3]
    protocol = repo / 'research/sta-velocity-control/v07/protocol02'
    frozen = json.loads((protocol / 'frozen.json').read_text())
    for name, expected in frozen['assets'].items():
        assert sha(repo / name) == expected, name
    ledger = json.loads((root / 'series02/ledger.json').read_text())
    summary = json.loads((root / 'assessment02/summary.json').read_text())
    verification = json.loads((root / 'verification_committed02/evidence.json').read_text())
    assert ledger['success'] is False and summary['success'] is False
    assert len(ledger['attempts']) == 9 and summary['accepted'] == 8
    assert len(summary['pairs']) == 4 and all(p['accepted'] for p in summary['pairs'])
    assert len(summary['replays']) == 8
    assert all(r['exit_code'] == 0 and r['metrics_byte_identical'] for r in summary['replays'])
    assert verification['success'] and verification['cpp_tests'] == 216 and verification['python_tests'] == 448
    assert ledger['parameter_restore_exact'] and not ledger['remaining_simulators']
    parameter = repo / 'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
    assert sha(parameter) == ledger['original_parameter_sha256']
    logs = []
    for attempt in ledger['attempts']:
        record = json.loads((Path(attempt['directory']) / 'result.json').read_text())
        for log in record['logs']:
            assert sha(Path(log['archive'])) == log['sha256']
            logs.append(log)
    files = sorted(p for p in root.rglob('*') if p.is_file()
                   and not p.is_symlink() and p.name != 'raw_artifacts.sha256')
    raw_index = ''.join(f'{sha(path)}  {path}\n' for path in files)
    # Previous exploratory index could include an open stdout log. Regenerate
    # after all writers exited; historical result/ULog files stay untouched.
    (root / 'assessment02/raw_artifacts.sha256').write_text(raw_index)
    output.mkdir(parents=True)
    copies = {
        'assessment02/summary.json': 'summary.json',
        'assessment02/raw_artifacts.sha256': 'raw_artifacts.sha256',
        'series02/ledger.json': 'ledger.json',
        'verification_committed02/evidence.json': 'verification.json',
        'failure_audit02/audit.json': 'failure_audit.json',
        'failure_audit02/inputs.sha256': 'failure_inputs.sha256',
        'local_position_loss01/evidence.json': 'local_position_loss_verification.json',
        'local_position_loss01/test.xml': 'local_position_loss_tests.xml',
        'clock_replay01/evidence.json': 'imu_replay.json',
        'authorization02.json': 'authorization.json',
        'postprocess.py': 'tools_snapshot/postprocess.py',
    }
    for attempt in ledger['attempts']:
        run = Path(attempt['directory']).name
        for name in ('job.json', 'result.json', 'xyz_metrics.json'):
            relative = f'series02/{run}/{name}'
            if (root / relative).exists():
                copies[relative] = f'runs/{run}/{name}'
    manifest = []
    for source, target in copies.items():
        destination = output / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / source, destination)
        manifest.append(dict(source=str(root / source), repository_file=target,
                             sha256=sha(destination)))
    result = dict(status='blocked/system_logging_evidence_loss', source_head=ledger['source_head'],
                  accepted=8, failed=1, cancelled=9, complete_pairs=4,
                  new_flights=0, raw_files=len(files), ulogs=len(logs),
                  frozen_assets=len(frozen['assets']), parameter_restore_exact=True,
                  raw_index_sha256=sha(output / 'raw_artifacts.sha256'), copies=manifest)
    (output / 'archive.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'copies'}))


if __name__ == '__main__':
    main()
