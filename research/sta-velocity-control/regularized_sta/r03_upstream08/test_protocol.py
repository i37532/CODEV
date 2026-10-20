"""Finite diagnostic contract and real retained evidence; zero flights."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('up08_protocol_test',HERE/'protocol.py');p=importlib.util.module_from_spec(s);s.loader.exec_module(p)


class Contract(unittest.TestCase):
    def test_registered_design_exact(self):self.assertTrue(p.validate_manifest())
    def test_history_real52_original_verdicts(self):
        h=p.retained_history();self.assertEqual((h['attempts'],h['takeoffs'],h['accepted'],h['failed']),(52,51,46,6))
        self.assertEqual(len(h['batches']),9);self.assertEqual(h['accepted_for_new_matrix'],0)
    def test_two_jobs_same_seed_pid_first_no_rsta(self):
        j=p.design()['jobs'];self.assertEqual([x['id'] for x in j],['diag001','diag002'])
        self.assertEqual([x['mode'] for x in j],[0,1]);self.assertEqual([x['axes'] for x in j],[0,7]);self.assertEqual(len({x['seed'] for x in j}),1)
    def test127_parameters_match_old_science(self):
        old=p.read(p.OLD/'manifest.json')
        for j in p.design()['jobs']:
            previous=next(x for x in old if x['mode']==j['mode'])
            self.assertEqual(len(j['parameters']),127);self.assertTrue(p.exact(j['parameters'],previous['parameters']))
            self.assertEqual(j['parameters']['MPC_VCT_TEST'],8)
    def test_budget_and_profile_are_separate_from_acceptance(self):
        d=p.design();self.assertEqual((d['historical_attempts'],d['maximum_attempts'],d['total_maximum_attempts']),(52,2,54))
        self.assertEqual(d['new_matrix_attempts'],0);self.assertIs(d['count_as_R03_acceptance'],False)
        self.assertEqual(d['logging_profile_before']|d['added_logging_mask'],d['logging_profile_after'])
        self.assertEqual(d['logging_profile_after'],3089)
    def test_path_and_inherited_checks(self):
        x=p.load_protocol();self.assertEqual(Path(x['config_dir']),HERE);self.assertEqual(x['gate'],'D')
        self.assertEqual(x['data_gate']['maximum_ulog_dropouts'],0);self.assertEqual(x['height_task']['target_height_m'],2.5)
        self.assertEqual(x['diagnostic_gate']['minimum_excitation_samples'],6390)
    def test_strict_json_types(self):
        for a,b in [(1,True),(1,1.0),({'a':1},{}),([1,2],[2,1])]:self.assertFalse(p.exact(a,b))
        with self.assertRaises(ValueError):p.exact(float('nan'),float('nan'))
    def test_scope_mutation_rejected(self):
        for key,value in [('maximum_attempts',3),('maximum_attempts',2.0),('diagnostic_only',False),('logging_profile_after',1041)]:
            d=p.design();d[key]=value
            with self.assertRaises(ValueError):p.validate_manifest(d)
    def test_parameter_change_rejected(self):
        d=p.design();d['jobs'][1]['parameters']['MPC_VC_L1_Z']=3
        with self.assertRaises(ValueError):p.validate_manifest(d)
    def test_no_overwrite_registration(self):
        with self.assertRaisesRegex(ValueError,'overwrite'):p.prepare()
    def test_auth_changed_rejected(self):
        with patch.object(p,'AUTHORIZATION_SHA','0'*64):
            with self.assertRaises(PermissionError):p.require_execution_authority()
    def test_old_source_changed_rejected(self):
        with patch.object(p,'OLD_PROTOCOL_SHA','0'*64):
            with self.assertRaises(ValueError):p.retained_history()
    def test_six_missing_cannot_be_erased(self):
        real=p.read
        def changed(path):
            d=real(path)
            if Path(path)==p.HISTORY06/'ledger.json':d['unattempted']=[]
            return d
        with patch.object(p,'read',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'verdict'):p.retained_history()
    def test_last_failure_cannot_be_regraded(self):
        real=p.read
        def changed(path):
            d=real(path)
            if Path(path)==p.HISTORY06/'ledger.json':d['attempts'][-1]['status']='accepted'
            return d
        with patch.object(p,'read',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'verdict'):p.retained_history()
    def test_real_abc_retained_not_new_qualification(self):
        a=p.retained_abc();self.assertEqual(a['accepted_design_runs'],27);self.assertEqual(a['new_attempts'],0)
    def test_foreign_used_seed_is_not_exempt(self):
        mock=types.SimpleNamespace(seed_audit=lambda seeds:dict(matches=[dict(path='/foreign/history.json',seeds=seeds)],invalid_json=[],accepted=False))
        real=p.load_file
        with patch.object(p,'load_file',side_effect=lambda n,x:mock if n=='_up08_seed_scan' else real(n,x)):
            self.assertFalse(p.fresh_seeds()['accepted'])
    def test_no_seed_migration_exception(self):
        self.assertNotIn('seed_migration',p.load_protocol())
    def test_missing_qualification_cannot_authorize(self):
        with self.assertRaises(ValueError):p.require_qualification('a'*40,Path('/tmp/not-a-diagnostic-qualification.json'))
    def test_expected_authority_has_no_seed_list(self):
        a=p.require_execution_authority();self.assertNotIn('seeds',a);self.assertNotIn('jobs',a)


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='up08-qualification-offline-');self.root=Path(self.tmp.name)
        self.qpath=self.root/'qualification01/evidence.json';self.qpath.parent.mkdir()
        self.log=self.qpath.parent/'tests.log';self.log.write_text('offline fixture, not executed flight')
        self.binding=dict(stage=p.STAGE,revision=p.REVISION,source_head='a'*40,**p.budget())
        self.q=dict(**self.binding,success=True,clean=True,counts=dict(cpp_unique_tests=525,python_tests=800),
            cpp_test_targets=['functional-VehicleIMU','functional-EKF2SelectorTiming','functional-EstimatorDiagnosticTopics'],
            evidence_files={str(self.log):p.fingerprint(self.log)})
        self.write()
        self.stack=__import__('contextlib').ExitStack()
        self.stack.enter_context(patch.object(p,'DATA_ROOT',self.root))
        self.stack.enter_context(patch.object(p,'qualification_binding',return_value=self.binding))
        self.freeze=unittest.mock.Mock()
        self.stack.enter_context(patch.object(p,'load_file',return_value=types.SimpleNamespace(check=self.freeze)))
        self.stack.enter_context(patch.object(p,'git',side_effect=lambda *a:'a'*40 if a==('rev-parse','HEAD') else ('research/sta-velocity-regularized' if a==('branch','--show-current') else '')))
    def write(self):
        self.qpath.write_text(json.dumps(self.q))
        (self.qpath.parent/'authorization.json').write_text(json.dumps(dict(**self.binding,approved=True,qualification_sha256=p.fingerprint(self.qpath))))
    def tearDown(self):self.stack.close();self.tmp.cleanup()
    def test_complete_fixture_calls_freeze(self):
        self.assertTrue(p.require_qualification('a'*40,self.qpath)['success']);self.freeze.assert_called_once()
    def test_missing_functional_target_rejected(self):
        self.q['cpp_test_targets'].pop();self.write()
        with self.assertRaisesRegex(ValueError,'targets'):p.require_qualification('a'*40,self.qpath)
    def test_minimum_cpp_python_and_type_enforced(self):
        for key,value in [('cpp_unique_tests',524),('python_tests',799),('cpp_unique_tests',525.0),('python_tests',True)]:
            self.q['counts']=dict(cpp_unique_tests=525,python_tests=800);self.q['counts'][key]=value;self.write()
            with self.assertRaisesRegex(ValueError,'tests'):p.require_qualification('a'*40,self.qpath)
    def test_old_revision_receipt_rejected(self):
        self.q['revision']='r03_revision06';self.write()
        with self.assertRaises(ValueError):p.require_qualification('a'*40,self.qpath)
    def test_profile_changed_rejected(self):
        self.q['logging_profile_after']=1041;self.write()
        with self.assertRaises(ValueError):p.require_qualification('a'*40,self.qpath)
    def test_evidence_bytes_changed_rejected(self):
        self.log.write_text('changed')
        with self.assertRaisesRegex(ValueError,'evidence'):p.require_qualification('a'*40,self.qpath)
    def test_changed_freeze_rejected(self):
        self.freeze.side_effect=ValueError('frozen source')
        with self.assertRaisesRegex(ValueError,'frozen'):p.require_qualification('a'*40,self.qpath)
    def test_missing_authority_cannot_be_inferred(self):
        (self.qpath.parent/'authorization.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'receipt'):p.require_qualification('a'*40,self.qpath)


if __name__=='__main__':unittest.main(verbosity=2)
