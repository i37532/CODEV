#!/usr/bin/env python3
"""Archive RI01 small evidence and fingerprint ALL retained offline attempts.

Does not run tests, modify external evidence, or launch PX4/Gazebo.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify', action='store_true', help='read-only verify existing index')
    args = parser.parse_args()
    root, out = args.evidence_dir.resolve(), args.output.resolve()
    assert root.is_dir() and root != out and root not in out.parents
    if args.verify:
        index = json.loads((out/'external_artifacts.json').read_text())
        assert str(root) == index['root']
        for name, item in index['files'].items():
            path = root/name
            assert path.stat().st_size == item['bytes'] and sha(path) == item['sha256'], name
        print(json.dumps(dict(verified_files=len(index['files']), exit_code=0)))
        return
    final = root/'verification03'
    evidence = json.loads((final/'evidence.json').read_text())
    assert evidence['success'] and evidence['counts']['cpp_unique'] == 517
    assert all(command['exit_code'] == 0 for command in evidence['commands'])
    for name, expected in evidence['input_sha256'].items():
        assert sha(Path(name)) == expected, name
    directories = sorted(p.name for p in root.iterdir() if p.is_dir())
    assert directories == sorted(['tests_attempt01', 'tests_attempt02', 'tests_attempt03',
        'model_attempt01', 'model_attempt02', 'verification01', 'verification02', 'verification03'])
    out.mkdir(parents=True, exist_ok=False)
    for name in ('evidence.json', 'artifacts.json', 'submodules.log', 'submodule_status.log'):
        shutil.copyfile(final/name, out/name)
    for path in sorted(final.glob('*.xml')):
        shutil.copyfile(path, out/path.name)
    index = {str(path.relative_to(root)): dict(bytes=path.stat().st_size, sha256=sha(path))
             for path in sorted(root.rglob('*')) if path.is_file()}
    payload = dict(root=str(root), directories=directories, files=index,
                   note='All eight offline attempts retained; no flight; files added later are not covered by this index.')
    (out/'external_artifacts.json').write_text(json.dumps(payload, indent=2)+'\n')
    print(json.dumps(dict(archived_xml=len(list(out.glob('*.xml'))),
                         external_files=len(index), external_bytes=sum(x['bytes'] for x in index.values()),
                         output=str(out), exit_code=0), indent=2))


if __name__ == '__main__':
    main()
