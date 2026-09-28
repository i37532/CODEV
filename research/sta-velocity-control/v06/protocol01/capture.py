"""Freeze current new protocol assets without rewriting historical snapshots."""
import json
import subprocess
from common import REPO,CONFIG,fingerprint,fresh_seeds,load_protocol

def capture():
    prior=REPO/'research/sta-velocity-control/v04/protocol17'
    data=json.loads((prior/'frozen.json').read_text()); p=load_protocol()
    data['control_parameters'].update({k:0 for k in p['candidate'] if k.endswith(('_Y','_Z'))})
    for mode in (0,1):
        target=CONFIG/('esta' if mode else 'pid'); target.mkdir(exist_ok=True)
        frozen=json.loads((prior/'pid/frozen.json').read_text())
        frozen['control_parameters'].update(p['startup_overrides'])
        frozen['control_parameters'].pop('MPC_VCT_TEST',None)
        frozen['control_parameters'].update(p['candidate'])
        frozen['control_parameters'].update(MPC_VC_MODE=mode,MPC_VC_AXES=7*mode)
        (target/'frozen.json').write_text(json.dumps(frozen,indent=2)+'\n')
    names=set(data['assets'])
    names.update(['research/sta-velocity-control/e01_xyz/qualified_xyz.json','sim_scripts/_internal/toolbox.py'])
    for folder in ('src/modules/mc_pos_control','research/sta-velocity-control/v06'):
        names.update(str(f.relative_to(REPO)) for f in (REPO/folder).rglob('*') if f.is_file()
                     and f.suffix in ('.cpp','.hpp','.c','.py','.json','.md','.txt','.sh')
                     and f not in (CONFIG/'frozen.json',CONFIG/'seed_audit.json'))
    data.update(kind='V06 XYZ trajectory tasks; preserved physical gates',
                parent_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
                assets={n:fingerprint(REPO/n) for n in sorted(names)})
    audit=fresh_seeds()
    if not audit['accepted']: raise RuntimeError(json.dumps(audit))
    (CONFIG/'seed_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    (CONFIG/'frozen.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps(dict(assets=len(names),seed_audit_accepted=True)))

if __name__=='__main__': capture()
