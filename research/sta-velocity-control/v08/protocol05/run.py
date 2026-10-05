"""Scoped pilot model adapter; unchanged production firmware and safety gates."""
import common
import task  # the bounded exact attitude evidence, frozen after validation
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET
import scenario
import analyze as pilot_analysis  # bind local pilot whitelist before TRAIN path
sys.path.insert(0,str(common.TRAIN))
spec=importlib.util.spec_from_file_location('v08_pilot_training_runtime',common.TRAIN/'run.py')
runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)
OriginalChecks=runtime.Checks

class Checks(OriginalChecks):
    def prepare_environment(self,output):
        library=Path(common.design()['force_library'])
        if common.fingerprint(library)!=common.design()['force_library_sha256']:raise RuntimeError('Pilot library changed')
        env=super().prepare_environment(output)
        iris,gps=scenario.expected_trees(output,self.plugins,library,self.job)
        ET.ElementTree(iris).write(output/'models/iris/iris.sdf',encoding='utf-8',xml_declaration=True)
        shutil.copyfile(output/'models/iris/iris.sdf',output/'models/iris/iris-gen.sdf')
        folder=output/'models/gps';folder.mkdir(exist_ok=False)
        ET.ElementTree(gps).write(folder/'gps.sdf',encoding='utf-8',xml_declaration=True)
        shutil.copyfile(common.REPO/'Tools/sitl_gazebo/models/gps/model.config',folder/'model.config')
        evidence=scenario.verify_model(output,self.plugins,library,self.job)
        runtime.save(output/'pilot_model_manifest.json',evidence)
        manifest=json.loads((output/'model_manifest.json').read_text())
        manifest.update(derived=evidence['iris_sha256'],derived_gps=evidence['gps_sha256'],
            only_change='Qualified contact and seeded IMU; scoped audit plugin and pinned GPS; mass1.10 with explicit inertia Q6(1.10 I)',
            scene=self.job['scene'],density_scale=evidence['density_scale'],
            force_library=str(library),force_library_sha256=common.fingerprint(library))
        runtime.save(output/'model_manifest.json',manifest)
        self.force_started=False
        return env

    def __call__(self,phase,cli,topic,output):
        super().__call__(phase,cli,topic,output)
        if phase=='preflight':runtime.save(output/'loaded_model_preflight.json',scenario.loaded_model(output,self.job))

    def monitor(self,phase,cli,topic,output,state):
        super().monitor(phase,cli,topic,output,state)
        d=self.latest_diagnostic
        if phase=='hover' and d['excitation_time']>=0 and not self.force_started:
            origin=scenario.trigger_origin(d)
            receipt=dict(origin_sim_s=origin,diagnostic={k:d[k] for k in ('timestamp','timestamp_sample','excitation_time')})
            runtime.save(output/'force_trigger_origin.json',receipt)
            temporary=output/'force.trigger.tmp'
            with temporary.open('x') as stream:stream.write(format(origin,'.17g')+'\n')
            temporary.rename(output/'force.trigger')
            self.force_started=True

runtime.Checks=Checks
base_analyze=runtime.analyze
accepted={}

def analyze(run,protocol,job):
    result=base_analyze(run,protocol,job)
    if result['accepted']:
        key=(job['scene'],job['seed']);group=accepted.setdefault(key,{})
        if job['mode'] in group:raise RuntimeError('Repeated pilot mode')
        group[job['mode']]=result
        if set(group)=={0,1}:
            pair=runtime.compare(group[0],group[1]);pair['scene']=job['scene']
            runtime.save(run/'pilot_pair.json',pair)
            if not pair['accepted']:raise RuntimeError('Pilot paired development gate failed')
    return result

runtime.analyze=analyze
if __name__=='__main__':runtime.main()
