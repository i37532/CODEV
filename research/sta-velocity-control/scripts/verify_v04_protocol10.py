#!/usr/bin/env python3
"""Offline wiring/build/corpus verification. Never calls an execution runner."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from pyulog import ULog
from run_v00 import active_simulators
from replay_v04_clock09 import ROOT, copy_metadata, outcome, digest
from v04_protocol10 import REPO, CONFIG, load_protocol
from v04_live_clock09 import replay as live_replay
from analyze_v04_protocol10 import analyze


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    out=p.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    param=REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
    e=dict(kind='offline_protocol10_wiring_not_flight',new_flights=0,commands=[],passed=False,
        source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        eeprom_before=digest(param),active_simulators_before=active_simulators())
    if e['active_simulators_before']:raise ValueError('Simulator already active')
    def save(): (out/'evidence.json').write_text(json.dumps(e,indent=2)+'\n')
    def run(name,argv,expected=0):
        with (out/(name+'.log')).open('w') as f:
            r=subprocess.run(argv,cwd=REPO,stdout=f,stderr=subprocess.STDOUT)
        e['commands'].append(dict(name=name,argv=argv,exit_code=r.returncode,expected_exit=expected));save()
        print(name,r.returncode,flush=True)
        if r.returncode!=expected:raise RuntimeError(name+' failed; evidence retained')
    save()
    scripts=REPO/'research/sta-velocity-control/scripts'
    run('full_regression',['python3',str(scripts/'verify_v04_protocol04.py'),'--output',str(out/'full')])
    run('imu_conversion',['python3',str(scripts/'verify_v04_imu0_repair.py'),'--output',str(out/'imu')])
    run('seven_clock_replays',['python3',str(scripts/'replay_v04_clock09.py'),'--output',str(out/'seven')])
    run('eight_landing_replays',['python3',str(scripts/'replay_v04_landing10.py'),'--output',str(out/'eight')])
    records=[ROOT/'results01/run01_result.json']+[ROOT/f'results{n:02d}/run01.json' for n in range(3,10)]
    e['historical_wiring']=[]
    for number,path in enumerate(records,1):
        record=json.loads(path.read_text());entry=max(record['logs'],key=lambda x:x['bytes'])
        if digest(entry['archive'])!=entry['sha256']:raise ValueError('Historical log changed')
        source=Path(entry['archive']).parent;dest=out/f'new_chain_series{number:02d}';copy_metadata(source,dest)
        job=json.loads((dest/'job.json').read_text())
        result=analyze(dest,load_protocol(),job)
        if result['accepted'] or 'historical results cannot be accepted' not in result['error']:
            raise ValueError('Old job must not become new acceptance')
        ref=source/'height_reference.json';frozen=source/'task_yaw.json'
        heading=outcome(lambda:live_replay(ULog(entry['archive']),json.loads(ref.read_text()),
            frozen=json.loads(frozen.read_text()) if frozen.exists() else None))
        e['historical_wiring'].append(dict(series=number,accepted=False,new_entry=result,live_heading=heading))
    old=json.loads((out/'seven/evidence.json').read_text())
    for path,sha in old['input_fingerprints'].items():
        if digest(path)!=sha:raise ValueError('Original changed during new-chain replay')
    eight=json.loads((out/'eight/evidence.json').read_text())
    for path,sha in eight['input_fingerprints'].items():
        if digest(path)!=sha:raise ValueError('Original changed during landing replay')
    e['eight_historical_inputs_unchanged']=len(eight['input_fingerprints'])
    e['eight_historical_verdicts_unchanged']=True
    reg=json.loads((out/'full/evidence.json').read_text())
    imu=json.loads((out/'imu/evidence.json').read_text())
    e.update(cpp_control_tests=reg['cpp_tests'],cpp_imu_unique_tests=imu['unique_gtests'],
        cpp_imu_sanitizer_tests=imu['tests']['sanitized_repaired']['tests'],python_tests=reg['python_tests'],
        historical_inputs_unchanged=len(old['input_fingerprints']),firmware_sha256=digest(REPO/'build/px4_sitl_default/bin/px4'),
        eeprom_after=digest(param),active_simulators_after=active_simulators(),seven_historical_verdicts_unchanged=True)
    if e['eeprom_before']!=e['eeprom_after'] or e['active_simulators_after']:raise ValueError('Unexpected runtime mutation')
    e['passed']=True;save()
    files=sorted(x for x in out.rglob('*') if x.is_file() and x!=out/'artifacts.sha256')
    (out/'artifacts.sha256').write_text(''.join(f'{digest(x)}  {x}\n' for x in files))
    print(json.dumps({k:v for k,v in e.items() if k not in ('historical_wiring','commands')},indent=2))


if __name__=='__main__':main()
