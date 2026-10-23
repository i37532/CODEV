"""Numerical integration negatives; synthetic arrays are not flight evidence."""
import ast
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np

spec=importlib.util.spec_from_file_location('revision11_numeric_test_analyzer',Path(__file__).with_name('analyzer.py'))
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
n=a._numeric


def fixture(mode=3):
    # Reuse the old synthetic builder without any generic import-key changes.
    path=a.OLD/'test_analysis.py';tree=ast.parse(path.read_text())
    nodes=[node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in ('job','Log','fixture')]
    assert len(nodes)==3
    namespace=dict(a=a._inherited,targets=a.targets,np=np,SimpleNamespace=SimpleNamespace)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),namespace)
    x,q,job,_,events=namespace['fixture']('B',mode)
    for data in (x,q):
        for key,value in data.items():
            data[key]=value[:800].astype(np.float32) if value.dtype.kind=='f' else value[:800].copy()
    events['hover_end']=int(x['timestamp'][-1])+10000
    return x,q,job,events


def bad_frame_fixture():
    x,q,job,events=fixture();i=799
    # Keep all predecessor states continuous at the real boundary. Placing
    # the diagnostic candidate last isolates its protected-output check from
    # the following frame's independent continuity check.
    for key in ('nu_before[2]','nu_ideal[2]','nu_applied[2]','a_sta[2]','a_req[2]','a_proxy[2]'):
        x[key][:]=np.float32(-4)
    q['correction[2]'][:]=np.float32(-4)
    values={'s[2]':.005658068228513002,'v[2]':-.0002895215875469148,
      'v_sp[2]':-.005947589874267578,'nu_before[2]':-4.,'nu_ideal[2]':-4.003394603729248,
      'nu_applied[2]':-4.,'a_sta[2]':-4.08001708984375,'a_req[2]':-4.08001708984375,
      'a_proxy[2]':-4.08001708984375,'a_ff[2]':0.,'raw_dt':.012,'used_dt':.012,'input_dt':.012}
    for key,value in values.items():x[key][i]=np.float32(value)
    x['sta_flags'][i]=8;q['h'][i]=np.float32(.012);q['correction[2]'][i]=x['a_sta[2]'][i]
    return x,q,job,events,i


class SealedPatch(unittest.TestCase):
    def test_one_replacement_restores_complete_original_ast(self):
        old,new=n.candidate_ast()
        self.assertNotEqual(ast.dump(old),ast.dump(new))
        calls=[v for v in ast.walk(new) if isinstance(v,ast.Call) and isinstance(v.func,ast.Name) and v.func.id=='_candidate_block']
        self.assertEqual(len(calls),1)
        restored=copy.deepcopy(new)
        class Restore(ast.NodeTransformer):
            def visit_Expr(self,node):
                if isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=='_candidate_block':
                    return ast.parse(n.OLD_REJECTION).body[0]
                return self.generic_visit(node)
        restored=Restore().visit(restored)
        self.assertEqual(ast.dump(old,include_attributes=False),ast.dump(restored,include_attributes=False))

    def test_modified_dependency_hash_rejected(self):
        with patch.object(n,'fingerprint',return_value='0'*64):
            with self.assertRaisesRegex(ValueError,'dependency'):n.candidate_ast()

    def test_replacement_pattern_cannot_broaden(self):
        with patch.object(n,'OLD_REJECTION','if True:\n raise ValueError("different")'):
            with self.assertRaisesRegex(ValueError,'exactly one'):n.candidate_ast()

    def test_no_shared_globals_numpy_or_legacy_function_mutation(self):
        before=dict(a._inherited.r02.check_regularized.__globals__)
        function=a._inherited.r02.check_regularized;allclose=np.allclose
        private,components,_=n.bind(a._inherited)
        x,q,j,_=fixture();private.check_regularized(x,q,j,True)
        self.assertIs(a._inherited.r02.check_regularized,function)
        self.assertEqual(before,function.__globals__)
        self.assertIs(np.allclose,allclose)
        self.assertIsNot(components.__globals__,a._inherited.check_components.__globals__)
        self.assertIs(components.__globals__['r02'],private)

    def test_source_columns_not_rewritten_to_make_candidate_pass(self):
        x,q,j,_,_=bad_frame_fixture()
        original=[{key:value.copy() for key,value in data.items()} for data in (x,q)]
        a._numeric_r02.check_regularized(x,q,j,False)
        for data,before in zip((x,q),original):
            for key in data:self.assertTrue(np.array_equal(data[key],before[key],equal_nan=True),key)


