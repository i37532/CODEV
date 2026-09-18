#!/usr/bin/env python3
import unittest
import numpy as np
from audit_actuator_logging import coverage


class CoverageTest(unittest.TestCase):
    def fixture(self):
        t=np.arange(1,7,dtype=np.int64)*4000
        d=dict(timestamp_sample=t,output_valid=np.ones(6,dtype=bool),
               updated=np.array([1,0,1,0,1,0]),held=np.array([0,1,0,1,0,1]),
               thrust=np.arange(6,dtype=np.float32)/10)
        for i in range(3):d[f'c_applied[{i}]']=np.arange(6,dtype=np.float32)+i
        a=dict(timestamp_sample=t.copy())
        for i in range(3):a[f'control[{i}]']=d[f'c_applied[{i}]'].copy()
        a['control[3]']=d['thrust'].copy()
        return d,a

    def test_complete(self):
        d,a=self.fixture();r=coverage(d,a,4000,24000)
        self.assertEqual(r['missing_callbacks'],0)
        self.assertTrue(r['matched_torque_thrust_bitwise_equal'])

    def test_loss_partitions_and_window(self):
        d,a=self.fixture();a={k:v[[0,3,4,5]] for k,v in a.items()}
        r=coverage(d,a,4000,20000)
        self.assertEqual((r['missing_updates'],r['missing_held']),(1,1))
        self.assertEqual(r['callbacks'],5)
        self.assertTrue(r['matched_torque_thrust_bitwise_equal'])

    def test_thrust_mismatch(self):
        d,a=self.fixture();a['control[3]'][3]+=1
        self.assertFalse(coverage(d,a,4000,24000)['matched_torque_thrust_bitwise_equal'])

    def test_no_matches_not_equivalence(self):
        d,a=self.fixture();a['timestamp_sample']+=100000
        r=coverage(d,a,4000,24000)
        self.assertEqual(r['missing_callbacks'],6)
        self.assertFalse(r['matched_torque_thrust_bitwise_equal'])


if __name__=='__main__':unittest.main()
