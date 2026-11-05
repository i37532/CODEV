import copy
import unittest
import numpy as np
import test_v03 as reference
from analyze_v04 import check_diagnostic, compare


class V04AnalysisTest(unittest.TestCase):
    def data(self,mode):
        d=reference.DiagnosticTest().data(); n=len(d['timestamp'])
        for k in ('sta_fault','sta_flags','config_pending','committed_axes','config_generation'):
            d[k]=np.zeros(n,dtype=np.uint32)
        d['pid_axes']=np.full(n,7 if mode==0 else 6)
        for i in range(3): d[f'a_ff[{i}]']=np.full(n,np.nan)
        for k in ('requested_mode','effective_mode','requested_axes','effective_axes','active_axes','committed_axes'):
            d[k][:]=mode
        if mode:
            for k in ('nu_before','nu_ideal','nu_applied','a_sta'): d[k+'[0]'][:]=0
        return d

    def test_pid_and_esta_windows(self):
        for mode in (0,1):
            r=check_diagnostic(self.data(mode),1000000,61000000,mode)
            self.assertEqual(r['samples'],3200)

    def test_wrong_algorithm_axis_inner_and_lifecycle(self):
        for key in ('effective_mode','effective_axes','pid_axes','committed_axes','inner_mode','sta_fault','config_pending','sta_flags'):
            d=self.data(1); d[key][100]+=1
            with self.subTest(key=key), self.assertRaises(ValueError): check_diagnostic(d,1000000,61000000,1)

    def test_stale_or_fake_candidate_rejected(self):
        for key in ('nu_before[0]','nu_ideal[0]','nu_applied[0]','a_sta[0]','a_req[0]','nu_applied[1]'):
            d=self.data(1); d[key][100]=.1
            with self.subTest(key=key), self.assertRaises(ValueError): check_diagnostic(d,1000000,61000000,1)

    def test_time_missing_and_boundary_rejected(self):
        for mode in (0,1):
            d={k:np.delete(v,100) for k,v in self.data(mode).items()}
            with self.assertRaises(ValueError): check_diagnostic(d,1000000,61000000,mode)
            with self.assertRaises(ValueError): check_diagnostic(self.data(mode),1000000,31000000,mode)

    def test_pair_noncommand_axis_and_near_zero_rule(self):
        pid=dict(accepted=True,job=dict(seed=9101,mode=0),diagnostic=dict(error=dict(rmse=[0.,0.,0.])),position_rmse=[0.,0.,0.],yaw_rmse=0.)
        esta=copy.deepcopy(pid); esta['job']['mode']=1
        esta['diagnostic']['error']['rmse']=[.02,.02,.01]
        self.assertTrue(compare(pid,esta)['accepted'])
        esta['diagnostic']['error']['rmse'][1]=.02001
        self.assertFalse(compare(pid,esta)['accepted'])
        esta['job']['seed']=9102
        with self.assertRaises(ValueError): compare(pid,esta)


if __name__=='__main__': unittest.main()
