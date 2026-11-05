#!/usr/bin/env python3
"""One M09 flight, same frozen M08 gains/scene; never batch M10."""
import json
import os
from pathlib import Path
import time
from run_m00 import main, save
from run_m04 import Checks as Base, RESEARCH


class Checks(Base):
    stage = 'm08'  # retain calibrated model + frozen M06 v2 excitation exactly
    prefix = 'M09'
    allowed_modes = (0, 1, 2)

    def __init__(self):
        mode = int(os.environ.get('M09_MODE', '0'))
        self.config_name = ('iris_pid.json', 'iris_esta_rpy.json', 'iris_ista_rpy_candidate02.json')[mode] if mode in self.allowed_modes else ''
        super().__init__()
        self.div = int(os.environ.get('M09_DIV', '1'))
        if self.div not in (1, 2, 4):
            raise ValueError('DIV must be 1/2/4')
        self.config['MC_RTC_DIV'] = self.div

    def __call__(self, phase, cli, topic, output):
        super().__call__(phase, cli, topic, output)
        if phase == 'preflight':
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                d = topic('sta_rate_ctrl_status')
                if d.get('div_eff') == self.div and d.get('div_ok') and not d.get('div_wait'):
                    save(output/'m09_preflight.json', d)
                    break
                time.sleep(.2)
            else:
                raise RuntimeError('Divisor not accepted before arming')
        if phase == 'disarmed':
            cli('logger', 'stop')
            self.flight_logger_stopped = True
            observations = []
            for div in (1, 2, 4, 3, 1):
                cli('param', 'set', 'MC_RTC_DIV', div)
                time.sleep(1.2)
                d = topic('sta_rate_ctrl_status')
                expected = 4 if div == 3 else div
                if d.get('armed') or d.get('div_eff') != expected or bool(d.get('div_ok')) != (div != 3):
                    raise RuntimeError('Ground divisor/rejection failed')
                observations.append(d)
            save(output/'m09_ground_divisors.json', observations)

    def monitor(self, phase, cli, topic, output, state):
        super().monitor(phase, cli, topic, output, state)
        if phase != 'warmup':
            d = topic('sta_rate_ctrl_status')
            if d.get('div_eff') != self.div or not d.get('div_ok'):
                raise RuntimeError('Effective divisor drift')


if __name__ == '__main__':
    main(checks=Checks(), scenario_path=Path(__file__))
