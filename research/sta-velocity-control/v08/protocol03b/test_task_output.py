import copy
import sys
import unittest
from types import SimpleNamespace
import numpy as np
import common
import task
import run

class TaskOutputTests(unittest.TestCase):
    def fixture(self):
        n=9000;t=np.arange(n,dtype=np.uint64)*10000+1000000
        d=dict(timestamp=t.copy(),attitude_timestamp=t.copy(),excitation_time=np.arange(n)*.01-12)
        a=dict(timestamp=t.copy())
        for i in range(4):d[f'q_sp[{i}]']=np.full(n,float(i==0));a[f'q_d[{i}]']=d[f'q_sp[{i}]'].copy()
        return d,a,int(t[0]),int(t[-1]+10000)

    def remove(self,a,indices):return {k:np.delete(v,indices) for k,v in a.items()}

    def test_complete_and_single_missing_output(self):
        d,a,start,end=self.fixture();di,ai,e=task.matched_attitude(d,a,start,end)
        self.assertEqual(e['coverage'],1);self.assertEqual(e['missing_count'],0)
        a=self.remove(a,[2082]);di,ai,e=task.matched_attitude(d,a,start,end)
        self.assertEqual(e['missing_count'],1);self.assertNotIn(2082,di)
        self.assertEqual(len(di),8999);self.assertEqual(e['max_abs_error'],0)

    def test_exact_coverage_boundary_and_neighbor(self):
        d,a,start,end=self.fixture();removed=np.arange(0,9000,5)
        _,_,e=task.matched_attitude(d,self.remove(a,removed),start,end);self.assertEqual(e['coverage'],.8)
        with self.assertRaises(ValueError):task.matched_attitude(d,self.remove(a,np.r_[removed,1]),start,end)

    def test_window_edges_exact_quarter_second_and_neighbor(self):
        d,a,start,end=self.fixture()
        for ids in (np.arange(25),np.arange(8975,9000)):
            task.matched_attitude(d,self.remove(a,ids),start,end)
        for ids in (np.arange(26),np.arange(8974,9000)):
            with self.assertRaises(ValueError):task.matched_attitude(d,self.remove(a,ids),start,end)

    def test_interior_gap_and_subwindow_failure(self):
        d,a,start,end=self.fixture()
        with self.assertRaises(ValueError):task.matched_attitude(d,self.remove(a,np.arange(2000,2026)),start,end)
        # Overall>80%, but one32s task window<80%; must not hide it globally.
        ids=np.arange(1200,4400,4)
        with self.assertRaises(ValueError):task.matched_attitude(d,self.remove(a,ids),start,end)

    def test_duplicate_backward_and_zero_timestamps_rejected(self):
        for which in ('output','request'):
            for kind in ('duplicate','backward','zero'):
                d,a,start,end=self.fixture();t=a['timestamp'] if which=='output' else d['attitude_timestamp']
                t[500]=t[499] if kind=='duplicate' else (t[499]-1 if kind=='backward' else 0)
                with self.assertRaises(ValueError):task.matched_attitude(d,a,start,end)

    def test_matched_geometry_and_nonfinite_unmatched_rejected(self):
        d,a,start,end=self.fixture();a['q_d[0]'][100]=.5
        with self.assertRaises(ValueError):task.matched_attitude(d,a,start,end)
        d,a,start,end=self.fixture();d['q_sp[0]'][100]=np.nan;a=self.remove(a,[100])
        with self.assertRaises(ValueError):task.matched_attitude(d,a,start,end)

    def test_consumed_source_stays_complete_and_unambiguous(self):
        src=dict(timestamp=np.array([1,2,3],dtype=np.uint64));x={k:src['timestamp'].copy() for k in ('timestamp','input_timestamp','setpoint_timestamp')}
        task.consumed_targets(src,x)
        with self.assertRaises(ValueError):task.consumed_targets(dict(timestamp=np.array([1,3],dtype=np.uint64)),x)
        with self.assertRaises(ValueError):task.consumed_targets(dict(timestamp=np.array([1,2,2,3],dtype=np.uint64)),x)

    def test_actual_runtime_uses_new_task_and_no_controller_changes(self):
        self.assertEqual(task.__file__,str(common.CONFIG/'task.py'))
        self.assertIs(sys.modules['task'],task)
        self.assertEqual(run.runtime.CONFIG,common.CONFIG)

    def full_fixture(self,mode):
        d,a,start,end=self.fixture();t=d['timestamp'];n=len(t);o=task.offsets(mode,d['excitation_time'])
        d['input_timestamp']=t.copy();d['setpoint_timestamp']=t.copy()
        src=dict(timestamp=t.copy(),x=np.zeros(n),y=np.zeros(n),z=np.full(n,-2.5),
                 vx=np.zeros(n),vy=np.zeros(n),yaw=np.zeros(n),yawspeed=np.zeros(n),
                 **{'acceleration[0]':np.zeros(n),'acceleration[1]':np.zeros(n)})
        for field,value in [('p_sp',o['p']),('v_ff',o['v']),('a_ff',o['a'])]:
            for i in (0,1):d[f'{field}[{i}]']=value[:,i].copy()
        d['p_sp[2]']=src['z'].copy();a['yaw_body']=o['yaw'].copy();a['yaw_sp_move_rate']=o['yaw_rate'].copy()
        job=dict(task={5:'hover',6:'figure8',7:'heading'}[mode],parameters={'MPC_VCT_TEST':mode})
        return d,a,src,dict(hover_start=start,hover_end=end),job

    def check_full(self,d,a,src,events,job):
        datasets={'trajectory_setpoint':src,'vehicle_attitude_setpoint':a}
        u=SimpleNamespace(get_dataset=lambda name:SimpleNamespace(data=datasets[name]))
        return task.check_targets(u,d,events,job)

    def test_actual_task_chain_all_tasks_with_missing_output(self):
        for mode in (5,6,7):
            d,a,s,e,j=self.full_fixture(mode);a=self.remove(a,[2082])
            result=self.check_full(d,a,s,e,j)
            self.assertEqual(result['attitude_task_output']['missing_count'],1)
            self.assertEqual(result['yaw_request_error_max'],0)

    def test_actual_task_chain_wrong_yaw_ff_and_missing_consumed_source_reject(self):
        for kind in ('yaw','ff','source','unrecorded_nan_request'):
            d,a,s,e,j=self.full_fixture(7);a=self.remove(a,[2082])
            if kind=='yaw':a['yaw_body'][100]+=1e-4
            if kind=='ff':a['yaw_sp_move_rate'][100]+=1e-4
            if kind=='source':s=self.remove(s,[2082])
            if kind=='unrecorded_nan_request':s['yaw'][2082]=np.nan
            with self.assertRaises(ValueError):self.check_full(d,a,s,e,j)

if __name__=='__main__':unittest.main(verbosity=2)
