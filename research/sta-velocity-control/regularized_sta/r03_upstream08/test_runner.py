"""Fake edge I/O, real BSON/restore/finite ledger logic; no simulator started."""
import ast
from contextlib import ExitStack,redirect_stdout
import copy
import importlib.util
import inspect
import io
import json
from pathlib import Path
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('up08_runner_test',HERE/'runner.py');r=importlib.util.module_from_spec(s);s.loader.exec_module(r)


class Fixture:
    def __init__(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='up08-fake-');self.root=Path(self.tmp.name)
        self.repo=self.root/'repo';self.bin=self.repo/'build/px4_sitl_default/bin';self.bin.mkdir(parents=True)
        (self.bin/'px4').write_bytes(b'fixture');self.rootfs=self.repo/'build/px4_sitl_default/tmp/rootfs'
        (self.rootfs/'eeprom').mkdir(parents=True);self.param=self.rootfs/'eeprom/parameters_10016'
        self.p=copy.deepcopy(r.api.load_protocol());self.output=self.root/'external/R03_upstream08/diagnostic01/batch01'
        self.p['artifacts']['new_run_root']=str(self.output)
        self.qpath=self.output.parent/'qualification01/evidence.json';self.qpath.parent.mkdir(parents=True)
        self.p['qualification_path']=str(self.qpath);self.head='a'*40
        self.q=dict(success=True,clean=True,source_head=self.head,firmware_sha256=r.digest(self.bin/'px4'))
        r.save(self.qpath,self.q);r.save(self.qpath.parent/'authorization.json',{'approved':True})
        controls={**self.p['jobs'][0]['parameters'],'MPC_VCT_TEST':0}
        self.frozen=dict(control_parameters=controls,assets={},external_assets={})
        vals={**controls,'SYS_AUTOSTART':10016,'SDLOG_PROFILE':1,'USER_UNRELATED':17}
        self.types={k:'Int32' if isinstance(v,int) else 'Float' for k,v in vals.items()}
        r.save(self.repo/'build/px4_sitl_default/parameters.json',dict(parameters=[dict(name=k,default=v,type=self.types[k]) for k,v in vals.items()]))
        self.original=r.historical.encode_bson(vals,self.types);self.param.write_bytes(self.original)
        old=self.root/'old';old.mkdir()
        self.history=dict(attempts=52,takeoffs=51,accepted=46,failed=6,accepted_for_new_matrix=0,batches=[dict(root=str(old))])
        self.abc={'accepted_design_runs':27};self.p.update(historical_budget=self.history,retained_abc=self.abc)
        self.calls=[];self.analysis_calls=[];self.failure=None;self.analysis_error=False;self.pair_error=False
        self.qualification=Mock(return_value=self.q)
    def close(self):self.tmp.cleanup()
    def git(self,*args):
        return self.head if args==('rev-parse','HEAD') else ('research/sta-velocity-regularized' if args==('branch','--show-current') else '')
    def flight(self,path,checks,scenario):
        self.calls.append(checks.job['id']);path.mkdir()
        vals=r.historical.persisted_bson(self.param.read_bytes())
        r.historical.check_parameters(vals,checks.expected)
        assert vals['USER_UNRELATED']==17 and vals['SDLOG_PROFILE']==3089
        checks.log_root=self.root/'fake-tmpfs'
        r.save(path/'job.json',checks.job);r.save(path/'result.json',dict(success=self.failure!=len(self.calls)))
        if self.failure==len(self.calls):raise RuntimeError('Injected flight/monitor failure')
    def analyze(self,path,p,job):
        assert self.param.read_bytes()==self.original
        assert p['qualification_path']==str(self.qpath.resolve())
        self.analysis_calls.append(job['id'])
        result=dict(accepted=False,flight_accepted=False,accepted_for_R03=0,diagnostic_checks_complete=not self.analysis_error,
                    scientific_checks_complete=True,job=job)
        r.save(path/'diagnostic_metrics.json',result);return result
    def compare(self,a,b):return dict(accepted=False,development_risk_passed=not self.pair_error)
    def patches(self):
        c=ExitStack()
        for obj,name,value in [(r,'REPO',self.repo),(r,'BIN',self.bin),(r,'ROOTFS',self.rootfs),
          (r,'active_simulators',lambda:[]),(r.base,'active_simulators',lambda:[]),
          (r.api,'load_protocol',lambda:copy.deepcopy(self.p)),(r.api,'require_execution_authority',Mock()),
          (r.api,'require_qualification',self.qualification),(r.api,'retained_history',lambda:copy.deepcopy(self.history)),
          (r.api,'retained_abc',lambda:copy.deepcopy(self.abc)),(r.api,'fresh_seeds',lambda:dict(accepted=True)),
          (r.historical,'git',self.git),(r,'preflight',lambda *args:(self.frozen,self.root/'plugins')),
          (r.historical.shutil,'disk_usage',lambda path:SimpleNamespace(free=20*1024**3)),
          (r.base.ram_log,'release_archived',lambda *args:None),(r.historical,'noise_prefix',lambda path:r.base.np.zeros(4)),
          (r,'execution_checks_class',lambda:lambda p,e,j,pl,q,h,b:SimpleNamespace(p=p,expected=e,job=j,qualification_path=q))]:
            c.enter_context(patch.object(obj,name,value))
        return c
    def execute(self,p=None):
        with self.patches():return r.execute(p or self.p,self.head,self.qpath,single_flight=self.flight,analyze=self.analyze,compare=self.compare)


