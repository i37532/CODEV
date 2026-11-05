#!/usr/bin/env python3
"""Print AX02 asset snapshot (caller reviews/applies; this never writes/flies)."""
import json
import subprocess
import sys
from pathlib import Path
import common
import run  # resolves the actual independent runner and its shared dependencies

def capture():
    repo=common.REPO; paths=set()
    old=json.loads((common.LEGACY/'frozen.json').read_text())
    # Keep old dependency inventory but hash CURRENT files, never pretend the
    # old frozen hashes describe new source. Includes model/launcher/logger.
    paths.update(repo/k for k in old['assets'] if k.startswith(('src/','msg/','Tools/','platforms/','sitl/','sim_scripts/')))
    paths.update((repo/'research/sta-velocity-control/scripts').glob('*.py'))
    paths.update(common.LEGACY.glob('*.py'))
    paths.update((repo/'research/sta-velocity-control/v04').glob('protocol*/*.json'))
    paths.update((repo/'research/sta-velocity-control/v04').glob('handoff06/*.json'))
    paths.update((repo/'research/sta-velocity-control/v04').glob('landing10/*.json'))
    paths.update((repo/'research/sta-velocity-control/v06/soft_landing').glob('*.json'))
    paths.add(repo/'research/sta-velocity-control/v06/soft_landing/offline03/evidence.json')
    for module in list(sys.modules.values()):
        filename=getattr(module,'__file__',None)
        if filename:
            p=Path(filename).resolve()
            if p.is_file() and repo in p.parents and '.px4-python' not in p.parts: paths.add(p)
    paths.update(common.CONFIG.glob('*.py'))
    paths.update(common.CONFIG.glob('parameters/*.json'))
    paths.update(common.CONFIG.glob('plan_entry/*'))
    paths.update(common.CONFIG.glob('models/*'))
    paths.update(common.CONFIG/name for name in ('execution.json','seed_reservations.json','seed_audit_initial.json','pid/frozen.json','esta/frozen.json'))
    paths.add(common.CONFIG.parent/'run.sh')
    paths.update((repo/'src/modules/mc_pos_control').rglob('*.hpp'))
    paths.update((repo/'src/modules/mc_pos_control').rglob('*.cpp'))
    paths.add(repo/'src/modules/mc_pos_control/mc_pos_control_params.c')
    paths.add(repo/'src/modules/mc_pos_control/PositionControl/CMakeLists.txt')
    plugins=Path(common.load_protocol()['plugins'])
    external=json.loads((plugins/'manifest.json').read_text())
    for name,expected in external.items():
        if common.fingerprint(name)!=expected: raise RuntimeError('Changed plugin dependency '+name)
    external[str(plugins/'manifest.json')]=common.fingerprint(plugins/'manifest.json')
    return dict(baseline_head='7e352a07a41df65fc56ca25b8a03b30c944bfb53',
        source_binding='AX03 receipt must match current clean HEAD; assets below must match; no old V08 authority',
        assets={str(p.relative_to(repo)):common.fingerprint(p) for p in sorted(paths)},
        external_assets=external, control_parameters=old['control_parameters'],
        derived_iris_sha256=common.fingerprint(common.CONFIG/'models/iris.sdf'),
        submodules=subprocess.check_output(['git','submodule','status','--recursive'],cwd=repo,text=True).splitlines(),
        random_scope='Only IMU engine seeded; first5000 innovation pairing, all other source independence not claimed',
        new_flights=0)

if __name__=='__main__': print(json.dumps(capture(),indent=2,ensure_ascii=False))
