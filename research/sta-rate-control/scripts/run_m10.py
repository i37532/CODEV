#!/usr/bin/env python3
"""One isolated research flight, original launcher, no competing setpoint source.

M10_JOB JSON and M10_PLUGINS paths required. The output directory must be new.
Formal jobs require a clean repository; development jobs explicitly record dirty
source via the inherited runner and a full tracked/untracked research snapshot.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from run_m00 import main, save, digest, REPO
from run_m04 import Checks as Base
from m10_design import scenario
import numpy as np


def trigger_origin(diagnostic):
    elapsed=diagnostic.get('research_elapsed',-1)
    stamp=diagnostic.get('timestamp_sample',float('nan'))
    if not np.isfinite(stamp) or stamp<=0 or not 0<=elapsed<1.5:
        raise RuntimeError('Research trigger delivery too late or inactive')
    origin=stamp*1e-6-elapsed
    if origin<0:raise RuntimeError('Invalid research trigger origin')
    return origin


def scale_inertia(tree,scale):
    if not np.isfinite(scale) or scale<=0:raise ValueError('Invalid inertia multiplier')
    for inertia in tree.findall('.//link/inertial/inertia'):
        for entry in inertia:
            entry.text=format(float(entry.text)*scale,'.17g')
        def v(key):return float(inertia.find(key).text)
        matrix=np.array([[v('ixx'),v('ixy'),v('ixz')],[v('ixy'),v('iyy'),v('iyz')],[v('ixz'),v('iyz'),v('izz')]])
        moments=np.linalg.eigvalsh(matrix)
        if moments[0]<=0 or moments[2]>moments[0]+moments[1]+1e-12:
            raise ValueError('Nonphysical principal inertia')


def check_param_show(raw,expected):
    observed={}
    for line in raw.splitlines():
        match=re.search(r'\b([A-Z][A-Z0-9_]+)\s+\[[^\]]+\]\s*:\s*([-+0-9.eE]+)\s*$',line)
        if match:observed[match.group(1)]=float(match.group(2))
    for name,value in expected.items():
        # PX4 CLI prints float parameters with 4 decimal places; ULog is checked
        # exactly after flight. This is an additional pre-arm coarse guard.
        if name not in observed or abs(observed[name]-value)>5.1e-5:
            raise RuntimeError('Frozen background parameter differs before arm: '+name)


class Checks(Base):
    stage='m08'
    prefix='M10'
    allowed_modes=(0,1,2)
    config_name='iris_esta_rpy.json'
    pid_parameters_modified=True  # explicitly load PID P/I/D/K/FF in every job

    def __init__(self):
        self.job=json.loads(Path(os.environ['M10_JOB']).read_text())
        os.environ['M10_MODE']=str(self.job['mode'])
        super().__init__()
        self.protocol.update(milestone='M10',version=1,
            analysis=dict(protocol='research/sta-rate-control/m10/PROTOCOL_CN.md',
                          ratio='No M08 1.25 performance filter; fixed sensor-time 36 s metrics',
                          scope='Paper comparison, small Iris SITL rate excitation, not hardware'),
            required=dict(nan=0,fallback=0,abort=0,failsafe=0,landed_disarmed=True))
        self.protocol['limits'].pop('rmse_ratio_max',None)
        self.config.update(self.job['parameters'])
        self.setting=scenario(self.job['scene'],self.job['seed'])
        self.config['MC_RTC_DIV']=self.setting['div']
        self.axes=self.config['MC_STA_AXES']
        self.simulation_speed=float(os.environ.get('M10_SPEED','5'))
        self.plugins=Path(os.environ['M10_PLUGINS']).resolve()
        for path,expected in json.loads((self.plugins/'manifest.json').read_text()).items():
            if digest(Path(path))!=expected:raise RuntimeError('Plugin dependency changed: '+path)
        self.last_trigger=False
        if self.job.get('formal'):
            if self.simulation_speed!=self.job['simulation_speed_requested']:raise RuntimeError('Changed frozen lockstep speed request')
            if len(self.job.get('fixed_parameters',{}))<100:raise RuntimeError('Formal job lacks frozen full parameter baseline')
            status=subprocess.check_output(['git','status','--porcelain'],cwd=REPO,text=True)
            if status.strip():raise RuntimeError('Formal experiment requires clean source')
            head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
            if head!=self.job['frozen_head']:raise RuntimeError('Wrong formal source commit')

    def prepare_environment(self, output):
        model_dir=output/'models/iris';model_dir.mkdir(parents=True)
        root=ET.parse(REPO/'Tools/sitl_gazebo/models/iris/iris.sdf')
        model=root.getroot().find('model')
        scale_inertia(root.getroot(),self.setting['inertia_scale'])
        # The GPS is an included model with its own 15 g link, not a direct Iris
        # child. Include it in the stated per-link inertia variation as well.
        gps_dir=output/'models/gps';gps_dir.mkdir()
        gps=ET.parse(REPO/'Tools/sitl_gazebo/models/gps/gps.sdf')
        scale_inertia(gps.getroot(),self.setting['inertia_scale'])
        gps.write(gps_dir/'gps.sdf',encoding='utf-8',xml_declaration=True)
        shutil.copyfile(REPO/'Tools/sitl_gazebo/models/gps/model.config',gps_dir/'model.config')
        imu=model.find("plugin[@name='rotors_gazebo_imu_plugin']")
        imu.set('filename',str(self.plugins/'libm10_imu.so'))
        noise=imu.find('gyroscopeNoiseDensity')
        noise.text=format(float(noise.text)*self.setting['gyro_density_scale'],'.17g')
        torque=ET.SubElement(model,'plugin',name='m10_torque',filename=str(self.plugins/'libm10_torque.so'))
        fields=dict(trigger=str(output/'torque.trigger'),log=str(output/'torque.csv'),scale=self.setting['torque_scale'])
        fields.update({f'phase{i}':v for i,v in enumerate(self.setting['torque_phases'])})
        for k,v in fields.items():ET.SubElement(torque,k).text=str(v)
        root.write(model_dir/'iris.sdf',encoding='utf-8',xml_declaration=True)
        # The stock launcher may choose iris-gen.sdf based on the upstream dir.
        shutil.copyfile(model_dir/'iris.sdf',model_dir/'iris-gen.sdf')
        shutil.copyfile(REPO/'Tools/sitl_gazebo/models/iris/model.config',model_dir/'model.config')
        (model_dir/'meshes').symlink_to(REPO/'Tools/sitl_gazebo/models/iris/meshes',target_is_directory=True)
        save(output/'m10_job.json',self.job)
        save(output/'m10_environment.json',dict(settings=self.setting,
            model_sha256=digest(model_dir/'iris.sdf'),gps_model_sha256=digest(gps_dir/'gps.sdf'),
            plugins=json.loads((self.plugins/'manifest.json').read_text()),
            random_scope='IMU engine explicit seed; torque PCG64 phases. GPS/mag/baro original default engines, NOT reseeded.',
            mass_change=False,world=str(REPO/'sitl/worlds/empty_grey.world')))
        # Source snapshot includes untracked M10 work during training/pilot.
        for folder in (() if self.job.get('formal') else ('scripts','m10')):
            for src in (REPO/'research/sta-rate-control'/folder).rglob('*'):
                if src.is_file() and '__pycache__' not in str(src):
                    dest=output/'source'/src.relative_to(REPO)
                    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
        return dict(GAZEBO_MODEL_PATH=str(output/'models')+':'+str(REPO/'Tools/sitl_gazebo/models'),
                    GAZEBO_PLUGIN_PATH=str(REPO/'build/px4_sitl_default/build_gazebo'),
                    M10_IMU_SEED=str(self.setting['imu_seed']),M10_IMU_LOG=str(output/'imu_innovations.csv'))

    def __call__(self,phase,cli,topic,output):
        super().__call__(phase,cli,topic,output)
        if phase=='preflight':
            if self.job.get('fixed_parameters'):
                raw=cli('param','show','-a')
                (output/'m10_frozen_preflight_params.txt').write_text(raw)
                check_param_show(raw,self.job['fixed_parameters'])
            marker='M10_IMU_SEED_ACCEPTED='+str(self.setting['imu_seed'])
            if marker not in (output/'console.log').read_text():raise RuntimeError('Seeded IMU not loaded')
            if str(output/'models/iris/iris.sdf') not in (output/'console.log').read_text():
                raise RuntimeError('Research model override not used')
            deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                d=topic('sta_rate_ctrl_status')
                if d.get('div_eff')==self.setting['div'] and d.get('div_ok'):break
                time.sleep(.1)
            else:raise RuntimeError('Divisor not accepted')
            save(output/'m10_preflight.json',d)
        if phase=='disarmed':
            cli('logger','stop');self.flight_logger_stopped=True

    def monitor(self,phase,cli,topic,output,state):
        # Consecutive CLI polls may observe the same lockstep instant (notably
        # first poll immediately after commander takeoff). Age against simulator
        # time and wall timeouts remain enforced by Base/main. Equality of two
        # sequence reads alone is not a sensor stall.
        self.last_seq=None
        super().monitor(phase,cli,topic,output,state)
        if self.triggered and not self.last_trigger:
            # param set acknowledgement precedes attitude-loop consumption.
            # Wait for the logged active stimulus, not merely CLI return.
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                diagnostic=topic('sta_rate_ctrl_status')
                if diagnostic.get('research_elapsed',-1)>=0:break
                time.sleep(.005)
            else:raise RuntimeError('Research trigger delivery inactive timeout')
            origin=trigger_origin(diagnostic)
            save(output/'m10_trigger_origin.json',dict(diagnostic=diagnostic,origin_sim_s=origin))
            pending=output/'torque.trigger.pending'
            pending.write_text(format(origin,'.17g')+'\n')
            pending.replace(output/'torque.trigger')
            self.last_trigger=True


if __name__=='__main__':main(checks=Checks(),scenario_path=Path(__file__))
