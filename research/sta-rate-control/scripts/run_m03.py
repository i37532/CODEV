#!/usr/bin/env python3
"""M03 PID-only Iris flight, high-rate logging and local SITL abort monitor.

No fault is injected into an airborne vehicle. Guard faults are tested offline.
The monitor raises on observed abort/fault/stale telemetry, and run_m00 shuts
down the owned simulator instance, archives it as failed, and never commands
zero torque or PID takeover. This is NOT a real-vehicle safety controller.
"""
import json
import math
from pathlib import Path
import re
import time

from run_m00 import main


def check_abort(status, now):
    required = ('timestamp', 'effective_mode', 'effective_axes', 'fault', 'abort_requested')
    if any(key not in status for key in required):
        raise RuntimeError('SITL abort: missing diagnostic fields')
    if any(not math.isfinite(float(status[key])) for key in required):
        raise RuntimeError('SITL abort: invalid diagnostic fields')
    if status['effective_mode'] != 0 or status['effective_axes'] != 0:
        raise RuntimeError('SITL abort: experimental controller unexpectedly active')
    if status['fault'] or status['abort_requested']:
        raise RuntimeError('SITL abort: latched research fault')
    if status.get('armed') and status.get('updated'):
        if status.get('timing_status') != 0 or not status.get('measurement_valid') or not status.get('output_valid'):
            raise RuntimeError('SITL abort: invalid active PID sample or output')
    if now - status['timestamp'] > 1e6 or status['timestamp'] - now > 1e6:
        raise RuntimeError('SITL abort: missing/stale diagnostic stream')


class Checks:
    def __init__(self):
        self.profile = None
        self.original_l1 = None
        self.last_seq = None

    @staticmethod
    def get_param(cli, name):
        raw = cli('param', 'show', name)
        found = re.search(r'\b' + re.escape(name) + r'\s+\[[\d,]+\]\s*:\s*([-+\d.eE]+)', raw)
        if not found:
            raise RuntimeError(f'Cannot parse {name}: {raw}')
        return float(found.group(1))

    def __call__(self, phase, cli, topic, output):
        if phase == 'preflight':
            if self.get_param(cli, 'MC_RTC_MODE') != 0 or self.get_param(cli, 'MC_STA_AXES') != 0:
                raise RuntimeError('Require existing PID defaults, do not override user configuration')
            self.profile = int(self.get_param(cli, 'SDLOG_PROFILE'))
            self.original_l1 = self.get_param(cli, 'MC_STA_L1_R')
            # Preserve every existing bit. Logger reads topic selection at start.
            cli('logger', 'stop')
            cli('param', 'set', 'SDLOG_PROFILE', self.profile | 16)
            cli('logger', 'start', '-b', '256', '-r', '1000', '-t', '-f')
            (output / 'm03_logging.json').write_text(json.dumps({
                'original_profile': self.profile, 'research_profile': self.profile | 16,
                'logger_args': ['-b', '256', '-r', '1000', '-t', '-f'],
                'note': 'Boot log retained separately; continuous research log selected explicitly by analyzer.'}, indent=2))
        elif phase == 'hover':
            before = topic('sta_rate_ctrl_status')
            cli('param', 'set', 'MC_STA_L1_R', self.original_l1 + 0.125)
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                after = topic('sta_rate_ctrl_status')
                if after.get('config_pending'):
                    break
                time.sleep(0.2)
            else:
                raise RuntimeError('Armed parameter update did not remain pending')
            if before['config_seq'] != after['config_seq']:
                raise RuntimeError('Armed experiment configuration applied unexpectedly')
            (output / 'armed_config_check.json').write_text(json.dumps({'before': before, 'after': after}, indent=2))
        elif phase == 'disarmed':
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                status = topic('sta_rate_ctrl_status')
                if not status.get('config_pending', True):
                    break
                time.sleep(0.2)
            else:
                raise RuntimeError('Configuration remained pending after disarm')
            (output / 'disarmed_config_check.json').write_text(json.dumps(status, indent=2))
        elif phase == 'cleanup' and self.profile is not None:
            cli('logger', 'stop')
            if self.original_l1 is not None:
                cli('param', 'set', 'MC_STA_L1_R', self.original_l1)
            cli('param', 'set', 'SDLOG_PROFILE', self.profile)
            cli('param', 'save')
            restored = {'SDLOG_PROFILE': self.get_param(cli, 'SDLOG_PROFILE'),
                        'MC_STA_L1_R': self.get_param(cli, 'MC_STA_L1_R')}
            if restored != {'SDLOG_PROFILE': self.profile, 'MC_STA_L1_R': self.original_l1}:
                raise RuntimeError('Parameter restoration failed')
            (output / 'restored_parameters.json').write_text(json.dumps(restored, indent=2))

    def monitor(self, phase, cli, topic, output, state):
        status = topic('sta_rate_ctrl_status')
        # Startup can precede the first estimator/controller publication.
        # The original warmup deadline still bounds this grace period; never
        # accept missing telemetry during takeoff/hover/landing.
        if phase == 'warmup' and ('timestamp' not in state['position'] or
                ('timestamp' not in status and state['position']['timestamp'] <= 30e6)):
            return
        check_abort(status, state['position']['timestamp'])
        seq = status.get('publish_seq')
        if seq is None or seq == self.last_seq:
            raise RuntimeError('SITL abort: diagnostic sequence stopped')
        self.last_seq = seq
        with (output / 'm03_monitor.jsonl').open('a') as stream:
            stream.write(json.dumps({'phase': phase, 'status': status}) + '\n')


if __name__ == '__main__':
    main(checks=Checks(), scenario_path=Path(__file__))
