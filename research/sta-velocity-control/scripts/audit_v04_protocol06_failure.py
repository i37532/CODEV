#!/usr/bin/env python3
"""Read-only diagnosis of series05; never repairs or changes original acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import numpy as np
from pyulog import ULog
from v04_protocol06 import REPO
from v04_heading_stream import data, replay
from v04_handoff06 import capture


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('run',type=Path)
    parser.add_argument('--output',type=Path,required=True); args=parser.parse_args()
    run,out=args.run.resolve(),args.output.resolve()
    if out==run or run in out.parents: raise ValueError('Isolate diagnosis from original evidence')
    out.mkdir(parents=True,exist_ok=False)
    result=json.loads((run/'result.json').read_text())
    metrics=json.loads((run/'v04_protocol06_metrics.json').read_text())
    ev={x['name']:x['timestamp_us'] for x in result['events']}
    evidence=dict(accepted=False,original_acceptance=metrics['accepted'],acceptance_changed=False,
        original_error=metrics['error'],source_head=result['source_head'],events=result['events'],logs=[],checks=[],commands=[])
    decoded=[]
    for item in result['logs']:
        path=Path(item['archive'])
        if sha(path)!=item['sha256']: raise ValueError('Original ULog fingerprint mismatch')
        u=ULog(str(path));decoded.append((item['bytes'],u))
        evidence['logs'].append(dict(**item,dropouts=len(u.dropouts),corruption=bool(u.file_corruption)))
    u=max(decoded,key=lambda x:x[0])[1]
    def check(name,value): evidence['checks'].append(dict(name=name,passed=bool(value)))
    check('completed_task_not_accepted',result['success'] and not metrics['accepted'])
    check('reported_error_matches',metrics['error']=='Empty/nonmonotonic vehicle_command')
    evidence['event_topics']={}
    for name in ('vehicle_command','vehicle_command_ack'):
        d=u.get_dataset(name).data;t=d['timestamp'].astype(np.int64)
        rows=[{k:v[i].item() for k,v in d.items()} for i in range(len(t))]
        evidence['event_topics'][name]=dict(rows=rows,equal_indices=np.flatnonzero(np.diff(t)==0).tolist(),
                                          backwards_indices=np.flatnonzero(np.diff(t)<0).tolist())
        check(name+'_distinct_takeoff_arm_share_timestamp',len(t)==4 and t[0]==t[1] and list(d['command'][:2])==[22,400])
        check(name+'_never_goes_backwards',np.all(np.diff(t)>=0))
        try: data(u,name)
        except ValueError as exc: evidence['event_topics'][name]['strict_accessor_error']=str(exc)
        else: raise ValueError('Expected original strict accessor rejection')
    ref=json.loads((run/'height_reference.json').read_text());frozen=json.loads((run/'task_yaw.json').read_text())
    target=json.loads((run/'handoff_target.json').read_text())
    evidence['heading']=replay(u,ref,end=ev['landed_disarmed'],frozen=frozen)
    rebuilt=capture(u,ref,frozen,ev['reposition_command'],source_us=target['source_timestamp'])
    check('source_provenance_exact',json.dumps(rebuilt,sort_keys=True)==json.dumps(target,sort_keys=True))
    c=u.get_dataset('vehicle_command').data;k=np.flatnonzero(c['command']==192)
    check('exactly_one_reposition',len(k)==1)
    k=int(k[0]);a=u.get_dataset('vehicle_command_ack').data;ak=np.flatnonzero(a['command']==192)
    check('unique_accepted_reposition_ack',len(ak)==1 and a['result'][ak[0]]==0)
    check('reposition_and_ack_before_handoff',ev['reposition_command']<=c['timestamp'][k]<=a['timestamp'][ak[0]]<=ev['handoff_ready'])
    # Independently reveal the next raw-comparison issue without bypassing or rerunning acceptance.
    cc=json.loads((REPO/'build/px4_sitl_default/compile_commands.json').read_text())
    receiver=next(x for x in cc if x['file'].endswith('/mavlink_receiver.cpp'))
    evidence['receiver_build_command']=receiver['command']
    numeric_flags=[x for x in shlex.split(receiver['command']) if x.startswith('-O') or x in
                   ('-fno-signed-zeros','-fno-trapping-math','-freciprocal-math','-fno-math-errno')]
    evidence['coordinate_probe_flags']=numeric_flags
    probe=REPO/'research/sta-velocity-control/v04/results06/ReceiverScaleProbe.cpp'
    evidence['source_sha256']={str(p.relative_to(REPO)):sha(p) for p in
        (probe,REPO/'src/modules/mavlink/mavlink_receiver.cpp',REPO/'src/modules/commander/Commander.cpp',
         REPO/'research/sta-velocity-control/scripts/analyze_v04_handoff06.py',
         REPO/'research/sta-velocity-control/scripts/v04_heading_stream.py')}
    evidence['coordinate_checks']=[]
    for variant,flags in [('strict',['-O2']),('receiver_flags',numeric_flags)]:
        binary=out/variant;argv=['g++','-std=c++14',*flags,str(probe),'-o',str(binary)]
        p=subprocess.run(argv,capture_output=True,text=True)
        (out/(variant+'_compile.log')).write_text(p.stdout+p.stderr)
        evidence['commands'].append(dict(argv=argv,exit_code=p.returncode));p.check_returncode()
        for wire,field in [('x','param5'),('y','param6')]:
            argv=[str(binary),str(target['wire'][wire])];q=subprocess.run(argv,capture_output=True,text=True)
            evidence['commands'].append(dict(argv=argv,exit_code=q.returncode,stdout=q.stdout));q.check_returncode()
            value=float(q.stdout.split()[0]);actual=float(c[field][k]);expected=target['lat' if wire=='x' else 'lon']
            evidence['coordinate_checks'].append(dict(variant=variant,wire=wire,value=value,hex=value.hex(),
                raw_value=actual,raw_hex=actual.hex(),original_python=expected,original_python_hex=expected.hex(),
                raw_matches_probe=actual==value,difference_deg=actual-expected,
                difference_ulp=(actual-expected)/np.spacing(expected)))
    optimized=[x for x in evidence['coordinate_checks'] if x['variant']=='receiver_flags']
    check('actual_receiver_flags_reproduce_raw_coordinates',all(x['raw_matches_probe'] for x in optimized))
    check('additional_exact_comparison_mismatch_observed',any(x['difference_ulp']!=0 for x in optimized))
    evidence['flight_metrics_descriptive_only']=metrics
    evidence['unexecuted_checks']='Full height_task/check_handoff acceptance stops at strict event accessor; not retroactively completed or accepted here. No paired metrics or seed comparison.'
    live=[json.loads(s) for s in (run/'heading_live.jsonl').read_text().splitlines()]
    evidence['live_transport']=dict(observations=len(live),min_age_us=min(x['age_us'] for x in live),max_age_us=max(x['age_us'] for x in live))
    check('ulog_no_reported_dropout_or_corruption',all(not x['dropouts'] and not x['corruption'] for x in evidence['logs']))
    evidence['diagnostic_passed']=all(x['passed'] for x in evidence['checks'])
    files=sorted(p for p in run.parent.rglob('*') if p.is_file() and not p.is_symlink())
    (out/'original_artifacts.sha256').write_text(''.join(f'{sha(p)}  {p}\n' for p in files))
    evidence['original_artifact_count']=len(files)
    (out/'diagnosis.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps({k:evidence[k] for k in ('original_error','checks','coordinate_checks','diagnostic_passed')},indent=2))
    return 0 if evidence['diagnostic_passed'] else 1


if __name__=='__main__':raise SystemExit(main())
