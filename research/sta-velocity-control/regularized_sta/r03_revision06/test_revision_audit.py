"""D-only qualification/scope adversarial checks; no builds or flights."""
import copy
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
ENTRY='ddb4c2f803e4a79af2bfb2c1ad9a1731688ec660'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


p=load('_r06_audit_protocol',HERE/'protocol.py')
f=load('_r06_audit_freeze',HERE/'freeze.py')
v=load('_r06_audit_verify',HERE/'verify.py')
a=load('_r06_readonly_audit',HERE/'revision_audit.py')


class RevisionAuditTest(unittest.TestCase):
    def test_diagnostic_existing_nonfinite_markers_and_key_order(self):
        self.assertTrue(v.diagnostic_metrics_equal({'x':[float('nan'),float('inf')],'a':False},
                                                 {'a':False,'x':[float('nan'),float('inf')]}))

    def test_diagnostic_numeric_values_types_and_sign_not_normalized(self):
        for x,y in ((1,1.0),(0,False),(1,True),(0.,-0.),(1.,1.0000000000000002),
                    (float('inf'),float('-inf')),(float('nan'),None),(float('nan'),'NaN')):
            with self.subTest(x=x,y=y):self.assertFalse(v.diagnostic_metrics_equal({'x':x},{'x':y}))

    def test_diagnostic_missing_extra_reorder_acceptance_not_ignored(self):
        original={'x':[1,2],'accepted':False}
        for changed in ({'x':[1,2]},dict(original,extra=0),dict(original,x=[2,1]),dict(original,accepted=True)):
            self.assertFalse(v.diagnostic_metrics_equal(original,changed))

    def test_protocol_still_rejects_nonfinite_json(self):
        for value in (float('nan'),float('inf'),float('-inf')):
            with self.assertRaises(ValueError):p.exact({'x':value},{'x':value})

    def fixture(self):
        history=dict(attempts=49,accepted=44,failed=5,takeoffs=48,accepted_for_new_matrix=0)
        gates=[dict(gate=g,revision='r03_revision04' if g=='A' else 'r03_revision05',
                    receipt_sha256=g.lower()*64,accepted=9) for g in 'ABC']
        retained=dict(gates=gates,accepted_design_runs=27,new_attempts=0)
        previous=[{k:g[k] for k in ('gate','revision','receipt_sha256')} for g in gates]
        record=dict(success=True,clean=True,new_flights=0,execution_authorized=True,
            flight_authorized=True,execution_ready=True,stage='R03-revision06-D',
            revision=p.REVISION,gate='D',seed_migration=p.seed_migration(),previous_gates=previous,
            historical_budget=history,retained_abc=retained,maximum_attempts=9,
            new_matrix_attempts=9,historical_attempts=49,total_maximum_attempts=58,
            source_head='b'*40,execution_sha256='c'*64,frozen_sha256='d'*64,firmware_sha256='e'*64)
        return record,history,retained,previous

    def receipt(self,record,history,retained,previous):
        with patch.object(v._protocol,'require_execution_authority',return_value={'approved':True}), \
             patch.object(v,'require_previous_gates',return_value=previous), \
             patch.object(v,'retained_failure',return_value=history), \
             patch.object(v,'retained_abc',return_value=retained),patch.object(v,'fingerprint',return_value='f'*64):
            return v.qualification_receipt(record,'D',Path('/fake-current-qualification'))

    def test_clean_receipt_binds_three_retained_gates_and_58_budget(self):
        args=self.fixture();result=self.receipt(*args)
        self.assertEqual((result['maximum_attempts'],result['new_matrix_attempts'],
                          result['historical_attempts'],result['total_maximum_attempts']),(9,9,49,58))
        self.assertTrue(p.exact(result['retained_abc'],args[2]))
        self.assertTrue(p.exact(result['previous_gates'],args[3]))

    def test_receipt_rejects_dirty_old_nonzero_flights_and_disabled_authority(self):
        args=self.fixture()
        for key,value in (('success',False),('clean',False),('new_flights',1),('revision','r03_revision05'),
            ('stage','R03-revision05-D'),('gate','C'),('execution_authorized',False),
            ('flight_authorized',False),('execution_ready',False)):
            with self.subTest(key=key),self.assertRaises(ValueError):self.receipt({**args[0],key:value},*args[1:])

    def test_receipt_rejects_all_missing_bindings(self):
        args=self.fixture()
        for key,value in (('retained_abc',{}),('historical_budget',{}),('previous_gates',[]),('seed_migration',{})):
            with self.subTest(key=key),self.assertRaises(ValueError):self.receipt({**args[0],key:value},*args[1:])

    def test_receipt_rejects_json_count_and_boolean_aliases(self):
        args=self.fixture()
        for key,value in (('new_flights',False),('new_flights',0.),('maximum_attempts',9.),('new_matrix_attempts',9.),
             ('historical_attempts',49.),('total_maximum_attempts',58.),('clean',1),('success',1),('execution_authorized',1)):
            with self.subTest(key=key),self.assertRaises(ValueError):self.receipt({**args[0],key:value},*args[1:])

    def test_receipt_rejects_each_changed_or_missing_retained_gate(self):
        args=self.fixture()
        for i in range(3):
            for key,value in (('accepted',9.),('receipt_sha256','0'*64),('revision','wrong')):
                changed=copy.deepcopy(args[0]);changed['retained_abc']['gates'][i][key]=value
                with self.subTest(i=i,key=key),self.assertRaises(ValueError):self.receipt(changed,*args[1:])
            changed=copy.deepcopy(args[0]);changed['previous_gates'].pop(i)
            with self.assertRaises(ValueError):self.receipt(changed,*args[1:])

    def test_receipt_refuses_nonfinite_json(self):
        args=self.fixture()
        for value in (float('nan'),float('inf'),float('-inf')):
            with self.assertRaises(ValueError):self.receipt({**args[0],'total_maximum_attempts':value},*args[1:])

    def test_missing_current_authority_never_issues_receipt(self):
        with patch.object(v._protocol,'require_execution_authority',side_effect=PermissionError('Missing')):
            with self.assertRaises(PermissionError):v.qualification_receipt({},'D',Path('/fake'))

    def test_only_d_gate_and_exact_existing_cumulative_masks(self):
        self.assertEqual(list(p.GATES),['D']);self.assertEqual(f.gate_masks('D'),[1,4,3,7])
        source='const bool regularized_gate_admitted = axes == 1 || axes == 4 || axes == 3 || axes == 7;'
        self.assertEqual(f.admitted_gate(source),'D')
        for gate in ('A','B','C','E','d',None):
            with self.assertRaises(ValueError):f.gate_masks(gate)
        for text in ('','axes == 1','true','axes >= 1','axes == 1 || axes == 4 || axes == 7 || axes == 3',
                     'axes == 1 || axes == 4 || axes == 3 || axes == 7 || axes == 2'):
            with self.assertRaises(ValueError):f.admitted_gate('const bool regularized_gate_admitted = '+text+';')
        with self.assertRaises(ValueError):f.admitted_gate(source+source)

    def test_frozen_budget_has_exact_stable_keys_and_counts(self):
        self.assertEqual(f.budget(),dict(total=58,this_gate=9,new_matrix=9,
            retained_attempts=49,retained_accepted=44,retained_invalid=5,replacement_after_this_revision=0))

    def test_all_production_changes_even_comments_or_tests_rejected(self):
        for path in (f.ADMISSION_SOURCE,f.METADATA,f.PREFIX+'RegularizedVelocityModuleTest.cpp',
                     'src/modules/sensors/new.cpp','Tools/new_model.sdf','msg/new.msg'):
            for operation in ('diff','ls-files'):
                def git(*args):
                    if args[0]==operation and not any('/regularized_sta/' in str(x) for x in args):return path
                    return ''
                with self.subTest(path=path,op=operation),patch.object(f,'git',side_effect=git):
                    with self.assertRaisesRegex(ValueError,'no production change'):f.check_scope()

    def test_every_previous_revision_and_repair_immutable(self):
        for tree in f.PRIOR_TREES:
            path='research/sta-velocity-control/regularized_sta/'+tree+'/changed.py'
            for operation in ('diff','ls-files'):
                def git(*args):
                    return path if args[0]==operation and any(path.startswith(str(x).rstrip('/')+'/') for x in args[1:]) else ''
                with self.subTest(tree=tree,op=operation),patch.object(f,'git',side_effect=git):
                    with self.assertRaisesRegex(ValueError,'Immutable prior'):f.check_scope()
        self.assertIn('r03_revision05',f.PRIOR_TREES);self.assertIn('r03_handoff06',f.PRIOR_TREES)

    def test_old_plan_immutable_new_exact_snapshot_allowed(self):
        def changed(name):
            return lambda *args:name if args[0]=='ls-files' and f.PLAN_PREFIX in args else ''
        with patch.object(f,'git',side_effect=changed(f.PLAN_PREFIX+'v1/changed.md')):
            with self.assertRaisesRegex(ValueError,'Immutable prior plan'):f.check_scope()
        with patch.object(f,'git',side_effect=changed(f.NEW_PLAN+'TODO_CN.md')):
            self.assertEqual(f.check_scope(),[])

    def test_private_loaders_ignore_generic_cache_without_overwriting_it(self):
        poison=types.SimpleNamespace(HERE=Path('/wrong'),REVISION='wrong');before=list(sys.path)
        with patch.dict(sys.modules,{'protocol':poison,'freeze':poison}):
            fresh=load('_poison06_freeze',HERE/'freeze.py');verify=load('_poison06_verify',HERE/'verify.py')
            for module in (fresh,verify):self.assertEqual(module._protocol.__file__,str(HERE/'protocol.py'))
            self.assertEqual(verify.freeze.__file__,str(HERE/'freeze.py'))
            self.assertIs(sys.modules['protocol'],poison);self.assertIs(sys.modules['freeze'],poison)
        self.assertEqual(sys.path,before)

    def test_actual_scope_old_source_and_retained_counts(self):
        self.assertTrue(set(f.check_scope()).issubset(f.ALLOWED));self.assertEqual(f.ENTRY,ENTRY)
        result=a.audit()
        self.assertEqual((result['historical_attempts'],result['historical_takeoffs'],result['historical_accepted'],
            result['historical_failed'],result['retained_design_runs'],result['new_planned'],result['total_budget']),
            (49,48,44,5,27,9,58))
        self.assertEqual(result['production_changes_from_revision_entry'],[])
        self.assertIs(result['execution_authority_granted'],False)

    def test_actual_production_sitl_gate_and_parameter_science(self):
        self.assertEqual(v.gate_check('D')['admitted_masks'],[1,4,3,7])
        old=load('_r06_audit_old_protocol',HERE.parent/'r03_revision05/protocol.py')
        before,current=old.load_protocol('D'),p.load_protocol('D')
        for a,b in zip(before['jobs'],current['jobs']):
            self.assertTrue(p.exact({**a,'revision':p.REVISION,'seed':b['seed']},b))
        for key in ('candidate','startup_overrides','diagnostic_gate','constraints','safety','log_requirements','landing','control_loop'):
            if key in before:self.assertTrue(p.exact(before[key],current[key]),key)

    def frozen_fixture(self):
        _,history,retained,previous=self.fixture()
        return dict(stage='R03-revision06-D',revision=p.REVISION,gate='D',budget=f.budget(),
            historical_budget=history,retained_abc=retained,previous_gates=previous,
            seed_migration=p.seed_migration(),new_flights=0,execution_authorized=True,
            flight_authorized=True,execution_ready=True,assets={},external_assets={},
            production_changes=[],execution_sha256='e'*64),history,retained,previous

    def check_frozen(self,record,history,retained,previous):
        with patch.object(f,'read',return_value=record),patch.object(f._protocol,'require_execution_authority',return_value={}), \
             patch.object(f._protocol,'require_previous_gates',return_value=previous), \
             patch.object(f,'retained_failure',return_value=history),patch.object(f,'retained_abc',return_value=retained), \
             patch.object(f,'admitted_gate',return_value='D'),patch.object(f,'check_scope',return_value=[]), \
             patch.object(f,'fingerprint',return_value='e'*64):return f.check('D')

    def test_frozen_accepts_exact_bindings(self):
        args=self.frozen_fixture();self.assertIs(self.check_frozen(*args),args[0])

    def test_frozen_rejects_old_missing_or_changed_bindings(self):
        args=self.frozen_fixture()
        for key,value in (('revision','r03_revision05'),('stage','R03-revision05-D'),('retained_abc',{}),
            ('historical_budget',{}),('budget',dict(total=57)),('previous_gates',[]),('seed_migration',{}),
            ('new_flights',False),('new_flights',0.),('execution_authorized',1),('execution_ready',False)):
            with self.subTest(key=key),self.assertRaises(ValueError):self.check_frozen({**args[0],key:value},*args[1:])


if __name__=='__main__':unittest.main()
