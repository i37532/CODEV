#!/usr/bin/env python3
"""Separate SITL-only flight: armed mode/gain changes must defer without reset.

Not part of the constant-request nine-flight performance comparison. Original
60-second hover/excitation/landing retained, with independent ULog verification.
"""
import os
from pathlib import Path
from run_m08 import Checks as BaseChecks
from run_m00 import main, save
from run_m04 import arrays


class Checks(BaseChecks):
    def __init__(self):
        super().__init__()
        if self.mode!=2 or self.axes!=7:raise ValueError('Lifecycle test requires full-axis ISTA')
        self.phase=0;self.events=[]

    def monitor(self,phase,cli,topic,output,state):
        super().monitor(phase,cli,topic,output,state)
        if phase!='hover' or not self.hover_start:return
        elapsed=(state['position']['timestamp']-self.hover_start)*1e-6
        if self.phase==0 and elapsed>=3:
            cli('param','set','MC_RTC_MODE',1)
            cli('param','set','MC_STA_L1_R',self.config['MC_STA_L1_R']*1.5)
            self.phase=1
        elif self.phase==1 and elapsed>=7:
            d=topic('sta_rate_ctrl_status');raw=cli('listener','sta_rate_ctrl_status','-n','1')
            if not (d.get('armed') and d.get('pending') and d.get('config_pending') and d.get('effective_mode')==2):
                raise RuntimeError('Armed request was not deferred')
            if abs(arrays(raw,'lambda1')[0]-self.config['MC_STA_L1_R'])>1e-4 or not any(arrays(raw,'nu')):
                raise RuntimeError('Active gain/state changed during pending request')
            self.events.append(dict(event='pending_verified',status=d,raw=raw))
            cli('param','set','MC_RTC_MODE',2)
            cli('param','set','MC_STA_L1_R',self.config['MC_STA_L1_R'])
            self.phase=2
        elif self.phase==2 and elapsed>=11:
            d=topic('sta_rate_ctrl_status')
            if d.get('pending') or d.get('config_pending') or d.get('effective_mode')!=2:
                raise RuntimeError('Pending cancellation failed')
            self.events.append(dict(event='cancel_verified',status=d))
            save(output/'armed_lifecycle.json',self.events);self.phase=3

    def __call__(self,phase,cli,topic,output):
        if phase=='disarmed' and self.phase!=3:raise RuntimeError('Armed lifecycle checks incomplete')
        super().__call__(phase,cli,topic,output)


if __name__=='__main__':
    os.environ['M08_MODE']='2';os.environ['M08_SCENE']='rpy'
    main(checks=Checks(),scenario_path=Path(__file__))
