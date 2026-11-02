"""Offline contract tests only: no simulator, ROS, MAVLink link or filesystem writes."""

import copy
import importlib.util
import json
import math
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('offboard_task_contract', Path(__file__).with_name('task_contract.py'))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

ORIGIN = dict(x=1.25, y=-0.5, z=0.12, heading=0.75)


class TrajectoryTests(unittest.TestCase):
    def test_quintic_endpoints_and_clamped_tail(self):
        self.assertEqual(c.quintic_state(0, 16, 0, 2.5), (0.0, 0.0, 0.0))
        self.assertEqual(c.quintic_state(16, 16, 0, 2.5), (2.5, 0.0, 0.0))
        self.assertEqual(c.quintic_state(1e300, 16, 0, 2.5), (2.5, 0.0, 0.0))

    def test_climb_monotone_and_bounded(self):
        samples = [c.height_profile('climb', index / 100) for index in range(1601)]
        self.assertTrue(all(0 <= h <= 2.5 and v >= 0 for h, v, _ in samples))
        self.assertTrue(all(a[0] <= b[0] for a, b in zip(samples, samples[1:])))

    def test_quintic_near_endpoints_does_not_overshoot(self):
        times = sorted([0.0, 16.0] + [16 * 10**(-i) for i in range(1, 17)] +
                       [16 * (1 - 10**(-i)) for i in range(1, 17)])
        values = [c.quintic_state(t, 16)[0] for t in times]
        self.assertTrue(all(0 <= value <= 1 for value in values))
        self.assertEqual(values, sorted(values))

    def test_descent_monotone_and_bounded(self):
        samples = [c.height_profile('descend', index / 100) for index in range(1601)]
        self.assertTrue(all(0.3 <= h <= 2.5 and v <= 0 for h, v, _ in samples))
        self.assertTrue(all(a[0] >= b[0] for a, b in zip(samples, samples[1:])))

    def test_exact_maximum_climb_and_descent_speeds(self):
        self.assertEqual(c.quintic_max_speed(0, 2.5, 16), 0.29296875)
        self.assertAlmostEqual(c.quintic_max_speed(2.5, 0.3, 16), 0.2578125)
        for phase, start, end in [('climb', 0, 2.5), ('descend', 2.5, 0.3)]:
            maximum = c.quintic_max_speed(start, end, 16)
            self.assertAlmostEqual(abs(c.height_profile(phase, 8)[1]), maximum)
            self.assertLess(maximum, c.SAFETY_LIMITS['vertical_speed_m_s'])

    def test_analytic_derivatives_match_finite_difference(self):
        dt = 1e-4
        for t in (1.0, 4.0, 8.0, 12.0, 15.0):
            a = c.quintic_state(t - dt, 16, 0, 2.5)
            b = c.quintic_state(t, 16, 0, 2.5)
            d = c.quintic_state(t + dt, 16, 0, 2.5)
            self.assertAlmostEqual((d[0] - a[0]) / (2 * dt), b[1], places=8)
            self.assertAlmostEqual((d[1] - a[1]) / (2 * dt), b[2], places=8)

    def test_smooth_stage_handoffs(self):
        for end_phase, start_phase, end_time in [('climb', 'recover', 16), ('recover', 'hover', 15)]:
            self.assertEqual(c.height_profile(end_phase, end_time), c.height_profile(start_phase, 0))
        self.assertEqual(c.height_profile('recover', 0), c.height_profile('descend', 0))

    def test_height_steps_are_exact_and_only_z_changes(self):
        before = c.make_target('hover', 10, ORIGIN)
        up = c.make_target('step_up', 0, ORIGIN)
        down = c.make_target('step_down', 0, ORIGIN)
        self.assertAlmostEqual(before['z'] - up['z'], 0.3)
        self.assertEqual(before, down)
        self.assertEqual(up, c.make_target('step_up', 8, ORIGIN))
        self.assertEqual({k: v for k, v in before.items() if k != 'z'},
                         {k: v for k, v in up.items() if k != 'z'})

    def test_ned_sign_and_descent_handoff_height(self):
        start = c.make_target('prestream', 0, ORIGIN)
        top = c.make_target('climb', 16, ORIGIN)
        bottom = c.make_target('descend', 16, ORIGIN)
        self.assertEqual(start['z'], ORIGIN['z'])
        self.assertAlmostEqual(top['z'], ORIGIN['z'] - 2.5)
        self.assertAlmostEqual(bottom['z'], ORIGIN['z'] - 0.3)
        self.assertLess(top['z'], bottom['z'])

    def test_velocity_phase_has_no_position_profile(self):
        with self.assertRaises(ValueError):
            c.height_profile('velocity', 0)


