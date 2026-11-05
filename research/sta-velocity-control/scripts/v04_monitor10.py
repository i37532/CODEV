"""Opt-in landing repair. No batch entry/authorization; historical Checks unchanged."""
import json
from run_v04_protocol09 import Checks as HistoricalChecks
from run_v00 import Checks as BaseChecks, save
from v04_task04 import check_cli_reference
from v04_live_clock09 import replay
from v04_landing10 import LandingMonitor
from v04_landing_live10 import LandingLiveLog


class Checks(HistoricalChecks):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.landing = LandingMonitor()
        self.landing_live = None

    def start_heading(self, topic, output):
        ref = super().start_heading(topic, output)
        self.landing_live = LandingLiveLog(self.live.path)
        # Reuse this extended reader in the unchanged heading monitor from now
        # on; avoid a first full-file parse exactly at the landing transition.
        self.live = self.landing_live
        return ref

    def begin_landing(self, start, end, lower, output):
        if not self.observation_completed or not self.planned_landing:
            raise ValueError('Landing plan not completed/sent')
        self.landing.begin(start, end, lower, True)
        save(output/'landing_context.json', self.landing.context)

    def monitor(self, phase, cli, topic, output, state):
        if phase != 'landing':
            return super().monitor(phase, cli, topic, output, state)
        # Retain the existing CLI envelope and inner-loop safeguards.
        BaseChecks.monitor(self, phase, cli, topic, output, state)
        d = topic('sta_velocity_ctrl_status')
        self.selection(d)
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

    def landing_complete(self):
        if not self.landing.last_evidence or self.landing.last_evidence['pending']:
            return False
        # CLI vehicle_status may already say disarmed while the controller still
        # holds its preceding armed diagnostic. Do not turn that race into success.
        if self.latest_diagnostic is None or self.latest_diagnostic.get('armed') != 0:
            return False
        self.landing.require_complete()
        return True
