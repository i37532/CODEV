#!/usr/bin/env python3
"""Offline only: full inherited regressions, attitude tests, exact old-log replay."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET
from pyulog import ULog
import numpy as np
from v04_protocol04 import REPO, CONFIG
from v04_heading_stream import LiveLog, TOPICS, data, row, index, replay
from v04_task04 import freeze_reference


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    evidence=dict(kind='offline_only_no_flight',new_flights=0,commands=[],source_head=subprocess.check_output(
        ['git','rev-parse','HEAD'],cwd=REPO,text=True).strip())
    def run(name,argv,expected=0):
        with (out/(name+'.log')).open('w') as stream:
            result=subprocess.run(argv,cwd=REPO,stdout=stream,stderr=subprocess.STDOUT)
        evidence['commands'].append(dict(name=name,argv=argv,exit_code=result.returncode,expected_exit=expected))
        (out/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
        if result.returncode!=expected: raise RuntimeError(name+' failed')
    run('regression',['python3',str(REPO/'research/sta-velocity-control/scripts/verify_v04_repair.py'),
                      '--output',str(out/'regression')])
    run('attitude',[str(REPO/'build/px4_sitl_test/unit-AttitudeControl'),'--gtest_output=xml:'+str(out/'AttitudeControl.xml')])
    record=json.loads((CONFIG.parent/'results03/run01.json').read_text())
    source=Path(record['logs'][-1]['archive']);sha=hashlib.sha256(source.read_bytes()).hexdigest()
    if sha!=record['logs'][-1]['sha256']: raise ValueError('Old log changed')
    live=LiveLog(source);begin=time.monotonic();log=live.read();elapsed=time.monotonic()-begin
    independent=ULog(str(source));comparisons=0
    for stream in independent.data_list:
        if stream.name not in TOPICS: continue
        actual=log.get_dataset(stream.name,stream.multi_id).data
        for k,v in stream.data.items():
            np.testing.assert_array_equal(actual[k],v);comparisons+=1
    d=data(log,'vehicle_local_position');t=next(e['timestamp_us'] for e in record['events'] if e['name']=='takeoff_command')
    ref=freeze_reference(row(d,index(d,t)));r=replay(log,ref)
    if not r['confirmed'] or r['ready'] or record['success']: raise ValueError('Wrong historical classification')
    evidence['historical_replay']=dict(raw_sha256=sha,field_arrays_equal=comparisons,first_decode_wall_s=elapsed,
        confirmation=r,historical_success_unchanged=False,full_new_protocol_acceptance=False)
    # Final acceptance must refuse the old failed attempt; isolate all analysis writes.
    run('historical_rejection',['python3',str(REPO/'research/sta-velocity-control/scripts/analyze_v04_protocol04.py'),
        str(source.parent),'--output',str(out/'historical_analysis')],expected=1)
    reg=json.loads((out/'regression/evidence.json').read_text())
    evidence['cpp_tests']=reg['unique_cpp_tests']+int(ET.parse(out/'AttitudeControl.xml').getroot().get('tests'))
    import re
    evidence['python_tests']=int(re.search(r'Ran (\d+) tests',(out/'regression/python_tools.log').read_text())[1])
    evidence['success']=True
    evidence['eeprom_sha256']=hashlib.sha256((REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016').read_bytes()).hexdigest()
    (out/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps({k:v for k,v in evidence.items() if k!='historical_replay'},indent=2))


if __name__=='__main__':main()
