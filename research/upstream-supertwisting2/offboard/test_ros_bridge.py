"""Offline bridge tests: no ROS runtime, UDP socket, or simulator required."""

import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import ros_bridge as bridge


NOW = 2000.0
CONTROL = {'generation': 1, 'phase': 'climb', 'start_us': 1000000,
           'origin': {'x': 1.25, 'y': -0.5, 'z': 0.12, 'heading': 0.75}, 'enabled': True}
TELEMETRY = {'time_boot_ms': 9000, 'sim_us': 9000000, 'wall_stamp': NOW,
             'x': 1.25, 'y': -0.5, 'z': -1.0, 'vx': 0.0, 'vy': 0.0, 'vz': -0.2}


def envelope(control=None, seq=1, telemetry=None):
    return bridge.make_envelope(control or CONTROL, telemetry or TELEMETRY, seq, NOW)


class ControlTests(unittest.TestCase):
    def test_missing_file_waits_then_valid_atomic_file_loads(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'control.json'
            reader = bridge.ControlReader(path)
            self.assertIsNone(reader.read())
            bridge.atomic_json(path, CONTROL)
            self.assertEqual(reader.read(), CONTROL)

    def test_existing_invalid_file_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'control.json'
            path.write_text('{', encoding='utf-8')
            with self.assertRaises(ValueError):
                bridge.ControlReader(path).read()

    def test_generation_must_advance_for_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'control.json'
            reader = bridge.ControlReader(path)
            bridge.atomic_json(path, CONTROL)
            reader.read()
            bridge.atomic_json(path, dict(CONTROL, phase='hover'))
            with self.assertRaisesRegex(ValueError, 'mutated'):
                reader.read()
            bridge.atomic_json(path, dict(CONTROL, generation=0))
            with self.assertRaisesRegex(ValueError, 'regressed'):
                reader.read()
            bridge.atomic_json(path, dict(CONTROL, generation=2, phase='hover'))
            self.assertEqual(reader.read()['phase'], 'hover')

    def test_invalid_control_types_and_fields(self):
        for key, value in [('generation', True), ('generation', -1), ('start_us', 1.5),
                           ('enabled', 1), ('phase', 'land'), ('origin', {}),
                           ('origin', dict(CONTROL['origin'], heading=float('nan')))]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                bridge.validate_control(dict(CONTROL, **{key: value}))
        with self.assertRaises(ValueError):
            bridge.validate_control(dict(CONTROL, command='arm'))

    def test_strict_json_rejects_nonfinite_and_duplicate_keys(self):
        for text in ('{"x":NaN}', '{"x":Infinity}', '{"x":1,"x":2}'):
            with self.assertRaises(ValueError):
                bridge.strict_json_loads(text)


class ClockTests(unittest.TestCase):
    def test_elapsed_uses_native_clock(self):
        value = envelope()
        self.assertEqual(value['elapsed_s'], 8.0)
        self.assertEqual(value['target']['z'], CONTROL['origin']['z'] - 1.25)
        self.assertEqual(bridge.make_envelope(CONTROL, dict(TELEMETRY, wall_stamp=NOW + 100), 2,
                                             NOW + 100)['elapsed_s'], 8.0)

    def test_bounded_future_phase_start_is_clamped_to_zero(self):
        control = dict(CONTROL, start_us=TELEMETRY['sim_us'] + 100000)
        self.assertEqual(envelope(control)['elapsed_s'], 0.0)
        with self.assertRaisesRegex(ValueError, 'too far ahead'):
            envelope(dict(control, start_us=control['start_us'] + 1))

    def test_stale_telemetry_and_regressing_native_samples_fail(self):
        with self.assertRaises(ValueError):
            bridge.validate_telemetry(dict(TELEMETRY, wall_stamp=NOW - 0.501), NOW)
        with self.assertRaises(ValueError):
            bridge.validate_telemetry(TELEMETRY, NOW, TELEMETRY['sim_us'] + 1000)
        self.assertEqual(bridge.validate_telemetry(TELEMETRY, NOW, TELEMETRY['sim_us']), TELEMETRY)

    def test_inconsistent_native_timestamps_fail(self):
        for value in (dict(TELEMETRY, sim_us=9000001), dict(TELEMETRY, time_boot_ms=True),
                      dict(TELEMETRY, time_boot_ms=-1), dict(TELEMETRY, vx=float('inf'))):
            with self.assertRaises(ValueError):
                bridge.validate_telemetry(value, NOW)

    def test_disabled_control_cannot_publish(self):
        with self.assertRaises(ValueError):
            envelope(dict(CONTROL, enabled=False))

    def test_fresh_repeated_packets_cannot_hide_stagnant_native_clock(self):
        clock = bridge.NativeClockGuard()
        clock.observe(9000000, 10.0)
        for offset in (.1, .2, .4, .5):
            refreshed_packet = dict(TELEMETRY, wall_stamp=NOW + offset)
            bridge.validate_telemetry(refreshed_packet, NOW + offset)
            clock.observe(refreshed_packet['sim_us'], 10.0 + offset)
            clock.check(10.0 + offset, enabled=True)
        clock.observe(9000000, 10.501)
        with self.assertRaisesRegex(ValueError, 'has not advanced'):
            clock.check(10.501, enabled=True)
        clock.check(10.501, enabled=False)

    def test_native_clock_progress_resets_stagnation_watchdog(self):
        clock = bridge.NativeClockGuard()
        self.assertIsNone(clock.check(10, enabled=True))
        clock.observe(9000000, 10.0)
        clock.observe(9001000, 10.4)
        self.assertAlmostEqual(clock.check(10.8, enabled=True), .4)
        with self.assertRaises(ValueError):
            clock.observe(9000000, 10.9)


class GuardTests(unittest.TestCase):
    def test_duplicate_native_time_is_valid_zero_order_hold(self):
        guard = bridge.TargetGuard()
        self.assertTrue(guard.accept(envelope(seq=1), CONTROL, NOW))
        self.assertTrue(guard.accept(envelope(seq=2), CONTROL, NOW))

    def test_duplicate_or_regressing_sequence_fails(self):
        for next_seq in (1, 2):
            guard = bridge.TargetGuard()
            guard.accept(envelope(seq=2), CONTROL, NOW)
            with self.assertRaisesRegex(ValueError, 'sequence'):
                guard.accept(envelope(seq=next_seq), CONTROL, NOW)

    def test_old_queued_target_is_dropped_after_atomic_phase_change(self):
        guard = bridge.TargetGuard()
        old_queued = envelope(seq=2)
        guard.accept(envelope(seq=1), CONTROL, NOW)
        next_control = dict(CONTROL, generation=2, phase='hover', start_us=9000000)
        self.assertFalse(guard.accept(old_queued, next_control, NOW))
        self.assertEqual(guard.rejected_stale_generation, 1)
        self.assertTrue(guard.accept(envelope(next_control, seq=3), next_control, NOW))
        self.assertEqual(guard.last_seq, 3)

    def test_future_generation_and_phase_mismatch_fail(self):
        for value in (dict(envelope(), generation=2), dict(envelope(), phase='hover')):
            with self.assertRaises(ValueError):
                bridge.TargetGuard().accept(value, CONTROL, NOW)

    def test_disabled_receiver_ceases_targets(self):
        guard = bridge.TargetGuard()
        self.assertFalse(guard.accept(envelope(), dict(CONTROL, enabled=False), NOW))
        self.assertEqual(guard.rejected_disabled, 1)

    def test_modified_target_mask_elapsed_or_phase_rejected(self):
        modifications = [lambda value: value['target'].update(type_mask=0),
                         lambda value: value['target'].update(z=-99.0),
                         lambda value: value.update(elapsed_s=7.9),
                         lambda value: value.update(phase='unrecognized'),
                         lambda value: value.update(phase='velocity'),
                         lambda value: value.update(sim_us=9000001)]
        for modify in modifications:
            value = copy.deepcopy(envelope())
            modify(value)
            with self.subTest(modify=modify), self.assertRaises(ValueError):
                bridge.TargetGuard().accept(value, CONTROL, NOW)

    def test_stale_or_future_wall_stamp_rejected(self):
        for stamp in (NOW - .501, NOW + .002, float('nan'), float('inf')):
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                bridge.TargetGuard().accept(dict(envelope(), wall_stamp=stamp), CONTROL, NOW)

    def test_regressing_native_time_rejected(self):
        guard = bridge.TargetGuard()
        guard.accept(envelope(), CONTROL, NOW)
        earlier = dict(TELEMETRY, sim_us=8999000, time_boot_ms=8999)
        with self.assertRaisesRegex(ValueError, 'simulation time regressed'):
            guard.accept(envelope(seq=2, telemetry=earlier), CONTROL, NOW)

    def test_nonfinite_envelope_fields_rejected(self):
        for key in ('seq', 'generation', 'sim_us', 'wall_stamp', 'elapsed_s'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                bridge.TargetGuard().accept(dict(envelope(), **{key: float('nan')}), CONTROL, NOW)


class WireTests(unittest.TestCase):
    def test_position_payload_has_explicit_mask_and_ignored_zero_fields(self):
        value = envelope()
        fields = bridge.wire_fields(value['target'], value['sim_us'])
        self.assertEqual(fields['type_mask'], 2552)
        self.assertEqual(fields['coordinate_frame'], 1)
        self.assertEqual((fields['target_system'], fields['target_component']), (1, 1))
        self.assertEqual(fields['time_boot_ms'], 9000)
        for key in ('vx', 'vy', 'vz', 'afx', 'afy', 'afz', 'yaw_rate'):
            self.assertEqual(fields[key], 0.0)
        self.assertEqual(fields['z'], bridge.float32(value['target']['z']))

    def test_mixed_z_velocity_payload_keeps_xy_and_yaw(self):
        control = dict(CONTROL, phase='velocity', start_us=9000000)
        value = envelope(control)
        fields = bridge.wire_fields(value['target'], value['sim_us'])
        self.assertEqual(fields['type_mask'], 2524)
        self.assertEqual(fields['vz'], bridge.float32(-0.2))
        self.assertEqual((fields['x'], fields['y'], fields['yaw']), (1.25, -0.5, 0.75))
        self.assertEqual(fields['z'], 0.0)

    def test_all_three_velocity_pulse_values_have_exact_float32_wire_values(self):
        origin = CONTROL['origin']
        for elapsed, expected_vz in ((0, -0.2), (2, 0.0), (6, 0.2), (8, 0.0)):
            target = bridge.make_target('velocity', elapsed, origin)
            fields = bridge.wire_fields(target, 9000000)
            self.assertEqual(fields['type_mask'], 2524)
            self.assertEqual(fields['vz'], bridge.float32(expected_vz))

    def test_exact_local_peer_and_native_system_required(self):
        bridge.check_peer(('127.0.0.1', 14580))
        bridge.check_native_source(1, 1)
        for peer in (('127.0.0.1', 14550), ('127.0.0.2', 14580), ('0.0.0.0', 14580)):
            with self.assertRaises(ValueError):
                bridge.check_peer(peer)
        for source in ((2, 1), (1, 2), (245, 191)):
            with self.assertRaises(ValueError):
                bridge.check_native_source(*source)

    def test_explicit_ros_isolation_environment_required(self):
        with mock.patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(ValueError):
                bridge.assert_isolated_environment()
        with mock.patch.dict('os.environ', {'ROS_DOMAIN_ID': '42', 'ROS_LOCALHOST_ONLY': '1'}, clear=True):
            bridge.assert_isolated_environment()

    def test_default_dry_run_never_calls_runtime(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(bridge, 'execute') as execute:
            output = Path(temporary) / 'out'
            result = bridge.main(['--control', str(Path(temporary) / 'absent.json'), '--output', str(output)])
            self.assertEqual(result, 0)
            execute.assert_not_called()
            receipt = json.loads((output / 'receipt.json').read_text())
            self.assertTrue(receipt['dry_run'])
            self.assertEqual(receipt['sent_count'], 0)
            self.assertFalse((output / 'sent.jsonl').exists())

    def test_runtime_error_produces_atomic_fatal_and_nonzero(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(bridge, 'execute', side_effect=ValueError('test fault')):
            result = bridge.main(['--control', str(Path(temporary) / 'absent.json'), '--output', temporary, '--execute'])
            self.assertEqual(result, 1)
            fatal = json.loads((Path(temporary) / 'fatal.json').read_text())
            self.assertEqual(fatal['status'], 'fatal')
            self.assertEqual(fatal['error'], 'test fault')

    def test_rerun_refusal_preserves_existing_evidence_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(bridge, 'execute') as execute:
            output = Path(temporary)
            original = {'fatal.json': b'{"error":"original failure"}\n',
                        'receipt.json': b'{"status":"original receipt"}\n',
                        'sent.jsonl': b'{"seq":17}\n'}
            for name, data in original.items():
                (output / name).write_bytes(data)
            for execute_flag in ([], ['--execute']):
                result = bridge.main(['--control', str(output / 'absent.json'), '--output', temporary] + execute_flag)
                self.assertEqual(result, 1)
                execute.assert_not_called()
                for name, data in original.items():
                    self.assertEqual((output / name).read_bytes(), data)


class ActualMavlinkWireTests(unittest.TestCase):
    """Optional pure serialization tests; these never open UDP or import ROS."""

    def dialect(self):
        try:
            from pymavlink.dialects.v20 import common
        except ImportError:
            self.skipTest('pymavlink not on this Python path; pure helper tests remain available')
        return common

    def test_56_exact_packet_round_trips_include_both_masks_and_all_pulses(self):
        common = self.dialect()
        tx = common.MAVLink(None, srcSystem=bridge.SOURCE_SYSTEM, srcComponent=bridge.SOURCE_COMPONENT)
        count = 0
        masks, pulses = set(), set()
        for phase in bridge.Phase:
            for elapsed in (0, 1.5, 2, 6, 8, 12, 16):
                target = bridge.make_target(phase, elapsed, CONTROL['origin'])
                fields = bridge.wire_fields(target, 12345000)
                packet = common.MAVLink_set_position_target_local_ned_message(**fields).pack(tx)
                decoded = common.MAVLink(None).parse_char(packet)
                self.assertEqual(decoded.get_type(), 'SET_POSITION_TARGET_LOCAL_NED')
                self.assertEqual(decoded.get_srcSystem(), 245)
                self.assertEqual(decoded.get_srcComponent(), 191)
                self.assertEqual({key: getattr(decoded, key) for key in fields}, fields)
                masks.add(decoded.type_mask)
                if phase == bridge.Phase.VELOCITY:
                    pulses.add(decoded.vz)
                count += 1
        self.assertEqual(count, 56)
        self.assertEqual(masks, {2552, 2524})
        self.assertEqual(pulses, {bridge.float32(-.2), 0.0, bridge.float32(.2)})

    def test_heartbeat_is_onboard_controller_and_never_gcs(self):
        common = self.dialect()
        tx = common.MAVLink(None, srcSystem=bridge.SOURCE_SYSTEM, srcComponent=bridge.SOURCE_COMPONENT)
        heartbeat = common.MAVLink_heartbeat_message(common.MAV_TYPE_ONBOARD_CONTROLLER,
            common.MAV_AUTOPILOT_INVALID, 0, 0, common.MAV_STATE_ACTIVE, 3)
        decoded = common.MAVLink(None).parse_char(heartbeat.pack(tx))
        self.assertEqual(decoded.type, common.MAV_TYPE_ONBOARD_CONTROLLER)
        self.assertNotEqual(decoded.type, common.MAV_TYPE_GCS)
        self.assertEqual((decoded.get_srcSystem(), decoded.get_srcComponent()), (245, 191))


if __name__ == '__main__':
    unittest.main()
