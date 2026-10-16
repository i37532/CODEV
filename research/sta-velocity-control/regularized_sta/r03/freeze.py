"""R03 per-gate immutable asset snapshots. New source, not AX04 qualification."""
import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys

from protocol import HERE, REPO, BASE, GATES, fingerprint, git, read, load_protocol
import historical_probe

PRODUCTION = ['src','msg','Tools','platforms','sitl','ROMFS','boards','cmake','CMakeLists.txt','Makefile','.gitmodules']
PREFIX='src/modules/mc_pos_control/'
ALLOWED={PREFIX+n for n in ('PositionControl/PositionControl.cpp','PositionControl/PositionControl.hpp',
    'MulticopterPositionControl.cpp','mc_pos_control_params.c',
    'PositionControl/RegularizedVelocityIntegrationTest.cpp',
    'PositionControl/RegularizedVelocityParamTest.cpp','RegularizedVelocityModuleTest.cpp')}


def check_scope():
    changed=set(git('diff','--name-only',BASE,'--',*PRODUCTION).splitlines())
    untracked=set(git('ls-files','--others','--exclude-standard','--',*PRODUCTION).splitlines())
    if (changed|untracked)-ALLOWED:
        raise ValueError('Unexpected R03 production change: '+str((changed|untracked)-ALLOWED))
    return sorted(changed|untracked)


def capture(gate):
    p=load_protocol(gate)
    changed=check_scope()
    historical=read(REPO/'research/sta-velocity-control/axis_ablation/ax04/frozen.json')
    assets={name:fingerprint(REPO/name) for name in historical['assets']}
    # Current hashes are intentional for admitted production changes; immutable
    # historical research/launch/model artifacts must remain byte-for-byte.
    for name,sha in historical['assets'].items():
        if not name.startswith(('src/modules/mc_pos_control/','msg/velocity_ctrl_selection.msg')) and assets[name]!=sha:
            raise ValueError('Unapproved inherited asset drift '+name)
    for folder in (REPO/PREFIX, HERE.parent/'r01', HERE.parent/'r02', HERE):
        for path in folder.rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and 'gates' not in path.relative_to(folder).parts:
                if path.suffix in ('.cpp','.hpp','.c','.h','.txt','.py','.md','.json','.msg'):
                    assets[str(path.relative_to(REPO))]=fingerprint(path)
    assets[str((HERE.parent/'AUTHORIZATION_CN.md').relative_to(REPO))]=fingerprint(HERE.parent/'AUTHORIZATION_CN.md')
    probes = historical_probe.check()
    external_assets = {**historical['external_assets'], **probes['fingerprints']}
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
    return dict(stage='R03-'+gate,gate=gate,baseline_head=BASE,production_changes=changed,
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
        budget=dict(total=36,this_gate=9,replacement=0),new_flights=0,
        random_scope='IMU only, first5000 innovations paired; other source independence not claimed')


def check(gate):
    path=HERE/'gates'/gate/'frozen.json'
    frozen=read(path)
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
