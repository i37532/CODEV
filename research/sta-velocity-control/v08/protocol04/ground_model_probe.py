"""No-PX4 Gazebo component probe: actual loaded inertials, zero gravity, no motors.

This is NOT a qualified flight model: remove non-audit Iris plugins solely to
avoid waiting for PX4 lockstep. Flight preflight must repeat the actual audit.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
import scenario

parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--library',type=Path,required=True);args=parser.parse_args()
out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
repo=scenario.REPO
plugins=out/'unused-seeded-plugin'
# Only used to write the IMU filename, which is then removed for this fixture.
evidence=dict(success=False,flights=0,px4_started=False,fixture_only=True,probes=[])
try:
    for scene in ('heading','mass'):
        run=out/scene;run.mkdir();job=dict(scene=scene,seed=40201)
        scenario.prepare_model(run,plugins,args.library.resolve(),job)
        sdf=ET.parse(run/'models/iris/iris.sdf');model=sdf.getroot().find('model')
        removed=[]
        for plugin in list(model.findall('plugin')):
            if plugin.get('name')!='v08_force_audit':removed.append(plugin.get('name'));model.remove(plugin)
        sdf.write(run/'models/iris/iris.sdf',encoding='utf-8',xml_declaration=True)
        shutil.copyfile(run/'models/iris/iris.sdf',run/'models/iris/iris-gen.sdf')
        # This harness tests loaded physical inertials only. GPS's sensor
        # plugin teardown requires a complete PX4-connected world lifecycle.
        gps=ET.parse(run/'models/gps/gps.sdf')
        for parent in list(gps.getroot().iter()):
            for node in list(parent):
                if node.tag in ('plugin','sensor'):
                    removed.append('gps::'+node.tag+'::'+node.get('name',''))
                    parent.remove(node)
        gps.write(run/'models/gps/gps.sdf',encoding='utf-8',xml_declaration=True)
        root=ET.Element('sdf',version='1.6');world=ET.SubElement(root,'world',name='v08_inertia_component_probe')
        ET.SubElement(world,'gravity').text='0 0 0'
        physics=ET.SubElement(world,'physics',name='probe',type='ode')
        ET.SubElement(physics,'max_step_size').text='0.004';ET.SubElement(physics,'real_time_update_rate').text='250'
        ET.SubElement(model,'pose').text='0 0 1 0 0 0'
        world.append(model)
        path=run/'probe.world';ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        env=os.environ.copy();env.update(GAZEBO_MASTER_URI='http://127.0.0.1:11355',GAZEBO_MODEL_PATH=str(run/'models')+':'+str(repo/'Tools/sitl_gazebo/models'),GAZEBO_PLUGIN_PATH=str(repo/'build/px4_sitl_default/build_gazebo'))
        argv=['gzserver','--verbose',str(path)]
        with (run/'server.log').open('x') as stream:
            process=subprocess.Popen(argv,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            try:
                deadline=time.monotonic()+25
                while not (run/'loaded_model.csv').exists() and process.poll() is None and time.monotonic()<deadline:time.sleep(.1)
                if process.poll() is not None:raise RuntimeError('Ground probe exited before audit')
                result=scenario.loaded_model(run,job)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid,signal.SIGINT)
                    try:process.wait(timeout=8)
                    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
        evidence['probes'].append(dict(scene=scene,argv=argv,controlled_stop_exit_code=process.returncode,removed_fixture_plugins=removed,loaded_model=result))
        if process.returncode not in (0,-signal.SIGINT):raise RuntimeError('Abnormal ground-probe shutdown')
    evidence['success']=True
finally:(out/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
print(json.dumps(evidence,indent=2))
