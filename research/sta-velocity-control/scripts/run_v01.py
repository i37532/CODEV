#!/usr/bin/env python3
"""Exactly one PID smoke attempt, dry-run by default; reuse the project launcher."""
import argparse
import json
import shutil
import socket
import sys
from pathlib import Path

import run_v00 as base
from run_v00 import REPO, ROOTFS, git, save, digest, active_simulators, check_parameters, parse_params, encode_bson, persisted_bson
from analyze_v01 import CONFIG, analyze


class Checks(base.Checks):
    def __call__(self, phase, cli, topic, output):
        super().__call__(phase,cli,topic,output)
        if phase in ('preflight','hover','disarmed'):
            d=topic('velocity_ctrl_selection')
            self.selection(d)
            save(output/('selection_'+phase+'.json'),d)

    @staticmethod
    def selection(d):
        if 'timestamp' not in d:
            raise RuntimeError('Missing velocity selector')
        for key in ('requested_mode','requested_axes','effective_mode','effective_axes','pending','reject'):
            if d.get(key)!=0:
                raise RuntimeError('Unexpected velocity selector '+key)

    def monitor(self, phase, cli, topic, output, state):
        super().monitor(phase,cli,topic,output,state)
        d=topic('velocity_ctrl_selection')
        self.selection(d)
        if abs(state['position'].get('timestamp',0)-d['timestamp'])>1e6:
            raise RuntimeError('Stale velocity selector')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--execute',action='store_true');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source-head',required=True)
    args=p.parse_args()
    protocol=json.loads((CONFIG/'protocol.json').read_text())
    frozen=json.loads((CONFIG/'frozen.json').read_text())
    print(json.dumps(protocol,ensure_ascii=False,indent=2),flush=True)
    if not args.execute:
        print('DRY RUN: no simulator, file or parameter changes');return
    if protocol['maximum_attempts']!=1 or protocol['attempt_order']!=['run01']:
        raise RuntimeError('V01 permits exactly one attempt')
    if git('branch','--show-current')!='research/sta-velocity-control' or git('rev-parse','HEAD')!=args.source_head:
        raise RuntimeError('Wrong branch/HEAD')
    if git('status','--porcelain') or git('submodule','foreach','--recursive','--quiet','git status --porcelain'):
        raise RuntimeError('Dirty source/submodules')
    if any(line[:1] in ('+','-','U') for line in git('submodule','status','--recursive').splitlines()):
        raise RuntimeError('Submodule revision mismatch')
    if active_simulators(): raise RuntimeError('Existing simulator/GCS')
    if shutil.disk_usage(ROOTFS).free<10*1024**3: raise RuntimeError('Need 10 GiB free')
    if (ROOTFS/'etc/logging/logger_topics.txt').exists(): raise RuntimeError('Custom logger profile')
    if any((REPO/'Tools/sitl_gazebo/models/iris').glob('*-gen.sdf')): raise RuntimeError('Generated model override')
    for port in (14550,11345):
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM if port==14550 else socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1',port))
    for rel,h in frozen['assets'].items():
        if digest(REPO/rel)!=h: raise RuntimeError('Frozen asset mismatch: '+rel)
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    parameter_file=ROOTFS/'eeprom/parameters_10016'
    original=parameter_file.read_bytes()
    (out/'original_parameters_10016.bson').write_bytes(original)
    values=persisted_bson(original)
    defaults=json.loads((REPO/'build/px4_sitl_default/parameters.json').read_text())['parameters']
    check_parameters({**{v['name']:v['default'] for v in defaults},**values},frozen['control_parameters'])
    profile=int(values.get('SDLOG_PROFILE',131))|16
    overrides={**values,**protocol['startup_overrides'],'SDLOG_PROFILE':profile}
    baseline=encode_bson(overrides,{v['name']:v['type'] for v in defaults})
    ledger=dict(source_head=args.source_head,planned=1,attempts=[],success=False,
                firmware_sha256=digest(REPO/'build/px4_sitl_default/bin/px4'),
                original_parameter_sha256=digest(parameter_file),applied_profile=profile)
    save(out/'ledger.json',ledger)
    old_argv=sys.argv
    try:
        parameter_file.write_bytes(baseline)
        run=out/'run01'
        attempt=dict(attempt=1,seed=None,directory=str(run),status='running')
        ledger['attempts'].append(attempt);save(out/'ledger.json',ledger)
        expected={**frozen['control_parameters'],**protocol['startup_overrides'],'SYS_AUTOSTART':10016,'SDLOG_PROFILE':profile}
        base.CONFIG=CONFIG  # Reused world check reads this exact V01 frozen world hash.
        sys.argv=[__file__,'--output',str(run)]
        base.legacy_run(checks=Checks(protocol,expected),scenario_path=CONFIG/'protocol.json')
        if digest(REPO/'build/px4_sitl_default/bin/px4')!=ledger['firmware_sha256']:
            raise RuntimeError('Launcher changed frozen firmware')
        metrics=analyze(run,protocol)
        if not metrics['accepted']: raise RuntimeError('ULog validation rejected')
        attempt['status']='accepted';ledger['success']=True
    except BaseException as exc:
        if ledger['attempts']:
            ledger['attempts'][-1].update(status='failed',error=repr(exc))
        raise
    finally:
        sys.argv=old_argv
        if not active_simulators(): parameter_file.write_bytes(original)
        ledger['parameter_restore_exact']=parameter_file.read_bytes()==original
        ledger['remaining_simulators']=active_simulators()
        save(out/'ledger.json',ledger)
    if not ledger['parameter_restore_exact'] or ledger['remaining_simulators']:
        raise RuntimeError('Cleanup or parameter restoration failed')


if __name__=='__main__': main()
