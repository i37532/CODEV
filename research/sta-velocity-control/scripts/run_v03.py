#!/usr/bin/env python3
"""One PID-only velocity diagnostic attempt, using unchanged V01/V00 launcher.

Default is dry-run. The inherited runner verifies source cleanliness, assets,
parameters, sole owned Iris simulator, restores EEPROM bytes, and never retries.
"""
import run_v01 as runner
from analyze_v03 import CONFIG, analyze


class Checks(runner.Checks):
    def monitor(self, phase, cli, topic, output, state):
        super().monitor(phase, cli, topic, output, state)
        d = topic('sta_velocity_ctrl_status')
        self.selection(d)
        if abs(state['position'].get('timestamp', 0)-d['timestamp']) > 1e6:
            raise RuntimeError('Stale velocity diagnostics')
        if state['status'].get('arming_state') == 2 and d.get('enabled'):
            for key, value in {'inner_mode':0,'inner_axes':0,'inner_divisor':1,'inner_valid':1,
                               'fault':0,'failsafe':0,'timing':0,'pid_calls':1,'valid':1}.items():
                if d.get(key) != value:
                    raise RuntimeError('V03 monitor: '+key+'='+str(d.get(key)))


if __name__ == '__main__':
    runner.CONFIG = CONFIG
    runner.Checks = Checks
    runner.analyze = analyze
    runner.main()
