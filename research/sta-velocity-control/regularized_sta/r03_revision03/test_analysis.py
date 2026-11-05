"""Prospective provenance/import regression; fixtures are not new flights."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import numpy as np
import analyzer as a


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
        self.retained=dict(attempts=8,accepted=6,failed=2,accepted_for_new_matrix=0,batches=[])
        self.migration=copy.deepcopy(a._protocol().seed_migration())
        self.authority=a._protocol().AUTHORIZATION
        self.p=dict(revision=a.REVISION,stage='R03-revision03-A',gate='A',jobs=[self.job],
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

    def test_budget_9_36_8_44_exact(self):
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
            value['historical_budget']['accepted']=6.0
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
        with patch.object(a._inherited,'analyze',namespace['analyze']):
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


if __name__=='__main__':unittest.main(verbosity=2)
