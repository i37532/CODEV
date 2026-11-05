#!/usr/bin/env python3
"""Bind successful RI02 offline evidence and retain every earlier attempt index."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from verify import ALLOWED, BASE, HERE, REPO, require, sha


def describe(path):
    return dict(bytes=path.stat().st_size, sha256=sha(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpp', type=Path, required=True)
    parser.add_argument('--tools', type=Path, required=True)
    parser.add_argument('--attempt-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cpp, tool = [json.loads((p / 'evidence.json').read_text()) for p in (args.cpp, args.tools)]
    require(cpp['success'] and tool['success'], 'Unsuccessful final qualification')
    require(cpp['new_flights'] == tool['new_flights'] == 0, 'Offline-only stage')
    require(cpp['counts']['cpp_unique'] > 0 and tool['python_tests'] > 0, 'Zero test count')
    require(tool['historical_replays'] == 36, 'Incomplete final historical replay')
    require(all(sha(path) == expected for path, expected in cpp['input_sha256'].items()), 'C++ inputs changed')
    require(all(sha(REPO / path) == expected for path, expected in tool['source_sha256_after'].items()), 'Tool inputs changed')
    commands = []

    def command(argv):
        done = subprocess.run(argv, cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        commands.append(dict(argv=argv, exit_code=done.returncode, stdout=done.stdout))
        require(done.returncode == 0, 'Audit command failed: ' + repr(argv))
        return done.stdout.strip()

    require(command(['git', 'rev-parse', 'HEAD']) == BASE, 'Baseline changed')
    require(command(['git', 'branch', '--show-current']) == 'research/ista-velocity-regularized', 'Wrong branch')
    require(not command(['git', 'submodule', 'foreach', '--quiet', '--recursive', 'git status --porcelain']), 'Dirty submodule')
    sm = command(['git', 'submodule', 'status', '--recursive'])
    require(len(sm.splitlines()) == 33 and not any(s.startswith(('+', '-', 'U')) for s in sm.splitlines()), 'Submodule mismatch')
    frozen_path = REPO / 'research/sta-velocity-control/regularized_sta/r03_revision11/gates/D/frozen.json'
    frozen = json.loads(frozen_path.read_text())
    changed = []
    for name, expected in frozen['assets'].items():
        actual = sha(REPO / name)
        if actual != expected:
            require(name in ALLOWED, 'Unexpected old frozen asset change: ' + name)
            changed.append(dict(path=name, original=expected, current=actual))
    for name, expected in frozen['external_assets'].items():
        require(sha(Path(name)) == expected, 'External model/plugin/input changed: ' + name)
    param = REPO / 'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
    require(sha(param) == cpp['eeprom_before'] == cpp['eeprom_after'], 'Runtime parameters changed')
    require(sha(REPO / 'build/px4_sitl_default/bin/px4') == cpp['firmware_sha256'], 'Firmware changed')
    source_package = Path('/home/yr/Desktop/STA-ISTA-MATLAB-PX4')
    sources = json.loads((HERE.parent / 'ri00/results/source_fingerprints.json').read_text())
    require(all(sha(source_package / name) == item['sha256'] for name, item in sources.items()), 'Source package changed')
    environment = {name: command(argv) for name, argv in {
        'python': [sys.executable, '--version'], 'compiler': ['g++', '--version'],
        'cmake': ['cmake', '--version'], 'ctest': ['ctest', '--version'], 'platform': ['uname', '-a']}.items()}
    command(['git', 'diff', '--check'])
    require(not args.output.exists(), 'No evidence overwrite')
    args.output.mkdir(parents=True)
    shutil.copyfile(args.cpp / 'evidence.json', args.output / 'cpp_evidence.json')
    shutil.copyfile(args.tools / 'evidence.json', args.output / 'tools_evidence.json')
    index = {str(path): describe(path) for path in sorted(args.attempt_root.rglob('*')) if path.is_file()}
    attempts = []
    for folder in sorted(args.attempt_root.iterdir()):
        if not folder.is_dir():
            continue
        summaries = []
        for filename in ('command.json', 'evidence.json', 'summary.json'):
            path = folder / filename
            if path.exists():
                value = json.loads(path.read_text())
                summaries.append(dict(path=str(path), sha256=sha(path), success=value.get('success'),
                    exit_code=value.get('exit_code', value.get('returncode')), failure=value.get('failure', value.get('error'))))
        attempts.append(dict(path=str(folder), summaries=summaries))
    result = dict(success=True, baseline=BASE, new_flights=0, new_seeds=0,
        cpp=str(args.cpp), tools=str(args.tools), counts={**cpp['counts'], 'python_tools': tool['python_tests']},
        source_package_files_verified=len(sources), submodules=sm,
        historical_assets=dict(total=len(frozen['assets']), unchanged=len(frozen['assets'])-len(changed),
            changed_explicit_ri02_scope=changed, external_verified=len(frozen['external_assets']),
            derived_iris_sha256=frozen['derived_iris_sha256'], frozen_file=describe(frozen_path)),
        environment=environment, commands=commands, previous_attempts=attempts,
        external_artifacts=index, external_artifact_count=len(index),
        qualification_scope='Offline code + build + fixtures + read-only historical replay; not a new flight qualification',
        firmware_sha256=cpp['firmware_sha256'], eeprom_sha256=cpp['eeprom_after'])
    (args.output / 'archive.json').write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    print(json.dumps({k: result[k] for k in ('success', 'counts', 'external_artifact_count', 'historical_assets')}, indent=2))


if __name__ == '__main__':
    main()