class BindingTests(unittest.TestCase):
    def test_flight_exact_inverse_and_old_globals_untouched(self):
        old=dict(r.base.flight_main.__globals__);f,proof=r.bind_flight_body(r.base.flight_main)
        self.assertTrue(proof['inverse_ast_equal']);self.assertEqual(proof['changed_expressions'],1)
        self.assertEqual(old,r.base.flight_main.__globals__);self.assertIsNot(f.__globals__,r.base.flight_main.__globals__)
        self.assertEqual(f.__globals__['__file__'],str(HERE/'runner.py'))
    def test_changed_authority_ast_rejected(self):
        def fake(output,checks,scenario):return None
        with self.assertRaises(ValueError):r.bind_flight_body(fake)
    def test_full_monitor_inherited(self):
        self.assertIs(r.Checks.monitor,r.base.Checks.monitor);self.assertIs(r.Checks.__call__,r.base.Checks.__call__)
        self.assertIs(r.Checks.configuration,r.base.Checks.configuration)
    def test_prearm_factory_keeps_checks(self):
        cls=r.execution_checks_class();self.assertTrue(issubclass(cls,r.Checks));self.assertIn('PrearmPrepared',cls.__name__)
    def test_model_environment_body_equal(self):
        def body(fn):
            tree=ast.parse(textwrap.dedent(inspect.getsource(fn))).body[0]
            start=next(i for i,n in enumerate(tree.body) if isinstance(n,ast.Assign) and ast.unparse(n.targets[0])=='self.log_root')
            class Normalize(ast.NodeTransformer):
                def visit_Attribute(self,node):
                    self.generic_visit(node)
                    if isinstance(node.value,ast.Name) and node.value.id=='base' and node.attr in ('ram_log','os'):
                        return ast.Name(id=node.attr,ctx=ast.Load())
                    return node
            return ast.dump(Normalize().visit(ast.Module(body=tree.body[start:],type_ignores=[])))
        self.assertEqual(body(r.Checks.prepare_environment),body(r.base.Checks.prepare_environment))
    def test_dryrun_never_executes(self):
        with patch.object(r,'execute',side_effect=AssertionError('flight')),redirect_stdout(io.StringIO()) as out:
            self.assertEqual(r.main([]),0)
        self.assertTrue(json.loads(out.getvalue())['dry_run'])


