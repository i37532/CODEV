#!/usr/bin/env python3
"""Two real disarmed Iris boots: save/restart/load/mask transitions and restore.

Never arms or publishes a setpoint. All CLI outputs and startup EEPROM retained.
"""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
from run_m00 import REPO, BIN, ROOTFS, active_simulators, digest, save
from run_m03 import Checks
from run_m04 import arrays


def main(output):
    if active_simulators(): raise RuntimeError('Existing simulator: '+str(active_simulators()))
    output.mkdir(parents=True,exist_ok=False)
    config=json.loads((REPO/'research/sta-rate-control/m06/iris_esta_rpy.json').read_text())
    eeprom=ROOTFS/'eeprom/parameters_10016'
    if eeprom.exists(): (output/'startup_parameters.bson').write_bytes(eeprom.read_bytes())
    original={}; proc=None; console=None
    result=dict(success=False,events=[],binary_sha256=digest(BIN/'px4'),source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip())
    (output/'tracked_diff.patch').write_bytes(subprocess.check_output(['git','diff','HEAD'],cwd=REPO))

    def cli(module,*args):
        cmd=[str(BIN/('px4-'+module)),*map(str,args)]
        p=subprocess.run(cmd,cwd=ROOTFS,text=True,capture_output=True,timeout=10)
        with (output/'commands.jsonl').open('a') as f:
            f.write(json.dumps(dict(cmd=cmd,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))+'\n')
        if p.returncode: raise RuntimeError('CLI failed '+str(cmd)+p.stdout+p.stderr)
        return p.stdout

    def disarmed():
        raw=cli('listener','vehicle_status','-n','1')
        if not re.search(r'arming_state:\s+1\b',raw): raise RuntimeError('Disarmed state required')

    def accepted(mode,axes):
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            disarmed(); raw=cli('listener','sta_rate_ctrl_status','-n','1')
            if re.search(r'effective_mode:\s+'+str(mode)+r'\b',raw) and re.search(r'effective_axes:\s+'+str(axes)+r'\b',raw):
                if any(arrays(raw,'nu')): raise RuntimeError('Nonzero disarmed nu')
                if not re.search(r'fault:\s+0\b',raw): raise RuntimeError('Controller fault')
                result['events'].append(dict(mode=mode,axes=axes,status=raw)); return
            time.sleep(.2)
        raise RuntimeError('Selection timeout')

    def stop():
        nonlocal proc,console
        if proc is not None and proc.poll() is None:
            try: cli('shutdown'); proc.wait(timeout=15)
            except (subprocess.TimeoutExpired,RuntimeError):
                os.killpg(proc.pid,signal.SIGTERM); proc.wait(timeout=15)
        if console: console.close()
        proc=None

    def boot(number):
        nonlocal proc,console
        env=os.environ.copy()
        for k in ('DONT_RUN','NO_PXH','PX4_SIM_SPEED_FACTOR'): env.pop(k,None)
        env['PX4_SITL_WORLD']=str(REPO/'sitl/worlds/empty_grey.world'); env['GAZEBO_MASTER_URI']='http://127.0.0.1:11345'
        path=output/('boot'+str(number)+'.log'); console=path.open('w')
        proc=subprocess.Popen(['./sitl/run.sh','--headless','--backend','gazebo','--model','iris'],cwd=REPO,env=env,stdin=subprocess.PIPE,stdout=console,stderr=subprocess.STDOUT,start_new_session=True)
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            if proc.poll() is not None: raise RuntimeError('Startup exited')
            if 'Startup script returned successfully' in path.read_text(): break
            time.sleep(.5)
        else: raise RuntimeError('Startup timeout')
        disarmed()
        if Checks.get_param(cli,'SYS_AUTOSTART')!=10016: raise RuntimeError('Iris only')

    try:
        boot(1)
        original={k:Checks.get_param(cli,k) for k in [*config,'MC_RATT_TEST']}
        if any(original[k] for k in ('MC_RTC_MODE','MC_STA_AXES','MC_RATT_TEST')): raise RuntimeError('Require inactive initial config')
        save(output/'original.json',original)
        for k,v in config.items(): cli('param','set',k,v)
        accepted(1,7); cli('param','save'); cli('param','save',str(output/'saved_rpy.bson'))
        stop(); boot(2)
        loaded={k:Checks.get_param(cli,k) for k in config}
        # PX4 CLI prints rounded decimals; compare as it printed before reboot.
        for k,v in config.items():
            if abs(loaded[k]-v)>max(1e-5,abs(v)*1e-6): raise RuntimeError('Restart value mismatch '+k)
        accepted(1,7); save(output/'restarted_values.json',loaded)
        for mask in (1,3,7):
            cli('param','set','MC_STA_AXES',mask); accepted(1,mask)
        cli('param','set','MC_RTC_MODE',0); cli('param','set','MC_STA_AXES',0); accepted(0,0)
        cli('param','load',str(output/'saved_rpy.bson')); accepted(1,7)
        reloaded={k:Checks.get_param(cli,k) for k in config}
        if reloaded!=loaded: raise RuntimeError('Reload mismatch')
        save(output/'reloaded_values.json',reloaded)
        result['success']=True
    except Exception as exc:
        result['error']=repr(exc)
    finally:
        if original and proc is not None and proc.poll() is None:
            try:
                disarmed()
                for k,v in original.items(): cli('param','set',k,v)
                accepted(0,0); cli('param','save')
                restored={k:Checks.get_param(cli,k) for k in original}
                if restored!=original: raise RuntimeError('Restore mismatch')
                save(output/'restored_values.json',restored)
            except Exception as exc: result.update(success=False,restore_error=repr(exc))
        elif original:
            result.update(success=False,restore_error='No running instance; inspect saved startup parameters before proceeding')
        stop(); save(output/'result.json',result)
    print(json.dumps(result,indent=2))
    if not result['success']: raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--output',type=Path,required=True);main(p.parse_args().output.resolve())
