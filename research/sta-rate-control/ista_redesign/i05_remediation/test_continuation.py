import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.append(str(Path(__file__).resolve().parents[1]/'i05'))
from logging_acceptance import validate
from continue_rc import plan,execute_pending


class LoggingTest(unittest.TestCase):
    def fixture(self,div=2):
        n=10032;t=np.arange(1,n+1,dtype=np.int64)*4000
        up=np.arange(n)%div==0
        d=dict(timestamp_sample=t,updated=up,held=~up,output_valid=np.ones(n,dtype=bool),thrust=np.full(n,.5,dtype=np.float32),
               research_yaw_addition=np.sin(np.arange(n)*.1))
        for i in range(3):d[f'c_applied[{i}]']=np.full(n,.01*i,dtype=np.float32)
        a=dict(timestamp_sample=t.copy())
        for i in range(3):a[f'control[{i}]']=d[f'c_applied[{i}]'].copy()
        a['control[3]']=d['thrust'].copy()
        masks=dict(flight=np.ones(n,dtype=bool),yaw_only=np.arange(n)<3000)
        return d,a,masks

    def test_missing_is_disclosed(self):
        d,a,m=self.fixture();a={k:np.delete(v,7) for k,v in a.items()}
        r=validate(d,a,m,2,{'yaw_only':(2,)})
        self.assertEqual(r['windows']['flight']['held']['missing'],1)

    def test_held_thrust_mismatch(self):
        d,a,m=self.fixture();a['control[3]'][7]=.7
        with self.assertRaisesRegex(ValueError,'mismatch'):validate(d,a,m,2,{})

    def test_empty_reverse_duplicate_unmatched_nonfinite(self):
        for kind in ('empty','reverse','duplicate','unmatched','nan'):
            with self.subTest(kind=kind):
                d,a,m=self.fixture()
                if kind=='empty':a={k:v[:0] for k,v in a.items()}
                if kind=='reverse':a={k:v[::-1] for k,v in a.items()}
                if kind=='duplicate':a['timestamp_sample'][2]=a['timestamp_sample'][1]
                if kind=='unmatched':a['timestamp_sample'][2]+=1
                if kind=='nan':a['control[0]'][7]=np.nan
                with self.assertRaises(ValueError):validate(d,a,m,2,{})

    def test_window_and_sign_coverage(self):
        d,a,m=self.fixture();m['empty']=np.zeros(len(d['updated']),dtype=bool)
        with self.assertRaisesRegex(ValueError,'No matched updates'):validate(d,a,m,2,{})
        del m['empty'];d['research_yaw_addition'][:]=1
        with self.assertRaisesRegex(ValueError,'negative'):validate(d,a,m,2,{'yaw_only':(2,)})


class BatchTest(unittest.TestCase):
    def test_ledger_and_all_17(self):
        _,pending=plan('f'*40);called=[];gates=[]
        def run(j):called.append(j['original_index']);return {'success':True}
        def gate(rows,div):gates.append((len(rows),div));return {'success':True}
        rows=execute_pending(pending,{'success':True},run,lambda *args:None,gate)
        self.assertEqual(called,list(range(1,18)));self.assertEqual(len(rows),18)
        self.assertEqual(gates,[(6,1),(12,2),(18,4)])

    def test_failure_stops_first(self):
        _,pending=plan('f'*40);called=[]
        def run(j):called.append(j['original_index']);return {'success':False}
        with self.assertRaises(RuntimeError):execute_pending(pending,{'success':True},run,lambda *args:None)
        self.assertEqual(called,[1])

    def test_gate_failure_stops_before_div2(self):
        _,pending=plan('f'*40);called=[]
        def run(j):called.append(j['original_index']);return {'success':True}
        with self.assertRaises(RuntimeError):execute_pending(pending,{'success':True},run,lambda *args:None,lambda *args:{'success':False})
        self.assertEqual(called,list(range(1,6)))

    def test_failed_first_and_replay_rejected(self):
        _,pending=plan('f'*40)
        def no_run(job):self.fail('must not start flight')
        with self.assertRaises(ValueError):execute_pending(pending,{'success':False},no_run,lambda *args:None)
        pending[0]['original_index']=0
        with self.assertRaises(ValueError):execute_pending(pending,{'success':True},no_run,lambda *args:None)


if __name__=='__main__':unittest.main()
