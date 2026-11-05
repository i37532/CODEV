#!/usr/bin/env python3
"""Publish RI00 small evidence, retaining both offline attempts externally."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
BASE = 'a286e40ec8bfbb0500b1c24add18c1a98b908778'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def describe(path):
    return {'bytes': path.stat().st_size, 'sha256': digest(path)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--previous-audit', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert args.audit != args.previous_audit
    for directory in (args.audit, args.previous_audit):
        assert json.loads((directory/'summary.json').read_text())['success']
    assert not args.output.exists(), 'Do not overwrite evidence'
    commands = []

    def command(argv):
        r = subprocess.run(argv, cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        commands.append({'argv': argv, 'exit_code': r.returncode, 'stdout': r.stdout})
        assert r.returncode == 0, commands[-1]
        return r.stdout.strip()

    head = command(['git', 'rev-parse', 'HEAD'])
    assert head == BASE
    assert command(['git', 'branch', '--show-current']) == 'research/ista-velocity-regularized'
    assert command(['git', 'rev-parse', 'research/sta-velocity-regularized']) == BASE
    assert not command(['git', 'diff', BASE, '--', 'src', 'msg', 'Tools', 'platforms', 'sitl', 'ROMFS', 'boards'])
    assert not command(['git', 'submodule', 'foreach', '--quiet', '--recursive', 'git status --porcelain'])
    submodules = command(['git', 'submodule', 'status', '--recursive'])
    assert len(submodules.splitlines()) == 33
    assert all(line[0] == ' ' for line in submodules.splitlines()[1:])
    # strip() removed just the first entry's leading space; compare actual entry snapshot too.
    entry = json.loads((args.audit/'entry.json').read_text())
    assert submodules == entry['submodules'].strip()
    for name, record in json.loads((args.audit/'source_fingerprints.json').read_text()).items():
        assert describe(Path('/home/yr/Desktop/STA-ISTA-MATLAB-PX4')/name) == record, name
    for name, expected in json.loads((args.audit/'interface.json').read_text())['code_fingerprints'].items():
        assert digest(REPO/name) == expected, name
    frozen_path = REPO/'research/sta-velocity-control/regularized_sta/r03_revision11/gates/D/frozen.json'
    frozen = json.loads(frozen_path.read_text())
    for name, expected in frozen['assets'].items():
        assert digest(REPO/name) == expected, name
    for name, expected in frozen['external_assets'].items():
        assert digest(Path(name)) == expected, name
    source_versions = {}
    for revision in ('eb25fecbdba9a499132a16ce16f6b847e4a218d3',
                     'b2883d7871f659cf810a0a527979c9c1f119fd41'):
        source_versions[revision] = command(['git', 'show', '-s', '--format=%H %s', revision])
    assert not command(['git', 'diff', *source_versions, '--', 'src', 'msg', 'sitl'])
    environment = {name: command(argv) for name, argv in {
        'python': [sys.executable, '--version'],
        'compiler': ['g++', '--version'],
        'cmake': ['cmake', '--version'],
        'ctest': ['ctest', '--version'],
        'platform': ['uname', '-a'],
    }.items()}
    # Logs and JSON only in the repo. Binaries/build files remain in external audit dirs.
    args.output.mkdir(parents=True)
    for path in sorted(args.audit.iterdir()):
        if path.is_file() and path.suffix in ('.json', '.log'):
            shutil.copyfile(path, args.output/path.name)
    external = {}
    for directory in (args.previous_audit, args.audit):
        for path in sorted(directory.rglob('*')):
            if path.is_file():
                external[str(path)] = describe(path)
    paths = [p for p in HERE.iterdir() if p.is_file()]
    paths += sorted((HERE.parent/'plan/v1').glob('*.md'))
    paths += sorted((HERE.parent/'plan/ri00_entry').glob('*.md'))
    tool_inputs = {str(p.relative_to(REPO)): describe(p) for p in paths}
    result = dict(success=True, source_base=head, r03_sources=source_versions,
        frozen_assets=describe(frozen_path), reverified_repo_assets=len(frozen['assets']),
        reverified_external_assets=len(frozen['external_assets']), environment=environment,
        commands=commands, ri00_files_at_archive=tool_inputs,
        external_artifacts=external,
        audit02_binding='probe.py/source_bridge.cpp unchanged since audit02; audit01 predates four additional tests and tracking label clarification',
        earlier_attempt_preserved=True, no_flight=True, no_seed_registration=True,
        source_tree_unchanged=True, production_unchanged=True,
        evidence_scope='Original source CTest + offline probes; not MATLAB rerun or PX4 regression/build/flight')
    with (args.output/'archive.json').open('x') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
    print(json.dumps({k: result[k] for k in ('success','reverified_repo_assets','reverified_external_assets','no_flight')},
                     indent=2))


if __name__ == '__main__':
    main()
