"""Deterministic scheduling tests with the UNCHANGED real landing validator."""
import copy
import inspect
import unittest
import numpy as np
from test_landing import fixture,last
from landing import LandingMonitor
from pending_poll import drain


class PendingPollTest(unittest.TestCase):
    def setup(self):
        full,ctx=fixture();partial=copy.deepcopy(full)
        partial.tables[('vehicle_status',0)]={k:v[:1] for k,v in partial.tables[('vehicle_status',0)].items()}
        wall=[0.];m=LandingMonitor(lambda:wall[0]);m.begin(**ctx)
        return full,partial,wall,m

    def test_immediate_fresh_poll_resolves_original_deadline(self):
        full,partial,wall,m=self.setup();records=[]
        def poll(i):
            wall[0]+=.35
            m.update(partial if i==0 else full,last(full),91108000+i*350000)
        drain(m,poll,records.append)
        self.assertEqual(len(records),2);self.assertFalse(m.failed);self.assertFalse(m.last_evidence['pending'])
        self.assertEqual(records[1]['pending_since'],(91108000,.35))

    def test_original_slow_task_loop_would_still_timeout(self):
        full,partial,wall,m=self.setup();m.update(partial,last(full),91108000)
        wall[0]=.550001
        with self.assertRaisesRegex(ValueError,'pending timeout'):m.update(full,last(full),91458000)
        self.assertTrue(m.failed)

    def test_no_pending_does_not_extra_poll(self):
        full,partial,wall,m=self.setup();records=[]
        drain(m,lambda i:m.update(full,last(full),91108000),records.append)
        self.assertEqual(len(records),1)

    def test_unresolved_cannot_reset_host_deadline(self):
        full,partial,wall,m=self.setup();records=[]
        def poll(i):
            wall[0]=i*.3
            m.update(partial,last(full),91108000)
        with self.assertRaisesRegex(ValueError,'pending timeout'):drain(m,poll,records.append)
        self.assertEqual(len(records),3);self.assertTrue(m.failed)
        self.assertEqual(m.pending_since,(91108000,0.))

    def test_real_fault_propagates_instead_of_more_polls(self):
        full,partial,wall,m=self.setup();records=[]
        def poll(i):
            d=last(full)
            if i:d['fault']=1
            m.update(partial,d,91108000)
        with self.assertRaisesRegex(ValueError,'failure'):drain(m,poll,records.append)
        self.assertEqual(len(records),2);self.assertTrue(m.failed)

    def test_future_status_cannot_be_borrowed(self):
        full,partial,wall,m=self.setup();records=[]
        s=full.tables[('vehicle_status',0)];s['timestamp'][-1]+=1;s['nav_state_timestamp'][-1]+=1
        with self.assertRaisesRegex(ValueError,'past/equal'):
            drain(m,lambda i:m.update(full,last(full),91108000),records.append)
        self.assertEqual(len(records),1)

    def test_both_clocks_frozen_are_bounded_not_spin_forever(self):
        full,partial,wall,m=self.setup();records=[]
        with self.assertRaisesRegex(ValueError,'count exhausted'):
            drain(m,lambda i:m.update(partial,last(full),91108000),records.append)
        self.assertEqual(len(records),8);self.assertTrue(m.failed)

    def test_runner_wiring_and_original_validator_bytes(self):
        import run,common
        self.assertIs(run.drain_pending,drain)
        self.assertIn('drain_pending(self.landing,poll,record)',inspect.getsource(run.Checks.monitor))
        self.assertIn("topic('vehicle_local_position')",inspect.getsource(run.Checks.monitor))
        for name in ('landing.py','position_live.py','position_log.py','core.py','cadence.py','analyze.py'):
            self.assertEqual((common.CONFIG/name).read_bytes(),(common.CONFIG.parent/'protocol04'/name).read_bytes(),name)


if __name__=='__main__':unittest.main(verbosity=2)
