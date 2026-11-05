#!/usr/bin/env python3
"""Offline R03 revision11 runner tests: fake processes, real BSON/ledger/restore logic."""
import ast
from contextlib import ExitStack, redirect_stdout
import copy
import fcntl
import importlib.util
import io
import json
import sys
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('r03_revision11_runner_under_test', HERE/'runner.py')
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)


class Fixture:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='r03-revision11-runner-offline-')
        self.root = Path(self.tmp.name)
        self.repo = self.root/'repo'; self.bin = self.repo/'build/px4_sitl_default/bin'
        self.rootfs = self.repo/'build/px4_sitl_default/tmp/rootfs'
        self.bin.mkdir(parents=True); (self.bin/'px4').write_bytes(b'offline fixture binary')
        (self.rootfs/'eeprom').mkdir(parents=True)
        version = self.repo/'build/px4_sitl_default/src/lib/version/build_git_version.h'
        version.parent.mkdir(parents=True); self.head = 'a'*40; version.write_text(self.head)
        self.p = copy.deepcopy(r.local_module('protocol').load_protocol('D'))
        self.output = self.root/'external/R03_revision11/D/batch01'
        self.p['artifacts']['new_run_root'] = str(self.output)
        config = self.root/'config'; config.mkdir(); self.p['config_dir'] = str(config)
        plugins = self.root/'plugins'; plugins.mkdir(); r.save(plugins/'manifest.json', {})
        self.p['plugins'] = str(plugins)
        self.execution = self.root/'execution.json'; r.save(self.execution, self.p['jobs'])
        self.p['execution_path'] = str(self.execution)
        self.qpath = self.root/'external/R03_revision11/D/qualification01/evidence.json'
        self.qpath.parent.mkdir(parents=True); self.p['qualification_path'] = str(self.qpath)
        self.q = dict(success=True, gate='D', source_head=self.head, firmware_sha256=r.digest(self.bin/'px4'))
        r.save(self.qpath, self.q)
        r.save(self.qpath.parent/'authorization.json', dict(approved=True, stage='R03-revision11-D', gate='D', revision='r03_revision11',
            source_head=self.head, maximum_attempts=9, total_maximum_attempts=97,
            new_matrix_attempts=9,historical_attempts=88,
            qualification_sha256=r.digest(self.qpath)))
        controls = {**self.p['jobs'][0]['parameters'], 'MPC_VCT_TEST': 0}
        defaults = {**self.p['startup_overrides'], **controls, 'SDLOG_PROFILE': 1041, 'SYS_AUTOSTART': 10016}
        self.types = {k: 'Int32' if isinstance(v, int) else 'Float' for k,v in defaults.items()}
        # An unrelated persistent value must survive every complete backup/restore.
        defaults['USER_FIXTURE'] = 17; self.types['USER_FIXTURE'] = 'Int32'
        definitions = [dict(name=k, default=v, type=self.types[k]) for k,v in defaults.items()]
        r.save(self.repo/'build/px4_sitl_default/parameters.json', dict(parameters=definitions))
        self.original = r.historical.encode_bson(defaults, self.types)
        self.param = self.rootfs/'eeprom/parameters_10016'; self.param.write_bytes(self.original)
        r.save(config/'frozen.json', dict(assets={}, external_assets={}, control_parameters=controls))
        self.old_root = self.root/'external/R03'
        self.old_ledger = self.old_root/'A/batch01/ledger.json'
        self.old_ledger.parent.mkdir(parents=True)
        r.save(self.old_ledger,dict(stage='R03-A',gate='A',attempts=[dict(status='failed')],success=False))
        self.old_journal = self.old_ledger.parent/'journal.jsonl'
        self.old_journal.write_text('{"event":"failed","job_id":"run010"}\\n')
        first = dict(root=str(self.old_root),ledger_path=str(self.old_ledger),
            ledger_sha256=r.digest(self.old_ledger),journal_path=str(self.old_journal),
            journal_sha256=r.digest(self.old_journal),attempts=1,accepted=0,failed=1,takeoffs=1,
            source_head='f'*40,run_id='run010',seed=71001)
        second_root = self.root/'external/R03_revision01'
        second = second_root/'A/batch01';second.mkdir(parents=True)
        r.save(second/'ledger.json',dict(success=False,attempts=[dict(status='accepted')]*6+[dict(status='failed')]))
        (second/'journal.jsonl').write_text('{"event":"failed","job_id":"run007"}\n')
        third_root = self.root/'external/R03_revision03'
        third = third_root/'A/batch01';third.mkdir(parents=True)
        r.save(third/'ledger.json',dict(success=False,attempts=[dict(status='accepted')]*6+[dict(status='failed')]))
        (third/'journal.jsonl').write_text('{"event":"failed","job_id":"run007","takeoff":false}\n')
        self.retained = dict(attempts=88,accepted=78,failed=8,takeoffs=86,diagnostic_complete=2,accepted_for_new_matrix=0,batches=[first,
            dict(root=str(second_root),ledger_path=str(second/'ledger.json'),ledger_sha256=r.digest(second/'ledger.json'),
                 journal_path=str(second/'journal.jsonl'),journal_sha256=r.digest(second/'journal.jsonl'),
                 attempts=7,accepted=6,failed=1,takeoffs=7,source_head='e'*40),
            dict(root=str(third_root),ledger_path=str(third/'ledger.json'),ledger_sha256=r.digest(third/'ledger.json'),
                 journal_path=str(third/'journal.jsonl'),journal_sha256=r.digest(third/'journal.jsonl'),
                 attempts=7,accepted=6,failed=1,takeoffs=6,source_head='d'*40)])
        # Both revision04 gates share the same process-lock root.
        fourth_root = self.root/'external/R03_revision04'
        for gate, accepted, failed in [('A',9,0),('B',5,1)]:
            directory=fourth_root/gate/'batch01';directory.mkdir(parents=True)
            r.save(directory/'ledger.json',dict(success=not failed,
                attempts=[dict(status='accepted')]*accepted+[dict(status='failed')]*failed))
            (directory/'journal.jsonl').write_text('synthetic historical '+gate+'\n')
            self.retained['batches'].append(dict(root=str(fourth_root),ledger_path=str(directory/'ledger.json'),
                ledger_sha256=r.digest(directory/'ledger.json'),journal_path=str(directory/'journal.jsonl'),
                journal_sha256=r.digest(directory/'journal.jsonl'),attempts=accepted+failed,
                accepted=accepted,failed=failed,takeoffs=accepted+failed,source_head='c'*40))
        self.a_path=fourth_root/'A/gate_pass.json';r.save(self.a_path,dict(gate='A',revision='r03_revision04',accepted=9))
        self.retained_abc=dict(gates=[dict(gate='A',revision='r03_revision04',receipt_sha256=r.digest(self.a_path),
            files={str(self.a_path):r.digest(self.a_path)},accepted_for_new_matrix=0)],
            files={str(self.a_path):r.digest(self.a_path)},accepted_design_runs=27,new_attempts=0)
        fifth_root=self.root/'external/R03_revision05'
        for gate,accepted,failed in [('B',9,0),('C',9,0),('D',0,1)]:
            directory=fifth_root/gate/'batch01';directory.mkdir(parents=True)
            r.save(directory/'ledger.json',dict(success=not failed,
                attempts=[dict(status='accepted')]*accepted+[dict(status='failed')]*failed))
            (directory/'journal.jsonl').write_text('synthetic historical '+gate+'\n')
            self.retained['batches'].append(dict(root=str(fifth_root),ledger_path=str(directory/'ledger.json'),
                ledger_sha256=r.digest(directory/'ledger.json'),journal_path=str(directory/'journal.jsonl'),
                journal_sha256=r.digest(directory/'journal.jsonl'),attempts=accepted+failed,
                accepted=accepted,failed=failed,takeoffs=accepted+failed,source_head='b'*40))
            if not failed:
                proof=fifth_root/gate/'gate_pass.json';r.save(proof,dict(gate=gate,revision='r03_revision05',accepted=9))
                self.retained_abc['gates'].append(dict(gate=gate,revision='r03_revision05',receipt_sha256=r.digest(proof),
                    files={str(proof):r.digest(proof)},accepted_for_new_matrix=0))
                self.retained_abc['files'][str(proof)]=r.digest(proof)
        self.p['retained_abc']=copy.deepcopy(self.retained_abc)
        self.p['historical_budget']=copy.deepcopy(self.retained)
        self.api = SimpleNamespace(GATES=dict.fromkeys('D'),retained_failure=Mock(side_effect=self.verify_history),
            retained_abc=Mock(side_effect=self.verify_a), exact=lambda a,b:json.dumps(a,sort_keys=True)==json.dumps(b,sort_keys=True),
            require_previous_gates=Mock(return_value=[dict(gate=g,revision=v) for g,v in
                [('A','r03_revision04'),('B','r03_revision05'),('C','r03_revision05')]]),
            require_execution_authority=Mock(),  # Mock qualification/flight I/O; never starts a simulator.
            require_qualification=Mock(return_value=self.q),
            fresh_seeds=Mock(return_value=dict(accepted=True, matches=[])),
            load_protocol=Mock(return_value=copy.deepcopy(self.p)))
        self.calls = []; self.analyzed = []; self.fail_flight = None; self.fail_analysis = None

    def verify_a(self):
        if any(r.digest(Path(path)) != sha for path,sha in self.retained_abc['files'].items()):
            raise RuntimeError('Retained A/B/C proof changed')
        return copy.deepcopy(self.retained_abc)

    def verify_history(self):
        if list(self.old_root.glob('*/batch*/ledger.json')) != [self.old_ledger]:
            raise RuntimeError('Historical additional batch')
        for old in self.retained['batches']:
            if r.digest(Path(old['ledger_path']))!=old['ledger_sha256'] or r.digest(Path(old['journal_path']))!=old['journal_sha256']:
                raise RuntimeError('Historical ledger/journal changed')
        return copy.deepcopy(self.retained)

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
            (r,'execution_checks_class',Mock(return_value=r.Checks)),
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


