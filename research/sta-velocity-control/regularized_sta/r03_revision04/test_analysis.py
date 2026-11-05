"""Prospective provenance/import regression; fixtures are not new flights."""
import copy
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import time
import unittest
from unittest.mock import patch

import numpy as np
_spec=importlib.util.spec_from_file_location('r03_revision04_test_analyzer',Path(__file__).with_name('analyzer.py'))
a=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(a)


def job(mode=0,gate='A'):
    task,axes,test,duration=a.targets.SPECS[gate]
    config=a._inherited.leaf('r02_config','research/sta-velocity-control/regularized_sta/r02/tools/config.py')
    value=config.candidate(mode,axes if mode else 0)
    value.update(revision=a.REVISION,id='run001',gate=gate,task=task,candidate={0:'PID',1:'ESTA',3:'RSTA'}[mode],
                 mode=mode,axes=axes if mode else 0,seed=999999,divisor=1,main_duration_s=duration)
    value['parameters']['MPC_VCT_TEST']=test
    return value


class Fixture:
    """Small fake evidence documents; no ULog decoding or flight claim."""
    def __init__(self,root):
        self.root=Path(root);self.job=job();self.run=self.root/'A/batch01/run001';self.run.mkdir(parents=True)
        config=self.root/'config';config.mkdir();(config/'frozen.json').write_text('{}')
        execution=self.root/'execution.json';execution.write_text('{}')
        self.qpath=self.root/'A/qualification01/evidence.json';self.qpath.parent.mkdir(parents=True)
        self.retained=dict(attempts=15,accepted=12,failed=3,accepted_for_new_matrix=0,batches=[])
        self.migration=copy.deepcopy(a._protocol().seed_migration())
        self.authority=a._protocol().AUTHORIZATION
        self.p=dict(revision=a.REVISION,stage='R03-revision04-A',gate='A',jobs=[self.job],
                    config_dir=str(config),execution_path=str(execution),qualification_path=str(self.qpath),
                    startup_overrides=copy.deepcopy(self.job['parameters']),
                    artifacts={'new_run_root':str(self.run.parent)},**a._budget())
        self.frozen=copy.deepcopy(self.p)
        self.protocol=types.SimpleNamespace(load_protocol=lambda gate:copy.deepcopy(self.frozen),
                                           require_execution_authority=lambda gate:None,  # Mock only; no real authority.
                                           retained_failure=lambda:copy.deepcopy(self.retained),
                                           seed_migration=lambda:copy.deepcopy(self.migration),AUTHORIZATION=self.authority)
        self.q=dict(success=True,clean=True,revision=a.REVISION,stage=self.p['stage'],gate='A',new_flights=0,
                    source_head='a'*40,firmware_sha256='b'*64,execution_sha256=a.digest(execution),
                    frozen_sha256=a.digest(config/'frozen.json'),historical_budget=copy.deepcopy(self.retained),
                    seed_migration=copy.deepcopy(self.migration),
                    execution_authorized=True,flight_authorized=True,execution_ready=True,**a._budget())
        self.record=dict(source_head=self.q['source_head'],binary_sha256=self.q['firmware_sha256'],
                         scenario_sha256=self.q['execution_sha256'],scenario_path=str(execution),
                         logs=[dict(archive=str(self.run/'fixture.ulg'))])
        (self.run/'fixture.ulg').write_bytes(b'not a real ULog; provenance fixture only')
        (self.run/'original_parameters.bson').write_bytes(b'fixture-bson')
        h=a.digest(self.run/'original_parameters.bson')
        self.restore=dict(parameter_restore_exact=True,remaining_simulators=[],stopped_before_restore=True,
                          source_head=self.q['source_head'],gate='A',job_id=self.job['id'],
                          original_parameter_sha256=h,restored_parameter_sha256=h)
        self.refresh()

    def write(self,name,value):
        (self.run/name).write_text(json.dumps(value))

    def refresh(self):
        self.qpath.write_text(json.dumps(self.q))
        self.approval=dict(approved=True,revision=a.REVISION,stage=self.p['stage'],gate='A',
            source_head=self.q['source_head'],firmware_sha256=self.q['firmware_sha256'],
            execution_sha256=self.q['execution_sha256'],frozen_sha256=self.q['frozen_sha256'],
            qualification_sha256=a.digest(self.qpath),historical_budget=copy.deepcopy(self.retained),
            seed_migration=copy.deepcopy(self.migration),authorization_sha256=a.digest(self.authority),
            execution_authorized=True,flight_authorized=True,execution_ready=True,**a._budget())
        self.write('authorization.json',self.approval)
        self.write('qualification_reference.json',{'path':str(self.qpath),'sha256':a.digest(self.qpath)})
        for name,value in (('result.json',self.record),('run_protocol.json',self.p),('job.json',self.job),
                           ('parameter_restore.json',self.restore)):
            self.write(name,value)


