#!/usr/bin/env python3
"""One M04 PID/roll-ESTA Iris run. Set M04_MODE=0 or 1; no other modes.

Original launcher, attitude-setpoint publisher and thrust source retained.
The only excitation is the existing attitude controller's bounded roll pulse.
"""
import json
import math
import os
from pathlib import Path
import re
import time
from run_m00 import main, save, digest
from run_m03 import Checks as M03Checks

RESEARCH = Path(__file__).resolve().parents[1]


def arrays(raw, key):
    match = re.search(r'\b'+key+r':\s*\[([^\]]+)\]', raw)
    if not match:
        raise RuntimeError('Missing vector '+key)
    return [float(x) for x in match.group(1).replace(',', ' ').split()]


class Checks:
    stage = 'm04'
    prefix = 'M04'
    config_name = 'iris_esta_roll.json'

    def __init__(self):
        self.mode = int(os.environ.get(self.prefix+'_MODE', '0'))
        if self.mode not in (0, 1):
            raise ValueError('Only PID or roll ESTA')
        config_path = Path(os.environ.get(self.prefix+'_CONFIG', str(RESEARCH/self.stage/self.config_name)))
        self.config = json.loads(config_path.read_text())
        self.config['MC_RTC_MODE'] = self.mode
        self.axes = int(self.config['MC_STA_AXES']) if self.mode else 0
        self.config['MC_STA_AXES'] = self.axes
        self.protocol = json.loads((RESEARCH/self.stage/'protocol.json').read_text())
        self.config.update(self.protocol.get('scenario_parameters',{}))
        calibration=json.loads((RESEARCH/self.stage/'calibration.json').read_text())
        for path,expected in calibration['files'].items():
            if digest(RESEARCH.parents[1]/path)!=expected:
                raise RuntimeError('Calibrated model/source changed: '+path)
        self.original = {}
        self.hover_start = None
        self.triggered = False
        self.last_seq = None

    def __call__(self, phase, cli, topic, output):
        if phase == 'preflight':
            if M03Checks.get_param(cli, 'SYS_AUTOSTART') != 10016:
                raise RuntimeError('Iris only')
            for name in ['MC_RTC_MODE','MC_STA_AXES','MC_RATT_TEST']:
                if M03Checks.get_param(cli, name) != 0:
                    raise RuntimeError('Require default inactive starting configuration: '+name)
            if os.environ.get('M04_REPAIR_V2_LAND_PARAM')=='1':
                # One-time repair of our documented v2 land-detector side effect.
                before={k:M03Checks.get_param(cli,k) for k in ['MPC_LAND_SPEED','LNDMC_Z_VEL_MAX']}
                if before != {'MPC_LAND_SPEED':0.7,'LNDMC_Z_VEL_MAX':0.3}:
                    raise RuntimeError('Unexpected state for explicit v2 repair: '+str(before))
                cli('param','set','LNDMC_Z_VEL_MAX',0.5)
                cli('param','save')
                save(output/'v2_parameter_repair.json',dict(before=before,restored_LNDMC_Z_VEL_MAX=0.5))
            for name in list(self.config)+['MC_RATT_TEST','SDLOG_PROFILE']:
                self.original[name] = M03Checks.get_param(cli,name)
            save(output/'m04_config.json',self.config)
            save(output/'m04_protocol.json',self.protocol)
            save(output/'m04_source_hashes.json', {str(p.relative_to(RESEARCH)):digest(p) for p in
                 [RESEARCH/self.stage/'calibration.json',RESEARCH/self.stage/'protocol.json',Path(__file__),
                  RESEARCH/'scripts/run_m00.py', RESEARCH/'scripts/run_m03.py',
                  RESEARCH/('scripts/run_'+self.stage+'.py')]})
            # Gains first, axes then mode. All are validated before arming.
            for name,value in self.config.items():
                cli('param','set',name,value)
            cli('logger','stop')
            time.sleep(1.1) # avoid assuming restart always gets a separate filename
            profile = int(self.original['SDLOG_PROFILE']) | 16
            cli('param','set','SDLOG_PROFILE',profile)
            cli('logger','start','-b','256','-r','1000','-t','-f')
            save(output/'m03_logging.json',dict(original_profile=int(self.original['SDLOG_PROFILE']),research_profile=profile))
            deadline = time.monotonic()+12
            while time.monotonic()<deadline:
                status=topic('sta_rate_ctrl_status')
                if status.get('effective_mode') == self.mode and status.get('effective_axes') == self.axes and status.get('config_valid'):
                    break
                time.sleep(.2)
            else:
                raise RuntimeError('Controller/config not accepted before arming')
            save(output/'preflight_selection.json',status)
        elif phase == 'hover':
            self.hover_start = topic('vehicle_local_position')['timestamp']
        elif phase == 'cleanup' and self.original:
            cli('logger','stop')
            # Requested parameters restored even on abort; no in-flight switch.
            for name,value in self.original.items():
                cli('param','set',name,value)
            cli('param','save')
            restored={name:M03Checks.get_param(cli,name) for name in self.original}
            if restored != self.original:
                raise RuntimeError('Parameter restoration failed')
            save(output/'restored_parameters.json',restored)

    def monitor(self, phase, cli, topic, output, state):
        d=topic('sta_rate_ctrl_status')
        now=state['position'].get('timestamp',0)
        if phase=='warmup' and (not now or ('timestamp' not in d and now<=30e6)):
            return
        if d.get('effective_mode')!=self.mode or d.get('effective_axes')!=self.axes:
            raise RuntimeError('Mode/axis mismatch')
        if d.get('fault',1) or d.get('abort_requested',True):
            raise RuntimeError('Latched controller fault: '+str(d))
        if abs(now-d.get('timestamp',float('inf')))>1e6 or d.get('publish_seq')==self.last_seq:
            raise RuntimeError('Stale/absent controller diagnostics')
        self.last_seq=d.get('publish_seq')
        if d.get('armed') and (not d.get('output_valid') or d.get('timing_status')!=0 or not d.get('measurement_valid')):
            raise RuntimeError('Invalid active controller output/time/measurement')
        if d.get('armed'):
            q=arrays(cli('listener','vehicle_attitude','-n','1'),'q')
            if len(q)!=4 or not all(math.isfinite(x) for x in q):
                raise RuntimeError('Invalid attitude quaternion')
            tilt=math.degrees(math.acos(max(-1.,min(1.,1.-2.*(q[1]**2+q[2]**2)))))
            if not math.isfinite(tilt) or tilt>self.protocol['limits']['tilt_deg']:
                raise RuntimeError('Tilt boundary exceeded: '+str(tilt))
            if phase=='hover':
                sp=topic('vehicle_local_position_setpoint')
                if abs(state['position']['z']-sp.get('z',float('inf')))>self.protocol['limits']['height_error_m']:
                    raise RuntimeError('Height tracking boundary exceeded')
        if phase=='hover' and self.hover_start and not self.triggered and now-self.hover_start>=15e6:
            cli('param','set','MC_RATT_TEST',self.protocol.get('trigger',1))
            self.triggered=True
            save(output/'pulse_trigger.json',dict(timestamp_us=now))
        with (output/'m04_monitor.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(phase=phase,status=d))+'\n')


if __name__=='__main__':
    main(checks=Checks(),scenario_path=Path(__file__))
