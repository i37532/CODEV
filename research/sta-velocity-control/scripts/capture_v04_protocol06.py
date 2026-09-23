"""New immutable asset/seed snapshot. No simulator or parameter mutation."""
import hashlib
import json
import subprocess
from check_v04_protocol02 import seed_audit
from v04_protocol06 import REPO, CONFIG


def fresh_seeds():
    result = seed_audit([9501, 9502, 9503])
    allowed = {str(CONFIG/'execution.json'), str(CONFIG/'seed_audit.json')}
    result['design_registrations'] = [m for m in result['matches'] if m['path'] in allowed]
    result['matches'] = [m for m in result['matches'] if m['path'] not in allowed]
    result['accepted'] = not result['matches'] and not result['invalid_json']
    return result


def capture():
    prior = json.loads((CONFIG.parent/'protocol04/frozen.json').read_text())
    names = set(prior['assets'])
    names.add('research/sta-velocity-control/v04/handoff06/protocol.json')
    names.add('research/sta-velocity-control/v04/handoff06/ProjectionWireProbe.cpp')
    names.update(str(p.relative_to(REPO)) for p in (REPO/'research/sta-velocity-control/scripts').glob('*.py'))
    names.update(str((CONFIG/p).relative_to(REPO)) for p in ('execution.json', 'pid/frozen.json', 'esta/frozen.json'))
    return dict(kind='protocol06 exact assets; clean execution SHA/firmware recorded at launch',
                parent_head=subprocess.check_output(['git','rev-parse','HEAD'], cwd=REPO, text=True).strip(),
                assets={n:hashlib.sha256((REPO/n).read_bytes()).hexdigest() for n in sorted(names)},
                control_parameters=prior['control_parameters'],
                submodules=subprocess.check_output(['git','submodule','status','--recursive'], cwd=REPO, text=True).splitlines())


if __name__ == '__main__':
    print(json.dumps(dict(frozen=capture(), seed_audit=fresh_seeds()), indent=2))
