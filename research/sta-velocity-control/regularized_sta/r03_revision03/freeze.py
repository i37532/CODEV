"""R03 per-gate immutable asset snapshots. New source, not AX04 qualification."""
import argparse
import importlib.util
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import pyulog.core

_path = Path(__file__).resolve().parent/'protocol.py'
_spec = importlib.util.spec_from_file_location('_r03_revision03_freeze_protocol', _path)
_protocol = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_protocol)
for _name in ('HERE','REPO','BASE','GATES','AUTHORIZATION','REVISION',
              'TOTAL_MAXIMUM_ATTEMPTS','HISTORICAL_ATTEMPTS','NEW_MATRIX_ATTEMPTS',
              'fingerprint','git','read','load_protocol','load_file','retained_failure','seed_migration'):
    globals()[_name] = getattr(_protocol, _name)
historical_probe = load_file('_r03_revision03_historical_probe', HERE.parent/'r03/historical_probe.py')

PRODUCTION = ['src','msg','Tools','platforms','sitl','ROMFS','boards','cmake','CMakeLists.txt','Makefile','.gitmodules']
PREFIX='src/modules/mc_pos_control/'
ALLOWED={PREFIX+n for n in ('PositionControl/PositionControl.cpp','PositionControl/PositionControl.hpp',
    'MulticopterPositionControl.cpp','mc_pos_control_params.c',
    'PositionControl/RegularizedVelocityIntegrationTest.cpp',
    'PositionControl/RegularizedVelocityParamTest.cpp','RegularizedVelocityModuleTest.cpp')}
ENTRY='73c2ef5b5544a27cc8dfcaf6dfe7b2d7ceb0950d'
ADMISSION_SOURCE=PREFIX+'PositionControl/PositionControl.cpp'
METADATA=PREFIX+'mc_pos_control_params.c'
ENTRY_ALLOWED={ADMISSION_SOURCE,METADATA,*(PREFIX+n for n in (
    'PositionControl/RegularizedVelocityIntegrationTest.cpp',
    'PositionControl/RegularizedVelocityParamTest.cpp','RegularizedVelocityModuleTest.cpp'))}


def admitted_gate(source):
    matches=re.findall(r'const bool regularized_gate_admitted = ([^;]+);',source)
    if len(matches)!=1:
        raise ValueError('Exactly one production admission predicate required')
    expression=re.sub(r'\s','',matches[0])
    prefixes=['||'.join('axes=='+str(GATES[g]['axes']) for g in list(GATES)[:i+1])
              for i in range(len(GATES))]
    if expression not in prefixes:
        raise ValueError('Production admission is not an exact ordered gate prefix')
    return list(GATES)[prefixes.index(expression)]


def code_tokens(source):
    # Preserve quoted strings/characters. Only comments and token-separating
    # whitespace may differ; production expressions/defaults remain exact.
    token=r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*[\s\S]*?\*/|\w+|[^\s]'
    return [value for value in re.findall(token,source)
            if not value.startswith(('//','/*'))]


def check_admission_only(before,after):
    admitted_gate(before);admitted_gate(after)
    pattern=r'const bool regularized_gate_admitted = [^;]+;'
    if code_tokens(re.sub(pattern,'GATE_PREDICATE;',before)) != code_tokens(re.sub(pattern,'GATE_PREDICATE;',after)):
        raise ValueError('Production change exceeds the admission predicate/comments')


def check_scope():
    immutable = ['research/sta-velocity-control/regularized_sta/'+name for name in
                 ('r01','r02','r03','r03_revision01','r03_revision02','r03_monitor02')]
    if git('diff','--name-only',ENTRY,'--',*immutable) or \
            git('ls-files','--others','--exclude-standard','--',*immutable):
        raise ValueError('Immutable prior R01/R02/R03/revision01/revision02/monitor02 changed after revision entry')
    latest=set(git('diff','--name-only',ENTRY,'--',*PRODUCTION).splitlines())
    if latest-ENTRY_ALLOWED or git('ls-files','--others','--exclude-standard','--',*PRODUCTION):
        raise ValueError('Unexpected revision03 production change/new file')
    actual=(REPO/ADMISSION_SOURCE).read_text()
    gate=admitted_gate(actual)
    if gate=='A' and latest:
        raise ValueError('Gate A must retain exact entry production source')
    if ADMISSION_SOURCE in latest:
        check_admission_only(git('show',ENTRY+':'+ADMISSION_SOURCE),actual)
    if METADATA in latest and code_tokens(git('show',ENTRY+':'+METADATA)) != code_tokens((REPO/METADATA).read_text()):
        raise ValueError('Metadata change exceeds comments; parameter code/defaults must remain exact')
    changed=set(git('diff','--name-only',BASE,'--',*PRODUCTION).splitlines())
    untracked=set(git('ls-files','--others','--exclude-standard','--',*PRODUCTION).splitlines())
    if (changed|untracked)-ALLOWED:
        raise ValueError('Unexpected R03 production change: '+str((changed|untracked)-ALLOWED))
    return sorted(changed|untracked)


