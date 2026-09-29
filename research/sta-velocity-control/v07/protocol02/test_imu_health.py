import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import common
import sys
sys.path.insert(0,str(common.REPO/'research/sta-velocity-control/v06/soft_landing'))
import imu_health as policy
import test_health


class ImuClock(unittest.TestCase):
    def fixture(self):
        log,tables=test_health.LandingHealth().log()
        for i in range(3):
            d=tables['vehicle_imu',i]; t=d['timestamp']; n=len(t)
            d.update(timestamp_sample=t.copy(),delta_angle_dt=np.full(n,4000),
                     accel_device_id=np.full(n,11+i),gyro_device_id=np.full(n,21+i),calibration_count=np.zeros(n))
            for stem in ('delta_angle','delta_velocity'):
                for axis in range(3): d[f'{stem}[{axis}]']=np.arange(n)*.001+axis
        return log,tables

    def test_ordinary_all_instances(self):
        log,_=self.fixture(); self.assertEqual(len(policy.check_health(log,1010000,1300000)['imu']),3)

    def test_distinct_integrals_same_publication_all_instances(self):
        for i in range(3):
            log,t=self.fixture(); d=t['vehicle_imu',i]; d['timestamp'][10]=d['timestamp'][11]
            r=policy.check_health(log,1010000,1300000)['imu'][str(i)]
            self.assertEqual(r['publication_ties'],1); self.assertEqual(r['max_age_us'],4000)
            self.assertNotEqual(d['delta_angle[0]'][10],d['delta_angle[0]'][11])

    def test_no_mutation_or_deduplication(self):
        log,t=self.fixture(); t['vehicle_imu',0]['timestamp'][10]=1044000
        before=copy.deepcopy(t);policy.check_health(log,1010000,1300000)
        for key in t:
            for field in t[key]: np.testing.assert_array_equal(t[key][field],before[key][field])

    def test_invalid_sample_and_publication_order(self):
        for key,value in [('timestamp',1035000),('timestamp_sample',1036000),('timestamp_sample',0),('timestamp_sample',1044001)]:
            log,t=self.fixture(); t['vehicle_imu',0][key][10]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError): policy.check_health(log,1010000,1300000)

    def test_exact_duplicate_rejected_even_same_payload(self):
        log,t=self.fixture(); d=t['vehicle_imu',0]
        for v in d.values(): v[10]=v[9]
        with self.assertRaises(ValueError): policy.check_health(log,1010000,1300000)

    def test_malformed_clocks_and_rows(self):
        for change in ('float','nan','zero','length','missing'):
            log,t=self.fixture(); d=t['vehicle_imu',0]
            if change=='float': d['timestamp']=d['timestamp'].astype(float)
            elif change=='nan': d['timestamp_sample']=np.full(100,np.nan)
            elif change=='zero': d['timestamp'][0]=0
            elif change=='length': d['delta_angle[0]']=np.zeros(99)
            else: del d['timestamp_sample']
            with self.subTest(change=change),self.assertRaises((ValueError,KeyError)): policy.check_health(log,1010000,1300000)

    def test_other_topics_still_strict(self):
        for name in ('sensor_accel','estimator_status','estimator_selector_status'):
            log,t=self.fixture(); t[name,0]['timestamp'][10]=t[name,0]['timestamp'][9]
            with self.subTest(topic=name),self.assertRaises(ValueError): policy.check_health(log,1010000,1300000)

    def test_each_integration_field_invalid(self):
        for field in ('delta_angle_dt','delta_velocity_dt'):
            for value in (0,-1,12001,np.nan,np.inf):
                log,t=self.fixture();d=t['vehicle_imu',2];d[field]=d[field].astype(float);d[field][10]=value
                with self.subTest(field=field,value=value),self.assertRaises(ValueError): policy.check_health(log,1010000,1300000)

    def test_nonfinite_integral_all_axes(self):
        for stem in ('delta_angle','delta_velocity'):
            for i in range(3):
                log,t=self.fixture(); t['vehicle_imu',1][f'{stem}[{i}]'][10]=np.nan
                with self.assertRaises(ValueError): policy.check_health(log,1010000,1300000)

    def test_calibration_device_and_clipping_in_tied_groups(self):
        for key in ('calibration_count','accel_device_id','gyro_device_id','delta_velocity_clipping'):
            for boundary in (10,75):
                log,t=self.fixture();d=t['vehicle_imu',1];d['timestamp'][boundary-1]=d['timestamp'][boundary];d[key][boundary-1]+=1
                with self.subTest(key=key,boundary=boundary),self.assertRaises(ValueError): policy.check_health(log,1040000,1300000)

    def test_boundary_groups_preserved(self):
        _,t=self.fixture();d=t['vehicle_imu',0];d['timestamp'][9]=1040000;d['timestamp'][74]=1300000
        m=policy.bounds(d,1040000,1300000);self.assertTrue(m[9] and m[10] and m[74] and m[75] and m[76])

    def test_sample_boundary_is_not_replaced_by_publication(self):
        _,t=self.fixture();d=t['vehicle_imu',0];d['timestamp']+=8000
        m=policy.bounds(d,1040000,1300000);self.assertTrue(m[8] and m[75] and m[76])

    def test_gap_exact_limit_and_next_microsecond(self):
        for extra,accepted in ((8000,True),(8001,False)):
            _,t=self.fixture();d=t['vehicle_imu',0]
            for k in ('timestamp','timestamp_sample'):d[k][20:]+=extra
            if accepted:policy.bounds(d,1010000,1300000)
            else:
                with self.assertRaises(ValueError):policy.bounds(d,1010000,1300000)

    def test_age_exact_limit_and_next_microsecond(self):
        for delay,accepted in ((12000,True),(12001,False)):
            _,t=self.fixture();d=t['vehicle_imu',0];d['timestamp']+=delay
            if accepted:policy.bounds(d,1020000,1300000)
            else:
                with self.assertRaises(ValueError):policy.bounds(d,1020000,1300000)

    def test_global_reverse_even_outside_window_rejected(self):
        _,t=self.fixture();d=t['vehicle_imu',0];d['timestamp_sample'][1]=1000000
        with self.assertRaises(ValueError):policy.bounds(d,1040000,1300000)

    def test_missing_start_never_pending(self):
        log,_=self.fixture()
        with self.assertRaises(ValueError):policy.complete_tail(log,999999,1300000)

    def test_unsealed_end_pending_then_complete(self):
        log,t=self.fixture();d=t['vehicle_imu',0]
        for key in d:d[key]=d[key][:76]
        self.assertEqual(policy.complete_tail(log,1010000,1300000),['vehicle_imu:0'])
        with self.assertRaises(ValueError):policy.check_health(log,1010000,1300000)
        full,_=self.fixture();it=iter((log,full));wait=[]
        r=policy.collect(lambda:next(it),lambda:dict(arming_state=1,landed=True),1010000,1300000,sleep=wait.append)
        self.assertEqual(len(wait),1);self.assertFalse(r['snapshots'][-1]['pending'])

    def test_timeout_and_ground_loss_rejected(self):
        log,t=self.fixture();d=t['vehicle_imu',0]
        for key in d:d[key]=d[key][:76]
        timer=[0.]
        def sleep(dt):timer[0]+=dt
        with self.assertRaises(TimeoutError):policy.collect(lambda:log,lambda:dict(arming_state=1,landed=True),1010000,1300000,now=lambda:timer[0],sleep=sleep)
        with self.assertRaises(ValueError):policy.collect(lambda:log,lambda:dict(arming_state=2,landed=True),1010000,1300000)

    def test_missing_instance_and_estimator_fault_still_rejected(self):
        log,t=self.fixture();del t['vehicle_imu',2]
        with self.assertRaises(KeyError):policy.check_health(log,1010000,1300000)
        log,t=self.fixture();t['estimator_status',5]['filter_fault_flags'][10]=1
        with self.assertRaises(ValueError):policy.check_health(log,1010000,1300000)

    def test_runner_and_final_analyzer_same_policy(self):
        import run,analyze
        self.assertIs(run.collect_tail,policy.collect);self.assertIs(analyze.check_health,policy.check_health)


if __name__=='__main__':unittest.main(verbosity=2)
