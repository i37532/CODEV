"""Freeze current new protocol assets without rewriting historical snapshots."""
import json
import subprocess
import platform
from common import REPO,CONFIG,fingerprint,fresh_seeds,load_protocol

def capture():
    prior=REPO/'research/sta-velocity-control/v04/protocol17'
    data=json.loads((prior/'frozen.json').read_text()); p=load_protocol()
    data['control_parameters']['MPC_VC_DIV']=1
    data['control_parameters'].update({k:0 for k in p['candidate'] if k.endswith(('_Y','_Z'))})
    for mode in (0,1):
        target=CONFIG/('esta' if mode else 'pid'); target.mkdir(exist_ok=True)
        frozen=json.loads((prior/'pid/frozen.json').read_text())
        frozen['control_parameters'].update(p['startup_overrides'])
        frozen['control_parameters'].pop('MPC_VCT_TEST',None)
        frozen['control_parameters'].pop('MPC_VC_DIV',None)
        frozen['control_parameters'].update(p['candidate'])
        frozen['control_parameters'].update(MPC_VC_MODE=mode,MPC_VC_AXES=3*mode)
        (target/'frozen.json').write_text(json.dumps(frozen,indent=2)+'\n')
    names=set(data['assets'])
    names.update(['/usr/share/gazebo-11/models/ground_plane/model.sdf',
                  '/usr/share/sdformat9/1.6/surface.sdf','/usr/share/sdformat9/1.6/collision.sdf'])
    names.update(['research/sta-velocity-control/v05/qualified_xy.json','msg/velocity_ctrl_selection.msg','sim_scripts/_internal/toolbox.py'])
    for folder in ('src/modules/mc_pos_control','research/sta-velocity-control/v06','research/sta-velocity-control/v07'):
        names.update(str(f.relative_to(REPO)) for f in (REPO/folder).rglob('*') if f.is_file()
                     and f.suffix in ('.cpp','.hpp','.c','.py','.json','.md','.txt','.sh')
                     and f not in (CONFIG/'frozen.json',CONFIG/'seed_audit.json'))
    data.update(kind='V07 XY-only independent velocity correction cadence gates',
                parent_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
                assets={n:fingerprint(REPO/n) for n in sorted(names)})
    from run_v00 import ROOTFS,persisted_bson
    parameter_file=ROOTFS/'eeprom/parameters_10016'
    defaults=json.loads((REPO/'build/px4_sitl_default/parameters.json').read_text())['parameters']
    actual={**{x['name']:x['default'] for x in defaults},**persisted_bson(parameter_file.read_bytes())}
    required=dict(MC_RTC_MODE=0,MC_STA_AXES=0,MC_RTC_DIV=1,MC_RATT_TEST=0,MC_STA_TKO_MGT=0,MPC_VC_MODE=0,MPC_VC_AXES=0,MPC_VC_DIV=1)
    assert all(actual[k]==v for k,v in required.items()),'Persistent/default research parameters not restored'
    versions={}
    for argv in [['gcc','--version'],['cmake','--version'],['ninja','--version'],['gzserver','--version']]:
        r=subprocess.run(argv,text=True,capture_output=True)
        # Gazebo11's version-only path prints a valid version and returns255.
        # Preserve that status; this read-only metadata is NOT a simulator test.
        assert r.returncode==0 or (argv[0]=='gzserver' and r.returncode==255 and r.stdout.startswith('Gazebo multi-robot simulator, version 11.'))
        versions[argv[0]]=dict(command=argv,exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr)
    data['v07_environment']=dict(branch=subprocess.check_output(['git','branch','--show-current'],cwd=REPO,text=True).strip(),
        platform=platform.platform(),python=platform.python_version(),parameter_sha256=fingerprint(parameter_file),
        persistent_plus_compiled_defaults={k:actual[k] for k in required},runtime_check='required again by each flight; this snapshot is not runtime proof',
        recursive_submodules=subprocess.check_output(['git','submodule','status','--recursive'],cwd=REPO,text=True),
        tools=versions)
    audit=fresh_seeds()
    if not audit['accepted']: raise RuntimeError(json.dumps(audit))
    (CONFIG/'seed_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    (CONFIG/'frozen.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps(dict(assets=len(names),seed_audit_accepted=True)))

if __name__=='__main__': capture()
