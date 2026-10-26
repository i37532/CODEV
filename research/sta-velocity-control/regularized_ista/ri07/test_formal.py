import copy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'tools'))
import bindings as b
p=b.api()
r=b.local('runner')
a=b.local('analyzer')

class FormalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.protocol=p.load_protocol();cls.jobs=cls.protocol['jobs']
    def test_exact200(self):self.assertEqual(len(self.jobs),200);r.validate_scope(self.protocol)
    def test_exact_original_fields(self):
        for new,old in zip(self.jobs,p.formal()['jobs']):
            self.assertEqual({k:new[k] for k in old},old)
    def test_a80_b120(self):self.assertEqual([sum(j['group']==g for j in self.jobs) for g in 'AB'],[80,120])
    def test_20_blocks_each(self):
        for group in 'AB':self.assertEqual(len({j['seed'] for j in self.jobs if j['group']==group}),20)
    def test_first_is_not_added_pid(self):self.assertEqual((self.jobs[0]['id'],self.jobs[0]['mode']),('A001',3))
    def test_no_old_esta(self):self.assertEqual({j['mode'] for j in self.jobs},{0,3,4})
    def test_defaults_dry_run(self):
        with patch.object(r,'execute_gate',side_effect=AssertionError('flight')),patch('builtins.print'):
            self.assertEqual(r.main([]),0)
    def test_reordered_refused(self):
        q=copy.deepcopy(self.protocol);q['jobs'][0],q['jobs'][1]=q['jobs'][1],q['jobs'][0]
        with self.assertRaises(RuntimeError):r.validate_scope(q)
    def test_reduced100_refused(self):
        q=copy.deepcopy(self.protocol);q['jobs']=q['jobs'][:100]
        with self.assertRaises(RuntimeError):r.validate_scope(q)
    def test_extended_refused(self):
        q=copy.deepcopy(self.protocol);q['jobs'].append(q['jobs'][-1])
        with self.assertRaises(RuntimeError):r.validate_scope(q)
    def test_seed_changed_refused(self):
        j=copy.deepcopy(self.jobs[0]);j['seed']=999
        with self.assertRaises(ValueError):a.validate_job(j)
    def test_mode_changed_refused(self):
        j=copy.deepcopy(self.jobs[0]);j['mode']=1
        with self.assertRaises(ValueError):a.validate_job(j)
    def test_parameter_changed_refused(self):
        j=copy.deepcopy(self.jobs[0]);j['parameters']['MPC_VC_L1_Z']*=2
        with self.assertRaises(ValueError):a.validate_job(j)
    def test_inner_mode_changed_refused(self):
        j=copy.deepcopy(self.jobs[0]);j['parameters']['MC_RTC_MODE']=1
        with self.assertRaises(ValueError):a.validate_job(j)
    def test_task_overlay_hv(self):
        for task in 'HV':
            j=next(j for j in self.jobs if j['task']==task)
            q=p.job_protocol(self.protocol,j)
            self.assertEqual(q['excitation']['task'],task)
            self.assertEqual(q['excitation']['parameter'],6 if task=='H' else 8)
            self.assertEqual(q['startup_overrides']['MPC_VCT_TEST'],6 if task=='H' else 8)
            a.protocol_identity(q,j)
    def test_wrong_task_overlay_refused(self):
        j=next(j for j in self.jobs if j['task']=='V');q=p.job_protocol(self.protocol,j)
        q['excitation']['parameter']=6
        with self.assertRaises(ValueError):a.protocol_identity(q,j)
    def test_caller_protocol_unchanged(self):
        before=copy.deepcopy(self.protocol);p.job_protocol(self.protocol,self.jobs[-1]);self.assertEqual(before,self.protocol)
    def test_wrong_axes_refused(self):
        j=copy.deepcopy(self.jobs[0]);j['axes']=3
        with self.assertRaises(ValueError):a.validate_job(j)
    def test_wrong_divisor_refused(self):
        j=copy.deepcopy(self.jobs[0]);j['divisor']=2
        with self.assertRaises(ValueError):a.validate_job(j)
    def test_wrong_phase_refused(self):
        j=copy.deepcopy(self.jobs[0]);j['phase']='training'
        with self.assertRaises(ValueError):a.validate_job(j)
    def test_fixed_firmware(self):self.assertEqual(p.formal()['firmware_sha256'],'b7548e2cc08208972e42501d1faf9e793a027224d30790264e9d16b316fcaaa1')
    def test_nonproduction_scope(self):self.assertTrue(all('src/' not in s[:4] for s in p.scope()))
    def test_production_edit_refused(self):
        with patch.object(p,'git',return_value='src/modules/mc_pos_control/PositionControl/PositionControl.cpp'):
            with self.assertRaises(ValueError):p.scope()
    def test_ordered200_fake_transport(self):
        ledger=dict(attempts=[],pairs=[],success=False);called=[]
        def perform(j,i):called.append(j['id']);return dict(job=j,accepted=True),{}
        def compare(x,y):return dict(accepted=True)
        r.run_ordered(self.protocol,perform,compare,ledger,lambda event:None)
        self.assertEqual(called,[j['id'] for j in self.jobs]);self.assertEqual(len(ledger['pairs']),80);self.assertTrue(ledger['success'])
    def test_first_failure_stops_and_missing_preserved(self):
        ledger=dict(attempts=[],pairs=[],success=False)
        def perform(j,i):raise RuntimeError('synthetic safety/log/replay failure')
        with self.assertRaises(RuntimeError):r.run_ordered(self.protocol,perform,None,ledger,lambda event:None)
        self.assertEqual(len(ledger['attempts']),1);self.assertEqual(len(ledger['unattempted']),199)
        self.assertEqual(ledger['attempts'][0]['status'],'failed');self.assertFalse(ledger['success'])
    def test_cannot_retry_failed_admission(self):
        admission=r.Admission(self.protocol,None)
        with self.assertRaises(RuntimeError):admission.accept(self.jobs[0],dict(job=self.jobs[0],accepted=False))
        with self.assertRaises(RuntimeError):admission.before(self.jobs[0])
    def test_wrong_metrics_job_refused(self):
        admission=r.Admission(self.protocol,None)
        with self.assertRaises(RuntimeError):admission.accept(self.jobs[0],dict(job=self.jobs[1],accepted=True))
    def test_explicit_execution_needs_qualification(self):
        with patch('builtins.print'),self.assertRaises(RuntimeError):r.main(['--execute'])

if __name__=='__main__':unittest.main()
