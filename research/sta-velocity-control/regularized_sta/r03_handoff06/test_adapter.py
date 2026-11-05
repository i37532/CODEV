"""Synthetic-only binding and full frozen handoff body tests; no flights/log replay."""
import ast
import copy
import importlib.util
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

sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location('handoff06_test_adapter', Path(__file__).with_name('adapter.py'))
a = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(a)


class Binding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analyzer = a.load_analyzer('analyzer-first')
        cls.height, cls.binding = a.bind_height(cls.analyzer)

    def test_all_pins_match(self):
        self.assertEqual(len(a.pinned_inputs()), 17)

    def test_both_full_function_asts_restore_identically(self):
        wanted = ast.parse('from task import offsets').body[0]
        for path, name in ((a.HEIGHT, 'height_evidence'), (a.HANDOFF, 'check_handoff')):
            old, new = a.import_only_ast(path, name)
            self.assertEqual(sum(isinstance(n, ast.Pass) for n in ast.walk(new)), 1)
            class Restore(ast.NodeTransformer):
                def visit_Pass(self, node): return copy.deepcopy(wanted)
            restored = Restore().visit(new)
            self.assertEqual(ast.dump(old, include_attributes=False), ast.dump(restored, include_attributes=False))

    def test_unknown_duplicate_import_ast_refused(self):
        for text in ('def f():\n pass', 'def f():\n from task import wrong',
                     'def f():\n from task import offsets\n from task import offsets'):
            with patch.object(a, 'function_ast', return_value=ast.parse(text).body[0]):
                with self.assertRaises(ValueError): a.import_only_ast(a.HANDOFF, 'f')

    def test_prior_function_and_shared_globals_unchanged(self):
        old = self.analyzer._height
        namespaces = [self.analyzer.__dict__, old.__globals__, old.__globals__['check_handoff'].__globals__]
        before = [{key:id(value) for key,value in n.items()} for n in namespaces]
        current = {name:sys.modules.get(name) for name in ('task','handoff','handoff_capture')}
        h, _ = a.bind_height(self.analyzer)
        self.assertIsNot(h.__globals__, old.__globals__)
        self.assertIsNot(h.__globals__['check_handoff'].__globals__, old.__globals__['check_handoff'].__globals__)
        self.assertEqual(before, [{key:id(value) for key,value in n.items()} for n in namespaces])
        for name, value in current.items(): self.assertIs(sys.modules.get(name), value)

    def test_height_and_handoff_share_same_explicit_offset_reference(self):
        h = self.height.__globals__
        f = h['check_handoff'].__globals__
        self.assertIs(h['offsets'], f['offsets'])
        self.assertEqual(Path(h['check_handoff'].__code__.co_filename), a.HANDOFF)
        self.assertFalse(self.binding['numerical_thresholds_changed'])
        self.assertTrue(self.binding['inverse_ast_identity'])

    def test_poisoned_task_handoff_and_capture_cannot_override(self):
        fake = types.ModuleType('poison')
        def poison(*args, **kwargs): raise AssertionError('generic dependency reached')
        fake.offsets = fake.check_handoff = fake.capture = poison
        with patch.dict(sys.modules, {key:fake for key in ('task','handoff','handoff_capture')}):
            height, _ = a.bind_height(self.analyzer)
            for function in (height, height.__globals__['check_handoff']):
                value = function.__globals__['offsets'](8, [24.])
                self.assertLess(value['p'][0,0], -.3)
            for key in ('task','handoff','handoff_capture'): self.assertIs(sys.modules[key], fake)

    def test_unique_helper_wrong_source_fails_closed(self):
        fake = types.ModuleType('v04_live_clock09')
        fake.replay = lambda *args: None
        with patch.dict(sys.modules, {'v04_live_clock09':fake}):
            with self.assertRaisesRegex(ValueError, 'dependency source'): a.bind_height(self.analyzer)

    def test_direct_symbol_wrong_name_or_path_rejected(self):
        with self.assertRaises(ValueError): a.attest(lambda:None, a.HANDOFF)
        with self.assertRaises(ValueError): a.attest(self.height, a.HEIGHT, 'wrong')

    def test_two_real_import_orders_in_fresh_processes(self):
        script = '''import adapter as a,sys,numpy as np
m=a.load_analyzer(sys.argv[1]); h,b=a.bind_height(m)
for f in (h,h.__globals__['check_handoff']):
 o=f.__globals__['offsets'](8,np.array([24.,40.]))
 assert o['p'].shape==(2,3) and o['p'][0,0]<-.3 and o['p'][0,2]<-.07
assert b['inverse_ast_identity'] and not b['numerical_thresholds_changed']
print('both nested references fixed; '+sys.argv[1])
'''
        for order in ('runner-first','analyzer-first'):
            result = subprocess.run([sys.executable,'-B','-c',script,order], cwd=a.HERE,
                env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'), capture_output=True,text=True)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_all_four_modes_have_complete_finite_n_by_three_shapes(self):
        for mode in (1,2,6,8):
            o = self.height.__globals__['offsets'](mode, [-1,0,8,24,40,64,70])
            for key in ('p','v','a'):
                self.assertEqual(o[key].shape, (7,3)); self.assertTrue(np.isfinite(o[key]).all())
            for key in ('yaw','yaw_rate'): self.assertEqual(o[key].shape,(7,))

    def test_mode_one_two_have_no_position_ff_addition(self):
        for mode in (1,2):
            o = self.height.__globals__['offsets'](mode,np.linspace(-1,92,1001))
            for value in o.values(): self.assertFalse(np.any(value))

    def test_mode_six_and_eight_same_xy_only_eight_has_z(self):
        t = np.linspace(-1,92,1001)
        h, v = [self.height.__globals__['offsets'](mode,t) for mode in (6,8)]
        for key in ('p','v','a'):
            np.testing.assert_array_equal(h[key][:,:2],v[key][:,:2])
            self.assertFalse(np.any(h[key][:,2])); self.assertTrue(np.any(v[key][:,2]))

    def test_independent_position_formula_and_finite_difference_derivatives(self):
        t = np.array([7.25,19.75,24.,40.,53.25]); dt=1e-3
        offsets=self.height.__globals__['offsets']
        middle=offsets(8,t); before=offsets(8,t-dt); after=offsets(8,t+dt)
        p=np.column_stack([amp*np.sin(np.pi*t/64)**4*np.sin(k*np.pi*t/16)
                          for amp,k in ((.5,1),(.25,2),(.1,1))])
        np.testing.assert_allclose(middle['p'],p,rtol=0,atol=1e-15)
        np.testing.assert_allclose((after['p']-before['p'])/(2*dt),middle['v'],rtol=0,atol=1e-8)
        np.testing.assert_allclose((after['p']-2*middle['p']+before['p'])/dt**2,middle['a'],rtol=0,atol=1e-8)

    def test_closed_task_boundaries_and_fixed_yaw(self):
        o = self.height.__globals__['offsets'](8,[-10.,0.,64.,100.])
        for value in o.values(): self.assertFalse(np.any(value))
        o = self.height.__globals__['offsets'](8,[8.,24.,40.])
        self.assertFalse(np.any(o['yaw'])); self.assertFalse(np.any(o['yaw_rate']))

    def test_invalid_modes_rejected(self):
        for mode in (True,1.,0,3,4,5,7,9,'8'):
            with self.assertRaises(ValueError): self.height.__globals__['offsets'](mode,[1.])

    def test_empty_nonvector_nonfinite_times_rejected(self):
        for t in ([],[[1.]], [float('nan')],[float('inf')]):
            with self.assertRaises(ValueError): self.height.__globals__['offsets'](8,t)

    def test_two_column_or_missing_reference_fields_rejected_not_padded(self):
        reference=self.height.__globals__['offsets']
        for key in ('p','v','a'):
            def bad(mode,t):
                o=reference(mode,t); o[key]=o[key][:,:2]; return o
            with self.assertRaises(ValueError): a.checked_offsets(bad,8,[1.])
        with self.assertRaises(ValueError): a.checked_offsets(lambda mode,t:{},8,[1.])

    def test_nonfinite_generated_fields_rejected(self):
        for key in ('p','v','a','yaw','yaw_rate'):
            def bad(mode,t):
                o=self.height.__globals__['offsets'](mode,t); o[key].flat[0]=np.nan; return o
            with self.assertRaises(ValueError): a.checked_offsets(bad,8,[1.])


class FullHandoffBody(unittest.TestCase):
    """Execute the entire unchanged handoff AST with synthetic upstream inputs.

Upstream capture/receiver fixtures are not proofs of their real-log correctness;
full historical CLI replay is separately required. The actual downstream loop,
windows, clocks, waveform correction and tolerance are never mocked.
"""
    @classmethod
    def setUpClass(cls):
        cls.height, _ = a.bind_height()

    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.run=Path(self.temporary.name)
        self.events=dict(takeoff_command=10_000_000,reposition_command=20_000_000,
            handoff_ready=21_000_000,hover_start=25_000_000,hover_end=115_000_000)
        self.frozen=dict(timestamp=11_000_000)
        w=dict(command=192,target_system=1,target_component=1,param1=-1.,param2=1.,param3=0.,param4=0.,z=10.)
        self.target=dict(source_timestamp=19_000_000,wire=w,xy_encoded=[0.,0.],lat=1.,lon=2.)
        self.command=dict(timestamp_us=20_000_000,message='COMMAND_INT',wire=w,maximum_sends=1,sent_monotonic=5.)
        for name,value in [('handoff_target',self.target),('reposition_command',self.command),
                           ('reposition_ack',dict(received_monotonic=6.)),('job',dict(parameters=dict(MPC_VCT_TEST=8)))]:
            (self.run/(name+'.json')).write_text(json.dumps(value))
        (self.run/'triplet_after.txt').write_text('synthetic')
        t=np.arange(22_000_000,115_000_000,10000,dtype=np.uint64)
        self.trajectory=dict(timestamp=t,x=np.zeros(len(t)),y=np.zeros(len(t)))
        excitation=(t.astype(float)-37_000_000)/1e6
        reference=self.height.__globals__['offsets'](8,excitation)
        self.diagnostic=dict(timestamp=t,excitation_time=excitation,
            **{'p_sp[0]':reference['p'][:,0].copy(),'p_sp[1]':reference['p'][:,1].copy()})
        self.status=dict(timestamp=np.array([21_000_000,114_990_000],dtype=np.uint64),nav_state=np.array([4,4]))
        self.trip=dict(timestamp=np.array([21_000_000,114_990_000],dtype=np.uint64),**{'current.valid':np.array([1,1])})
        expected=dict(w,param5=1.,param6=2.,param7=10.,source_system=255,source_component=190,from_external=1,confirmation=0)
        expected.pop('z')
        self.command_rows={key:np.array([value]) for key,value in dict(expected,timestamp=20_000_000).items()}
        self.ack_rows={key:np.array([value]) for key,value in dict(command=192,timestamp=20_500_000,result=0,
            target_system=255,target_component=190,from_external=0).items()}
        function=self.height.__globals__['check_handoff']
        self.function=a.clone(function, validate_receiver_profile=lambda:{'synthetic':True},
            capture=lambda *args,**kwargs:copy.deepcopy(self.target), receiver_target=lambda target:target,
            accepted_ack=lambda *args:True, triplet_data=lambda *args:(self.trip,{}),
            index=lambda d,t,*args:np.searchsorted(d['timestamp'],t,side='right')-1,
            matches_target=lambda d,target,**kwargs:d.get('valid')==1,
            decode_current=lambda raw:dict(valid=1),
            event_data=lambda u,name:self.command_rows if name=='vehicle_command' else self.ack_rows,
            data=lambda u,name:{'vehicle_status':self.status,'trajectory_setpoint':self.trajectory,
                                'sta_velocity_ctrl_status':self.diagnostic}[name])

    def call(self): return self.function(None,self.run,{},self.frozen,self.events)

    def test_mode_eight_real_nonzero_xy_reference_is_accepted(self):
        self.assertGreater(np.max(abs(self.diagnostic['p_sp[0]'])),.3)
        self.assertIn('receiver_expected',self.call())

    def test_mode_six_same_xy_is_accepted(self):
        (self.run/'job.json').write_text(json.dumps(dict(parameters=dict(MPC_VCT_TEST=6))))
        self.assertIn('receiver_expected',self.call())

    def test_mode_one_and_two_no_position_offsets(self):
        for mode in (1,2):
            (self.run/'job.json').write_text(json.dumps(dict(parameters=dict(MPC_VCT_TEST=mode))))
            self.diagnostic['p_sp[0]'][:]=0.;self.diagnostic['p_sp[1]'][:]=0.
            self.call()

    def test_old_mode_eight_zero_reference_reproduces_failure(self):
        original=self.function.__globals__['offsets']
        broken=lambda mode,t:original(1,t)
        f=a.clone(self.function,offsets=broken)
        with self.assertRaisesRegex(ValueError,'Downstream XY target differs'):
            f(None,self.run,{},self.frozen,self.events)

    def test_true_x_drift_not_hidden_by_fixed_reference(self):
        self.diagnostic['p_sp[0]'][2000]+=.050001
        with self.assertRaisesRegex(ValueError,'Downstream XY target differs'): self.call()

    def test_true_y_drift_not_hidden_by_fixed_reference(self):
        self.diagnostic['p_sp[1]'][2000]-=.050001
        with self.assertRaisesRegex(ValueError,'Downstream XY target differs'): self.call()

    def test_upstream_trajectory_drift_is_still_rejected(self):
        self.trajectory['x'][100]=.050001
        with self.assertRaisesRegex(ValueError,'Downstream XY target differs'): self.call()

    def test_original_five_centimetre_boundary_not_changed(self):
        self.trajectory['x'][:]=.05
        self.call()
        self.trajectory['x'][1]=np.nextafter(.05,np.inf)
        with self.assertRaisesRegex(ValueError,'Downstream XY target differs'): self.call()

    def test_nonfinite_diagnostic_is_rejected(self):
        self.diagnostic['p_sp[1]'][2000]=np.nan
        with self.assertRaisesRegex(ValueError,'Downstream XY target differs'): self.call()

    def test_waveform_wrong_phase_is_rejected(self):
        self.diagnostic['excitation_time']+=4.
        with self.assertRaisesRegex(ValueError,'Downstream XY target differs'): self.call()

    def test_unknown_task_is_explicitly_rejected(self):
        (self.run/'job.json').write_text(json.dumps(dict(parameters=dict(MPC_VCT_TEST=9))))
        with self.assertRaisesRegex(ValueError,'task modes'): self.call()

    def test_missing_window_edge_is_rejected(self):
        for key in self.diagnostic:self.diagnostic[key]=self.diagnostic[key][5:]
        with self.assertRaisesRegex(ValueError,'Missing downstream XY target window'): self.call()

    def test_internal_forty_ms_coverage_gate_is_retained(self):
        keep=np.ones(len(self.diagnostic['timestamp']),bool);keep[100:104]=False
        for key in self.diagnostic:self.diagnostic[key]=self.diagnostic[key][keep]
        with self.assertRaisesRegex(ValueError,'Missing downstream XY target window'): self.call()

    def test_raw_navigator_target_loss_is_not_skipped(self):
        self.trip['current.valid'][1]=0
        with self.assertRaisesRegex(ValueError,'Wrong/lost raw Navigator target'): self.call()

    def test_auto_loiter_loss_is_not_skipped(self):
        self.status['nav_state'][1]=2
        with self.assertRaisesRegex(ValueError,'Left AUTO_LOITER'): self.call()

    def test_duplicate_logged_command_is_not_skipped(self):
        for key in self.command_rows:self.command_rows[key]=np.repeat(self.command_rows[key],2)
        with self.assertRaisesRegex(ValueError,'Nonunique handoff command'): self.call()

    def test_rejected_logged_ack_is_not_skipped(self):
        self.ack_rows['result'][0]=1
        with self.assertRaisesRegex(ValueError,'Missing/duplicate/rejected logged ACK'): self.call()


class DiagnosticOnly(unittest.TestCase):
    def test_every_payload_forces_nonacceptance(self):
        for accepted in (True,False):
            out=a.diagnostic_payload(dict(accepted=accepted))
            self.assertEqual(out['diagnostic_checks_complete'],accepted)
            self.assertFalse(out['accepted']);self.assertFalse(out['flight_accepted'])
            self.assertFalse(out['execution_authority_granted']);self.assertEqual(out['new_flights'],0)

    def test_private_full_chain_wiring_and_every_saved_metric_nonaccepting(self):
        saved=[]
        def save(path,value):saved.append((Path(path).name,copy.deepcopy(value)))
        ns=dict(Path=Path,save=save)
        exec('def analyze(run,p,j):\n b=provenance(run,p,j)\n h=height_evidence()\n c=check_components()\n'
             ' r={"accepted":h=="fixed" and c=="numeric","binding":b}\n save(Path(run)/"r03_metrics.json",r)\n return r',ns)
        inherited=types.SimpleNamespace(analyze=ns['analyze'],save=save)
        analyzer=types.SimpleNamespace(_inherited=inherited,provenance=lambda *args:{'original':'checked'},
            prearm_evidence=lambda run:{'valid':True},_components=lambda:'numeric',_numeric_r02=object(),NUMERIC_BINDING={'same':True})
        before={k:id(v) for k,v in ns.items()}
        with patch.object(a,'copied_input_binding',return_value={'fixture.json':'sha'}):
            out=a.diagnostic_analyze(analyzer,lambda:'fixed',Path('/not_written'),{},{},{'fixed':True},source=Path('/original'))
        self.assertTrue(out['diagnostic_checks_complete']);self.assertFalse(out['accepted'])
        self.assertEqual(len(saved),2)
        self.assertTrue(all(value['accepted'] is False and value['new_flights']==0 for _,value in saved))
        self.assertEqual(before,{k:id(v) for k,v in ns.items()})

    def test_unsafe_or_existing_output_refused(self):
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'source';source.mkdir()
            for dest in (source,source/'nested',source.parent):
                with self.assertRaises(ValueError):a.copy_sidecars(source,dest)
            target=Path(root)/'existing';target.mkdir()
            with self.assertRaises(ValueError):a.copy_sidecars(source,target)

    def test_original_logs_not_copied_and_no_authorization_receipt_minted(self):
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'old';source.mkdir();target=Path(root)/'diagnostic'
            for name in ('gate_pass.json','authorization.json','r03_metrics.json','job.json','log.ulg'):
                (source/name).write_text('{}')
            a.copy_sidecars(source,target)
            self.assertEqual({p.name for p in target.iterdir()},{'job.json'})
            self.assertEqual(len(list(source.iterdir())),5)

    def test_early_diagnostic_error_cannot_leave_original_accepted_metric(self):
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'old';source.mkdir();target=Path(root)/'diagnostic'
            (source/'r03_metrics.json').write_text(json.dumps(dict(accepted=True)))
            a.copy_sidecars(source,target)
            with self.assertRaises(RuntimeError): raise RuntimeError('early provenance failure')
            self.assertFalse((target/'r03_metrics.json').exists())
            self.assertTrue(json.loads((source/'r03_metrics.json').read_text())['accepted'])

    def test_new_output_inside_any_actual_batch_refused(self):
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'old';source.mkdir()
            with self.assertRaises(ValueError):a.copy_sidecars(source,Path(root)/'batch01'/'new_run')

    def test_retained_a_uses_original_analysis_and_keeps_job_revision(self):
        analyzer=types.SimpleNamespace(_protocol=lambda:types.SimpleNamespace(retained_a=lambda:{'root':'/retained/A'}))
        job=dict(revision='r03_revision04',gate='A',id='run001'); before=copy.deepcopy(job)
        original=object()
        with patch.object(a,'load_path',return_value=original) as load:
            self.assertIs(a.original_analysis(analyzer,job,Path('/retained/A/batch01/run001')),original)
            self.assertEqual(load.call_args.args[1],a.RETAINED/'analyzer.py')
        self.assertEqual(job,before)

    def test_retained_a_wrong_archive_and_other_old_gate_refused(self):
        analyzer=types.SimpleNamespace(_protocol=lambda:types.SimpleNamespace(retained_a=lambda:{'root':'/retained/A'}))
        for job,path in [(dict(revision='r03_revision04',gate='A',id='run001'),'/wrong/run001'),
                         (dict(revision='r03_revision04',gate='B',id='run010'),'/retained/B/batch01/run010'),
                         (dict(revision='r03_revision03',gate='A',id='run001'),'/old/run001')]:
            with self.assertRaises(ValueError):a.original_analysis(analyzer,job,Path(path))

    def test_current_revision_uses_its_own_analyzer(self):
        analyzer=object()
        self.assertIs(a.original_analysis(analyzer,dict(revision='r03_revision05'),Path('/not_read')),analyzer)

    def test_copy_binding_rejects_changed_missing_or_added_sidecar(self):
        for mutation in ('changed','missing','extra'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as root:
                source=Path(root)/'source';source.mkdir();dest=Path(root)/'diagnostic'
                (source/'job.json').write_text('{}');a.copy_sidecars(source,dest)
                self.assertEqual(a.copied_input_binding(source,dest),{'job.json':a.digest(source/'job.json')})
                if mutation=='changed':(dest/'job.json').write_text('{"bad":1}')
                elif mutation=='missing':(dest/'job.json').unlink()
                else:(dest/'authorization.json').write_text('{"approved":true}')
                with self.assertRaisesRegex(ValueError,'sidecar copy differs'):a.copied_input_binding(source,dest)

    def test_real_frozen_provenance_reads_original_authorization_not_output(self):
        # Execute the real frozen provenance body. Only upstream protocol/manifest
        # lookup helpers are fixture-bound; receipt/source/restore checks stay real.
        original=a.load_analyzer('analyzer-first')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'original';source.mkdir();dest=root/'diagnostic'
            config=root/'config';config.mkdir();(config/'frozen.json').write_text('{}')
            execution=root/'execution.json';execution.write_text('{}')
            auth=root/'AUTH.md';auth.write_text('historical fixture authority')
            qualification=root/'qualification.json'
            budget=dict(maximum_attempts=9,new_matrix_attempts=27,historical_attempts=30,total_maximum_attempts=57)
            protocol=dict(config_dir=str(config),execution_path=str(execution),qualification_path=str(qualification),stage='R03-revision05-B')
            job=dict(revision='r03_revision05',gate='B',id='run010')
            helpers=types.SimpleNamespace(require_execution_authority=lambda gate:None,retained_failure=lambda:{'history':'fixture'},
                retained_a=lambda:{'retained':'fixture'},seed_migration=lambda:{'migration':'none'},AUTHORIZATION=auth)
            qualified=dict(success=True,clean=True,revision='r03_revision05',stage=protocol['stage'],gate='B',new_flights=0,
                source_head='source',firmware_sha256='firmware',execution_sha256=a.digest(execution),frozen_sha256=a.digest(config/'frozen.json'),
                historical_budget=helpers.retained_failure(),retained_a=helpers.retained_a(),seed_migration=helpers.seed_migration(),
                execution_authorized=True,flight_authorized=True,execution_ready=True,**budget)
            qualification.write_text(json.dumps(qualified))
            approval={key:value for key,value in qualified.items() if key not in ('success','clean','new_flights')}
            approval.update(approved=True,qualification_sha256=a.digest(qualification),authorization_sha256=a.digest(auth))
            record=dict(source_head='source',binary_sha256='firmware',scenario_sha256=a.digest(execution),scenario_path=str(execution))
            (source/'original_parameters.bson').write_bytes(b'parameters')
            restore=dict(parameter_restore_exact=True,remaining_simulators=[],stopped_before_restore=True,source_head='source',gate='B',job_id='run010',
                original_parameter_sha256=a.digest(source/'original_parameters.bson'),restored_parameter_sha256=a.digest(source/'original_parameters.bson'))
            for name,value in [('authorization',approval),('result',record),('run_protocol',protocol),('job',job),('parameter_restore',restore),
                               ('qualification_reference',dict(path=str(qualification),sha256=a.digest(qualification)))]:
                (source/(name+'.json')).write_text(json.dumps(value))
            real_provenance=a.clone(original.provenance,_protocol_identity=lambda p,j:None,_protocol=lambda:helpers,
                _archive_scope=lambda run,p,j:json.loads((Path(run)/'result.json').read_text()),_budget=lambda:budget)
            self.assertEqual(real_provenance(source,protocol,job)['source_head'],'source')
            a.copy_sidecars(source,dest)
            self.assertFalse((dest/'authorization.json').exists())
            with self.assertRaises(FileNotFoundError):real_provenance(dest,protocol,job)
            called=[];saved=[]
            def provenance(path,p,j):
                called.append(Path(path));return real_provenance(path,p,j)
            def save(path,value):saved.append(value)
            ns={'Path':Path,'save':save}
            exec('def analyze(run,p,j):\n b=provenance(run,p,j)\n r={"accepted":True,"binding":b}\n save(Path(run)/"r03_metrics.json",r)\n return r',ns)
            fixture=types.SimpleNamespace(_inherited=types.SimpleNamespace(analyze=ns['analyze'],save=save),provenance=provenance,
                prearm_evidence=lambda path:{'valid':Path(path)==source},_components=None,_numeric_r02=None,NUMERIC_BINDING={})
            out=a.diagnostic_analyze(fixture,lambda:None,dest,protocol,job,{},source=source)
            self.assertEqual(called,[source]);self.assertTrue(out['diagnostic_checks_complete']);self.assertFalse(out['accepted'])
            self.assertTrue(out['prearm_preparation']['valid']);self.assertFalse((dest/'authorization.json').exists())
            approval['approved']=False;(source/'authorization.json').write_text(json.dumps(approval))
            with self.assertRaisesRegex(ValueError,'qualification/authorization'):
                a.diagnostic_analyze(fixture,lambda:None,dest,protocol,job,{},source=source)


if __name__ == '__main__': unittest.main(verbosity=2)
