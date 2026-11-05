#!/usr/bin/env python3
"""Verify the authorized IMU0 conversion repair against frozen production source.

No flight, socket, parameter save or historical artifact changes.
Old-source defect rejection is a separate negative control, never a passing flight.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[3]
BUILD = REPO/'build/px4_sitl_test'
TEST = REPO/'research/sta-velocity-control/v04/imu0_repair01/ImuConversionRepairTest.cpp'
FROZEN = 'e9d824d06d5b253937d739da57f53bd531169fb6'
SOURCES = ['src/modules/simulator/simulator_mavlink.cpp',
           'src/lib/drivers/accelerometer/PX4Accelerometer.cpp',
           'src/modules/sensors/vehicle_imu/VehicleIMU.cpp']


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    out=p.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    e=dict(kind='offline_actual_sources_not_flight',new_flights=0,commands=[],passed=False,
           head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip())
    db=json.loads((BUILD/'compile_commands.json').read_text())
    def save(): (out/'evidence.json').write_text(json.dumps(e,indent=2)+'\n')
    def run(name,argv,expected=0,extra_env=None):
        env={**os.environ,**(extra_env or {})}
        with (out/(name+'.log')).open('w') as f:
            r=subprocess.run(argv,cwd=BUILD,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=300)
        e['commands'].append(dict(name=name,argv=argv,exit_code=r.returncode,expected_exit=expected,extra_env=extra_env))
        save();print(name,r.returncode,flush=True)
        if r.returncode!=expected:raise RuntimeError(name+' failed; evidence preserved')
    def compile_one(name,source,template,sanitize=False,extra=()):
        entry=next(v for v in db if v['file'].endswith('/'+template))
        argv=shlex.split(entry['command']);argv[argv.index('-c')+1]=str(source)
        obj=out/(name+'.o');argv[argv.index('-o')+1]=str(obj)
        argv+=list(extra)
        if sanitize:argv+=['-fsanitize=float-cast-overflow','-fno-sanitize-recover=float-cast-overflow']
        run(name,argv);return str(obj)
    run('compiler',['/usr/bin/c++','--version'])
    commands=subprocess.check_output(['ninja','-t','commands','functional-VelocityModule'],cwd=BUILD,text=True)
    line=next(v for v in reversed(commands.splitlines()) if ' -o functional-VelocityModule ' in v)
    original=shlex.split(line.split(' && ')[1])
    # Existing functional runner and infrastructure; discard unused module objects.
    link=[x for x in original if x not in ('-rdynamic','-Wl,--export-dynamic')
          and not x.endswith('VelocityModuleTest.cpp.o')]
    extras=['src/lib/drivers/gyroscope/libdrivers_gyroscope.a',
            'src/lib/drivers/magnetometer/libdrivers_magnetometer.a',
            'src/lib/drivers/barometer/libdrivers_barometer.a',
            'src/lib/sensor_calibration/libsensor_calibration.a',
            'src/lib/conversion/libconversion.a']
    harness=compile_one('harness',TEST,'VelocityModuleTest.cpp',extra=[
        '-fno-access-control','-I'+str(REPO/'mavlink/include/mavlink'),
        '-I'+str(REPO/'src/modules/sensors'),'-Wno-address-of-packed-member'])
    source_objects=[compile_one(Path(s).stem,REPO/s,Path(s).name) for s in SOURCES]
    def link_binary(name,objects,sanitize=False):
        argv=link.copy();binary=out/name;argv[argv.index('-o')+1]=str(binary)
        # Static groups resolve sensor calibration/parameters circular references.
        first=next(i for i,x in enumerate(argv) if x.endswith('.a'))
        argv[first:first]=[harness,*objects,'-Wl,--start-group']
        argv+=extras+['-Wl,--end-group','-Wl,--gc-sections']
        if sanitize:argv+=['-fsanitize=float-cast-overflow']
        run('link_'+name,argv);return str(binary)
    normal=link_binary('chain',source_objects)
    valid_filter='ImuConversionChain.*-ImuConversionChain.Overflow*:ImuConversionChain.Invalid*'
    run('repaired',[normal,'--gtest_filter='+valid_filter,
                    '--gtest_output=xml:'+str(out/'repaired.xml')])
    # Freeze the exact historical implementation; no copied conversion formula.
    original_source=subprocess.check_output(['git','show',FROZEN+':'+SOURCES[0]],cwd=REPO)
    frozen_path=out/'frozen_simulator_mavlink.cpp';frozen_path.write_bytes(original_source)
    e['reference_source_sha256']=hashlib.sha256(original_source).hexdigest()
    original_object=compile_one('frozen_simulator',frozen_path,'simulator_mavlink.cpp',
                               extra=['-I'+str(REPO/'src/modules/simulator')])
    old=link_binary('chain_frozen',[original_object,*source_objects[1:]])
    trace_filter='--gtest_filter=ImuConversionChain.RepairValidTrace2048AgainstFrozenSource'
    run('frozen_valid_trace',[old,trace_filter,'--gtest_output=xml:'+str(out/'frozen_valid_trace.xml')])
    get_trace=lambda name:[x for x in (out/(name+'.log')).read_text().splitlines() if x.startswith('REPAIR_TRACE ')]
    old_rows=get_trace('frozen_valid_trace');new_rows=get_trace('repaired')
    if len(old_rows)!=2048 or old_rows!=new_rows:
        raise RuntimeError('Frozen valid-range trace mismatch')
    e['equivalent_samples']=len(new_rows)
    e['equivalent_trace_sha256']=hashlib.sha256(('\n'.join(new_rows)+'\n').encode()).hexdigest()
    # Negative control: the original implementation fails the new sign/clipping test.
    run('frozen_defect_rejected',[old,'--gtest_filter=ImuConversionChain.RepairSaturatedPulseKeepsSignAndClippingXYZ',
                                '--gtest_output=xml:'+str(out/'frozen_defect_rejected.xml')],1)
    attrs=ET.parse(out/'frozen_defect_rejected.xml').getroot().attrib
    if int(attrs['tests'])!=1 or int(attrs['failures'])!=1:
        raise RuntimeError('Negative control did not fail exactly one test')
    sanitized=compile_one('simulator_mavlink_ubsan',REPO/SOURCES[0],'simulator_mavlink.cpp',sanitize=True)
    sanitizer=link_binary('chain_ubsan',[sanitized,*source_objects[1:]],True)
    run('sanitized_repaired',[sanitizer,'--gtest_filter='+valid_filter,
                             '--gtest_output=xml:'+str(out/'sanitized_repaired.xml')])
    e['tests']={}
    for name in ['repaired','sanitized_repaired','frozen_valid_trace']:
        attrs=ET.parse(out/(name+'.xml')).getroot().attrib
        e['tests'][name]={k:int(attrs[k]) for k in ['tests','failures','errors','disabled']}
        if not e['tests'][name]['tests'] or any(e['tests'][name][k] for k in ['failures','errors','disabled']):
            raise RuntimeError('Empty/failed suite')
    areas=[json.loads(line.split(' ',1)[1]) for line in (out/'repaired.log').read_text().splitlines()
           if line.startswith('REPAIR_AREA ')]
    (out/'areas.json').write_text(json.dumps(areas,indent=2)+'\n')
    e['source_sha256']={s:hashlib.sha256((REPO/s).read_bytes()).hexdigest() for s in
                        [*SOURCES,'research/sta-velocity-control/v04/imu0_chain01/ImuConversionChainTest.cpp',str(TEST.relative_to(REPO)),str(Path(__file__).resolve().relative_to(REPO))]}
    e['unique_gtests']=e['tests']['repaired']['tests']
    e['frozen_source_commit']=FROZEN;e['expected_negative_control_failures']=1
    e['passed']=True;save()
    files=sorted(p for p in out.iterdir() if p.is_file() and p.name!='artifacts.sha256')
    (out/'artifacts.sha256').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p}\n' for p in files))
    print(json.dumps(dict(tests=e['tests'],equivalent_samples=e['equivalent_samples'],areas=areas),indent=2))


if __name__=='__main__':main()
