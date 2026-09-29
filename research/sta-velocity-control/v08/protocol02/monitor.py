"""V08 opt-in monitor: unchanged envelopes/history, per-read diagnostic clock.

Method bodies are scoped copies of run_v00, run_v04_protocol09 and
v04_monitor10. Old modules and historical verdicts remain unchanged.
"""
import json
import math
from run_v00 import check_inner, arrays, save
from v04_monitor17 import Checks as HistoricalChecks
from v04_task04 import check_cli_reference, excitation_class
from v04_live_clock09 import replay
from cli_clock import require_fresh


class Checks(HistoricalChecks):
    def _base_monitor(self, phase, cli, topic, output, state):
        pos, vehicle = state['position'], state['status']
        d = topic('sta_rate_ctrl_status')
        if phase == 'warmup' and ('timestamp' not in d or 'timestamp' not in pos):
            return
        check_inner(d)
        require_fresh(d)
        if d['publish_seq'] == self.last_seq:
            raise RuntimeError('Stale diagnostic')
        self.last_seq = d['publish_seq']
        if phase == 'warmup' and pos.get('xy_valid') and pos.get('z_valid'):
            self.ground = [pos['x'], pos['y'], pos['z']]
            save(output / 'ground.json', self.ground)
        if vehicle.get('arming_state') == 2:
            if vehicle.get('failsafe') or vehicle.get('failure_detector_status'):
                raise RuntimeError('Vehicle failsafe/failure detector')
            for k in ('xy_valid', 'z_valid', 'v_xy_valid', 'v_z_valid'):
                if not pos.get(k):
                    raise RuntimeError('Invalid local position: ' + k)
            q = arrays(cli('listener', 'vehicle_attitude', '-n', '1'), 'q')
            if len(q) != 4 or not all(math.isfinite(v) for v in q):
                raise RuntimeError('Invalid attitude')
            tilt = math.degrees(math.acos(max(-1., min(1., 1 - 2*(q[1]**2 + q[2]**2)))))
            xy_speed = math.hypot(pos['vx'], pos['vy'])
            xy_dist = math.hypot(pos['x'] - self.ground[0], pos['y'] - self.ground[1])
            height = self.ground[2] - pos['z']
            if tilt > 15 or xy_speed > 1 or xy_dist > 2 or not -.5 <= height <= 4:
                raise RuntimeError('Position/tilt/velocity flight envelope')
            if abs(pos['vz']) > (.6 if phase == 'hover' else 3.5):
                raise RuntimeError('Vertical velocity envelope')
            if phase == 'hover' and abs(height - 2.5) > 1:
                raise RuntimeError('Hover altitude envelope')
        with (output / 'v00_monitor.jsonl').open('a') as stream:
            stream.write(json.dumps({'phase': phase, 'inner': d}) + '\n')

    def _phase_monitor(self,phase,cli,topic,output,state):
        self._base_monitor(phase,cli,topic,output,state)
        d=topic('sta_velocity_ctrl_status'); self.selection(d)
        self.latest_diagnostic=d
        if self.reference and state['status'].get('arming_state')==2:
            check_cli_reference(state['position'],self.reference)
        for key in ('first_fail','retry_result','first_input','excitation_fault'):
            if key not in d: raise RuntimeError('Missing diagnostic '+key)
        if d.get('armed') and d.get('enabled'):
            if d['first_fail'] or d['retry_result']: raise RuntimeError('First update/retry failure')
        if self.reference:
            evidence=replay(self.live.read(),self.reference,frozen=self.frozen_yaw,allow_pending=True)
            now=topic('vehicle_local_position')
            age=now['timestamp']-evidence['through_us']
            if not 0<=age<=500000: raise RuntimeError('Live ULog transport stale/future')
            # Raw full-rate history establishes quiet time; CLI only guards delivery age.
            if not self.task_yaw_ready and evidence['ready']:
                self.frozen_yaw=evidence['freeze_candidate']
                self.reference['yaw']=self.frozen_yaw['yaw']
                self.task_yaw_ready=True
                save(output/'task_yaw.json',self.frozen_yaw)
            with (output/'heading_live.jsonl').open('a') as stream:
                stream.write(json.dumps(dict(phase=phase,age_us=age,evidence=evidence))+'\n')
        # CLI reads are asynchronous; definitive callback-level phase check is in ULog.
        category=excitation_class(int(d['excitation_fault']),bool(d['armed']),
            int(state['status']['nav_state']),self.planned_landing,self.observation_completed,d['excitation'])
        with (output/'protocol09_monitor.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(phase=phase,diagnostic=d,category=category))+'\n')
        require_fresh(d)
        if state['status'].get('arming_state')==2 and d.get('enabled'):
            for key,value in dict(inner_mode=0,inner_axes=0,inner_divisor=1,inner_valid=1,fault=0,
                                  failsafe=0,timing=0,pid_calls=1,valid=1,sta_fault=0,config_pending=0).items():
                if d.get(key)!=value: raise RuntimeError('V04 monitor '+key+'='+str(d.get(key)))

    def monitor(self, phase, cli, topic, output, state):
        if phase != 'landing':
            return self._phase_monitor(phase, cli, topic, output, state)
        # Retain the existing CLI envelope and inner-loop safeguards.
        self._base_monitor(phase, cli, topic, output, state)
        d = topic('sta_velocity_ctrl_status')
        self.selection(d)
        require_fresh(d)
        self.latest_diagnostic = d
        if self.reference and d.get('armed'):
            check_cli_reference(state['position'], self.reference)
        if self.reference is None or self.landing_live is None:
            raise ValueError('Missing raw landing reader/reference')
        # Full history reset, tilt, primary and clock checks remain mandatory.
        log = self.landing_live.read()
        heading = replay(log, self.reference, frozen=self.frozen_yaw, allow_pending=True)
        now = topic('vehicle_local_position')['timestamp']
        age = now-heading['through_us']
        if not 0 <= age <= 500000:
            raise ValueError('Live ULog transport stale/future')
        with (output/'heading_live.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(phase=phase, age_us=age, evidence=heading))+'\n')
        evidence = self.landing.update(log, d, now)
        with (output/'landing10_monitor.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(phase=phase, diagnostic=d, cli_status=state['status'],
                                         evidence=evidence))+'\n')