class VelocityTests(unittest.TestCase):
    def test_exact_pulse_boundaries(self):
        expected = [(0, 0.2), (1.999999, 0.2), (2, 0), (5.999999, 0),
                    (6, -0.2), (7.999999, -0.2), (8, 0), (11.999999, 0), (12, 0), (99, 0)]
        for elapsed, value in expected:
            with self.subTest(elapsed=elapsed):
                self.assertEqual(c.upward_velocity(elapsed), value)
                self.assertEqual(c.make_target('velocity', elapsed, ORIGIN)['vz'], -value)

    def test_integral_is_zero_after_both_pulses(self):
        for elapsed, expected in [(0, 0), (1, 0.2), (2, 0.4), (4, 0.4),
                                  (6, 0.4), (7, 0.2), (8, 0), (12, 0), (1e300, 0)]:
            self.assertAlmostEqual(c.velocity_height_offset(elapsed), expected)

    def test_numeric_integral_agrees_with_analytic_integral(self):
        dt = 0.001
        integral = 0.0
        for i in range(12000):
            integral += c.upward_velocity((i + 0.5) * dt) * dt
        self.assertAlmostEqual(integral, c.velocity_height_offset(12), places=12)

    def test_xy_position_hold_and_z_position_ignored(self):
        for elapsed in (0, 2, 6, 8, 12):
            target = c.make_target('velocity', elapsed, ORIGIN)
            self.assertEqual(target['kind'], 'z_velocity')
            self.assertEqual((target['x'], target['y'], target['yaw']),
                             (ORIGIN['x'], ORIGIN['y'], ORIGIN['heading']))
            self.assertEqual((target['z'], target['vx'], target['vy']), (0, 0, 0))

    def test_reference_integral_stays_inside_height_limits(self):
        values = [2.5 + c.velocity_height_offset(i / 100) for i in range(1201)]
        self.assertEqual(min(values), 2.5)
        self.assertEqual(max(values), 2.9)


