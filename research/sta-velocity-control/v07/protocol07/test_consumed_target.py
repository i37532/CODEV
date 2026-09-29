"""Exact source identity, negative clocks, unchanged numeric target checks."""
import copy
import unittest
import numpy as np
from task import consumed_targets,check_targets,offsets

class ConsumedTargetTest(unittest.TestCase):
    def fixture(self):
        return {'timestamp':np.array([10000,20000,30000,40000])},dict(
            timestamp=np.array([21000,31000,41000]),input_timestamp=np.array([18000,28000,38000]),
            setpoint_timestamp=np.array([20000,30000,40000]))

    def test_newer_than_position_but_exact_consumed_source(self):
        s,x=self.fixture();j,age=consumed_targets(s,x)
        np.testing.assert_array_equal(j,[1,2,3]);np.testing.assert_array_equal(age,[1000]*3)

    def test_reused_consumed_target_is_valid(self):
        s,x=self.fixture();x['setpoint_timestamp'][:]=20000
        np.testing.assert_array_equal(consumed_targets(s,x)[0],[1,1,1])

    def test_exact_40ms_boundary_and_neighbor(self):
        s,x=self.fixture();x={k:v[:1] for k,v in x.items()};x['timestamp'][0]=60000
        self.assertEqual(consumed_targets(s,x)[1][0],40000)
        x['timestamp'][0]+=1
        with self.assertRaisesRegex(ValueError,'Stale'):consumed_targets(s,x)

    def test_missing_source_no_nearest_fallback(self):
        s,x=self.fixture();s['timestamp']=np.array([10000,30000,40000])
        with self.assertRaisesRegex(ValueError,'Missing exact'):consumed_targets(s,x)

    def test_future_target_relative_to_publication_rejected(self):
        s,x=self.fixture();x['timestamp'][0]=19999
        with self.assertRaisesRegex(ValueError,'Future'):consumed_targets(s,x)

    def test_future_input_rejected(self):
        s,x=self.fixture();x['input_timestamp'][0]=21001
        with self.assertRaisesRegex(ValueError,'Future'):consumed_targets(s,x)

    def test_same_time_ambiguity_never_deduplicated(self):
        s,x=self.fixture();s['timestamp']=np.array([10000,20000,20000,30000,40000])
        with self.assertRaisesRegex(ValueError,'Ambiguous'):consumed_targets(s,x)

    def test_backward_source_or_consumption_rejected(self):
        for key in ('source','setpoint_timestamp','timestamp','input_timestamp'):
            s,x=self.fixture()
            if key=='source':s['timestamp'][2]=19999
            else:x[key][1]=x[key][0]-1
            with self.subTest(key=key),self.assertRaises(ValueError):consumed_targets(s,x)

    def test_noninteger_nonfinite_zero_clocks_rejected(self):
        for value in (0,-1,float('nan'),float('inf'),20000.5):
            s,x=self.fixture();x['setpoint_timestamp']=x['setpoint_timestamp'].astype(float);x['setpoint_timestamp'][0]=value
            with self.subTest(value=value),self.assertRaises(ValueError):consumed_targets(s,x)

    def task_fixture(self):
        n=9000;t=np.arange(n)*10000+1000000;c=t+4000
        d=dict(timestamp=c,timestamp_sample=t,input_timestamp=t,setpoint_timestamp=c,
               attitude_timestamp=c,excitation_time=np.arange(n)*.01-12)
        src={'timestamp':c,'x':np.zeros(n),'y':np.zeros(n),'z':-2+np.arange(n)*1e-5,
             'vx':np.zeros(n),'vy':np.zeros(n),'acceleration[0]':np.zeros(n),
             'acceleration[1]':np.zeros(n),'yaw':np.full(n,.5),'yawspeed':np.zeros(n)}
        o=offsets(6,d['excitation_time'])
        for field,add in [('p_sp',o['p']),('v_ff',o['v']),('a_ff',o['a'])]:
            for i in (0,1):d[f'{field}[{i}]']=add[:,i].copy()
        d['p_sp[2]']=src['z'].copy()
        attitude=dict(timestamp=c,yaw_body=src['yaw'].copy(),yaw_sp_move_rate=np.zeros(n))
        class Dataset:
            def __init__(self,data):self.data=data
        class Log:
            def get_dataset(self,name):return Dataset(src if name=='trajectory_setpoint' else attitude)
        return Log(),d,dict(hover_start=int(c[0]),hover_end=int(c[-1])+1),dict(task='figure8',parameters={'MPC_VCT_TEST':6})

    def test_full_task_newer_targets_and_numeric_ff_once(self):
        u,d,e,j=self.task_fixture();r=check_targets(u,d,e,j)
        self.assertEqual(r['samples'],9000);self.assertEqual(r['source_after_position_samples'],9000)
        self.assertLessEqual(max(r['maximum_target_error']['a_ff']),2e-6)

    def test_wrong_z_still_rejected(self):
        u,d,e,j=self.task_fixture();d['p_sp[2]'][100]+=1e-4
        with self.assertRaisesRegex(ValueError,'Z target'):check_targets(u,d,e,j)

    def test_wrong_xy_ff_or_yaw_still_rejected(self):
        for key in ('p_sp[0]','v_ff[1]','a_ff[0]'):
            u,d,e,j=self.task_fixture();d[key][100]+=1e-4
            with self.subTest(key=key),self.assertRaises(ValueError):check_targets(u,d,e,j)
        u,d,e,j=self.task_fixture();u.get_dataset('vehicle_attitude_setpoint').data['yaw_body'][100]+=.001
        with self.assertRaisesRegex(ValueError,'heading'):check_targets(u,d,e,j)

if __name__=='__main__':unittest.main(verbosity=2)
