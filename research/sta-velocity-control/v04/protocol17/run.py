#!/usr/bin/env python3
from common import REPO
"""Six frozen V04 attempts. Default dry-run; every failed gate stops the batch."""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import time
import xml.etree.ElementTree as ET
import numpy as np
import run_v00 as base
from run_v00 import REPO, ROOTFS, git, save, digest, active_simulators, persisted_bson, encode_bson, check_parameters, parse_params
from world_v00 import snapshot, validate_world
from analyze import analyze, compare, CONFIG
from flight import main as flight
from v04_task04 import check_cli_reference, excitation_class
from common import fresh_seeds
from common import load_protocol, require_authorization
from v04_logcheck07 import validate_receiver_profile
from v04_heading_stream import LiveLog, data, row
from v04_live_clock09 import replay, reference_row
from v04_monitor17 import Checks as LandingChecks


class Checks(LandingChecks):
    """New authorization/world bindings; inherited audited landing and heading guards."""
    def prepare_environment(self, output):
        authorization=require_authorization(self.authorization_token,load_protocol())
        save(output/'authorization.json',authorization)
        model_dir=output/'models/iris'; model_dir.mkdir(parents=True)
        original=REPO/'Tools/sitl_gazebo/models/iris/iris.sdf'
        tree=ET.parse(original); imu=tree.getroot().find("model/plugin[@name='rotors_gazebo_imu_plugin']")
        if imu is None: raise RuntimeError('Missing original IMU plugin')
        imu.set('filename',str(self.plugins/'libm10_imu.so'))
        tree.write(model_dir/'iris.sdf',encoding='utf-8',xml_declaration=True)
        shutil.copyfile(model_dir/'iris.sdf',model_dir/'iris-gen.sdf')
        shutil.copyfile(original.parent/'model.config',model_dir/'model.config')
        (model_dir/'meshes').symlink_to(original.parent/'meshes',target_is_directory=True)
        save(output/'job.json',self.job)
        save(output/'model_manifest.json',dict(original=digest(original),derived=digest(model_dir/'iris.sdf'),
             only_change='IMU library filename: original equations with explicit engine seed and innovation log',
             seed_scope='IMU only; GPS/barometer/magnetometer and host scheduling not independently seeded'))
        return dict(GAZEBO_MODEL_PATH=str(output/'models')+':'+str(REPO/'Tools/sitl_gazebo/models'),
            GAZEBO_PLUGIN_PATH=str(REPO/'build/px4_sitl_default/build_gazebo'),LD_LIBRARY_PATH='',
            M10_IMU_SEED=str(self.job['seed']),M10_IMU_LOG=str(output/'imu_innovations.csv'),PX4_SIM_SPEED_FACTOR='1')

    def __call__(self, phase, cli, topic, output):
        if phase=='preflight': self.logs_before=set(ROOTFS.glob('log/**/*.ulg'))
        if phase!='preflight':
            base.Checks.__call__(self,phase,cli,topic,output)
        else:
            if topic('vehicle_status').get('arming_state')!=1: raise RuntimeError('Must begin disarmed')
            params=parse_params(cli('param','show','-a')); check_parameters(params,self.expected)
            save(output/'runtime_parameters_start.json',params)
            console=(output/'console.log').read_text()
            if 'Using: '+str(output/'models/iris/iris.sdf') not in console: raise RuntimeError('Derived Iris not loaded')
            if 'M10_IMU_SEED_ACCEPTED='+str(self.job['seed']) not in console: raise RuntimeError('Seed not consumed')
            launcher_pid=json.loads((output/'result.json').read_text())['launcher_pid']
            world=REPO/'sitl/worlds/empty_grey.world'; evidence=snapshot(launcher_pid,world)
            save(output/'world_process.json',evidence)
            validate_world(evidence['servers'],launcher_pid,evidence['launcher_sid'],world,'http://127.0.0.1:11345')
            if evidence['world_sha256']!=json.loads((CONFIG/'frozen.json').read_text())['assets'][str(world.relative_to(REPO))]:
                raise RuntimeError('Frozen world changed')
            (output/'uorb_start.txt').write_text(cli('uorb','status'))
            cli('logger','stop'); time.sleep(1.1); cli('logger','start','-b','256','-r','1000','-t','-f')
        if phase in ('preflight','hover','disarmed'): self.selection(topic('velocity_ctrl_selection'))



