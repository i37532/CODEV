"""Synthetic offline fixtures; none is a vehicle experiment or a flight result."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import plot_results as p


def events(task):
    result = [dict(name='climb_start', timestamp_us=1000000, generation=2),
              dict(name='takeoff_command', timestamp_us=900000),
              dict(name='control_change', timestamp_us=1500000, generation=3, enabled=True)]
    if task == 'position':
        result += [dict(name='step_up_start', timestamp_us=3000000, generation=6),
                   dict(name='step_up_end', timestamp_us=11000000, generation=6),
                   dict(name='step_down_start', timestamp_us=11000000, generation=7),
                   dict(name='step_down_end', timestamp_us=19000000, generation=7)]
    else:
        result += [dict(name='velocity_start', timestamp_us=3000000, generation=6),
                   dict(name='velocity_end', timestamp_us=15000000, generation=6)]
    result += [dict(name='landed_disarmed', timestamp_us=22000000, generation=12)]
    return result


def native_fixture(task='position', array=False):
    t = np.arange(500000, 22200000, 100000, dtype=np.int64)
    z = np.full(len(t), -2.5)
    vz = np.zeros(len(t))
    if task == 'position':
        # Actual moves after a 50 ms native-receipt delay; no interpolation.
        z[(t >= 3100000) & (t < 11100000)] = -2.8
    else:
        vz[(t >= 3100000) & (t < 5100000)] = -.2
        vz[(t >= 9100000) & (t < 11100000)] = .2
    local = dict(timestamp=t + 30000, timestamp_sample=t,
                 x=np.ones(len(t)), y=np.full(len(t), 2.), z=z,
                 vx=np.zeros(len(t)), vy=np.zeros(len(t)), vz=vz)
    tt = np.arange(500000, 22200000, 50000, dtype=np.int64)
    zz = np.full(len(tt), -2.5)
    vv = np.full(len(tt), np.nan)
    if task == 'position':
        zz[(tt >= 3050000) & (tt < 11050000)] = -2.8
    else:
        active = (tt >= 3050000) & (tt < 15050000)
        zz[active] = np.nan
        vv[active] = 0.
        vv[(tt >= 3050000) & (tt < 5050000)] = -.2
        vv[(tt >= 9050000) & (tt < 11050000)] = .2
    trajectory = dict(timestamp=tt, z=zz, vz=vv)
    if array:
        trajectory['position[2]'] = trajectory.pop('z')
        trajectory['velocity[2]'] = trajectory.pop('vz')
    return SimpleNamespace(data_list=[
        SimpleNamespace(name='vehicle_local_position', multi_id=0, data=local),
        SimpleNamespace(name='trajectory_setpoint', multi_id=0, data=trajectory)],
        file_corruption=False, dropouts=[])


class ResponseTests(unittest.TestCase):
    def metrics(self, actual, end=4000000, target=1.):
        times = np.arange(900000, 4100000, 100000, dtype=np.int64)
        return p.response_metrics(times, actual(times), 1000000, end, target)

    def test_first_crossings_have_exact_native_brackets(self):
        result = self.metrics(lambda t: np.clip((t - 1000000) / 1000000, 0., 1.))
        self.assertEqual(result['baseline_sample_us'], 900000)
        self.assertEqual(result['crossing_10']['sample_bracket_us'], [1000000, 1100000])
        self.assertEqual(result['crossing_90']['sample_bracket_us'], [1800000, 1900000])
        self.assertAlmostEqual(result['rise_10_90_s'], .8)
        self.assertAlmostEqual(result['settling_5pct_s'], 1.)
        self.assertEqual(result['overshoot_percent'], 0.)

    def test_negative_step_uses_measured_baseline_and_requested_target(self):
        result = self.metrics(lambda t: 4. - 2. * np.clip((t - 1000000) / 1000000, 0., 1.), target=2.)
        self.assertEqual(result['baseline'], 4.)
        self.assertAlmostEqual(result['threshold_10'], 3.8)
        self.assertAlmostEqual(result['threshold_90'], 2.2)
        self.assertAlmostEqual(result['rise_10_90_s'], .8)

    def test_numeric_roundoff_tolerance_does_not_advance_near_crossing(self):
        def actual(t):
            y = np.zeros(len(t))
            y[t >= 1100000] = .9 - 1e-10
            y[t >= 1200000] = .9
            return y
        result = self.metrics(actual)
        self.assertEqual(result['crossing_90']['sample_bracket_us'], [1100000, 1200000])

    def test_short_pulse_unreached_90_and_settling_are_null_not_failure(self):
        result = self.metrics(lambda t: np.maximum(t - 1000000, 0.) / 5000000, end=3000000)
        self.assertIsNotNone(result['crossing_10'])
        self.assertIsNone(result['crossing_90'])
        self.assertIsNone(result['rise_10_90_s'])
        self.assertIsNone(result['settling_5pct_s'])
        self.assertNotIn('failed', result)

    def test_both_crossings_can_share_one_sample_and_keep_resolution(self):
        result = self.metrics(lambda t: (t >= 1000000).astype(float))
        self.assertEqual(result['rise_10_90_s'], 0.)
        self.assertEqual(result['crossing_10']['sample_bracket_us'], [900000, 1000000])
        np.testing.assert_allclose(result['rise_10_90_native_bounds_s'], [0., .1])

    def test_first_crossing_is_not_replaced_by_later_clean_crossing(self):
        def actual(t):
            y = np.zeros(len(t))
            y[t == 1100000] = .95
            y[t >= 2000000] = 1.
            return y
        result = self.metrics(actual)
        self.assertAlmostEqual(result['crossing_90']['first_observed_s'], .1)

    def test_late_exit_from_band_invalidates_early_settling(self):
        def actual(t):
            y = np.ones(len(t)); y[t < 1000000] = 0.; y[t == 3800000] = 1.2
            return y
        result = self.metrics(actual)
        self.assertIsNone(result['settling_5pct_s'])
        self.assertAlmostEqual(result['overshoot_percent'], 20.)

    def test_settling_requires_full_observed_second(self):
        def actual(t):
            return (t >= 3000000).astype(float)
        result = self.metrics(actual)
        self.assertIsNone(result['settling_5pct_s'])  # 3.0 to 3.9 is only .9 s.
        longer = self.metrics(lambda t: (t >= 2900000).astype(float))
        self.assertAlmostEqual(longer['observed_final_in_band_duration_s'], 1.)

    def test_command_end_is_exclusive(self):
        def actual(t):
            y = (t >= 1000000).astype(float); y[t >= 3000000] = 5.; return y
        result = self.metrics(actual, end=3000000)
        self.assertEqual(result['overshoot_percent'], 0.)

    def test_missing_baseline_nonfinite_clock_and_gaps_rejected(self):
        with self.assertRaisesRegex(ValueError, 'baseline'):
            p.response_metrics(np.array([1000000, 1100000]), np.ones(2), 1000000, 1200000, 2.)
        with self.assertRaisesRegex(ValueError, 'strictly increasing'):
            p.response_metrics(np.array([900000, 1000000, 1000000]), np.zeros(3), 1000000, 1200000, 1.)
        with self.assertRaisesRegex(ValueError, 'gap'):
            p.response_metrics(np.array([900000, 1000000, 2000000, 2100000]), np.zeros(4), 1000000, 2200000, 1.)
        with self.assertRaisesRegex(ValueError, 'Nonfinite'):
            self.metrics(lambda t: np.full(len(t), np.nan))

    def test_zero_requested_change_is_undefined_not_zero_rise_time(self):
        with self.assertRaisesRegex(ValueError, 'undefined'):
            self.metrics(lambda t: np.ones(len(t)))


class NativeCommandTests(unittest.TestCase):
    def test_native_position_receipt_not_event_or_takeoff_time(self):
        data = native_fixture().data_list[1].data
        result = p.command_windows('position', events('position'), data)
        self.assertEqual([row['t0_us'] for row in result], [3050000, 11050000])
        self.assertEqual([row['end_us'] for row in result], [11000000, 19000000])
        self.assertEqual([row['display_seconds'] for row in result], [8., 8.])

    def test_original_array_layout_matches_codev_scalar_layout(self):
        first = p.command_windows('position', events('position'), native_fixture().data_list[1].data)
        second = p.command_windows('position', events('position'), native_fixture(array=True).data_list[1].data)
        self.assertEqual(first, second)

    def test_velocity_uses_true_nonzero_pulse_receipts(self):
        result = p.command_windows('velocity', events('velocity'), native_fixture('velocity', True).data_list[1].data)
        self.assertEqual([row['t0_us'] for row in result], [3050000, 9050000])
        self.assertEqual([row['end_us'] for row in result], [5050000, 11050000])
        self.assertTrue(all(row['short_pulse'] for row in result))

    def test_missing_target_change_or_wrong_velocity_pattern_rejected(self):
        data = native_fixture().data_list[1].data
        data['z'][:] = -2.5
        with self.assertRaisesRegex(ValueError, 'Missing received'):
            p.command_windows('position', events('position'), data)
        data = native_fixture('velocity').data_list[1].data
        data['vz'][np.isfinite(data['vz'])] = 0.
        with self.assertRaisesRegex(ValueError, 'sequence'):
            p.command_windows('velocity', events('velocity'), data)

    def test_sample_clock_preferred_and_extra_event_fields_ignored(self):
        local = native_fixture().data_list[0].data
        t, field = p.native_clock(local)
        self.assertEqual(field, 'timestamp_sample')
        self.assertEqual(t[0], 500000)
        self.assertEqual(p.phase_window(events('position'), 'step_up'), (3000000, 11000000))


class InputGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        jobs = [dict(id=f'O{i:03d}', task=task, system=system) for i, (task, system) in
                enumerate(((task, system) for task in p.TASKS for system in p.SYSTEMS), 1)]
        self.manifest = dict(data_root=str(self.root / 'new'), order=[job['id'] for job in jobs], jobs=jobs)
        self.manifest_path = self.root / 'manifest.json'
        self.manifest_path.write_text(json.dumps(self.manifest))
        for job in jobs:
            folder = Path(self.manifest['data_root']) / 'runs' / job['id']
            folder.mkdir(parents=True)
            raw = folder / 'native_00.ulg'
            raw.write_bytes(('synthetic-only-' + job['id']).encode())
            result = dict(job, success=True, independent_replay_passed=True,
                          manifest_sha256=p.sha256(self.manifest_path), events=events(job['task']),
                          logs=[dict(archive=str(raw), bytes=raw.stat().st_size, sha256=p.sha256(raw))])
            (folder / 'result.json').write_text(json.dumps(result))
            (folder / 'origin.json').write_text(json.dumps(dict(x=1., y=2., z=0., heading=0.)))

    def folder(self, identifier='O001'):
        return Path(self.manifest['data_root']) / 'runs' / identifier

    def alter_result(self, change, identifier='O001'):
        file = self.folder(identifier) / 'result.json'
        result = json.loads(file.read_text()); change(result); file.write_text(json.dumps(result))

    def test_valid_exact_eight_inputs_and_largest_archive_selected(self):
        large = self.folder() / 'native_01.ulg'; large.write_bytes(b'larger-synthetic-log-not-a-flight' * 2)
        self.alter_result(lambda result: result['logs'].append(dict(archive=str(large), bytes=large.stat().st_size, sha256=p.sha256(large))))
        unused, records = p.audit_inputs(self.manifest_path)
        self.assertEqual(len(records), 8)
        self.assertEqual(records[0]['path'], large)

    def test_missing_run_is_rejected_without_output_directory(self):
        (self.folder('O008') / 'result.json').unlink()
        output = self.root / 'plots'
        with self.assertRaisesRegex(ValueError, 'Missing evidence'):
            p.generate(self.manifest_path, output)
        self.assertFalse(output.exists())

    def test_first_failed_and_seven_unattempted_cannot_create_figures(self):
        self.alter_result(lambda result: result.update(success=False, independent_replay_passed=False))
        for identifier in (f'O{i:03d}' for i in range(2, 9)):
            (self.folder(identifier) / 'result.json').unlink()
        output = self.root / 'rejected-comparison'
        with self.assertRaisesRegex(ValueError, 'Require success'):
            p.generate(self.manifest_path, output)
        self.assertFalse(output.exists())

    def test_wrong_job_order_or_historical_identifier_rejected(self):
        for mutate in (lambda data: data['jobs'].reverse(),
                       lambda data: data['jobs'][0].update(id='OLD001')):
            content = self.manifest_path.read_text()
            data = json.loads(content)
            mutate(data)
            self.manifest_path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'O001'):
                p.audit_inputs(self.manifest_path)
            self.manifest_path.write_text(content)

    def test_archive_bytes_mismatch_rejected_before_decode(self):
        self.alter_result(lambda result: result['logs'][0].update(bytes=1))
        with self.assertRaisesRegex(ValueError, 'byte count'):
            p.audit_inputs(self.manifest_path)

    def test_failure_or_missing_replay_cannot_enter_plots(self):
        for field in ('success', 'independent_replay_passed'):
            with self.subTest(field=field):
                self.alter_result(lambda result: result.update({field: False}))
                with self.assertRaisesRegex(ValueError, 'Require success'):
                    p.audit_inputs(self.manifest_path)
                self.alter_result(lambda result: result.update({field: True}))

    def test_manifest_fingerprint_and_ulog_hash_mismatch_rejected(self):
        self.alter_result(lambda result: result.update(manifest_sha256='0' * 64))
        with self.assertRaisesRegex(ValueError, 'manifest SHA256'):
            p.audit_inputs(self.manifest_path)
        self.alter_result(lambda result: result.update(manifest_sha256=p.sha256(self.manifest_path)))
        self.alter_result(lambda result: result['logs'][0].update(sha256='0' * 64))
        with self.assertRaisesRegex(ValueError, 'ULog SHA256'):
            p.audit_inputs(self.manifest_path)

    def test_missing_origin_and_external_old_archive_rejected(self):
        origin = self.folder() / 'origin.json'; content = origin.read_text(); origin.unlink()
        with self.assertRaisesRegex(ValueError, 'Missing evidence'):
            p.audit_inputs(self.manifest_path)
        origin.write_text(content)
        old = self.root / 'native_00.ulg'; old.write_bytes(b'old sample')
        self.alter_result(lambda result: result['logs'][0].update(archive=str(old), bytes=old.stat().st_size, sha256=p.sha256(old)))
        with self.assertRaisesRegex(ValueError, 'belong to this new run'):
            p.audit_inputs(self.manifest_path)

    def test_duplicate_selected_ulog_rejected(self):
        first = self.folder() / 'native_00.ulg'; second = self.folder('O002') / 'native_00.ulg'
        second.write_bytes(first.read_bytes())
        self.alter_result(lambda result: result['logs'][0].update(bytes=second.stat().st_size, sha256=p.sha256(second)), 'O002')
        with self.assertRaisesRegex(ValueError, 'Reused native ULog'):
            p.audit_inputs(self.manifest_path)

    def test_existing_output_is_never_overwritten(self):
        output = self.root / 'plots'; output.mkdir()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            p.generate(self.manifest_path, output)

    def test_native_loader_rejects_missing_topic_and_uses_sample_clock(self):
        unused, records = p.audit_inputs(self.manifest_path)
        run = p.load_run(records[0], lambda *args, **kwargs: native_fixture())
        self.assertEqual(run['clock_field'], 'timestamp_sample')
        self.assertEqual(run['responses'][0]['metrics']['t0_us'], 3050000)
        fake = native_fixture(); fake.data_list.pop()
        with self.assertRaisesRegex(ValueError, 'Missing/ambiguous native topic'):
            p.load_run(records[0], lambda *args, **kwargs: fake)

    def test_complete_synthetic_render_separates_six_figures_and_provenance(self):
        output = self.root / 'synthetic-not-flight-plots'
        def loader(path, **kwargs):
            identifier = Path(path).parent.name
            return native_fixture('position' if int(identifier[1:]) <= 4 else 'velocity', array=identifier in ('O002', 'O006'))
        report = p.generate(self.manifest_path, output, ulog_class=loader)
        self.assertEqual(len(report['figures']), 6)
        self.assertEqual(len(list(output.glob('*.png'))), 6)
        self.assertEqual(len(list(output.glob('*.svg'))), 6)
        self.assertEqual(len(report['runs']), 8)
        self.assertTrue(all((output / (name + '.png')).stat().st_size > 1000 for name in report['figures']))
        self.assertIn('n=1', (output / 'README.md').read_text())
        self.assertIn('(position_actual_velocity_xyz.png)', (output / 'README.md').read_text())


if __name__ == '__main__':
    unittest.main()
