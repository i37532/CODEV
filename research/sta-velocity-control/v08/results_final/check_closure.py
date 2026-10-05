"""Read-only final raw-artifact/source/parameter audit, zero simulation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

REPO=Path('/home/yr/Desktop/Codev-autopilot');BASE=REPO/'research/sta-velocity-control/v08'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if args.output.exists():raise RuntimeError('Do not overwrite closure evidence')
    e=dict(success=False,new_flights=0,commands=[],raw_file_entries=0,raw_ulog_entries=0)
    try:
        for name in ('results01','results02','results03','results03b','results04','results05'):
            directory=BASE/name;index=directory/'original_artifacts.sha256';argv=['sha256sum','--status','-c',str(index)]
            result=subprocess.run(argv,cwd=REPO,capture_output=True,text=True)
            e['commands'].append(dict(argv=argv,exit_code=result.returncode,stderr=result.stderr,index_sha256=sha(index)))
            if result.returncode:raise RuntimeError('Raw evidence changed: '+name)
            e['raw_file_entries']+=len(index.read_text().splitlines())
            e['raw_ulog_entries']+=len(json.loads((directory/'summary.json').read_text())['raw_logs'])
            print(name,'raw hashes OK',flush=True)
        frozen=json.loads((BASE/'formal/frozen.json').read_text())
        for name,expected in frozen['assets'].items():
            if sha(REPO/name)!=expected:raise RuntimeError('Frozen asset changed: '+name)
        e['assets_checked']=len(frozen['assets'])
        verification=json.loads((BASE/'results_final/verification.json').read_text())
        assert verification['success'] and verification['head']=='392d61ca9876dd5e3bf27ad4b746e4f0f6c8c62b'
        e['formal_source_head']=verification['head'];e['verification_sha256']=sha(BASE/'results_final/verification.json')
        e['firmware_sha256']=sha(REPO/'build/px4_sitl_default/bin/px4');assert e['firmware_sha256']==verification['firmware_sha256']
        e['branch']=subprocess.check_output(['git','branch','--show-current'],cwd=REPO,text=True).strip();assert e['branch']=='research/sta-velocity-control'
        e['production_diff']=subprocess.check_output(['git','diff','dd3da2e3827b978cd065771c8e1a80df88fce2eb','--','src','msg','Tools','sitl'],cwd=REPO,text=True);assert not e['production_diff']
        e['submodules']=subprocess.check_output(['git','submodule','status','--recursive'],cwd=REPO,text=True)
        assert len(e['submodules'].splitlines())==33 and all(line.startswith(' ') for line in e['submodules'].splitlines())
        assert not subprocess.check_output(['git','submodule','foreach','--recursive','--quiet','git status --porcelain'],cwd=REPO,text=True)
        e['parameter_sha256']=sha(REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016')
        assert e['parameter_sha256']=='06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc'
        outcomes=json.loads((BASE/'formal/outcomes_unattempted.json').read_text());assert len(outcomes)==200 and all(x['status']=='unattempted' for x in outcomes)
        assert not Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-V09-FORMAL01').exists()
        e['formal_runs']=0;e['success']=True
    finally:args.output.write_text(json.dumps(e,indent=2)+'\n')
    print(json.dumps({k:v for k,v in e.items() if k not in ('commands','submodules')},indent=2))

if __name__=='__main__':main()