def noise_prefix(run):
    data=np.genfromtxt(run/'imu_innovations.csv',delimiter=',',names=True,max_rows=5000)
    if len(data)!=5000: raise RuntimeError('Missing seeded innovations')
    x=np.column_stack([data[name] for name in ('dt','gx','gy','gz','ax','ay','az')])
    if not np.all(np.isfinite(x)): raise RuntimeError('Invalid seeded innovations')
    return x


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--execute',action='store_true')
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--source-head',required=True)
    parser.add_argument('--authorization',default='')
    args=parser.parse_args(); protocol=load_protocol()
    frozen=json.loads((CONFIG/'frozen.json').read_text()); jobs=protocol['jobs']
    print(json.dumps(jobs,indent=2),flush=True)
    if not args.execute: print('DRY RUN: no process, file or parameter changes'); return
    authorization=require_authorization(args.authorization,protocol)
    if len(jobs)!=6 or protocol['maximum_attempts']!=6: raise RuntimeError('Wrong frozen budget')
    if git('branch','--show-current')!='research/sta-velocity-control' or git('rev-parse','HEAD')!=args.source_head: raise RuntimeError('Wrong branch/HEAD')
    if git('status','--porcelain') or git('submodule','foreach','--recursive','--quiet','git status --porcelain'): raise RuntimeError('Dirty source')
    if any(s[:1] in ('+','-','U') for s in git('submodule','status','--recursive').splitlines()): raise RuntimeError('Submodule mismatch')
    if active_simulators(): raise RuntimeError('Conflicting simulator')
    if shutil.disk_usage(ROOTFS).free<10*1024**3: raise RuntimeError('Insufficient space')
    if (ROOTFS/'etc/logging/logger_topics.txt').exists(): raise RuntimeError('Custom logger profile')
    if any((REPO/'Tools/sitl_gazebo/models/iris').glob('*-gen.sdf')): raise RuntimeError('Unexpected original model override')
    audit=fresh_seeds()
    if not audit['accepted']: raise RuntimeError('Seed history changed; no launch')
    for port in (14550,11345):
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM if port==14550 else socket.SOCK_STREAM) as s: s.bind(('127.0.0.1',port))
    for rel,expected in frozen['assets'].items():
        if digest(REPO/rel)!=expected: raise RuntimeError('Frozen asset changed: '+rel)
    validate_receiver_profile()  # pinned compiled receiver reference before any launch
    plugins=Path(protocol['plugins'])
    for path,expected in json.loads((plugins/'manifest.json').read_text()).items():
        if digest(Path(path))!=expected: raise RuntimeError('Plugin dependency changed')
    out=args.output.resolve()
    if out!=Path(protocol['artifacts']['new_run_root']): raise RuntimeError('Wrong frozen output root')
    if not protocol['execution_ready']: raise RuntimeError('Protocol not ready')
    version=(REPO/'build/px4_sitl_default/src/lib/version/build_git_version.h').read_text()
    if args.source_head not in version: raise RuntimeError('Firmware not built at source commit')
    out.mkdir(parents=True,exist_ok=False)
    save(out/'seed_audit_before_launch.json',audit)
    save(out/'authorization.json',authorization)
    param=ROOTFS/'eeprom/parameters_10016'; original=param.read_bytes()
    (out/'original_parameters.bson').write_bytes(original); values=persisted_bson(original)
    defaults=json.loads((REPO/'build/px4_sitl_default/parameters.json').read_text())['parameters']
    check_parameters({**{p['name']:p['default'] for p in defaults},**values},frozen['control_parameters'])
    profile=int(values.get('SDLOG_PROFILE',131))|16|1024
    ledger=dict(source_head=args.source_head,planned=6,attempts=[],pairs=[],success=False,
        firmware_sha256=digest(REPO/'build/px4_sitl_default/bin/px4'),original_parameter_sha256=digest(param),applied_profile=profile)
    save(out/'ledger.json',ledger); results={}; prefixes={}
    try:
        for index,job in enumerate(jobs,1):
            if active_simulators() or git('status','--porcelain') or git('rev-parse','HEAD')!=args.source_head: raise RuntimeError('Changed state before attempt')
            if param.read_bytes()!=original: raise RuntimeError('Parameters not restored')
            p={**protocol,'startup_overrides':{**protocol['startup_overrides'],**job['parameters']}}
            param.write_bytes(encode_bson({**values,**p['startup_overrides'],'SDLOG_PROFILE':profile},{v['name']:v['type'] for v in defaults}))
            run=out/f'run{index:02d}'; item=dict(attempt=index,job=job,directory=str(run),status='running')
            ledger['attempts'].append(item); save(out/'ledger.json',ledger); old=sys.argv
            try:
                sys.argv=[__file__,'--output',str(run)]
                expected={**frozen['control_parameters'],**p['startup_overrides'],'SYS_AUTOSTART':10016,'SDLOG_PROFILE':profile}
                checks=Checks(p,expected,job,plugins); checks.execution_permitted=True; checks.authorization_token=args.authorization
                flight(checks=checks,scenario_path=CONFIG/'execution.json')
                if digest(REPO/'build/px4_sitl_default/bin/px4')!=ledger['firmware_sha256']: raise RuntimeError('Changed firmware')
                metrics=analyze(run,p,job)
                if not metrics['accepted']: raise RuntimeError('ULog acceptance failed')
                prefix=noise_prefix(run); key=(job['seed'],job['mode']); prefixes[key]=prefix; results[key]=metrics
                item['status']='accepted'
                if (job['seed'],0) in results and (job['seed'],1) in results:
                    pair=compare(results[(job['seed'],0)],results[(job['seed'],1)])
                    pair['imu_prefix_max_difference']=float(np.max(np.abs(prefixes[(job['seed'],0)]-prefixes[(job['seed'],1)])))
                    pair['paired_noise']=pair['imu_prefix_max_difference']<1e-10
                    pair['accepted']=pair['accepted'] and pair['paired_noise']; ledger['pairs'].append(pair)
                    if not pair['accepted']: raise RuntimeError('Paired development gate failed')
                for (seed,mode),prior in prefixes.items():
                    if seed!=job['seed'] and np.max(np.abs(prior-prefix))<=1e-6: raise RuntimeError('Seeds not distinct')
            except BaseException as exc:
                item.update(status='failed',error=repr(exc)); raise
            finally:
                sys.argv=old
                if not active_simulators(): param.write_bytes(original)
                save(out/'ledger.json',ledger)
            if param.read_bytes()!=original: raise RuntimeError('Parameter restoration failed')
        ledger['success']=True
    finally:
        if not active_simulators(): param.write_bytes(original)
        ledger['parameter_restore_exact']=param.read_bytes()==original
        ledger['remaining_simulators']=active_simulators(); save(out/'ledger.json',ledger)
    if not ledger['parameter_restore_exact'] or ledger['remaining_simulators']:
        raise RuntimeError('Cleanup or full parameter restoration failed')


if __name__=='__main__': main()
