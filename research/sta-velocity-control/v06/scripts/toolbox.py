"""Velocity-only convenience commands. No default flight, independent of rate scripts."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
spec=importlib.util.spec_from_file_location('v06_local_io',REPO/'sim_scripts/_internal/toolbox.py')
rate_io=importlib.util.module_from_spec(spec); spec.loader.exec_module(rate_io)
sys.path.insert(0,str(HERE.parent/'protocol01'))
from common import load_protocol, CONFIG, fingerprint
STATE=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260928/V06/manual')
RATE=dict(MC_RTC_MODE=0,MC_STA_AXES=0,MC_RTC_DIV=1,MC_RATT_TEST=0,MC_STA_TKO_MGT=0)

def config(mode):
    p=load_protocol()
    return {**p['startup_overrides'],**p['candidate'],**RATE,'MPC_VCT_TEST':0,'MPC_USE_HTE':1,
            'MPC_VC_MODE':mode,'MPC_VC_AXES':7*mode}

def verify(mode):
    rate_io.ground()
    for k,v in RATE.items():
        if rate_io.parameter(k)!=v: raise RuntimeError('Rate parameter mismatch '+k)
    r=rate_io.topic('sta_rate_ctrl_status'); v=rate_io.topic('velocity_ctrl_selection')
    for d in (r,v):
        if d.get('pending') or d.get('reject') or d.get('fault'): raise RuntimeError('Pending/rejected/faulted selection')
    if r.get('effective_mode')!=0 or r.get('effective_axes')!=0: raise RuntimeError('Rate not actual PID')
    if v.get('effective_mode')!=mode or v.get('effective_axes')!=7*mode: raise RuntimeError('Velocity mode not effective')

def apply(mode):
    rate_io.ground()
    if not (STATE/'session.json').is_file(): raise RuntimeError('先用本目录 start.sh 启动；不接管其他会话')
    record=json.loads((STATE/'session.json').read_text())
    if not Path('/proc/'+str(record['owner'])).exists(): raise RuntimeError('启动会话已结束，拒绝陈旧标记')
    before={k:rate_io.parameter(k) for k in config(mode)}
    try:
        rate_io.set_parameter('MPC_VC_MODE',0); rate_io.set_parameter('MPC_VC_AXES',0)
        for k,v in config(mode).items():
            if k not in ('MPC_VC_MODE','MPC_VC_AXES'): rate_io.set_parameter(k,v)
        rate_io.set_parameter('MPC_VC_AXES',mode*7); rate_io.set_parameter('MPC_VC_MODE',mode)
        time.sleep(.3); verify(mode)
        print('已核验：速度 '+('XYZ ESTA' if mode else 'PID')+'；角速度 PID；任务 TEST=0。')
    except BaseException:
        rate_io.ground()
        for k,v in before.items(): rate_io.set_parameter(k,v)
        raise

def start():
    rate_io.no_simulator(include_qgc=True)
    from run_v00 import ROOTFS,encode_bson,persisted_bson
    STATE.mkdir(parents=True,exist_ok=True)
    if (STATE/'session.json').exists(): raise RuntimeError('已有会话/未确认恢复记录，拒绝覆盖')
    path=ROOTFS/'eeprom/parameters_10016'; original=path.read_bytes()
    stamp=str(time.time_ns()); backup=STATE/(stamp+'.bson'); backup.write_bytes(original)
    defaults=json.loads((REPO/'build/px4_sitl_default/parameters.json').read_text())['parameters']
    (STATE/'session.json').write_text(json.dumps(dict(owner=os.getpid(),backup=str(backup),sha256=hashlib.sha256(original).hexdigest())))
    try:
        path.write_bytes(encode_bson({**persisted_bson(original),**config(0)},{p['name']:p['type'] for p in defaults}))
        print('仅打开仿真，不自动解锁。退出请在 PX4 控制台 shutdown；退出后自动恢复全部 EEPROM。',flush=True)
        subprocess.run(['./sitl/run.sh','--backend','gazebo','--model','iris'],cwd=REPO,env=rate_io.environment(),check=True)
    finally:
        if not rate_io.processes({'px4','gzserver','gazebo'}):
            path.write_bytes(original)
            if path.read_bytes()!=backup.read_bytes(): raise RuntimeError('EEPROM恢复失败，保留会话')
            (STATE/'session.json').rename(STATE/(stamp+'-restored.json'))
        else: print('进程未完全退出：保留备份与会话，不能自动覆盖运行中参数。',file=sys.stderr)

def main():
    p=argparse.ArgumentParser(); p.add_argument('action',choices=['start','switch','fly'])
    p.add_argument('choice',nargs='?'); p.add_argument('--execute',action='store_true')
    p.add_argument('--authorization',default=''); p.add_argument('--source-head',default='')
    a=p.parse_args()
    if a.action=='switch' and a.choice not in ('pid','esta'): p.error('switch pid|esta')
    if a.action=='fly' and a.choice not in ('hover','figure8','heading','all'): p.error('fly hover|figure8|heading|all')
    print('仅 Iris SITL；正式任务为 PID 对 XYZ速度ESTA；角速度始终PID。',flush=True)
    if a.action=='fly':
        protocol=load_protocol()
        argv=[sys.executable,str(CONFIG/'run.py'),'--task',a.choice,'--output',protocol['artifacts']['new_run_root'],
              '--source-head',a.source_head or subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()]
        if a.execute: argv+=['--execute','--authorization',a.authorization]
        subprocess.run(argv,cwd=REPO,env=rate_io.environment(),check=True); return
    print(json.dumps(config(int(a.choice=='esta')),indent=2))
    if not a.execute: print('预检/清单模式：未启动、未改参数、未飞行。加 --execute 明确执行。'); return
    if a.action=='start': start()
    else: apply(int(a.choice=='esta'))

if __name__=='__main__': main()