class WireContractTests(unittest.TestCase):
    def test_position_mask_enables_all_position_and_yaw_only(self):
        self.assertEqual(c.POSITION_MASK, 2552)
        self.assertEqual(c.POSITION_MASK & 7, 0)
        self.assertEqual(c.POSITION_MASK & 56, 56)
        self.assertEqual(c.POSITION_MASK & 448, 448)
        self.assertEqual(c.POSITION_MASK & (512 | 1024), 0)
        self.assertEqual(c.POSITION_MASK & 2048, 2048)

    def test_mixed_mask_enables_xy_position_z_velocity_yaw_only(self):
        self.assertEqual(c.Z_VELOCITY_MASK, 2524)
        self.assertEqual(c.Z_VELOCITY_MASK & 7, 4)
        self.assertEqual(c.Z_VELOCITY_MASK & 56, 24)
        self.assertEqual(c.Z_VELOCITY_MASK & 448, 448)
        self.assertEqual(c.Z_VELOCITY_MASK & (512 | 1024), 0)
        self.assertEqual(c.Z_VELOCITY_MASK & 2048, 2048)

    def test_every_axis_has_a_target_and_xy_pairs_match(self):
        for mask in (c.POSITION_MASK, c.Z_VELOCITY_MASK):
            active = lambda bit: not (mask & (1 << bit))
            self.assertEqual(active(0), active(1))
            self.assertEqual(active(3), active(4))
            for axis in range(3):
                self.assertTrue(active(axis) or active(axis + 3) or active(axis + 6))

    def test_no_derived_feedforward_is_sent_during_climb_or_descent(self):
        for phase in ('climb', 'descend'):
            self.assertNotEqual(c.height_profile(phase, 8)[1], 0)
            target = c.make_target(phase, 8, ORIGIN)
            self.assertEqual((target['vx'], target['vy'], target['vz']), (0, 0, 0))
            self.assertEqual(target['type_mask'], c.POSITION_MASK)

    def test_all_outputs_have_exact_finite_json_wire_fields(self):
        expected = {'kind', 'x', 'y', 'z', 'vx', 'vy', 'vz', 'yaw', 'type_mask'}
        for phase in c.Phase:
            for elapsed in (0, 1, 2, 6, 8, 12, 16, 100):
                target = c.make_target(phase, elapsed, ORIGIN)
                self.assertEqual(set(target), expected)
                self.assertEqual(json.loads(json.dumps(target, allow_nan=False)), target)

    def test_masks_cannot_default_to_zero_or_change_control_level(self):
        for phase in ('hover', 'velocity'):
            for mask in (0, -1, 65535, 2503, 3576, True, 2524.0):
                target = c.make_target(phase, 0, ORIGIN)
                target['type_mask'] = mask
                with self.subTest(phase=phase, mask=mask), self.assertRaises(ValueError):
                    c.validate_target(target)

    def test_nonzero_ignored_fields_rejected(self):
        for phase, field in [('hover', 'vx'), ('hover', 'vy'), ('hover', 'vz'),
                             ('velocity', 'z'), ('velocity', 'vx'), ('velocity', 'vy')]:
            target = c.make_target(phase, 0, ORIGIN)
            target[field] = 0.01
            with self.subTest(phase=phase, field=field), self.assertRaises(ValueError):
                c.validate_target(target)

    def test_velocity_amplitude_cannot_be_expanded_or_retuned(self):
        for velocity in (-0.2001, 0.2001, 1.0, 0.1):
            target = c.make_target('velocity', 0, ORIGIN)
            target['vz'] = velocity
            with self.subTest(velocity=velocity), self.assertRaises(ValueError):
                c.validate_target(target)

    def test_missing_extra_and_unknown_kind_rejected(self):
        for mutate in (lambda t: t.pop('yaw'), lambda t: t.update(afx=0),
                       lambda t: t.update(kind='acceleration')):
            target = c.make_target('hover', 0, ORIGIN)
            mutate(target)
            with self.assertRaises(ValueError):
                c.validate_target(target)


class ValidationTests(unittest.TestCase):
    def test_invalid_times_rejected_in_every_entry_point(self):
        for invalid in (-0.1, float('nan'), float('inf'), -float('inf'), True, None, '1'):
            for call in (lambda t: c.make_target('hover', t, ORIGIN),
                         lambda t: c.height_profile('climb', t), c.upward_velocity,
                         c.velocity_height_offset, lambda t: c.quintic_state(t, 16)):
                with self.subTest(value=invalid, call=call), self.assertRaises(ValueError):
                    call(invalid)

    def test_invalid_dt_and_duration_rejected(self):
        for invalid in (0, -1, float('nan'), float('inf'), True, None, '0.1'):
            for call in (c.validate_dt, lambda dt: c.quintic_state(1, dt),
                         lambda dt: c.quintic_max_speed(0, 2.5, dt)):
                with self.subTest(value=invalid), self.assertRaises(ValueError):
                    call(invalid)
        self.assertEqual(c.validate_dt(0.05), 0.05)

    def test_invalid_origin_field_and_absent_origin_rejected(self):
        for key in ORIGIN:
            for invalid in (float('nan'), float('inf'), True, None, '0', 1e39):
                origin = dict(ORIGIN, **{key: invalid})
                with self.subTest(key=key, value=invalid), self.assertRaises(ValueError):
                    c.make_target('hover', 0, origin)
            origin = dict(ORIGIN)
            del origin[key]
            with self.assertRaises(ValueError):
                c.make_target('hover', 0, origin)
        for origin in (None, (), 3, 'origin'):
            with self.assertRaises(ValueError):
                c.make_target('hover', 0, origin)

    def test_nonfinite_or_out_of_range_wire_payload_rejected(self):
        for key in ('x', 'y', 'z', 'vx', 'vy', 'vz', 'yaw'):
            for invalid in (float('nan'), float('inf'), True, 1e39):
                target = c.make_target('hover', 0, ORIGIN)
                target[key] = invalid
                with self.subTest(key=key, value=invalid), self.assertRaises(ValueError):
                    c.validate_target(target)

    def test_extreme_numbers_fail_closed(self):
        for args in ((1, 16, -(10**1000), 1), (1e-301, 1e-300, 0, 2.5),
                     (8, 16, -1e308, 1e308)):
            with self.assertRaises(ValueError):
                c.quintic_state(*args)

    def test_unknown_phases_are_not_silently_hover(self):
        for phase in ('takeoff', 'land', 'AUTO_LAND', '', None, 0, []):
            with self.subTest(phase=phase), self.assertRaises(ValueError):
                c.make_target(phase, 0, ORIGIN)

    def test_input_origin_is_not_modified(self):
        original = copy.deepcopy(ORIGIN)
        for phase in c.Phase:
            c.make_target(phase, 8, ORIGIN)
        self.assertEqual(original, ORIGIN)


