"""Actual uORB latest-value loss reproduction; no flight or production changes."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import xml.etree.ElementTree as ET

REPO=Path(__file__).resolve().parents[4]
BUILD=REPO/'build/px4_sitl_test'
SOURCES=['src/modules/simulator/simulator_mavlink.cpp','src/lib/drivers/accelerometer/PX4Accelerometer.cpp','src/modules/sensors/vehicle_imu/VehicleIMU.cpp']

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);out=p.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    evidence=dict(success=False,new_flights=0,commands=[],head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip())
    def run(name,argv):
        with (out/(name+'.log')).open('w') as f:r=subprocess.run(argv,cwd=BUILD,stdout=f,stderr=subprocess.STDOUT,timeout=300)
        evidence['commands'].append(dict(name=name,argv=argv,exit_code=r.returncode))
        (out/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n');print(name,r.returncode,flush=True)
        if r.returncode:raise RuntimeError(name)
    db=json.loads((BUILD/'compile_commands.json').read_text())
    def compile(name,source,template,extra=()):
        entry=next(x for x in db if x['file'].endswith('/'+template));argv=shlex.split(entry['command'])
        obj=out/(name+'.o');argv[argv.index('-c')+1]=str(source);argv[argv.index('-o')+1]=str(obj);argv+=list(extra)
        run(name,argv);return str(obj)
    source=Path(__file__).with_name('LocalPositionLossTest.cpp')
    harness=compile('harness',source,'VelocityModuleTest.cpp',['-fno-access-control','-I'+str(REPO/'mavlink/include/mavlink'),'-I'+str(REPO/'src/modules/sensors'),'-Wno-address-of-packed-member'])
    objects=[compile(Path(s).stem,REPO/s,Path(s).name) for s in SOURCES]
    commands=subprocess.check_output(['ninja','-t','commands','functional-VelocityModule'],cwd=BUILD,text=True)
    line=next(v for v in reversed(commands.splitlines()) if ' -o functional-VelocityModule ' in v)
    link=[x for x in shlex.split(line.split(' && ')[1]) if x not in ('-rdynamic','-Wl,--export-dynamic') and not x.endswith('VelocityModuleTest.cpp.o')]
    binary=out/'local_position_loss';link[link.index('-o')+1]=str(binary)
    index=next(i for i,x in enumerate(link) if x.endswith('.a'))
    link[index:index]=[harness,*objects,'-Wl,--start-group']
    link+=['src/lib/drivers/gyroscope/libdrivers_gyroscope.a','src/lib/drivers/magnetometer/libdrivers_magnetometer.a','src/lib/drivers/barometer/libdrivers_barometer.a','src/lib/sensor_calibration/libsensor_calibration.a','src/lib/conversion/libconversion.a','-Wl,--end-group','-Wl,--gc-sections']
    run('link',link)
    run('test',[str(binary),'--gtest_filter=ImuConversionChain.LatestValueSubscriberCanMissConsumedPosition:ImuConversionChain.PromptSubscriberRetainsEachPosition','--gtest_output=xml:'+str(out/'test.xml')])
    a=ET.parse(out/'test.xml').getroot().attrib
    evidence['tests']={k:int(a[k]) for k in ('tests','failures','errors','disabled')}
    assert evidence['tests']==dict(tests=2,failures=0,errors=0,disabled=0)
    evidence['success']=True;(out/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')

if __name__=='__main__':main()
