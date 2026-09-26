from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from test_v04_attitude_clock09 import attitude
from test_v04_protocol04 import Log
from v04_attitude_clock09 import AttitudeClockPolicy
from v04_live_clock09 import sealed_time, reference_row as old_reference
from v04_prearm17 import reference_row
import v04_monitor17 as monitor


def fixture(pos=(98000,106000,118000), pub=(96000,100000,104000,108000,112000,116000,120000)):
    p=dict(timestamp=np.array(pos,np.uint64),timestamp_sample=np.array(pos,np.uint64),
           x=np.zeros(len(pos)),y=np.zeros(len(pos)),z=np.zeros(len(pos)))
    return Log({('vehicle_attitude',0):attitude(pub,pub),('vehicle_local_position',0):p})


class Prearm17(unittest.TestCase):
    def test_original_empty_point_interval_reproduced_without_weakening_policy(self):
        u=fixture();old=old_reference(u);self.assertEqual(old['timestamp'],118000)
        with self.assertRaisesRegex(ValueError,'Missing attitude interval'):
            AttitudeClockPolicy().window(u.tables[('vehicle_attitude',0)],118000,118000)
        new=reference_row(u);self.assertEqual(new['timestamp'],106000)
        ix=AttitudeClockPolicy().window(u.tables[('vehicle_attitude',0)],new['timestamp'],sealed_time(u))
        self.assertGreaterEqual(len(ix),2)

    def test_aligned_clock_preserves_old_reference(self):
        u=fixture((100000,112000,120000));self.assertEqual(reference_row(u),old_reference(u))

    def test_all_phase_offsets_have_real_causal_rows(self):
        for phase in range(0,4000,1000):
            u=fixture(tuple(range(80000+phase,150001,10000)),tuple(range(76000,156001,4000)))
            r=reference_row(u);stop=sealed_time(u);a=u.tables[('vehicle_attitude',0)]
            ix=AttitudeClockPolicy().window(a,r['timestamp'],stop)
            self.assertIn(r['timestamp'],u.tables[('vehicle_local_position',0)]['timestamp'])
            self.assertTrue(np.any(a['timestamp'][ix]>=r['timestamp']))
            self.assertLessEqual(int(a['timestamp'][ix][-1]),stop)

    def test_missing_causal_position_rejected(self):
        with self.assertRaisesRegex(ValueError,'No causal'):reference_row(fixture((118000,)))

    def test_no_complete_attitude_group_rejected(self):
        with self.assertRaises(ValueError):reference_row(fixture((90000,), (96000,100000)))

    def test_stale_predecessor_is_not_forgiven(self):
        with self.assertRaises(ValueError):reference_row(fixture((98000,106000,118000),(60000,116000,120000)))

    def test_future_reversed_or_nonfinite_attitude_still_rejected(self):
        for kind in ('future','backward','nan'):
            u=fixture();a=u.tables[('vehicle_attitude',0)]
            if kind=='future':a['timestamp_sample'][-1]+=4000
            elif kind=='backward':a['timestamp'][-1]=1
            else:a['q[1]'][-1]=np.nan
            with self.assertRaises(ValueError):reference_row(u)

    def test_complete_equal_groups_and_reset_edges_are_preserved(self):
        u=fixture();a=u.tables[('vehicle_attitude',0)]
        a['timestamp'][3]=112000;a['quat_reset_counter'][4:]=3
        r=reference_row(u);p=AttitudeClockPolicy();ix=p.window(a,r['timestamp'],sealed_time(u))
        self.assertIn(3,ix);self.assertIn(4,ix)
        self.assertEqual(p.reset_indices(a,r['timestamp'],sealed_time(u)).tolist(),[4])

    def test_monitor_only_prearm_override_and_original_checks_execute(self):
        self.assertIs(monitor.Checks.monitor,monitor.HistoricalChecks.monitor)
        self.assertIs(monitor.Checks.landing_complete,monitor.HistoricalChecks.landing_complete)
        p=dict(timestamp=106000,x=1,y=2,z=3);ref={'position':p};u=object()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'log/t.ulg';path.parent.mkdir();path.touch()
            c=monitor.Checks.__new__(monitor.Checks);c.logs_before=set()
            live=SimpleNamespace(path=path,inode=123,read=lambda:u)
            topics=lambda n: {'arming_state':1} if n=='vehicle_status' else {'timestamp':120000}
            with patch.object(monitor,'ROOTFS',root),patch.object(monitor,'LiveLog',return_value=live), \
                 patch.object(monitor,'reference_row',return_value=p) as select, \
                 patch.object(monitor,'freeze_reference',return_value=ref), \
                 patch.object(monitor,'replay') as replay,patch.object(monitor,'LandingLiveLog',return_value='extended'):
                self.assertEqual(c.start_heading(topics,root),ref)
                select.assert_called_once_with(u);replay.assert_called_once_with(u,ref)
                self.assertEqual(c.live,'extended');self.assertEqual(c.ground,[1,2,3])
                with self.assertRaisesRegex(RuntimeError,'prearm'):
                    c.start_heading(lambda n:{'arming_state':2},root)
                with self.assertRaisesRegex(RuntimeError,'Stale prearm'):
                    c.start_heading(lambda n:{'arming_state':1} if n=='vehicle_status' else {'timestamp':900000},root)


if __name__=='__main__':unittest.main()
