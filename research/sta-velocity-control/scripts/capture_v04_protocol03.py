#!/usr/bin/env python3
"""Print freeze material, no file mutation and no flight. Apply snapshot before commit."""
import hashlib
import json
from pathlib import Path
import subprocess
from check_v04_protocol02 import seed_audit

REPO=Path(__file__).resolve().parents[3]
CONFIG=REPO/'research/sta-velocity-control/v04/protocol03'


def fresh_seeds():
    audit=seed_audit([9201,9202,9203])
    registration=str(CONFIG/'protocol.json')
    audit['design_registrations']=[m for m in audit['matches'] if m['path']==registration]
    audit['matches']=[m for m in audit['matches'] if m['path']!=registration]
    audit['accepted']=not audit['matches'] and not audit['invalid_json']
    return audit


def capture():
    prior=json.loads((CONFIG.parent/'protocol02/design_snapshot.json').read_text())
    names=set(prior['assets'])
    names.update(str(p.relative_to(REPO)) for p in (REPO/'research/sta-velocity-control/scripts').glob('*.py'))
    names.add('src/modules/logger/logged_topics.cpp')
    names.add(str((CONFIG/'protocol.json').relative_to(REPO)))
    names.add(str((CONFIG/'ExcitationExitTrace.cpp').relative_to(REPO)))
    assets={name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in sorted(names)}
    return dict(kind='execution asset snapshot; exact source SHA assigned by clean commit before launch',
        parent_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        assets=assets,control_parameters=prior['control_parameters'],
        submodules=subprocess.check_output(['git','submodule','status','--recursive'],cwd=REPO,text=True).splitlines())


if __name__=='__main__':
    print(json.dumps(dict(frozen=capture(),seed_audit=fresh_seeds()),indent=2))