class ExecutionTests(unittest.TestCase):
    def setUp(self):self.f=Fixture()
    def tearDown(self):self.f.close()
    def test_two_diagnostics_restore_unrelated_bson_and_no_acceptance(self):
        x=self.f.execute();self.assertTrue(x['success']);self.assertEqual(self.f.calls,['diag001','diag002'])
        self.assertEqual(x['accepted_for_R03'],0);self.assertFalse(x['r03_gate_pass']);self.assertEqual(self.f.param.read_bytes(),self.f.original)
        self.assertEqual(x['unattempted'],[])
    def test_first_flight_failure_stops_second_and_restores(self):
        self.f.failure=1
        with self.assertRaises(RuntimeError):self.f.execute()
        x=r.api.read(self.f.output/'ledger.json');self.assertEqual(self.f.calls,['diag001']);self.assertEqual(x['unattempted'],['diag002'])
        self.assertEqual(self.f.param.read_bytes(),self.f.original);self.assertEqual(x['attempts'][0]['status'],'failed')
    def test_second_failure_no_third_retry(self):
        self.f.failure=2
        with self.assertRaises(RuntimeError):self.f.execute()
        self.assertEqual(len(self.f.calls),2)
        with self.assertRaises(RuntimeError):self.f.execute()
        self.assertEqual(len(self.f.calls),2)
    def test_invalid_analysis_stops_after_first(self):
        self.f.analysis_error=True
        with self.assertRaises(RuntimeError):self.f.execute()
        self.assertEqual(self.f.calls,['diag001']);self.assertEqual(self.f.param.read_bytes(),self.f.original)
    def test_pair_risk_failure_is_not_acceptance(self):
        self.f.pair_error=True
        with self.assertRaises(RuntimeError):self.f.execute()
        x=r.api.read(self.f.output/'ledger.json');self.assertFalse(x['success']);self.assertEqual(x['accepted_for_R03'],0)
    def test_unknown_extra_batch_rejected(self):
        (self.f.output.parent.parent/'diagnostic02/batch01').mkdir(parents=True)
        with self.assertRaises(RuntimeError):self.f.execute()
        self.assertFalse(self.f.calls)
    def test_qualification_failure_before_parameters(self):
        self.f.qualification.side_effect=RuntimeError('bad qualification')
        with self.assertRaises(RuntimeError):self.f.execute()
        self.assertFalse(self.f.calls);self.assertEqual(self.f.param.read_bytes(),self.f.original)
    def test_profile_changed_rejected_before_attempt(self):
        v=r.historical.persisted_bson(self.f.original);v['SDLOG_PROFILE']=131
        self.f.param.write_bytes(r.historical.encode_bson(v,self.f.types));before=self.f.param.read_bytes()
        with self.assertRaisesRegex(RuntimeError,'profile'):self.f.execute()
        self.assertFalse(self.f.calls);self.assertEqual(self.f.param.read_bytes(),before)
    def test_canonical_order_budget_type_values_before_qualification(self):
        for mutate in [lambda p:p.update(maximum_attempts=2.0),lambda p:p.update(diagnostic_only=1),
                       lambda p:p['jobs'].reverse(),lambda p:p['jobs'][1]['parameters'].update(MPC_VC_L2_Z=2),
                       lambda p:p['jobs'][0].update(seed=float('nan')),lambda p:p['artifacts'].update(new_run_root='/tmp/elsewhere')]:
            p=copy.deepcopy(self.f.p);mutate(p);self.f.qualification.reset_mock()
            with self.assertRaises(RuntimeError):self.f.execute(p)
            self.f.qualification.assert_not_called();self.assertFalse(self.f.calls)
    def test_reject_r03_accepted_output(self):
        old=self.f.analyze
        def invalid(*args):x=old(*args);x['accepted']=True;return x
        self.f.analyze=invalid
        with self.assertRaises(RuntimeError):self.f.execute()
        self.assertEqual(len(self.f.calls),1)
    def test_wrong_job_output_rejected(self):
        old=self.f.analyze
        def invalid(*args):x=old(*args);x['job']={};return x
        self.f.analyze=invalid
        with self.assertRaises(RuntimeError):self.f.execute()
        self.assertEqual(len(self.f.calls),1)
    def test_archive_failure_restores_and_stops(self):
        with self.f.patches(),patch.object(r.base.ram_log,'release_archived',side_effect=RuntimeError('archive')):
            with self.assertRaises(RuntimeError):r.execute(self.f.p,self.f.head,self.f.qpath,single_flight=self.f.flight,analyze=self.f.analyze,compare=self.f.compare)
        self.assertEqual(len(self.f.calls),1);self.assertEqual(self.f.param.read_bytes(),self.f.original)
    def test_incomplete_existing_dir_cannot_resume(self):
        self.f.output.mkdir()
        with self.assertRaises(RuntimeError):self.f.execute()
        self.assertFalse(self.f.calls)
    def test_direct_checks_need_actual_registered_pending_attempt(self):
        checks=r.Checks.__new__(r.Checks);checks.source_head=self.f.head;checks.qualification_path=self.f.qpath
        checks.job=self.f.p['jobs'][0];checks.backup=self.f.output/'original_parameters.bson'
        checks.p={**self.f.p,'startup_overrides':{**self.f.p['startup_overrides'],**checks.job['parameters']}}
        with self.f.patches():
            with self.assertRaises(FileNotFoundError):checks.require_execution()
            self.f.qualification.assert_not_called()
    def test_wrong_direct_output_rejected_before_flight(self):
        checks=SimpleNamespace(p=self.f.p,job=self.f.p['jobs'][0],require_execution=Mock())
        with self.f.patches():
            with self.assertRaisesRegex(RuntimeError,'output'):r.flight_authority(self.f.root/'not-registered',checks)
        self.assertFalse(self.f.calls)
    def test_restore_never_writes_while_process_survives(self):
        self.f.output.mkdir();backup=self.f.output/'original_parameters.bson';backup.write_bytes(self.f.original)
        self.f.param.write_bytes(b'changed parameters')
        with patch.object(r.base,'active_simulators',return_value=[('fake','px4')]):
            with self.assertRaisesRegex(RuntimeError,'restoration'):
                r.restore_parameters(self.f.param,self.f.original,self.f.output/'diag001',backup,self.f.head,self.f.p['jobs'][0])
        self.assertEqual(self.f.param.read_bytes(),b'changed parameters')


if __name__=='__main__':unittest.main(verbosity=2)