def prepared_class(cls):
    matches=[base for base in cls.__mro__ if 'start_heading' in base.__dict__
        and 'OwnedWarmReader' in base.__dict__['start_heading'].__globals__]
    if len(matches)!=1:raise AssertionError('Expected one original prearm wrapper')
    return matches[0]


class SourceContract(unittest.TestCase):
    def test_actual_factory_cannot_start_before_relative_warmup(self):
        cls=r.execution_checks_class();check=cls.__new__(cls)
        reader=SimpleNamespace(path=Path('/owned/new.ulg'),last_timing={'completed':True})
        state=dict(reader=reader,failed=False,warmup_reads=1)
        with tempfile.TemporaryDirectory() as tmp,patch.object(cls,'_prearm_state',return_value=state), \
                patch.object(prepared_class(cls),'start_heading',return_value={'reference':'original'}) as original:
            with self.assertRaises(ValueError):check.start_heading(None,tmp)
            self.assertFalse(check.warmup_ready({'position':{'timestamp':38524000}},tmp))
            with self.assertRaises(ValueError):check.start_heading(None,tmp)
            self.assertFalse(check.warmup_ready({'position':{'timestamp':68523999}},tmp))
            with self.assertRaises(ValueError):check.start_heading(None,tmp)
            original.assert_not_called()
            self.assertTrue(check.warmup_ready({'position':{'timestamp':68524000}},tmp))
            self.assertEqual(check.start_heading(None,tmp),{'reference':'original'})
            original.assert_called_once_with(None,tmp)

    def test_actual_factory_never_swallows_original_boundary_failure(self):
        cls=r.execution_checks_class();check=cls.__new__(cls)
        state=dict(reader=SimpleNamespace(path=Path('/owned'),last_timing={'completed':True}),failed=False,warmup_reads=1)
        with tempfile.TemporaryDirectory() as tmp,patch.object(cls,'_prearm_state',return_value=state), \
                patch.object(prepared_class(cls),'start_heading',side_effect=ValueError('Missing attitude boundary predecessor')) as old:
            check.warmup_ready({'position':{'timestamp':1}},tmp)
            check.warmup_ready({'position':{'timestamp':30000001}},tmp)
            with self.assertRaisesRegex(ValueError,'boundary predecessor'):check.start_heading(None,tmp)
            old.assert_called_once_with(None,tmp)

    def test_actual_factory_previous_failure_never_reaches_prearm(self):
        cls=r.execution_checks_class();check=cls.__new__(cls)
        with tempfile.TemporaryDirectory() as tmp,patch.object(cls,'_prearm_state',return_value=dict(reader=None,failed=True,warmup_reads=0)), \
                patch.object(prepared_class(cls),'start_heading') as old:
            with self.assertRaises(ValueError):check.warmup_ready({'position':{'timestamp':40000000}},tmp)
            with self.assertRaises(ValueError):check.start_heading(None,tmp)
            old.assert_not_called()

    def test_revoked_authority_refuses_execute_and_private_entry_before_any_mutation(self):
        api=r.local_module('protocol');p = api.load_protocol('D')
        with patch.object(r,'save') as save,patch.object(r.fcntl,'flock') as lock, \
             patch.object(r,'active_simulators') as processes, \
             patch.object(api,'require_execution_authority',side_effect=PermissionError('not authorized')):
            for entry in (r.execute_gate,r._execute_gate):
                with self.subTest(entry=entry.__name__),self.assertRaisesRegex(PermissionError,'not authorized'):
                    entry(p,'a'*40,Path(p['qualification_path']))
            save.assert_not_called();lock.assert_not_called();processes.assert_not_called()

    def test_counterfeit_checks_do_not_bypass_real_execution_authority(self):
        checks=SimpleNamespace(job={'gate':'A'},execution_permitted=True,require_execution=Mock())
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'must-not-exist'
            with patch.object(r.local_module('protocol'),'require_execution_authority',side_effect=PermissionError('revoked')):
                with self.assertRaises(PermissionError):r.flight_main(dest,checks,None)
            self.assertFalse(dest.exists());checks.require_execution.assert_not_called()

    def test_old_offline_revision_remains_hard_closed(self):
        spec=importlib.util.spec_from_file_location('immutable_offline_revision02',HERE.parent/'r03_revision02/protocol.py')
        old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        for gate in 'BCD':
            with self.subTest(gate=gate),self.assertRaises(PermissionError):old.require_execution_authority(gate)

    def test_authorized_manifest_does_not_replace_clean_qualification(self):
        api=r.local_module('protocol');p=api.load_protocol('D')
        with patch.object(api,'require_qualification',side_effect=ValueError('missing clean qualification')), \
             patch.object(r.fcntl,'flock') as lock,patch.object(r,'active_simulators') as processes:
            with self.assertRaisesRegex(ValueError,'missing clean qualification'):
                r.execute_gate(p,'a'*40,Path(p['qualification_path']))
            lock.assert_not_called();processes.assert_not_called()

    def test_opt_in_monitor_factory_is_private_and_preserves_old_reader_globals(self):
        old = r.historical.Checks.start_heading
        before = dict(old.__globals__)
        first,second = r.execution_checks_class(),r.execution_checks_class()
        self.assertIsNot(first,second);self.assertTrue(issubclass(first,r.Checks))
        self.assertIs(r.historical.Checks.start_heading,old)
        self.assertEqual(old.__globals__,before)
        self.assertIsNot(prepared_class(first).start_heading.__globals__,old.__globals__)
        self.assertEqual(prepared_class(first).start_heading.__globals__['OwnedWarmReader'].__module__,
                         '_r03_revision11_monitor_integration')
        self.assertEqual(Path(prepared_class(first).start_heading.__globals__['__file__']).resolve(),
                         (HERE.parent/'r03_prearm04/integration.py').resolve())
        self.assertIs(first.require_execution,r.Checks.require_execution)
        self.assertIs(first.prepare_environment,r.Checks.prepare_environment)
        self.assertNotIn('PositionLiveLog',prepared_class(first).start_heading.__globals__)

    def test_execution_factory_retains_warm_reader_and_prearm_failure_receipt(self):
        spec=importlib.util.spec_from_file_location('revision11_frozen_monitor_fixtures',
            HERE.parent/'r03_monitor02/test_integration.py')
        fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
        tables,_=fixture.heading_tables();header,packets=fixture.encode(tables)
        raw=header+b''.join(p[3] for p in packets)
        for age,accepted in ((499999,True),(500000,True),(500001,False),(-1,False)):
            with self.subTest(age=age),tempfile.TemporaryDirectory(prefix='revision11-prearm-wiring-') as tmp:
                output=Path(tmp);root=output/'owned';path=root/'sess001/log001.ulg'
                path.parent.mkdir(parents=True);path.write_bytes(raw)
                cls=r.execution_checks_class();check=cls.__new__(cls)
                check.log_root=root;check.logs_before=set();check.reference=None
                with patch.object(cls,'_position11_ax04_monitor',autospec=True):
                    check.monitor('warmup',None,lambda _: {},output,{})
                # Component age-bound fixture; separate tests exercise actual 30s readiness.
                check._warmup10=SimpleNamespace(ready=True,failed=False)
                reader=check._prearm04['reader']
                self.assertEqual(reader.last_size,len(raw))
                def topic(name):
                    return {'arming_state':1,'timestamp':3990000+age}
                if accepted:
                    check.start_heading(topic,output)
                    self.assertIs(check.live,reader);self.assertIs(check.landing_live,reader)
                else:
                    with self.assertRaisesRegex(RuntimeError,'Stale prearm ULog'):
                        check.start_heading(topic,output)
                receipts=[json.loads(line) for line in (output/'r03_prearm04_timing.jsonl').read_text().splitlines()]
                self.assertEqual([x['phase'] for x in receipts],['warmup','prearm'])
                self.assertEqual(receipts[-1]['raw_reader']['new_bytes'],0)
                self.assertEqual(receipts[-1]['reference_timestamp_us'],3990000)
                self.assertEqual(receipts[-1]['actual_cli'][-1]['timestamp_us'],3990000+age)
                self.assertEqual(receipts[-1]['failure_latched'],not accepted)
                self.assertFalse(receipts[-1]['execution_authority_granted'])

    def test_private_load_ignores_generic_names_and_rejects_cache_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            here=Path(tmp);(here/'protocol.py').write_text('marker = "private protocol"\n')
            (here/'analyzer.py').write_text('marker = "private analyzer"\n')
            with patch.object(r,'HERE',here),patch.dict(sys.modules):
                for name in ('protocol','analyzer'):
                    sys.modules[name]=SimpleNamespace(marker='foreign generic')
                    sys.modules.pop('_r03_revision11_'+name,None)
                    module=r.local_module(name)
                    self.assertEqual(module.marker,'private '+name)
                    self.assertEqual(sys.modules[name].marker,'foreign generic')
                    self.assertEqual(Path(module.__file__),here/(name+'.py'))
                    self.assertIs(r.local_module(name),module)
                sys.modules['_r03_revision11_protocol']=SimpleNamespace(__file__='/foreign/protocol.py')
                with self.assertRaisesRegex(RuntimeError,'path collision'):r.local_module('protocol')

    def test_private_import_failure_removes_partial_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            here=Path(tmp);(here/'protocol.py').write_text('raise RuntimeError("incomplete dependency")\n')
            with patch.object(r,'HERE',here),patch.dict(sys.modules):
                sys.modules.pop('_r03_revision11_protocol',None)
                with self.assertRaisesRegex(RuntimeError,'incomplete dependency'):r.local_module('protocol')
                self.assertNotIn('_r03_revision11_protocol',sys.modules)
                with self.assertRaisesRegex(ValueError,'Unknown'):r.local_module('task')

    def test_owned_startup_flight_landing_archive_body_unchanged(self):
        old = (r.REPO/'research/sta-velocity-control/v08/protocol02/flight.py').read_text()
        new = (HERE/'runner.py').read_text()
        marker = '    # Opt-in M10 only; prior milestones retain exactly the original timing.'
        old_body = old[old.index(marker):old.index('\n\nif __name__')].strip()
        new_body = new[new.index(marker):new.index('\n\nclass Checks')].strip()
        new_body=new_body.replace('            log_ready = checks.warmup_ready(state, output)\n','').replace(' and telemetry and log_ready:', ' and telemetry:')
        self.assertEqual(old_body,new_body)
        self.assertEqual(r.digest(r.REPO/'research/sta-velocity-control/v08/protocol02/flight.py'),
            'ed6901ce8203821943241bf4108f6b6a6d1768b80b2c6a4e65f687a6d1ed9cfb')
        for name in ('active_simulators','shutdown_owned'):
            a = next(n for n in ast.parse(old).body if isinstance(n,ast.FunctionDef) and n.name==name)
            b = next(n for n in ast.parse(new).body if isinstance(n,ast.FunctionDef) and n.name==name)
            self.assertEqual(ast.dump(a),ast.dump(b))

    def test_default_dry_run_and_missing_sha_never_execute(self):
        p = r.local_module('protocol').load_protocol('D')
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
            p=dict(gate='D',retained_abc={},historical_budget=dict(attempts=88,accepted=78,failed=8,takeoffs=86,diagnostic_complete=2,accepted_for_new_matrix=0),
                artifacts=dict(new_run_root=str(Path(tmp)/'R03_revision11/B/batch01')))
            api=SimpleNamespace(require_execution_authority=Mock(),retained_failure=Mock(return_value=p['historical_budget']),require_qualification=Mock(side_effect=ValueError('not qualified')),
                retained_abc=lambda:{},exact=lambda a,b: a==b,load_protocol=Mock(return_value=copy.deepcopy(p)))
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
        self.assertEqual(result['total_budget'],97);self.assertEqual(result['prior_attempts'],88)
        self.assertEqual(result['retained_invalid_attempts'],8);self.assertEqual(result['new_planned'],9)
        self.assertEqual(result['retained_accepted_attempts'],78);self.assertEqual(result['retained_attempts'],88)
        self.assertEqual(result['historical_budget'],self.f.retained)
        self.assertEqual(r.digest(self.f.old_ledger),self.f.retained['batches'][0]['ledger_sha256'])
        self.assertEqual(r.digest(self.f.old_journal),self.f.retained['batches'][0]['journal_sha256'])
        self.assertEqual(len(self.f.calls),9); self.assertEqual(len(self.f.analyzed),9)
        self.assertEqual(self.f.param.read_bytes(),self.f.original)
        self.assertEqual((self.f.output/'original_parameters.bson').read_bytes(),self.f.original)
        self.f.api.fresh_seeds.assert_called_once_with('D')
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
        record=json.loads((self.f.output/(self.f.p['jobs'][1]['id']+'_paired_checks_at_stop.json')).read_text())
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

    def test_history_is_fingerprinted_before_qualification_or_locks(self):
        self.f.old_ledger.write_text('{}')
        with self.assertRaisesRegex(RuntimeError,'Historical'):self.f.execute()
        self.f.api.require_qualification.assert_not_called()
        self.assertEqual(self.f.calls,[]);self.assertEqual(self.f.param.read_bytes(),self.f.original)
        self.assertFalse((self.f.output.parent.parent/'.runner.lock').exists())

    def test_latest_retained_revision03_failure_is_not_omitted(self):
        third=self.f.retained['batches'][2]
        Path(third['journal_path']).write_text('changed revision03 prearm failure')
        with self.assertRaisesRegex(RuntimeError,'Historical'):self.f.execute()
        self.f.api.require_qualification.assert_not_called()
        self.assertEqual(self.f.calls,[])
        self.assertEqual(self.f.param.read_bytes(),self.f.original)
        self.assertFalse((self.f.output.parent.parent/'.runner.lock').exists())

    def test_revision04_b_failure_is_bound_before_mutation(self):
        Path(self.f.retained['batches'][4]['ledger_path']).write_text('changed old B failure')
        with self.assertRaisesRegex(RuntimeError,'Historical'):self.f.execute()
        self.f.api.require_qualification.assert_not_called()
        self.assertFalse(self.f.output.exists());self.assertEqual(self.f.calls,[])

    def test_retained_abc_proof_is_not_replaced_by_history_counts(self):
        self.f.a_path.write_text('{}')
        with self.assertRaisesRegex(RuntimeError,'Retained A'):self.f.execute()
        self.assertFalse(self.f.output.exists());self.assertEqual(self.f.calls,[])
        self.assertEqual(self.f.param.read_bytes(),self.f.original)

    def test_previous_raw_gate_rejection_precedes_batch_and_parameters(self):
        self.f.api.require_previous_gates.side_effect=ValueError('retained A raw evidence failed')
        with self.assertRaisesRegex(ValueError,'raw evidence'):self.f.execute()
        self.assertFalse(self.f.output.exists());self.assertEqual(self.f.calls,[])
        self.assertEqual(self.f.param.read_bytes(),self.f.original)

    def test_revision04_shared_lock_is_acquired_once_but_still_excludes_foreign_owner(self):
        roots=[b['root'] for b in self.f.retained['batches']]
        self.assertEqual(roots[3],roots[4])
        lockpath=Path(roots[3])/'.runner.lock'
        with lockpath.open('a') as lock:
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError,'runner lock'):self.f.execute()
        # Nine-run success elsewhere exercises no self-conflict on this root.
        self.assertFalse(self.f.output.exists());self.assertEqual(self.f.calls,[])

    def test_new_historical_attempt_is_not_hidden_by_new_revision(self):
        path=self.f.old_root/'D/batch01/ledger.json';path.parent.mkdir(parents=True)
        r.save(path,dict(attempts=[{}]))
        with self.assertRaisesRegex(RuntimeError,'additional batch'):self.f.execute()
        self.f.api.require_qualification.assert_not_called()
        self.assertEqual(self.f.calls,[])

    def test_history_change_between_rounds_stops_without_second_attempt(self):
        flight=self.f.flight
        def changing(*args):
            flight(*args)
            self.f.old_journal.write_text('changed history')
        self.f.flight=changing
        with self.assertRaisesRegex(RuntimeError,'Historical'):self.f.execute()
        ledger=json.loads((self.f.output/'ledger.json').read_text())
        self.assertEqual(len(ledger['attempts']),1);self.assertFalse(ledger['success'])
        self.assertTrue(ledger['parameter_restore_exact'])

    def test_historical_lock_blocks_new_revision(self):
        lockpath=self.f.old_root/'.runner.lock'
        with lockpath.open('a') as lock:
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError,'runner lock'):self.f.execute()
        self.assertFalse(self.f.output.exists());self.assertEqual(self.f.calls,[])

    def test_latest_retained_revision03_lock_blocks_new_revision(self):
        lockpath=Path(self.f.retained['batches'][2]['root'])/'.runner.lock'
        with lockpath.open('a') as lock:
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError,'runner lock'):self.f.execute()
        self.assertFalse(self.f.output.exists());self.assertEqual(self.f.calls,[])

    def test_prearm_rejection_consumes_attempt_without_rearming_or_retry(self):
        flight=self.f.flight
        def fail(*args):
            flight(*args)
            raise RuntimeError('Stale prearm ULog')
        self.f.flight=fail
        with self.assertRaisesRegex(RuntimeError,'Stale prearm ULog'):self.f.execute()
        self.assert_stop(1)
        self.assertEqual(len(self.f.calls),1)
        self.assertEqual(self.f.analyzed,[])
        receipt=json.loads((self.f.output/self.f.p['jobs'][0]['id']/'parameter_restore.json').read_text())
        self.assertTrue(receipt['parameter_restore_exact'])

    def test_unknown_empty_new_batch_cannot_be_ignored(self):
        (self.f.output.parent.parent/'A/batch02').mkdir(parents=True)
        with self.assertRaisesRegex(RuntimeError,'replacement'):self.f.execute()
        self.assertEqual(self.f.calls,[]);self.assertEqual(self.f.param.read_bytes(),self.f.original)