class CandidateAndUnchangedChecks(unittest.TestCase):
    def check(self,x,q,j,steady=False):return a._numeric_r02.check_regularized(x,q,j,steady)

    def test_ordinary_steady_zero_candidates_and_counts(self):
        x,q,j,_=fixture();result=self.check(x,q,j,True)
        self.assertEqual(result['candidate_numeric']['candidates'],800)
        self.assertEqual(result['candidate_numeric']['axes'][0]['branches']['inside_or_boundary'],800)

    def test_real_failure_frame_passes_candidate_but_old_original_still_rejects(self):
        x,q,j,_,_=bad_frame_fixture()
        with self.assertRaisesRegex(ValueError,'rho/raw-dt'):a._inherited.r02.check_regularized(x,q,j,False)
        result=self.check(x,q,j)
        self.assertGreater(result['candidate_numeric']['axes'][0]['max_abs_frozen_decimal_double_reference_residual'],2e-7)
        with self.assertRaisesRegex(ValueError,'rho/raw-dt'):a._inherited.r02.check_regularized(x,q,j,False)

    def test_one_ulp_candidate_corruption_both_directions_rejected(self):
        for target in (-np.inf,np.inf):
            x,q,j,_,i=bad_frame_fixture();x['nu_ideal[2]'][i]=np.nextafter(x['nu_ideal[2]'][i],np.float32(target))
            with self.subTest(target=target),self.assertRaisesRegex(ValueError,'exact binary32 candidate'):self.check(x,q,j)

    def test_actual_selected_epsilon_must_match_bits_not_old_tolerance(self):
        x,q,j,_,i=bad_frame_fixture();q['eps_eff[2]'][i]=np.nextafter(q['eps_eff[2]'][i],np.float32(1))
        with self.assertRaisesRegex(ValueError,'frozen binary32'):self.check(x,q,j)

    def test_applied_cannot_substitute_ideal(self):
        x,q,j,_,i=bad_frame_fixture();x['nu_ideal[2]'][i]=x['nu_applied[2]'][i]
        with self.assertRaisesRegex(ValueError,'exact binary32 candidate'):self.check(x,q,j)

    def test_raw_psi_output_guard_unchanged(self):
        x,q,j,_,i=bad_frame_fixture();x['a_sta[2]'][i]+=.001
        with self.assertRaisesRegex(ValueError,'old-nu/Psi'):self.check(x,q,j)

    def test_applied_state_guard_after_numeric_candidate_still_runs(self):
        x,q,j,_,i=bad_frame_fixture();x['nu_applied[2]'][i]+=.001
        with self.assertRaisesRegex(ValueError,'protected applied'):self.check(x,q,j)

    def test_once_ff_guard_unchanged(self):
        x,q,j,_,i=bad_frame_fixture();x['a_ff[2]'][i]=.001
        with self.assertRaisesRegex(ValueError,'FF missing/double'):self.check(x,q,j)

    def test_cadence_lifecycle_and_hte_guards_unchanged(self):
        x,q,j,_=fixture();q['div_eff'][400]=2
        with self.assertRaisesRegex(ValueError,'cadence'):self.check(x,q,j)
        x,q,j,_=fixture();x['nu_before[2]'][400]=np.float32(.01);x['nu_ideal[2]'][400]=np.float32(.01)
        x['nu_applied[2]'][400]=np.float32(.01);x['a_sta[2]'][400]=np.float32(.01)
        q['correction[2]'][400]=np.float32(.01);x['a_req[2]'][400]=np.float32(.01)
        with self.assertRaisesRegex(ValueError,'HTE'):self.check(x,q,j,True)

    def test_full_component_clock_and_mode_negatives_preserved(self):
        for field in ('timestamp_sample','effective_mode','inner_mode'):
            x,q,j,e=fixture();x[field][400]+=1
            with self.subTest(field=field),self.assertRaises(ValueError):
                a._components(x,q,j,e['hover_start'],e['hover_end'],True)

    def test_pid_and_legacy_esta_components_unchanged(self):
        for mode in (0,1):
            x,q,j,e=fixture(mode)
            old=a._inherited.check_components(x,q,j,e['hover_start'],e['hover_end'],True)[0]
            new=a._components(x,q,j,e['hover_start'],e['hover_end'],True)[0]
            self.assertEqual(old,new)
            self.assertNotIn('candidate_numeric',new['cadence'])


if __name__=='__main__':unittest.main(verbosity=2)
