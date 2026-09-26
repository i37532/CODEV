"""Offline revised-clock positives/negatives. No flight or historical regrading."""
import copy
import io
import math
import struct
import unittest
import numpy as np
from pyulog import ULog
from test_v04_protocol04 import fixture, Log
from v04_heading_stream import data, replay
from v04_attitude_clock09 import (AttitudeClockPolicy, clock, strict_clock,
                                 unique_previous, exact_output_match)


def attitude(p=(90000,100000,100000,104000), s=(90000,96000,100000,104000)):
    n = len(p)
    d = dict(timestamp=np.array(p,np.uint64), timestamp_sample=np.array(s,np.uint64),
             quat_reset_counter=np.full(n,2,np.uint8))
    for prefix in ('q','delta_q_reset'):
        for i in range(4): d[f'{prefix}[{i}]']=np.full(n,float(i==0),np.float32)
    return d


def targets():
    t=np.arange(70000,140001,1000,dtype=np.uint64)
    return dict(timestamp=t,yaw_body=np.zeros(len(t)))


def heading_fixture():
    log, ref = fixture()
    a = log.tables[('vehicle_attitude',0)]
    for k,v in list(a.items()): a[k]=np.r_[v[0],v]
    a['timestamp'][0]=990000
    a['timestamp_sample']=a['timestamp'].copy()
    for i in range(4): a[f'q[{i}]']=np.full(len(a['timestamp']),float(i==0))
    return log,ref


