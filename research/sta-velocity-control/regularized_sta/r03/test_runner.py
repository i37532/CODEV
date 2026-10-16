#!/usr/bin/env python3
"""Offline R03 runner tests: fake processes, real BSON/ledger/restore logic."""
import ast
from contextlib import ExitStack, redirect_stdout
import copy
import fcntl
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('r03_runner_under_test', HERE/'runner.py')
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)


class Fixture:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='r03-runner-offline-')
        self.root = Path(self.tmp.name)
        self.repo = self.root/'repo'; self.bin = self.repo/'build/px4_sitl_default/bin'
        self.rootfs = self.repo/'build/px4_sitl_default/tmp/rootfs'
        self.bin.mkdir(parents=True); (self.bin/'px4').write_bytes(b'offline fixture binary')
        (self.rootfs/'eeprom').mkdir(parents=True)
        version = self.repo/'build/px4_sitl_default/src/lib/version/build_git_version.h'
        version.parent.mkdir(parents=True); self.head = 'a'*40; version.write_text(self.head)
        self.p = copy.deepcopy(r.local_module('protocol').load_protocol('A'))
        self.output = self.root/'external/R03/A/batch01'
        self.p['artifacts']['new_run_root'] = str(self.output)
        config = self.root/'config'; config.mkdir(); self.p['config_dir'] = str(config)
        plugins = self.root/'plugins'; plugins.mkdir(); r.save(plugins/'manifest.json', {})
        self.p['plugins'] = str(plugins)
        self.execution = self.root/'execution.json'; r.save(self.execution, self.p['jobs'])
        self.p['execution_path'] = str(self.execution)
        self.qpath = self.root/'external/R03/A/qualification01/evidence.json'
        self.qpath.parent.mkdir(parents=True); self.p['qualification_path'] = str(self.qpath)
        self.q = dict(success=True, gate='A', source_head=self.head, firmware_sha256=r.digest(self.bin/'px4'))
        r.save(self.qpath, self.q)
        r.save(self.qpath.parent/'authorization.json', dict(approved=True, stage='R03-A', gate='A',
            source_head=self.head, maximum_attempts=9, total_maximum_attempts=36,
            qualification_sha256=r.digest(self.qpath)))
        controls = {**self.p['jobs'][0]['parameters'], 'MPC_VCT_TEST': 0}
        defaults = {**self.p['startup_overrides'], **controls, 'SDLOG_PROFILE': 131, 'SYS_AUTOSTART': 10016}
        self.types = {k: 'Int32' if isinstance(v, int) else 'Float' for k,v in defaults.items()}
        # An unrelated persistent value must survive every complete backup/restore.
        defaults['USER_FIXTURE'] = 17; self.types['USER_FIXTURE'] = 'Int32'
        definitions = [dict(name=k, default=v, type=self.types[k]) for k,v in defaults.items()]
        r.save(self.repo/'build/px4_sitl_default/parameters.json', dict(parameters=definitions))
        self.original = r.historical.encode_bson(defaults, self.types)
        self.param = self.rootfs/'eeprom/parameters_10016'; self.param.write_bytes(self.original)
        r.save(config/'frozen.json', dict(assets={}, external_assets={}, control_parameters=controls))
        self.api = SimpleNamespace(require_qualification=Mock(return_value=self.q),
            fresh_seeds=Mock(return_value=dict(accepted=True, matches=[])),
            load_protocol=Mock(return_value=copy.deepcopy(self.p)))
        self.calls = []; self.analyzed = []; self.fail_flight = None; self.fail_analysis = None

    def git(self, *args):
        if args == ('branch','--show-current'): return 'research/sta-velocity-regularized'
        if args == ('rev-parse','HEAD'): return self.head
        return ''

    def flight(self, output, checks, scenario):
        self.calls.append(checks.job['id']); output.mkdir()
        self.assert_applied(checks)
        checks.log_root = self.root/'fake-owned-tmpfs'
        r.qualification_reference(output,checks.qualification_path)
        r.save(output/'run_protocol.json',checks.p)
        r.save(output/'job.json', checks.job)
        r.save(output/'result.json', dict(success=True, source_head=self.head))
        if len(self.calls) == self.fail_flight: raise RuntimeError('Injected owned-process failure')

    def assert_applied(self, checks):
        actual = r.historical.persisted_bson(self.param.read_bytes())
        r.historical.check_parameters(actual, checks.expected)
        if actual['USER_FIXTURE'] != 17: raise AssertionError('Lost unrelated BSON parameter')

    def analyze(self, output, protocol, job):
        if self.param.read_bytes() != self.original: raise AssertionError('Analyze before restoration')
        if protocol['qualification_path'] != str(self.qpath.resolve()): raise AssertionError('Wrong actual qualification binding')
        ref=json.loads((output/'qualification_reference.json').read_text())
        if ref!=dict(path=str(self.qpath.resolve()),sha256=r.digest(self.qpath)):
            raise AssertionError('Missing exact qualification sidecar')
        receipt = json.loads((output/'parameter_restore.json').read_text())
        if not receipt['parameter_restore_exact'] or not receipt['stopped_before_restore']:
            raise AssertionError('Missing real restore receipt')
        self.analyzed.append(job['id'])
        value = dict(accepted=len(self.analyzed) != self.fail_analysis, job=job)
        r.save(output/'r03_metrics.json', value)
        return value

    def patches(self):
        stack = ExitStack()
        replacements = [(r,'REPO',self.repo), (r,'ROOTFS',self.rootfs), (r,'BIN',self.bin),
            (r,'local_module',Mock(return_value=self.api)), (r,'active_simulators',Mock(return_value=[])),
            (r.historical,'git',Mock(side_effect=lambda *a:self.git(*a))),
            (r.historical.shutil,'disk_usage',Mock(return_value=SimpleNamespace(free=30*1024**3))),
            (r.historical,'require_passive',Mock()), (r.historical,'require_qualification',Mock()),
            (r.historical,'validate_receiver_profile',Mock()), (r.historical.socket,'socket',MagicMock()),
            (r.ram_log,'release_archived',Mock()),
            (r.historical,'noise_prefix',Mock(side_effect=lambda path:r.np.full((5,7),
                json.loads((path/'job.json').read_text())['seed'],dtype=float)))]
        for obj,name,value in replacements: stack.enter_context(patch.object(obj,name,value))
        stack.enter_context(redirect_stdout(io.StringIO()))
        return stack

    def execute(self, **kw):
        with self.patches():
            return r.execute_gate(self.p,self.head,self.qpath,single_flight=self.flight,
                analyze=self.analyze,compare=kw.get('compare',lambda a,b:dict(accepted=True)))

    def close(self): self.tmp.cleanup()


