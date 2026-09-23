#!/usr/bin/env python3
"""Build actual conversion/driver/VehicleIMU sources, offline uORB only.

No CMake/production source edits, simulator processes, sockets or parameter saves.
Separate range-valid tests from defect reproductions and expected UBSan failures.
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
TEST = REPO/'research/sta-velocity-control/v04/imu0_chain01/ImuConversionChainTest.cpp'
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
    run('range_valid',[normal,'--gtest_filter=ImuConversionChain.*-ImuConversionChain.Overflow*:ImuConversionChain.Invalid*',
                       '--gtest_output=xml:'+str(out/'range_valid.xml')])
    run('defect_reproduction',[normal,'--gtest_filter=ImuConversionChain.Overflow*',
                               '--gtest_output=xml:'+str(out/'defect_reproduction.xml')])
    sanitized=compile_one('simulator_mavlink_ubsan',REPO/SOURCES[0],'simulator_mavlink.cpp',sanitize=True)
    sanitizer=link_binary('chain_ubsan',[sanitized,*source_objects[1:]],True)
    run('sanitized_range_valid',[sanitizer,'--gtest_filter=ImuConversionChain.*-ImuConversionChain.Overflow*:ImuConversionChain.Invalid*',
                                 '--gtest_output=xml:'+str(out/'sanitized_range_valid.xml')])
    # +16 g is already 32768 counts (outside int16); -16 g is -32768
    # and is exercised in the valid suite. Also probe just below the negative edge.
    invalid_inputs=['156.906403','-156.911194','157','-157','250','-250','nan','inf','-inf','1e20']
    for i,value in enumerate(invalid_inputs):
        name='sanitized_invalid_'+str(i)
        run(name,[sanitizer,'--gtest_filter=ImuConversionChain.InvalidConversionProbe'],1,{'IMU_AUDIT_INPUT':value})
        log=(out/(name+'.log')).read_text()
        if 'simulator_mavlink.cpp:' not in log or 'outside the range of representable values' not in log:
            raise RuntimeError('Expected production-source conversion diagnostic missing')
    e['tests']={}
    for name in ['range_valid','defect_reproduction','sanitized_range_valid']:
        attrs=ET.parse(out/(name+'.xml')).getroot().attrib
        e['tests'][name]={k:int(attrs[k]) for k in ['tests','failures','errors','disabled']}
        if not e['tests'][name]['tests'] or any(e['tests'][name][k] for k in ['failures','errors','disabled']):
            raise RuntimeError('Empty/failed suite')
    rows=[];areas=[]
    for name in ['range_valid','defect_reproduction']:
        for line in (out/(name+'.log')).read_text().splitlines():
            if line.startswith('IMU_CHAIN_ROW '):rows.append(json.loads(line.split(' ',1)[1]))
            if line.startswith('IMU_CHAIN_AREA '):areas.append(json.loads(line.split(' ',1)[1]))
    (out/'samples.json').write_text(json.dumps(dict(rows=rows,areas=areas),indent=2)+'\n')
    e['source_sha256']={s:hashlib.sha256((REPO/s).read_bytes()).hexdigest() for s in
                        [*SOURCES,str(TEST.relative_to(REPO)),str(Path(__file__).resolve().relative_to(REPO))]}
    e['unique_gtests']=e['tests']['range_valid']['tests']+e['tests']['defect_reproduction']['tests']
    e['expected_ubsan_failures']=len(invalid_inputs);e['invalid_inputs']=invalid_inputs
    e['passed']=True;save()
    files=sorted(p for p in out.iterdir() if p.is_file() and p.name!='artifacts.sha256')
    (out/'artifacts.sha256').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p}\n' for p in files))
    print(json.dumps(dict(tests=e['tests'],expected_ubsan_failures=len(invalid_inputs),areas=areas),indent=2))


if __name__=='__main__':main()
