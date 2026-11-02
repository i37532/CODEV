#!/usr/bin/env python3
"""One-time B04 read-only workspace/source capture; no flight or parameter write."""
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
from prepare import SOURCE, sha256
from run import active_simulators

ROOT = Path('/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-ROS-OFFBOARD-20261102-B04')
MAIN = Path('/home/yr/Desktop/Codev-autopilot')
ORIGINAL = Path('/home/yr/Desktop/Codev-SuperTwisting2-original')


def command(argv, cwd=MAIN):
    result = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError((argv, result.returncode, result.stderr))
    return dict(argv=argv, cwd=str(cwd), exit_code=0, stdout=result.stdout, stderr=result.stderr)


def main():
    if active_simulators():
        raise ValueError('Active simulator/QGC before B04')
    ROOT.mkdir(exist_ok=False)
    source = json.loads(SOURCE.read_text())
    receipts = []
    for name, repo in (('main', MAIN), ('original', ORIGINAL)):
        item = command(['git', 'submodule', 'status', '--recursive'], repo)
        with (ROOT / ('submodules_' + name + '.txt')).open('x') as stream:
            stream.write(item['stdout'])
        receipts.append(item)
        for argv in (['git', 'status', '--short'], ['git', 'branch', '--show-current'],
                     ['git', 'rev-parse', 'HEAD']):
            receipts.append(command(argv, repo))
    with (ROOT / 'workspace_before.txt').open('x') as stream:
        for item in receipts:
            stream.write(json.dumps(item, ensure_ascii=False) + '\n')
    hashes = dict(source['assets'])
    for job in source['jobs']:
        hashes[str(Path(job['bin']) / 'px4')] = job['firmware_sha256']
        for relative, expected in job['source_assets'].items():
            hashes[str(Path(job['repo']) / relative)] = expected
    for path, expected in hashes.items():
        if sha256(path) != expected:
            raise ValueError('Original frozen source/asset changed: ' + path)
    for path in HERE.glob('*.py'):
        hashes[str(path)] = sha256(path)
    hashes[str(Path(__file__).resolve())] = sha256(__file__)
    with (ROOT / 'preflight_sha256.txt').open('x') as stream:
        for path, digest in sorted(hashes.items()):
            stream.write(digest + '  ' + path + '\n')
    print(json.dumps(dict(root=str(ROOT), verified_files=len(hashes), command_exit_codes=[r['exit_code'] for r in receipts])))


if __name__ == '__main__': main()
