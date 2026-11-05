#!/usr/bin/env python3
"""Index every retained M07 attempt (including failures); never overwrite an index."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', required=True, type=Path)
    parser.add_argument('--final', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root = args.data_root.resolve()
    attempts = sorted(root.glob('attempt*/evidence.json'))
    assert attempts, 'No recorded attempts'
    assert args.final in [p.parent.name for p in attempts], 'Final attempt must be recorded'
    records = []
    for path in attempts:
        data = json.loads(path.read_text())
        for line in (path.parent / 'artifacts.sha256').read_text().splitlines():
            expected, filename = line.split('  ', 1)
            assert digest(Path(filename)) == expected, filename
        records.append(dict(attempt=path.parent.name, passed=data['passed'], failure=data.get('failure'),
                            evidence=str(path), sha256=digest(path),
                            commands=json.loads((path.parent / 'commands.json').read_text())))
    final = json.loads((root / args.final / 'evidence.json').read_text())
    assert final['passed'], 'Cannot summarize a failed final attempt as accepted'
    repo = Path(__file__).resolve().parents[3]
    assert all(digest(repo / p) == sha for p, sha in final['sources'].items()), 'Tested source drift'
    final.update(attempts=records, data_root=str(root), accepted_attempt=args.final)
    files = sorted(p for p in root.rglob('*') if p.is_file())
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'artifacts.sha256').write_text(''.join(f'{digest(p)}  {p}\n' for p in files))
    final['artifact_count'] = len(files)
    final['index_sha256'] = digest(args.output / 'artifacts.sha256')
    (args.output / 'evidence.json').write_text(json.dumps(final, indent=2) + '\n')
    print(json.dumps(dict(attempts=len(attempts), artifacts=len(files), index_sha256=final['index_sha256'])))


if __name__ == '__main__':
    main()
