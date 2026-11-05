"""Offline wiring/authority tests. Synthetic stubs are NOT flight acceptance.

The real inherited analyze function is executed through its entire control flow;
individual already-tested numerical/ULog predicates are spied at their boundary.
Separate timing tests exercise real arrays. No simulator or formal seeds used.
"""
import copy
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_up08_analysis_test', HERE/'analyzer.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2)+'\n')


class ProvenanceFixture:
    def __init__(self, root):
        self.run = Path(root)/'batch01/diag001'
        self.run.mkdir(parents=True)
        self.qp = Path(root)/'qualification01/evidence.json'
        self.qp.parent.mkdir()
        save(self.qp, {'success': True})
        self.execution = Path(root)/'execution.json'
        save(self.execution, {'fixture_only': True})
        self.job = dict(id='diag001', gate='D', mode=0, axes=0,
                        revision='r03_upstream08', parameters={'MPC_VC_MODE': 0})
        self.frozen = dict(revision='r03_upstream08', stage='R03-upstream08-diagnostic',
            jobs=[self.job], startup_overrides={'IMU_TEST': 0},
            qualification_path=str(self.qp), execution_path=str(self.execution),
            artifacts={'new_run_root': str(self.run.parent)})
        self.p = copy.deepcopy(self.frozen)
        self.p['startup_overrides'].update(self.job['parameters'])
        self.q = dict(source_head='fixture-source', firmware_sha256='fixture-binary')
        self.approval = dict(approved=True, diagnostic_only=True, accepted_for_R03=0)
        self.archive = self.run/'archive.ulg'
        self.archive.write_bytes(b'provenance-only, not a ULog')
        (self.run/'original_parameters.bson').write_bytes(b'exact original backup')
        self.record = dict(source_head=self.q['source_head'], binary_sha256=self.q['firmware_sha256'],
            scenario_sha256=a.digest(self.execution), scenario_path=str(self.execution),
            logs=[dict(archive=str(self.archive), sha256=a.digest(self.archive))])
        self.restore = dict(source_head=self.q['source_head'], gate='D', job_id='diag001',
            parameter_restore_exact=True, remaining_simulators=[], stopped_before_restore=True,
            original_parameter_sha256=a.digest(self.run/'original_parameters.bson'),
            restored_parameter_sha256=a.digest(self.run/'original_parameters.bson'))
        self.write()
        self.calls = []
        def qualified(head, path):
            self.calls.append(('qualified', head, str(path)))
            if head != self.q['source_head'] or Path(path) != self.qp:
                raise ValueError('wrong source or qualification fixture')
            return copy.deepcopy(self.q)
        self.api = types.SimpleNamespace(
            require_execution_authority=lambda: self.calls.append(('authority',)),
            load_protocol=lambda: copy.deepcopy(self.frozen),
            require_qualification=qualified,
            authorization_binding=lambda q, path: copy.deepcopy(self.approval),
            qualification_binding=lambda head: {'source_head': head, 'diagnostic_only': True})

    def write(self):
        for name, value in {
            'authorization.json': self.approval, 'result.json': self.record,
            'run_protocol.json': self.p, 'job.json': self.job,
            'parameter_restore.json': self.restore,
            'qualification_reference.json': {'path': str(self.qp), 'sha256': a.digest(self.qp)},
            'runtime_parameters_start.json': {'SDLOG_PROFILE': 3089},
            'runtime_parameters_end.json': {'SDLOG_PROFILE': 3089},
        }.items():
            save(self.run/name, value)


