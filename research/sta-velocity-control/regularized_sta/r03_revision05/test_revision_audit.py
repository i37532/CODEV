"""Read-only revision05 scope/qualification audit; no build, flight or seed write.

Synthetic receipts use fake hashes, never future trial seeds. Actual checks
read the entry source, immutable prior research and retained historical rows.
Historical qualifications are not reissued as new B/C/D qualification.
"""
import copy
import importlib.util
from pathlib import Path
import re
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
ENTRY='7d865a085bc8cd39aa17d868162bafacddd6d37d'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


p=load('_revision05_audit_protocol',HERE/'protocol.py')
f=load('_revision05_audit_freeze',HERE/'freeze.py')
v=load('_revision05_audit_verify',HERE/'verify.py')


class RevisionAuditTest(unittest.TestCase):
    def test_diagnostic_json_preserves_existing_nonfinite_markers(self):
        left={'unused':[float('nan'),float('inf'),float('-inf')],'accepted':False}
        right={'accepted':False,'unused':[float('nan'),float('inf'),float('-inf')]}
        self.assertTrue(v.diagnostic_metrics_equal(left,right))

    def test_diagnostic_nan_cannot_equal_null_numeric_or_infinity(self):
        for other in (None,0,float('inf'),float('-inf'),'NaN'):
            with self.subTest(other=other):
                self.assertFalse(v.diagnostic_metrics_equal({'x':float('nan')},{'x':other}))

    def test_diagnostic_infinity_sign_and_zero_sign_are_preserved(self):
        for before,after in ((float('inf'),float('-inf')),(float('-inf'),float('inf')),
                             (0.0,-0.0),(float('inf'),'Infinity')):
            with self.subTest(before=before,after=after):
                self.assertFalse(v.diagnostic_metrics_equal({'x':before},{'x':after}))

    def test_diagnostic_numeric_types_are_not_normalized(self):
        for before,after in ((1,1.0),(0,False),(1,True)):
            with self.subTest(before=before,after=after):
                self.assertFalse(v.diagnostic_metrics_equal({'nested':[before]},{'nested':[after]}))

    def test_diagnostic_missing_extra_fields_or_list_order_not_ignored(self):
        before={'unused':float('nan'),'values':[1,2]}
        for after in ({'values':[1,2]}, {**before,'extra':None}, {**before,'values':[2,1]}):
            self.assertFalse(v.diagnostic_metrics_equal(before,after))

    def test_diagnostic_finite_value_difference_not_tolerated(self):
        self.assertFalse(v.diagnostic_metrics_equal({'value':1.0},{'value':1.0000000000000002}))

    def test_diagnostic_acceptance_flag_cannot_change(self):
        before={'accepted':False,'flight_accepted':False,'diagnostic_only':True}
        for key in ('accepted','flight_accepted'):
            self.assertFalse(v.diagnostic_metrics_equal(before,{**before,key:True}))

    def test_protocol_exact_still_rejects_nonfinite_after_diagnostic_comparison(self):
        for value in (float('nan'),float('inf'),float('-inf')):
            self.assertTrue(v.diagnostic_metrics_equal({'x':value},{'x':value}))
            with self.assertRaises(ValueError):p.exact({'x':value},{'x':value})

    def receipt_fixture(self):
        history=dict(attempts=30,accepted=26,failed=4,takeoffs=29,accepted_for_new_matrix=0)
        retained=dict(gate='A',revision='r03_revision04',accepted=9,receipt_sha256='a'*64)
        previous=[dict(gate='A',revision='r03_revision04',receipt_sha256='a'*64)]
        e=dict(success=True,clean=True,new_flights=0,execution_authorized=True,
            flight_authorized=True,execution_ready=True,stage='R03-revision05-B',
            revision=p.REVISION,gate='B',seed_migration=p.seed_migration(),previous_gates=previous,
            historical_budget=history,retained_a=retained,maximum_attempts=9,
            new_matrix_attempts=27,historical_attempts=30,total_maximum_attempts=57,
            source_head='b'*40,execution_sha256='c'*64,frozen_sha256='d'*64,firmware_sha256='e'*64)
        return e,history,retained,previous

    def receipt(self,evidence,history,retained,previous):
        with patch.object(v._protocol,'require_execution_authority',return_value={'approved':True}), \
             patch.object(v,'require_previous_gates',return_value=previous), \
             patch.object(v,'retained_failure',return_value=history), \
             patch.object(v,'retained_a',return_value=retained), \
             patch.object(v,'fingerprint',return_value='f'*64):
            return v.qualification_receipt(evidence,'B',Path('/fake-new-qualification'))

    def test_receipt_binds_passed_a_and_exact_new_budget(self):
        args=self.receipt_fixture();receipt=self.receipt(*args)
        self.assertEqual((receipt['maximum_attempts'],receipt['new_matrix_attempts'],
            receipt['historical_attempts'],receipt['total_maximum_attempts']),(9,27,30,57))
        self.assertTrue(p.exact(receipt['retained_a'],args[2]))
        self.assertTrue(p.exact(receipt['previous_gates'],args[3]))
        self.assertIs(receipt['approved'],True)

    def test_receipt_rejects_dirty_old_or_nonzero_flight_evidence(self):
        args=self.receipt_fixture()
        for key,value in (('success',False),('clean',False),('new_flights',1),
                          ('revision','r03_revision04'),('stage','R03-revision04-B'),('gate','A'),
                          ('execution_authorized',False),('flight_authorized',False),('execution_ready',False)):
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.receipt({**args[0],key:value},*args[1:])

    def test_receipt_rejects_missing_prior_a_or_history(self):
        args=self.receipt_fixture()
        for key,value in (('retained_a',{}),('historical_budget',{}),('previous_gates',[]),
                          ('seed_migration',{})):
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.receipt({**args[0],key:value},*args[1:])

    def test_receipt_rejects_number_boolean_float_aliases(self):
        args=self.receipt_fixture()
        for key,value in (('success',1),('clean',1),('new_flights',False),('new_flights',0.0),
            ('maximum_attempts',9.0),('new_matrix_attempts',27.0),('historical_attempts',30.0),
            ('total_maximum_attempts',57.0),('execution_authorized',1),('flight_authorized',1)):
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.receipt({**args[0],key:value},*args[1:])

    def test_receipt_nested_count_aliases_and_changed_a_proof_rejected(self):
        args=self.receipt_fixture()
        for field,key,value in [('retained_a','accepted',9.0),('retained_a','receipt_sha256','0'*64),
             ('historical_budget','attempts',30.0),('historical_budget','accepted_for_new_matrix',False),
             ('historical_budget','takeoffs',30)]:
            changed=copy.deepcopy(args[0]);changed[field][key]=value
            with self.subTest(field=field,key=key),self.assertRaises(ValueError):
                self.receipt(changed,*args[1:])

    def test_receipt_refuses_nonfinite_json(self):
        args=self.receipt_fixture()
        for value in (float('nan'),float('inf'),float('-inf')):
            with self.assertRaises(ValueError):
                self.receipt({**args[0],'total_maximum_attempts':value},*args[1:])

    def test_missing_current_authority_never_issues_receipt(self):
        with patch.object(v._protocol,'require_execution_authority',side_effect=PermissionError('No new authority')):
            with self.assertRaises(PermissionError):v.qualification_receipt({},'B',Path('/fake'))

    def test_masks_retain_a_while_only_bcd_are_new_gates(self):
        self.assertEqual(list(p.GATES),['B','C','D'])
        for gate,masks in [('B',[1,4]),('C',[1,4,3]),('D',[1,4,3,7])]:
            self.assertEqual(f.gate_masks(gate),masks)
            source='const bool regularized_gate_admitted = '+' || '.join('axes == '+str(a) for a in masks)+';'
            self.assertEqual(f.admitted_gate(source),gate)
        for gate in ('A','E','b',None):
            with self.assertRaises(ValueError):f.gate_masks(gate)

    def test_admission_rejects_old_a_and_unordered_or_extra_axes(self):
        for expression in ('axes == 1','axes == 4','axes == 7','axes == 4 || axes == 1',
            'axes == 1 || axes == 3','axes == 1 || axes == 4 || axes == 2',
            'axes == 1 || axes == 4 || axes == 5','axes == 1 || axes == 4 || axes == 6',
            'axes == 1 || axes == 4 || true','axes >= 1','true',
            'axes == 1 || axes == 4 || axes == 4'):
            with self.subTest(expression=expression),self.assertRaises(ValueError):
                f.admitted_gate('const bool regularized_gate_admitted = '+expression+';')

    def test_admission_requires_exact_single_predicate(self):
        source='const bool regularized_gate_admitted = axes == 1 || axes == 4;'
        for changed in ('',source+source):
            with self.assertRaises(ValueError):f.admitted_gate(changed)

    def test_future_patch_changes_only_admission_not_control_math(self):
        before='const bool regularized_gate_admitted = axes == 1 || axes == 4;\nfloat same=1.f;'
        for extra in (' || axes == 3',' || axes == 3 || axes == 7'):
            after=before.replace('axes == 4;','axes == 4'+extra+';')
            f.check_admission_only(before,after)
            with self.assertRaises(ValueError):f.check_admission_only(before,after.replace('1.f','2.f'))

    def test_comment_updates_do_not_hide_string_or_token_changes(self):
        before='const bool regularized_gate_admitted = axes == 1 || axes == 4; /* B */\nconst char *s="a b";'
        after=before.replace('axes == 4;','axes == 4 || axes == 3;').replace('/* B */','// C')
        f.check_admission_only(before,after)
        for changed in (after.replace('"a b"','"ab"'),after.replace('const char','char'),after+'int x=1;'):
            with self.assertRaises(ValueError):f.check_admission_only(before,changed)
        self.assertEqual(f.code_tokens('PARAM_DEFINE_FLOAT(X,1.f); /* text */'),
                         f.code_tokens('PARAM_DEFINE_FLOAT(X,1.f); // other'))
        self.assertNotEqual(f.code_tokens('PARAM_DEFINE_FLOAT(X,1.f);'),f.code_tokens('PARAM_DEFINE_FLOAT(X,2.f);'))

    def test_b_production_must_equal_entry_bytes(self):
        original=Path.read_text
        def source(path,*a,**kw):
            return 'const bool regularized_gate_admitted = axes == 1 || axes == 4;' if path==REPO/f.ADMISSION_SOURCE else original(path,*a,**kw)
        for operation in ('diff','ls-files'):
            def git(*args):
                if args[0]==operation and not any('/regularized_sta/' in str(x) for x in args):
                    return f.ADMISSION_SOURCE
                return ''
            with self.subTest(operation=operation),patch.object(f,'git',side_effect=git),patch.object(Path,'read_text',source):
                with self.assertRaisesRegex(ValueError,'Gate B|production change'):f.check_scope()

    def test_prior_research_numeric_checker_and_plans_are_immutable(self):
        for path in ('research/sta-velocity-control/regularized_sta/r03_revision04/analyzer.py',
                     'research/sta-velocity-control/regularized_sta/r03_numeric05/checker.py',
                     'research/sta-velocity-control/regularized_sta/plan/r03_revision04_entry/old.md'):
            for operation in ('diff','ls-files'):
                def git(*args):
                    return path if args[0]==operation and any(path.startswith(str(x).rstrip('/')+'/') for x in args[1:]) else ''
                with self.subTest(path=path,operation=operation),patch.object(f,'git',side_effect=git):
                    with self.assertRaisesRegex(ValueError,'Immutable prior'):f.check_scope()

    def test_new_plan_snapshot_does_not_grant_parent_directory_exemption(self):
        def git(*args):
            if args[0]=='ls-files' and f.PLAN_PREFIX in args:return f.NEW_PLAN+'TODO_CN.md'
            return ''
        with patch.object(f,'git',side_effect=git):self.assertEqual(f.check_scope(),[])

    def test_upstream_or_model_new_production_files_rejected(self):
        for path in ('src/modules/land_detector/MulticopterLandDetector.cpp','Tools/new_model.sdf',
                     'src/modules/sensors/new.cpp','msg/new.msg'):
            for operation in ('diff','ls-files'):
                def git(*args):
                    return path if args[0]==operation and not any('/regularized_sta/' in str(x) for x in args) else ''
                with self.subTest(path=path,operation=operation),patch.object(f,'git',side_effect=git):
                    with self.assertRaisesRegex(ValueError,'production change'):f.check_scope()

    def test_private_loaders_ignore_generic_import_cache(self):
        poison=types.SimpleNamespace(HERE=Path('/wrong'),REVISION='r03')
        before=list(sys.path)
        with patch.dict(sys.modules,{'protocol':poison,'freeze':poison}):
            freeze=load('_poison05_freeze',HERE/'freeze.py');verify=load('_poison05_verify',HERE/'verify.py')
            for module in (freeze,verify):
                self.assertEqual(module.HERE,HERE);self.assertEqual(module._protocol.__file__,str(HERE/'protocol.py'))
            self.assertEqual(verify.freeze.__file__,str(HERE/'freeze.py'))
            self.assertEqual(freeze.TOTAL_MAXIMUM_ATTEMPTS,57)
            self.assertIs(sys.modules['protocol'],poison);self.assertIs(sys.modules['freeze'],poison)
        self.assertEqual(sys.path,before)

    def test_actual_entry_scope_and_historical_sources(self):
        self.assertTrue(set(f.check_scope()).issubset(f.ALLOWED))
        self.assertEqual(f.ENTRY,ENTRY);self.assertEqual(p.design()['revision_entry_head'],ENTRY)
        history=p.retained_history()
        self.assertEqual((history['attempts'],history['accepted'],history['failed'],history['takeoffs'],
                          history['accepted_for_new_matrix']),(30,26,4,29,0))
        self.assertEqual(len(history['batches']),5)
        for batch in history['batches']:
            self.assertEqual(p.read(batch['ledger_path'])['source_head'],batch['source_head'])
            self.assertEqual(subprocess.check_output(['git','cat-file','-t',batch['source_head']],cwd=REPO,text=True).strip(),'commit')

    def test_actual_a_is_retained_complete_not_new_attempts(self):
        a=p.retained_a()
        self.assertEqual((a['gate'],a['revision'],a['accepted'],a['independent_replays'],a['paired_checks']),
                         ('A','r03_revision04',9,9,6))
        self.assertEqual(a['accepted_for_new_matrix'],0)
        self.assertEqual(f.budget(),dict(total=57,this_gate=9,new_matrix=27,retained_attempts=30,
            retained_accepted=26,retained_invalid=4,replacement_after_this_revision=0))

    def test_actual_gate_is_precise_bcd_prefix(self):
        source=(REPO/f.ADMISSION_SOURCE).read_text();gate=f.admitted_gate(source)
        result=v.gate_check(gate)
        self.assertEqual(result['admitted_masks'],f.gate_masks(gate));self.assertEqual(result['divisor'],1)
        self.assertTrue(result['sitl_only'])
        for other in set(p.GATES)-{gate}:
            with self.assertRaises(ValueError):v.gate_check(other)

    def test_new_jobs_match_prior_bcd_science_parameters_and_order(self):
        old=load('_audit05_prior_protocol',HERE.parent/'r03_revision04/protocol.py')
        for gate in p.GATES:
            before,current=old.load_protocol(gate),p.load_protocol(gate)
            for prior,new in zip(before['jobs'],current['jobs']):
                self.assertTrue(p.exact({**prior,'revision':p.REVISION,'seed':new['seed']},new))
                self.assertEqual(len(new['parameters']),127)
            for key in ('candidate','startup_overrides','diagnostic_gate','constraints','safety',
                        'log_requirements','landing','control_loop'):
                if key in before:self.assertTrue(p.exact(before[key],current[key]),key)
            self.assertEqual(current['maximum_attempts'],9)

    def test_future_admission_test_files_are_only_known_three(self):
        self.assertEqual(f.ENTRY_ALLOWED-{f.ADMISSION_SOURCE,f.METADATA},{f.PREFIX+n for n in (
            'PositionControl/RegularizedVelocityIntegrationTest.cpp',
            'PositionControl/RegularizedVelocityParamTest.cpp','RegularizedVelocityModuleTest.cpp')})

    def frozen_fixture(self):
        previous=[dict(gate='A',revision='r03_revision04',receipt_sha256='a'*64)]
        return dict(stage='R03-revision05-B',revision=p.REVISION,gate='B',budget=f.budget(),
            historical_budget=p.retained_history(),retained_a=p.retained_a(),previous_gates=previous,
            seed_migration=p.seed_migration(),new_flights=0,execution_authorized=True,
            flight_authorized=True,execution_ready=True,assets={},external_assets={},
            production_changes=[],execution_sha256='e'*64),previous

    def check_frozen(self,record,previous):
        with patch.object(f,'read',return_value=record), \
             patch.object(f._protocol,'require_execution_authority',return_value={}), \
             patch.object(f._protocol,'require_previous_gates',return_value=previous), \
             patch.object(f,'admitted_gate',return_value='B'), \
             patch.object(f,'check_scope',return_value=[]), \
             patch.object(f,'fingerprint',return_value='e'*64):
            return f.check('B')

    def test_frozen_binding_accepts_exact_new_budget(self):
        record,previous=self.frozen_fixture();self.assertIs(self.check_frozen(record,previous),record)

    def test_frozen_binding_rejects_old_budget_or_missing_a(self):
        record,previous=self.frozen_fixture()
        for key,value in (('revision','r03_revision04'),('stage','R03-revision04-B'),('retained_a',{}),
            ('historical_budget',{}),('budget',dict(total=51)),('previous_gates',[]),('seed_migration',{})):
            with self.subTest(key=key),self.assertRaises(ValueError):self.check_frozen({**record,key:value},previous)

    def test_frozen_zero_flight_and_authority_types_are_exact(self):
        record,previous=self.frozen_fixture()
        for key,value in (('new_flights',False),('new_flights',0.0),('execution_authorized',1),
                          ('flight_authorized',None),('execution_ready',False)):
            with self.subTest(key=key),self.assertRaises(ValueError):self.check_frozen({**record,key:value},previous)


if __name__=='__main__':
    unittest.main()
