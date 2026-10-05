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
import sys
sys.path.insert(0,str(Path('/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/v08/protocol04')))
import scenario

parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--library',type=Path,required=True)
parser.add_argument('--revised-scenario',type=Path)
args=parser.parse_args()
if args.revised_scenario:
    import importlib.util
    spec=importlib.util.spec_from_file_location('revised_scenario',args.revised_scenario)
    scenario=importlib.util.module_from_spec(spec);spec.loader.exec_module(scenario)
out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
repo=scenario.REPO
plugins=out/'unused-seeded-plugin'
# Only used to write the IMU filename, which is then removed for this fixture.
evidence=dict(success=False,flights=0,px4_started=False,fixture_only=True,probes=[])
try:
    for case,scene,route in [('nominal_cli','heading','cli'),('mass_cli','mass','cli'),('nominal_raw','heading','raw'),('mass_raw','mass','raw')]:
        run=out/case;run.mkdir();job=dict(scene=scene,seed=40201)
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
        # Match project startup: create world FIRST, then insert the model via
        # a transport request, unlike the earlier embedded-model fixture.
        path=run/'probe.world';ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        env=os.environ.copy();env.update(GAZEBO_MASTER_URI='http://127.0.0.1:11355',GAZEBO_MODEL_PATH=str(run/'models')+':'+str(repo/'Tools/sitl_gazebo/models'),GAZEBO_PLUGIN_PATH=str(repo/'build/px4_sitl_default/build_gazebo'))
        argv=['gzserver','--verbose',str(path)]
        with (run/'server.log').open('x') as stream:
            process=subprocess.Popen(argv,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            try:
                deadline=time.monotonic()+20
                while time.monotonic()<deadline:
                    ready=subprocess.run(['gz','topic','-l'],env=env,capture_output=True,text=True,timeout=5)
                    if '/gazebo/v08_inertia_component_probe/factory' in ready.stdout:break
                    time.sleep(.1)
                else:raise RuntimeError('No Gazebo factory topic')
                if route=='cli':
                    spawn=['gz','model','--verbose','--spawn-file='+str(run/'models/iris/iris.sdf'),'--model-name=iris','-x','1.01','-y','.98','-z','.83']
                else:
                    message='sdf: '+json.dumps((run/'models/iris/iris.sdf').read_text())+' pose {position {x: 1.01 y: .98 z: .83} orientation {w: 1 x: 0 y: 0 z: 0}}'
                    spawn=['gz','topic','-p','/gazebo/v08_inertia_component_probe/factory','-m',message]
                insertion=subprocess.run(spawn,env=env,capture_output=True,text=True,timeout=15)
                (run/'spawn.json').write_text(json.dumps(dict(argv=spawn,exit_code=insertion.returncode,stdout=insertion.stdout,stderr=insertion.stderr),indent=2)+'\n')
                if insertion.returncode:raise RuntimeError('Spawn command failed')
                deadline=time.monotonic()+25
                while not (run/'loaded_model.csv').exists() and process.poll() is None and time.monotonic()<deadline:time.sleep(.1)
                if process.poll() is not None:raise RuntimeError('Ground probe exited before audit')
                try:result=scenario.loaded_model(run,job);match=True
                except ValueError as exc:result=dict(error=str(exc));match=False
                # Both factory routes quantize in this installed Gazebo.
                # The explicitly revised Q6 model MUST match without tolerance changes.
                if match!=(bool(args.revised_scenario) or scene!='mass'):raise RuntimeError('Unexpected transport precision result: '+case+' '+str(result))
            finally:
                if process.poll() is None:
                    os.killpg(process.pid,signal.SIGINT)
                    try:process.wait(timeout=8)
                    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
        evidence['probes'].append(dict(case=case,scene=scene,route=route,argv=argv,controlled_stop_exit_code=process.returncode,removed_fixture_plugins=removed,loaded_model=result,strict_model_match=match))
        if process.returncode not in (0,-signal.SIGINT):raise RuntimeError('Abnormal ground-probe shutdown')
    evidence['success']=True
finally:(out/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
print(json.dumps(evidence,indent=2))
