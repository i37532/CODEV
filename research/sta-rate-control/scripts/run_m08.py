#!/usr/bin/env python3
"""M08 staged ISTA, original Iris launcher and M04/M05/M06 excitations only."""
import json
import os
from pathlib import Path
import time
from run_m00 import main, save
from run_m04 import Checks as BaseChecks, RESEARCH, arrays


class Checks(BaseChecks):
    stage = 'm08'
    prefix = 'M08'
    config_name = 'iris_ista_rpy.json'
    allowed_modes = (0, 1, 2)

    def __init__(self):
        super().__init__()
        scene = os.environ.get('M08_SCENE', 'rpy')
        if scene not in ('roll', 'rp', 'rpy'):
            raise ValueError('Unknown M08 scene')
        axes = {'roll': 1, 'rp': 3, 'rpy': 7}[scene]
        if self.mode and self.axes != axes:
            raise ValueError('Config axes do not match staged scene')
        if scene != 'rpy':
            self.protocol = json.loads((RESEARCH/('m04' if scene == 'roll' else 'm05')/'protocol.json').read_text())
            self.protocol.update(integration_milestone='M08', integration_version=1, frozen_before_ista_flight=True)
            # Do NOT import M06 heading mode into historical M04/M05 regression.
            self.config.pop('MPC_YAW_MODE', None)
            self.config.update(self.protocol['scenario_parameters'])

    def __call__(self, phase, cli, topic, output):
        super().__call__(phase, cli, topic, output)
        if phase != 'disarmed':
            return
        if topic('vehicle_status').get('arming_state') != 1:
            raise RuntimeError('Ground transitions require disarmed vehicle')
        cli('logger', 'stop')
        self.flight_logger_stopped = True
        events = []
        # All modes may be selected while disarmed, but no flight expands masks
        # until the staged gate has passed. Config/reset observation only here.
        for mode, mask in [(0,0), (1,1), (2,1), (1,3), (2,3), (1,7), (2,7), (0,0)]:
            cli('param', 'set', 'MC_STA_AXES', mask)
            cli('param', 'set', 'MC_RTC_MODE', mode)
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                d = topic('sta_rate_ctrl_status')
                if d.get('armed'): raise RuntimeError('Unexpected arming')
                if (d.get('effective_mode') == mode and d.get('effective_axes') == mask
                        and not d.get('pending') and not d.get('config_pending')):
                    raw = cli('listener','sta_rate_ctrl_status','-n','1')
                    if any(arrays(raw,'nu')) or d.get('fault') or not d.get('config_valid'):
                        raise RuntimeError('Ground reset/config/fault check failed')
                    events.append(dict(mode=mode, axes=mask, status=d, raw=raw))
                    break
                time.sleep(.2)
            else: raise RuntimeError('Ground transition timeout')
        save(output/'postflight_transitions.json', events)


if __name__ == '__main__':
    main(checks=Checks(), scenario_path=Path(__file__))
