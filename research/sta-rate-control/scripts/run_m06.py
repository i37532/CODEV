#!/usr/bin/env python3
"""M06 uses original launcher/monitor; optional yaw-only precursor is archived."""
import os
import time
from pathlib import Path
from run_m00 import main, save
from run_m04 import Checks as BaseChecks, arrays


class Checks(BaseChecks):
    stage = 'm06'
    prefix = 'M06'
    config_name = 'iris_esta_rpy.json'

    def __init__(self):
        super().__init__()
        if self.axes != (7 if self.mode else 0):
            raise ValueError('M06 requires PID AXES=0 or ESTA AXES=7')
        if os.environ.get('M06_YAW_ONLY', '0') == '1':
            self.protocol['trigger'] = 3
            self.protocol['windows'] = {'yaw_only': [0,12], 'yaw_repeat': [12,24], 'yaw_final': [24,36]}

    def __call__(self, phase, cli, topic, output):
        super().__call__(phase, cli, topic, output)
        if phase != 'disarmed':
            return
        # Close the flight's constant-configuration ULog before ground-only
        # transitions. Commands and complete listener output are still archived.
        if topic('vehicle_status').get('arming_state') != 1:
            raise RuntimeError('Ground transitions require disarmed vehicle')
        cli('logger','stop')
        self.flight_logger_stopped = True
        events=[]
        for mask in (1,3,7,0):
            cli('param','set','MC_STA_AXES',mask)
            cli('param','set','MC_RTC_MODE',int(mask != 0))
            deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                d=topic('sta_rate_ctrl_status')
                if d.get('armed'): raise RuntimeError('Unexpected arming during ground transitions')
                if d.get('effective_mode')==int(mask!=0) and d.get('effective_axes')==mask and not d.get('pending') and not d.get('config_pending'):
                    raw=cli('listener','sta_rate_ctrl_status','-n','1')
                    if any(arrays(raw,'nu')) or d.get('fault') or not d.get('config_valid'):
                        raise RuntimeError('Ground reset/config/fault verification failed')
                    events.append(dict(mask=mask,status=d,raw=raw));break
                time.sleep(.2)
            else: raise RuntimeError('Ground transition not accepted')
        save(output/'postflight_transitions.json',events)


if __name__ == '__main__':
    main(checks=Checks(), scenario_path=Path(__file__))
