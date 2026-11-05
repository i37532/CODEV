"""RI06 exact XYZ task/parameter/stop wiring, no live process or parameter writes."""
import copy
import io
import contextlib
import sys
import unittest
from unittest.mock import patch
import bindings as b

p=b.api();a,r,replay=[b.local(n) for n in ('analyzer','runner','replay')]
# Reuse audited synthetic diagnostic fixture generation, not a flight verdict.
old=b.load('fixture_tests',b.STAGE.parent/'ri05/tools/test_tools.py')

def job(gate='TH',mode=4):
    return copy.deepcopy(next(j for j in p.jobs(gate) if j['mode']==mode and j['candidate_index']==1))

def fixture(gate='TH'):
    x,q,_,start,end=old.FIXTURES.fixture(7)
    import numpy as np
    x['inner_timestamp']=x['timestamp_sample'].copy();x['inner_check_timestamp']=x['timestamp_sample'].copy()
    x['inner_seq']=x['publish_seq'].copy();x['inner_reads']=np.ones(len(x['timestamp']),dtype=np.int32)
    x['hover_thrust']=np.full(len(x['timestamp']),.5,dtype=np.float32)
    for axis in range(3):
        x[f'thrust[{axis}]']=(x[f'a_proxy[{axis}]']-(9.80665 if axis==2 else 0))*.5/9.80665
        q[f'ri_thrust_published[{axis}]']=x[f'thrust[{axis}]'].copy()
    return x,q,job(gate),start,end

def metrics(j):return old.metrics(j)

class Wiring(unittest.TestCase):
    def test_actual_xyz_components_H_and_V(self):
        for gate in ('TH','TV'):
            x,q,j,start,end=fixture(gate)
            result,_,_=a.components(x,q,j,start,end,True)
            self.assertTrue(result['cadence']['component_valid'])
            self.assertGreater(result['closed_cache_hte']['eligible_pairs'],700)
    def test_H_explicit_xyz_not_relabel_xy(self):
        j=job();self.assertEqual(a.validate_job(j),('H',7,6,64));j['axes']=3
        with self.assertRaises(ValueError):a.validate_job(j)
    def test_all_candidates_accepted_by_config(self):
        for gate in ('TH','TV'):
            for j in p.jobs(gate):a.validate_job(j)
    def test_full_engine_preserved(self):
        f=a.full_analysis(lambda *args:{});oldf=b.FINAL.full_analysis(lambda *args:{},lambda *args:None)
        for name in ('check_health','check_complete','height_evidence','exact_output_match','r02','ULog'):
            self.assertIs(f.__globals__[name],oldf.__globals__[name])
        self.assertEqual(f.__globals__['spec'](job()),('H',7,6,64))
    def test_flight_and_lifecycle_unchanged(self):
        self.assertIs(r.flight_main.__code__,b.OLD_RUNNER.flight_main.__code__)
        current,prior=r.execution_checks_class(),b.OLD_RUNNER.execution_checks_class()
        self.assertEqual([c.__name__ for c in current.__mro__[1:]],[c.__name__ for c in prior.__mro__])
    def test_mode_axes_inner_wrong_rejected(self):
        for key,value in [('MPC_VC_MODE',3),('MPC_VC_AXES',3),('MC_RTC_MODE',1),('MPC_VC_DIV',2)]:
            j=job();j['parameters'][key]=value
            with self.assertRaises(ValueError):a.validate_job(j)
    def test_unregistered_gain_rejected(self):
        j=job();j['parameters']['MPC_VC_L2_Z']=1.11
        with self.assertRaises(ValueError):a.validate_job(j)
    def test_pair_same_candidate_and_different_algos(self):
        for gate in ('TH','TV'):
            for index in range(3):
                rows=[j for j in p.jobs(gate) if j['candidate_index']==index and j['block']==1]
                pid=metrics(next(j for j in rows if j['mode']==0))
                for j in rows[1:]:
                    result=a.compare(pid,metrics(j));self.assertEqual(len(result['checks']),13)
                    self.assertEqual(result,replay.paired_decision(pid,metrics(j)))
    def test_wrong_candidate_pair_rejected(self):
        x=metrics(job(mode=0));j=next(j for j in p.jobs('TH') if j['mode']==4 and j['candidate_index']==0)
        with self.assertRaises(ValueError):a.compare(x,metrics(j))
    def test_native_old_spec_not_mutated(self):
        self.assertEqual(b.FINAL.targets.SPECS['C'][1],3)
    def test_dryrun_no_execute(self):
        with patch.object(r,'execute_gate',side_effect=AssertionError('flight')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(r.main(['--gate','TH']),0)
    def test_complete18_12pairs(self):
        protocol=p.load_protocol('TH');ledger=dict(attempts=[],pairs=[])
        r.run_ordered(protocol,lambda j,i:(metrics(j),{}),a.compare,ledger,lambda e:None)
        self.assertTrue(ledger['success']);self.assertEqual(len(ledger['attempts']),18);self.assertEqual(len(ledger['pairs']),12)
    def test_first_failure_stops_without_retry(self):
        protocol=p.load_protocol('TH');ledger=dict(attempts=[],pairs=[]);calls=[]
        def perform(j,i):
            calls.append(i);v=metrics(j);v['accepted']=i!=2;return v,{}
        with self.assertRaises(RuntimeError):r.run_ordered(protocol,perform,a.compare,ledger,lambda e:None)
        self.assertEqual(calls,[1,2]);self.assertEqual(len(ledger['unattempted']),16)
    def test_risk_failure_stops(self):
        protocol=p.load_protocol('TH');ledger=dict(attempts=[],pairs=[])
        def perform(j,i):
            v=metrics(j)
            if i==2:v['diagnostic']['error']['rmse'][2]=100
            return v,{}
        with self.assertRaises(RuntimeError):r.run_ordered(protocol,perform,a.compare,ledger,lambda e:None)
        self.assertEqual(len(ledger['attempts']),2)
    def test_extra_or_reordered_manifest_rejected(self):
        for mutate in (lambda j:j.append(j[0]),lambda j:j.reverse()):
            protocol=p.load_protocol('TH');mutate(protocol['jobs'])
            with self.assertRaises(RuntimeError):r.validate_scope(protocol)
    def test_replay_authority_not_copied(self):
        f=a.full_analysis(lambda *args:{})
        self.assertIsNot(f.__globals__['check_components'],b.FINAL._components)
        self.assertIsNot(b.KERNEL.full_chain.analyzer,a)

class Negatives(unittest.TestCase):pass
for gate in ('TH','TV'):
    for case in ('mode','axes','inner','inner_stale','duplicate_sample','backward_publication','missing_selection',
                 'same_time_ambiguous','missing_update','not_taken_over','partial_commit','p','nu_candidate',
                 'old_nu_output','applied','published','proxy','ff_twice','wrong_h','legacy_clamp_h','zero_cost',
                 'false_valid','selected_nan','interval','reset','long_pause','epsilon','generation','pid_axes'):
        f=b.clone(old.negative_component('D',case),fixture=lambda _ignored,g=gate:fixture(g),analyzer=a)
        setattr(Negatives,'test_'+gate+'_'+case,f)

if __name__=='__main__':unittest.main()