class SourceContract(unittest.TestCase):
    def test_owned_startup_flight_landing_archive_body_unchanged(self):
        old = (r.REPO/'research/sta-velocity-control/v08/protocol02/flight.py').read_text()
        new = (HERE/'runner.py').read_text()
        marker = '    # Opt-in M10 only; prior milestones retain exactly the original timing.'
        old_body = old[old.index(marker):old.index('\n\nif __name__')].strip()
        new_body = new[new.index(marker):new.index('\n\nclass Checks')].strip()
        self.assertEqual(old_body,new_body)
        self.assertEqual(r.digest(r.REPO/'research/sta-velocity-control/v08/protocol02/flight.py'),
            'ed6901ce8203821943241bf4108f6b6a6d1768b80b2c6a4e65f687a6d1ed9cfb')
        for name in ('active_simulators','shutdown_owned'):
            a = next(n for n in ast.parse(old).body if isinstance(n,ast.FunctionDef) and n.name==name)
            b = next(n for n in ast.parse(new).body if isinstance(n,ast.FunctionDef) and n.name==name)
            self.assertEqual(ast.dump(a),ast.dump(b))

    def test_default_dry_run_and_missing_sha_never_execute(self):
        p = r.local_module('protocol').load_protocol('A')
        api = SimpleNamespace(validate_manifest=Mock(),load_protocol=Mock(return_value=p))
        with patch.object(r,'local_module',return_value=api), patch.object(r,'execute_gate') as execute, redirect_stdout(io.StringIO()):
            self.assertEqual(r.main([]),0); execute.assert_not_called()
            with self.assertRaisesRegex(RuntimeError,'source SHA'): r.main(['--execute'])
            execute.assert_not_called()

    def test_single_flight_requires_qualified_batch_before_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'not-created'
            with self.assertRaisesRegex(RuntimeError,'Qualified'): r.flight_main(output,None,None)
            self.assertFalse(output.exists())

    def test_qualification_rejection_precedes_lock_or_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=dict(gate='A',artifacts=dict(new_run_root=str(Path(tmp)/'R03/A/batch01')))
            api=SimpleNamespace(require_qualification=Mock(side_effect=ValueError('not qualified')),
                load_protocol=Mock(return_value=copy.deepcopy(p)))
            with patch.object(r,'local_module',return_value=api), self.assertRaises(ValueError):
                r.execute_gate(p,'a'*40,Path(tmp)/'q.json')
            self.assertEqual(list(Path(tmp).iterdir()),[])


