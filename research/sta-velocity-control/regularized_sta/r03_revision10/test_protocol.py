"""Offline finite D-only protocol and qualification tests; no flights."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('revision10_protocol_test',HERE/'protocol.py')
p=importlib.util.module_from_spec(s);s.loader.exec_module(p)

class Protocol(unittest.TestCase):
    def test_registered_exact_nine_three_fresh_paired_seeds(self):
        p.validate_manifest();d=p.design()
        self.assertEqual(len(d['jobs']),9);self.assertEqual({j['gate'] for j in d['jobs']},{'D'})
        self.assertEqual({j['seed'] for j in d['jobs']},{71731,71732,71733})
        for seed in (71731,71732,71733):
            block=[j for j in d['jobs'] if j['seed']==seed]
            self.assertEqual(block[0]['mode'],0);self.assertEqual(sorted(j['mode'] for j in block),[0,1,3])
    def test_all_127_parameters_and_tasks_unchanged(self):
        for old,new in zip(p.source_jobs('D'),p.design()['jobs']):
            self.assertEqual(len(new['parameters']),127)
            self.assertTrue(p.exact({k:v for k,v in old.items() if k not in ('revision','seed','phase','role')},
                {k:v for k,v in new.items() if k not in ('revision','seed','phase','role')}))
    def test_exact_history_includes_failed_zero_takeoff(self):
        h=p.retained_history()
        self.assertEqual([h[k] for k in ('attempts','takeoffs','accepted','failed','diagnostic_complete')],[82,80,73,7,2])
        self.assertEqual(h['batches'][-1]['takeoffs'],0);self.assertEqual(h['batches'][-1]['failed'],1)
    def test_old_abc_not_relabelled_or_pooled(self):
        d=p.design();self.assertFalse(d['same_source_all36'])
        self.assertFalse(d['retained_abc']['counts_toward_new_matrix'])
        self.assertEqual(d['retained_abc']['accepted_design_runs'],27)
        self.assertTrue(all(g['source_head']==p.PREVIOUS_HEAD for g in d['retained_abc']['gates']))
    def test_unknown_gate_and_authority_rejected(self):
        for g in ('A','B','C','',None,1):
            with self.subTest(g=g),self.assertRaises(ValueError):p.load_protocol(g)
        with patch.object(p,'DRAFT_ONLY',True),self.assertRaises(PermissionError):p.require_execution_authority('D')
        with patch.object(p,'AUTHORIZATION_SHA','0'*64),self.assertRaises(PermissionError):p.require_execution_authority('D')
    def test_budget_is_finite_and_warmup_explicit(self):
        b=p.budget('D');self.assertEqual(b['historical_attempts']+b['new_matrix_attempts'],91)
        self.assertEqual(b['maximum_attempts'],9);self.assertEqual(b['prior_attempts'],82)
        self.assertEqual(p.load_protocol('D')['post_logger_warmup_us'],30000000)
    def test_mutated_registered_budget_parameters_refused(self):
        for key,value in (('total_maximum_attempts',92),('historical_attempts',82.0),('new_matrix_attempts',10)):
            d=p.design();d[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):p.validate_manifest(d)
    def test_failed_raw_fingerprint_protected(self):
        with patch.object(p,'FAILED_LEDGER_SHA','0'*64),self.assertRaises(ValueError):p.retained_history()
    def test_previous_proof_no_missing_substitution(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(p,'EXTERNAL',Path(tmp)),self.assertRaises(ValueError):
            p.require_previous_gates('D','a'*40,'b'*64)
    def test_preparation_cannot_overwrite(self):
        with self.assertRaises(ValueError):p.prepare()


class Qualification(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'D/qualification01/evidence.json';self.path.parent.mkdir(parents=True)
        self.head='a'*40;self.firmware='b'*64
        self.frozen=Mock();self.frozen.archive_check=Mock()
        self.values={'success':True,'clean':True,**p.budget('D'),
            'stage':'R03-revision10-D','revision':p.REVISION,'gate':'D','source_head':self.head,
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

    def check(self):return p.archive_qualification('D',self.head,self.path)

    def test_archival_proof_does_not_depend_on_live_head(self):
        with patch.object(p,'git',side_effect=AssertionError('No live checkout lookup')):
            self.assertIs(self.check(),self.values)
        self.frozen.archive_check.assert_called_once_with('D',self.head,'f'*64)

    def test_missing_actual_tests_rejected(self):
        for field,value in [('cpp_unique_tests',0),('python_tests',0),('cpp_unique_tests',True)]:
            old=copy.deepcopy(self.values['counts']);self.values['counts'][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):self.check()
            self.values['counts']=old

    def test_missing_upstream_targets_rejected(self):
        self.values['cpp_test_targets']=[]
        with self.assertRaises(ValueError):self.check()

    def test_wrong_source_or_budget_rejected(self):
        for field,value in [('source_head','c'*40),('historical_attempts',54.0),('new_matrix_attempts',37),('clean',False),('gate','A')]:
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
