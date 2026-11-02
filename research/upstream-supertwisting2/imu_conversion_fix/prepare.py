#!/usr/bin/env python3
"""Preserve original STA2 and create an isolated repair checkout; never fly."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

MAIN=Path('/home/yr/Desktop/Codev-autopilot')
ORIGINAL=Path('/home/yr/Desktop/Codev-SuperTwisting2-original')
REPAIR=Path('/home/yr/Desktop/Codev-SuperTwisting2-imu-fix')
OUT=Path('/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-IMU-FIX-20261102')
HEAD='fc3720f67767c78cfab668777de13f68562fe2fd'
BRANCH='research/sta2-sim-imu-fix'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git(repo,*args):return subprocess.check_output(['git','-C',str(repo),*args],text=True)

def main():
    assert git(ORIGINAL,'rev-parse','HEAD').strip()==HEAD
    assert not REPAIR.exists() and not OUT.exists()
    assert not git(ORIGINAL,'branch','--list',BRANCH).strip()
    OUT.mkdir(parents=True)
    snapshot=OUT/'original_snapshot';snapshot.mkdir()
    evidence={'head':HEAD,'main_head':git(MAIN,'rev-parse','HEAD').strip(),
              'original_status':git(ORIGINAL,'status','--short'),
              'main_status':git(MAIN,'status','--short'),
              'submodules':git(ORIGINAL,'submodule','status','--recursive'),
              'original_tracked_sha256':{},'commands':[], 'new_flights':0}
    for name in git(ORIGINAL,'ls-files').splitlines():
        p=ORIGINAL/name
        if p.is_file():evidence['original_tracked_sha256'][str(p)]=sha(p)
    manifest=json.loads((MAIN/'research/upstream-supertwisting2/offboard/results/batch04/manifest.json').read_text())
    evidence['frozen_b04_assets']=manifest['assets']
    assert all(sha(p)==h for p,h in manifest['assets'].items())
    for name in ['src/modules/simulation/simulator_mavlink/SimulatorMavlink.cpp',
                 'src/modules/simulation/simulator_mavlink/SimulatorMavlink.hpp',
                 'build/px4_sitl_default/bin/px4','build/px4_sitl_default/CMakeCache.txt',
                 'build/px4_sitl_default/compile_commands.json']:
        src=ORIGINAL/name;dst=snapshot/name;dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst);assert sha(src)==sha(dst)
    with (snapshot/'original_head.tar').open('xb') as f:
        subprocess.run(['git','-C',str(ORIGINAL),'archive','--format=tar',HEAD],stdout=f,check=True)
    for key,repo in [('main',MAIN),('original',ORIGINAL)]:
        (snapshot/(key+'_worktree.patch')).write_text(git(repo,'diff','--binary'))
    enabled=[]
    for line in evidence['submodules'].splitlines():
        if line.startswith('-'):continue
        commit,path,*_=line.strip().split();enabled.append((commit,path))
        evidence['original_tracked_sha256'].update({str(ORIGINAL/path/n):sha(ORIGINAL/path/n)
            for n in git(ORIGINAL/path,'ls-files').splitlines() if (ORIGINAL/path/n).is_file()})
        patch=snapshot/('submodule_'+path.replace('/','_')+'.patch')
        patch.write_text(git(ORIGINAL/path,'diff','--binary'))
    cmd=['git','-C',str(ORIGINAL),'worktree','add','-b',BRANCH,str(REPAIR),HEAD]
    subprocess.run(cmd,check=True);evidence['commands'].append(cmd)
    # Local object stores only; no branch movement, network fetch, or mutation of original submodules.
    for commit,path in enabled:
        cmd=['git','clone','--shared','--no-checkout',str(ORIGINAL/path),str(REPAIR/path)]
        subprocess.run(cmd,check=True);evidence['commands'].append(cmd)
        cmd=['git','-C',str(REPAIR/path),'checkout','--detach',commit]
        subprocess.run(cmd,check=True);evidence['commands'].append(cmd)
    evidence['repair_branch']=git(REPAIR,'branch','--show-current').strip()
    evidence['repair_status']=git(REPAIR,'status','--short')
    evidence['snapshot_sha256']={str(p):sha(p) for p in snapshot.rglob('*') if p.is_file()}
    assert not evidence['repair_status']
    assert all(sha(p)==h for p,h in evidence['original_tracked_sha256'].items())
    (OUT/'snapshot.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(dict(snapshot=str(snapshot),repair=str(REPAIR),branch=BRANCH,
                         tracked_original_files=len(evidence['original_tracked_sha256']),frozen_assets=len(manifest['assets'])),indent=2))

if __name__=='__main__':main()