class GateLoop(unittest.TestCase):
    def setUp(self): self.f=Fixture()
    def tearDown(self): self.f.close()

    def test_nine_real_bson_transactions_and_six_pairs(self):
        result=self.f.execute()
        self.assertTrue(result['success']); self.assertTrue(result['parameter_restore_exact'])
        self.assertEqual(len(result['attempts']),9); self.assertEqual(len(result['pairs']),6)
        self.assertEqual(len(self.f.calls),9); self.assertEqual(len(self.f.analyzed),9)
        self.assertEqual(self.f.param.read_bytes(),self.f.original)
        self.assertEqual((self.f.output/'original_parameters.bson').read_bytes(),self.f.original)
        self.f.api.fresh_seeds.assert_called_once_with('A')
        journal=[json.loads(x) for x in (self.f.output/'journal.jsonl').read_text().splitlines()]
        self.assertEqual([x['event'] for x in journal].count('attempt'),9)
        self.assertEqual([x['event'] for x in journal].count('restore'),9)
        self.assertEqual(journal[-1]['event'],'gate_end')
        for job in self.f.p['jobs']:
            receipt=json.loads((self.f.output/job['id']/'parameter_restore.json').read_text())
            self.assertEqual(receipt['original_parameter_sha256'],receipt['restored_parameter_sha256'])
            self.assertEqual(receipt['remaining_simulators'],[])

    def test_failure_first_consumes_one_no_retry(self):
        self.f.fail_flight=1
        with self.assertRaisesRegex(RuntimeError,'owned-process'): self.f.execute()
        self.assert_stop(1)
        with self.assertRaisesRegex(RuntimeError,'already exists'): self.f.execute()
        self.assertEqual(len(self.f.calls),1)

    def test_failure_fifth_consumes_five_preserves_four(self):
        self.f.fail_flight=5
        with self.assertRaises(RuntimeError): self.f.execute()
        self.assert_stop(5)

    def test_failure_ninth_does_not_claim_complete(self):
        self.f.fail_analysis=9
        with self.assertRaisesRegex(RuntimeError,'ULog'): self.f.execute()
        self.assert_stop(9)

    def test_pair_failure_stops_without_replacement(self):
        with self.assertRaisesRegex(RuntimeError,'paired'): self.f.execute(compare=lambda a,b:dict(accepted=False))
        self.assert_stop(2)
        record=json.loads((self.f.output/'run002_paired_checks_at_stop.json').read_text())
        self.assertEqual(record,[dict(accepted=False)])

    def assert_stop(self,count):
        result=json.loads((self.f.output/'ledger.json').read_text())
        self.assertFalse(result['success']); self.assertTrue(result['parameter_restore_exact'])
        self.assertEqual(len(result['attempts']),count); self.assertEqual(len(result['unattempted']),9-count)
        self.assertEqual(result['attempts'][-1]['status'],'failed')
        self.assertEqual(self.f.param.read_bytes(),self.f.original)
        self.assertEqual(len(self.f.calls),count)

    def test_missing_type_before_launch_is_retained_and_restored(self):
        path=self.f.repo/'build/px4_sitl_default/parameters.json'
        data=json.loads(path.read_text()); data['parameters']=[x for x in data['parameters'] if x['name']!='USER_FIXTURE']
        r.save(path,data)
        with self.assertRaises(KeyError): self.f.execute()
        self.assertEqual(self.f.calls,[])
        ledger=json.loads((self.f.output/'ledger.json').read_text())
        self.assertEqual(len(ledger['attempts']),1); self.assertTrue(ledger['parameter_restore_exact'])
        self.assertEqual(self.f.param.read_bytes(),self.f.original)

    def test_fresh_seed_conflict_blocks_before_parameter_write(self):
        self.f.api.fresh_seeds.return_value=dict(accepted=False)
        with self.assertRaisesRegex(RuntimeError,'Seed history'): self.f.execute()
        self.assertFalse(self.f.output.exists()); self.assertEqual(self.f.param.read_bytes(),self.f.original)

    def test_second_qualification_exact_path_survives_all_rounds(self):
        old=self.f.qpath
        self.f.qpath=old.parent.parent/'qualification02/evidence.json';self.f.qpath.parent.mkdir()
        self.f.qpath.write_bytes(old.read_bytes())
        (self.f.qpath.parent/'authorization.json').write_bytes((old.parent/'authorization.json').read_bytes())
        result=self.f.execute();self.assertTrue(result['success'])
        for job in self.f.p['jobs']:
            run=self.f.output/job['id']
            self.assertEqual(json.loads((run/'qualification_reference.json').read_text())['path'],str(self.f.qpath))
            self.assertEqual(json.loads((run/'run_protocol.json').read_text())['qualification_path'],str(self.f.qpath))

    def test_gate_capacity_below_twelve_gib_blocks_before_attempt(self):
        with self.f.patches(),patch.object(r.historical.shutil,'disk_usage',return_value=SimpleNamespace(free=11*1024**3)):
            with self.assertRaisesRegex(RuntimeError,'12 GiB'):
                r.execute_gate(self.f.p,self.f.head,self.f.qpath,single_flight=self.f.flight,analyze=self.f.analyze,compare=lambda a,b:dict(accepted=True))
        self.assertFalse(self.f.output.exists());self.assertEqual(self.f.calls,[])

    def test_programmatic_protocol_cannot_mutate_gains_root_order_or_budget(self):
        original=copy.deepcopy(self.f.p)
        for change in ('gain','output','order','budget','startup'):
            self.f.p=copy.deepcopy(original)
            if change=='gain':self.f.p['jobs'][1]['parameters']['MPC_VC_L1_X']+=.01
            elif change=='output':self.f.p['artifacts']['new_run_root']=str(self.f.root/'alternative-batch')
            elif change=='order':self.f.p['jobs'][1],self.f.p['jobs'][2]=self.f.p['jobs'][2],self.f.p['jobs'][1]
            elif change=='budget':self.f.p['maximum_attempts']=10
            else:self.f.p['startup_overrides']['MPC_VC_L1_X']+=.01
            with self.subTest(change=change),self.assertRaisesRegex(RuntimeError,'canonical'):
                self.f.execute()
            self.assertEqual(self.f.calls,[]);self.assertEqual(self.f.param.read_bytes(),self.f.original)
            self.assertFalse(self.f.output.exists())
            self.assertFalse((self.f.output.parent.parent/'.runner.lock').exists())

    def test_boolean_cannot_impersonate_integer_before_qualification(self):
        original=copy.deepcopy(self.f.p)
        for key,value in (('mode',True),('axes',True),('divisor',True)):
            self.f.p=copy.deepcopy(original);self.f.p['jobs'][1][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(RuntimeError,'canonical'):
                self.f.execute()
            self.assert_no_admission_or_mutation()

    def test_float_cannot_impersonate_integer_before_qualification(self):
        original=copy.deepcopy(self.f.p)
        for key,value in (('mode',1.0),('axes',1.0),('seed',71001.0),('main_duration_s',32.0)):
            self.f.p=copy.deepcopy(original);self.f.p['jobs'][1][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(RuntimeError,'canonical'):
                self.f.execute()
            self.assert_no_admission_or_mutation()
        self.f.p=copy.deepcopy(original);self.f.p['maximum_attempts']=9.0
        with self.assertRaisesRegex(RuntimeError,'canonical'):self.f.execute()
        self.assert_no_admission_or_mutation()

    def test_nonfinite_protocol_rejected_before_qualification(self):
        original=copy.deepcopy(self.f.p)
        for value in (float('nan'),float('inf'),float('-inf')):
            self.f.p=copy.deepcopy(original);self.f.p['jobs'][1]['parameters']['MPC_VC_L1_X']=value
            with self.subTest(value=value),self.assertRaisesRegex(RuntimeError,'noncanonical JSON'):
                self.f.execute()
            self.assert_no_admission_or_mutation()

    def assert_no_admission_or_mutation(self):
        self.f.api.require_qualification.assert_not_called()
        self.assertEqual(self.f.calls,[])
        self.assertEqual(self.f.param.read_bytes(),self.f.original)
        self.assertFalse(self.f.output.exists())
        self.assertFalse((self.f.output.parent.parent/'.runner.lock').exists())

    def test_low_tmpfs_blocks_before_new_attempt(self):
        with self.f.patches(),patch.object(r.historical.shutil,'disk_usage',side_effect=lambda path:SimpleNamespace(free=100 if str(path)=='/dev/shm' else 30*1024**3)):
            with self.assertRaisesRegex(RuntimeError,'disk/tmpfs'):
                r.execute_gate(self.f.p,self.f.head,self.f.qpath,single_flight=self.f.flight,analyze=self.f.analyze,compare=lambda a,b:dict(accepted=True))
        ledger=json.loads((self.f.output/'ledger.json').read_text())
        self.assertEqual(ledger['attempts'],[]);self.assertEqual(len(ledger['unattempted']),9)
        self.assertEqual(self.f.param.read_bytes(),self.f.original)

    def test_source_change_between_rounds_stops_without_new_attempt(self):
        original=self.f.flight
        def changed(*args):
            original(*args)
            self.f.git=lambda *a: 'research/sta-velocity-regularized' if a==('branch','--show-current') else ('b'*40 if a==('rev-parse','HEAD') else '')
        self.f.flight=changed
        with self.assertRaisesRegex(RuntimeError,'Source/process'): self.f.execute()
        ledger=json.loads((self.f.output/'ledger.json').read_text())
        self.assertEqual(len(ledger['attempts']),1); self.assertFalse(ledger['success'])
        self.assertEqual(ledger['attempts'][0]['status'],'accepted')
        self.assertTrue(ledger['parameter_restore_exact'])

    def test_concurrent_gate_lock_rejected_before_batch(self):
        lockpath=self.f.output.parent.parent/'.runner.lock'
        with lockpath.open('a') as lock:
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError,'runner lock'): self.f.execute()
        self.assertFalse(self.f.output.exists()); self.assertEqual(self.f.calls,[])

    def test_lingering_foreign_process_not_killed_or_overwritten(self):
        run=self.f.root/'run'; run.mkdir(); self.f.param.write_bytes(b'current live state')
        with patch.object(r,'active_simulators',return_value=[('99999','px4')]), self.assertRaisesRegex(RuntimeError,'restoration'):
            r.restore_parameters(self.f.param,self.f.original,run,self.f.root/'backup',self.f.head,self.f.p['jobs'][0])
        self.assertEqual(self.f.param.read_bytes(),b'current live state')
        receipt=json.loads((run/'parameter_restore.json').read_text())
        self.assertFalse(receipt['stopped_before_restore']); self.assertFalse(receipt['parameter_restore_exact'])


class BudgetAndSelection(unittest.TestCase):
    def setUp(self): self.p=copy.deepcopy(r.local_module('protocol').load_protocol('A'))

    def test_missing_or_changed_budget_rejected(self):
        for value in (None,35,37):
            p=copy.deepcopy(self.p)
            if value is None: del p['total_maximum_attempts']
            else: p['total_maximum_attempts']=value
            with self.assertRaises(RuntimeError): r.Admission(p,lambda a,b:dict(accepted=True))

    def test_invalid_order_pairing_and_exhausted_state(self):
        admission=r.Admission(self.p,lambda a,b:dict(accepted=True))
        with self.assertRaisesRegex(RuntimeError,'order'): admission.before(self.p['jobs'][1])
        for job in self.p['jobs']: admission.accept(job,dict(accepted=True,job=job))
        with self.assertRaisesRegex(RuntimeError,'exhausted'): admission.before(self.p['jobs'][0])
        p=copy.deepcopy(self.p); p['jobs'][2]['mode']=1
        with self.assertRaisesRegex(RuntimeError,'Each seed'): r.Admission(p,lambda a,b:None)

    def test_rejected_metrics_latches_gate(self):
        a=r.Admission(self.p,lambda x,y:None); job=self.p['jobs'][0]
        with self.assertRaises(RuntimeError): a.accept(job,dict(accepted=False,job=job))
        with self.assertRaises(RuntimeError): a.before(job)

    def test_prior_failed_or_duplicate_gate_cannot_reset_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'A/batch01/ledger.json'; path.parent.mkdir(parents=True)
            r.save(path,dict(gate='A',attempts=[{}],success=False,parameter_restore_exact=True))
            with self.assertRaisesRegex(RuntimeError,'failed/incomplete'): r.verify_prior_budget(tmp,'B')
            with self.assertRaisesRegex(RuntimeError,'already has attempts'): r.verify_prior_budget(tmp,'A')
            r.save(path,dict(gate='A',attempts=[{}]*28,success=True,parameter_restore_exact=True))
            with self.assertRaisesRegex(RuntimeError,'36-attempt'): r.verify_prior_budget(tmp,'B')

    def metadata(self,mode=3):
        axes=1 if mode else 0
        return dict(requested_mode=mode,effective_mode=mode,requested_axes=axes,effective_axes=axes,
            pending=0,reject=0,div_req=1,div_eff=1,div_pending=0,div_reject=0,control_fault=0,
            variant_req=mode,variant_eff=mode,sta_pending=0,sta_gen=1,sta_reject=0)

    def test_selection_all_modes_and_missing_metadata_fail_closed(self):
        check=r.Checks.__new__(r.Checks)
        for mode in (0,1,3):
            check.job=dict(mode=mode,axes=1 if mode else 0); data=self.metadata(mode)
            check.selection(data)
            for field in ('variant_eff','sta_pending','sta_reject','sta_gen'):
                bad=data.copy(); del bad[field]
                with self.assertRaises(RuntimeError): check.selection(bad)
        check.job=dict(mode=3,axes=1)
        for key,value in (('effective_mode',1),('effective_axes',3),('pending',1),('sta_gen',True),('sta_gen',-.1),('sta_gen',0),('div_eff',2),('sta_reject',1)):
            bad=self.metadata(); bad[key]=value
            with self.assertRaises(RuntimeError): check.selection(bad)

    def test_full_epsilon_metadata_and_inner_pid_are_verified(self):
        check=r.Checks.__new__(r.Checks); check.job=dict(mode=3,axes=1)
        check.expected=dict(MPC_VC_EPS_X=.01,MPC_VC_EPS_Y=.01,MPC_VC_EPS_Z=.02)
        inner=dict(requested_mode=0,requested_axes=0,effective_mode=0,effective_axes=0,
            div_req=1,div_eff=1,fault=0,abort_requested=0,termination=0)
        def raw(req='0.01, 0.01, 0.02',eff='0.01, nan, nan'):
            return '\n'.join(f'    {k}: {v}' for k,v in self.metadata().items())+f'\n    eps_req: [{req}]\n    eps_eff: [{eff}]\n'
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)
            check.configuration(lambda *a:raw(),lambda *a:inner,output,'preflight')
            with self.assertRaisesRegex(RuntimeError,'selection metadata'):
                check.configuration(lambda *a:raw().replace('    div_req: 1\n',''),lambda *a:inner,output,'preflight')
            for req,eff in (('.01,.01','.01,nan,nan'),('.01,.01,.02','.02,nan,nan'),('.01,.01,.02','.01,.01,nan')):
                with self.assertRaises(RuntimeError): check.configuration(lambda *a:raw(req,eff),lambda *a:inner,output,'preflight')
            inner['effective_mode']=1
            with self.assertRaises(RuntimeError): check.configuration(lambda *a:raw(),lambda *a:inner,output,'preflight')


if __name__=='__main__': unittest.main(verbosity=2)
