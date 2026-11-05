#!/usr/bin/env python3
"""Read-only AX00 audit. Prints evidence; never launches PX4 or writes parameters."""
import hashlib
import json
import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[4]
BASE = REPO / 'research/sta-velocity-control'
HERE = Path(__file__).resolve().parent
COMMANDS = []


def command(args, cwd=REPO):
    r = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    COMMANDS.append(dict(argv=args, cwd=str(cwd), exit_code=r.returncode,
                         stdout=r.stdout, stderr=r.stderr))
    if r.returncode:
        raise RuntimeError(COMMANDS[-1])
    return r.stdout.strip()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def seed_scan():
    roots = [REPO / 'research', Path('/home/yr/Desktop/codev doc/experiments'),
             Path('/home/yr/Desktop/codev doc/plan')]
    # No exclusion of old protocols; only this audit's self-generated evidence.
    r = subprocess.run(['rg', '--files', '-g', '*.json', *map(str, roots)],
                       text=True, capture_output=True, check=True)
    wanted = set(range(51001, 51004)) | set(range(51011, 51014)) | set(range(52001, 52021))
    forbidden = set(range(41001, 41021))
    matches, reserved, invalid, exceptions = [], [], [], []
    manifest = hashlib.sha256()
    count = 0

    def numbers(v):
        if isinstance(v, bool): return set()
        if isinstance(v, int): return {v}
        if isinstance(v, str) and v.isdigit(): return {int(v)}
        if isinstance(v, list): return set().union(*(numbers(x) for x in v))
        return set()

    def walk(v, path, field=''):
        if isinstance(v, dict):
            for k, item in v.items():
                if 'seed' in k.lower():
                    for target, output in ((wanted, matches), (forbidden, reserved)):
                        found = target & numbers(item)
                        if found: output.append(dict(path=str(path), field=field+k, seeds=sorted(found)))
                walk(item, path, field+k+'.')
        elif isinstance(v, list):
            for i, item in enumerate(v): walk(item, path, field+str(i)+'.')

    for name in sorted(r.stdout.splitlines()):
        path = Path(name)
        if HERE in path.parents: continue
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        manifest.update((name+'\0'+digest+'\n').encode())
        if name == '/home/yr/Desktop/codev doc/experiments/M06-20260916/c02_regression_roll_diagnostic.json' and raw == b'':
            exceptions.append(dict(path=name, sha256=digest, reason='known unchanged empty diagnostic, not registry'))
            continue
        try: data = json.loads(raw)
        except (ValueError, UnicodeError):
            invalid.append(dict(path=name, sha256=digest)); continue
        count += 1
        walk(data, path)
    return dict(command=['rg', '--files', '-g', '*.json', *map(str, roots)], exit_code=r.returncode,
                roots=list(map(str, roots)), files_parsed=count, manifest_sha256=manifest.hexdigest(),
                candidate_numbers=sorted(wanted), candidate_matches=matches, invalid_json=invalid,
                known_exceptions=exceptions, forbidden_numbers=sorted(forbidden),
                forbidden_match_count=len(reserved), forbidden_files=sorted({x['path'] for x in reserved}),
                status='not allocated; recheck before AX02/AX04',
                scope='Structured JSON seed keys only; not proof of IID or all RNG control; text search separately')


