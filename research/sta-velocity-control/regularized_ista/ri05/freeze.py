"""RI05 source/asset freeze; no build, flight or authority creation.

Current capture inherits the accepted RI04 revision01 inventory and permits
only the named XY/XYZ admission, metadata comments and regression tests. Archived checks read Git blobs and nested gitlinks
at the claimed source; they do not require current HEAD/production equality.
"""
import argparse
from collections import defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('_ri05_freeze_protocol', HERE/'protocol.py')
p = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p)
REPO = p.REPO
ENTRY_HEAD = 'bbc5396c272666bd20f526a54113e9698e87c16b'
PRIOR_ROOT = 'research/sta-velocity-control/regularized_ista/ri04_revision01'
REPAIR_ROOT = 'research/sta-velocity-control/regularized_ista/ri04_hte_fix'
BASE = REPO/PRIOR_ROOT/'gates/B/frozen.json'
BASE_SHA = '21a6d96b25284ba5ddd5277e4cc05b8d1a7fb7735ac3e34f863a08d6a1a02a61'
BASE_COUNT = 1049
PRODUCTION = ('src', 'msg', 'Tools', 'platforms', 'sitl', 'ROMFS', 'boards',
              'cmake', 'CMakeLists.txt', 'Makefile', '.gitmodules', 'mavlink')
MODULE = 'src/modules/mc_pos_control/'
ALLOWED = {MODULE+name for name in ('PositionControl/PositionControl.cpp',
    'MulticopterPositionControl.cpp', 'mc_pos_control_params.c',
    'PositionControl/RegularizedIstaPositionTest.cpp', 'RegularizedIstaVelocityModuleTest.cpp', 'PositionControl/RegularizedIstaVelocityParamTest.cpp',
    'PositionControl/CMakeLists.txt')}
REBOUND = set()  # Entry contains the identical accepted RI04 revision01 production.
IMMUTABLE = (
    'research/sta-rate-control', 'research/sta-velocity-control/regularized_sta',
    'research/sta-velocity-control/axis_ablation', 'research/sta-velocity-control/v08',
    'research/sta-velocity-control/scripts', 'sim_scripts',
    'research/sta-velocity-control/regularized_ista/ri00',
    'research/sta-velocity-control/regularized_ista/ri01',
    'research/sta-velocity-control/regularized_ista/ri02',
    'research/sta-velocity-control/reports/RI00.md',
    'research/sta-velocity-control/reports/RI01.md',
    'research/sta-velocity-control/reports/RI02.md',
    'research/sta-velocity-control/reports/RI03.md',
    'research/sta-velocity-control/reports/RI04.md',
    'research/sta-velocity-control/reports/RI04_HTE_FIX.md',
    'research/sta-velocity-control/reports/RI04_REVISION01.md',
    'research/sta-velocity-control/reports/RI04_Z_BANDWIDTH.md',
    'research/sta-velocity-control/reports/PROPER_ISTA_PROBE.md',
    'research/sta-velocity-control/proper_ista_probe',
    'research/sta-velocity-control/regularized_ista/ri04_z_bandwidth',
    'research/sta-velocity-control/regularized_ista/ri03',
    'research/sta-velocity-control/regularized_ista/ri04', PRIOR_ROOT, REPAIR_ROOT,
    'research/sta-velocity-control/regularized_ista/plan/v1',
    'research/sta-velocity-control/regularized_ista/plan/ri00_entry',
    'research/sta-velocity-control/regularized_ista/plan/ri01_entry',
    'research/sta-velocity-control/regularized_ista/plan/ri02_entry',
    'research/sta-velocity-control/regularized_ista/plan/ri03_entry',
    'research/sta-velocity-control/regularized_ista/plan/ri04_entry')
PARAMETERS = MODULE+'mc_pos_control_params.c'
WORLD = 'sitl/worlds/empty_grey.world'
WORLD_SHA = '09d9a334728b35a5ca0392e8751e3df5b8aea8b1d5019f8e850a4b0b8bc57b96'
MODEL = 'research/sta-velocity-control/axis_ablation/ax02/models/iris.sdf'
MODEL_SHA = 'fe9900329b47f3afb3f2aafac164af047a6feb0e676ea74e658ada5e887b5150'
GENERATED_ASSETS = {
    'Tools/sitl_gazebo/models/iris/iris.sdf':
        '366bf1264ce86c0c65b837a5323410c7cd695b0ffa23cdd29e6c52f6315dc00e'}
