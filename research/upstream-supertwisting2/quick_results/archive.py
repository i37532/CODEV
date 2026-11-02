#!/usr/bin/env python3
"""Archive bounded run receipts and verify unchanged original/frozen evidence."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

from analyze_results import ROOT,HERE,digest,require

MAIN=HERE.parents[2]
REPAIR=Path('/home/yr/Desktop/Codev-SuperTwisting2-imu-fix')
OLDROOT=Path('/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-IMU-FIX-20261102')


def main():
    out=HERE/'results01/evidence'
    require(not out.exists(),'Do not overwrite evidence')
    source=json.loads((OLDROOT/'snapshot.json').read_text())
    for key in ('original_tracked_sha256','frozen_b04_assets'):
        require(all(digest(p)==h for p,h in source[key].items()),'Historical evidence changed: '+key)
    q=json.loads((ROOT/'qualification02/qualification.json').read_text())
    require(q['passed'],'Qualification failed')
    for p,h in q['source_sha256'].items():require(digest(p)==h,'Qualified tool changed')
    report=dict(new_budget=5,new_attempts=0,new_accepted=0,stages={},
                original_tracked_unchanged=len(source['original_tracked_sha256']),
                old_b04_assets_unchanged=len(source['frozen_b04_assets']),
                source_status={},external_sha256={},committed=False,pushed=False)
    out.mkdir(parents=True)
    for stage,count in [('contact_gate',1),('comparison',4)]:
        root=ROOT/stage;m=json.loads((root/'manifest.json').read_text())
        require(m['max_attempts']==count,'Wrong budget')
        require(len(list((root/'runs').iterdir()))==count,'Wrong attempt count')
        for p,h in m['assets'].items():require(digest(p)==h,'Frozen asset changed: '+p)
        outcomes={}
        for job in m['jobs']:
            d=root/'runs'/job['id'];r=json.loads((d/'result.json').read_text())
            accepted=r.get('success') and r.get('independent_replay_passed') and r.get('parameter_restore_exact')
            require(accepted and r.get('remaining_simulators')==[],'Incomplete flight/restore')
            report['new_attempts']+=1;report['new_accepted']+=1
            outcomes[job['id']]=dict(system=job['system'],accepted=True,
                                    result=str(d/'result.json'),sha256=digest(d/'result.json'))
            dest=out/stage/job['id'];dest.mkdir(parents=True)
            for name in ('result.json','origin.json','parameters_start.txt','parameters_hover.txt','parameters_end.txt',
                         'parameter_backup.json','contact_audit.json'):
                if (d/name).exists():shutil.copy2(d/name,dest/name)
            for p in d.rglob('*'):
                if p.is_file():report['external_sha256'][str(p)]=digest(p)
        (root/'outcomes.json').write_text(json.dumps(outcomes,indent=2)+'\n')
        report['stages'][stage]=outcomes
        shutil.copy2(root/'manifest.json',out/(stage+'_manifest.json'))
    shutil.copy2(ROOT/'contact_gate/repair_source.patch',out/'repair_source.patch')
    shutil.copy2(ROOT/'qualification02/qualification.json',out/'qualification.json')
    for repo in (MAIN,REPAIR):
        subprocess.run(['git','diff','--check'],cwd=repo,check=True)
        report['source_status'][str(repo)]=dict(head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),
            branch=subprocess.check_output(['git','branch','--show-current'],cwd=repo,text=True).strip(),
            status=subprocess.check_output(['git','status','--short'],cwd=repo,text=True))
    require(subprocess.check_output(['git','diff','--binary'],cwd=MAIN,text=True)==
            (OLDROOT/'original_snapshot/main_worktree.patch').read_text(),'Pre-existing main tracked changes altered')
    report['main_preexisting_tracked_diff_preserved']=True
    report['remaining_simulators']=[]
    sys.path.insert(0,str(HERE.parent/'tools'))
    from run_hover import active_simulators
    require(not active_simulators(),'Simulator process remains')
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('new_budget','new_attempts','new_accepted','old_b04_assets_unchanged')}))


if __name__=='__main__':main()
