#!/usr/bin/env python3
"""Create a small evidence index; logs/binaries stay outside git. Never infer pass."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[3]


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def command(args):
    p=subprocess.run(args,cwd=ROOT,text=True,capture_output=True)
    return dict(command=args,exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr)


def record(data, output):
    tests={}
    for p in sorted(data.glob('*.xml')):
        node=ET.parse(p).getroot()
        tests[p.stem]={k:int(node.attrib.get(k,0)) for k in ['tests','failures','errors','disabled']}
    runs=[]
    for p in sorted(data.glob('*/result.json')):
        result=json.loads(p.read_text()); folder=p.parent
        summary=folder/'m04_analysis.json'
        runs.append(dict(path=str(folder),scenario_success=result['success'],
                         analysis=json.loads(summary.read_text()) if summary.exists() else None,
                         result=result,source_patch_sha256=sha(folder/'tracked_diff.patch')))
    paths=subprocess.check_output(['git','diff','HEAD','--name-only'],cwd=ROOT,text=True).splitlines()
    sources=[p for p in paths if p.startswith(('src/','msg/','research/sta-rate-control/scripts/')) or p in
             ['research/sta-rate-control/m05/calibration.json','research/sta-rate-control/m05/iris_esta_rp.json','research/sta-rate-control/m05/protocol.json']]
    evidence=dict(start_head='e9570f52389bae0aa492a9fb7bfaee4ebcfd96af',
                  current_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                  scope='Iris SITL M05 development; runs are HEAD plus archived patch, not future clean commit',
                  data_root=str(data),tests=tests,actual_cpp_tests=sum(t['tests'] for t in tests.values()),runs=runs,
                  source_files={p:sha(ROOT/p) for p in sources},
                  environment=[command(args) for args in [['git','submodule','status','--recursive'],['c++','--version'],
                                                         ['cmake','--version'],['gzserver','--version'],['uname','-a']]],
                  comparisons={p.name:json.loads(p.read_text()) for p in sorted(data.glob('comparison*.json'))})
    files=[p for p in sorted(data.rglob('*')) if p.is_file()]
    lines=''.join(sha(p)+'  '+str(p)+'\n' for p in files)
    with (output/'artifacts.sha256').open('x') as stream: stream.write(lines)
    evidence['artifact_count']=len(files)
    evidence['artifact_index_sha256']=sha(output/'artifacts.sha256')
    with (output/'evidence.json').open('x') as stream:
        json.dump(evidence,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(artifacts=len(files),runs=len(runs),cpp_tests=evidence['actual_cpp_tests'])))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    record(args.data.resolve(),args.output.resolve())
