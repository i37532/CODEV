"""Offline revised matrix, qualification and refusal tests; never launches SITL."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('revision09_protocol_test',HERE/'protocol.py')
p=importlib.util.module_from_spec(s);s.loader.exec_module(p)


class Protocol(unittest.TestCase):
    def test_exact_36_jobs_four_gates_and_twelve_seeds(self):
        p.validate_manifest();d=p.design()
        self.assertEqual(len(d['jobs']),36)
        self.assertEqual(len({j['seed'] for j in d['jobs']}),12)
        self.assertEqual(len({j['id'] for j in d['jobs']}),36)
        for gate in 'ABCD':
            jobs=p.load_protocol(gate)['jobs']
            self.assertEqual(len(jobs),9)
            for seed in {j['seed'] for j in jobs}:
                block=[j for j in jobs if j['seed']==seed]
                self.assertEqual(block[0]['mode'],0)
                self.assertEqual(sorted(j['mode'] for j in block),[0,1,3])
                self.assertTrue(all(j['parameters']['MC_RTC_MODE']==0 and j['parameters']['MC_RTC_DIV']==1 for j in block))

    def test_all_parameters_and_science_match_original_per_gate(self):
        for gate,cfg in p.GATES.items():
            before=p.source_jobs(gate);after=p.load_protocol(gate)['jobs']
            for old,new in zip(before,after):
                self.assertTrue(p.exact({k:v for k,v in old.items() if k not in ('revision','seed','phase','role')},
                    {k:v for k,v in new.items() if k not in ('revision','seed','phase','role')}))
                self.assertEqual(len(new['parameters']),127)

    def test_registered_manifest_tampering_rejected(self):
        for key,value in [('new_matrix_attempts',37),('total_maximum_attempts',91),('historical_attempts',54.0)]:
            d=copy.deepcopy(p.design());d[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):p.validate_manifest(d)
        d=copy.deepcopy(p.design());d['jobs'][1]['parameters']['MPC_VC_L1_X']=.8
        with self.assertRaises(ValueError):p.validate_manifest(d)

    def test_unknown_gates_and_old_authority_fail_closed(self):
        for gate in ('','E','AB',None,1):
            with self.subTest(gate=gate),self.assertRaises(ValueError):p.load_protocol(gate)
        with patch.object(p,'DRAFT_ONLY',True),self.assertRaises(PermissionError):p.require_execution_authority('A')
        with patch.object(p,'AUTHORIZATION_SHA','0'*64),self.assertRaises(PermissionError):p.require_execution_authority('A')

    def test_historical_counts_include_two_nonaccepting_diagnostics(self):
        h=p.retained_history()
        self.assertEqual([h[k] for k in ('attempts','takeoffs','accepted','failed','diagnostic_complete')],[54,53,46,6,2])
        self.assertEqual(h['accepted_for_new_matrix'],0)
        self.assertFalse(p.retained_abc()['counts_toward_new_matrix'])
        self.assertEqual(p.diagnostic_replay_binding()['accepted_for_R03'],0)

    def test_no_forged_diagnostic_replay(self):
        with patch.object(p,'UPSTREAM_REPLAY_SHA','0'*64),self.assertRaises(ValueError):p.diagnostic_replay_binding()

    def test_old_gate_receipt_does_not_admit_new_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);dest=root/'A/gate_pass.json';dest.parent.mkdir()
            dest.write_text(json.dumps(dict(success=True,revision='r03_revision04',source_head='a'*40,accepted=9)))
            verifier=SimpleNamespace(verify_complete=Mock(side_effect=ValueError('missing new raw/replay')))
            with patch.object(p,'DATA_ROOT',root),patch.object(p,'load_file',return_value=verifier),self.assertRaises(ValueError):
                p.require_previous_gates('B','a'*40)

    def test_missing_previous_gate_rejected_without_flight(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(p,'DATA_ROOT',Path(tmp)),self.assertRaises(ValueError):
            p.require_previous_gates('B','a'*40)
        self.assertEqual(p.require_previous_gates('A','a'*40),[])

    def test_each_gate_prior_budget_and_logging(self):
        for index,gate in enumerate('ABCD'):
            b=p.budget(gate)
            self.assertEqual(b['prior_attempts'],54+9*index)
            self.assertEqual(b['maximum_attempts'],9)
            self.assertEqual(b['historical_attempts']+b['new_matrix_attempts'],90)
            self.assertEqual(b['logging_profile'],3089)

    def test_previous_gate_firmware_must_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);dest=root/'A/gate_pass.json';dest.parent.mkdir()
            receipt=dict(success=True,source_head='a'*40,firmware_sha256='b'*64)
            dest.write_text(json.dumps(receipt))
            verifier=SimpleNamespace(verify_complete=lambda gate,path:receipt)
            with patch.object(p,'DATA_ROOT',root),patch.object(p,'load_file',return_value=verifier):
                self.assertEqual(p.require_previous_gates('B','a'*40,'b'*64)[0]['firmware_sha256'],'b'*64)
                with self.assertRaisesRegex(ValueError,'firmware'):p.require_previous_gates('B','a'*40,'c'*64)
                with self.assertRaisesRegex(ValueError,'source'):p.require_previous_gates('B','c'*40,'b'*64)

    def test_preparation_refuses_registered_files(self):
        with self.assertRaises(ValueError):p.prepare()


class Qualification(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'A/qualification01/evidence.json';self.path.parent.mkdir(parents=True)
        self.head='a'*40;self.firmware='b'*64
        self.frozen=Mock();self.frozen.archive_check=Mock()
        self.values={'success':True,'clean':True,**p.budget('A'),
            'stage':'R03-revision09-A','revision':p.REVISION,'gate':'A','source_head':self.head,
            'firmware_sha256':self.firmware,'new_flights':0,'execution_authorized':True,
            'flight_authorized':True,'execution_ready':True,'historical_budget':{},'retained_abc':{},
            'seed_migration':p.seed_migration(),'diagnostic_replay':{},'previous_gates':[],
            'authorization_sha256':p.AUTHORIZATION_SHA,'execution_sha256':'e'*64,'frozen_sha256':'f'*64,
            'counts':dict(cpp_unique_tests=541,python_tests=1258),
            'cpp_test_targets':['functional-VehicleIMU','functional-EKF2SelectorTiming','functional-EstimatorDiagnosticTopics'],
            'evidence_files':{str(self.path.parent/'tests.log'):'c'*64}}
        self.addCleanup(patch.stopall)
        patch.object(p,'DATA_ROOT',self.root).start()
        patch.object(p,'retained_history',return_value={}).start();patch.object(p,'retained_abc',return_value={}).start()
        patch.object(p,'diagnostic_replay_binding',return_value={}).start()
        patch.object(p,'require_previous_gates',return_value=[]).start()
        patch.object(p,'load_file',return_value=self.frozen).start()
        def sha(path):
            if str(path).endswith('execution.json'):return 'e'*64
            if str(path).endswith('frozen.json'):return 'f'*64
            if str(path).endswith('tests.log'):return 'c'*64
            return 'd'*64
        patch.object(p,'fingerprint',side_effect=sha).start()
        self.approval=p.authorization_binding(self.values,self.path)
        patch.object(p,'read',side_effect=lambda path:self.approval if Path(path).name=='authorization.json' else self.values).start()

    def check(self):return p.archive_qualification('A',self.head,self.path)

    def test_archival_proof_does_not_depend_on_live_head(self):
        with patch.object(p,'git',side_effect=AssertionError('No live checkout lookup')):
            self.assertIs(self.check(),self.values)
        self.frozen.archive_check.assert_called_once_with('A',self.head,'f'*64)

    def test_missing_actual_tests_rejected(self):
        for field,value in [('cpp_unique_tests',0),('python_tests',0),('cpp_unique_tests',True)]:
            old=copy.deepcopy(self.values['counts']);self.values['counts'][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):self.check()
            self.values['counts']=old

    def test_missing_upstream_targets_rejected(self):
        self.values['cpp_test_targets']=[]
        with self.assertRaises(ValueError):self.check()

    def test_wrong_source_or_budget_rejected(self):
        for field,value in [('source_head','c'*40),('historical_attempts',54.0),('new_matrix_attempts',37),('clean',False),('gate','D')]:
            old=self.values[field];self.values[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.check()
            self.values[field]=old

    def test_evidence_hash_and_foreign_path_rejected(self):
        for files in ({},{str(self.path.parent/'tests.log'):'0'*64},{'/tmp/foreign.log':'c'*64}):
            self.values['evidence_files']=files
            with self.subTest(files=files),self.assertRaises(ValueError):self.check()

    def test_wrong_authorization_rejected(self):
        self.approval['approved']=False
        with self.assertRaises(ValueError):self.check()

    def test_changed_committed_assets_rejected(self):
        self.frozen.archive_check.side_effect=ValueError('Changed committed source')
        with self.assertRaises(ValueError):self.check()


if __name__=='__main__':unittest.main(verbosity=2)