def capture(gate):
    p=load_protocol(gate)
    _protocol.require_execution_authority(gate)
    _protocol.require_previous_gates(gate)
    changed=check_scope()
    if admitted_gate((REPO/ADMISSION_SOURCE).read_text())!=gate:
        raise ValueError('Frozen gate does not match actual production admission')
    historical=read(REPO/'research/sta-velocity-control/axis_ablation/ax04/frozen.json')
    assets={name:fingerprint(REPO/name) for name in historical['assets']}
    # Current hashes are intentional for admitted production changes; immutable
    # historical research/launch/model artifacts must remain byte-for-byte.
    for name,sha in historical['assets'].items():
        if not name.startswith(('src/modules/mc_pos_control/','msg/velocity_ctrl_selection.msg')) and assets[name]!=sha:
            raise ValueError('Unapproved inherited asset drift '+name)
    for folder in (REPO/PREFIX, HERE.parent/'r01', HERE.parent/'r02', HERE.parent/'r03', HERE.parent/'r03_revision01', HERE.parent/'r03_revision02', HERE.parent/'r03_monitor02', HERE):
        for path in folder.rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and not (folder==HERE and 'gates' in path.relative_to(folder).parts):
                if path.suffix in ('.cpp','.hpp','.c','.h','.txt','.py','.md','.json','.msg'):
                    assets[str(path.relative_to(REPO))]=fingerprint(path)
    assets[str((HERE.parent/'AUTHORIZATION_CN.md').relative_to(REPO))]=fingerprint(HERE.parent/'AUTHORIZATION_CN.md')
    assets[str(AUTHORIZATION.relative_to(REPO))]=fingerprint(AUTHORIZATION)
    probes = historical_probe.check()
    external_assets = {**historical['external_assets'], **probes['fingerprints']}
    decoder_path = Path(pyulog.core.__file__).resolve()
    decoder_sha = fingerprint(decoder_path)
    if decoder_sha != '130187f7676dd53582f984085a8659f6a2c0545fb627c7a683e7609807a6f2ef':
        raise ValueError('Incremental-reader pyulog dependency changed')
    external_assets[str(decoder_path)] = decoder_sha
    for name,sha in external_assets.items():
        if fingerprint(name)!=sha:
            raise ValueError('Changed external dependency '+name)
    subs=git('submodule','status','--recursive').splitlines()
    # git() strips the leading space from the first line; use raw output here.
    subs=subprocess.check_output(['git','submodule','status','--recursive'],cwd=REPO,text=True).splitlines()
    if len(subs)!=33 or any(not line.startswith(' ') for line in subs):
        raise ValueError('Submodule mismatch')
    if git('submodule','foreach','--recursive','--quiet','git status --porcelain --untracked-files=all'):
        raise ValueError('Dirty submodule')
    return dict(stage=p['stage'],revision=REVISION,gate=gate,baseline_head=BASE,production_changes=changed,
        assets=assets,external_assets=external_assets,
        historical_target_probe={key:value for key,value in probes.items() if key != 'fingerprints'},
        control_parameters=historical['control_parameters'],
        derived_iris_sha256=historical['derived_iris_sha256'],submodules=subs,
        source_binding='Post-commit clean rebuild qualification binds exact HEAD/binary, separate from this precommit asset snapshot',
        parameters_source='AX04 parameter values only; no inherited flight/source qualification',
        execution_sha256=fingerprint(HERE/'execution.json'),
        environment=dict(python=sys.version,platform=platform.platform(),
            compiler=subprocess.check_output(['g++','--version'],text=True).splitlines()[0],
            cmake=subprocess.check_output(['cmake','--version'],text=True).splitlines()[0]),
        budget=dict(total=TOTAL_MAXIMUM_ATTEMPTS,this_gate=9,new_matrix=NEW_MATRIX_ATTEMPTS,retained_attempts=8,retained_accepted=6,retained_invalid=2,replacement_after_this_revision=0),historical_budget=retained_failure(),new_flights=0,
        seed_migration=seed_migration(),execution_authorized=True,flight_authorized=True,execution_ready=True,
        random_scope='IMU only, first5000 innovations paired; other source independence not claimed')


def check(gate):
    path=HERE/'gates'/gate/'frozen.json'
    frozen=read(path)
    _protocol.require_execution_authority(gate)
    _protocol.require_previous_gates(gate)
    if admitted_gate((REPO/ADMISSION_SOURCE).read_text())!=gate:
        raise ValueError('Qualified gate does not match actual production admission')
    if not _protocol.exact(frozen.get('seed_migration'),seed_migration()):
        raise ValueError('Frozen migration changed')
    for name,sha in frozen['assets'].items():
        if fingerprint(REPO/name)!=sha:
            raise ValueError('Frozen asset changed '+name)
    for name,sha in frozen['external_assets'].items():
        if fingerprint(name)!=sha:
            raise ValueError('Frozen external dependency changed '+name)
    if check_scope()!=frozen['production_changes']:
        raise ValueError('Unexpected post-freeze production scope')
    if frozen['execution_sha256']!=fingerprint(HERE/'execution.json'):
        raise ValueError('Execution changed')
    return frozen


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gate',choices=GATES,required=True)
    p.add_argument('--check',action='store_true')
    args=p.parse_args()
    if args.check:
        result=check(args.gate)
    else:
        result=capture(args.gate)
        path=HERE/'gates'/args.gate/'frozen.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x') as stream:
            json.dump(result,stream,indent=2); stream.write('\n')
    print(json.dumps(dict(gate=args.gate,assets=len(result['assets']),new_flights=0)))


if __name__=='__main__':
    main()
