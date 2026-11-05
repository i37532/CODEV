"""Only prearm reference selection differs from the established live monitor."""
from v04_monitor10 import Checks as HistoricalChecks
from run_v00 import ROOTFS, save
from v04_heading_stream import LiveLog
from v04_live_clock09 import replay
from v04_prearm17 import reference_row
from v04_landing_live10 import LandingLiveLog
from v04_task04 import freeze_reference


class Checks(HistoricalChecks):
    def start_heading(self, topic, output):
        paths=set(ROOTFS.glob('log/**/*.ulg'))-self.logs_before
        if len(paths)!=1: raise RuntimeError('Need exactly one owned restarted logger file')
        self.live=LiveLog(paths.pop()); log=self.live.read()
        p=reference_row(log)
        if topic('vehicle_status')['arming_state']!=1: raise RuntimeError('Reference must be prearm')
        age=topic('vehicle_local_position')['timestamp']-p['timestamp']
        if not 0<=age<=500000: raise RuntimeError('Stale prearm ULog')
        ref=freeze_reference(p)
        replay(log,ref)  # all original metadata, reset, attitude and mode checks
        self.ground=[p[k] for k in ('x','y','z')]
        save(output/'ground.json',self.ground)
        save(output/'live_log.json',dict(path=str(self.live.path),inode=self.live.inode,transport_max_age_us=500000))
        self.landing_live=LandingLiveLog(self.live.path)
        self.live=self.landing_live
        return ref