class ScopeTests(unittest.TestCase):
    def test_exact_eight_attempts_pid_first_in_each_task(self):
        expected = tuple((task, system) for task in ('position', 'velocity')
                         for system in ('PID', 'STA2', 'RSTA', 'RISTA'))
        self.assertEqual(c.MAX_ATTEMPTS, 8)
        self.assertEqual(c.validate_batch_order(expected), expected)
        self.assertEqual(len(set(expected)), 8)
        self.assertEqual(c.BATCH_ORDER[0], ('position', 'PID'))
        self.assertEqual(c.BATCH_ORDER[4], ('velocity', 'PID'))

    def test_no_reorder_duplicate_omission_or_extra_task(self):
        invalid = [c.BATCH_ORDER[::-1], c.BATCH_ORDER[:-1], c.BATCH_ORDER + (('position', 'PID'),),
                   (c.BATCH_ORDER[0],) * 8, (('yaw', 'PID'),) + c.BATCH_ORDER[1:]]
        for order in invalid:
            with self.subTest(order=order), self.assertRaises(ValueError):
                c.validate_batch_order(order)

    def test_budget_cannot_be_expanded_or_reinterpreted(self):
        for attempts in (0, 4, 7, 9, 16, 8.0, True, '8', None):
            with self.subTest(attempts=attempts), self.assertRaises(ValueError):
                c.validate_batch_order(c.BATCH_ORDER, attempts)

    def test_phase_counts_and_unscored_landing_tail(self):
        self.assertEqual(len(c.TASK_PHASES['position']), 8)
        self.assertEqual(len(c.TASK_PHASES['velocity']), 7)
        self.assertEqual(c.TASK_PHASES['position'],
                         ('prestream', 'climb', 'recover', 'hover', 'step_up', 'step_down', 'recover', 'descend'))
        self.assertEqual(c.TASK_PHASES['velocity'],
                         ('prestream', 'climb', 'recover', 'hover', 'velocity', 'recover', 'descend'))
        for phases in c.TASK_PHASES.values():
            self.assertEqual(phases[-1], 'descend')
            self.assertNotIn('land', phases)

    def test_frozen_durations_and_stable_window(self):
        self.assertEqual(dict(c.PHASE_DURATION_S), dict(climb=16, hover=10, step_up=8, step_down=8,
                                                      velocity=12, descend=16))
        self.assertEqual((c.STABLE_REQUIRED_S, c.STABLE_TIMEOUT_S), (3, 15))
        self.assertEqual(sum(c.PHASE_DURATION_S[p] for p in c.TASK_PHASES['position']
                             if p in c.PHASE_DURATION_S), 58)
        self.assertEqual(sum(c.PHASE_DURATION_S[p] for p in c.TASK_PHASES['velocity']
                             if p in c.PHASE_DURATION_S), 54)

    def test_safety_envelope_preserves_inherited_limits(self):
        self.assertEqual(dict(c.SAFETY_LIMITS), dict(tilt_deg=15, xy_speed_m_s=1, xy_displacement_m=2,
            height_range_m=(-0.5, 4), vertical_speed_m_s=3.5,
            hover_height_deviation_m=1, hover_vertical_speed_m_s=0.6))

    def test_protocol_mappings_are_read_only(self):
        for mapping, key in [(c.SAFETY_LIMITS, 'tilt_deg'), (c.ENTRY_LIMITS, 'stable_s'),
                             (c.PHASE_DURATION_S, 'hover'), (c.TASK_PHASES, 'position')]:
            with self.assertRaises(TypeError):
                mapping[key] = 99


if __name__ == '__main__':
    unittest.main()
