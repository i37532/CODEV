#!/usr/bin/env python3
"""Index all M08 development attempts, including rejected performance gates.
Only writes NEW evidence/index files; raw logs remain external, no Git writes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


ROOT=Path(__file__).resolve().parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())


def record(data,output):
    verification=read(data/'verification01/evidence.json')
    comparison=read(data/'final01/comparison.json')
    series=read(data/'final01/series.json')
    require=[verification['success'],comparison['success'],series['success'],
             read(data/'restart01/result.json')['success'],read(data/'lifecycle01/lifecycle_analysis.json')['success']]
    if not all(require):raise RuntimeError('Mandatory M08 validation incomplete')
    for name,expected in series['source_files'].items():
        if sha(ROOT/name)!=expected:raise RuntimeError('Final series source drift: '+name)
    for r in comparison['runs']:
        if r['summary']['binary_sha256']!=verification['firmware_sha256']:raise RuntimeError('Final binary mismatch')
    runs=[]
    for p in sorted(data.rglob('result.json')):
        folder=p.parent
        runs.append(dict(path=str(folder),result=read(p),
                         analysis=read(folder/'m04_analysis.json') if (folder/'m04_analysis.json').exists() else None,
                         lifecycle=read(folder/'lifecycle_analysis.json') if (folder/'lifecycle_analysis.json').exists() else None,
                         transitions=read(folder/'postflight_transitions.json') if (folder/'postflight_transitions.json').exists() else None))
    source_paths=set(subprocess.check_output(['git','diff','HEAD','--name-only'],cwd=ROOT,text=True).splitlines())
    source_paths.update(subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines())
    sources={name:sha(ROOT/name) for name in sorted(source_paths) if (ROOT/name).is_file()
             and name.startswith(('src/','msg/','research/sta-rate-control/scripts/','research/sta-rate-control/m08/'))
             and not name.endswith(('artifacts.sha256','evidence.json'))}
    environment=[]
    for args in (['git','submodule','status','--recursive'],['c++','--version'],['cmake','--version'],['gzserver','--version'],['uname','-a']):
        p=subprocess.run(args,cwd=ROOT,text=True,capture_output=True)
        environment.append(dict(argv=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
    evidence=dict(start_head='d1f43ff63f211d3c95b2bf8fafba27e8c1a0fdb1',
                  current_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                  scope='M08 nominal Iris SITL development only; flight source is starting commit plus archived patch/new-file snapshots',
                  data_root=str(data),verification=verification,comparison=comparison,runs=runs,
                  gates={p.name:read(p) for p in sorted(data.glob('gate*.json'))},
                  source_files=sources,environment=environment,
                  matlab=dict(executable=shutil.which('matlab'),executed=False),
                  octave=dict(executable=shutil.which('octave'),executed=False))
    files=sorted(p for p in data.rglob('*') if p.is_file())
    with (output/'artifacts.sha256').open('x') as stream:
        stream.write(''.join(sha(p)+'  '+str(p)+'\n' for p in files))
    evidence.update(artifact_count=len(files),artifact_index_sha256=sha(output/'artifacts.sha256'))
    with (output/'evidence.json').open('x') as stream:json.dump(evidence,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(artifacts=len(files),records=len(runs),source_files=len(sources),index_sha256=evidence['artifact_index_sha256'])))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();record(args.data.resolve(),args.output.resolve())
