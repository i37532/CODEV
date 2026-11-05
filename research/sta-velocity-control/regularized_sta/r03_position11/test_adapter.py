import copy
import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
import numpy as np
from test_v04_protocol04 import fixture as old_fixture
from v04_heading_stream import row
from v04_task04 import freeze_reference
from v04_attitude_clock09 import AttitudeClockPolicy

spec=importlib.util.spec_from_file_location('position_adapter_test',Path(__file__).with_name('adapter.py'))
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)


def fixture():
    log,unused=old_fixture();p=log.tables[('vehicle_local_position',0)]
    p['z'][:20]=0
    ref=freeze_reference(row(p,10))
    attitude=log.tables[('vehicle_attitude',0)]
    attitude['timestamp_sample']=attitude['timestamp'].copy()
    for i,val in enumerate((math.cos(.5),0.,0.,math.sin(.5))):
        attitude[f'q[{i}]']=np.full(len(p['timestamp']),val)
    return log,ref


def tie(log,index=100):
    p=log.tables[('vehicle_local_position',0)];d=log.tables[('sta_velocity_ctrl_status',0)]
    p['timestamp'][index]=p['timestamp'][index+1]
    d['timestamp'][index]=p['timestamp'][index];d['input_timestamp'][index]=p['timestamp'][index]


class AdapterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.h=a.build_heading()
    def replay(self,log,ref,**kw):return self.h.replay(log,ref,attitude_policy=AttitudeClockPolicy(),**kw)
    def test_untied_heading(self):
        log,ref=fixture();self.assertTrue(self.replay(log,ref)['ready'])
    def test_tied_heading_and_callback(self):
        log,ref=fixture();tie(log);r=self.replay(log,ref)
        self.assertTrue(r['ready']);self.assertEqual(r['position_samples'],291)
    def test_missing_tied_consumed_sample(self):
        log,ref=fixture();tie(log);p=log.tables[('vehicle_local_position',0)]
        log.tables[('vehicle_local_position',0)]={k:np.delete(v,100) for k,v in p.items()}
        with self.assertRaisesRegex(ValueError,'pair'):self.replay(log,ref)
    def test_hidden_first_tied_coordinate_reset(self):
        log,ref=fixture();tie(log);log.tables[('vehicle_local_position',0)]['xy_reset_counter'][100]=1
        with self.assertRaisesRegex(ValueError,'Coordinate/reset'):self.replay(log,ref)
    def test_hidden_second_tied_coordinate_reset(self):
        log,ref=fixture();tie(log);log.tables[('vehicle_local_position',0)]['z_reset_counter'][101]=1
        with self.assertRaisesRegex(ValueError,'Coordinate/reset'):self.replay(log,ref)
    def test_heading_reset_transient_inside_tie(self):
        log,ref=fixture();tie(log);log.tables[('vehicle_local_position',0)]['heading_reset_counter'][100]+=1
        with self.assertRaisesRegex(ValueError,'Repeated'):self.replay(log,ref)
    def test_invalid_first_tied_estimate(self):
        log,ref=fixture();tie(log);log.tables[('vehicle_local_position',0)]['xy_valid'][100]=0
        with self.assertRaisesRegex(ValueError,'Invalid'):self.replay(log,ref)
    def test_fault_first_tied_callback(self):
        log,ref=fixture();tie(log);log.tables[('sta_velocity_ctrl_status',0)]['fault'][100]=1
        with self.assertRaisesRegex(ValueError,'Controller fault'):self.replay(log,ref)
    def test_missing_tied_callback_seq(self):
        log,ref=fixture();tie(log);log.tables[('sta_velocity_ctrl_status',0)]['publish_seq'][101]+=1
        with self.assertRaisesRegex(ValueError,'identity'):self.replay(log,ref)
    def test_wrong_inner_on_tied_callback(self):
        log,ref=fixture();tie(log);log.tables[('sta_velocity_ctrl_status',0)]['inner_mode'][100]=1
        with self.assertRaisesRegex(ValueError,'Controller inner_mode'):self.replay(log,ref)
    def test_unaudited_topic_tie_rejected(self):
        log,ref=fixture();t=log.tables[('vehicle_status',0)]['timestamp'];t[100]=t[101]
        with self.assertRaisesRegex(ValueError,'nonmonotonic vehicle_status'):self.replay(log,ref)
    def test_tied_freeze_sample_required(self):
        log,ref=fixture();tie(log,299);r=self.replay(log,ref);f=r['freeze_candidate']
        self.assertTrue(self.replay(log,ref,frozen=f)['ready'])
        f['timestamp_sample']-=1
        with self.assertRaisesRegex(ValueError,'Freeze'):self.replay(log,ref,frozen=f)
    def test_opening_reset_not_hidden(self):
        log,ref=fixture();log.tables[('vehicle_local_position',0)]['xy_reset_counter'][9]=1
        with self.assertRaisesRegex(ValueError,'opening reset'):self.replay(log,ref)
    def test_last_group_sealed_by_both_topics(self):
        log,ref=fixture();p=log.tables[('vehicle_local_position',0)];p['timestamp'][-2]=p['timestamp'][-1]
        self.assertEqual(self.h.sealed_time(log),int(p['timestamp'][-3]))
    def test_no_duplicate_groups_discarded(self):
        log,ref=fixture();tie(log);before=copy.deepcopy(log.tables)
        self.replay(log,ref)
        for key in before:
            for field in before[key]:np.testing.assert_array_equal(before[key][field],log.tables[key][field])
    def test_rewrite_missing_pattern_rejected(self):
        with self.assertRaisesRegex(ValueError,'replacement count'):
            a.rewrite(a.load('reference',a.SCRIPTS/'v04_prearm17.py').reference_row,[("123456","42",True)])
    def test_new_attitude_policy_preserves_geometry(self):
        policy=a.build_attitude_policy()()
        self.assertEqual(policy.validate.__func__.__code__.co_code,AttitudeClockPolicy.validate.__code__.co_code)
        log,ref=fixture();d=log.tables[('vehicle_attitude',0)]
        target=dict(timestamp=d['timestamp'].copy(),yaw_body=np.ones(len(d['timestamp'])))
        target['timestamp'][100]=target['timestamp'][101]
        self.assertGreater(policy.safety(d,target,1100000,4000000)['records'],0)
        target['yaw_body'][100]=2
        with self.assertRaisesRegex(ValueError,'Ambiguous'):policy.safety(d,target,1100000,4000000)


if __name__=='__main__':unittest.main(verbosity=2)
