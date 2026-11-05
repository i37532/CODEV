"""Snapshot current formal dependencies without changing old snapshots."""
import argparse
import json
import re
import shutil
import subprocess
import sys
import platform
import numpy as np
from pathlib import Path
from common import CONFIG, REPO, fingerprint
from design import OLD, BASE_HEAD

PRODUCTION = ['src','msg','Tools','platforms','sitl','ROMFS','boards','cmake','CMakeLists.txt','Makefile','.gitmodules']


def capture():
    old = json.loads((OLD/'frozen.json').read_text())
    assets = dict(old['assets'])
    for rel, sha in assets.items():
        if fingerprint(REPO/rel) != sha:
            raise ValueError('Changed AX03 dependency '+rel)
    for path, sha in old['external_assets'].items():
        if fingerprint(path) != sha:
            raise ValueError('Changed external dependency '+path)
    for path in CONFIG.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts and path.name != 'frozen.json' and 'results' not in path.parts:
            assets[str(path.relative_to(REPO))] = fingerprint(path)
    for path in (CONFIG.parent/'ax03/results').glob('*.json'):
        assets[str(path.relative_to(REPO))] = fingerprint(path)
    replay = REPO/'research/sta-velocity-control/v08/evidence_tools/replay_batch.py'
    assets[str(replay.relative_to(REPO))] = fingerprint(replay)
    version = (REPO/'build/px4_sitl_default/src/lib/version/build_git_version.h').read_text()
    head = re.search(r'#define PX4_GIT_VERSION_STR "([0-9a-f]{40})"', version)[1]
    if subprocess.check_output(['git','diff',head,'--',*PRODUCTION], cwd=REPO):
        raise ValueError('Current production tree differs from frozen firmware build')
    if subprocess.check_output(['git','diff','ab9df703f837a3cb2b78a9295c5d4202e4f5a3ff','--',*PRODUCTION], cwd=REPO):
        raise ValueError('Production differs from qualified AX03')
    return dict(baseline_head=BASE_HEAD, production_paths=PRODUCTION,
        source_binding='AX04 post-commit qualified_source.json binds final clean commit and its exact rebuilt binary; AX05 requires that exact commit/binary/receipt, no automatic refresh',
        assets=assets, external_assets=old['external_assets'], control_parameters=old['control_parameters'],
        derived_iris_sha256=old['derived_iris_sha256'],
        firmware=dict(path='build/px4_sitl_default/bin/px4', sha256=fingerprint(REPO/'build/px4_sitl_default/bin/px4'),
                      build_head=head, relation='Offline rebuilt during AX04; production source unchanged from AX03, version metadata differs'),
        generated_parameters_sha256=fingerprint(REPO/'build/px4_sitl_default/parameters.json'),
        environment=dict(python=sys.version,numpy=np.__version__,numpy_path=np.__file__,
            numpy_init_sha256=fingerprint(np.__file__),platform=platform.platform(),
            compiler=subprocess.check_output(['g++','--version'],text=True).splitlines()[0],
            cmake=subprocess.check_output(['cmake','--version'],text=True).splitlines()[0]),
        submodules=subprocess.check_output(['git','submodule','status','--recursive'],cwd=REPO,text=True).splitlines(),
        random_scope=old['random_scope'], new_flights=0)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check', action='store_true')
    p.add_argument('--archive-firmware', type=Path)
    args = p.parse_args()
    current = capture()
    if args.check:
        frozen = json.loads((CONFIG/'frozen.json').read_text())
        # Final clean-source build is bound by qualified_source.json. The
        # precommit firmware fingerprint below is historical, never silently
        # used to authorize a new binary. All other assets must match exactly.
        current['firmware'] = frozen['firmware']
        if current != frozen:
            raise ValueError('Frozen formal assets changed')
        print('Frozen snapshot matches:', len(current['assets']), 'repository assets')
    else:
        with (CONFIG/'frozen.json').open('x') as stream:
            json.dump(current, stream, indent=2); stream.write('\n')
    if args.archive_firmware:
        args.archive_firmware.mkdir(parents=True, exist_ok=False)
        shutil.copy2(REPO/current['firmware']['path'], args.archive_firmware/'px4')
        if fingerprint(args.archive_firmware/'px4') != current['firmware']['sha256']:
            raise ValueError('Firmware archive mismatch')


if __name__ == '__main__':
    main()
