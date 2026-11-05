from pathlib import Path
import json
import unittest
import numpy as np
from pyulog import ULog
import test_health
from postland import collect, complete_tail


class Postland(unittest.TestCase):
    def fixture(self): return test_health.LandingHealth().log()

    def test_complete_does_not_wait(self):
        log,_=self.fixture()
        r=collect(lambda:log,lambda:dict(arming_state=1,landed=True),1010000,1300000)
        self.assertEqual(r['snapshots'],[dict(pending=[])])

    def test_pending_is_not_success_then_complete(self):
        first,tables=self.fixture()
        for k,v in tables['estimator_selector_status',0].items(): tables['estimator_selector_status',0][k]=v[:60]
        full,_=self.fixture(); logs=iter((first,full)); sleeps=[]
        r=collect(lambda:next(logs),lambda:dict(arming_state=1,landed=True),1010000,1300000,sleep=sleeps.append)
        self.assertEqual(r['snapshots'][0]['pending'],['estimator_selector_status:0'])
        self.assertEqual(len(sleeps),1)

    def test_timeout_no_reacceptance(self):
        log,tables=self.fixture()
        for k,v in tables['estimator_selector_status',0].items(): tables['estimator_selector_status',0][k]=v[:60]
        clock=[0.]
        def sleep(dt): clock[0]+=dt
        with self.assertRaises(TimeoutError):
            collect(lambda:log,lambda:dict(arming_state=1,landed=True),1010000,1300000,now=lambda:clock[0],sleep=sleep)
        self.assertGreaterEqual(clock[0],15)

    def test_rearm_contact_loss_failsafe_rejected(self):
        for state in (dict(arming_state=2,landed=True),dict(arming_state=1,landed=False),dict(arming_state=1,landed=True,failsafe=True)):
            with self.assertRaises(ValueError): collect(lambda:self.fixture()[0],lambda:state,1010000,1300000)

    def test_fault_not_fixed_by_complete_tail(self):
        log,tables=self.fixture(); tables['vehicle_imu',2]['delta_velocity_clipping'][10]=4
        with self.assertRaisesRegex(ValueError,'clipping'):
            collect(lambda:log,lambda:dict(arming_state=1,landed=True),1010000,1300000)

    def test_missing_start_topic_or_duplicate_never_pending(self):
        for action in ('start','missing','duplicate'):
            log,tables=self.fixture()
            if action=='missing': del tables['vehicle_imu',1]
            elif action=='start': tables['sensor_accel',0]['timestamp']+=1000000
            else: tables['estimator_selector_status',0]['timestamp'][10]=1036000
            with self.assertRaises((KeyError,ValueError)): complete_tail(log,1010000,1300000)

    def test_real_failure_only_selector_tail_missing(self):
        root=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260928/V06/soft_landing/series01/run02')
        r=json.loads((root/'result.json').read_text()); e={x['name']:x['timestamp_us'] for x in r['events']}
        u=ULog(max(r['logs'],key=lambda x:x['bytes'])['archive'])
        self.assertEqual(complete_tail(u,e['land_command'],e['landed_disarmed']),['estimator_selector_status:0'])


if __name__=='__main__': unittest.main()
