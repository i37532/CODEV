"""Read-only exact source/model/plugin/parameter and proposed seed inventory."""
import hashlib
import json
from pathlib import Path
import subprocess
from check_v04_protocol02 import seed_audit
from v04_protocol04 import REPO, CONFIG, load_protocol


def fresh_seeds():
    a=seed_audit([9301,9302,9303])
    allowed={str(CONFIG/'execution.json'),str(CONFIG/'seed_audit.json')}
    a['design_registrations']=[m for m in a['matches'] if m['path'] in allowed]
    a['matches']=[m for m in a['matches'] if m['path'] not in allowed]
    a['accepted']=not a['matches'] and not a['invalid_json']
    return a


def capture():
    prior=json.loads((CONFIG.parent/'protocol03/frozen.json').read_text())
    names=set(prior['assets'])
    names.update(str(p.relative_to(REPO)) for p in (REPO/'research/sta-velocity-control/scripts').glob('*.py'))
    names.update(str((CONFIG/p).relative_to(REPO)) for p in ('protocol.json','execution.json','pid/frozen.json','esta/frozen.json'))
    return dict(kind='offline implementation snapshot; exact execution SHA must be clean-built after approval',
        parent_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        assets={n:hashlib.sha256((REPO/n).read_bytes()).hexdigest() for n in sorted(names)},
        control_parameters=prior['control_parameters'],
        submodules=subprocess.check_output(['git','submodule','status','--recursive'],cwd=REPO,text=True).splitlines())


if __name__=='__main__':
    print(json.dumps(dict(frozen=capture(),seed_audit=fresh_seeds()),indent=2))
