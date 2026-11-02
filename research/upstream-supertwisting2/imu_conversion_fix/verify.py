#!/usr/bin/env python3
"""Offline actual-source repair regression; separate known upstream failures."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import xml.etree.ElementTree as ET

REPAIR=Path('/home/yr/Desktop/Codev-SuperTwisting2-imu-fix')
ORIGINAL=Path('/home/yr/Desktop/Codev-SuperTwisting2-original')
BUILD=REPAIR/'build/px4_sitl_test'
ROOT=Path('/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-IMU-FIX-20261102')
REL='src/modules/simulation/simulator_mavlink'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def cases(p):
    root=ET.parse(p).getroot()
    return dict(tests=int(root.attrib['tests']),failures=int(root.attrib['failures']),
                disabled=int(root.attrib['disabled']),errors=int(root.attrib['errors']),
                failed_names=sorted(c.attrib['classname']+'.'+c.attrib['name']
                                    for c in root.iter('testcase') if c.find('failure') is not None))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    report=dict(new_flights=0,passed=False,commands=[],tests={})
    def save():(out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    def run(name,argv,expected=0):
        with (out/(name+'.log')).open('x') as f:
            r=subprocess.run([str(x) for x in argv],cwd=BUILD,stdout=f,stderr=subprocess.STDOUT,timeout=180)
        report['commands'].append(dict(name=name,argv=[str(x) for x in argv],exit_code=r.returncode,expected_exit=expected));save()
        print(name,r.returncode,flush=True)
        if r.returncode!=expected:raise RuntimeError(name+' unexpected exit; evidence retained')
    def test(name,binary,filter=None,expected=0):
        cmd=[binary,'--gtest_output=xml:'+str(out/(name+'.xml'))]
        if filter:cmd+=['--gtest_filter='+filter]
        run(name,cmd,expected);stats=cases(out/(name+'.xml'));report['tests'][name]=stats;save()
        assert stats['tests']>0 and stats['disabled']==0 and stats['errors']==0
        if expected==0:assert stats['failures']==0
        return stats
    db=json.loads((BUILD/'compile_commands.json').read_text())
    def compile_one(name,source,template,flags=(),target=None):
        entry=next(e for e in db if e['file'].endswith('/'+template) and (not target or target in e['command']))
        cmd=shlex.split(entry['command']);cmd[cmd.index('-c')+1]=str(source)
        obj=out/(name+'.o');cmd[cmd.index('-o')+1]=str(obj)
        for flag in ['-MF','-MT']:
            if flag in cmd:cmd[cmd.index(flag)+1]=str(obj)+('.d' if flag=='-MF' else '')
        cmd+=list(flags);run(name,cmd);return str(obj)
    def link_command(target):
        lines=subprocess.check_output(['ninja','-t','commands',target],cwd=BUILD,text=True).splitlines()
        line=next(l for l in reversed(lines) if ' -o '+target+' ' in l)
        return shlex.split(line.split(' && ')[1])
    base_link=link_command('functional-ImuConversion')
    original_object=next(v for v in base_link if v.endswith('/SimulatorMavlink.cpp.o'))
    def link(name,obj,sanitized=False):
        cmd=[obj if v==original_object else v for v in base_link]
        dest=out/name;cmd[cmd.index('-o')+1]=str(dest)
        if sanitized:cmd+=['-fsanitize=float-cast-overflow']
        run('link_'+name,cmd);return dest
    test('repaired',BUILD/'functional-ImuConversion')
    # Exact original .cpp, with current header only adding unused error-counter storage.
    # Keep the copied source outside ORIGINAL so the harness and object share layout.
    frozen=out/'frozen_SimulatorMavlink.cpp'
    shutil.copy2(ROOT/'original_snapshot'/REL/'SimulatorMavlink.cpp',frozen)
    assert sha(frozen)==sha(ORIGINAL/REL/'SimulatorMavlink.cpp')
    oldobj=compile_one('frozen_simulator',frozen,'SimulatorMavlink.cpp',
                       ['-I'+str(REPAIR/REL)],'functional-ImuConversion.dir')
    old=link('chain_frozen',oldobj)
    trace='ImuConversionChain.RepairValidTrace2048AgainstFrozenSource'
    test('frozen_trace',old,trace)
    rows=lambda n:[l for l in (out/(n+'.log')).read_text().splitlines() if l.startswith('REPAIR_TRACE ')]
    new_rows=rows('repaired');old_rows=rows('frozen_trace')
    assert len(new_rows)==2048 and new_rows==old_rows
    report['equivalent_samples']=2048
    report['trace_sha256']=hashlib.sha256(('\n'.join(new_rows)+'\n').encode()).hexdigest()
    negative=test('old_saturation_rejected',old,'ImuConversionChain.RepairSaturatedPulseKeepsSignAndClippingXYZ',expected=1)
    assert negative['tests']==1 and negative['failures']==1
    sanitized=compile_one('simulator_ubsan',REPAIR/REL/'SimulatorMavlink.cpp','SimulatorMavlink.cpp',
             ['-fsanitize=float-cast-overflow','-fno-sanitize-recover=float-cast-overflow'],'functional-ImuConversion.dir')
    test('repaired_ubsan',link('chain_ubsan',sanitized,True))
    # Unchanged pre-existing control suites, including the known failing PositionControl suite.
    for target in ['unit-rate_control_test','unit-AttitudeControl','unit-ControlMath','unit-Takeoff','unit-PositionControl']:
        test(target,BUILD/target,expected=1 if target=='unit-PositionControl' else 0)
    originals=[]
    for filename in ['ControlMath.cpp','PositionControl.cpp','PositionStaControl.cpp']:
        rel='src/modules/mc_pos_control/PositionControl/'+filename
        assert sha(ORIGINAL/rel)==sha(REPAIR/rel)
        originals.append(compile_one('original_'+filename,ORIGINAL/rel,filename))
    cmd=link_command('unit-PositionControl');library='src/modules/mc_pos_control/PositionControl/libPositionControl.a'
    i=cmd.index(library);cmd[i:i+1]=originals
    binary=out/'position_frozen';cmd[cmd.index('-o')+1]=str(binary);run('link_position_frozen',cmd)
    old_position=test('original_PositionControl',binary,expected=1)
    assert old_position==report['tests']['unit-PositionControl']
    assert old_position['tests']==16 and old_position['failures']==12
    report['position_failures_identical_to_unmodified_source']=True
    report['old_cpp_sha256']=sha(frozen)
    report['source_sha256']={str(REPAIR/REL/f):sha(REPAIR/REL/f) for f in
                           ['SimulatorMavlink.cpp','SimulatorMavlink.hpp','CMakeLists.txt','ImuConversionTest.cpp']}
    report['firmware_sha256']=sha(REPAIR/'build/px4_sitl_default/bin/px4')
    snapshot=json.loads((ROOT/'snapshot.json').read_text())
    for key in ['original_tracked_sha256','snapshot_sha256','frozen_b04_assets']:
        assert all(sha(p)==h for p,h in snapshot[key].items())
    report['original_preserved']=True;report['frozen_b04_assets_preserved']=len(snapshot['frozen_b04_assets'])
    report['passed']=True
    report['status']='conversion_repair_offline_passed_with_unchanged_upstream_PositionControl_failures'
    report['all_control_tests_passed']=False
    report['note']='No EKF/physics/flight validation. Saturation preserves sign and flags, not the full impulse.'
    save();print(json.dumps({k:report[k] for k in ['status','equivalent_samples','tests']},indent=2))

if __name__=='__main__':main()