class BudgetAndSelection(unittest.TestCase):
    def setUp(self): self.p=copy.deepcopy(r.local_module('protocol').load_protocol('D'))

    def test_missing_or_changed_budget_rejected(self):
        for value in (None,35,36,44,51.0,True):
            p=copy.deepcopy(self.p)
            if value is None: del p['total_maximum_attempts']
            else: p['total_maximum_attempts']=value
            with self.assertRaises(RuntimeError): r.Admission(p,lambda a,b:dict(accepted=True))

    def test_invalid_order_pairing_and_exhausted_state(self):
        admission=r.Admission(self.p,lambda a,b:dict(accepted=True))
        with self.assertRaisesRegex(RuntimeError,'order'): admission.before(self.p['jobs'][1])
        for job in self.p['jobs']: admission.accept(job,dict(accepted=True,job=job))
        with self.assertRaisesRegex(RuntimeError,'exhausted'): admission.before(self.p['jobs'][0])
        p=copy.deepcopy(self.p); p['jobs'][2]['mode']=p['jobs'][1]['mode']
        with self.assertRaisesRegex(RuntimeError,'Each seed'): r.Admission(p,lambda a,b:None)

    def test_rejected_metrics_latches_gate(self):
        a=r.Admission(self.p,lambda x,y:None); job=self.p['jobs'][0]
        with self.assertRaises(RuntimeError): a.accept(job,dict(accepted=False,job=job))
        with self.assertRaises(RuntimeError): a.before(job)

    def test_prior_gate_count_includes_all_forty_nine_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);history=dict(attempts=88,accepted=78,failed=8,takeoffs=86,diagnostic_complete=2,accepted_for_new_matrix=0)
            api=SimpleNamespace(GATES=dict.fromkeys('D'),retained_failure=lambda:history,retained_abc=lambda:{},exact=lambda a,b:a==b,
                require_previous_gates=Mock())
            p=dict(historical_budget=history,retained_abc={},seed_migration={},
                historical_attempts=88,maximum_attempts=9,new_matrix_attempts=9,total_maximum_attempts=97)
            self.assertEqual(r.verify_prior_budget(root,'D',api,p),88)
            api.require_previous_gates.assert_called_once_with('D')
            for gate in ('','E','AB'):
                with self.assertRaisesRegex(RuntimeError,'Unknown budget'):
                    r.verify_prior_budget(root,gate,api,p)

    def test_existing_failed_partial_empty_or_foreign_batch_rejected(self):
        for scenario in ('failed','accepted','empty','foreign'):
            with self.subTest(scenario=scenario),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);history=dict(attempts=88,accepted=78,failed=8,takeoffs=86,diagnostic_complete=2,accepted_for_new_matrix=0)
                api=SimpleNamespace(GATES=dict.fromkeys('D'),retained_failure=lambda:history,retained_abc=lambda:{},exact=lambda a,b:a==b,
                    require_previous_gates=Mock())
                p=dict(historical_budget=history,retained_abc={},seed_migration={},
                    historical_attempts=88,maximum_attempts=9,total_maximum_attempts=97)
                directory=root/('B' if scenario=='foreign' else 'D')/'batch01';directory.mkdir(parents=True)
                if scenario!='empty':r.save(directory/'ledger.json',dict(success=scenario=='accepted'))
                with self.assertRaisesRegex(RuntimeError,'replacement'):
                    r.verify_prior_budget(root,'D',api,p)

    def test_missing_retained_gate_proof_stops_before_new_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            history=dict(attempts=88,accepted=78,failed=8,takeoffs=86,diagnostic_complete=2,accepted_for_new_matrix=0)
            api=SimpleNamespace(retained_failure=lambda:history,retained_abc=lambda:{},exact=lambda a,b:a==b,
                require_previous_gates=Mock(side_effect=ValueError('retained C replay missing')))
            p=dict(historical_budget=history,retained_abc={})
            with self.assertRaisesRegex(ValueError,'retained C'):
                r.verify_prior_budget(Path(tmp),'D',api,p)

    def test_retained_binding_and_boolean_count_cannot_be_rewritten(self):
        for actual in (dict(attempts=2,accepted=0),dict(attempts=1,accepted=1),
                       dict(attempts=True,accepted=0),dict(attempts=1,accepted=False)):
            p=dict(historical_budget=actual)
            with self.subTest(actual=actual),self.assertRaises(RuntimeError):
                r.retained_budget(p,SimpleNamespace(retained_failure=lambda:actual))
        with self.assertRaisesRegex(RuntimeError,'binding'):
            r.retained_budget(dict(historical_budget=dict(attempts=1,accepted=0)),
                SimpleNamespace(retained_failure=lambda:dict(attempts=1,accepted=0,changed=True)))

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
