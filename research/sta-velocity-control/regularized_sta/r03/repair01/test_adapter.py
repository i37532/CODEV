"""Offline import collision and unchanged-height regression; no flight access."""
import ast
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
import adapter as a


class Binding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analyzer = a.load_analyzer('analyzer-first')
        cls.height, cls.report = a.bind_height(cls.analyzer)
        cls.reference = staticmethod(a.load_path('r03_repair01_test_reference', a.TASK).offsets)

    def test_ast_only_import_changes(self):
        old, new, index = a.height_ast()
        self.assertIsInstance(new.body[index], ast.Pass)
        new.body[index] = copy.deepcopy(old.body[index])
        self.assertEqual(ast.dump(old, include_attributes=False), ast.dump(new, include_attributes=False))
        self.assertFalse(self.report['numerical_thresholds_changed'])

    def test_sources_still_pinned(self):
        self.assertEqual(len(a.pinned_inputs()), 4)

    def test_private_globals_and_old_function_unchanged(self):
        original = self.analyzer.height_evidence
        keys = {k:id(v) for k,v in original.__globals__.items()}
        current_task = sys.modules.get('task')
        fixed, _ = a.bind_height(self.analyzer)
        self.assertIs(self.analyzer.height_evidence, original)
        self.assertIsNot(fixed.__globals__, original.__globals__)
        self.assertEqual(keys, {k:id(v) for k,v in original.__globals__.items()})
        self.assertIs(sys.modules.get('task'), current_task)

    def test_two_real_import_orders_in_fresh_processes(self):
        for order in ('runner-first', 'analyzer-first'):
            with self.subTest(order=order):
                script = """import adapter as a,numpy as np,sys
m=a.load_analyzer(sys.argv[1]);f,_=a.bind_height(m)
v=f.__globals__['offsets'](8,np.array([7.,13.,23.,39.,55.]))
assert v['p'].shape==(5,3) and np.max(abs(v['p'][:,2]))>.01
assert f.__globals__ is not m.height_evidence.__globals__
print('explicit Nx3; order='+sys.argv[1])
"""
                env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
                p = subprocess.run([sys.executable, '-c', script, order], cwd=a.HERE,
                                   env=env, text=True, capture_output=True)
                self.assertEqual(p.returncode, 0, p.stdout+p.stderr)

    def test_fake_two_column_task_cannot_override(self):
        fake = types.ModuleType('task')
        fake.offsets = lambda mode,t: dict(p=np.ones((len(t),2)))
        with patch.dict(sys.modules, {'task':fake}):
            fixed, _ = a.bind_height(self.analyzer)
            self.assertEqual(fixed.__globals__['offsets'](1,np.array([0.,1.]))['p'].shape,(2,3))
            self.assertIs(sys.modules['task'], fake)

    def test_fake_raising_task_cannot_override(self):
        fake = types.ModuleType('task')
        def fail(*args): raise AssertionError('Wrong generic task called')
        fake.offsets = fail
        with patch.dict(sys.modules, {'task':fake}):
            fixed, _ = a.bind_height(self.analyzer)
            self.assertTrue(np.any(fixed.__globals__['offsets'](8,np.array([11.,21.]))['p'][:,2]))

    def test_a_b_c_have_zero_z_position_offset(self):
        t = np.linspace(-5,92,1000)
        for mode in (1,2,6):
            result = a.checked_offsets(self.reference,mode,t)
            for key in ('p','v','a'):
                np.testing.assert_array_equal(result[key][:,2],np.zeros(len(t)))

    def test_d_has_true_z_not_padding(self):
        t = np.array([-1.,0.,7.,13.,23.,39.,55.,64.,70.])
        result = a.checked_offsets(self.reference,8,t)
        u=np.where((t>0)&(t<64),t,0.)
        expected=.1*np.sin(np.pi*u/64)**4*np.sin(2*np.pi*u/32)
        np.testing.assert_allclose(result['p'][:,2],expected,rtol=0,atol=1e-16)
        self.assertGreater(np.max(abs(result['p'][:,2])),.03)

    def test_explicit_reference_matches_every_field(self):
        t=np.linspace(-5,92,1000)
        for mode in (1,2,6,8):
            one=self.reference(mode,t);two=a.checked_offsets(self.reference,mode,t)
            for field in one:np.testing.assert_array_equal(one[field],two[field])

    def test_invalid_mode_rejected(self):
        for mode in (0,3,5,7,9,True,1.0):
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                a.checked_offsets(self.reference,mode,np.array([1.]))

    def test_nan_inf_empty_or_nonvector_time_rejected(self):
        for times in ([np.nan],[np.inf],[],[[1.,2.]]):
            with self.subTest(times=times),self.assertRaises(ValueError):
                a.checked_offsets(self.reference,1,times)

    def test_two_column_reference_rejected_not_padded(self):
        def bad(mode,t):
            result=self.reference(mode,t);result['p']=result['p'][:,:2];return result
        with self.assertRaisesRegex(ValueError,'Malformed'):
            a.checked_offsets(bad,1,[1.,2.])

    def test_nonfinite_generated_reference_rejected(self):
        for field in ('p','v','a','yaw','yaw_rate'):
            def bad(mode,t):
                result=self.reference(mode,t);result[field].flat[0]=np.nan;return result
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'nonfinite'):
                a.checked_offsets(bad,8,[1.,2.])

    def test_reference_wrong_schema_rejected(self):
        def bad(mode,t):
            result=self.reference(mode,t);result['extra']=0.;return result
        with self.assertRaisesRegex(ValueError,'schema'):
            a.checked_offsets(bad,1,[1.])

    def test_payload_cannot_authorize(self):
        for accepted in (False,True):
            result=a.diagnostic_payload({'accepted':accepted,'error':'fixture'})
            self.assertFalse(result['accepted']);self.assertFalse(result['flight_accepted'])
            self.assertTrue(result['diagnostic_only']);self.assertTrue(result['historical_acceptance_unchanged'])
            self.assertEqual(result['diagnostic_checks_complete'],accepted)
            self.assertEqual(result['new_flights'],0)

    def test_analyzer_code_cloned_and_save_marked_private(self):
        saved=[]
        def save(path,value):saved.append((path,value))
        def height_evidence():return 'old'
        namespace={'save':save,'height_evidence':height_evidence,'Path':Path}
        # The fixture must use globals, like the real top-level analyzer.
        exec("def analyze(run,protocol,job):\n v={'accepted':height_evidence()=='new'}\n save(Path(run)/'r03_metrics.json',v)\n return v",namespace)
        module=types.SimpleNamespace(analyze=namespace['analyze'])
        before={k:id(v) for k,v in namespace.items()}
        result=a.diagnostic_analyze(module,lambda:'new',Path('/not_written'),{}, {})
        self.assertTrue(result['diagnostic_checks_complete']);self.assertFalse(result['accepted'])
        self.assertFalse(saved[0][1]['accepted']);self.assertTrue(saved[0][1]['diagnostic_only'])
        self.assertEqual(before,{k:id(v) for k,v in namespace.items()})

    def test_output_cannot_be_original_descendant_or_ancestor(self):
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'old';source.mkdir()
            for dest in (source,source/'child',source.parent):
                with self.subTest(dest=dest),self.assertRaises(ValueError):a.copy_sidecars(source,dest)

    def test_sidecars_new_directory_preserves_raw_archive_paths(self):
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'old';source.mkdir();dest=Path(root)/'new'
            raw=source/'log.ulg';raw.write_bytes(b'raw')
            record={'logs':[{'archive':str(raw)}]}
            (source/'result.json').write_text(json.dumps(record))
            before=a.snapshot(source);a.copy_sidecars(source,dest)
            self.assertEqual(json.loads((dest/'result.json').read_text()),record)
            self.assertFalse((dest/'log.ulg').exists());self.assertEqual(before,a.snapshot(source))
            with self.assertRaises(FileExistsError):a.copy_sidecars(source,dest)

    def height_fixture(self,root,mode=1):
        """Synthetic only: heading/handoff stubs leave all height checks intact."""
        original=self.height
        namespace=dict(original.__globals__)
        namespace.update(replay=lambda *args,**kwargs:{'fixture':'heading'},
                         check_handoff=lambda *args,**kwargs:{'fixture':'handoff'})
        fn=types.FunctionType(original.__code__,namespace)
        fn.__kwdefaults__=original.__kwdefaults__
        t=np.arange(6000000,106000001,10000,dtype=np.int64);n=len(t)
        position={key:np.zeros(n) for key in namespace['REFERENCE']}
        position.update(timestamp=t.copy(),z=np.full(n,-2.5),vz=np.zeros(n))
        for key in ('xy_valid','z_valid','v_xy_valid','v_z_valid'):position[key]=np.ones(n)
        status=dict(timestamp=t.copy(),arming_state=np.full(n,2),nav_state=np.full(n,4),failsafe=np.zeros(n))
        land=dict(timestamp=t.copy(),landed=np.zeros(n),ground_contact=np.zeros(n))
        trajectory=dict(timestamp=t.copy(),z=np.full(n,-2.5),vz=np.zeros(n),yaw=np.zeros(n))
        datasets=dict(vehicle_local_position=position,vehicle_status=status,vehicle_land_detected=land,
                      trajectory_setpoint=trajectory)
        u=types.SimpleNamespace(get_dataset=lambda name:types.SimpleNamespace(data=datasets[name]))
        excitation=t.astype(float)*1e-6-16
        dz=self.reference(mode,excitation)['p'][:,2]
        d={'timestamp':t.copy(),'timestamp_sample':t.copy(),'excitation_time':excitation,'p_sp[2]':-2.5+dz}
        events=dict(takeoff_command=6000000,reposition_command=8000000,hover_start=10000000,
                    hover_end=101000000,landed_disarmed=106000000)
        ref=dict(position={key:0. for key in namespace['REFERENCE']},target_z=-2.5)
        ref['position']['z']=0.
        (root/'height_reference.json').write_text(json.dumps(ref))
        (root/'task_yaw.json').write_text(json.dumps(dict(timestamp=7000000,yaw=0.)))
        (root/'job.json').write_text(json.dumps(dict(parameters={'MPC_VCT_TEST':mode})))
        return fn,u,d,events,datasets

    def test_full_height_a_b_c_d_positive_synthetic(self):
        for mode in (1,2,6,8):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as root:
                fn,u,d,events,_=self.height_fixture(Path(root),mode)
                result=fn(u,Path(root),d,events,attitude_policy=object())
                self.assertEqual(result['entry_samples'],301)
                self.assertAlmostEqual(result['ready_after_gate_s'],6.)

    def test_full_height_wrong_consumed_target_rejected(self):
        for mode in (1,2,6,8):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as root:
                fn,u,d,events,_=self.height_fixture(Path(root),mode)
                d['p_sp[2]'][1000]+=.051
                with self.assertRaisesRegex(ValueError,'Wrong consumed height'):
                    fn(u,Path(root),d,events,attitude_policy=object())

    def test_full_height_nan_consumed_target_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            fn,u,d,events,_=self.height_fixture(Path(root))
            d['p_sp[2]'][1000]=np.nan
            with self.assertRaisesRegex(ValueError,'Wrong consumed height'):
                fn(u,Path(root),d,events,attitude_policy=object())

    def test_full_height_d_missing_vertical_wave_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            fn,u,d,events,_=self.height_fixture(Path(root),8)
            d['p_sp[2]'][:]=-2.5
            with self.assertRaisesRegex(ValueError,'Wrong consumed height'):
                fn(u,Path(root),d,events,attitude_policy=object())

    def test_full_height_entry_boundary_and_reference_reset_unchanged(self):
        for failure in ('height','speed','reset','clock','validity','entry_trajectory'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as root:
                fn,u,d,events,sets=self.height_fixture(Path(root))
                pos=sets['vehicle_local_position'];i=200
                if failure=='height':pos['z'][i]=-3.001
                if failure=='speed':pos['vz'][i]=.2
                if failure=='reset':pos['z_reset_counter'][i]=1
                if failure=='clock':pos['timestamp'][i]=pos['timestamp'][i-1]
                if failure=='validity':pos['z_valid'][i]=0
                if failure=='entry_trajectory':sets['trajectory_setpoint']['z'][i]+=.051
                with self.assertRaises(ValueError):fn(u,Path(root),d,events,attitude_policy=object())

    def test_full_height_bad_excitation_clock_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            fn,u,d,events,_=self.height_fixture(Path(root))
            d['timestamp_sample'][1200]+=11
            with self.assertRaisesRegex(ValueError,'Excitation clock'):
                fn(u,Path(root),d,events,attitude_policy=object())

    def test_full_height_heading_handoff_faults_not_swallowed(self):
        for field in ('replay','check_handoff'):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as root:
                fn,u,d,events,_=self.height_fixture(Path(root))
                def fail(*args,**kwargs):raise ValueError('Retained helper rejection')
                fn.__globals__[field]=fail
                with self.assertRaisesRegex(ValueError,'Retained helper rejection'):
                    fn(u,Path(root),d,events,attitude_policy=object())


if __name__=='__main__':unittest.main(verbosity=2)