class AttitudeClock09Test(unittest.TestCase):
    def setUp(self): self.policy=AttitudeClockPolicy()

    def test_replay_resolves_historical_inheritance_without_running_jobs(self):
        from replay_v04_clock09 import historical_protocol
        for n in (1,3,4,5,6,7,8):
            p=historical_protocol(n)
            self.assertIn('startup_overrides',p)
            self.assertEqual(len(p['jobs']),6)
        with self.assertRaises(ValueError):historical_protocol(2)

    def test_int64_boundary_without_float_rounding(self):
        self.assertEqual(int(clock(np.array([2**63-1],np.int64))[0]),2**63-1)
        for v in ([0],[-1],[True],[1.0],[float('nan')],[float('inf')],[2**63],[],[[1]]):
            with self.subTest(v=v),self.assertRaises(ValueError): clock(v)

    def test_equal_publish_positive_sample_preserves_every_column(self):
        a=attitude(); old=copy.deepcopy(a)
        log=Log({('vehicle_attitude',0):a})
        self.assertIs(self.policy.data(log),a)
        for k in a: np.testing.assert_array_equal(old[k],a[k])
        self.assertEqual(self.policy.candidates(a,100000)[0].tolist(),[1,2])

    def test_old_accessor_remains_strict(self):
        with self.assertRaisesRegex(ValueError,'nonmonotonic'):
            data(Log({('vehicle_attitude',0):attitude()}),'vehicle_attitude')

    def test_whitelist_does_not_extend_to_other_topics(self):
        for name in ('vehicle_local_position','vehicle_attitude_setpoint','sta_rate_ctrl_status',
                     'sta_velocity_ctrl_status','actuator_controls_0','estimator_attitude'):
            with self.subTest(name=name),self.assertRaises(ValueError):
                self.policy.data(Log({(name,0):attitude()}),name)
        with self.assertRaisesRegex(ValueError,'instance 0'):
            self.policy.data(Log({('vehicle_attitude',1):attitude()}),'vehicle_attitude',1)

    def test_missing_sample_never_fabricated(self):
        a=attitude();del a['timestamp_sample']
        with self.assertRaises(KeyError):self.policy.validate(a)

    def test_sample_duplicate_or_backward_rejected(self):
        for value in (96000,95000):
            a=attitude();a['timestamp_sample'][2]=value
            with self.assertRaises(ValueError): self.policy.validate(a)

    def test_publication_backward_rejected(self):
        a=attitude();a['timestamp'][2]=99000
        with self.assertRaisesRegex(ValueError,'Backward'): self.policy.validate(a)

    def test_future_sample_rejected(self):
        a=attitude();a['timestamp_sample'][-1]=104001
        with self.assertRaisesRegex(ValueError,'Future'):self.policy.validate(a)

    def test_existing_freshness_bound_at_and_above(self):
        a=attitude((100000,100000),(80000,100000));self.policy.validate(a)
        a['timestamp_sample'][0]=79999
        with self.assertRaisesRegex(ValueError,'Stale'):self.policy.validate(a)

    def test_malformed_columns_rejected(self):
        a=attitude();a['q[0]']=a['q[0]'][:-1]
        with self.assertRaises(ValueError):self.policy.validate(a)

    def test_nonfinite_first_tied_row_cannot_hide(self):
        for k in ('q[1]','delta_q_reset[2]'):
            a=attitude();a[k][1]=np.nan
            with self.subTest(k=k),self.assertRaisesRegex(ValueError,'Nonfinite'):self.policy.validate(a)

    def test_reset_counter_invalid_rejected(self):
        for c in ([-1]*4,[256]*4,[2.]*4):
            a=attitude();a['quat_reset_counter']=np.array(c)
            with self.assertRaises(ValueError):self.policy.validate(a)

    def test_window_has_predecessor_and_full_start_and_end_groups(self):
        a=attitude((90000,100000,100000,104000,104000),(90000,96000,100000,102000,104000))
        self.assertEqual(self.policy.window(a,100000,104000).tolist(),[0,1,2,3,4])
        self.assertEqual(self.policy.window(a,100001,104000).tolist(),[1,2,3,4])

    def test_boundary_missing_predecessor_rejected(self):
        with self.assertRaisesRegex(ValueError,'predecessor'):self.policy.window(attitude(),90000,104000)

    def test_reset_on_first_boundary_row_and_return_not_hidden(self):
        a=attitude();a['quat_reset_counter'][:]=[2,3,2,2]
        self.assertEqual(self.policy.reset_indices(a,100000,104000).tolist(),[1,2])

    def test_reset_at_end_and_wrap_preserved(self):
        a=attitude();a['quat_reset_counter'][:]=[255,255,255,0]
        self.assertEqual(self.policy.reset_indices(a,100000,104000).tolist(),[3])

    def test_pre_window_reset_not_counted_and_no_future_borrow(self):
        a=attitude((90000,100000,100000,104000,108000),(90000,96000,100000,104000,108000))
        a['quat_reset_counter'][:]=[2,3,3,3,4]
        self.assertEqual(self.policy.reset_indices(a,100001,107999).tolist(),[])
        self.assertNotIn(4,self.policy.window(a,100000,107999))

    def test_empty_backwards_and_stale_window_rejected(self):
        for start,end in ((104000,100000),(100000,125000),(1,100000)):
            with self.subTest(bounds=(start,end)),self.assertRaises(ValueError):self.policy.window(attitude(),start,end)

    def test_true_gap_rejected_despite_fresh_endpoints(self):
        a=attitude((90000,100000,400001),(90000,100000,400001))
        with self.assertRaisesRegex(ValueError,'gap'):self.policy.window(a,100000,400001)

    def test_ambiguity_is_not_resolved_by_identical_payload(self):
        with self.assertRaisesRegex(ValueError,'Ambiguous'):self.policy.unique_index(attitude(),100000)
        self.assertEqual(self.policy.unique_index(attitude(),104000).tolist(),[3])

    def test_oldest_group_member_freshness_not_only_last(self):
        a=attitude((80000,100000,100000),(80000,84000,100000))
        self.policy.candidates(a,104000)
        with self.assertRaisesRegex(ValueError,'Stale'):self.policy.candidates(a,104001)

    def test_unique_preceding_target_rejects_duplicate_and_stale(self):
        for p in ([90000,90000],[100000,90000]):
            with self.assertRaises(ValueError):unique_previous(p,[100000])
        with self.assertRaisesRegex(ValueError,'Stale'):unique_previous([70000],[100000])
        with self.assertRaises(ValueError):unique_previous([110000],[100000])

    def test_output_duplicate_diagnostic_or_output_key_rejected(self):
        d=dict(timestamp=np.array([100,200]),link=np.array([100,200]),value=np.zeros(2))
        o=dict(timestamp=np.array([100,100,200]),value=np.array([0.,1.,0.]))
        with self.assertRaises(ValueError):exact_output_match(d,o,'link',[('value','value')],100,201)
        d['link'][1]=100;o=dict(timestamp=np.array([100,200]),value=np.zeros(2))
        with self.assertRaises(ValueError):exact_output_match(d,o,'link',[('value','value')],100,201)

    def test_unique_exact_output_preserves_old_equal_values(self):
        d=dict(timestamp=np.array([100,200]),link=np.array([100,200]),value=np.zeros(2))
        o=dict(timestamp=np.array([100,200]),value=np.zeros(2))
        self.assertEqual(exact_output_match(d,o,'link',[('value','value')],100,201)['coverage'],1)
        o['value'][1]=1
        with self.assertRaises(ValueError):exact_output_match(d,o,'link',[('value','value')],100,201)

    def test_frequency_reports_both_clocks_without_zero_weight(self):
        r,covered=self.policy.topic_rates(attitude(),np.ones(4,bool))
        self.assertEqual(r['publication']['dt_min_s'],0)
        self.assertGreater(r['sample']['dt_min_s'],0)
        self.assertFalse(covered);self.assertEqual(r['equal_publish'],1)

    def test_yaw_metric_keeps_every_tied_record_weight(self):
        a=attitude();a['q[0]'][1]=math.cos(.1);a['q[3]'][1]=math.sin(.1)
        r=self.policy.yaw_metrics(a,targets(),100000,104000)
        self.assertEqual(r['records'],2)
        self.assertAlmostEqual(r['stats']['rmse'],.2/math.sqrt(2),places=6)

    def test_tilt_violation_first_or_last_boundary_tie_rejected(self):
        for i in (1,2,3):
            a=attitude();a['q[0]'][i]=math.cos(.2);a['q[1]'][i]=math.sin(.2)
            with self.subTest(i=i),self.assertRaisesRegex(ValueError,'tilt'):self.policy.safety(a,targets(),100000,104000)

    def test_yaw_violation_or_nonfinite_target_rejected(self):
        a=attitude();a['q[0]'][1]=math.cos(.3);a['q[3]'][1]=math.sin(.3)
        with self.assertRaisesRegex(ValueError,'Yaw'):self.policy.safety(a,targets(),100000,104000)
        t=targets();t['yaw_body'][:]=np.nan
        with self.assertRaises(ValueError):self.policy.safety(attitude(),t,100000,104000)

    def test_heading_legacy_and_new_identical_without_ties(self):
        log,ref=heading_fixture()
        self.assertEqual(replay(log,ref),replay(log,ref,attitude_policy=self.policy))

    def test_heading_tied_reset_detected_and_legacy_still_rejects(self):
        log,ref=heading_fixture();a=log.tables[('vehicle_attitude',0)]
        a['timestamp'][50]=a['timestamp'][51]
        with self.assertRaises(ValueError):replay(log,ref)
        r=replay(log,ref,attitude_policy=self.policy);self.assertTrue(r['ready'])
        a['quat_reset_counter'][50]=4
        with self.assertRaisesRegex(ValueError,'Repeated'):replay(log,ref,attitude_policy=self.policy)

    def test_heading_reset_at_window_start_not_hidden(self):
        log,ref=heading_fixture();a=log.tables[('vehicle_attitude',0)]
        a['quat_reset_counter'][1]=3
        with self.assertRaisesRegex(ValueError,'Repeated'):replay(log,ref,attitude_policy=self.policy)

    def test_heading_reset_after_freeze_rejected(self):
        log,ref=heading_fixture();f=replay(log,ref,attitude_policy=self.policy)['freeze_candidate']
        a=log.tables[('vehicle_attitude',0)];a['quat_reset_counter'][-1]=4
        with self.assertRaises(ValueError):replay(log,ref,frozen=f,attitude_policy=self.policy)

    def test_original_safety_faults_remain_rejected_under_new_policy(self):
        for name,key,value in [('estimator_selector_status','primary_instance',2),
                ('vehicle_local_position','ref_timestamp',1),('sta_velocity_ctrl_status','first_fail',1),
                ('sta_velocity_ctrl_status','inner_mode',1),('vehicle_status','failsafe',1)]:
            log,ref=heading_fixture();log.tables[(name,0)][key][100]=value
            with self.subTest(key=key),self.assertRaises(ValueError):replay(log,ref,attitude_policy=self.policy)

    def test_typed_binary_ulog_keeps_equal_publish_records(self):
        a=attitude()
        def msg(k,b):return struct.pack('<HB',len(b),ord(k))+b
        fields='uint64_t timestamp;uint64_t timestamp_sample;uint8_t quat_reset_counter;'
        fields+=''.join(f'float {k};' for k in a if k not in ('timestamp','timestamp_sample','quat_reset_counter'))
        blob=ULog.HEADER_BYTES+b'\x01'+struct.pack('<Q',0)
        blob+=msg('F',('vehicle_attitude:'+fields).encode())
        blob+=msg('A',struct.pack('<BH',0,1)+b'vehicle_attitude')
        for i in range(4):
            blob+=msg('D',struct.pack('<HQQB8f',1,*[v[i].item() for v in a.values()]))
        u=ULog(io.BytesIO(blob));actual=self.policy.data(u)
        for k in a:np.testing.assert_array_equal(a[k],actual[k])
        self.assertEqual(len(actual['timestamp']),4)


if __name__=='__main__':unittest.main()