class Provenance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.f = ProvenanceFixture(self.temp.name)
        self.mock = patch.object(a, 'api', return_value=self.f.api)
        self.mock.start(); self.addCleanup(self.mock.stop)

    def check(self):
        return a.provenance(self.f.run, self.f.p, self.f.job)

    def test_exact_clean_diagnostic_source(self):
        before = {str(p): a.digest(p) for p in self.f.run.iterdir()}
        result = self.check()
        self.assertEqual(result['source_head'], 'fixture-source')
        self.assertEqual(before, {str(p): a.digest(p) for p in self.f.run.iterdir()})
        self.assertIn(('authority',), self.f.calls)

    def test_wrong_protocol_extra_field(self):
        self.f.p['extra'] = 'changed'
        with self.assertRaises(ValueError): self.check()

    def test_wrong_job_mode_axes_or_revision(self):
        for field, value in [('mode', 3), ('axes', 1), ('revision', 'r03_revision06')]:
            job = copy.deepcopy(self.f.job); job[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                a.provenance(self.f.run, self.f.p, job)

    def test_wrong_parameter_overlay(self):
        self.f.p['startup_overrides']['MPC_VC_MODE'] = 1
        with self.assertRaises(ValueError): self.check()

    def test_old_or_sibling_run_rejected_before_writes(self):
        other = self.f.run.parent/'run030'; other.mkdir()
        with self.assertRaises(ValueError): a.provenance(other, self.f.p, self.f.job)
        self.assertEqual(list(other.iterdir()), [])

    def test_saved_job_or_protocol_changed(self):
        for name in ('job.json', 'run_protocol.json'):
            self.f.write(); value = a.read(self.f.run/name); value['changed'] = True
            save(self.f.run/name, value)
            with self.subTest(name=name), self.assertRaises(ValueError): self.check()

    def test_authorization_boolean_and_binding(self):
        for value in (False, 1, None):
            save(self.f.run/'authorization.json', {**self.f.approval, 'approved': value})
            with self.subTest(value=value), self.assertRaises(ValueError): self.check()

    def test_qualification_reference_hash_or_path(self):
        for value in ({'path': str(self.f.qp), 'sha256': 'wrong'},
                      {'path': str(self.f.qp.parent/'other'), 'sha256': a.digest(self.f.qp)}):
            save(self.f.run/'qualification_reference.json', value)
            with self.subTest(value=value), self.assertRaises(ValueError): self.check()

    def test_source_binary_scenario_changes(self):
        for key in ('source_head', 'binary_sha256', 'scenario_sha256', 'scenario_path'):
            self.f.write(); value = copy.deepcopy(self.f.record); value[key] = 'wrong'
            save(self.f.run/'result.json', value)
            with self.subTest(key=key), self.assertRaises(ValueError): self.check()

    def test_missing_duplicate_or_foreign_archive(self):
        for logs in ([], self.f.record['logs']*2, [{'archive': str(Path(self.temp.name)/'other.ulg')}]):
            self.f.write(); save(self.f.run/'result.json', {**self.f.record, 'logs': logs})
            with self.subTest(logs=logs), self.assertRaises(ValueError): self.check()

    def test_cleanup_and_restore_all_fields(self):
        changes = {'parameter_restore_exact': 1, 'remaining_simulators': ['px4'],
            'stopped_before_restore': False, 'source_head': 'wrong', 'gate': 'C',
            'job_id': 'other', 'original_parameter_sha256': 'wrong',
            'restored_parameter_sha256': 'wrong'}
        for key, value in changes.items():
            save(self.f.run/'parameter_restore.json', {**self.f.restore, key: value})
            with self.subTest(key=key), self.assertRaises(ValueError): self.check()

    def test_profile_must_be_present_at_both_ends(self):
        for name in ('runtime_parameters_start.json', 'runtime_parameters_end.json'):
            for value in (1041, 2048, None):
                self.f.write(); save(self.f.run/name, {'SDLOG_PROFILE': value})
                with self.subTest(name=name, value=value), self.assertRaises(ValueError): self.check()


class ScienceFixture:
    """Actual inherited function, spied predicate boundaries, synthetic tables."""
    def __init__(self, root, failed=None):
        self.run = Path(root); self.failed = failed; self.calls = []
        self.events = dict(takeoff_command=100, hover_start=200, hover_end=90200200,
                           land_command=90200200, landed_disarmed=100000000)
        save(self.run/'result.json', {'events': [{'name': k, 'timestamp_us': v} for k,v in self.events.items()]})
        save(self.run/'landing_context.json', {})
        save(self.run/'postland_tail.json', dict(landing_start_us=self.events['land_command'],
            landed_disarmed_us=self.events['landed_disarmed'], snapshots=[{'pending': []}], health={'ok': True}))
        (self.run/'commands.jsonl').write_text(json.dumps({'cmd':['px4-commander','mode','auto:land'],'returncode':0})+'\n')
        for name in ('runtime_parameters_start.json', 'runtime_parameters_end.json'): save(self.run/name, {'SDLOG_PROFILE':3089})
        self.d = {k: np.zeros(2, dtype=int) for k in ('z_phase','active_axes','committed_axes','pid_axes','takeoff_state','reset_bits')}
        self.d.update(timestamp=np.array([300,400]), z_hte_shift=np.zeros(2))
        self.q = dict(control_updated=np.ones(2,dtype=bool), variant_eff=np.zeros(2,dtype=int),
                      path_ns=np.ones(2),module_ns=np.ones(2))
        self.rate = dict(timestamp=np.array([300,400]),sat_bits=np.zeros(2),sat_valid=np.ones(2))
        self.log = types.SimpleNamespace(dropouts=[],file_corruption=False,initial_parameters={},
            position_log_evidence={'fixture':True},get_dataset=lambda name,*args:
            types.SimpleNamespace(data=self.rate if name=='sta_rate_ctrl_status' else self.d))
        self.base = dict(accepted=True,checks={'safety':True},ulog={'archive':str(self.run/'main.ulg')},
            metrics={'position_error_m':{'rmse':[.01]*3},'yaw_error_rad':{'rmse':.01},'height_error_from_2p5_m':{}})
        self.job = dict(gate='D', task='V', mode=0, axes=0, parameters={'MPC_VCT_TEST':8},
                        main_duration_s=64, divisor=1)
        self.p = dict(plugins='fixture',config_dir='fixture',startup_overrides={})

    def spy(self, name, result):
        def call(*args, **kwargs):
            self.calls.append(name)
            if self.failed == name: raise ValueError('injected '+name)
            return copy.deepcopy(result)
        return call

    def full(self, bound, save=None):
        # Keep the actual factory, with isolated function globals only.
        function = REAL_FULL(bound, save)
        base = types.SimpleNamespace(analyze=self.spy('baseline', self.base))
        bs = types.SimpleNamespace(loader=types.SimpleNamespace(exec_module=lambda m: None))
        util = types.SimpleNamespace(spec_from_file_location=lambda *args: bs,module_from_spec=lambda s: base)
        replaces = dict(importlib=types.SimpleNamespace(util=util),
            verify_model=self.spy('model', None), ULog=lambda path:self.log,
            check_components=self.spy('components', ({'ok':True},self.d,self.q)),
            first_invocation=self.spy('first_invocation',{}),check_exit=self.spy('exit',{}),
            check_targets=self.spy('targets',{}), window_metrics=self.spy('window',{}),
            spectral_metrics=self.spy('spectra',{'rate':100}),
            check_parameters=self.spy('parameters',None),exact_output_match=self.spy('outputs',{}),
            height_evidence=self.spy('height',{}),check_complete=self.spy('landing',{}),
            check_health=self.spy('health',{'ok':True}),audit_commands=self.spy('cli',{}),
            saturation_summary=self.spy('mixer',{}),
            r02=types.SimpleNamespace(cadence_checks=lambda:types.SimpleNamespace(check_pid_path=self.spy('pid',{})),
                                     rate_and_actuator_evidence=self.spy('rate',{})))
        return a.old._numeric.clone(function, **replaces)


REAL_FULL = a.old.full_analysis


class ScienceWiring(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.f = ScienceFixture(self.temp.name)
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.provenance = self.stack.enter_context(patch.object(a,'provenance',return_value={'fixture':True}))
        self.prearm = self.stack.enter_context(patch.object(a.old,'prearm_evidence',return_value={'valid':True}))
        self.stack.enter_context(patch.object(a.old,'full_analysis',side_effect=self.f.full))
        self.stack.enter_context(patch.object(a.old._inherited,'ULog',side_effect=lambda path:self.f.log))
        self.timing = self.stack.enter_context(patch.object(a.timing,'inspect_log',return_value={'diagnostic_only':True}))

    def run_analysis(self): return a.analyze(self.f.run,self.f.p,self.f.job)

    def test_complete_real_science_control_flow_never_accepts(self):
        result = self.run_analysis()
        self.assertTrue(result['scientific_checks_complete']);self.assertTrue(result['diagnostic_checks_complete'])
        self.assertIs(result['accepted'],False);self.assertEqual(result['accepted_for_R03'],0)
        self.assertIs(result['r03_gate_pass'],False)
        self.assertEqual(result['candidate_numeric_binding'],a.old.NUMERIC_BINDING)
        self.assertEqual(result['handoff_dependency_binding'],a.old.HANDOFF_BINDING)
        self.prearm.assert_called_once();self.timing.assert_called_once()
        for name in ('model','baseline','components','first_invocation','exit','targets','window',
                     'pid','spectra','parameters','outputs','rate','height','landing','health','cli','mixer'):
            self.assertIn(name,self.f.calls)
        self.assertEqual(self.f.calls.count('components'),2)
        self.assertEqual(self.f.calls.count('parameters'),2)
        for name in ('v00_metrics.json','r03_metrics.json','diagnostic_metrics.json'):
            self.assertIs(a.read(self.f.run/name)['accepted'],False)
        self.assertFalse((self.f.run/'gate_pass.json').exists())

    def test_each_required_science_failure_stops_later_acceptance(self):
        for name in ('model','baseline','components','first_invocation','exit','targets','window',
                     'pid','spectra','parameters','outputs','rate','height','landing','health','cli','mixer'):
            self.f.failed=name;self.f.calls.clear();self.timing.reset_mock()
            result=self.run_analysis()
            with self.subTest(name=name):
                self.assertIs(result['accepted'],False);self.assertIs(result['scientific_checks_complete'],False)
                self.assertIs(result['diagnostic_checks_complete'],False)
                self.assertIn('injected '+name,result['error']);self.timing.assert_not_called()

    def test_late_tail_boundary_failure_remains_failure(self):
        value=a.read(self.f.run/'postland_tail.json');value['snapshots'][-1]['pending']=['imu0']
        save(self.f.run/'postland_tail.json',value)
        result=self.run_analysis()
        self.assertIn('Incomplete postlanding tail',result['error']);self.timing.assert_not_called()

    def test_missing_disarm_event_never_synthesized(self):
        value=a.read(self.f.run/'result.json');value['events']=[e for e in value['events'] if e['name']!='landed_disarmed']
        save(self.f.run/'result.json',value)
        result=self.run_analysis()
        self.assertIs(result['scientific_checks_complete'],False)
        self.assertIn('landed_disarmed',result['error']);self.timing.assert_not_called()

    def test_prearm_invalid_rejected_before_science(self):
        self.prearm.side_effect=ValueError('invalid prepared reader')
        result=self.run_analysis()
        self.assertIn('invalid prepared reader',result['error']);self.assertEqual(self.f.calls,[])

    def test_additional_timing_failure_does_not_clear_science_result(self):
        self.timing.side_effect=ValueError('sparse gyro')
        result=self.run_analysis()
        self.assertIs(result['scientific_checks_complete'],True)
        self.assertIs(result['diagnostic_checks_complete'],False)
        self.assertIs(result['accepted'],False);self.assertIn('sparse gyro',result['error'])

    def test_foreign_source_rejected_before_any_write(self):
        before={p.name:a.digest(p) for p in self.f.run.iterdir()}
        self.provenance.side_effect=ValueError('legacy source')
        with self.assertRaises(ValueError):self.run_analysis()
        self.assertEqual(before,{p.name:a.digest(p) for p in self.f.run.iterdir()})

    def test_private_scientific_binding_is_exact(self):
        before=dict(a.old._inherited.analyze.__globals__)
        f=REAL_FULL(lambda *args:{})
        self.assertIs(f.__globals__['height_evidence'],a.old._height)
        self.assertIs(f.__globals__['check_components'],a.old._components)
        self.assertIs(f.__globals__['r02'],a.old._numeric_r02)
        self.assertEqual(before,a.old._inherited.analyze.__globals__)


class Historical(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.source=Path(self.temp.name)/'original';self.source.mkdir()
        self.dest=Path(self.temp.name)/'new'
        save(self.source/'job.json',{'revision':'r03_revision06','gate':'D'})
        save(self.source/'result.json',{'success':False,'error':'CLI reference representation changed: ref_alt'})

    def fake_full(self, provenance, save):
        def run(source,p,job):
            value={'accepted':False,'error':'landed_disarmed'};save(source/'r03_metrics.json',value);return value
        return run

    def test_no_original_metrics_failure_retained_and_no_source_writes(self):
        before={p.name:a.digest(p) for p in self.source.iterdir()}
        with patch.object(a.old,'replay_protocol',return_value={}),patch.object(a.old,'full_analysis',side_effect=self.fake_full):
            result=a.historical(self.source,self.dest,'analyzer-first')
        self.assertIs(result['original_accepted'],False);self.assertIs(result['historical_acceptance_unchanged'],True)
        self.assertIs(result['accepted'],False);self.assertEqual(result['new_flights'],0)
        self.assertEqual(result['original_error'],'CLI reference representation changed: ref_alt')
        self.assertEqual(result['replay_error'],'landed_disarmed')
        self.assertEqual(before,{p.name:a.digest(p) for p in self.source.iterdir()})
        self.assertFalse((self.dest/'authorization.json').exists())

    def test_existing_original_failure_not_promoted(self):
        save(self.source/'r03_metrics.json',{'accepted':False,'error':'old failure'})
        with patch.object(a.old,'replay_protocol',return_value={}),patch.object(a.old,'full_analysis',return_value=lambda *args:{'accepted':True}):
            with self.assertRaisesRegex(ValueError,'pass/fail changed'):a.historical(self.source,self.dest,'analyzer-first')
        self.assertIs(a.read(self.source/'r03_metrics.json')['accepted'],False)

    def test_missing_metrics_cannot_invent_failure_for_success_or_unknown(self):
        for success in (True, 0, None):
            save(self.source/'result.json',{'success':success,'error':None})
            with patch.object(a.old,'replay_protocol',return_value={}),\
                    self.subTest(success=success),self.assertRaisesRegex(ValueError,'explicitly failed result'):
                a.historical(self.source,self.dest,'analyzer-first')
            self.assertFalse(self.dest.exists())

    def test_nested_baseline_save_receives_copy_not_original(self):
        save(self.source/'v00_metrics.json',{'accepted':False,'old_limitations':['preserve']})
        original=a.digest(self.source/'v00_metrics.json')
        def full(provenance, save):
            def run(directory,p,job):
                self.assertEqual(directory,self.dest)
                provenance(directory,p,job)
                # The inherited baseline has its own save global. It must only
                # see the copy directory, regardless of the outer save hook.
                a.old._inherited.save(directory/'v00_metrics.json',{'accepted':False,'recomputed':True})
                value={'accepted':False,'error':'missing landed_disarmed'}
                save(directory/'r03_metrics.json',value)
                return value
            return run
        with patch.object(a.old,'replay_protocol',return_value={}),patch.object(a.old,'provenance',return_value={}) as p,\
                patch.object(a.old,'full_analysis',side_effect=full):
            result=a.historical(self.source,self.dest,'analyzer-first')
        self.assertEqual(p.call_args.args[0],self.source)
        self.assertEqual(a.digest(self.source/'v00_metrics.json'),original)
        self.assertTrue(a.read(self.dest/'v00_metrics.json')['recomputed'])
        self.assertTrue(result['source_inputs_unchanged'])

    def test_fresh_external_destination_required(self):
        for dest in (self.source,self.source/'nested'):
            with self.subTest(dest=dest),self.assertRaises(ValueError):a.historical(self.source,dest,'analyzer-first')

    def test_invalid_import_order(self):
        with self.assertRaises(ValueError):a.historical(self.source,self.dest,'other')


class Comparison(unittest.TestCase):
    def setUp(self):
        real_budget=a.api().budget()
        self.jobs=[]
        mocked=types.SimpleNamespace(budget=lambda:copy.deepcopy(real_budget),
            load_protocol=lambda:{'jobs':copy.deepcopy(self.jobs)})
        stub=patch.object(a,'api',return_value=mocked)
        stub.start();self.addCleanup(stub.stop)

    def values(self):
        jobs=json.loads((HERE.parent/'r03_revision06/manifest.json').read_text())
        pid=copy.deepcopy(next(j for j in jobs if j['mode']==0));esta=copy.deepcopy(next(j for j in jobs if j['mode']==1))
        esta['seed']=pid['seed']
        for index,job in enumerate((pid,esta),1):
            job.update(revision='r03_upstream08',id='diag%03d'%index,phase='diagnostic')
        self.jobs=copy.deepcopy([pid,esta])
        def item(job):
            windows={name:{'error':{'rmse':[.01]*3}} for name,_,_ in a.old._inherited.windows(job)}
            return dict(job=job,binding={'revision':'r03_upstream08','same_source':True,**a.api().budget()},diagnostic_checks_complete=True,
                scientific_checks_complete=True,accepted=False,accepted_for_R03=0,r03_gate_pass=False,
                diagnostic_only=True,flight_accepted=False,prearm_preparation={'valid':True},
                candidate_numeric_binding=a.old.NUMERIC_BINDING,handoff_dependency_binding=a.old.HANDOFF_BINDING,
                diagnostic={'error':{'rmse':[.01]*3},'windows':windows},position_rmse=[.01]*3,yaw_rmse=.01)
        return item(pid),item(esta)

    def test_real_risk_comparison_remains_nonaccepting(self):
        pid,esta=self.values();before=copy.deepcopy((pid,esta));result=a.compare(pid,esta)
        self.assertIs(result['development_risk_passed'],True);self.assertIs(result['accepted'],False)
        self.assertEqual(result['accepted_for_R03'],0);self.assertEqual((pid,esta),before)

    def test_foreign_pair_or_failed_diagnostic_rejected(self):
        for key,value in [('accepted',True),('diagnostic_checks_complete',False),('accepted_for_R03',1),('r03_gate_pass',True)]:
            pid,esta=self.values();esta[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):a.compare(pid,esta)
        pid,esta=self.values();esta['job']['seed']+=1
        with self.assertRaises(ValueError):a.compare(pid,esta)

    def test_science_preparation_and_component_binding_cannot_be_forged(self):
        changes=[('scientific_checks_complete',False),('prearm_preparation',{'valid':False}),
                 ('candidate_numeric_binding',{}),('handoff_dependency_binding',{})]
        for key,value in changes:
            pid,esta=self.values();esta[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):a.compare(pid,esta)

    def test_old_revision_and_rsta_are_not_part_of_two_diagnostics(self):
        for key,value in (('revision','r03_revision06'),('mode',3),('id','run030')):
            pid,esta=self.values();esta['job'][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'exact PID/ESTA diagnostic manifest'):
                a.compare(pid,esta)


class ImportIsolation(unittest.TestCase):
    def test_real_runner_first_and_analyzer_first_have_private_xyz_binding(self):
        script=r'''
import importlib.util,sys,types
from pathlib import Path
import numpy as np
here=Path(sys.argv[1]);order=sys.argv[2]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
if order=='runner-first':load('_actual_up08_runner_first',here/'runner.py')
m=load('_actual_up08_analyzer',here/'analyzer.py')
if order=='analyzer-first':load('_actual_up08_runner_last',here/'runner.py')
bad=types.ModuleType('task');bad.offsets=lambda *args:(_ for _ in ()).throw(ValueError('generic task must not execute'))
sys.modules['task']=bad
h=m.old._height;f=h.__globals__['check_handoff'];offs=f.__globals__['offsets']
value=offs(8,np.array([0.,16.,32.]))
assert np.asarray(value['p']).shape==(3,3)
assert m.old._height.__globals__['offsets'] is offs
assert sys.modules['task'] is bad
assert m.old.full_analysis(lambda *args:{}).__globals__['height_evidence'] is h
print('actual import order',order,'private XYZ dependency retained')
'''
        for order in ('runner-first','analyzer-first'):
            with self.subTest(order=order):
                result=subprocess.run([sys.executable,'-B','-c',script,str(HERE),order],text=True,capture_output=True,timeout=40)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main(verbosity=2)