def main():
    branch = command(['git', 'branch', '--show-current'])
    head = command(['git', 'rev-parse', 'HEAD'])
    if branch != 'research/sta-velocity-control': raise RuntimeError('Wrong branch')
    command(['git', 'status', '--short'])
    submodules = command(['git', 'submodule', 'status', '--recursive'])
    # Preserve leading status character: command().strip() removes first leading space only.
    if any(line.startswith(('-', '+', 'U')) for line in submodules.splitlines()):
        raise RuntimeError('Submodule revision mismatch')
    command(['git', 'submodule', 'foreach', '--quiet', '--recursive',
             'test -z "$(git status --porcelain)"'])
    protected = ['src', 'msg', 'Tools', 'sitl', 'ROMFS', 'boards',
                 'research/sta-velocity-control/v08']
    diff = command(['git', 'diff', '05a8ae3b3c00cf14dd575d87417296baa1996f69', '--', *protected])
    if diff: raise RuntimeError('Protected implementation/model/V08 changed')
    selection = read(BASE/'v08/formal/selection.json')
    base = read(BASE/'v08/formal/pid/frozen.json')['control_parameters']
    xyz = read(BASE/'e01_xyz/qualified_xyz.json')
    pid = {**base, **selection['parameters']['0']}
    esta = {**base, **selection['parameters']['1']}
    # Audit-only candidate, NOT a loadable/qualified flight config.
    candidate = {**pid, 'MPC_VCT_TEST': 0}
    for axis in 'XY':
        for prefix in ('L1', 'L2', 'NU', 'A'):
            key = 'MPC_VC_'+prefix+'_'+axis
            candidate[key] = esta[key]
    for prefix in ('L1', 'L2', 'NU', 'A'):
        key = 'MPC_VC_'+prefix+'_Z'
        candidate[key] = xyz['parameters'][key]
    # Historical actual runtime snapshots establish original composition.
    runtime = {}
    for run in ('run01', 'run02'):
        p = BASE/'v08/results04'/run/'runtime_parameters_start.json'
        actual = read(p)
        keys = set(base) | set(selection['parameters']['0'])
        runtime[run] = dict(path=str(p.relative_to(REPO)), sha256=sha(p),
                           audited_parameters={k: actual[k] for k in sorted(keys) if k in actual})
    invariant = dict(MC_RTC_MODE=0, MC_STA_AXES=0, MC_RTC_DIV=1, MC_RATT_TEST=0,
                     MC_STA_TKO_MGT=0, MPC_VC_DIV=1, MPC_Z_VEL_P_ACC=4,
                     MPC_Z_VEL_I_ACC=2, MPC_Z_VEL_D_ACC=0, MPC_USE_HTE=1)
    for k, v in invariant.items():
        if any(r['audited_parameters'].get(k) != v for r in runtime.values()):
            raise RuntimeError('Historical invariant mismatch '+k)
    zpath = BASE/'z_velocity/results03/run02/runtime_parameters_start.json'
    zruntime = read(zpath)
    for prefix in ('L1', 'L2', 'NU', 'A'):
        key = 'MPC_VC_'+prefix+'_Z'
        if zruntime[key] != xyz['parameters'][key]: raise RuntimeError('Z03/E01 gain mismatch '+key)
    sources = list((REPO/'src/modules/mc_pos_control').glob('*.cpp'))
    sources += list((REPO/'src/modules/mc_pos_control').glob('*.hpp'))
    sources += list((REPO/'src/modules/mc_pos_control/PositionControl').glob('*.*'))
    sources += [REPO/'src/modules/mc_pos_control/mc_pos_control_params.c',
                REPO/'msg/sta_velocity_ctrl_status.msg', REPO/'msg/velocity_ctrl_selection.msg',
                REPO/'src/modules/logger/logged_topics.cpp', REPO/'sitl/run.sh',
                REPO/'sitl/worlds/empty_grey.world', REPO/'Tools/sitl_gazebo/models/iris/iris.sdf',
                BASE/'v08/formal/selection.json', BASE/'v08/formal/execution.json',
                BASE/'v08/formal/manifest.json', BASE/'v08/formal/pid/frozen.json',
                BASE/'v08/formal/esta/frozen.json', BASE/'e01_xyz/qualified_xyz.json',
                BASE/'v06/soft_landing/qualified_contact.json', BASE/'v06/scripts/toolbox.py',
                zpath, BASE/'v08/protocol02/common.py', BASE/'v08/protocol02/run.py',
                BASE/'v08/protocol02/core.py', BASE/'v08/protocol02/cadence.py',
                BASE/'v08/formal/analyze.py', BASE/'v06/protocol03/xyzcore.py',
                BASE/'v06/soft_landing/contact_model.py']
    root = ET.parse(REPO/'Tools/sitl_gazebo/models/iris/iris.sdf').getroot()
    model = root.find('model')
    physical = {}
    for link in model.findall('link'):
        inertial = link.find('inertial')
        if inertial is not None:
            physical[link.attrib['name']] = ET.tostring(inertial, encoding='unicode')
    seeds = seed_scan()
    if seeds['candidate_matches'] or seeds['invalid_json']:
        raise RuntimeError('Candidate seed collision or unaudited invalid registry')
    command(['g++', '--version'])
    result = dict(stage='AX00', audit_completed=True, branch=branch, audited_head=head,
                  commands=COMMANDS, submodule_count=len(submodules.splitlines()),
                  protected_paths_unchanged=protected,
                  source_sha256={str(p.relative_to(REPO)):sha(p) for p in sorted(set(sources)) if p.is_file()},
                  parameters=dict(meaning='audit inventory, not flight authorization or unified-matrix qualification',
                    base_control_parameters=base, v08_selected_overrides=selection['parameters'],
                    historical_runtime=runtime, historical_xyz_overrides=xyz['parameters'],
                    z03_runtime=dict(path=str(zpath.relative_to(REPO)), sha256=sha(zpath),
                        audited_parameters={k:v for k,v in zruntime.items() if k.startswith(('MPC_', 'MC_', 'SYS_VEHICLE_RESP'))}),
                    proposed_fixed_per_axis_baseline=candidate,
                    new_matrix_qualification=False,
                    hidden_pid_gain_difference='V08 ESTA idle XY PID 1.8/.4/.2 versus selected PID 2.16/.48/.24; use common selected PID gains in future mixed groups'),
                  model=dict(nominal_iris_inertials=physical,
                    contact_source='research/sta-velocity-control/v06/soft_landing/qualified_contact.json',
                    axes='local NED, not body roll/pitch/yaw', hardware_validated=False),
                  seeds=seeds, new_flights=0, full_sitl_build=False, matlab=False)
    eeprom = REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
    result['persisted_eeprom'] = dict(path=str(eeprom), sha256=sha(eeprom),
        meaning='read-only fingerprint; no new live runtime verification')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