class ProspectiveBinding(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.f=Fixture(self.temp.name)
        self.mock=patch.object(a,'_protocol',return_value=self.f.protocol);self.mock.start();self.addCleanup(self.mock.stop)

    def check(self):return a.provenance(self.f.run,self.f.p,self.f.job)

    def test_valid_prospective_fixture_not_a_flight(self):
        result=self.check()
        self.assertEqual(result['revision'],a.REVISION)
        for key,value in a._budget().items():self.assertEqual(result[key],value)
        self.assertEqual(result['historical_budget'],self.f.retained)

    def test_migration_and_actual_execution_flags_cannot_be_forged(self):
        for target in ('q','approval'):
            for key,value in (('seed_migration',{}),('execution_authorized',False),
                              ('flight_authorized',1),('execution_ready',None)):
                before=copy.deepcopy(getattr(self.f,target))
                changed={**before,key:value}
                if target=='q':self.f.q=changed;self.f.refresh()
                else:self.f.write('authorization.json',changed)
                with self.subTest(target=target,key=key),self.assertRaises(ValueError):self.check()
                if target=='q':self.f.q=before
                self.f.refresh()

    def test_legacy_job_refused_before_output_write(self):
        before=a._repair.snapshot(self.f.run);self.f.job.pop('revision')
        with self.assertRaisesRegex(ValueError,'prospective'):a.analyze(self.f.run,self.f.p,self.f.job)
        self.assertEqual(before,a._repair.snapshot(self.f.run))

    def test_wrong_stage_revision_or_gate_refused(self):
        for field,value in (('stage','R03-A'),('revision','r03'),('gate','B')):
            with self.subTest(field=field),patch.dict(self.f.p,{field:value}):
                with self.assertRaises(ValueError):self.check()

    def test_budget_9_36_15_51_exact(self):
        for key in a._budget():
            with self.subTest(key=key),patch.dict(self.f.p,{key:self.f.p[key]+1}):
                with self.assertRaisesRegex(ValueError,'budget'):self.check()

    def test_budget_bool_not_integer(self):
        with patch.dict(self.f.p,{'historical_attempts':True}):
            with self.assertRaisesRegex(ValueError,'budget'):self.check()

    def test_parameter_overlay_numeric_aliases_are_not_equal(self):
        for value in (False,0.0):
            with self.subTest(value=value),patch.dict(self.f.p['startup_overrides'],{'MPC_VC_MODE':value}):
                with self.assertRaises(ValueError):self.check()

    def test_nested_retained_history_number_aliases_rejected(self):
        for target in ('q','approval'):
            value=copy.deepcopy(getattr(self.f,target))
            value['historical_budget']['accepted']=12.0
            if target=='q':
                self.f.q=value;self.f.refresh()
            else:
                self.f.write('authorization.json',value)
            with self.subTest(target=target),self.assertRaises(ValueError):self.check()
            self.f.q['historical_budget']=copy.deepcopy(self.f.retained);self.f.refresh()

    def test_legacy_qualification_refused(self):
        self.f.q.update(revision='r03',stage='R03-A');self.f.refresh()
        with self.assertRaisesRegex(ValueError,'qualification'):self.check()

    def test_qualification_counts_and_retained_failure_bound(self):
        for key in ('maximum_attempts','new_matrix_attempts','historical_attempts','total_maximum_attempts','historical_budget'):
            original=copy.deepcopy(self.f.q)
            self.f.q[key]=2 if key!='historical_budget' else {'status':'accepted'};self.f.refresh()
            with self.subTest(key=key),self.assertRaises(ValueError):self.check()
            self.f.q=original;self.f.refresh()

    def test_qualification_flags_strict(self):
        for key,value in (('success',False),('clean',False),('new_flights',1),('new_flights',False)):
            original=copy.deepcopy(self.f.q);self.f.q[key]=value;self.f.refresh()
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):self.check()
            self.f.q=original;self.f.refresh()

    def test_authorization_budget_and_retained_failure_bound(self):
        for key in ('revision','maximum_attempts','new_matrix_attempts','historical_attempts','total_maximum_attempts','historical_budget'):
            original=copy.deepcopy(self.f.approval)
            self.f.approval[key]='wrong';self.f.write('authorization.json',self.f.approval)
            with self.subTest(key=key),self.assertRaises(ValueError):self.check()
            self.f.approval=original;self.f.write('authorization.json',original)

    def test_no_parameter_restore_rejected(self):
        self.f.restore['parameter_restore_exact']=False;self.f.refresh()
        with self.assertRaisesRegex(ValueError,'restore'):self.check()

    def test_active_simulator_restore_rejected(self):
        self.f.restore['remaining_simulators']=['px4'];self.f.refresh()
        with self.assertRaisesRegex(ValueError,'restore'):self.check()

    def test_old_raw_archive_cannot_be_laundered(self):
        self.f.record['logs'][0]['archive']='/old/R03/A/batch01/run001/old.ulg';self.f.refresh()
        with self.assertRaisesRegex(ValueError,'prospective job'):self.check()

    def test_duplicate_or_missing_raw_archives_rejected(self):
        for logs in ([],[self.f.record['logs'][0]]*2):
            with self.subTest(logs=logs):
                self.f.record['logs']=logs;self.f.refresh()
                with self.assertRaises(ValueError):self.check()

    def test_source_scenario_or_firmware_mismatch(self):
        for key in ('source_head','binary_sha256','scenario_sha256','scenario_path'):
            original=self.f.record[key];self.f.record[key]='wrong';self.f.refresh()
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'provenance'):self.check()
            self.f.record[key]=original;self.f.refresh()

    def test_actual_saved_protocol_mismatch(self):
        self.f.write('run_protocol.json',{})
        with self.assertRaisesRegex(ValueError,'Saved actual protocol'):self.check()

    def test_qualification_sidecar_hash_mismatch(self):
        self.f.write('qualification_reference.json',{'path':str(self.f.qpath),'sha256':'0'*64})
        with self.assertRaisesRegex(ValueError,'sidecar'):self.check()

    def test_replay_permits_only_explicit_same_gate_qualification_path(self):
        new=self.f.root/'A/qualification02/evidence.json';new.parent.mkdir();new.write_bytes(self.f.qpath.read_bytes())
        self.f.p['qualification_path']=str(new);self.f.write('run_protocol.json',self.f.p)
        self.f.write('qualification_reference.json',{'path':str(new),'sha256':a.digest(new)})
        self.assertEqual(a.replay_protocol(self.f.run,self.f.job),self.f.p)

    def test_replay_qualification_outside_gate_rejected(self):
        self.f.p['qualification_path']=str(self.f.root/'B/qualification01/evidence.json')
        self.f.write('run_protocol.json',self.f.p)
        with self.assertRaisesRegex(ValueError,'outside'):a.replay_protocol(self.f.run,self.f.job)

    def test_other_frozen_protocol_change_rejected(self):
        self.f.p['undisclosed_relaxation']=True
        with self.assertRaisesRegex(ValueError,'frozen gate'):self.check()

    def test_wrong_runtime_parameter_overlay_rejected(self):
        self.f.p['startup_overrides']['MPC_VC_MODE']=3
        with self.assertRaisesRegex(ValueError,'overlay'):self.check()

    def test_replay_old_job_creates_no_output(self):
        self.f.job.pop('revision');self.f.write('job.json',self.f.job)
        dest=self.f.root/'forbidden-output'
        with self.assertRaises(ValueError):a.replay_new(self.f.run,dest)
        self.assertFalse(dest.exists())

    def test_new_fixture_dispatches_private_height_and_provenance(self):
        namespace={'height_evidence':None,'provenance':None}
        exec("def analyze(run,p,j):\n return {'accepted':height_evidence is not None, 'binding':provenance(run,p,j)}",namespace)
        original_globals=dict(namespace)
        with patch.object(a._inherited,'analyze',namespace['analyze']), patch.object(a,'prearm_evidence',return_value={'valid':True}):
            result=a.analyze(self.f.run,self.f.p,self.f.job)
        self.assertTrue(result['accepted']);self.assertEqual(result['binding']['revision'],a.REVISION)
        self.assertEqual(namespace,original_globals)


