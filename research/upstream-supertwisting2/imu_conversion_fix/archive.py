#!/usr/bin/env python3
"""Archive offline evidence and a replayable patch; do not stage, commit or fly."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
MAIN = HERE.parents[2]
ORIGINAL = Path('/home/yr/Desktop/Codev-SuperTwisting2-original')
REPAIR = Path('/home/yr/Desktop/Codev-SuperTwisting2-imu-fix')
ROOT = Path('/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-IMU-FIX-20261102')
REL = 'src/modules/simulation/simulator_mavlink/'
TRACKED = {REL + n for n in ('CMakeLists.txt', 'SimulatorMavlink.cpp', 'SimulatorMavlink.hpp')}
TEST = REL + 'ImuConversionTest.cpp'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True)


def main():
    out = HERE / 'evidence01'
    assert not out.exists(), 'Never overwrite archived evidence'
    snapshot = json.loads((ROOT / 'snapshot.json').read_text())
    verified = json.loads((ROOT / 'verify01/verification.json').read_text())
    assert verified['status'] == 'conversion_repair_offline_passed_with_unchanged_upstream_PositionControl_failures'
    assert git(REPAIR, 'branch', '--show-current').strip() == 'research/sta2-sim-imu-fix'
    assert git(REPAIR, 'rev-parse', 'HEAD').strip() == snapshot['head']
    assert not git(REPAIR, 'diff', '--cached')
    assert set(git(REPAIR, 'diff', '--name-only').splitlines()) == TRACKED
    assert git(REPAIR, 'ls-files', '--others', '--exclude-standard').splitlines() == [TEST]
    assert git(MAIN, 'diff', '--binary') == (ROOT / 'original_snapshot/main_worktree.patch').read_text()
    assert git(ORIGINAL, 'status', '--short') == snapshot['original_status']
    assert git(ORIGINAL, 'submodule', 'status', '--recursive') == snapshot['submodules']
    for key in ('original_tracked_sha256', 'snapshot_sha256', 'frozen_b04_assets'):
        assert all(sha(p) == h for p, h in snapshot[key].items()), key
    for p, h in verified['source_sha256'].items():
        assert sha(p) == h
    assert sha(REPAIR / 'build/px4_sitl_default/bin/px4') == verified['firmware_sha256']
    for repo in (MAIN, REPAIR):
        subprocess.run(['git', '-C', str(repo), 'diff', '--check'], check=True)

    out.mkdir()
    patch = git(REPAIR, 'diff', '--binary', '--', *sorted(TRACKED))
    added = subprocess.run(['git', 'diff', '--no-index', '--', '/dev/null', TEST],
                           cwd=REPAIR, text=True, capture_output=True)
    assert added.returncode == 1 and not added.stderr
    patch += added.stdout
    patch_path = out / 'sta2_sim_imu_fix.patch'
    patch_path.write_text(patch)
    subprocess.run(['git', '-C', str(ORIGINAL), 'apply', '--check', str(patch_path)], check=True)
    subprocess.run(['git', '-C', str(REPAIR), 'apply', '--reverse', '--check', str(patch_path)], check=True)
    # Small machine-readable evidence only; binaries and large traces stay external.
    for name in ('verification.json', 'repaired.xml', 'repaired_ubsan.xml',
                 'unit-PositionControl.xml', 'original_PositionControl.xml'):
        shutil.copy2(ROOT / 'verify01' / name, out / name)
    external = {str(p): sha(p) for p in sorted(ROOT.iterdir()) if p.is_file()}
    external.update({str(p): sha(p) for p in sorted((ROOT / 'verify01').iterdir()) if p.is_file()})
    audit = dict(original_head=snapshot['head'], main_head=snapshot['main_head'],
                 repair_head=git(REPAIR, 'rev-parse', 'HEAD').strip(),
                 branch=git(REPAIR, 'branch', '--show-current').strip(),
                 changed_files=sorted(TRACKED | {TEST}),
                 original_sources_preserved=len(snapshot['original_tracked_sha256']),
                 frozen_b04_assets_preserved=len(snapshot['frozen_b04_assets']),
                 original_firmware_sha256=sha(ORIGINAL / 'build/px4_sitl_default/bin/px4'),
                 repaired_firmware_sha256=verified['firmware_sha256'],
                 original_status_unchanged=True, main_tracked_diff_unchanged=True,
                 patch_forward_and_reverse_check_exit=0, diff_check_exit=0,
                 new_flights=0, committed=False, pushed=False,
                 external_sha256=external,
                 archive_sha256={p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()})
    (out / 'scope_audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    print(json.dumps({k: audit[k] for k in ('changed_files', 'original_sources_preserved',
                                          'frozen_b04_assets_preserved', 'new_flights')}, indent=2))


if __name__ == '__main__':
    main()