GENERATED_SOURCES = ('Tools/sitl_gazebo/models/iris/iris.sdf.jinja',
    'Tools/sitl_gazebo/models/iris/model.config', 'Tools/sitl_gazebo/scripts/jinja_gen.py',
    'Tools/sitl_gazebo/.gitignore')
EXCLUDED_PARTS = {'__pycache__', 'results', 'gates', '.git'}
SOURCE_RESULTS = ('interface.json', 'cadence.json', 'source_fingerprints.json')


def sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def git_bytes(*args, directory=REPO, input_bytes=None):
    return subprocess.run(['git', *args], cwd=directory, input=input_bytes,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout


def safe_name(name):
    if not isinstance(name, str):
        raise ValueError('Asset path must be text')
    value = PurePosixPath(name)
    if (not name or value.is_absolute()
            or '..' in value.parts or '\\' in name or str(value) != name):
        raise ValueError('Unsafe/noncanonical asset path '+repr(name))
    return name


def base():
    if p.ENTRY_HEAD != ENTRY_HEAD:
        raise ValueError('Wrong RI05 entry identity')
    if p.fingerprint(BASE) != BASE_SHA:
        raise ValueError('Accepted RI04 revision01 frozen manifest changed')
    committed = git_bytes('show', p.ENTRY_HEAD+':'+str(BASE.relative_to(REPO)))
    if sha_bytes(committed) != BASE_SHA:
        raise ValueError('Wrong inherited manifest at HTE repair entry')
    old = json.loads(committed)
    if len(old['assets']) != BASE_COUNT or len(old['external_assets']) != 79 or len(old['submodules']) != 33:
        raise ValueError('Inherited asset/submodule inventory changed')
    if old['derived_iris_sha256'] != MODEL_SHA or old['assets'].get(WORLD) != WORLD_SHA:
        raise ValueError('Original model/world identity changed')
    return old


def submodule_map(lines):
    result = {}
    for line in lines:
        match = re.fullmatch(r' ([0-9a-f]{40}) ([^\s]+)(?: \(.*\))?', line)
        if match is None or match[2] in result:
            raise ValueError('Uninitialized/dirty/duplicate submodule identity')
        result[safe_name(match[2])] = match[1]
    if len(result) != 33:
        raise ValueError('Expected exactly 33 recursive submodules')
    return result


def submodules():
    lines = git_bytes('submodule', 'status', '--recursive').decode().splitlines()
    actual = submodule_map(lines)
    if actual != submodule_map(base()['submodules']):
        raise ValueError('Inherited submodule revisions changed')
    if git_bytes('submodule', 'foreach', '--recursive', '--quiet',
                 'git status --porcelain --untracked-files=all').strip():
        raise ValueError('Dirty recursive submodule')
    return [' '+oid+' '+name for name, oid in sorted(actual.items())]


def owner(name, modules):
    safe_name(name)
    roots = [root for root in modules if name.startswith(root+'/')]
    root = max(roots, key=len) if roots else ''
    return root, name[len(root)+1:] if root else name


def tree_entries(raw):
    entries = {}
    for line in raw.split(b'\0'):
        if not line:
            continue
        metadata, name = line.split(b'\t', 1)
        mode, kind, oid = metadata.decode().split()
        name = safe_name(name.decode())
        if name in entries:
            raise ValueError('Duplicate Git tree path')
        entries[name] = (mode, kind, oid)
    return entries


def verify_gitlinks(source_head, modules):
    """Resolve each nested pin through its parent's committed gitlink."""
    for name, expected in sorted(modules.items(), key=lambda item: (item[0].count('/'), item[0])):
        parent_modules = {root: oid for root, oid in modules.items() if root != name}
        parent, relative = owner(name, parent_modules)
        revision = modules[parent] if parent else source_head
        found = tree_entries(git_bytes('ls-tree', '-z', revision, '--', relative,
                                      directory=REPO/parent))
        if found.get(relative) != ('160000', 'commit', expected):
            raise ValueError('Source submodule gitlink differs '+name)


def batch_hashes(directory, oids):
    """Hash exact blob payloads, never the current working-tree substitute."""
    unique = sorted(set(oids))
    if not unique:
        return {}
    raw = git_bytes('cat-file', '--batch', directory=directory,
                    input_bytes=('\n'.join(unique)+'\n').encode())
    offset, result = 0, {}
    for wanted in unique:
        boundary = raw.find(b'\n', offset)
        if boundary < 0:
            raise ValueError('Truncated Git batch header')
        header = raw[offset:boundary].decode().split()
        if len(header) != 3 or header[0] != wanted or header[1] != 'blob' or not header[2].isdigit():
            raise ValueError('Missing/non-blob Git object '+wanted)
        start, size = boundary+1, int(header[2])
        end = start+size
        if end >= len(raw) or raw[end:end+1] != b'\n':
            raise ValueError('Truncated Git blob payload')
        result[wanted] = sha_bytes(raw[start:end])
        offset = end+1
    if offset != len(raw):
        raise ValueError('Unexpected trailing Git batch payload')
    return result


def committed_assets(names, source_head, modules):
    groups = defaultdict(list)
    for name in names:
        root, relative = owner(name, modules)
        groups[root].append((name, relative))
    result = {}
    for root, members in groups.items():
        revision = modules[root] if root else source_head
        entries = tree_entries(git_bytes('ls-tree', '-rz', revision, '--',
            *[relative for _, relative in members], directory=REPO/root))
        objects = {}
        for name, relative in members:
            entry = entries.get(relative)
            if name in GENERATED_ASSETS:
                # This sole pre-existing ignored SDF is not a Git blob. Its
                # original exact bytes and committed generator/template remain
                # pinned; no directory-wide or arbitrary submodule exemption.
                expected = GENERATED_ASSETS[name]
                if entry is not None or p.fingerprint(REPO/name) != expected:
                    raise ValueError('Original generated Iris identity changed')
                result[name] = expected
                continue
            if entry is None or entry[1] != 'blob' or entry[0] not in ('100644', '100755'):
                raise ValueError('Asset not a committed regular file '+name)
            objects[name] = entry[2]
        hashes = batch_hashes(REPO/root, objects.values())
        result.update({name: hashes[oid] for name, oid in objects.items()})
    return result


def parameter_definitions(raw):
    text = raw.decode()
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    entries = re.findall(r'\bPARAM_DEFINE_[A-Z0-9_]+\s*\([^;]*?\)\s*;', text)
    if not entries:
        raise ValueError('Missing real PARAM_DEFINE definitions')
    return [re.sub(r'\s+', '', item) for item in entries]


def scope(source_head=None):
    """Only declared admission/comments/tests; defaults/math/model stay pinned."""
    revisions = [p.ENTRY_HEAD] if source_head is None else [p.ENTRY_HEAD, source_head]
    names = set(git_bytes('diff', '--name-only', *revisions, '--', *PRODUCTION).decode().splitlines())
    if source_head is None:
        names.update(git_bytes('ls-files', '--others', '--exclude-standard', '--',
                               *PRODUCTION).decode().splitlines())
    if names-ALLOWED:
        raise ValueError('RI05 production scope exceeded '+repr(sorted(names-ALLOWED)))
    changed_old = git_bytes('diff', '--name-only', *revisions, '--', *IMMUTABLE).decode().splitlines()
    if source_head is None:
        changed_old += git_bytes('ls-files', '--others', '--exclude-standard', '--',
                                 *IMMUTABLE).decode().splitlines()
    if changed_old:
        raise ValueError('Historical research changed '+repr(changed_old))
    entry_raw = git_bytes('show', p.ENTRY_HEAD+':'+PARAMETERS)
    current_raw = ((REPO/PARAMETERS).read_bytes() if source_head is None
                   else git_bytes('show', source_head+':'+PARAMETERS))
    definitions = parameter_definitions(entry_raw)
    if parameter_definitions(current_raw) != definitions:
        raise ValueError('PARAM_DEFINE defaults changed')
    return dict(entry_head=p.ENTRY_HEAD, production_changes=sorted(names),
                allowed_production_changes=sorted(ALLOWED), immutable_research_unchanged=True,
                parameter_default_count=len(definitions),
                parameter_defaults_sha256=sha_bytes('\n'.join(definitions).encode()))


def roots():
    return [REPO/MODULE, HERE, HERE.parent/'ri00', HERE.parent/'ri01',
            HERE.parent/'ri02', HERE.parent/'ri03', HERE.parent/'ri04',
            HERE.parent/'ri04_hte_fix', HERE.parent/'ri04_revision01', HERE.parent/'plan']


def include_source(relative):
    return not EXCLUDED_PARTS.intersection(relative.parts) and relative.suffix not in ('.pyc', '.pyo')


def prior_archive_names():
    """All accepted RI04 revision01 and repair evidence stays immutable."""
    entries = tree_entries(git_bytes('ls-tree', '-rz', ENTRY_HEAD, '--', PRIOR_ROOT, REPAIR_ROOT))
    names = set()
    for name, (mode, kind, _) in entries.items():
        path = PurePosixPath(name)
        if '__pycache__' in path.parts or path.suffix in ('.pyc', '.pyo'):
            continue
        if kind != 'blob' or mode not in ('100644', '100755'):
            raise ValueError('Prior RI04/repair archive contains nonregular asset '+name)
        names.add(name)
    if not {PRIOR_ROOT+'/results/summary.json', PRIOR_ROOT+'/results/ulog_index.json',
            PRIOR_ROOT+'/gates/B/frozen.json', REPAIR_ROOT+'/verification_summary.json',
            REPAIR_ROOT+'/recorded_hte_fixture.hpp'}.issubset(names):
        raise ValueError('Incomplete committed RI04/repair archive at entry')
    return names


def required_names(old):
    names = set(old['assets'])
    names.update(prior_archive_names())
    names.update(GENERATED_SOURCES)
    # These small prior results are consumed inputs, not new result archives.
    for name in SOURCE_RESULTS:
        names.add(str((HERE.parent/'ri00/results'/name).relative_to(REPO)))
    for name in ('RI00.md', 'RI01.md', 'RI02.md', 'RI03.md', 'RI04.md', 'RI04_HTE_FIX.md', 'RI04_REVISION01.md'):
        names.add('research/sta-velocity-control/reports/'+name)
    names.update((str(BASE.relative_to(REPO)), '.gitmodules', 'Makefile', 'CMakeLists.txt'))
    return names


def asset_names(old):
    names = required_names(old)
    for root in roots():
        for path in root.rglob('*'):
            relative = path.relative_to(root)
            if path.is_file() and include_source(relative):
                if path.is_symlink():
                    raise ValueError('Source asset must not be a symlink '+str(path))
                names.add(str(path.relative_to(REPO)))
    return sorted(safe_name(name) for name in names)


def committed_asset_names(old, source_head):
    names = required_names(old)
    prefixes = [PurePosixPath(str(root.relative_to(REPO))) for root in roots()]
    entries = tree_entries(git_bytes('ls-tree', '-rz', source_head, '--', *map(str, prefixes)))
    for name, (mode, kind, _) in entries.items():
        path = PurePosixPath(name)
        prefix = next((item for item in prefixes if item in path.parents), None)
        if prefix is None:
            raise ValueError('Unexpected source-root inventory entry '+name)
        if include_source(path.relative_to(prefix)):
            if kind != 'blob' or mode not in ('100644', '100755'):
                raise ValueError('Source inventory contains a nonregular file '+name)
            names.add(name)
    if not ALLOWED.issubset(names):
        raise ValueError('Missing new RI05 admission/test source inventory')
    return sorted(safe_name(name) for name in names)


def external_check(old):
    for name, expected in old['external_assets'].items():
        if p.fingerprint(name) != expected:
            raise ValueError('Immutable external dependency changed '+name)


def capture(gate='C'):
    p.valid_gate(gate)
    p.require_execution_authority(gate)
    p.require_prior_gate(gate)
    old, audit, subs = base(), scope(), submodules()
    modules = submodule_map(subs)
    verify_gitlinks(p.ENTRY_HEAD, modules)
    entry = committed_assets(old['assets'], p.ENTRY_HEAD, modules)
    assets = {name: p.fingerprint(REPO/name) for name in asset_names(old)}
    for name, expected in entry.items():
        if name not in ALLOWED and assets[name] != expected:
            raise ValueError('Inherited entry asset changed outside RI05 scope '+name)
    external_check(old)
    if assets[WORLD] != WORLD_SHA or assets[MODEL] != MODEL_SHA:
        raise ValueError('Qualified world/model changed')
    rebased = {name: dict(ri04_sha256=old['assets'][name], entry_sha256=value)
               for name, value in entry.items() if old['assets'][name] != value}
    if set(rebased) != REBOUND:
        raise ValueError('Inherited accepted RI04 revision01 source differs at entry')
    return dict(stage=p.stage(gate), revision=p.REVISION, gate=gate, entry_head=p.ENTRY_HEAD,
        scope=audit, assets=assets, external_assets=old['external_assets'], submodules=subs,
        inherited_frozen_sha256=BASE_SHA, inherited_assets_count=BASE_COUNT,
        inherited_rebased_to_entry=rebased, control_parameters=old['control_parameters'],
        generated_assets=GENERATED_ASSETS,
        derived_iris_sha256=MODEL_SHA, execution_sha256=p.fingerprint(HERE/'execution.json'),
        authorization_sha256=p.AUTHORIZATION_SHA, budget=p.budget(gate),
        new_flights=0, post_logger_warmup_us=30000000,
        source_binding='Current revision clean qualification binds its own source and rebuilt firmware; old failed RI04 and offline HTE repair are not launch authority')


def check(gate='C'):
    p.valid_gate(gate)
    saved = p.read(HERE/'gates'/gate/'frozen.json')
    if not p.exact(saved, capture(gate)):
        raise ValueError('RI05 frozen source/asset/protocol changed')
    return saved


def archive_check(gate, source_head, frozen_sha):
    p.valid_gate(gate)
    if not re.fullmatch(r'[0-9a-f]{40}', source_head or ''):
        raise ValueError('Full archived source SHA required')
    git_bytes('merge-base', '--is-ancestor', p.ENTRY_HEAD, source_head)
    path = HERE/'gates'/gate/'frozen.json'
    if p.fingerprint(path) != frozen_sha:
        raise ValueError('Archived frozen manifest changed')
    committed = git_bytes('show', source_head+':'+str(path.relative_to(REPO)))
    if sha_bytes(committed) != frozen_sha:
        raise ValueError('Frozen manifest not committed at claimed source')
    saved, old = json.loads(committed), base()
    if (saved.get('stage') != p.stage(gate) or saved.get('revision') != p.REVISION
            or saved.get('gate') != gate or saved.get('entry_head') != p.ENTRY_HEAD
            or saved.get('inherited_frozen_sha256') != BASE_SHA
            or saved.get('generated_assets') != GENERATED_ASSETS
            or saved.get('external_assets') != old['external_assets']
            or saved.get('control_parameters') != old['control_parameters']
            or saved.get('derived_iris_sha256') != MODEL_SHA
            or not p.exact(saved.get('budget'), p.budget(gate))
            or saved.get('new_flights') != 0 or saved.get('post_logger_warmup_us') != 30000000):
        raise ValueError('Archived freeze identity/inherited contract changed')
    modules = submodule_map(saved['submodules'])
    if modules != submodule_map(old['submodules']):
        raise ValueError('Archived submodule pins changed')
    verify_gitlinks(source_head, modules)
    if saved.get('scope') != scope(source_head):
        raise ValueError('Archived source scope/defaults differ')
    if set(saved['assets']) != set(committed_asset_names(old, source_head)):
        raise ValueError('Archived full source inventory is incomplete or contains extra assets')
    actual = committed_assets(saved['assets'], source_head, modules)
    if actual != saved['assets']:
        raise ValueError('Asset blob does not match claimed source')
    # Ensure a caller cannot produce a smaller forged inventory omitting checks.
    entry_assets = committed_assets(old['assets'], p.ENTRY_HEAD, modules)
    if not set(old['assets']).issubset(saved['assets']):
        raise ValueError('Archived inherited inventory is incomplete')
    rebased = {name: dict(ri04_sha256=old['assets'][name], entry_sha256=value)
               for name, value in entry_assets.items() if old['assets'][name] != value}
    if set(rebased) != REBOUND:
        raise ValueError('Unexpected inherited rebase at RI05 entry')
    if saved.get('inherited_assets_count') != BASE_COUNT or saved.get('inherited_rebased_to_entry') != rebased:
        raise ValueError('Archived RI04 entry rebase evidence differs')
    for name, expected in entry_assets.items():
        if name not in ALLOWED and actual[name] != expected:
            raise ValueError('Archived inherited source changed '+name)
    for key, file in (('execution_sha256', HERE/'execution.json'),
                      ('authorization_sha256', p.AUTHORIZATION)):
        name = str(file.relative_to(REPO))
        if saved.get(key) != actual.get(name):
            raise ValueError('Archived protocol/authority file binding differs')
    if actual.get(WORLD) != WORLD_SHA or actual.get(MODEL) != MODEL_SHA:
        raise ValueError('Archived model/world differs')
    external_check(old)
    return saved


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gate', choices=p.GATES, default='C')
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--check', action='store_true')
    action.add_argument('--write', action='store_true', help='Exclusively create the new frozen manifest')
    args = parser.parse_args()
    record = check(args.gate) if args.check else capture(args.gate)
    if args.write:
        destination = HERE/'gates'/args.gate/'frozen.json'
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('x') as stream:
            json.dump(record, stream, indent=2); stream.write('\n')
    print(json.dumps(dict(gate=args.gate, assets=len(record['assets']),
        external_assets=len(record['external_assets']), new_flights=0,
        manifest_written=args.write)))
