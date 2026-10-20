"""Pin the minimal upstream fix plus a separately bounded diagnostic package."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('_up08_freeze_protocol',HERE/'protocol.py')
p=importlib.util.module_from_spec(s);s.loader.exec_module(p)
REPO=p.REPO
ENTRY='09c96f3cd0481f8b6672aa047cd7d49ffd21fc03'
PRODUCTION=('src','msg','Tools','platforms','sitl','ROMFS','boards','cmake','CMakeLists.txt','Makefile','.gitmodules')
ALLOWED={
    'src/modules/sensors/vehicle_imu/'+name for name in
    ('VehicleIMU.cpp','VehicleIMU.hpp','VehicleIMUTest.cpp','CMakeLists.txt')}
ALLOWED|={'src/modules/logger/'+name for name in
    ('logged_topics.cpp','logged_topics.h','params.c','EstimatorDiagnosticTopicsTest.cpp')}
ALLOWED|={'src/modules/ekf2/'+name for name in
    ('EKF2SelectorTimingTest.cpp','EKF2Selector.hpp','CMakeLists.txt')}


def scope():
    names=set(p.git('diff','--name-only',ENTRY,'--',*PRODUCTION).splitlines())
    names.update(p.git('ls-files','--others','--exclude-standard','--',*PRODUCTION).splitlines())
    if names-ALLOWED:raise ValueError('Upstream repair scope exceeded '+str(names-ALLOWED))
    old=p.read(HERE.parent/'r03_revision06/gates/D/frozen.json')
    for name,sha in old['assets'].items():
        if name not in ALLOWED and p.fingerprint(REPO/name)!=sha:
            raise ValueError('Immutable inherited asset changed '+name)
    return sorted(names)


def submodules():
    subs=subprocess.check_output(['git','submodule','status','--recursive'],cwd=REPO,text=True).splitlines()
    if len(subs)!=33 or any(not x.startswith(' ') for x in subs):raise ValueError('Submodule version/count mismatch')
    if p.git('submodule','foreach','--recursive','--quiet','git status --porcelain --untracked-files=all'):
        raise ValueError('Dirty submodule')
    return subs


def capture():
    p.require_execution_authority();old=p.read(HERE.parent/'r03_revision06/gates/D/frozen.json')
    changed=scope();assets={name:p.fingerprint(REPO/name) for name in old['assets']}
    for path in (REPO/name for name in sorted(ALLOWED)):
        assets[str(path.relative_to(REPO))]=p.fingerprint(path)
    for path in HERE.rglob('*'):
        if path.is_file() and path.name!='frozen.json' and '__pycache__' not in path.parts:
            assets[str(path.relative_to(REPO))]=p.fingerprint(path)
    for path in (HERE.parent/'plan/r03_upstream08_entry').glob('*.md'):
        assets[str(path.relative_to(REPO))]=p.fingerprint(path)
    assets[str(p.AUTHORIZATION.relative_to(REPO))]=p.fingerprint(p.AUTHORIZATION)
    for name,sha in old['external_assets'].items():
        if p.fingerprint(name)!=sha:raise ValueError('External dependency changed '+name)
    return dict(stage=p.STAGE,revision=p.REVISION,entry_head=ENTRY,production_changes=changed,
        assets=assets,external_assets=old['external_assets'],submodules=submodules(),
        control_parameters=old['control_parameters'],derived_iris_sha256=old['derived_iris_sha256'],
        execution_sha256=p.fingerprint(HERE/'execution.json'),authorization_sha256=p.AUTHORIZATION_SHA,
        budget=p.budget(),historical_budget=p.retained_history(),retained_abc=p.retained_abc(),
        new_flights=0,source_binding='Clean qualification binds new HEAD and rebuilt binary; old source qualification is not reused',
        applicability='Old ABC retain their historical source. Upstream timing change requires separately frozen engineering bridge or complete revalidation before final R03 acceptance')


def check():
    saved=p.read(HERE/'frozen.json');actual=capture()
    if not p.exact(saved,actual):raise ValueError('Frozen diagnostic source/assets/protocol changed')
    return saved


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    result=check() if args.check else capture()
    if not args.check:
        with (HERE/'frozen.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(dict(assets=len(result['assets']),production_changes=result['production_changes'],new_flights=0)))
