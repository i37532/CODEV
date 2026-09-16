#!/usr/bin/env python3
"""Archive M06 provenance and every attempt, including rejected results."""
import argparse
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
from record_m05 import ROOT, sha, command


def record(data, output):
    tests={}
    for path in sorted(data.glob('*.xml')):
        node=ET.parse(path).getroot()
        tests[path.stem]={k:int(node.attrib.get(k,0)) for k in ('tests','failures','errors','disabled')}
    runs=[]
    for path in sorted(data.glob('*/result.json')):
        result=json.loads(path.read_text());folder=path.parent;summary=folder/'m04_analysis.json'
        transitions=folder/'postflight_transitions.json'
        runs.append(dict(path=str(folder),result=result,
                         analysis=json.loads(summary.read_text()) if summary.exists() else None,
                         postflight_transitions=json.loads(transitions.read_text()) if transitions.exists() else None,
                         source_patch_sha256=sha(folder/'tracked_diff.patch')))
    paths=subprocess.check_output(['git','diff','HEAD','--name-only'],cwd=ROOT,text=True).splitlines()
    sources=[p for p in paths if p.startswith(('src/','msg/','research/sta-rate-control/scripts/')) or p in
             ['research/sta-rate-control/m06/calibration.json','research/sta-rate-control/m06/iris_esta_rpy.json','research/sta-rate-control/m06/protocol.json']]
    evidence=dict(start_head='7ef77081a32b9d5e42fe8167659c894f13dff524',
                  current_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                  scope='Iris SITL M06 development; flights on M05 HEAD plus archived patch, not future clean commit',
                  data_root=str(data),tests=tests,actual_cpp_tests=sum(t['tests'] for t in tests.values()),runs=runs,
                  source_files={p:sha(ROOT/p) for p in sources},
                  environment=[command(args) for args in [['git','submodule','status','--recursive'],['c++','--version'],
                                                         ['cmake','--version'],['gzserver','--version'],['uname','-a']]],
                  comparisons={p.name:json.loads(p.read_text()) for p in sorted(data.glob('comparison*.json'))})
    files=[p for p in sorted(data.rglob('*')) if p.is_file()]
    with (output/'artifacts.sha256').open('x') as stream:
        stream.write(''.join(sha(p)+'  '+str(p)+'\n' for p in files))
    evidence.update(artifact_count=len(files),artifact_index_sha256=sha(output/'artifacts.sha256'))
    with (output/'evidence.json').open('x') as stream:json.dump(evidence,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(artifacts=len(files),attempts=len(runs),cpp_tests=evidence['actual_cpp_tests'])))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();record(args.data.resolve(),args.output.resolve())