class ExplicitDependencies(unittest.TestCase):
    def test_revoked_authority_refuses_acceptance_even_with_fake_log_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture=Fixture(tmp)
            def revoked(gate):raise PermissionError('explicit authority revoked')
            fixture.protocol.require_execution_authority=revoked
            before=a._repair.snapshot(fixture.run)
            with patch.object(a,'_protocol',return_value=fixture.protocol):
                for entry in (a.provenance,a.analyze):
                    with self.subTest(entry=entry.__name__),self.assertRaises(PermissionError):
                        entry(fixture.run,fixture.p,fixture.job)
                with self.assertRaises(PermissionError):a.replay_new(fixture.run,Path(tmp)/'output')
            self.assertEqual(before,a._repair.snapshot(fixture.run))
            self.assertFalse((Path(tmp)/'output').exists())

    def test_three_dimensional_height_bound_to_fixed_path(self):
        self.assertEqual(a.HEIGHT_BINDING['offsets_source'],str(a._repair.TASK))
        value=a._height.__globals__['offsets'](8,np.array([7.,13.,23.,39.,55.]))
        self.assertEqual(value['p'].shape,(5,3));self.assertGreater(np.max(abs(value['p'][:,2])),.03)

    def test_fake_task_two_columns_and_raises_ignored(self):
        for raise_error in (False,True):
            fake=types.ModuleType('task')
            def offsets(mode,t):
                if raise_error:raise AssertionError('Polluted generic task called')
                return {'p':np.zeros((len(t),2))}
            fake.offsets=offsets
            with self.subTest(raise_error=raise_error),patch.dict(sys.modules,{'task':fake}):
                module=a.load_path('revision02_poison_test',a.HERE/'analyzer.py')
                self.assertEqual(module._height.__globals__['offsets'](1,np.array([1.]))['p'].shape,(1,3))
                self.assertIs(sys.modules['task'],fake)

    def test_targets_are_exact_old_implementation(self):
        self.assertEqual(Path(a.targets.__file__).resolve(),a.OLD/'targets.py')
        self.assertEqual(a.digest(a.OLD/'targets.py'),a._repair.PINS[a.OLD/'targets.py'])

    def test_all_new_modes_and_gates_validate_without_changing_math(self):
        for gate in 'ABCD':
            for mode in (0,1,3):
                j=job(mode,gate)
                self.assertEqual(a.validate_job(j),a._inherited.validate_job(j))

    def test_prospective_pair_rejects_old_binding(self):
        with self.assertRaises(ValueError):a.compare({'job':job(),'binding':{}},{'job':job(3),'binding':{}})

    def test_real_runner_first_and_analyzer_first_processes(self):
        self.assertTrue((a.HERE/'runner.py').exists(),'Real new runner required; no mocked import-order acceptance')
        for order in ('runner-first','analyzer-first'):
            script="""import importlib.util,pathlib,sys,numpy as np
here=pathlib.Path(sys.argv[1]);order=sys.argv[2]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
if order=='runner-first':
 r=load('actual_revision02_runner',here/'runner.py');m=r.local_module('analyzer')
else:
 m=load('actual_revision02_analyzer',here/'analyzer.py');r=load('actual_revision02_runner_after',here/'runner.py')
v=m._height.__globals__['offsets'](8,np.array([7.,13.,23.,39.,55.]))
assert v['p'].shape==(5,3) and np.max(abs(v['p'][:,2]))>.03
assert m._height.__globals__ is not m._inherited.height_evidence.__globals__
print('real order passed',order)
"""
            p=subprocess.run([sys.executable,'-c',script,str(a.HERE),order],cwd=a.REPO,
                             env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),text=True,capture_output=True)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)


