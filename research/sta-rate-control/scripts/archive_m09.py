#!/usr/bin/env python3
"""Index M09 evidence after acceptance, never delete data or commit/push."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--series',type=Path,required=True);p.add_argument('--verification',type=Path,required=True)
    a=p.parse_args();repo=Path(__file__).resolve().parents[3];root=a.root.resolve();out=repo/'research/sta-rate-control/m09'
    series=json.loads((a.series/'series.json').read_text());verification=json.loads((a.verification/'evidence.json').read_text())
    audit=json.loads((a.series/'supplementary_audit.json').read_text())
    refined_path=a.series/'refined_analysis.json'
    refined=json.loads(refined_path.read_text()) if refined_path.exists() else None
    assert series['success'] and len(series['runs'])==9 and verification['success'], 'Not accepted'
    assert audit['success'] and len(audit['runs'])==9, 'Whole-flight audit not accepted'
    assert sha(repo/'build/px4_sitl_default/bin/px4') == series['firmware_sha256'], 'Unexplained firmware drift'
    files=[x for x in sorted(root.rglob('*')) if x.is_file() and '__pycache__' not in x.parts]
    (out/'artifacts.sha256').write_text(''.join(f'{sha(f)}  {f}\n' for f in files))
    changed=subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=repo,text=True).splitlines()
    changed+=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=repo,text=True).splitlines()
    source={name:sha(repo/name) for name in sorted(set(changed)) if (repo/name).is_file()
            and not name.startswith(('research/sta-rate-control/m09/','research/sta-rate-control/reports/'))
            and name!='research/sta-rate-control/README.md'}
    environment={}
    for key,cmd in [('compiler',['g++','--version']),('gazebo',['gazebo','--version']),('kernel',['uname','-a']),
                    ('cpu',['lscpu']),('submodules',['git','submodule','status','--recursive'])]:
        r=subprocess.run(cmd,cwd=repo,text=True,capture_output=True)
        environment[key]=dict(argv=cmd,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
    evidence=dict(scope='M09 Iris SITL development; not M10 or hardware',source_head=series['source_head'],
                  series_path=str(a.series.resolve()),verification_path=str(a.verification.resolve()),
                  series=series,refined_analysis=refined,supplementary_audit=audit,verification=verification,source_files=source,environment=environment,
                  raw_file_count=len(files),index_sha256=sha(out/'artifacts.sha256'))
    (out/'evidence.json').write_text(json.dumps(evidence,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(dict(raw_files=len(files),index_sha256=evidence['index_sha256']),indent=2))


if __name__=='__main__':main()
