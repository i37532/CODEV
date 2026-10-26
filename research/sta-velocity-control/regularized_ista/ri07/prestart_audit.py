"""RI07 read-only entry audit. No simulator, seed consumption or flight API.

Exit 2 means blocked before any formal attempt, not a failed flight.
The disk rule is inherited verbatim from RI06 tools/runner.py:precheck.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
PACKAGE = HERE.parent / 'ri06/results/final02/package.json'
PACKAGE_SHA = 'd9351d9a4f76d66274739928b60cf8df6499f03ac21e6198f2e075ae6bd3e842'
GIB = 1024 ** 3
MIB = 1024 ** 2


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda: f.read(MIB), b''):
            h.update(data)
    return h.hexdigest()


def capacity(free, remaining):
    if type(free) is not int or free < 0 or type(remaining) is not int or not 0 <= remaining <= 200:
        raise ValueError('Invalid capacity inputs')
    required = 12 * GIB + remaining * 200 * MIB
    return dict(free_bytes=free, remaining=remaining, required_bytes=required,
                deficit_bytes=max(0, required-free), passed=free >= required,
                rule='200 MiB per remaining run + 12 GiB reserve; unchanged RI06 full-remaining rule')


def verify_assets(assets, root):
    mismatches = []
    for name, expected in assets.items():
        path = Path(root) / name
        actual = sha(path) if path.is_file() else None
        if actual != expected:
            mismatches.append(dict(path=str(path), expected=expected, actual=actual))
    return dict(count=len(assets), mismatches=mismatches, passed=not mismatches)


def formal_checks(f):
    jobs = f['jobs']
    if len(jobs) != 200 or len({j['id'] for j in jobs}) != 200:
        raise ValueError('Wrong exact formal matrix')
    if Counter(j['group'] for j in jobs) != {'A': 80, 'B': 120}:
        raise ValueError('Wrong A/B budget')
    for j in jobs:
        if j['status'] != 'unattempted' or j['flight_authorized'] is not False:
            raise ValueError('Frozen package is not an untouched RI06 declaration')
        p = j['parameters']
        expected = hashlib.sha256(json.dumps(p, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if expected != j['parameters_sha256']:
            raise ValueError('Parameters fingerprint mismatch')
        if j['mode'] != {'PID': 0, 'RSTA': 3, 'RISTA': 4}[j['candidate']]:
            raise ValueError('Mode/algorithm mismatch')
        if j['axes'] != (7 if j['mode'] else 0) or j['divisor'] != 1:
            raise ValueError('Axes/divisor mismatch')
        for key, value in dict(MC_RTC_MODE=0, MC_STA_AXES=0, MC_RTC_DIV=1,
                              MC_RATT_TEST=0, MC_STA_TKO_MGT=0, MPC_VC_DIV=1).items():
            if p[key] != value:
                raise ValueError('Wrong frozen inner control: ' + key)
    return dict(passed=True, planned=200, A=80, B=120, all_unattempted=True,
                parameters_checked=200, frozen_order_preserved=True)


def audit():
    evidence = dict(stage='RI07', utc=datetime.now(timezone.utc).isoformat(),
                    attempts=0, takeoffs=0, accepted_runs=0, invalid_flights=0,
                    unattempted=200, new_seed_consumption=0, flight_authorized=False, commands=[])
    def command(argv):
        r = subprocess.run(argv, cwd=REPO, text=True, capture_output=True)
        evidence['commands'].append(dict(argv=argv, exit_code=r.returncode, stdout=r.stdout, stderr=r.stderr))
        if r.returncode:
            raise ValueError('Read-only command failed: ' + repr(argv))
        return r.stdout
    evidence['branch'] = command(['git', 'branch', '--show-current']).strip()
    evidence['head'] = command(['git', 'rev-parse', 'HEAD']).strip()
    evidence['worktree'] = command(['git', 'status', '--porcelain'])
    require_branch = evidence['branch'] == 'research/ista-velocity-regularized'
    evidence['package_sha256'] = sha(PACKAGE)
    if evidence['package_sha256'] != PACKAGE_SHA or not require_branch:
        raise ValueError('Wrong branch or frozen package')
    f = json.loads(PACKAGE.read_text())['formal']
    evidence['formal'] = formal_checks(f)
    evidence['repo_assets'] = verify_assets(f['assets'], REPO)
    evidence['external_assets'] = verify_assets(f['external_assets'], '/')
    actual_subs = command(['git', 'submodule', 'status', '--recursive']).splitlines()
    normalize = lambda lines: sorted(' '.join(line.split()[:2]) for line in lines)
    subs_dirty = command(['git', 'submodule', 'foreach', '--quiet', '--recursive', 'git status --porcelain'])
    evidence['submodules'] = dict(count=len(actual_subs), matching=normalize(actual_subs)==normalize(f['submodules']),
        clean=not subs_dirty, revisions=actual_subs)
    firmware = REPO / 'build/px4_sitl_default/bin/px4'
    evidence['firmware'] = dict(path=str(firmware), sha256=sha(firmware), expected=f['firmware_sha256'])
    evidence['firmware']['matching'] = evidence['firmware']['sha256'] == f['firmware_sha256']
    evidence['frozen_executable_source'] = f['executable_source_head']
    evidence['changes_from_frozen_source'] = command(['git', 'diff', '--name-only', f['executable_source_head'], 'HEAD']).splitlines()
    eeprom = REPO / 'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
    evidence['eeprom'] = dict(path=str(eeprom), sha256=sha(eeprom), expected='06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc')
    evidence['eeprom']['matching'] = evidence['eeprom']['sha256'] == evidence['eeprom']['expected']
    evidence['capacity'] = capacity(shutil.disk_usage(eeprom.parent).free, 200)
    evidence['tmpfs_free_bytes'] = shutil.disk_usage('/dev/shm').free
    processes = command(['ps', '-eo', 'pid,comm,args'])
    evidence['simulators'] = [line for line in processes.splitlines()
                              if len(line.split()) > 1 and line.split()[1] in ('px4', 'gzserver', 'gzclient')]
    evidence['mounted_storage'] = command(['df', '-B1', '-x', 'tmpfs', '-x', 'devtmpfs', '-x', 'squashfs'])
    plots = HERE.parent / 'ri06/results/plots01'
    evidence['preserved_untracked_plots'] = {str(p.relative_to(REPO)): sha(p)
        for p in sorted(plots.rglob('*')) if p.is_file()}
    evidence['blockers'] = []
    if not evidence['capacity']['passed']:
        evidence['blockers'].append('Insufficient full-remaining disk forecast; no reduction or historical deletion permitted')
    if evidence['worktree']:
        evidence['blockers'].append('Workspace not clean: existing plot artifacts and this new prestart audit; no flight qualification claimed')
    for name in ('repo_assets', 'external_assets'):
        if not evidence[name]['passed']:
            evidence['blockers'].append(name + ' mismatch')
    if not evidence['firmware']['matching'] or not evidence['eeprom']['matching']:
        evidence['blockers'].append('Firmware or restored-parameter fingerprint differs')
    if not evidence['submodules']['matching'] or not evidence['submodules']['clean'] or evidence['simulators']:
        evidence['blockers'].append('Submodule or simulator conflict')
    evidence['not_executed'] = ['RI07 formal runner/admission implementation and qualification',
        'new build/full controller regression', 'fresh all-history seed clearance',
        'any SITL attempt', 'formal ULog decode/replay/statistics', 'push', 'hardware']
    evidence['status'] = 'blocked_before_batch' if evidence['blockers'] else 'prestart_only_not_flight_qualification'
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Do not overwrite an earlier audit')
    result = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(status=result['status'], capacity=result['capacity'], attempts=0,
                          assets=result['repo_assets']['count'], external=result['external_assets']['count'])))
    raise SystemExit(2 if result['blockers'] else 0)
