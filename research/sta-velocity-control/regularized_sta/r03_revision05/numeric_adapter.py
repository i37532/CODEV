"""Versioned candidate-only replacement around immutable R02/R03 checks.

The unique old ideal-nu allclose rejection is replaced, not caught or skipped.
Every other AST node (raw/Psi, applied protection, HTE, lifecycle, cadence) is
unchanged. Private function globals prevent changing any inherited module.
The old binary64 equation remains a diagnostic reference, not the acceptance
oracle for a binary32 candidate. Numeric05 supplies exact staged RN-even and
independent integer/Fraction arithmetic; its compiler assumptions still apply.
"""
import ast
import copy
import hashlib
import importlib.util
from pathlib import Path
import types

import numpy as np

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
R02=HERE.parent/'r02/tools/analyzer.py'
R03=HERE.parent/'r03/analyzer.py'
CHECKER=HERE.parent/'r03_numeric05/checker.py'
PINS={R02:'04acd7847cf21382013bf40af841e3c8e805f41035e50193ca0057783d932ed7',
      R03:'c43f2bff38e874eb23618fc126ccf95f20da38f93ad238b67edabc9a64ce6c72',
      CHECKER:'2eadb904b45b34e93232706418de7e097b7e34970036f0d9c7109707685c37bf'}


def fingerprint(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pinned_inputs():
    values={str(path):fingerprint(path) for path in PINS}
    if any(values[str(path)]!=value for path,value in PINS.items()):
        raise ValueError('Frozen candidate adapter dependency changed')
    return values


def load_checker():
    pinned_inputs()
    spec=importlib.util.spec_from_file_location('r03_revision05_exact_candidate_checker',CHECKER)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


checker=load_checker()
OLD_REJECTION="""if not np.allclose(ideal[commit], expected_ideal, atol=2e-7, rtol=0):
    raise ValueError('RSTA rho/raw-dt candidate mismatch')
"""
NEW_STATEMENT="_candidate_block(x, q, job, axis, commit, before, ideal, expected_ideal)"


def candidate_ast():
    """Exact source AST, changing only one pinned candidate rejection block."""
    pinned_inputs()
    tree=ast.parse(R02.read_text(),filename=str(R02))
    functions=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='check_regularized']
    if len(functions)!=1:raise ValueError('Missing unique frozen check_regularized')
    original=functions[0];revised=copy.deepcopy(original)
    wanted=ast.dump(ast.parse(OLD_REJECTION).body[0],include_attributes=False)
    replacement=ast.parse(NEW_STATEMENT).body[0]
    class Replace(ast.NodeTransformer):
        count=0
        def visit_If(self,node):
            if ast.dump(node,include_attributes=False)==wanted:
                self.count+=1
                return ast.copy_location(copy.deepcopy(replacement),node)
            return self.generic_visit(node)
    transform=Replace();revised=transform.visit(revised)
    if transform.count!=1:raise ValueError('Candidate patch must replace exactly one frozen rejection')
    class Restore(ast.NodeTransformer):
        count=0
        def visit_Expr(self,node):
            if ast.dump(node,include_attributes=False)==ast.dump(replacement,include_attributes=False):
                self.count+=1
                return ast.copy_location(ast.parse(OLD_REJECTION).body[0],node)
            return self.generic_visit(node)
    inverse=Restore();restored=inverse.visit(copy.deepcopy(revised))
    if inverse.count!=1 or ast.dump(restored,include_attributes=False)!=ast.dump(original,include_attributes=False):
        raise ValueError('Candidate patch changed another scientific/safety check')
    return original,revised


def strict_candidates(x,q,job,axis,commit,before,ideal,expected_double):
    """Log scalars stay unrounded; parameter declaration has its own binding."""
    if job['mode']!=3:raise ValueError('New candidate arithmetic is MODE3 only')
    suffix='XYZ'[axis];p=job['parameters'];indices=np.flatnonzero(commit)
    declared_lambda=p['MPC_VC_L2_'+suffix];declared_epsilon=p['MPC_VC_EPS_'+suffix]
    # lambda2 is not a per-sample message field. Its frozen configuration is
    # independently checked against runtime/ULog parameters by the full chain.
    actual_lambda=checker.binary32(declared_lambda)
    maximum_equation=maximum_bound=maximum_old=0.
    branches={'inside_or_boundary':0,'outside':0}
    for offset,i in enumerate(indices):
        evidence=checker.check_candidate(s=x[f's[{axis}]'][i],h=x['raw_dt'][i],
          lambda2=actual_lambda,epsilon=q[f'eps_eff[{axis}]'][i],
          nu_before=before[i],nu_ideal=ideal[i],declared_lambda2=declared_lambda,declared_epsilon=declared_epsilon)
        maximum_equation=max(maximum_equation,abs(evidence['exact_residual']['value']))
        maximum_bound=max(maximum_bound,evidence['absolute_error_bound']['value'])
        maximum_old=max(maximum_old,abs(float(ideal[i])-float(expected_double[offset])))
        branches[evidence['branch']]+=1
    return dict(axis=axis,candidates=len(indices),branches=branches,
      max_abs_unrounded_actual_parameter_equation_residual=maximum_equation,
      max_exact_rounding_bound=maximum_bound,max_abs_frozen_decimal_double_reference_residual=maximum_old,
      lambda2_source='Frozen configuration, separately bound to runtime and initial ULog parameters',
      epsilon_source='Actual selected epsilon message, bitwise bound to frozen configuration')


def clone(function,**overrides):
    namespace=dict(function.__globals__);namespace.update(overrides)
    new=types.FunctionType(function.__code__,namespace,function.__name__,function.__defaults__,function.__closure__)
    new.__kwdefaults__=function.__kwdefaults__
    return new


def bind(inherited):
    """Return private R02 namespace and R03 dispatcher; never mutate originals."""
    sources=pinned_inputs();_,revised=candidate_ast()
    if Path(inherited.r02.check_regularized.__code__.co_filename).resolve()!=R02.resolve():
        raise ValueError('Unexpected R02 candidate implementation path')
    if Path(inherited.check_components.__code__.co_filename).resolve()!=R03.resolve():
        raise ValueError('Unexpected R03 component implementation path')
    code=compile(ast.fix_missing_locations(ast.Module(body=[revised],type_ignores=[])),str(R02),'exec')
    def check_regularized(x,q,job,steady):
        records=[]
        def block(*args):records.append(strict_candidates(*args))
        namespace=dict(inherited.r02.check_regularized.__globals__)
        namespace['_candidate_block']=block
        exec(code,namespace)
        result=namespace['check_regularized'](x,q,job,steady)
        result['candidate_numeric']=dict(revision='numeric05',source_sha256=sources,
          candidates=sum(item['candidates'] for item in records),axes=records,
          arithmetic='binary32 staged RN-even plus independent integer/Fraction oracle',
          scope='Ideal candidate only; unchanged surrounding checks validate raw/applied/lifecycle',
          compiler_limit='No universal FMA/reassociation/reciprocal/FTZ guarantee; frozen build and real logs remain required')
        return result
    private=types.SimpleNamespace(**vars(inherited.r02))
    private.check_regularized=check_regularized
    components=clone(inherited.check_components,r02=private)
    return private,components,dict(source_sha256=sources,
      only_change='Unique ideal-nu fixed allclose rejection replaced by exact staged candidate audit',
      other_ast_nodes_unchanged=True,shared_globals_modified=False)