class PreparedRun:
    """Real factory/decoder/guards plus journaled synthetic CLI; zero flights.

    No receipt is hand-authored. A bounded local encoded ULog and a simulated
    listener backend exercise the actual new runner factory and journal shape.
    Full production protocol/source/flight acceptance is deliberately not
    claimed by this preparation-component fixture.
    """
    def __init__(self, root, age=10000, pending=False, early_empty=False, post_shape=False):
        self.root=Path(root);self.root.mkdir(exist_ok=True)
        self.runner=a.load_path('revision04_real_runner_for_receipts',a.HERE/'runner.py')
        self.fixtures=a.load_path('revision04_monitor_fixtures',a.HERE.parent/'r03_monitor02/test_integration.py')
        old,_,state,topics,_,_=self.fixtures.MonitorGuardTests().fixture()
        self.check=self.runner.execution_checks_class().__new__(self.runner.execution_checks_class())
        self.check.__dict__.update(old.__dict__)
        self.check.reference=None
        self.check.log_root=self.root/'owned';self.check.log_root.mkdir()
        self.check.logs_before=set()
        self.path=self.check.log_root/'sess001/log001.ulg';self.path.parent.mkdir()
        tables,_=self.fixtures.heading_tables()
        header,packets=self.fixtures.encode(tables)
        self.raw=header+b''.join(row[3] for row in packets)
        self.topics={name:{key:value for key,value in data.items() if key!='_clock'} for name,data in topics.items()}
        for data in self.topics.values(): data['timestamp']=4000000
        self.topics['vehicle_status']={'timestamp':4000000,'arming_state':1}
        self.topics['vehicle_attitude']={'timestamp':4000000}
        state['position']['timestamp']=4000000
        self.state=state
        self.commands=[];self.samples=[]
        if early_empty:
            self.path.write_bytes(header)  # Complete schema but no attitude/data yet.
            stamp=self.topics['sta_rate_ctrl_status'].pop('timestamp')
            self.warmup()  # Original warmup allows the first absent rate timestamp.
            self.topics['sta_rate_ctrl_status']['timestamp']=stamp
        if pending:
            self.warmup()  # No owned file is a preparation state, not approval.
            self.path.write_bytes(self.raw[:7]);self.warmup()
        cut=next(i for i,row in enumerate(packets) if row[0]>3000000)
        first=header+b''.join(row[3] for row in packets[:cut])
        self.path.write_bytes(first);self.warmup()
        # A second warmup can have the same prefix; it must reuse the state.
        self.warmup()
        with self.path.open('ab') as stream:stream.write(self.raw[len(first):])
        self.topics['vehicle_local_position']['timestamp']=3990000+age
        self.topics['vehicle_status']['timestamp']=3990000+age
        reference=self.check.start_heading(self.topic,self.root)
        (self.root/'height_reference.json').write_text(json.dumps(reference))
        self.command('commander',['takeoff'],'')  # Journal fixture only, no subprocess.
        self.topic('vehicle_attitude')  # Original full command audit topic coverage.
        if post_shape:
            self.check.reference=reference
            # Real nonlanding monitor route; still synthetic/unarmed telemetry.
            for phase in ('takeoff','hover'):
                self.samples.append({'phase':phase})
                self.topics['sta_rate_ctrl_status']['publish_seq']+=1
                self.check.monitor(phase,None,self.topic,self.root,self.state)
            # Exercise the exact receipt wrapper for a multi-read/multi-topic
            # landing-shaped call. This is only a serialization/association
            # fixture, NOT a synthetic proof of physical landing safety.
            self.samples.append({'phase':'landing'})
            def multi_read(row):
                topic=self.check._prearm_topic(self.topic,row)
                self.check.live.read();topic('vehicle_local_position')
                self.check.live.read();topic('vehicle_status');topic('vehicle_local_position')
                row['read_attempted']=True
                row['segments']['parent_monitor_s']=0.
            self.check._prearm_record(self.root,'landing',multi_read)
        archive=self.root/'archived.ulg';archive.write_bytes(self.raw)
        result={'logs':[{'source':str(self.path),'archive':str(archive),'bytes':len(self.raw),'sha256':a.digest(archive)}]}
        (self.root/'result.json').write_text(json.dumps(result))
        self.flush()

    def command(self,module,args,raw):
        start=time.monotonic_ns();end=time.monotonic_ns()
        receipt=a._cli_clock.receipt(module,args,raw,start,end)
        self.commands.append(dict(cmd=['/synthetic/px4-'+module,*args],returncode=0,stdout=raw,stderr='',
            host_start_ns=start,host_end_ns=end,host_elapsed_ns=end-start,clock=receipt))
        return receipt

    def topic(self,name):
        data=self.topics[name]
        text='TOPIC: '+name+'\n'
        for key,value in data.items():
            if key=='timestamp':text+=' timestamp: '+str(int(value))+' (0.000000 seconds ago)\n'
            elif np.isscalar(value):text+=' '+key+': '+str(value)+'\n'
        receipt=self.command('listener',[name,'-n','1'],text)
        parsed=a._task_reference.scalars(text)
        if receipt is not None:parsed['_clock']=receipt
        return parsed

    def warmup(self):
        self.samples.append({'phase':'warmup'})
        self.topics['sta_rate_ctrl_status']['publish_seq']+=1
        self.check.monitor('warmup',None,self.topic,self.root,self.state)

    def flush(self):
        for name,items in (('commands.jsonl',self.commands),('samples.jsonl',self.samples)):
            (self.root/name).write_text(''.join(json.dumps(row)+'\n' for row in items))


class ActualPreparedEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def fixture(self,**kwargs):return PreparedRun(self.root,**kwargs)
    def rows(self):return a.json_lines(self.root/a._prearm.RECEIPT)
    def save_rows(self,rows):
        (self.root/a._prearm.RECEIPT).write_text(''.join(json.dumps(row)+'\n' for row in rows))

    def test_actual_factory_full_history_success(self):
        f=self.fixture();result=a.prearm_evidence(self.root)
        self.assertTrue(result['valid']);self.assertEqual(result['warmup_completed_reads'],2)
        self.assertEqual(result['transport_age_us'],10000)
        self.assertGreater(self.rows()[-1]['raw_reader']['new_bytes'],0)
        self.assertIs(f.check.live,f.check._prearm04['reader'])
        self.assertIs(f.check.landing_live,f.check.live)

    def test_pending_absent_and_partial_header_are_not_cold_acceptance(self):
        self.fixture(pending=True);result=a.prearm_evidence(self.root)
        self.assertEqual(result['warmup_completed_reads'],2)
        self.assertEqual(result['prefix_reads'],4)

    def test_original_inclusive_500ms(self):
        self.fixture(age=500000)
        self.assertEqual(a.prearm_evidence(self.root)['transport_age_us'],500000)

    def test_early_complete_header_without_attitude_and_none_rate_timestamp(self):
        self.fixture(early_empty=True);result=a.prearm_evidence(self.root)
        self.assertEqual(result['warmup_completed_reads'],3)
        first=self.rows()[0]
        self.assertIsNone(first['actual_cli'][0]['timestamp_us'])
        self.assertIsNone(first['actual_cli'][0]['receipt'])
        self.assertTrue(first['raw_reader']['completed'])

    def test_post_prearm_multiread_phase_and_none_status_clock_shape(self):
        self.fixture(post_shape=True);result=a.prearm_evidence(self.root)
        self.assertEqual(result['receipts'],6)
        last=self.rows()[-1]
        self.assertEqual(len(last['actual_cli']),3)
        self.assertIsNone(last['actual_cli'][1]['receipt'])
        self.assertEqual(last['raw_reader']['new_bytes'],0)
        self.assertTrue(last['read_attempted'])
        last['reader_inode']+=1
        rows=self.rows();rows[-1]=last;self.save_rows(rows)
        with self.assertRaisesRegex(ValueError,'identity'):a.prearm_evidence(self.root)

    def test_prearm_reference_functions_are_exact_original_bindings(self):
        runner=a.load_path('revision04_reference_identity_runner',a.HERE/'runner.py')
        original=runner.Checks.start_heading.__globals__
        import inspect
        # reference_row/freeze_reference are LOCAL imports in start_heading;
        # the same-named module-global reference_row is an older unused helper.
        body=inspect.getsource(runner.Checks.start_heading)
        self.assertIn('from v04_prearm17 import reference_row',body)
        self.assertIn('from v04_task04 import freeze_reference',body)
        self.assertEqual(inspect.getsource(sys.modules['v04_prearm17'].reference_row),inspect.getsource(a._reference.reference_row))
        self.assertEqual(inspect.getsource(sys.modules['v04_task04'].freeze_reference),inspect.getsource(a._task_reference.freeze_reference))
        self.assertEqual(inspect.getsource(original['replay']),inspect.getsource(a._heading.replay))

    def test_old_failed_run_cannot_pass_missing_prearm04_evidence(self):
        old=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision03/A/batch01/run007')
        before=a._repair.snapshot(old)
        with self.assertRaises(FileNotFoundError):a.prearm_evidence(old)
        self.assertEqual(before,a._repair.snapshot(old))

    def test_original_500001_and_future_rejected_by_actual_factory(self):
        for age in (500001,-1,540000):
            with self.subTest(age=age),tempfile.TemporaryDirectory() as temp:
                with self.assertRaisesRegex(RuntimeError,'Stale prearm ULog'):PreparedRun(temp,age=age)

    def test_missing_receipt_rejected(self):
        self.fixture();(self.root/a._prearm.RECEIPT).unlink()
        with self.assertRaises(FileNotFoundError):a.prearm_evidence(self.root)

    def test_removed_warmup_or_prearm(self):
        self.fixture();original=self.rows()
        for rows in (original[1:],original[:-1],original+original[-1:]):
            self.save_rows(rows)
            with self.subTest(length=len(rows)),self.assertRaises(ValueError):a.prearm_evidence(self.root)

    def test_error_latch_or_granted_authority_rejected(self):
        self.fixture();original=self.rows()
        for key,value in (('error','failure'),('failure_latched',True),('execution_authority_granted',True),
                          ('transport_max_age_us',500001),('transport_max_age_us',500000.0)):
            rows=copy.deepcopy(original);rows[-1][key]=value;self.save_rows(rows)
            with self.subTest(key=key),self.assertRaises(ValueError):a.prearm_evidence(self.root)

    def test_prefix_accounting_and_persistent_identity_rejected(self):
        self.fixture();original=self.rows()
        for key in ('new_bytes','new_records','raw_offset','pending_bytes','total_records','received_bytes'):
            rows=copy.deepcopy(original);rows[-1]['raw_reader'][key]+=1;self.save_rows(rows)
            with self.subTest(key=key),self.assertRaises(ValueError):a.prearm_evidence(self.root)
        for key in ('reader_inode','reader_device','warmup_reads'):
            rows=copy.deepcopy(original);rows[-1][key]+=1;self.save_rows(rows)
            with self.subTest(key=key),self.assertRaises(ValueError):a.prearm_evidence(self.root)

    def test_wrong_reference_watermark_or_omitted_replay_rejected(self):
        self.fixture();original=self.rows()
        for key,value in (('reference_timestamp_us',3980000),('sealed_watermark_us',4000000),('segments',{'reference_s':0.})):
            rows=copy.deepcopy(original);rows[-1][key]=value;self.save_rows(rows)
            with self.subTest(key=key),self.assertRaises(ValueError):a.prearm_evidence(self.root)

    def test_cli_timestamp_receipt_and_order_are_not_trusted(self):
        self.fixture();original=self.rows()
        for mutation in ('timestamp','receipt','order','host'):
            rows=copy.deepcopy(original);cli=rows[-1]['actual_cli']
            if mutation=='timestamp':cli[-1]['timestamp_us']+=1
            if mutation=='receipt':cli[-1]['receipt']['age_at_print_us']+=1
            if mutation=='order':cli.reverse()
            if mutation=='host':cli[-1]['started_monotonic']=0
            self.save_rows(rows)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):a.prearm_evidence(self.root)

    def test_archive_or_reference_drift_rejected(self):
        self.fixture();path=self.root/'archived.ulg';raw=path.read_bytes();path.write_bytes(raw+b'bad')
        with self.assertRaises(ValueError):a.prearm_evidence(self.root)
        path.write_bytes(raw)
        ref=json.loads((self.root/'height_reference.json').read_text());ref['position']['z']+=.001
        (self.root/'height_reference.json').write_text(json.dumps(ref))
        with self.assertRaisesRegex(ValueError,'reference'):a.prearm_evidence(self.root)

    def test_historical_no_new_prearm_claim(self):
        with patch.object(a._repair,'run_diagnostic',return_value={'accepted':False,'historical_acceptance_unchanged':True}):
            result=a.historical_diagnostic('old','new','analyzer-first')
        self.assertFalse(result['accepted']);self.assertFalse(result['new_prearm_acceptance'])
        self.assertFalse(result['prearm04_receipt_applicable'])


if __name__=='__main__':unittest.main(verbosity=2)
