#!/usr/bin/env python3
"""Offline runner tests; never starts PX4/Gazebo or changes real parameters."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('quick_hover_runner', HERE/'run_hover.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def manifest(root='/tmp/not_executed'):
    job = dict(id='S001', label='STA2', repo='/tmp/source', bin='/tmp/source/bin', rootfs='/tmp/source/rootfs',
        launch_command=['make', 'gazebo'], launch_env={}, parameters={'MIS_TAKEOFF_ALT': 2.5, 'SDLOG_MODE': 1},
        expected_parameters={'MIS_TAKEOFF_ALT': 2.5, 'SDLOG_MODE': 1}, firmware_sha256='f'*64, source_head='a'*40)
    jobs = [dict(job, id='S00%d' % i, label=label) for i, label in enumerate(('STA2', 'RSTA', 'RISTA'), 1)]
    return dict(max_attempts=3, hover_s=10, takeoff_alt_m=2.5, jobs=jobs,
                order=[j['id'] for j in jobs], data_root=root)


def position():
    return dict(x=0., y=0., z=-2.5, vx=0., vy=0., vz=0.,
                xy_valid=True, z_valid=True, v_xy_valid=True, v_z_valid=True)


class ParserTests(unittest.TestCase):
    def test_diagnostic_na_preserved_without_zero_or_nonstandard_json(self):
        data = {'mode':3, 'unused':[float('nan'), float('inf'),-float('inf')], 'active':.2}
        value = r.diagnostic_json(data)
        self.assertEqual(value, {'mode':3,'unused':['NaN','+Inf','-Inf'],'active':.2})
        json.dumps(value, allow_nan=False)
        self.assertTrue(r.math.isnan(data['unused'][0]))

    def test_bad_required_parameter_remains_rejected(self):
        with self.assertRaises(ValueError): r.check_parameters({'GAIN':float('nan')},{'GAIN':1.})

    def test_initial_topics_must_all_publish(self):
        self.assertFalse(r.native_topics_ready({'position':{'timestamp':12},'attitude':{}}))
        self.assertTrue(r.native_topics_ready({'position':{'timestamp':12},'attitude':{'timestamp':11}}))

    def test_initial_zero_nan_and_empty_rejected(self):
        for value in (0., float('nan'), -1.):
            self.assertFalse(r.native_topics_ready({'attitude':{'timestamp':value}}))
        self.assertFalse(r.native_topics_ready({}))

    def test_hold_target_preserves_ground_relative_height(self):
        p = dict(ref_lat=47., ref_lon=8., ref_alt=500., x=0., y=0., z=-.4)
        self.assertEqual(r.hold_target(p), dict(latitude_e7=470000000, longitude_e7=80000000, altitude_m=502.9))

    def test_hold_target_north_east_direction(self):
        target = r.hold_target(dict(ref_lat=47.,ref_lon=8.,ref_alt=500.,x=1.,y=1.,z=0.))
        self.assertGreater(target['latitude_e7'], 470000000)
        self.assertGreater(target['longitude_e7'], 80000000)

    def test_hold_target_invalid_reference_rejected(self):
        with self.assertRaises(ValueError): r.hold_target(dict(ref_lat=float('nan')))

    def test_scalars_arrays(self):
        parsed = r.parse_topic('vehicle_attitude\n    timestamp: 12345\n    q: [1.0, 0, 0, 0]\n    valid: True\n    x: -0.25\n')
        self.assertEqual(parsed, dict(timestamp=12345., q=[1., 0., 0., 0.], valid=True, x=-.25))

    def test_parameters_symbols(self):
        text = 'x + MPC_VC_MODE [459,761] : 3\n    MPC_Z_P [4,5] : 1.0000\nx * MPC_XY_P [2,3] : 0.9500\n'
        self.assertEqual(r.parse_parameters(text), {'MPC_VC_MODE': 3, 'MPC_Z_P': 1, 'MPC_XY_P': .95})

    def test_float_display_precision(self):
        r.check_parameters({'GAIN': .5280}, {'GAIN': .528})

    def test_parameter_missing(self):
        with self.assertRaises(ValueError):
            r.check_parameters({}, {'MODE': 3})

    def test_parameter_wrong_mode(self):
        with self.assertRaises(ValueError):
            r.check_parameters({'MODE': 4}, {'MODE': 3})


class ScopeTests(unittest.TestCase):
    def addition(self):
        m = manifest()
        p = dict(MIS_TAKEOFF_ALT=2.5, SDLOG_MODE=1, MPC_VC_MODE=0, MPC_VC_AXES=0,
            MPC_VC_DIV=1, MC_RTC_MODE=0, MC_STA_AXES=0, MC_RTC_DIV=1, MC_RATT_TEST=0)
        m['jobs'].append(dict(m['jobs'][0], id='S304', label='PID', parameters=p, expected_parameters=dict(p)))
        m.update(max_attempts=4, order=[j['id'] for j in m['jobs']],
            pid_addition=dict(new_attempts=1, preserved_results={j['id']:'a'*64 for j in m['jobs'][:3]}))
        return m

    def test_only_one_pid_addition(self):
        self.assertEqual(r.validate_manifest(self.addition(), 'S304')['label'], 'PID')

    def test_addition_cannot_reexecute_original(self):
        with self.assertRaises(ValueError): r.validate_manifest(self.addition(), 'S001')

    def test_addition_cannot_increase_budget(self):
        m = self.addition(); m['pid_addition']['new_attempts'] = 2
        with self.assertRaises(ValueError): r.validate_manifest(m, 'S304')

    def test_addition_requires_actual_pid(self):
        m = self.addition(); m['jobs'][-1]['parameters']['MPC_VC_MODE'] = 3
        with self.assertRaises(ValueError): r.validate_manifest(m, 'S304')

    def test_addition_requires_all_preserved_receipts(self):
        m = self.addition(); del m['pid_addition']['preserved_results']['S001']
        with self.assertRaises(ValueError): r.validate_manifest(m, 'S304')

    def test_preserved_receipt_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.addition(); m['data_root'] = tmp
            for j in m['jobs'][:3]:
                p = Path(tmp)/'runs'/j['id']/'result.json'; p.parent.mkdir(parents=True)
                p.write_text('{"success":true}')
                m['pid_addition']['preserved_results'][j['id']] = r.digest(p)
            r.check_order(m, 'S304')
            p.write_text('{"success":true,"modified":true}')
            with self.assertRaises(ValueError): r.check_order(m, 'S304')

    def test_valid(self):
        self.assertEqual(r.validate_manifest(manifest(), 'S001')['label'], 'STA2')

    def test_extra_budget(self):
        m = manifest(); m['max_attempts'] = 4
        with self.assertRaises(ValueError): r.validate_manifest(m, 'S001')

    def test_reject_task9(self):
        m = manifest(); m['jobs'][0]['parameters']['MPC_VCT_TEST'] = 9
        with self.assertRaises(ValueError): r.validate_manifest(m, 'S001')

    def test_no_logging(self):
        m = manifest(); m['jobs'][0]['parameters']['SDLOG_MODE'] = 0
        with self.assertRaises(ValueError): r.validate_manifest(m, 'S001')

    def test_duplicate_order(self):
        m = manifest(); m['order'][1] = 'S001'
        with self.assertRaises(ValueError): r.validate_manifest(m, 'S001')

    def test_unsafe_id(self):
        m = manifest(); m['jobs'][0]['id'] = '../x'; m['order'][0] = '../x'
        with self.assertRaises(ValueError): r.validate_manifest(m, '../x')

    def test_finite_parameter(self):
        m = manifest(); m['jobs'][0]['parameters']['GAIN'] = float('nan')
        with self.assertRaises(ValueError): r.validate_manifest(m, 'S001')

    def test_prior_failure_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = manifest(tmp)
            p = Path(tmp)/'runs/S001'; p.mkdir(parents=True)
            (p/'result.json').write_text('{"success":false}')
            with self.assertRaises(ValueError): r.check_order(m, 'S002')

    def test_previous_success_and_reexecution_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = manifest(tmp)
            r.check_order(m, 'S001')
            p = Path(tmp)/'runs/S001'; p.mkdir(parents=True)
            (p/'result.json').write_text('{"success":true}')
            with self.assertRaises(ValueError): r.check_order(m, 'S001')
            r.check_order(m, 'S002')

    def test_missing_previous_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError): r.check_order(manifest(tmp), 'S002')


class SafetyTests(unittest.TestCase):
    def check(self, p, phase='hover'):
        return r.check_envelope(p, {'q': [1, 0, 0, 0]}, {'x': 0, 'y': 0, 'z': 0}, phase)

    def test_nominal(self):
        self.assertEqual(self.check(position()), 2.5)

    def test_hover_height_boundary(self):
        p = position(); p['z'] = -3.5; self.check(p)
        p['z'] = -3.50001
        with self.assertRaises(ValueError): self.check(p)

    def test_hover_vertical_speed_boundary(self):
        p = position(); p['vz'] = .6; self.check(p)
        p['vz'] = .60001
        with self.assertRaises(ValueError): self.check(p)

    def test_xy_norm(self):
        p = position(); p['vx'] = .8; p['vy'] = .8
        with self.assertRaises(ValueError): self.check(p)

    def test_invalid_estimate(self):
        p = position(); p['z_valid'] = False
        with self.assertRaises(ValueError): self.check(p)

    def test_nan(self):
        p = position(); p['vz'] = float('nan')
        with self.assertRaises(ValueError): self.check(p)

    def test_nonunit_quaternion(self):
        with self.assertRaises(ValueError): r.tilt([2, 0, 0, 0])

    def test_entry_height_and_ground(self):
        state = dict(position=position(), status=dict(nav_state=4, arming_state=2, failsafe=False), land=dict(landed=False))
        self.assertTrue(r.entry_ok(state, {'z': 0}))
        state['position']['z'] = -1.8
        self.assertFalse(r.entry_ok(state, {'z': 0}))
        state['position']['z'] = -2.5; state['land']['landed'] = True
        self.assertFalse(r.entry_ok(state, {'z': 0}))


class RestoreTests(unittest.TestCase):
    def test_old_and_new_parameter_layouts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'rootfs'; out = Path(tmp)/'out'
            (root/'eeprom').mkdir(parents=True); out.mkdir()
            (root/'eeprom/parameters_10016').write_bytes(b'old baseline')
            (root/'parameters.bson').write_bytes(b'old upstream')
            (root/'log').mkdir(); (root/'log/parameters.bson').write_bytes(b'untouched log')
            snap = r.snapshot_parameters(root, out)
            (root/'eeprom/parameters_10016').write_bytes(b'changed')
            (root/'parameters.bson').write_bytes(b'changed')
            (root/'parameters_backup.bson').write_bytes(b'new')
            receipt = r.restore_parameters(root, snap)
            self.assertTrue(receipt['parameter_restore_exact'])
            self.assertEqual((root/'eeprom/parameters_10016').read_bytes(), b'old baseline')
            self.assertEqual((root/'parameters.bson').read_bytes(), b'old upstream')
            self.assertFalse((root/'parameters_backup.bson').exists())
            self.assertEqual((root/'log/parameters.bson').read_bytes(), b'untouched log')

    def test_first_start_new_rootfs_restores_absence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'rootfs'; out = Path(tmp)/'out'; out.mkdir()
            snap = r.snapshot_parameters(root, out)
            root.mkdir(); (root/'parameters.bson').write_bytes(b'created')
            r.restore_parameters(root, snap)
            self.assertFalse((root/'parameters.bson').exists())

    def test_symlink_parameter_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'rootfs'; out = Path(tmp)/'out'; root.mkdir(); out.mkdir()
            outside = Path(tmp)/'important'; outside.write_bytes(b'original')
            (root/'parameters.bson').symlink_to(outside)
            with self.assertRaises(ValueError): r.snapshot_parameters(root, out)
            self.assertEqual(outside.read_bytes(), b'original')


if __name__ == '__main__':
    unittest.main()
